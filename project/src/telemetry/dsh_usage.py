"""Đọc số đo token, áp suất ngữ cảnh và chi phí thật từ runtime DSH.

Module này là nguồn số liệu duy nhất cho `token_ledger.py`, `ctx_probe.py` và
`pipeline_radar.py token`. Nó thay thế hoàn toàn các hằng số ước lượng cũ
(450 token/bài tầng L1, 1.470 token/bài tầng Gold) vốn lệch thực tế 21-41 lần.

Sáu luật kế toán bắt buộc, mỗi luật đã đối soát bằng số thật trên máy này:

1. `inputTokens` trong event DSH là phần **chưa cache**, không phải kích thước
   prompt. Hiểu nhầm trường này làm hụt chi phí khoảng 30 lần.
2. Trong một request, `inputTokens + cacheReadTokens + outputTokens == totalTokens`.
   `totalTokens` KHÔNG tích lũy, nên tuyệt đối không cộng dồn nó qua các request.
3. `reasoningTokens` là tập con của `outputTokens`. Cộng cả hai là đếm trùng.
4. `cacheWriteTokens` luôn bằng 0 với adapter DeepSeek, không dựng dòng chi phí cho nó.
5. DSH không lưu bất kỳ dữ liệu giá nào, nên tiền luôn tính ngoài từ
   `config/token_pricing.yaml`.
6. `contextPressure.surfaceTokens` là `systemTokens + messageTokens` và KHÔNG gồm
   `toolsTokens`; `pressureTokens` là tổng input của mẫu mới nhất và KHÔNG gồm output.

Chi phí của agent con KHÔNG xuất hiện trong `tokenUsage` của phiên cha: mỗi con là
một Session riêng có tệp projcache riêng. Muốn biết chi phí trọn một wave phải cộng
cả phiên cha lẫn từng phiên con, xem :func:`wave_usage`.
"""
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

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"

_PRICING_PATH = Path(__file__).resolve().parents[2] / "config" / "token_pricing.yaml"


def dsh_home() -> Path:
    """Xác định thư mục gốc của DSH trên máy hiện tại.

    Returns:
        Đường dẫn tới `%DSH_HOME%` nếu biến môi trường được đặt, ngược lại là `~/.dsh`.
    """
    env = os.environ.get("DSH_HOME")
    return Path(env) if env else Path.home() / ".dsh"


def projcache_dir() -> Path:
    """Trả về thư mục chứa các tệp checkpoint projection của phiên DSH.

    Returns:
        Đường dẫn tới thư mục `storages/session_projcache/sessions`.
    """
    return dsh_home() / "storages" / "session_projcache" / "sessions"


def sessions_dir() -> Path:
    """Trả về thư mục chứa nhật ký JSONL của các phiên DSH.

    Returns:
        Đường dẫn tới thư mục `sessions`.
    """
    return dsh_home() / "sessions"


# ---------------------------------------------------------------------------
# Bảng giá
# ---------------------------------------------------------------------------
def load_pricing(path: str | Path | None = None) -> dict:
    """Nạp bảng giá token từ tệp cấu hình.

    Args:
        path: Đường dẫn tệp giá. Mặc định dùng `config/token_pricing.yaml`.

    Returns:
        Từ điển cấu hình giá đã phân tích cú pháp.

    Raises:
        FileNotFoundError: Khi tệp giá không tồn tại.
    """
    p = Path(path) if path else _PRICING_PATH
    if not p.exists():
        raise FileNotFoundError(f"Thiếu bảng giá token: {p}")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def is_peak(ts: datetime | None = None, pricing: dict | None = None) -> bool:
    """Xác định một thời điểm có rơi vào khung giờ cao điểm của nhà cung cấp không.

    Args:
        ts: Thời điểm cần xét. Mặc định là thời điểm hiện tại theo UTC.
        pricing: Cấu hình giá đã nạp sẵn. Mặc định tự nạp từ tệp.

    Returns:
        True khi thời điểm nằm trong khung cao điểm, ngược lại False.
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
    """Tính chi phí tiền tệ từ ba rổ token rời rạc.

    Args:
        uncached: Số token đầu vào không trúng bộ nhớ đệm.
        cache_read: Số token đầu vào trúng bộ nhớ đệm.
        output: Số token đầu ra, đã bao gồm phần suy luận.
        peak: Ép dùng giá cao điểm hoặc thấp điểm. Mặc định suy ra từ `ts`.
        ts: Thời điểm phát sinh chi phí, dùng khi `peak` không được chỉ định.
        model: Tên model tra trong bảng giá.
        pricing: Cấu hình giá đã nạp sẵn.

    Returns:
        Chi phí quy đổi ra USD.
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
# Checkpoint projection — nguồn tổng hợp theo phiên
# ---------------------------------------------------------------------------
@dataclass
class SessionUsage:
    """Số đo tổng hợp của một phiên DSH đọc từ tệp checkpoint projection."""

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

    @property
    def quota_tokens(self) -> int:
        """Tổng token tính vào hạn mức, gồm cả phần trúng bộ nhớ đệm.

        Returns:
            Tổng của ba rổ token đầu vào chưa cache, đầu vào trúng cache và đầu ra.
        """
        return self.uncached_input + self.cache_read + self.output

    @property
    def pressure_ratio(self) -> float:
        """Tỷ lệ lấp đầy cửa sổ ngữ cảnh của phiên.

        Returns:
            Giá trị từ 0 đến 1; trả về 0 khi chưa biết kích thước cửa sổ.
        """
        return (self.pressure_tokens / self.context_window) if self.context_window else 0.0

    def usd(self, *, peak: bool | None = None, pricing: dict | None = None) -> float:
        """Quy đổi số đo của phiên ra chi phí tiền tệ.

        Args:
            peak: Ép dùng giá cao điểm hoặc thấp điểm.
            pricing: Cấu hình giá đã nạp sẵn.

        Returns:
            Chi phí USD của phiên.
        """
        ts = datetime.fromtimestamp(self.mtime, tz=timezone.utc) if self.mtime else None
        return billed_usd(self.uncached_input, self.cache_read, self.output,
                          peak=peak, ts=ts, pricing=pricing)


def _row_val(rows: dict, key: str) -> dict:
    """Bóc phần giá trị của một hàng projection.

    Args:
        rows: Từ điển các hàng projection của phiên.
        key: Tên hàng cần lấy.

    Returns:
        Nội dung trường `val` của hàng, hoặc từ điển rỗng khi không có.
    """
    node = rows.get(key) or {}
    val = node.get("val")
    return val if isinstance(val, dict) else {}


def read_projcache(path: str | Path) -> SessionUsage | None:
    """Đọc một tệp checkpoint projection thành số đo phiên.

    Args:
        path: Đường dẫn tệp JSON checkpoint.

    Returns:
        Đối tượng số đo phiên, hoặc None khi tệp hỏng hoặc không đúng định dạng.
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
    )


def iter_sessions(cwd_filter: str | None = None, *, since: float = 0.0) -> list[SessionUsage]:
    """Liệt kê số đo của các phiên DSH, mới nhất trước.

    Args:
        cwd_filter: Chỉ giữ phiên có thư mục làm việc chứa chuỗi này. None là lấy tất cả.
        since: Chỉ giữ phiên có thời điểm sửa đổi lớn hơn mốc epoch này.

    Returns:
        Danh sách số đo phiên sắp xếp giảm dần theo thời điểm sửa đổi.
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
# Nhật ký JSONL — nguồn chi tiết theo từng bước
# ---------------------------------------------------------------------------
def _decode_with_cli(blob: bytes) -> bytes | None:
    """Giải nén bằng chương trình `zstd` ngoài nếu có sẵn trên máy.

    Args:
        blob: Dữ liệu nén nhiều khung.

    Returns:
        Dữ liệu đã giải nén, hoặc None khi không có chương trình hoặc lệnh thất bại.
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
    """Giải nén bằng thư viện zstd của Python nếu môi trường có cài.

    Quét thủ công theo số nhận dạng khung vì tệp nhật ký là chuỗi nhiều khung nối
    tiếp; gọi giải nén một lần chỉ trả về khung đầu tiên.

    Args:
        blob: Dữ liệu nén nhiều khung.

    Returns:
        Dữ liệu đã giải nén, hoặc None khi không có thư viện phù hợp.
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
    """Giải nén bằng Node bằng cách xử lý từng khung một.

    DSH chạy trên Node nên đây là đường dự phòng gần như luôn dùng được.

    Args:
        blob: Dữ liệu nén nhiều khung.

    Returns:
        Dữ liệu đã giải nén, hoặc None khi không gọi được Node.
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
    """Xác định vị trí bắt đầu và kết thúc của từng khung nén trong tệp.

    Args:
        blob: Dữ liệu nén nhiều khung.

    Returns:
        Danh sách cặp chỉ số [bắt đầu, kết thúc) của mỗi khung.
    """
    starts: list[int] = []
    pos = blob.find(ZSTD_MAGIC)
    while pos != -1:
        starts.append(pos)
        pos = blob.find(ZSTD_MAGIC, pos + 4)
    return [[s, starts[i + 1] if i + 1 < len(starts) else len(blob)]
            for i, s in enumerate(starts)]


def decode_session_log(path: str | Path) -> str | None:
    """Giải nén nhật ký phiên thành văn bản JSONL.

    Thử lần lượt chương trình `zstd`, thư viện Python, rồi Node. Trả về None khi
    không đường nào khả dụng; phía gọi phải xử lý được trường hợp này vì mọi số đo
    cốt lõi vẫn lấy được từ checkpoint projection.

    Args:
        path: Đường dẫn tệp `session.v3.jsonl.zstd`.

    Returns:
        Nội dung JSONL dạng văn bản, hoặc None khi không giải nén được.
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
    """Bóc số đo token của từng thông điệp trợ lý trong một phiên.

    Đây là đường duy nhất lấy được `reasoningTokens`, thứ không có trong checkpoint
    projection nhưng cần để kiểm bất biến tắt suy luận của worker.

    Args:
        path: Đường dẫn tệp nhật ký phiên.

    Returns:
        Danh sách từ điển số đo theo thứ tự xuất hiện; rỗng khi không giải nén được.
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
    """Tìm tệp nhật ký JSONL tương ứng với một mã phiên.

    Args:
        session_id: Mã phiên, có hoặc không có tiền tố `session-`.

    Returns:
        Đường dẫn tệp nhật ký, hoặc None khi không tìm thấy.
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
# Tổng hợp theo wave
# ---------------------------------------------------------------------------
@dataclass
class WaveUsage:
    """Số đo gộp của một đợt xử lý, gồm phiên điều phối và toàn bộ phiên con."""

    sessions: list[SessionUsage] = field(default_factory=list)
    reasoning_tokens: int = 0
    reasoning_known: bool = False

    @property
    def uncached_input(self) -> int:
        """Tổng token đầu vào chưa trúng bộ nhớ đệm của cả đợt.

        Returns:
            Tổng số token chưa cache.
        """
        return sum(s.uncached_input for s in self.sessions)

    @property
    def cache_read(self) -> int:
        """Tổng token đầu vào trúng bộ nhớ đệm của cả đợt.

        Returns:
            Tổng số token trúng cache.
        """
        return sum(s.cache_read for s in self.sessions)

    @property
    def output(self) -> int:
        """Tổng token đầu ra của cả đợt.

        Returns:
            Tổng số token sinh ra.
        """
        return sum(s.output for s in self.sessions)

    @property
    def quota_tokens(self) -> int:
        """Tổng token tính vào hạn mức của cả đợt.

        Returns:
            Tổng ba rổ token của mọi phiên trong đợt.
        """
        return self.uncached_input + self.cache_read + self.output

    @property
    def hit_ratio(self) -> float:
        """Tỷ lệ token đầu vào trúng bộ nhớ đệm.

        Returns:
            Giá trị từ 0 đến 1; trả về 0 khi chưa có token đầu vào nào.
        """
        total_in = self.uncached_input + self.cache_read
        return (self.cache_read / total_in) if total_in else 0.0

    def usd(self, *, peak: bool | None = None, pricing: dict | None = None) -> float:
        """Quy đổi số đo của đợt ra chi phí tiền tệ.

        Args:
            peak: Ép dùng giá cao điểm hoặc thấp điểm.
            pricing: Cấu hình giá đã nạp sẵn.

        Returns:
            Chi phí USD của cả đợt.
        """
        return billed_usd(self.uncached_input, self.cache_read, self.output,
                          peak=peak, pricing=pricing)


def wave_usage(since: float, *, cwd_filter: str | None = None,
               with_reasoning: bool = True) -> WaveUsage:
    """Gộp số đo của mọi phiên phát sinh sau một mốc thời gian.

    Chi phí của agent con không nằm trong số đo của phiên cha vì mỗi con là một
    Session riêng, nên hàm này quét toàn bộ phiên mới thay vì chỉ đọc phiên cha.

    Args:
        since: Mốc epoch, chỉ gộp phiên có thời điểm sửa đổi lớn hơn mốc này.
        cwd_filter: Chỉ gộp phiên thuộc thư mục làm việc chứa chuỗi này.
        with_reasoning: Có cố đọc thêm `reasoningTokens` từ nhật ký JSONL không.

    Returns:
        Số đo gộp của cả đợt.
    """
    sessions = iter_sessions(cwd_filter, since=since)
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
