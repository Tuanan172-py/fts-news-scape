"""Run and orchestrate article analysis tasks through the OpenRouter API."""
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
from src.core import paths
from src.core.staging import safe_json_dump
from src.core.stdio import force_utf8_stdio
from src.core.paths import PROJECT_ROOT

force_utf8_stdio()

CORE_PATH = PROJECT_ROOT / "assets" / "prefix" / "ARTICLE_SYSTEM_CORE.md"
OPENROUTER_ENV = PROJECT_ROOT.parent / "openrouter" / ".env"
DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning:free"
FALLBACK_MODEL = "nvidia/nemotron-3.5-lightning:free"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_TOKENS = 32000


@dataclass
class OpenRouterExecutionResult:
    """Result of running one article batch through the OpenRouter API.

    Attributes:
        ok: Whether the run met the requirements.
        batch_id: Batch identifier.
        status: Status class (OK, RETRYABLE, FATAL, TIMEOUT, PARTIAL, CACHED).
        records: Records extracted successfully.
        usage: Token usage information.
        latency_seconds: Run time in seconds.
        error_message: Detailed error message, if any.
    """

    ok: bool
    batch_id: str
    status: str
    records: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_seconds: float = 0.0
    error_message: str = ""


class OpenRouterRunner:
    """Orchestrate and run cognitive analysis tasks through the OpenRouter API.

    Attributes:
        api_key: OpenRouter API authentication key.
        base_url: OpenRouter API endpoint address.
        model: Inference model name in use.
        timeout_seconds: Maximum time for one call.
        max_tokens: Maximum completion tokens per call.
        core_text: Full system prefix text.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        """Initialize the OpenRouterRunner.

        Args:
            api_key: API key; None reads OPENROUTER_API_KEY from the environment or openrouter/.env.
            base_url: API base URL; None reads ROUTER_BASE_URL or uses the default.
            model: Inference model name.
            timeout_seconds: Maximum time for one call.
            max_tokens: Maximum completion tokens per call.

        Raises:
            ValueError: If no API key is found.
        """
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
        """Run one batch and record an `agent` span when the trace context exists.

        Args:
            batch_id: Batch identifier.
            task_path: Path of the input packet file (.task.json).
            out_dir: Directory that receives the output files.
            max_attempts: Maximum number of attempts on a recoverable error.
            force: Rerun even if the batch already has an output.

        Returns:
            Detailed execution result.
        """
        from src.telemetry import trace as tracing

        parent = os.environ.get(tracing.ENV_PARENT)
        with tracing.span(f"lô {batch_id}", "agent", "article-processor",
                          span_id=f"{parent}/{batch_id}" if parent else None,
                          batch=batch_id, model=self.model, entrypoint="openrouter chat",
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
    ) -> OpenRouterExecutionResult:
        """Send one article batch to the OpenRouter API and store the analysis result.

        Args:
            batch_id: Batch identifier.
            task_path: Path of the input packet file (.task.json).
            out_dir: Directory that receives the output files.
            max_attempts: Maximum number of attempts on a recoverable error.
            force: Rerun even if the batch already has an output.

        Returns:
            Detailed execution result.
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
            "reasoning": {"effort": "none"},
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

        # Write the output.
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
        """Run all article batches of a wave in parallel.

        Args:
            manifest_data: Content of the manifest file wave_<wave>.json.
            out_dir: Directory that receives the output files.
            concurrency: Maximum number of parallel threads.
            force: Rerun even if a batch already has an output.

        Returns:
            Summary report of the whole wave.
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
