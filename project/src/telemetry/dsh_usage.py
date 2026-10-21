"""Read real token, context-pressure and cost measurements from the DSH runtime."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Source of truth for `token_ledger.py`, `ctx_probe.py` and `pipeline_radar.py token`.
#
# Six mandatory accounting rules, each checked against real numbers on this machine:
# 1. `inputTokens` in a DSH event is the UNCACHED part, not the prompt size. Misreading it
#    understates cost by about 30 times.
# 2. Within one request, `inputTokens + cacheReadTokens + outputTokens == totalTokens`.
#    `totalTokens` does NOT accumulate, so never sum it across requests.
# 3. `reasoningTokens` is a subset of `outputTokens`; adding both counts it twice.
# 4. `cacheWriteTokens` is always 0 with the DeepSeek adapter; do not build a cost line for it.
# 5. DSH stores no pricing data, so money is always computed outside from
#    `config/token_pricing.yaml`.
# 6. `contextPressure.surfaceTokens` is `systemTokens + messageTokens` and EXCLUDES
#    `toolsTokens`; `pressureTokens` is the total input of the latest sample and EXCLUDES output.
#
# Sub-agent cost does NOT appear in the parent session's `tokenUsage`: each child is its own
# Session with its own projcache file. The full cost of a wave is the parent plus every child
# session; see :func:`wave_usage`.

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

_PRICING_PATH = Path(__file__).resolve().parents[2] / "config" / "token_pricing.yaml"


def dsh_home() -> Path:
    """Determine the DSH home directory on this machine.

    Returns:
        Path in `%DSH_HOME%` if the environment variable is set, otherwise `~/.dsh`.
    """
    env = os.environ.get("DSH_HOME")
    return Path(env) if env else Path.home() / ".dsh"


def projcache_dir() -> Path:
    """Return the directory holding the projection checkpoint files of DSH sessions.

    Returns:
        Path of the `storages/session_projcache/sessions` directory.
    """
    return dsh_home() / "storages" / "session_projcache" / "sessions"


def sessions_dir() -> Path:
    """Return the directory holding the JSONL logs of DSH sessions.

    Returns:
        Path of the `sessions` directory.
    """
    return dsh_home() / "sessions"


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
def load_pricing(path: str | Path | None = None) -> dict:
    """Load the token price table from the config file.

    Args:
        path: Pricing file path. Defaults to `config/token_pricing.yaml`.

    Returns:
        Parsed pricing configuration.

    Raises:
        FileNotFoundError: If the pricing file does not exist.
    """
    p = Path(path) if path else _PRICING_PATH
    if not p.exists():
        raise FileNotFoundError(f"Thiếu bảng giá token: {p}")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_peak(ts: datetime | None = None, pricing: dict | None = None) -> bool:
    """Determine whether a time falls in the provider's peak-hours window.

    Args:
        ts: Time to check. Defaults to the current UTC time.
        pricing: Preloaded pricing configuration. Defaults to loading it from the file.

    Returns:
        True if the time is inside the peak window, otherwise False.
    """
    pricing = pricing or load_pricing()
    ts = (ts or datetime.now(timezone.utc)).astimezone(timezone.utc)
    win = pricing.get("peak_windows_utc") or {}
    if ts.weekday() not in set(win.get("weekdays") or []):
        return False
    for rng in win.get("ranges") or []:
        if rng["start_hour"] <= ts.hour < rng["end_hour"]:
            return True
    return False


def billed_usd(uncached: int, cache_read: int, output: int, *,
               peak: bool | None = None, ts: datetime | None = None,
               model: str = "deepseek-flash", pricing: dict | None = None) -> float:
    """Compute the monetary cost from three separate token buckets.

    Args:
        uncached: Input tokens that missed the cache.
        cache_read: Input tokens that hit the cache.
        output: Output tokens, including reasoning.
        peak: Force peak or off-peak pricing. Defaults to being derived from `ts`.
        ts: Time the cost was incurred, used when `peak` is not given.
        model: Model name looked up in the price table.
        pricing: Preloaded pricing configuration.

    Returns:
        Cost in USD.
    """
    pricing = pricing or load_pricing()
    if peak is None:
        peak = is_peak(ts, pricing)
    table = pricing["models"][model]["peak" if peak else "off_peak"]
    unit = float(pricing.get("unit_tokens", 1_000_000))
    return (uncached * table["input_cache_miss"]
            + cache_read * table["input_cache_hit"]
            + output * table["output"]) / unit


# ---------------------------------------------------------------------------
# Projection checkpoint: per-session aggregate source
# ---------------------------------------------------------------------------
@dataclass
class SessionUsage:
    """Aggregate measurements of one DSH session read from a projection checkpoint file.

    Attributes:
        session_id: Session identifier (checkpoint file stem).
        cwd: Working directory of the session.
        uncached_input: Input tokens that missed the cache.
        output: Output tokens.
        cache_read: Input tokens that hit the cache.
        cache_write: Cache write tokens.
        turns: Last turn number.
        steps: Last step number.
        surface_tokens: System plus message tokens, excluding tools.
        pressure_tokens: Total input of the latest sample, excluding output.
        context_window: Context window size in tokens.
        seq: Sequence number of the `tokenUsage` row.
        mtime: Modification time of the checkpoint file, epoch seconds.
        path: Checkpoint file path.
        created_at: Session creation time, epoch seconds.
    """

    session_id: str
    cwd: str = ""
    uncached_input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    turns: int = 0
    steps: int = 0
    surface_tokens: int = 0
    pressure_tokens: int = 0
    context_window: int = 0
    seq: int = 0
    mtime: float = 0.0
    path: str = ""
    created_at: float = 0.0

    @property
    def is_child(self) -> bool:
        """Whether the session is a child spawned by a parent agent.

        A top-level session has the id `session-<uuid>`, while the child session of an agent
        call has a bare uuid. This is the only marker in the checkpoint that tells a worker
        from an orchestrating session, because a child inherits the parent's preset.

        Returns:
            True when the session id lacks the `session-` prefix.
        """
        return not self.session_id.startswith("session-")

    @property
    def quota_tokens(self) -> int:
        """Total tokens counted against the quota, including cache hits.

        Returns:
            Sum of the three buckets: uncached input, cached input and output.
        """
        return self.uncached_input + self.cache_read + self.output

    @property
    def pressure_ratio(self) -> float:
        """Fill ratio of the session context window.

        Returns:
            A value from 0 to 1; 0 when the window size is unknown.
        """
        return (self.pressure_tokens / self.context_window) if self.context_window else 0.0

    def usd(self, *, peak: bool | None = None, pricing: dict | None = None) -> float:
        """Convert the session measurements to a monetary cost.

        Args:
            peak: Force peak or off-peak pricing.
            pricing: Preloaded pricing configuration.

        Returns:
            Session cost in USD.
        """
        ts = datetime.fromtimestamp(self.mtime, tz=timezone.utc) if self.mtime else None
        return billed_usd(self.uncached_input, self.cache_read, self.output,
                          peak=peak, ts=ts, pricing=pricing)


def _row_val(rows: dict, key: str) -> dict:
    """Extract the value part of one projection row.

    Args:
        rows: Projection rows of the session.
        key: Name of the row to take.

    Returns:
        Content of the row's `val` field, or an empty dict if absent.
    """
    node = rows.get(key) or {}
    val = node.get("val")
    return val if isinstance(val, dict) else {}


def read_projcache(path: str | Path) -> SessionUsage | None:
    """Read one projection checkpoint file into session measurements.

    Args:
        path: Path of the JSON checkpoint file.

    Returns:
        The session measurements, or None if the file is corrupt or malformed.
    """
    p = Path(path)
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    record = doc.get("record") or {}
    rows = record.get("rows") or {}
    identity = record.get("identity") or {}

    usage = _row_val(rows, "tokenUsage")
    totals = usage.get("totals") or {}
    last = usage.get("last") or {}
    pressure = _row_val(rows, "contextPressure")

    return SessionUsage(
        session_id=p.stem,
        cwd=identity.get("cwd", ""),
        uncached_input=int(totals.get("uncachedInputTokens") or 0),
        output=int(totals.get("outputTokens") or 0),
        cache_read=int(totals.get("cacheReadTokens") or 0),
        cache_write=int(totals.get("cacheWriteTokens") or 0),
        turns=int(last.get("turn") or 0),
        steps=int(last.get("step") or 0),
        surface_tokens=int(pressure.get("surfaceTokens") or 0),
        pressure_tokens=int(pressure.get("pressureTokens") or 0),
        context_window=int(pressure.get("contextWindow") or 0),
        seq=int((rows.get("tokenUsage") or {}).get("seq") or 0),
        mtime=p.stat().st_mtime,
        path=str(p),
        created_at=_created_epoch(identity.get("createdAt")),
    )


def _created_epoch(raw) -> float:
    """Convert the checkpoint session creation time from milliseconds to epoch seconds.

    Args:
        raw: Value of `identity.createdAt`, a number or a string of milliseconds.

    Returns:
        Epoch seconds, or 0 when missing or unreadable.
    """
    try:
        return int(raw) / 1000.0
    except (TypeError, ValueError):
        return 0.0


def iter_sessions(cwd_filter: str | None = None, *, since: float = 0.0) -> list[SessionUsage]:
    """List the measurements of DSH sessions, newest first.

    Args:
        cwd_filter: Keep only sessions whose working directory contains this string. None keeps all.
        since: Keep only sessions modified after this epoch time.

    Returns:
        Session measurements sorted by modification time, descending.
    """
    root = projcache_dir()
    if not root.is_dir():
        return []
    out: list[SessionUsage] = []
    for p in root.glob("*.json"):
        su = read_projcache(p)
        if su is None or su.mtime < since:
            continue
        if cwd_filter and cwd_filter.lower() not in (su.cwd or "").lower():
            continue
        out.append(su)
    out.sort(key=lambda s: s.mtime, reverse=True)
    return out


# ---------------------------------------------------------------------------
# JSONL log: per-step detail source
# ---------------------------------------------------------------------------
def _decode_with_cli(blob: bytes) -> bytes | None:
    """Decompress with the external `zstd` program if installed.

    Args:
        blob: Multi-frame compressed data.

    Returns:
        Decompressed data, or None if the program is missing or the command fails.
    """
    exe = shutil.which("zstd")
    if not exe:
        return None
    with tempfile.NamedTemporaryFile(suffix=".zst", delete=False) as tmp:
        tmp.write(blob)
        tmp_path = tmp.name
    try:
        res = subprocess.run([exe, "-dc", tmp_path], capture_output=True, timeout=120)
        return res.stdout if res.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _decode_with_python(blob: bytes) -> bytes | None:
    """Decompress with a Python zstd library if installed.

    Frames are located manually by magic number because the log file is a sequence of
    concatenated frames; a single decompress call returns only the first frame.

    Args:
        blob: Multi-frame compressed data.

    Returns:
        Decompressed data, or None if no suitable library is available.
    """
    decompress = None
    try:
        import zstandard

        decompress = zstandard.ZstdDecompressor().decompress
    except ImportError:
        try:
            import pyzstd

            decompress = pyzstd.decompress
        except ImportError:
            try:
                from compression import zstd as _cz

                decompress = _cz.decompress
            except ImportError:
                return None

    parts: list[bytes] = []
    for start, end in _frame_spans(blob):
        try:
            parts.append(decompress(blob[start:end]))
        except Exception:
            continue
    return b"".join(parts) if parts else None


def _decode_with_node(blob: bytes) -> bytes | None:
    """Decompress with Node, one frame at a time.

    DSH runs on Node, so this fallback is almost always available.

    Args:
        blob: Multi-frame compressed data.

    Returns:
        Decompressed data, or None if Node cannot be called.
    """
    if not shutil.which("node"):
        return None
    spans = _frame_spans(blob)
    if not spans:
        return None
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.bin"
        src.write_bytes(blob)
        offsets = json.dumps(spans)
        script = (
            "const fs=require('fs'),z=require('zlib');"
            f"const b=fs.readFileSync({json.dumps(str(src))});"
            f"const sp={offsets};const out=[];"
            "for(const [s,e] of sp){try{out.push(z.zstdDecompressSync(b.subarray(s,e)));}catch(_){}}"
            "process.stdout.write(Buffer.concat(out));"
        )
        try:
            res = subprocess.run(["node", "-e", script], capture_output=True, timeout=180)
            return res.stdout if res.returncode == 0 and res.stdout else None
        except (OSError, subprocess.SubprocessError):
            return None


def _frame_spans(blob: bytes) -> list[list[int]]:
    """Locate the start and end of each compressed frame in the data.

    Args:
        blob: Multi-frame compressed data.

    Returns:
        List of [start, end) index pairs, one per frame.
    """
    starts: list[int] = []
    pos = blob.find(ZSTD_MAGIC)
    while pos != -1:
        starts.append(pos)
        pos = blob.find(ZSTD_MAGIC, pos + 4)
    return [[s, starts[i + 1] if i + 1 < len(starts) else len(blob)]
            for i, s in enumerate(starts)]


def decode_session_log(path: str | Path) -> str | None:
    """Decompress a session log into JSONL text.

    Tries the `zstd` program, then a Python library, then Node. Returns None when no route
    is available; callers must handle this because every core measurement is still
    available from the projection checkpoint.

    Args:
        path: Path of the `session.v3.jsonl.zstd` file.

    Returns:
        JSONL content as text, or None if it cannot be decompressed.
    """
    p = Path(path)
    if not p.exists():
        return None
    if p.suffix != ".zstd":
        return p.read_text(encoding="utf-8", errors="replace")
    blob = p.read_bytes()
    for decoder in (_decode_with_cli, _decode_with_python, _decode_with_node):
        data = decoder(blob)
        if data:
            return data.decode("utf-8", errors="replace")
    return None


def message_usage(path: str | Path) -> list[dict]:
    """Extract the token measurements of each assistant message in a session.

    This is the only route to `reasoningTokens`, which the projection checkpoint lacks but
    which is needed to check the worker invariant that reasoning is off.

    Args:
        path: Path of the session log file.

    Returns:
        Measurement dicts in order of appearance; empty if the log cannot be decompressed.
    """
    text = decode_session_log(path)
    if not text:
        return []
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or '"usage"' not in line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = ev.get("data") or {}
        usage = data.get("usage")
        if not isinstance(usage, dict):
            continue
        rows.append({
            "seq": ev.get("seq"),
            "time": ev.get("time"),
            "input_tokens": int(usage.get("inputTokens") or 0),
            "output_tokens": int(usage.get("outputTokens") or 0),
            "cache_read_tokens": int(usage.get("cacheReadTokens") or 0),
            "reasoning_tokens": int(usage.get("reasoningTokens") or 0),
            "total_tokens": int(usage.get("totalTokens") or 0),
        })
    return rows


def find_session_log(session_id: str) -> Path | None:
    """Find the JSONL log file of a session id.

    Args:
        session_id: Session id, with or without the `session-` prefix.

    Returns:
        Path of the log file, or None if not found.
    """
    root = sessions_dir()
    if not root.is_dir():
        return None
    uuid = session_id[len("session-"):] if session_id.startswith("session-") else session_id
    for ws in root.iterdir():
        if not ws.is_dir():
            continue
        for cand in (ws / uuid, ws / f"session-{uuid}"):
            if cand.is_dir():
                for name in ("session.v3.jsonl.zstd", "session.v3.jsonl"):
                    f = cand / name
                    if f.exists():
                        return f
    return None


# ---------------------------------------------------------------------------
# Per-wave aggregation
# ---------------------------------------------------------------------------
@dataclass
class WaveUsage:
    """Combined measurements of one processing wave, covering the orchestrating session and all child sessions.

    Attributes:
        sessions: Sessions included in the wave.
        reasoning_tokens: Total reasoning tokens read from the session logs.
        reasoning_known: True if reasoning tokens could be read from at least one log.
    """

    sessions: list[SessionUsage] = field(default_factory=list)
    reasoning_tokens: int = 0
    reasoning_known: bool = False

    @property
    def uncached_input(self) -> int:
        """Total uncached input tokens of the wave.

        Returns:
            Sum of uncached tokens.
        """
        return sum(s.uncached_input for s in self.sessions)

    @property
    def cache_read(self) -> int:
        """Total cache-hit input tokens of the wave.

        Returns:
            Sum of cache-hit tokens.
        """
        return sum(s.cache_read for s in self.sessions)

    @property
    def output(self) -> int:
        """Total output tokens of the wave.

        Returns:
            Sum of generated tokens.
        """
        return sum(s.output for s in self.sessions)

    @property
    def quota_tokens(self) -> int:
        """Total tokens counted against the quota for the wave.

        Returns:
            Sum of the three token buckets across every session in the wave.
        """
        return self.uncached_input + self.cache_read + self.output

    @property
    def hit_ratio(self) -> float:
        """Share of input tokens that hit the cache.

        Returns:
            A value from 0 to 1; 0 when there are no input tokens.
        """
        total_in = self.uncached_input + self.cache_read
        return (self.cache_read / total_in) if total_in else 0.0

    def usd(self, *, peak: bool | None = None, pricing: dict | None = None) -> float:
        """Convert the wave measurements to a monetary cost.

        Args:
            peak: Force peak or off-peak pricing.
            pricing: Preloaded pricing configuration.

        Returns:
            Wave cost in USD.
        """
        return billed_usd(self.uncached_input, self.cache_read, self.output,
                          peak=peak, pricing=pricing)


def wave_usage(since: float, *, cwd_filter: str | None = None,
               with_reasoning: bool = True, workers_only: bool = False) -> WaveUsage:
    """Combine the measurements of every session active after a point in time.

    Child-agent cost is not in the parent session's measurements because each child is its
    own Session, so this function scans all new sessions instead of reading only the parent.

    Checkpoint figures are cumulative over the whole session life. Filtering by modification
    time therefore also pulls in sessions opened days earlier that were still active during the
    wave, with all of their tokens. `workers_only` keeps only child sessions CREATED after the
    cutoff, which are exactly the worker calls of the wave.

    Args:
        since: Epoch cutoff; only sessions modified after it are combined.
        cwd_filter: Combine only sessions whose working directory contains this string.
        with_reasoning: If True, also try to read `reasoningTokens` from the JSONL logs.
        workers_only: Combine only child sessions created after `since`.

    Returns:
        Combined measurements of the wave.
    """
    sessions = iter_sessions(cwd_filter, since=since)
    if workers_only:
        sessions = [s for s in sessions if s.is_child and s.created_at >= since]
    wave = WaveUsage(sessions=sessions)
    if not with_reasoning:
        return wave
    total = 0
    known = False
    for s in sessions:
        log = find_session_log(s.session_id)
        if not log:
            continue
        rows = message_usage(log)
        if rows:
            known = True
            total += sum(r["reasoning_tokens"] for r in rows)
    wave.reasoning_tokens = total
    wave.reasoning_known = known
    return wave
