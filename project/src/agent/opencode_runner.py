"""Thực thi và điều phối các tác vụ phân tích bài đăng bằng OpenCode CLI."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.article_contract import (
    build_user_message,
    request_meta,
    result_meta,
    validate_response,
)
from src.core import paths
from src.core.staging import safe_atomic_write, safe_json_dump
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = PROJECT_ROOT / "assets" / "prefix" / "ARTICLE_SYSTEM_CORE.md"
DEFAULT_MODEL = "opencode/deepseek-v4.1-flash-free"
FALLBACK_MODELS = [
    "opencode/minimax-m3.1-flash-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/beam-free",
    "opencode/nemotron-3.5-lightning-free",
]
DEFAULT_TIMEOUT_SECONDS = 180

INSTRUCTION_GUARD = (
    "\n\n## QUY TẮC BẮT BUỘC:\n"
    "- Bạn là bộ xử lý JSON thuần túy (Prompt-in, JSON-out).\n"
    "- TUYỆT ĐỐI KHÔNG GỌI BẤT KỲ CÔNG CỤ NÀO.\n"
    "- Trả kết quả trực tiếp dưới dạng duy nhất là mảng JSON hợp lệ chứa các bản ghi phân tích.\n"
    "- Mã nhóm thực thể (e) BẮT BUỘC chỉ gồm đúng 1 trong 11 mã chuẩn (3 ký tự): "
    "TIC, COM, PER, FND, IDX, EXC, IND, GEO, THM, AST, INS.\n"
    "- Mảng trích dẫn (c) BẮT BUỘC phải có từ 2 đến 4 chỉ số đoạn văn khác nhau (ví dụ: [0, 1] hoặc [1, 2]), "
    "nằm trong phạm vi mảng p của bài viết đó.\n"
    "- Trường hàm ý (im) BẮT BUỘC có độ dài tối thiểu 40 ký tự phân tích tác động dòng tiền hoặc rủi ro.\n"
)


@dataclass
class OpencodeExecutionResult:
    """Kết quả thực thi một lô bài viết qua OpenCode CLI.

    Attributes:
        ok: Trạng thái thực thi đạt chuẩn hay không.
        batch_id: Mã định danh của lô bài viết.
        status: Phân loại trạng thái (OK, PARTIAL, RETRYABLE, FATAL, TIMEOUT).
        records: Danh sách bản ghi trích xuất thành công.
        usage: Thông tin số lượng token sử dụng.
        latency_seconds: Thời gian thực thi tính bằng giây.
        error_message: Thông điệp lỗi chi tiết nếu có.
    """

    ok: bool
    batch_id: str
    status: str
    records: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_seconds: float = 0.0
    error_message: str = ""


def resolve_opencode() -> str:
    """Tìm đường dẫn tuyệt đối của binary OpenCode trong môi trường hệ thống.

    Returns:
        Đường dẫn khả thi tới tệp thực thi opencode, hoặc chuỗi 'opencode' dự phòng.
    """
    explicit = os.environ.get("OPENCODE_BIN")
    if explicit and Path(explicit).exists():
        return explicit
    local_app = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    known_paths = [
        local_app / "opencode-cli" / "opencode.exe",
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@opencode" / "cli-windows-x64" / "bin" / "opencode.exe",
        local_app / "opencode" / "OpenCode.exe",
    ]
    for p in known_paths:
        if p.exists():
            return str(p)
    found = shutil.which("opencode")
    if found:
        return found
    return "opencode"


class OpencodeRunner:
    """Điều phối và thực thi các gói tác vụ nhận thức bằng OpenCode CLI Headless.

    Attributes:
        model: Mã mô hình chính được cấu hình.
        timeout_seconds: Giới hạn thời gian tối đa cho một lượt gọi.
        core_text: Nội dung tiền tố hệ thống chuẩn mực.
        opencode_bin: Đường dẫn thực thi binary OpenCode.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        core_text: str | None = None,
        opencode_bin: str | None = None,
    ):
        """Khởi tạo OpencodeRunner với mô hình và tiền tố hệ thống.

        Args:
            model: Tên mô hình chính cần dùng.
            timeout_seconds: Thời gian tối đa chờ phản hồi của mỗi lô.
            core_text: Toàn văn tiền tố hệ thống (None tải từ ARTICLE_SYSTEM_CORE.md).
            opencode_bin: Đường dẫn cụ thể tới binary opencode (nếu có).
        """
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.opencode_bin = opencode_bin or resolve_opencode()

        if core_text is not None:
            self.core_text = core_text
        elif CORE_PATH.exists():
            self.core_text = CORE_PATH.read_text(encoding="utf-8")
        else:
            self.core_text = (
                "Bạn là chuyên viên phân tích tài chính cấp cao. "
                "Đọc packet và trả lời bằng một mảng JSON duy nhất theo chuẩn v2-lean: "
                '[{"i":"0","e":[["chuỗi","NHÓM"]],"s":"tóm tắt","k":["luận điểm"],"im":"hàm ý >=40 ký tự","sn":"pos|neg|neu","ts":"urg|today|week|month|arch","c":[0,2]}]'
            )

    def run_batch(
        self,
        batch_id: str,
        task_path: Path,
        out_dir: Path,
        max_attempts: int = 2,
        force: bool = False,
    ) -> OpencodeExecutionResult:
        """Chạy một lô và ghi vết span `agent` khi có ngữ cảnh ghi vết của daemon.

        Args:
            batch_id: Mã định danh của lô.
            task_path: Đường dẫn tệp task.json đầu vào.
            out_dir: Thư mục ghi tệp kết quả đầu ra.
            max_attempts: Số lần thử lại tối đa khi gặp lỗi tạm thời.
            force: Buộc chạy lại kể cả khi lô đã có kết quả đầu ra.

        Returns:
            Đối tượng OpencodeExecutionResult chứa kết quả và số đo chi tiết.
        """
        from src.ops import trace as tracing

        parent = os.environ.get(tracing.ENV_PARENT)
        with tracing.span(f"lô {batch_id}", "agent", "article-processor",
                          span_id=f"{parent}/{batch_id}" if parent else None,
                          batch=batch_id, model=self.model, entrypoint="opencode run",
                          input_ref=str(task_path)) as sp:
            res = self._run_batch_impl(batch_id, task_path, out_dir, max_attempts, force)
            sp.set(runner_status=res.status, items=len(res.records), usage=res.usage,
                   latency_s=round(res.latency_seconds, 2),
                   error=(res.error_message or "")[:200], tool_invoked=False,
                   denied_actions=False,
                   output_ref=str(out_dir / f"{batch_id}.output.json") if res.records else None)
            if res.status == "PARTIAL":
                sp.status = "partial"
            elif res.status == "TIMEOUT":
                sp.status = "timeout"
            elif not res.ok:
                sp.status = "fail"
            return res

    def _run_batch_impl(
        self,
        batch_id: str,
        task_path: Path,
        out_dir: Path,
        max_attempts: int = 2,
        force: bool = False,
    ) -> OpencodeExecutionResult:
        """Thực thi phân tích một lô bài viết qua OpenCode CLI và ghi kết quả ra đĩa.

        Args:
            batch_id: Mã định danh của lô bài viết.
            task_path: Đường dẫn tệp packet đầu vào (.task.json).
            out_dir: Thư mục lưu trữ kết quả đầu ra.
            max_attempts: Số lần thử lại tối đa khi gặp lỗi có thể khôi phục.
            force: Buộc chạy lại kể cả khi lô đã có kết quả đầu ra.

        Returns:
            Đối tượng kết quả thực thi chi tiết.
        """
        out_file = out_dir / f"{batch_id}.output.json"
        meta_file = out_dir / f"{batch_id}.meta.json"
        if not force and out_file.exists():
            try:
                cached_recs = json.loads(out_file.read_text(encoding="utf-8"))
                if isinstance(cached_recs, list) and len(cached_recs) > 0:
                    meta_info: dict[str, Any] = {}
                    if meta_file.exists():
                        try:
                            meta_info = json.loads(meta_file.read_text(encoding="utf-8"))
                        except Exception:
                            meta_info = {}
                    return OpencodeExecutionResult(
                        ok=True,
                        batch_id=batch_id,
                        status=meta_info.get("status", "OK"),
                        records=cached_recs,
                        usage=meta_info.get("usage", {}),
                        latency_seconds=meta_info.get("latency_seconds", 0.0),
                        error_message="",
                    )
            except Exception:
                pass

        out_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()

        try:
            task_content = task_path.read_text(encoding="utf-8")
            task_data = json.loads(task_content)
            packet_items = task_data.get("a", [])
        except Exception as exc:
            return OpencodeExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                error_message=f"Lỗi đọc tệp task packet: {exc}",
            )

        n_expected = len(packet_items)
        if n_expected == 0:
            return OpencodeExecutionResult(
                ok=True,
                batch_id=batch_id,
                status="OK",
                records=[],
                error_message="Gói công việc rỗng",
            )

        prompt_payload = (
            f"{self.core_text}{INSTRUCTION_GUARD}\n\n"
            f"## DỮ LIỆU ĐẦU VÀO:\n{task_content}\n\n"
            "CHỈ TRẢ VỀ DUY NHẤT MẢNG JSON HỢP LỆ THEO CHUẨN V2-LEAN:"
        )

        models_to_try = [self.model] + [m for m in FALLBACK_MODELS if m != self.model]
        last_error = ""
        valid_recs: list[dict[str, Any]] = []
        domain_errors: list[str] = []
        contract_meta: dict[str, Any] = {}
        usage_data: dict[str, int] = {}
        model_used = self.model

        for attempt in range(max_attempts):
            model_index = min(attempt, len(models_to_try) - 1)
            current_model = models_to_try[model_index]
            model_used = current_model

            cmd = [
                self.opencode_bin,
                "run",
                "--format", "json",
                "-m", current_model,
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt_payload,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                last_error = f"Quá thời gian thực thi {self.timeout_seconds}s với mô hình {current_model}"
                if attempt < max_attempts - 1:
                    time.sleep(3)
                    continue
                return OpencodeExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="TIMEOUT",
                    latency_seconds=time.time() - t0,
                    error_message=last_error,
                )
            except Exception as exc:
                last_error = f"Lỗi gọi tiến trình opencode: {exc}"
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                return OpencodeExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="FATAL",
                    latency_seconds=time.time() - t0,
                    error_message=last_error,
                )

            stdout_text = proc.stdout or ""
            stderr_text = proc.stderr or ""
            return_code = proc.returncode

            # Bóc tách NDJSON stream
            extracted_text = ""
            error_msg = ""

            for line in stdout_text.splitlines():
                line_str = line.strip()
                if not line_str.startswith("{"):
                    continue
                try:
                    ev = json.loads(line_str)
                    ev_type = ev.get("type")
                    if ev_type == "text":
                        part = ev.get("part", {})
                        extracted_text += part.get("text", "")
                    elif ev_type == "step_finish":
                        part = ev.get("part", {})
                        tokens_info = part.get("tokens", {})
                        if tokens_info:
                            usage_data = {
                                "prompt_tokens": tokens_info.get("input", 0),
                                "completion_tokens": tokens_info.get("output", 0),
                                "total_tokens": tokens_info.get("total", 0),
                            }
                    elif ev_type == "error":
                        err_data = ev.get("error", {})
                        error_msg = err_data.get("data", {}).get("message") or err_data.get("message") or str(err_data)
                except json.JSONDecodeError:
                    continue

            if return_code != 0 or error_msg:
                combined_err = f"{error_msg} {stderr_text}".strip()
                last_error = f"Mô hình {current_model} trả lỗi (code {return_code}): {combined_err[:200]}"
                err_lower = combined_err.lower()
                is_rate_limit = "429" in err_lower or "quota" in err_lower or "rate" in err_lower
                if is_rate_limit and attempt < max_attempts - 1:
                    time.sleep(15)
                    continue
                if attempt < max_attempts - 1:
                    time.sleep(3)
                    continue

            # Kiểm tra và làm sạch Markdown codeblock nếu có
            if extracted_text:
                cleaned_text = extracted_text.strip()
                if cleaned_text.startswith("```"):
                    lines = cleaned_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned_text = "\n".join(lines).strip()

                parsed = validate_response(cleaned_text, packet_items)
                valid_recs = list(parsed.records.values())
                contract_meta = result_meta(parsed)
                domain_errors = contract_meta.get("domain_errors", [])

                if valid_recs:
                    break
                else:
                    domain_err_str = "; ".join(domain_errors) if domain_errors else ""
                    last_error = f"Bản ghi không đạt hợp đồng: {domain_err_str}".strip()
            else:
                last_error = f"Mô hình không trả về nội dung text. Stderr: {stderr_text[:150]}"

            if attempt < max_attempts - 1:
                time.sleep(2)

        latency = round(time.time() - t0, 2)
        n_valid = len(valid_recs)

        if n_valid == 0:
            return OpencodeExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                latency_seconds=latency,
                error_message=last_error or "Không trích xuất được bản ghi hợp lệ nào sau các lần thử",
            )

        # Ghi tệp kết quả output và meta
        safe_atomic_write(out_file, json.dumps(valid_recs, ensure_ascii=False, indent=1))

        if not usage_data:
            usage_data = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        meta_info = {
            "batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **request_meta(
                "opencode-native",
                model_used,
                sampling={"temperature": 0.1, "max_tokens": 32000},
                prefix_sha256=hashlib.sha256(self.core_text.encode("utf-8")).hexdigest(),
            ),
            "items_expected": n_expected,
            "items_valid": n_valid,
            "latency_seconds": latency,
            "usage": usage_data,
            "status": "OK" if n_valid >= n_expected else "PARTIAL",
            **contract_meta,
        }
        safe_json_dump(meta_info, meta_file)

        status = "OK" if n_valid >= n_expected else "PARTIAL"
        return OpencodeExecutionResult(
            ok=True,
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
        force: bool = False,
    ) -> dict[str, Any]:
        """Chạy toàn bộ các lô bài viết trong một đợt phân tích.

        Args:
            manifest_data: Dữ liệu tệp manifest wave_<wave>.json.
            out_dir: Thư mục lưu trữ kết quả đầu ra.
            concurrency: Số luồng chạy song song tối đa (mặc định 2).
            force: Buộc chạy lại kể cả khi lô đã có kết quả đầu ra.

        Returns:
            Báo cáo tổng hợp kết quả của cả đợt.
        """
        batches = manifest_data.get("batches", [])
        wave = manifest_data.get("wave", "unknown")
        results: list[OpencodeExecutionResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            future_to_batch = {}
            for b in batches:
                bid = b["batch_id"]
                task_file_str = b.get("path") or b.get("packet_file") or b.get("task_file")
                if not task_file_str:
                    task_file_str = str(paths.article_packets_dir() / f"{bid}.task.json")
                tpath = paths.resolve_data_path(task_file_str)
                future = executor.submit(self.run_batch, bid, tpath, out_dir, 2, force)
                future_to_batch[future] = bid

            for future in concurrent.futures.as_completed(future_to_batch):
                bid = future_to_batch[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    results.append(
                        OpencodeExecutionResult(
                            ok=False,
                            batch_id=bid,
                            status="FATAL",
                            error_message=f"Lỗi luồng: {exc}",
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
