"""Thực thi và điều phối các tác vụ phân tích bài đăng bằng Antigravity CLI."""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.l1_router import TYPE_GROUP
from src.agent.prefix import prefix_hash
from src.core.staging import safe_atomic_write, safe_json_dump
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = PROJECT_ROOT / "data" / "prefix" / "ARTICLE_SYSTEM_CORE.md"
DEFAULT_MODEL = "gemini-3.8-flash-low"
DEFAULT_TIMEOUT_SECONDS = 600

# Ký tự có dấu tiếng Việt phục vụ kiểm tra bảo toàn dấu.
_VIETNAMESE_DIACRITICS_RE = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


@dataclass
class AgyExecutionResult:
    """Kết quả thực thi một lô bài viết qua Antigravity CLI.

    Attributes:
        ok: Trạng thái thực thi đạt yêu cầu hay không.
        batch_id: Mã định danh của lô bài viết.
        status: Phân loại trạng thái (OK, FATAL, RETRYABLE, QUOTA, TIMEOUT, VIOLATION, PARTIAL, SOFT_FAIL).
        exit_code: Mã thoát của tiến trình agy.
        records: Danh sách bản ghi trích xuất thành công.
        usage: Thông tin số lượng token sử dụng.
        latency_seconds: Thời gian thực thi tính bằng giây.
        error_message: Thông điệp lỗi chi tiết nếu có.
    """

    ok: bool
    batch_id: str
    status: str
    exit_code: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_seconds: float = 0.0
    error_message: str = ""


def has_vietnamese_diacritics(text: str) -> bool:
    """Kiểm tra chuỗi văn bản có chứa ký tự tiếng Việt có dấu hay không.

    Args:
        text: Chuỗi văn bản cần kiểm tra.

    Returns:
        True nếu chuỗi có ít nhất một ký tự tiếng Việt có dấu.
    """
    return bool(_VIETNAMESE_DIACRITICS_RE.search(text or ""))


def build_sandbox_profile(profile_dir: Path, core_text: str) -> dict[str, Path]:
    """Khởi tạo cấu hình hồ sơ làm việc cô lập cho Antigravity CLI.

    Args:
        profile_dir: Thư mục gốc chứa hồ sơ worker.
        core_text: Toàn văn nội dung tiền tố hệ thống ARTICLE_SYSTEM_CORE.

    Returns:
        Từ điển đường dẫn các tệp cấu hình đã khởi tạo.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)

    # 1. Agent definition toàn cục trong hồ sơ worker
    agents_dir = profile_dir / ".gemini" / "config" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_path = agents_dir / "article-processor.md"

    frontmatter = (
        "---\n"
        "name: article-processor\n"
        "description: Chuyên gia phân tích tin tức tài chính và trích xuất thực thể\n"
        "tools: []\n"
        "excludeDefaultComponents: true\n"
        "inheritCustomizations: false\n"
        "---\n"
    )
    agent_content = frontmatter + (core_text or "")
    agent_path.write_text(agent_content, encoding="utf-8")

    # 2. settings.json cô lập hoàn toàn quyền hạn
    cli_dir = profile_dir / ".gemini" / "antigravity-cli"
    cli_dir.mkdir(parents=True, exist_ok=True)
    settings_path = cli_dir / "settings.json"
    settings_data = {
        "permissions": {"allow": []},
        "trustedWorkspaces": [],
    }
    settings_path.write_text(json.dumps(settings_data, indent=2), encoding="utf-8")

    # 3. hooks.json phòng thủ chặn đứng mọi lượt gọi công cụ
    config_dir = profile_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    hooks_path = config_dir / "hooks.json"
    hooks_data = {
        "hooks": [
            {
                "event": "PreToolUse",
                "matcher": "*",
                "decision": "deny",
            }
        ]
    }
    hooks_path.write_text(json.dumps(hooks_data, indent=2), encoding="utf-8")

    return {
        "agent": agent_path,
        "settings": settings_path,
        "hooks": hooks_path,
    }


def salvage_json_records(text: str) -> list[dict[str, Any]]:
    """Trích xuất và khôi phục mảng bản ghi JSON từ chuỗi phản hồi của mô hình.

    Args:
        text: Chuỗi văn bản thô do mô hình trả về.

    Returns:
        Danh sách các từ điển bản ghi đã bóc tách.

    Raises:
        ValueError: Khi không tìm thấy cấu trúc JSON hợp lệ.
    """
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("Phản hồi rỗng.")

    # Loại bỏ khối markdown nếu mô hình bọc trong ```json ... ```
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    # Thử bóc trực tiếp đối tượng mảng JSON
    try:
        data = json.loads(stripped)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):
            if "r" in data and isinstance(data["r"], list):
                return [d for d in data["r"] if isinstance(d, dict)]
            if "records" in data and isinstance(data["records"], list):
                return [d for d in data["records"] if isinstance(d, dict)]
    except json.JSONDecodeError:
        pass

    # Tìm mảng ngoài cùng bằng chỉ số ngoặc vuông
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = stripped[start : end + 1]
        try:
            arr = json.loads(snippet)
            if isinstance(arr, list):
                return [d for d in arr if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass

    raise ValueError("Không thể bóc tách mảng JSON từ phản hồi.")


def validate_records(
    records: list[dict[str, Any]], packet_items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Kiểm tra tính hợp lệ về mặt miền nghiệp vụ của các bản ghi phân tích.

    Args:
        records: Danh sách bản ghi do mô hình trả về.
        packet_items: Danh sách các bài viết trong gói công việc đầu vào.

    Returns:
        Cặp giá trị gồm danh sách bản ghi hợp lệ và danh sách thông báo lỗi.
    """
    valid_records: list[dict[str, Any]] = []
    errors: list[str] = []

    item_map = {item.get("i"): item for item in packet_items if "i" in item}
    valid_groups = set(TYPE_GROUP.keys())

    for idx, rec in enumerate(records):
        item_i = rec.get("i")
        if item_i is None or item_i not in item_map:
            errors.append(f"Bản ghi #{idx}: Chỉ số 'i'={item_i} không khớp bài nào trong packet.")
            continue

        raw_item = item_map[item_i]
        title = raw_item.get("t") or ""
        paragraphs = raw_item.get("p") or []

        # 1. Kiểm tra nhóm thực thể
        entities = rec.get("e") or []
        invalid_entities = False
        if not isinstance(entities, list):
            errors.append(f"Bài i={item_i}: Trường 'e' không phải mảng.")
            continue

        for ent in entities:
            if not (isinstance(ent, list) and len(ent) >= 2):
                invalid_entities = True
                break
            grp = str(ent[1]).strip().upper()
            if grp not in valid_groups:
                errors.append(f"Bài i={item_i}: Mã nhóm '{grp}' không thuộc 11 nhóm chuẩn.")
                invalid_entities = True
                break

        if invalid_entities:
            continue

        # 2. Kiểm tra chỉ số trích dẫn
        citations = rec.get("c") or []
        if not isinstance(citations, list) or len(citations) < 1:
            errors.append(f"Bài i={item_i}: Trường trích dẫn 'c' thiếu chỉ số đoạn.")
            continue

        out_of_range = False
        for c_idx in citations:
            if not isinstance(c_idx, int) or c_idx < 0 or c_idx >= len(paragraphs):
                errors.append(
                    f"Bài i={item_i}: Chỉ số đoạn c={c_idx} vượt dải đoạn [0..{len(paragraphs)-1}]."
                )
                out_of_range = True
                break

        if out_of_range:
            continue

        # 3. Kiểm tra bảo toàn dấu tiếng Việt
        source_has_diacritics = has_vietnamese_diacritics(title) or any(
            has_vietnamese_diacritics(p) for p in paragraphs[:3]
        )
        if source_has_diacritics:
            summary = rec.get("s") or ""
            implication = rec.get("im") or ""
            if not has_vietnamese_diacritics(summary) and not has_vietnamese_diacritics(implication):
                errors.append(f"Bài i={item_i}: Bài gốc có dấu nhưng tóm tắt/hàm ý mất hoàn toàn dấu.")
                continue

        valid_records.append(rec)

    return valid_records, errors


class AgyRunner:
    """Điều phối và thực thi các gói tác vụ nhận thức bằng Antigravity CLI.

    Attributes:
        profile_root: Thư mục chứa các hồ sơ sandbox.
        work_root: Thư mục làm việc rỗng chứa tiến trình con.
        model: Mã mô hình được ghim.
        timeout_seconds: Giới hạn thời gian chờ tối đa cho một lượt gọi.
    """

    def __init__(
        self,
        *,
        profile_root: Path | None = None,
        work_root: Path | None = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Khởi tạo AgyRunner với các cấu hình thư mục cách ly.

        Args:
            profile_root: Thư mục gốc chứa các sandbox profile.
            work_root: Thư mục làm việc rỗng ngoài kho mã.
            model: Mã mô hình sử dụng.
            timeout_seconds: Thời gian tối đa chờ phản hồi.
        """
        local_app = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        self.profile_root = profile_root or (local_app / "news-scape" / "agy_profiles")
        self.work_root = work_root or (local_app / "news-scape" / "agy_work")
        self.model = model
        self.timeout_seconds = timeout_seconds

        self.profile_root.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)

    def run_batch(
        self,
        batch_id: str,
        task_path: Path,
        out_dir: Path,
        *,
        core_text: str | None = None,
        mock_subprocess: Any | None = None,
    ) -> AgyExecutionResult:
        """Thực thi phân tích một lô bài viết và ghi kết quả ra tệp.

        Args:
            batch_id: Mã định danh của lô.
            task_path: Đường dẫn tệp task.json đầu vào.
            out_dir: Thư mục ghi tệp kết quả đầu ra.
            core_text: Nội dung quy chuẩn tiền tố hệ thống.
            mock_subprocess: Đối tượng giả lập gọi lệnh phục vụ kiểm thử.

        Returns:
            Đối tượng AgyExecutionResult chứa trạng thái và số đo chi tiết.
        """
        start_time = time.time()
        out_dir.mkdir(parents=True, exist_ok=True)

        if core_text is None:
            if not CORE_PATH.exists():
                return AgyExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="FATAL",
                    error_message=f"Không tìm thấy tệp tiền tố quy chuẩn: {CORE_PATH}",
                )
            core_text = CORE_PATH.read_text(encoding="utf-8")

        # 1. Đọc nội dung gói công việc đầu vào
        try:
            task_content = task_path.read_text(encoding="utf-8")
            task_data = json.loads(task_content)
            packet_items = task_data.get("a", [])
        except Exception as exc:
            return AgyExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                error_message=f"Lỗi đọc tệp task.json: {exc}",
            )

        # 2. Khởi tạo Sandboxed Worker Profile
        profile_dir = self.profile_root / batch_id
        build_sandbox_profile(profile_dir, core_text)

        # 3. Chuẩn bị thư mục làm việc rỗng và dòng lệnh
        work_dir = self.work_root / batch_id
        work_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "agy",
            "-p=",
            "--agent",
            "article-processor",
            "--model",
            self.model,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            f"--print-timeout={self.timeout_seconds}s",
            "--disable-slash-commands",
        ]

        env = os.environ.copy()
        env["USERPROFILE"] = str(profile_dir)
        env["HOME"] = str(profile_dir)
        env["ANTIGRAVITY_APP_DATA_DIR"] = str(profile_dir / ".gemini" / "antigravity-cli")
        env["PYTHONUTF8"] = "1"

        ndjson_input = json.dumps(
            {"event": "user", "message": {"content": f"## Packet\n{task_content}"}},
            ensure_ascii=False,
        ) + "\n"

        # 4. Thực thi subprocess
        if mock_subprocess:
            proc_res = mock_subprocess(cmd, ndjson_input, env, work_dir)
            stdout_text = proc_res.stdout
            stderr_text = proc_res.stderr
            return_code = proc_res.returncode
        else:
            try:
                proc = subprocess.run(
                    cmd,
                    input=ndjson_input,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(work_dir),
                    env=env,
                    timeout=self.timeout_seconds + 30,
                )
                stdout_text = proc.stdout
                stderr_text = proc.stderr
                return_code = proc.returncode
            except subprocess.TimeoutExpired:
                return AgyExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="TIMEOUT",
                    latency_seconds=time.time() - start_time,
                    error_message=f"Quá thời gian thực thi {self.timeout_seconds} giây.",
                )
            except Exception as exc:
                return AgyExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="FATAL",
                    error_message=f"Lỗi khởi chạy tiến trình agy: {exc}",
                )

        latency = time.time() - start_time

        # 5. Phân tích kết quả theo Bộ Phân Loại Lỗi 9 Tầng
        # Tầng 1: Exit code khác 0 hoặc chuỗi AGY_ERROR
        if return_code != 0 or "AGY_ERROR" in (stderr_text or ""):
            err_lower = (stderr_text or "").lower()
            if "429" in err_lower or "resource_exhausted" in err_lower or "quota" in err_lower:
                return AgyExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="QUOTA",
                    exit_code=return_code,
                    latency_seconds=latency,
                    error_message="Hạn mức phiên chạm ngưỡng 429 Resource Exhausted.",
                )
            if "retryable:true" in err_lower or return_code == 3:
                return AgyExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="RETRYABLE",
                    exit_code=return_code,
                    latency_seconds=latency,
                    error_message=f"Lỗi API có thể thử lại: {stderr_text[:200]}",
                )
            return AgyExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                exit_code=return_code,
                latency_seconds=latency,
                error_message=f"Tiến trình agy thất bại: {stderr_text[:300]}",
            )

        # Tầng 2: Kiểm tra timeout âm thầm trong stderr
        if "print timeout" in (stderr_text or "").lower():
            return AgyExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="TIMEOUT",
                exit_code=return_code,
                latency_seconds=latency,
                error_message="Mô hình hết thời gian in chuỗi văn bản.",
            )

        # Tầng 3, 4, 5, 6: Đọc các sự kiện NDJSON từ stdout
        events: list[dict[str, Any]] = []
        raw_response = ""
        usage_data: dict[str, int] = {}
        tool_invoked = False
        denied_actions = False

        for line in (stdout_text or "").splitlines():
            line_str = line.strip()
            if not line_str.startswith("{"):
                continue
            try:
                ev = json.loads(line_str)
                events.append(ev)
                ev_type = ev.get("type") or ev.get("event")
                if ev_type == "init":
                    init_data = ev.get("data", {})
                    # Kiểm tra mô hình ghim
                    if init_data.get("model") and self.model not in init_data.get("model", ""):
                        return AgyExecutionResult(
                            ok=False,
                            batch_id=batch_id,
                            status="FATAL",
                            latency_seconds=latency,
                            error_message=f"Mô hình khởi tạo ({init_data.get('model')}) không khớp ({self.model}).",
                        )
                elif ev_type == "step_update":
                    step = ev.get("step", {})
                    if step.get("type") == "tool" or step.get("tool_name"):
                        tool_invoked = True
                elif ev_type == "result":
                    res_data = ev.get("data", {}) or ev
                    raw_response = res_data.get("response") or res_data.get("content") or ""
                    usage_data = res_data.get("usage") or {}
                    if res_data.get("denied_actions"):
                        denied_actions = True
            except json.JSONDecodeError:
                continue

        # Tầng 5: Vi phạm quyền hoặc gọi công cụ ngoài ý muốn
        if tool_invoked or denied_actions:
            return AgyExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="VIOLATION",
                latency_seconds=latency,
                error_message="Phát hiện lượt gọi công cụ trái quy tắc Zero-Tool.",
            )

        # Tầng 7: Bóc tách cấu trúc JSON
        try:
            records = salvage_json_records(raw_response or stdout_text)
        except Exception as exc:
            return AgyExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="SOFT_FAIL",
                latency_seconds=latency,
                error_message=f"Bóc tách JSON thất bại: {exc}",
            )

        # Tầng 8: Kiểm định miền nghiệp vụ
        valid_recs, domain_errors = validate_records(records, packet_items)
        if len(valid_recs) < len(packet_items):
            status = "PARTIAL"
        else:
            status = "OK"

        # 6. Ghi an toàn tệp kết quả ra đĩa
        output_file = out_dir / f"{batch_id}.output.json"
        meta_file = out_dir / f"{batch_id}.meta.json"

        # Tệp output ghi dưới dạng mảng JSON thuần túy để tương thích với article_expand
        safe_atomic_write(output_file, json.dumps(valid_recs, ensure_ascii=False, indent=1))

        meta_info = {
            "batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "agent_provider": "agy",
            "model_used": self.model,
            "prefix_hash": prefix_hash(),
            "items_total": len(packet_items),
            "items_valid": len(valid_recs),
            "status": status,
            "usage": usage_data,
            "latency_seconds": round(latency, 2),
            "domain_errors": domain_errors,
        }
        safe_json_dump(meta_file, meta_info)

        return AgyExecutionResult(
            ok=(status == "OK"),
            batch_id=batch_id,
            status=status,
            records=valid_recs,
            usage=usage_data,
            latency_seconds=latency,
            error_message="; ".join(domain_errors) if domain_errors else "",
        )

    def run_wave(
        self,
        manifest_data: dict[str, Any],
        out_dir: Path,
        *,
        concurrency: int = 2,
    ) -> dict[str, Any]:
        """Chạy toàn bộ các lô bài viết trong một đợt phân tích song song.

        Args:
            manifest_data: Dữ liệu tệp manifest wave_<wave>.json.
            out_dir: Thư mục lưu trữ kết quả đầu ra.
            concurrency: Số tiến trình chạy song song tối đa (mặc định 2).

        Returns:
            Báo cáo tổng hợp kết quả của cả đợt.
        """
        batches = manifest_data.get("batches", [])
        wave = manifest_data.get("wave", "unknown")
        results: list[AgyExecutionResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            future_to_batch = {}
            for b in batches:
                bid = b["batch_id"]
                tpath = Path(b["packet_file"])
                future = executor.submit(self.run_batch, bid, tpath, out_dir)
                future_to_batch[future] = bid

            for future in concurrent.futures.as_completed(future_to_batch):
                bid = future_to_batch[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    results.append(
                        AgyExecutionResult(
                            ok=False,
                            batch_id=bid,
                            status="FATAL",
                            error_message=f"Lỗi ngoại lệ luồng: {exc}",
                        )
                    )

        n_ok = sum(1 for r in results if r.ok)
        total_items = sum(len(r.records) for r in results)
        total_tokens = sum(r.usage.get("total_tokens", 0) for r in results)

        return {
            "wave": wave,
            "batches_total": len(batches),
            "batches_ok": n_ok,
            "items_extracted": total_items,
            "total_tokens": total_tokens,
            "results": [
                {
                    "batch_id": r.batch_id,
                    "status": r.status,
                    "ok": r.ok,
                    "items": len(r.records),
                    "error": r.error_message,
                }
                for r in results
            ],
        }
