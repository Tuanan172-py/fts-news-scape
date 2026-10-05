"""Thực thi và điều phối các tác vụ phân tích bài đăng qua OpenRouter API."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.agent.article_contract import (
    SAMPLING,
    build_user_message,
    request_meta,
    result_meta,
    validate_response,
)
from src.core.staging import safe_json_dump
from src.core.stdio import force_utf8_stdio

force_utf8_stdio()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = PROJECT_ROOT / "data" / "prefix" / "ARTICLE_SYSTEM_CORE.md"
OPENROUTER_ENV = PROJECT_ROOT.parent / "openrouter" / ".env"
DEFAULT_MODEL = "stealth/space-bunny-alpha"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_TOKENS = 32000


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
        max_tokens: int = DEFAULT_MAX_TOKENS,
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
        self.max_tokens = max_tokens

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
        max_attempts: int = 2,
        force: bool = False,
    ) -> OpenRouterExecutionResult:
        """Gửi một lô bài viết tới OpenRouter API và lưu trữ kết quả phân tích.

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
                    meta_info = {}
                    if meta_file.exists():
                        try:
                            meta_info = json.loads(meta_file.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                    return OpenRouterExecutionResult(
                        ok=True,
                        batch_id=batch_id,
                        status="CACHED",
                        records=cached_recs,
                        usage=meta_info.get("usage", {}),
                        latency_seconds=meta_info.get("latency_seconds", 0.0),
                    )
            except Exception:
                pass

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

        user_message = build_user_message(task_path.read_text(encoding="utf-8"))

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:20128",
            "X-Title": "News-Scape Article Lane",
        }

        req_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.core_text},
                {"role": "user", "content": user_message},
            ],
            "reasoning": {"effort": "minimal"},
            "temperature": SAMPLING["temperature"],
            "seed": SAMPLING["seed"],
            "max_tokens": self.max_tokens,
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

        parsed = validate_response(raw_text, packet_items)
        if parsed.counters.get("raw_records", 0) == 0:
            return OpenRouterExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="FATAL",
                latency_seconds=latency,
                error_message=f"Không bóc được bản ghi JSON nào | Đầu ra thô: {raw_text[:200]}",
            )

        valid_recs = list(parsed.records.values())
        contract_meta = result_meta(parsed)
        domain_errors = contract_meta["domain_errors"]
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
            **request_meta(
                "openrouter", self.model,
                sampling={"temperature": SAMPLING["temperature"], "seed": SAMPLING["seed"],
                          "max_tokens": self.max_tokens, "reasoning": "minimal"},
                prefix_sha256=hashlib.sha256(self.core_text.encode("utf-8")).hexdigest()),
            "batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items_expected": n_expected,
            "items_valid": n_valid,
            "latency_seconds": round(latency, 2),
            "usage": usage_data,
            "status": "OK" if n_valid >= n_expected else "PARTIAL",
            **contract_meta,
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
        force: bool = False,
    ) -> dict[str, Any]:
        """Chạy toàn bộ các lô bài viết trong một đợt phân tích song song.

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
        results: list[OpenRouterExecutionResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            future_to_batch = {}
            for b in batches:
                bid = b["batch_id"]
                task_file_str = b.get("path") or b.get("packet_file") or b.get("task_file")
                if not task_file_str:
                    task_file_str = str(PROJECT_ROOT / "data" / "agent_tasks" / "article" / f"{bid}.task.json")
                tpath = Path(task_file_str)
                future = executor.submit(self.run_batch, bid, tpath, out_dir, 2, force)
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
