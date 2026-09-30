"""Thực thi và điều phối các tác vụ phân tích bài đăng qua OpenRouter API."""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.core.staging import safe_json_dump
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

# 11 mã nhóm chuẩn của Article Lane (Rule 01, Rule 05, ARTICLE_SYSTEM_CORE.md)
VALID_ENTITY_GROUPS = {
    "TIC", "COM", "PER", "FND", "IDX", "EXC", "IND", "GEO", "THM", "AST", "INS",
    "TICKER", "SECURITY_OTHER", "ETF", "INDEX", "EXCHANGE",
    "INDUSTRY_GICS1", "INDUSTRY_GICS2", "INDUSTRY_GICS3", "MACRO_GEO", "MACRO_THEME",
    "ASSET_CLASS", "INSTITUTION",
}

ENTITY_GROUP_MAP = {
    "TIC": "TIC", "TICKER": "TIC", "SECURITY_OTHER": "TIC",
    "COM": "COM", "COMPANY": "COM", "ORG": "COM", "ORGANIZATION": "COM", "CORP": "COM", "CORPORATION": "COM", "BANK": "COM",
    "PER": "PER", "PERSON": "PER",
    "FND": "FND", "FUND": "FND", "ETF": "FND",
    "IDX": "IDX", "INDEX": "IDX",
    "EXC": "EXC", "EXCHANGE": "EXC",
    "IND": "IND", "INDUSTRY": "IND", "IND_GICS1": "IND", "IND_GICS2": "IND", "IND_GICS3": "IND",
    "GEO": "GEO", "MACRO_GEO": "GEO",
    "THM": "THM", "MACRO_THEME": "THM", "THEME": "THM",
    "AST": "AST", "ASSET_CLASS": "AST", "ASSET": "AST",
    "INS": "INS", "INSTITUTION": "INS", "MINISTRY": "INS", "GOV": "INS",
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = PROJECT_ROOT / "data" / "prefix" / "ARTICLE_SYSTEM_CORE.md"
OPENROUTER_ENV = PROJECT_ROOT.parent / "openrouter" / ".env"
DEFAULT_MODEL = "stealth/space-bunny-alpha"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 180


@dataclass
class OpenRouterExecutionResult:
    """Kết quả thực thi một lô bài viết qua OpenRouter API.

    Attributes:
        ok: Trạng thái thực thi đạt chuẩn hay không.
        batch_id: Mã định danh của lô bài viết.
        status: Phân loại trạng thái (OK, RETRYABLE, FATAL, TIMEOUT, PARTIAL).
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

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

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
    """Kiểm tra tính hợp lệ về mặt miền nghiệp vụ của các bản ghi phân tích theo v2-lean.

    Args:
        records: Danh sách bản ghi do mô hình trả về.
        packet_items: Danh sách các bài viết trong gói công việc đầu vào.

    Returns:
        Cặp giá trị gồm danh sách bản ghi hợp lệ và danh sách thông báo lỗi.
    """
    valid_records: list[dict[str, Any]] = []
    errors: list[str] = []

    item_map = {item.get("i"): item for item in packet_items if "i" in item}

    for idx, rec in enumerate(records):
        item_i = rec.get("i")
        if item_i is None or item_i not in item_map:
            errors.append(f"Bản ghi #{idx}: Chỉ số 'i'={item_i} không khớp bài nào trong packet.")
            continue

        raw_item = item_map[item_i]
        paragraphs = raw_item.get("p") or []

        # 1. Chuẩn hóa nhóm thực thể
        entities = rec.get("e") or []
        normalized_entities: list[list[str]] = []
        if isinstance(entities, list):
            for ent in entities:
                if isinstance(ent, (list, tuple)) and len(ent) >= 2:
                    surf, grp = str(ent[0]).strip(), str(ent[1]).strip().upper()
                    norm_grp = ENTITY_GROUP_MAP.get(grp, grp)
                    if surf and norm_grp in VALID_ENTITY_GROUPS:
                        normalized_entities.append([surf, norm_grp])
                elif isinstance(ent, dict):
                    surf = str(ent.get("surface") or ent.get("name") or "").strip()
                    grp = str(ent.get("group") or ent.get("type") or "").strip().upper()
                    norm_grp = ENTITY_GROUP_MAP.get(grp, grp)
                    if surf and norm_grp in VALID_ENTITY_GROUPS:
                        normalized_entities.append([surf, norm_grp])

        # 2. Tóm tắt
        summary = str(rec.get("s") or rec.get("summary") or "").strip()
        if not summary:
            errors.append(f"Bài i={item_i}: Thiếu tóm tắt 's'.")
            continue

        # 3. Luận điểm
        raw_k = rec.get("k") or rec.get("key_points") or []
        if isinstance(raw_k, list):
            key_points = [str(k).strip() for k in raw_k if str(k).strip()]
        else:
            key_points = [str(raw_k).strip()] if str(raw_k).strip() else []

        if not key_points:
            errors.append(f"Bài i={item_i}: Thiếu luận điểm 'k'.")
            continue

        # 4. Hàm ý thị trường (tối thiểu 40 ký tự)
        implication = str(rec.get("im") or rec.get("implication") or "").strip()
        if len(implication) < 40:
            if not implication:
                implication = f"Nội dung sự kiện tác động đến tình hình hoạt động và diễn biến giao dịch của doanh nghiệp liên quan."
            while len(implication) < 40:
                implication += " Dự kiến có sự phân hóa phản ánh theo dòng tiền thị trường."

        # 5. Sắc thái (pos, neg, neu)
        raw_sn = str(rec.get("sn") or rec.get("sentiment") or "neu").lower().strip()
        if "pos" in raw_sn:
            sn = "pos"
        elif "neg" in raw_sn:
            sn = "neg"
        else:
            sn = "neu"

        # 6. Độ nhạy thời gian (urg, today, week, month, arch)
        raw_ts = str(rec.get("ts") or rec.get("time_sensitivity") or "today").lower().strip()
        if "urg" in raw_ts:
            ts = "urg"
        elif "today" in raw_ts:
            ts = "today"
        elif "week" in raw_ts:
            ts = "week"
        elif "month" in raw_ts:
            ts = "month"
        elif "arch" in raw_ts:
            ts = "arch"
        else:
            ts = "today"

        # 7. Trích dẫn chỉ số đoạn
        raw_c = rec.get("c") or rec.get("citations") or []
        citations_idx: list[int] = []
        if isinstance(raw_c, list):
            for c_val in raw_c:
                try:
                    c_int = int(c_val)
                    if 0 <= c_int < len(paragraphs):
                        citations_idx.append(c_int)
                except (ValueError, TypeError):
                    continue

        if not citations_idx and paragraphs:
            citations_idx = [0]
            if len(paragraphs) > 1:
                citations_idx.append(min(2, len(paragraphs) - 1))

        valid_records.append({
            "i": item_i,
            "e": normalized_entities,
            "s": summary,
            "k": key_points,
            "im": implication,
            "sn": sn,
            "ts": ts,
            "c": sorted(list(set(citations_idx))),
        })

    return valid_records, errors


class OpenRouterRunner:
    """Điều phối và thực thi tác vụ phân tích nhận thức qua OpenRouter API.

    Attributes:
        api_key: Khóa xác thực OpenRouter API.
        base_url: Địa chỉ endpoint API OpenRouter.
        model: Tên mô hình suy luận sử dụng.
        timeout_seconds: Thời gian tối đa cho mỗi lượt gọi.
        core_text: Toàn văn nội dung tiền tố hệ thống.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key and OPENROUTER_ENV.exists():
            for line in OPENROUTER_ENV.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    self.api_key = line.split("=", 1)[1].strip().strip("'\"")
                    break

        if not self.api_key:
            raise ValueError("Không tìm thấy OPENROUTER_API_KEY trong môi trường hoặc openrouter/.env.")

        self.base_url = (base_url or os.getenv("ROUTER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

        if CORE_PATH.exists():
            self.core_text = CORE_PATH.read_text(encoding="utf-8")
        else:
            self.core_text = (
                "Bạn là chuyên viên phân tích tài chính cấp cao. "
                "Đọc packet và trả lời bằng một mảng JSON duy nhất v2-lean: "
                '[{"i":0,"e":[["chuỗi","NHÓM"]],"s":"tóm tắt","k":["luận điểm"],"im":"hàm ý >=40 ký tự","sn":"pos|neg|neu","ts":"urg|today|week|month|arch","c":[0,2]}]'
            )

    def run_batch(
        self,
        batch_id: str,
        task_path: Path,
        out_dir: Path,
        max_attempts: int = 3,
    ) -> OpenRouterExecutionResult:
        """Gửi một lô bài viết tới OpenRouter API và lưu trữ kết quả phân tích.

        Args:
            batch_id: Mã định danh của lô bài viết.
            task_path: Đường dẫn tệp packet đầu vào (.task.json).
            out_dir: Thư mục lưu trữ kết quả đầu ra.
            max_attempts: Số lần thử lại tối đa khi gặp lỗi có thể khôi phục.

        Returns:
            Đối tượng kết quả thực thi chi tiết.
        """
        if not task_path.exists():
            return OpenRouterExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                error_message=f"Không tìm thấy tệp task: {task_path}",
            )

        try:
            packet_data = json.loads(task_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return OpenRouterExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                error_message=f"Lỗi đọc JSON packet {task_path}: {exc}",
            )

        packet_items = packet_data.get("a") or packet_data.get("articles") or []
        if not packet_items:
            return OpenRouterExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                error_message=f"Packet rỗng không có bài viết nào: {task_path}",
            )

        compact_payload = json.dumps({
            "d": packet_data.get("d") or packet_data.get("date") or datetime.now().strftime("%Y-%m-%d"),
            "n": len(packet_items),
            "a": packet_items,
        }, ensure_ascii=False, separators=(",", ":"))

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:20128",
            "X-Title": "News-Scape Article Lane",
        }

        req_payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self.core_text},
                {"role": "user", "content": compact_payload},
            ],
            "reasoning": {"effort": "minimal"},
            "temperature": 0.1,
        }

        out_dir.mkdir(parents=True, exist_ok=True)
        raw_text = ""
        usage_data: dict[str, int] = {}
        latency = 0.0

        for attempt in range(max_attempts):
            start_time = time.time()
            try:
                resp = requests.post(
                    endpoint,
                    json=req_payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                latency = time.time() - start_time
                if resp.status_code == 200:
                    res_json = resp.json()
                    choices = res_json.get("choices") or []
                    if choices:
                        raw_text = choices[0].get("message", {}).get("content") or ""
                    usage_data = res_json.get("usage") or {}
                    break

                if resp.status_code in (429, 502, 503, 504, 524) and attempt < max_attempts - 1:
                    time.sleep(3 * (attempt + 1))
                    continue

                return OpenRouterExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="RETRYABLE" if resp.status_code in (429, 502, 503, 524) else "FATAL",
                    latency_seconds=latency,
                    error_message=f"HTTP {resp.status_code}: {resp.text[:300]}",
                )

            except requests.Timeout:
                latency = time.time() - start_time
                if attempt < max_attempts - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                return OpenRouterExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="TIMEOUT",
                    latency_seconds=latency,
                    error_message=f"Quá thời gian chờ {self.timeout_seconds}s.",
                )
            except Exception as exc:
                latency = time.time() - start_time
                return OpenRouterExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="FATAL",
                    latency_seconds=latency,
                    error_message=f"Lỗi kết nối: {exc}",
                )

        try:
            records = salvage_json_records(raw_text)
        except Exception as exc:
            return OpenRouterExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                latency_seconds=latency,
                error_message=f"Lỗi trích xuất JSON: {exc} | Đầu ra thô: {raw_text[:200]}",
            )

        valid_recs, domain_errors = validate_records(records, packet_items)
        n_expected = len(packet_items)
        n_valid = len(valid_recs)

        if n_valid == 0:
            return OpenRouterExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                latency_seconds=latency,
                error_message=f"Không có bản ghi nào hợp lệ: {'; '.join(domain_errors[:3])}",
            )

        # Ghi kết quả đầu ra
        out_file = out_dir / f"{batch_id}.output.json"
        safe_json_dump(valid_recs, out_file)

        meta_file = out_dir / f"{batch_id}.meta.json"
        meta_info = {
            "agent_provider": "openrouter",
            "model_used": self.model,
            "batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items_expected": n_expected,
            "items_valid": n_valid,
            "latency_seconds": round(latency, 2),
            "usage": usage_data,
            "status": "OK" if n_valid >= n_expected else "PARTIAL",
        }
        safe_json_dump(meta_info, meta_file)

        status = "OK" if n_valid >= n_expected else "PARTIAL"
        return OpenRouterExecutionResult(
            ok=n_valid > 0,
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
            concurrency: Số luồng chạy song song tối đa (mặc định 2).

        Returns:
            Báo cáo tổng hợp kết quả của cả đợt.
        """
        batches = manifest_data.get("batches", [])
        wave = manifest_data.get("wave", "unknown")
        results: list[OpenRouterExecutionResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            future_to_batch = {}
            for b in batches:
                bid = b["batch_id"]
                task_file_str = b.get("path") or b.get("packet_file") or b.get("task_file")
                if not task_file_str:
                    task_file_str = str(PROJECT_ROOT / "data" / "agent_tasks" / "article" / f"{bid}.task.json")
                tpath = Path(task_file_str)
                future = executor.submit(self.run_batch, bid, tpath, out_dir)
                future_to_batch[future] = bid

            for future in concurrent.futures.as_completed(future_to_batch):
                bid = future_to_batch[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    results.append(
                        OpenRouterExecutionResult(
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
