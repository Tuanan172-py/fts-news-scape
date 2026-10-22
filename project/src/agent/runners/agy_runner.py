"""Run and orchestrate article analysis tasks through the Antigravity CLI."""
from __future__ import annotations

import concurrent.futures
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

from src.agent.contract.article_contract import (  # noqa: F401
    build_user_message,
    has_vietnamese_diacritics,
    result_meta,
    validate_response,
)
from src.agent.packet.prefix import prefix_hash
from src.core import paths
from src.core.staging import safe_atomic_write, safe_json_dump
from src.core.stdio import force_utf8_stdio
from src.core.paths import PROJECT_ROOT

force_utf8_stdio()

CORE_PATH = PROJECT_ROOT / "assets" / "prefix" / "ARTICLE_SYSTEM_CORE.md"
DEFAULT_MODEL = "gemini-3.8-flash-low"
DEFAULT_TIMEOUT_SECONDS = 600

@dataclass
class AgyExecutionResult:
    """Result of running one article batch through the Antigravity CLI.

    Attributes:
        ok: Whether the run met the requirements.
        batch_id: Batch identifier.
        status: Status class (OK, FATAL, RETRYABLE, QUOTA, TIMEOUT, VIOLATION, PARTIAL, SOFT_FAIL).
        exit_code: Exit code of the agy process.
        records: Records extracted successfully.
        usage: Token usage information.
        latency_seconds: Run time in seconds.
        error_message: Detailed error message, if any.
        raw_ref: Path of the raw response file for a SOFT_FAIL batch, for diagnosis.
    """

    ok: bool
    batch_id: str
    status: str
    exit_code: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_seconds: float = 0.0
    error_message: str = ""
    raw_ref: str | None = None


RAW_DUMP_LIMIT = 256 * 1024


def dump_raw_response(batch_id: str, stdout_text: str, stderr_text: str, raw_response: str) -> str | None:
    """Write the raw response of a failed batch to `ops_logs/waves/<wave>/raw/`.

    Each part is truncated at 256 KB and has secrets redacted.

    Args:
        batch_id: Batch id, in the form `article_<wave>_NN`.
        stdout_text: Standard output of agy.
        stderr_text: Standard error of agy.
        raw_response: Content of the `result` event.

    Returns:
        Path of the file written, or None if writing failed.
    """
    try:
        from src.core.ops_config import resolve_paths
        from src.core.redact import redact

        wave = os.environ.get("OPS_TRACE_WAVE") or batch_id.split("_")[1]
        target = resolve_paths().log_dir / "waves" / wave / "raw" / f"{batch_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        parts = (("result", raw_response), ("stdout", stdout_text), ("stderr", stderr_text))
        body = "\n".join(f"=== {name} ({len(text or '')} ký tự) ===\n{redact((text or '')[:RAW_DUMP_LIMIT])}"
                         for name, text in parts)
        target.write_text(body, encoding="utf-8")
        return str(target)
    except Exception:  # noqa: BLE001 - diagnostics must not break the batch
        return None


def resolve_agy() -> str:
    """Find the absolute path of `agy` in any runtime environment.

    The user PATH may store `%LOCALAPPDATA%\\agy\\bin` without expanding the variable. An
    interactive shell expands it but Task Scheduler does not, so a bare `agy` raises
    WinError 2 under `ops_daemon`. Search order: the `AGY_BIN` variable, the current PATH,
    PATH after environment-variable expansion, then the known install locations.

    Returns:
        Path to `agy`, or the string `agy` when it is not found anywhere.
    """
    explicit = os.environ.get("AGY_BIN")
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("agy")
    if found:
        return found
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        expanded = os.path.expandvars(entry.strip())
        if expanded and expanded != entry:
            hit = shutil.which("agy", path=expanded)
            if hit:
                return hit
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    for cand in (local / "agy" / "bin" / "agy.exe", Path.home() / ".gemini" / "bin" / "agy.exe"):
        if cand.exists():
            return str(cand)
    return "agy"


def build_sandbox_profile(
    profile_dir: Path,
    core_text: str,
    work_dir: Path | None = None,
    *,
    agent_name: str = "article-processor",
    description: str = "Chuyên gia phân tích tin tức tài chính và trích xuất thực thể",
    instruction_guard: str | None = None,
) -> dict[str, Path]:
    """Create the isolated work profile configuration for the Antigravity CLI.

    Args:
        profile_dir: Root directory of the worker profile.
        core_text: Full text of the agent system prefix.
        work_dir: Empty working directory of the child process, if any.
        agent_name: Name of the custom agent written to the profile.
        description: Short description of the agent.
        instruction_guard: Rule block appended after the agent body; None uses the JSON-array rules.

    Returns:
        Dict of the paths of the configuration files created.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Global agent definition in the worker profile.
    agents_dir = profile_dir / ".gemini" / "config" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_path = agents_dir / f"{agent_name}.md"

    frontmatter = (
        "---\n"
        f"name: {agent_name}\n"
        f"description: {description}\n"
        "tools: []\n"
        "excludeDefaultComponents: true\n"
        "inheritCustomizations: false\n"
        "---\n"
    )
    instruction_guard = instruction_guard if instruction_guard is not None else (
        "\n\n## QUY TẮC BẮT BUỘC:\n"
        "- Bạn là bộ xử lý JSON thuần túy (Prompt-in, JSON-out).\n"
        "- TUYỆT ĐỐI KHÔNG GỌI BẤT KỲ CÔNG CỤ NÀO (kể cả manage_task, run_code, schedule, v.v.).\n"
        "- Trả kết quả trực tiếp dưới dạng duy nhất là mảng JSON hợp lệ chứa các bản ghi phân tích.\n"
        "- Mã nhóm thực thể (e) BẮT BUỘC chỉ gồm đúng 1 trong 11 mã chuẩn (3 ký tự): TIC, COM, PER, FND, IDX, EXC, IND, GEO, THM, AST, INS. TUYỆT ĐỐI KHÔNG dùng tiền tố phân cấp cũ (như IND_GICS1, IND_GICS2, MACRO_GEO, MACRO_THEME). Quỹ đầu tư / ETF bắt buộc dùng mã FND.\n"
        "- Mảng trích dẫn (c) BẮT BUỘC phải có từ 2 đến 4 chỉ số đoạn văn khác nhau (ví dụ: [0, 1] hoặc [1, 2]), không được chỉ có 1 chỉ số, và phải nằm trong phạm vi mảng p của bài viết đó (từ 0 đến len(p)-1).\n"
    )
    agent_content = frontmatter + (core_text or "") + instruction_guard
    agent_path.write_text(agent_content, encoding="utf-8")

    # With a work_dir, also sync into .agents/agents of the child workspace.
    if work_dir is not None:
        work_agents_dir = work_dir / ".agents" / "agents"
        work_agents_dir.mkdir(parents=True, exist_ok=True)
        (work_agents_dir / f"{agent_name}.md").write_text(agent_content, encoding="utf-8")

    # settings.json with all permissions removed.
    cli_dir = profile_dir / ".gemini" / "antigravity-cli"
    cli_dir.mkdir(parents=True, exist_ok=True)
    settings_path = cli_dir / "settings.json"
    settings_data = {
        "permissions": {"allow": []},
        "trustedWorkspaces": [],
    }
    settings_path.write_text(json.dumps(settings_data, indent=2), encoding="utf-8")

    # Defensive hooks.json that denies every tool call.
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


class AgyRunner:
    """Orchestrate and run cognitive task packets through the Antigravity CLI.

    Attributes:
        profile_root: Directory that holds the sandbox profiles.
        work_root: Empty working directory for the child processes.
        model: Pinned model identifier.
        timeout_seconds: Maximum wait time for one call.
    """

    def __init__(
        self,
        *,
        profile_root: Path | None = None,
        work_root: Path | None = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize the AgyRunner with isolated directory settings.

        Args:
            profile_root: Root directory of the sandbox profiles.
            work_root: Empty working directory outside the code repository.
            model: Model identifier to use.
            timeout_seconds: Maximum time to wait for a response.
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
        """Run one batch and record an `agent` span when the daemon trace context exists.

        Args:
            batch_id: Batch identifier.
            task_path: Path of the input task.json file.
            out_dir: Directory that receives the output files.
            core_text: Canonical system prefix text.
            mock_subprocess: Mock of the command call, for tests.

        Returns:
            AgyExecutionResult with the status and detailed metrics.
        """
        from src.telemetry import trace as tracing

        parent = os.environ.get(tracing.ENV_PARENT)
        with tracing.span(f"lô {batch_id}", "agent", "article-processor",
                          span_id=f"{parent}/{batch_id}" if parent else None,
                          batch=batch_id, model=self.model, entrypoint="agy -p=",
                          input_ref=str(task_path)) as sp:
            res = self._run_batch_impl(batch_id, task_path, out_dir, core_text=core_text,
                                       mock_subprocess=mock_subprocess)
            meta: dict[str, Any] = {}
            if res.status in ("OK", "PARTIAL"):
                try:
                    meta = json.loads((out_dir / f"{batch_id}.meta.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    meta = {}
            sp.set(runner_status=res.status, items=len(res.records), usage=res.usage,
                   latency_s=round(res.latency_seconds, 2), exit_code=res.exit_code,
                   error=(res.error_message or "")[:200], raw_ref=res.raw_ref,
                   items_total=meta.get("items_total"),
                   tool_invoked=bool(meta.get("tool_invoked")),
                   denied_actions=bool(meta.get("denied_actions")),
                   attempts=meta.get("attempts"), prefix_hash=meta.get("prefix_hash"),
                   output_ref=str(out_dir / f"{batch_id}.output.json") if meta else None)
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
        *,
        core_text: str | None = None,
        mock_subprocess: Any | None = None,
    ) -> AgyExecutionResult:
        """Analyze one article batch and write the results to files.

        Args:
            batch_id: Batch identifier.
            task_path: Path of the input task.json file.
            out_dir: Directory that receives the output files.
            core_text: Canonical system prefix text.
            mock_subprocess: Mock of the command call, for tests.

        Returns:
            AgyExecutionResult with the status and detailed metrics.
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

        # Read the input work package.
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

        # Prepare the empty working directory and the sandboxed worker profile.
        profile_dir = self.profile_root / batch_id
        work_dir = self.work_root / batch_id
        work_dir.mkdir(parents=True, exist_ok=True)
        build_sandbox_profile(profile_dir, core_text, work_dir=work_dir)

        cmd = [
            resolve_agy(),
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
            {"event": "user", "message": {"content": build_user_message(task_content)}},
            ensure_ascii=False,
        ) + "\n"

        # Run the subprocess, retrying automatically on a transient RETRYABLE error or a 429 QUOTA error.
        max_attempts = 3
        for attempt in range(max_attempts):
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

            err_lower = (stderr_text or "").lower()
            is_429 = (
                return_code != 0
                and (
                    "429" in err_lower
                    or "resource_exhausted" in err_lower
                    or "quota" in err_lower
                )
            )
            is_retryable = (
                return_code != 0
                and (
                    "retryable:true" in err_lower
                    or return_code == 3
                    or "503" in err_lower
                    or "unavailable" in err_lower
                    or "502" in err_lower
                    or "bad gateway" in err_lower
                )
            )
            if (is_retryable or is_429) and attempt < max_attempts - 1:
                sleep_sec = 15 if (is_429 and not mock_subprocess) else (3 if not mock_subprocess else 0.001)
                time.sleep(sleep_sec)
                continue
            break

        latency = time.time() - start_time

        # Analyze the result with the 9-level error classification.
        # Level 1: non-zero exit code or the AGY_ERROR string.
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
            if (
                "retryable:true" in err_lower
                or return_code == 3
                or "503" in err_lower
                or "unavailable" in err_lower
                or "502" in err_lower
                or "bad gateway" in err_lower
            ):
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

        # Level 2: silent timeout reported in stderr.
        if "print timeout" in (stderr_text or "").lower():
            return AgyExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="TIMEOUT",
                exit_code=return_code,
                latency_seconds=latency,
                error_message="Mô hình hết thời gian in chuỗi văn bản.",
            )

        # Levels 3-6: read the NDJSON events from stdout.
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
                    init_data = ev.get("init") or ev.get("data", {})
                    # Check the pinned model.
                    if init_data.get("model") and self.model not in init_data.get("model", ""):
                        return AgyExecutionResult(
                            ok=False,
                            batch_id=batch_id,
                            status="FATAL",
                            latency_seconds=latency,
                            error_message=f"Mô hình khởi tạo ({init_data.get('model')}) không khớp ({self.model}).",
                        )
                elif ev_type == "step_update":
                    step = ev.get("step_update") or ev.get("step", {})
                    if step.get("type") == "tool" or step.get("tool_name"):
                        tool_invoked = True
                elif ev_type == "result":
                    res_data = ev.get("result") or ev.get("data", {}) or ev
                    raw_response = res_data.get("response") or res_data.get("content") or ""
                    usage_data = res_data.get("usage") or {}
                    if res_data.get("denied_actions"):
                        denied_actions = True
            except json.JSONDecodeError:
                continue

        # Levels 7-8: unwrap and validate the contract with the validator shared by all providers.
        parsed = validate_response(raw_response or stdout_text, packet_items)
        json_salvage_error: Exception | None = None
        if parsed.counters.get("raw_records", 0) == 0:
            json_salvage_error = ValueError("Không bóc được bản ghi JSON nào từ phản hồi.")
        valid_recs = list(parsed.records.values())
        contract_meta = result_meta(parsed)
        domain_errors = contract_meta["domain_errors"]

        # Level 5: check for tool-call violations.
        tool_warning: str | None = None
        if tool_invoked or denied_actions:
            if valid_recs:
                tool_warning = "Phát hiện lượt gọi công cụ bị hook chặn; đã khôi phục thành công các bản ghi hợp lệ."
            else:
                return AgyExecutionResult(
                    ok=False,
                    batch_id=batch_id,
                    status="VIOLATION",
                    latency_seconds=latency,
                    error_message="Phát hiện lượt gọi công cụ trái quy tắc Zero-Tool và không có JSON hợp lệ.",
                )

        if json_salvage_error is not None:
            return AgyExecutionResult(
                ok=False,
                batch_id=batch_id,
                status="SOFT_FAIL",
                latency_seconds=latency,
                error_message=f"Bóc tách JSON thất bại: {json_salvage_error}",
                raw_ref=dump_raw_response(batch_id, stdout_text, stderr_text, raw_response),
            )

        if len(valid_recs) < len(packet_items):
            status = "PARTIAL"
        else:
            status = "OK"

        # Write the result files to disk safely.
        output_file = out_dir / f"{batch_id}.output.json"
        meta_file = out_dir / f"{batch_id}.meta.json"

        # The output file is a plain JSON array, compatible with article_expand.
        safe_atomic_write(output_file, json.dumps(valid_recs, ensure_ascii=False, indent=1))

        meta_info = {
            "batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "agent_provider": "agy",
            "model_used": self.model,
            "sampling": {"temperature": "unsupported", "seed": "unsupported"},
            "prefix_hash": prefix_hash(),
            "items_total": len(packet_items),
            "items_valid": len(valid_recs),
            "status": status,
            "usage": usage_data,
            "latency_seconds": round(latency, 2),
            **contract_meta,
            "tool_invoked": tool_invoked,
            "denied_actions": denied_actions,
            "attempts": attempt + 1,
        }
        if tool_warning:
            meta_info["warning"] = tool_warning
        safe_json_dump(meta_info, meta_file)

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
        """Run all article batches of a wave in parallel.

        Args:
            manifest_data: Content of the manifest file wave_<wave>.json.
            out_dir: Directory that receives the output files.
            concurrency: Maximum number of parallel workers.

        Returns:
            Summary report of the whole wave.
        """
        batches = manifest_data.get("batches", [])
        wave = manifest_data.get("wave", "unknown")
        results: list[AgyExecutionResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
            future_to_batch = {}
            for b in batches:
                bid = b["batch_id"]
                task_file_str = b.get("path") or b.get("packet_file") or b.get("task_file")
                if not task_file_str:
                    task_file_str = str(paths.article_packets_dir() / f"{bid}.task.json")
                tpath = paths.resolve_data_path(task_file_str)
                future = executor.submit(self.run_batch, bid, tpath, out_dir)
                future_to_batch[future] = bid

            for future in concurrent.futures.as_completed(future_to_batch):
                bid = future_to_batch[future]
                try:
                    res = future.result()
                    results.append(res)
                except Exception as exc:
                    import traceback
                    tb = traceback.format_exc()
                    results.append(
                        AgyExecutionResult(
                            ok=False,
                            batch_id=bid,
                            status="FATAL",
                            error_message=f"Lỗi ngoại lệ luồng: {exc} | TB: {tb}",
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
