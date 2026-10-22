"""Record and report measured DSH runtime token usage in the `token_ledger` table."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.prefix import cached_prefix_tokens    # noqa: E402
from src.core import paths                           # noqa: E402
from src.core.stdio import force_utf8_stdio          # noqa: E402
from src.telemetry.dsh_usage import (                # noqa: E402
    is_peak,
    load_pricing,
    wave_usage,
)
from src.db.connect import open_rw  # noqa: E402

force_utf8_stdio()

HARNESS_DB = str(paths.harness_db_path())

# The wave descriptor sits next to the packets; it gives the number of worker CALLS
# in a wave, which differs from the DSH session count because that includes Conductor sessions.
TASK_DIR = str(paths.article_packets_dir())

SCHEMA = """
CREATE TABLE IF NOT EXISTS token_ledger (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT    NOT NULL,
    wave             TEXT,
    batch_id         TEXT,
    agent_id         TEXT    NOT NULL DEFAULT 'article-processor',
    n_items          INTEGER NOT NULL DEFAULT 0,
    n_sessions       INTEGER NOT NULL DEFAULT 0,
    miss_tokens      INTEGER NOT NULL DEFAULT 0,
    hit_tokens       INTEGER NOT NULL DEFAULT 0,
    out_tokens       INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER,
    quota_tokens     INTEGER NOT NULL DEFAULT 0,
    turns_max        INTEGER NOT NULL DEFAULT 0,
    ctx_peak         INTEGER NOT NULL DEFAULT 0,
    ctx_pct          REAL    NOT NULL DEFAULT 0,
    est_miss         INTEGER,
    est_out          INTEGER,
    billed_usd       REAL    NOT NULL DEFAULT 0,
    peak_window      INTEGER NOT NULL DEFAULT 0,
    note             TEXT
);
CREATE INDEX IF NOT EXISTS idx_token_ledger_wave ON token_ledger(wave);
CREATE INDEX IF NOT EXISTS idx_token_ledger_ts   ON token_ledger(ts);
"""


RUNNER_SOURCES = ("agy", "openrouter", "opencode-native", "auto")
# agy unit prices (USD per 1M tokens), taken from the Gemini Flash Low price table (ADR 0011).
AGY_USD_PER_M = {"in": 0.075, "out": 0.30}


def normalize_usage(provider: str, usage: dict | None) -> dict:
    """Map the `usage` block of each provider onto one common set of ledger columns.

    Args:
        provider: Provider name recorded in the meta file (`agy`, `openrouter`, `opencode-native`).
        usage: The `usage` block of the meta file; may be missing or contain no numbers.

    Returns:
        Dict with `miss`, `hit`, `out`, `reasoning`, `usd`, `has_usage`.
    """
    u = usage if isinstance(usage, dict) else {}
    if provider == "agy" or "input_tokens" in u:
        hit = int(u.get("cache_read_tokens") or 0)
        prompt = int(u.get("input_tokens") or 0)
        out = int(u.get("output_tokens") or 0)
        reasoning = int(u.get("thinking_tokens") or 0)
        usd = ((prompt - hit) * AGY_USD_PER_M["in"] + out * AGY_USD_PER_M["out"]) / 1e6
        return {"miss": max(0, prompt - hit), "hit": hit, "out": out, "reasoning": reasoning,
                "usd": usd, "has_usage": bool(prompt or out)}
    prompt = int(u.get("prompt_tokens") or 0)
    if not prompt and not u.get("completion_tokens") and u.get("total_tokens"):
        prompt = int(u["total_tokens"])
    hit = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    out = int(u.get("completion_tokens") or 0)
    reasoning = int((u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    try:
        usd = float(u.get("cost") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    return {"miss": max(0, prompt - hit), "hit": hit, "out": out, "reasoning": reasoning,
            "usd": usd, "has_usage": bool(prompt or out)}


def aggregate_meta(meta_files: list[str], fallback: str | None) -> dict[str, dict]:
    """Sum the `usage` of meta files per the provider recorded in each file.

    A wave can run its first pass on agy and be patched with openrouter, so assigning
    the whole wave to one provider would misattribute the cost.

    Args:
        meta_files: Paths of the `*.meta.json` files of the wave.
        fallback: Provider used when a meta file has no `agent_provider`.

    Returns:
        Dict keyed by provider with `batches`, `items`, the token columns, `usd`, `has_usage`.
    """
    totals: dict[str, dict] = {}
    for mf in meta_files:
        try:
            with open(mf, encoding="utf-8") as f:
                mdata = json.load(f)
        except (OSError, ValueError):
            continue
        provider = mdata.get("agent_provider") or fallback
        if not provider or provider == "auto":
            continue
        u = normalize_usage(provider, mdata.get("usage"))
        t = totals.setdefault(provider, {"batches": 0, "items": 0, "miss": 0, "hit": 0,
                                         "out": 0, "reasoning": 0, "usd": 0.0,
                                         "has_usage": False})
        t["batches"] += 1
        t["items"] += int(mdata.get("items_valid") or 0)
        for k in ("miss", "hit", "out", "reasoning", "usd"):
            t[k] += u[k]
        t["has_usage"] = t["has_usage"] or u["has_usage"]
    return totals


def latest_snapshots(rows: list) -> list:
    """Keep the latest snapshot of each wave and drop older snapshots of the same wave.

    `append` writes a **cumulative** snapshot on every run, not an increment: a rerun
    for the same wave as child sessions finish yields a row that contains the previous
    row in full. Wave W2 has four such rows, and summing them directly yields 800
    articles for a 200-article wave.

    The latest-row convention already exists in `estimate_wave.py`; this function lets
    every tool share that single convention.

    Args:
        rows: Ledger rows in ascending write order.

    Returns:
        Rows remaining after older snapshots are removed.
    """
    latest: dict[tuple, object] = {}
    for r in rows:
        latest[(r["wave"], r["batch_id"], r["agent_id"])] = r
    return list(latest.values())


def worker_calls(wave: str | None) -> int | None:
    """Return the real number of worker calls of a wave, read from the wave descriptor on disk.

    Args:
        wave: Wave identifier.

    Returns:
        Number of worker calls, or None when the wave descriptor is absent.
    """
    if not wave:
        return None
    path = os.path.join(TASK_DIR, f"wave_{wave}.json")
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return None
    n = len(m.get("batches") or [])
    if not n:
        return None
    return n + (1 if m.get("warmed") else 0)


def cache_shortfall(cache_read: int, n_sessions: int, prefix_tokens: int,
                    calls: int | None = None) -> tuple[int, int]:
    """Compare the measured cache-hit tokens with the minimum that must hit.

    Every worker call sends the same static prefix. The first call writes the cache and
    each later call must read back roughly the whole prefix at the cache-hit price. The
    minimum floor is therefore `prefix * (worker calls - 1)`; a value below the floor
    means the prefix drifted between calls, and the drifted part is billed at the
    uncached token price, which is about fifty times higher.

    This is the only check that detects cache slippage. The aggregate cache-hit ratio of
    a wave does **not** detect it: the ratio stays high when calls repeat steps even if
    the prefix misses entirely.

    The count is by worker call, not by session. A two-batch wave has up to four
    sessions: the Conductor session, the warm-up call and the two batches. The Conductor
    session has a different persona and tool set, so it does **not** read the worker
    prefix; counting it in the floor would demand a cache amount that never exists and
    raise false alarms on every normal wave.

    Args:
        cache_read: Measured cache-hit tokens of the whole wave.
        n_sessions: DSH session count of the wave, used only when the call count is unknown.
        prefix_tokens: Size of the static prefix.
        calls: Real number of worker calls. When omitted it is derived from the session
            count, and the floor is then only a rough estimate.

    Returns:
        Pair of the minimum floor and the shortfall against it; a shortfall of 0 passes.
    """
    n = calls if calls else max(0, n_sessions - 1)
    expected = max(0, prefix_tokens) * max(0, n - 1)
    return expected, max(0, expected - max(0, cache_read))


def connect(db_path: str = HARNESS_DB) -> sqlite3.Connection:
    """Open the ledger connection and ensure the table schema exists.

    Args:
        db_path: Path of the `harness.db` file.

    Returns:
        Ready-to-use SQLite connection.
    """
    conn = open_rw(db_path, row_factory=True)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def cmd_init(args: argparse.Namespace) -> int:
    """Create the ledger table if it does not exist.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0.
    """
    conn = connect(args.db)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(token_ledger)")]
    conn.close()
    print(f"✅ Bảng token_ledger sẵn sàng tại {args.db} ({len(cols)} cột).")
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    """Aggregate the measurements of sessions created after a cutoff into one ledger row.

    Child agent cost is not part of the parent session measurement because each child is
    its own Session, so this function scans all new sessions instead of reading only the
    coordinating session.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 when a row is written, 2 when no session is found in the range.
    """
    since = args.since if args.since is not None else time.time() - args.window_min * 60
    workers_only = getattr(args, "workers_only", False)

    manifest_path = os.path.join(TASK_DIR, f"wave_{args.wave}.json") if getattr(args, "wave", None) else None
    is_agy = getattr(args, "source", None) == "agy"
    if not is_agy and manifest_path and os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                mf = json.load(f)
                if mf.get("runner") == "agy":
                    is_agy = True
        except Exception:
            pass
    source = getattr(args, "source", None)
    is_runner_meta = is_agy or source in RUNNER_SOURCES

    if is_runner_meta:
        fallback = "agy" if is_agy and source in (None, "auto") else source
        out_dir = str(paths.agent_outputs_dir("_article"))
        meta_files = glob.glob(os.path.join(out_dir, f"article_{args.wave}_*.meta.json"))
        if not meta_files:
            print(f"⚠️  Không tìm thấy tệp meta nào của runner cho đợt {args.wave}. Không ghi gì.")
            return 2
        totals = aggregate_meta(meta_files, fallback)
        if not totals:
            print(f"⚠️  Tệp meta của đợt {args.wave} không ghi provider. Truyền --source.")
            return 2
        conn = connect(args.db)
        # Runner figures are summed from every meta file of the wave, so they already form
        # a full-wave snapshot: a rerun of `--finish` replaces all earlier runner rows of
        # the wave instead of adding duplicates.
        conn.execute("DELETE FROM token_ledger WHERE wave IS ? AND batch_id IS ? "
                     "AND agent_id LIKE 'article-processor-%'", (args.wave, args.batch))
        single = len(totals) == 1
        for provider, t in sorted(totals.items()):
            quota_tokens = t["miss"] + t["hit"] + t["out"]
            n_items = args.items if single else t["items"]
            note = f"runner={provider}" + ("" if t["has_usage"] else " usage=không ghi")
            conn.execute(
                """INSERT INTO token_ledger
                   (ts, wave, batch_id, agent_id, n_items, n_sessions, miss_tokens, hit_tokens,
                    out_tokens, reasoning_tokens, quota_tokens, turns_max, ctx_peak, ctx_pct,
                    est_miss, est_out, billed_usd, peak_window, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 args.wave, args.batch, f"article-processor-{provider}", n_items,
                 t["batches"], t["miss"], t["hit"], t["out"], t["reasoning"], quota_tokens,
                 1, 0, 0.0, args.est_miss if single else None,
                 args.est_out if single else None, round(t["usd"], 6), 0, note),
            )
            print(f"✅ Đã ghi sổ cái ({provider}): wave={args.wave or '-'} "
                  f"({t['batches']} lô, {n_items} bài)")
            print(f"   quota {quota_tokens:,} token (miss {t['miss']:,} · hit {t['hit']:,} · "
                  f"out {t['out']:,} · ~${t['usd']:.4f})"
                  + ("" if t["has_usage"] else " · provider không ghi usage"))
        conn.commit()
        conn.close()
        return 0

    wave = wave_usage(since, cwd_filter=args.cwd_filter, with_reasoning=not args.no_reasoning,
                      workers_only=workers_only)

    if not wave.sessions:
        print(f"⚠️  Không có phiên DSH nào {'worker tạo' if workers_only else 'sửa đổi'} "
              f"sau mốc đã cho ({datetime.fromtimestamp(since):%Y-%m-%d %H:%M:%S}). "
              f"Không ghi gì.")
        return 2
    if workers_only:
        dropped = len(wave_usage(since, cwd_filter=args.cwd_filter,
                                 with_reasoning=False).sessions) - len(wave.sessions)
        if dropped:
            print(f"   bỏ {dropped} phiên không phải worker của đợt (điều phối, phiên mở "
                  f"từ trước); chúng không tính vào token mỗi bài")
        if not args.note:
            args.note = "workers-only"

    pricing = load_pricing()
    peak = args.peak if args.peak is not None else is_peak(pricing=pricing)
    usd = wave.usd(peak=peak, pricing=pricing)
    ctx_peak = max((s.pressure_tokens for s in wave.sessions), default=0)
    ctx_pct = max((s.pressure_ratio for s in wave.sessions), default=0.0)
    turns_max = max((s.turns for s in wave.sessions), default=0)

    conn = connect(args.db)
    conn.execute(
        """INSERT INTO token_ledger
           (ts, wave, batch_id, agent_id, n_items, n_sessions, miss_tokens, hit_tokens,
            out_tokens, reasoning_tokens, quota_tokens, turns_max, ctx_peak, ctx_pct,
            est_miss, est_out, billed_usd, peak_window, note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),
         args.wave, args.batch, args.agent, args.items, len(wave.sessions),
         wave.uncached_input, wave.cache_read, wave.output,
         wave.reasoning_tokens if wave.reasoning_known else None,
         wave.quota_tokens, turns_max, ctx_peak, round(ctx_pct, 4),
         args.est_miss, args.est_out, round(usd, 6), int(peak), args.note),
    )
    conn.commit()
    conn.close()

    per_item = wave.quota_tokens / args.items if args.items else 0
    print(f"✅ Đã ghi sổ cái: wave={args.wave or '-'} batch={args.batch or '-'} "
          f"({len(wave.sessions)} phiên, {args.items} bài)")
    print(f"   quota {wave.quota_tokens:,} token "
          f"(miss {wave.uncached_input:,} · hit {wave.cache_read:,} · out {wave.output:,})")
    if wave.reasoning_known:
        flag = "" if wave.reasoning_tokens == 0 else "  ⚠️ effort chưa tắt?"
        print(f"   reasoning {wave.reasoning_tokens:,} token{flag}")
    else:
        print("   reasoning: không đọc được nhật ký JSONL (không chặn, số khác vẫn đúng)")
    if args.items:
        print(f"   {per_item:,.0f} token/bài · ${usd:.4f} ({'peak' if peak else 'off-peak'})")
    if turns_max > 1:
        print(f"   ⚠️ turns_max={turns_max}: có phiên chạy quá 1 bước, soi lại persona worker")

    pfx = args.prefix_tokens or cached_prefix_tokens()
    # In workers-only mode every remaining session is a worker call, so the session
    # count is the call count when the wave descriptor is absent.
    calls = (args.worker_calls or worker_calls(args.wave)
             or (len(wave.sessions) if workers_only else None))
    expected_hit, shortfall = cache_shortfall(wave.cache_read, len(wave.sessions), pfx,
                                              calls=calls)
    basis = (f"{calls} luot goi worker theo mo ta dot" if calls
             else f"{len(wave.sessions)} phien, tru phien dieu phoi")
    if expected_hit:
        table = pricing["models"]["deepseek-flash"]["peak" if peak else "off_peak"]
        gap_usd = shortfall * (table["input_cache_miss"] - table["input_cache_hit"]) / 1e6
        if shortfall:
            print(f"   ⚠️ bộ nhớ đệm TRƯỢT: hit {wave.cache_read:,} token, sàn tối thiểu "
                  f"{expected_hit:,} (tiền tố {pfx:,} × số lượt sau lượt đầu; "
                  f"cơ sở: {basis}) — hụt {shortfall:,} token ≈ ${gap_usd:.4f}")
            print(f"      Kiểm theo thứ tự: (1) `build_article_prefix.py --check` — "
                  f"persona trong preset có còn khớp prefix từng byte không; (2) trong "
                  f"đợt có đổi tool set, model hay reasoningEffort không; (3) phiên nào "
                  f"chạm ngưỡng nén 80% thì vùng surface đã bị viết lại.")
        else:
            print(f"   ✅ bộ nhớ đệm trúng: hit {wave.cache_read:,} token so với sàn "
                  f"{expected_hit:,}")
    # Tokens per article are only recorded and printed for the user to judge; no
    # threshold applies to them per article, batch or wave.
    return 0


def _fmt_row(r: sqlite3.Row) -> str:
    """Format one ledger row as a display string.

    Args:
        r: Row read from the ledger table.

    Returns:
        Single-line string with aligned columns.
    """
    per = (r["quota_tokens"] / r["n_items"]) if r["n_items"] else 0
    reasoning = "—" if r["reasoning_tokens"] is None else f"{r['reasoning_tokens']:,}"
    return (f"{r['ts'][:19]:20} {str(r['wave'] or '-'):>6} {r['n_items']:>6} "
            f"{r['miss_tokens']:>10,} {r['hit_tokens']:>12,} {r['out_tokens']:>9,} "
            f"{reasoning:>9} {per:>9,.0f} {r['turns_max']:>5} ${r['billed_usd']:>8.4f}")


def cmd_report(args: argparse.Namespace) -> int:
    """Print the ledger report filtered by wave or by day.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0.
    """
    conn = connect(args.db)
    sql = "SELECT * FROM token_ledger"
    params: list = []
    where = []
    if args.wave:
        where.append("wave = ?")
        params.append(args.wave)
    if args.date:
        where.append("substr(ts,1,10) = ?")
        params.append(args.date)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(args.limit)
    rows = list(conn.execute(sql, params))
    conn.close()

    print("=" * 110)
    print(" 🪙  SỔ CÁI TOKEN — SỐ THẬT TỪ RUNTIME DSH")
    print("=" * 110)
    if not rows:
        print("Chưa có dòng nào. Chạy `token_ledger.py append` sau một wave để ghi.")
        print("=" * 110)
        return 0

    print(f"{'thời điểm':20} {'wave':>6} {'bài':>6} {'miss':>10} {'hit':>12} "
          f"{'out':>9} {'reason':>9} {'tok/bài':>9} {'lượt':>5} {'USD':>9}")
    print("-" * 110)
    for r in rows:
        print(_fmt_row(r))

    # Totals use the latest snapshot of each wave. The table above prints every row
    # because the operator needs the ledger as recorded, but the totals must not count
    # a wave more than once.
    unique = latest_snapshots(list(reversed(rows)))
    tot_items = sum(r["n_items"] for r in unique)
    tot_quota = sum(r["quota_tokens"] for r in unique)
    tot_usd = sum(r["billed_usd"] for r in unique)
    tot_miss = sum(r["miss_tokens"] for r in unique)
    tot_hit = sum(r["hit_tokens"] for r in unique)
    print("-" * 110)
    dropped = len(rows) - len(unique)
    note = f" (bỏ {dropped} ảnh chụp cũ của cùng đợt)" if dropped else ""
    print(f"CỘNG {len(unique)} đợt{note} · {tot_items:,} bài · "
          f"quota {tot_quota:,} token · ${tot_usd:.4f}")
    if tot_items:
        print(f"Trung bình {tot_quota / tot_items:,.0f} token/bài")
    if tot_miss + tot_hit:
        print(f"Tỷ lệ trúng cache {tot_hit / (tot_miss + tot_hit):.1%}")
    print("=" * 110)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Check the six accounting rules against real session data.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code 0 when every checkable rule passes, 1 when a rule fails.
    """
    from src.telemetry.dsh_usage import find_session_log, iter_sessions, message_usage

    sessions = iter_sessions(args.cwd_filter)
    if not sessions:
        print("Không có phiên nào để đối soát.")
        return 0

    s = sessions[0]
    log = find_session_log(s.session_id)
    rows = message_usage(log) if log else []

    print("=" * 78)
    print(f" 🔍  ĐỐI SOÁT LUẬT KẾ TOÁN — phiên {s.session_id[:36]}")
    print("=" * 78)
    ok = True

    print(f"L1 · inputTokens là phần CHƯA cache, không phải kích thước prompt")
    print(f"     uncached {s.uncached_input:,} so với hit {s.cache_read:,} "
          f"(nếu đọc nhầm sẽ hụt ~{(s.cache_read / max(s.uncached_input, 1)):.0f} lần)")

    if rows:
        bad = [r for r in rows
               if r["input_tokens"] + r["cache_read_tokens"] + r["output_tokens"]
               != r["total_tokens"]]
        status = "ĐẠT" if not bad else f"SAI ở {len(bad)}/{len(rows)} dòng"
        ok = ok and not bad
        print(f"L2 · in + hit + out == total cho từng request: {status}")

        sub = [r for r in rows if r["reasoning_tokens"] > r["output_tokens"]]
        ok = ok and not sub
        print(f"L3 · reasoning là tập con của output: "
              f"{'ĐẠT' if not sub else f'SAI ở {len(sub)} dòng'}")
    else:
        print("L2 · bỏ qua: không giải nén được nhật ký JSONL")
        print("L3 · bỏ qua: không giải nén được nhật ký JSONL")

    print(f"L4 · cacheWrite luôn 0 với adapter DeepSeek: "
          f"{'ĐẠT' if s.cache_write == 0 else f'SAI ({s.cache_write:,})'}")
    ok = ok and s.cache_write == 0

    print("L5 · DSH không lưu giá; tiền tính từ config/token_pricing.yaml: ĐẠT theo thiết kế")
    print(f"L6 · surface {s.surface_tokens:,} <= pressure {s.pressure_tokens:,} "
          f"(surface không gồm tools, pressure không gồm output)")
    print("=" * 78)
    print("KẾT LUẬN:", "mọi luật kiểm được đều ĐẠT" if ok else "CÓ LUẬT SAI, xem ở trên")
    return 0 if ok else 1


def main(argv=None) -> int:
    """Run the command-line interface of the token ledger.

    Args:
        argv: Command-line arguments; defaults to `sys.argv`.

    Returns:
        Exit code of the selected subcommand.
    """
    ap = argparse.ArgumentParser(description="Sổ cái token đọc số thật từ runtime DSH")
    ap.add_argument("--db", default=HARNESS_DB, help="Đường dẫn harness.db")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Tạo bảng token_ledger")

    a = sub.add_parser("append", help="Gộp phiên mới thành một dòng sổ cái")
    a.add_argument("--wave", help="Mã đợt xử lý")
    a.add_argument("--batch", help="Mã lô")
    a.add_argument("--agent", default="article-processor", help="Mã tác nhân")
    a.add_argument("--items", type=int, default=0, help="Số bài đã xử lý trong đợt")
    a.add_argument("--since", type=float, help="Mốc epoch bắt đầu tính")
    a.add_argument("--window-min", type=int, default=30,
                   help="Nếu không có --since thì lấy ngược lại bấy nhiêu phút")
    a.add_argument("--cwd-filter", default="news-scape", help="Lọc phiên theo thư mục làm việc")
    a.add_argument("--est-miss", type=int, help="Dự toán token miss để đo sai số")
    a.add_argument("--est-out", type=int, help="Dự toán token out để đo sai số")
    a.add_argument("--peak", type=int, choices=[0, 1], help="Ép khung giá, bỏ trống thì tự suy")
    a.add_argument("--no-reasoning", action="store_true",
                   help="Bỏ qua việc giải nén JSONL để lấy reasoning")
    a.add_argument("--worker-calls", type=int,
                   help="Số lượt gọi worker của đợt. Bỏ trống thì đọc từ mô tả đợt, "
                        "không có mô tả thì suy thô từ số phiên")
    a.add_argument("--prefix-tokens", type=int,
                   help="Kích thước tiền tố tĩnh dùng để đối chiếu cache. Bỏ trống "
                        "thì lấy từ tệp mô tả prefix")
    a.add_argument("--note", help="Ghi chú tự do")
    a.add_argument("--workers-only", action="store_true",
                   help="Chỉ gộp phiên worker được tạo sau --since; bỏ phiên điều phối "
                        "và mọi phiên mở từ trước còn đang hoạt động")
    a.add_argument("--source", choices=["dsh", *RUNNER_SOURCES],
                     help="Nguồn runtime: dsh (phiên DSH), hoặc agy/openrouter/opencode-native/auto "
                          "(đọc usage từ meta; auto lấy provider ghi trong từng tệp)")

    r = sub.add_parser("report", help="In báo cáo sổ cái")
    r.add_argument("--wave", help="Lọc theo đợt")
    r.add_argument("--date", help="Lọc theo ngày YYYY-MM-DD")
    r.add_argument("--limit", type=int, default=30, help="Số dòng tối đa")

    v = sub.add_parser("verify", help="Đối soát sáu luật kế toán")
    v.add_argument("--cwd-filter", default="news-scape", help="Lọc phiên theo thư mục làm việc")

    args = ap.parse_args(argv)
    if args.cmd == "append" and args.peak is not None:
        args.peak = bool(args.peak)
    return {"init": cmd_init, "append": cmd_append,
            "report": cmd_report, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
