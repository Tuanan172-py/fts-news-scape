"""Provide CLI subcommands that report the operating state of News-Scape."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Force UTF-8 output on the Windows console.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.token_ledger import (                         # noqa: E402
    latest_snapshots,
    worker_calls,
)
from src.agent.prefix import cached_prefix_tokens          # noqa: E402
from src.core import paths                                 # noqa: E402
from src.core.user_manifest import load_user_manifest      # noqa: E402
from src.db.preflight import probe_write, resolve_db_path  # noqa: E402
from src.telemetry.dsh_usage import (                      # noqa: E402
    billed_usd,
    is_peak,
    iter_sessions,
    load_pricing,
)
from src.db.connect import open_ro  # noqa: E402

ARTICLE_TASK_DIR = paths.article_packets_dir()
USER_OUTPUT_DIR = paths.users_output_dir()
HARNESS_DB = paths.harness_db_path()
PY = '& "C:\\venvs\\news-scape\\Scripts\\python.exe"'


def get_db_connection() -> sqlite3.Connection:
    """Open a read-only connection to the database that the ingest step writes to.

    Returns:
        SQLite connection opened with `mode=ro`.
    """
    return open_ro(resolve_db_path())


def _local_naive(ts: str) -> datetime:
    """Convert an ISO string, with or without a time zone, to naive local time.

    Args:
        ts: ISO timestamp string.

    Returns:
        Timestamp in machine-local time without tzinfo.
    """
    clean = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean)
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def latest_wave() -> dict | None:
    """Read the manifest of the most recently packed Article Lane wave.

    Returns:
        Content of the newest `wave_<id>.json` file, or None if no wave exists.
    """
    best = None
    for p in ARTICLE_TASK_DIR.glob("wave_*.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if m.get("wave") and (best is None
                              or m.get("created_epoch", 0) > best.get("created_epoch", 0)):
            best = m
    return best


def wave_state(conn: sqlite3.Connection, manifest: dict) -> dict:
    """Determine the lifecycle phase of a wave and its next command.

    The four phases, in lifecycle order: batches without output (run the
    conductor), articles sent but with no record received (repair), records
    complete but database coverage insufficient (finish), and done.

    Args:
        conn: Read-only SQLite connection.
        manifest: Wave manifest produced by the packing step.

    Returns:
        Dict of wave metrics with the keys `phase` and `next` (next command, empty when done).
    """
    from scripts import article_run as ar

    wave = manifest["wave"]
    have, missing = ar.pending_batches(wave)
    ids = ar.wave_article_ids(wave)
    n = len(ids)
    received = ar.wave_received_ids(wave) if have else set()
    cov = ar.coverage_of(conn, ids) if ids else {"l1_ok": set(), "gold_ok": set()}
    st = {"wave": wave, "n": n, "batches": len(have) + len(missing),
          "have": len(have), "missing": missing, "received": len(received),
          "l1_ok": len(cov["l1_ok"]), "gold_ok": len(cov["gold_ok"]),
          "created_at": manifest.get("created_at", "?")}

    finish = f"{PY} scripts/article_run.py --wave {wave} --finish"
    if missing:
        kind = "repair" if all("_r" in b[len(f"article_{wave}_"):] for b in missing) else "conductor"
        st["phase"] = f"{len(missing)} lô chưa có đầu ra mô hình"
        st["next"] = (f"Chạy trọn data/agent_tasks/article/wave_{wave}.{kind}.ts trong MỘT "
                      f"lệnh run_code (preset news-scape-conductor), rồi: {finish}")
    elif n and len(received) < n:
        st["phase"] = f"{n - len(received)} bài đã gửi mà chưa nhận được bản ghi"
        st["next"] = f"{PY} scripts/article_run.py --wave {wave} --repair"
    elif n and min(st["l1_ok"], st["gold_ok"]) / n < ar.MIN_COVERAGE:
        st["phase"] = "đủ bản ghi nhưng cơ sở dữ liệu chưa đủ"
        st["next"] = finish
    else:
        st["phase"] = "đã xong"
        st["next"] = ""
    return st


def ops_summary() -> dict | None:
    """Read the control-plane state from `ops.db` without breaking the radar when it is absent.

    Returns:
        Dict of daemon state, or None if `ops.db` does not exist or cannot be read.
    """
    try:
        from src.ops.breakers import Breakers
        from src.core.ops_config import load_config, resolve_paths
        from src.ops.order import load_order
        from src.ops.reports import heartbeat_age_s
        from src.ops.store import OpsStore

        paths = resolve_paths()
        if not paths.ops_db.exists():
            return None
        store = OpsStore(paths.ops_db)
        cfg = load_config()
        age = heartbeat_age_s(store)
        with store.conn() as c:
            unsent = c.execute("SELECT COUNT(*) FROM ops_alerts WHERE sent_at IS NULL"
                               ).fetchone()[0]
        return {"alive": age is not None and age < 180, "age": age,
                "level": load_order(paths.standing_order).effective_level(),
                "paused": store.get_state("paused") == "1",
                "active": store.active_wave(),
                "open_breakers": [b for b in Breakers(store, cfg["breaker"]).all()
                                  if b.state != "CLOSED"],
                "unsent": unsent}
    except Exception:  # noqa: BLE001 — the radar must survive an operations-layer failure
        return None


def cmd_status(args: argparse.Namespace) -> None:
    """Report the current state of the Article Lane and recommend the next command.

    The Article Lane is the only processing path. The radar neither reads nor
    recommends anything from the retired L1/Gold lane (`l1_tasks`, the
    `work_items` queue, `agent_tasks/l1` packets), because such recommendations
    would send the orchestrator down the wrong path.

    Args:
        args: Parsed command-line arguments; uses `date`.
    """
    from scripts.article_pack import ANALYZED_L1, is_thin_row, load_candidates

    target_date = args.date or f"{datetime.now():%Y-%m-%d}"
    print("=" * 80)
    print(f" 🛰️  NEWS-SCAPE PIPELINE RADAR — ARTICLE LANE — [{target_date}]")
    print("=" * 80)

    probe = probe_write()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT max(last_run_ts) FROM scraper_heartbeat WHERE scraper_name NOT LIKE '%-%'")
    ref_ts_str = (cur.fetchone() or [None])[0]
    if not ref_ts_str:
        cur.execute("SELECT max(fetched_at) FROM articles")
        ref_ts_str = (cur.fetchone() or [None])[0]
    scrape_delay_minutes = None
    if ref_ts_str:
        try:
            scrape_delay_minutes = max(0, int(
                (datetime.now() - _local_naive(ref_ts_str)).total_seconds() / 60))
        except ValueError:
            pass

    cur.execute("SELECT count(*) FROM articles WHERE substr(published_at,1,10) = ?",
                (target_date,))
    crawled_count = cur.fetchone()[0]

    # Coverage by PUBLISH DATE, using the same definition as `handoff.py`.
    # Code-first rows do not count as analyzed.
    covered = {}
    for table, cond in (("l1_outputs", ANALYZED_L1), ("agent_outputs", "o.dod_pass = 1")):
        cur.execute(f"""
            SELECT count(distinct o.article_id) FROM {table} o
            JOIN articles a ON a.url_title_hash = o.article_id
            WHERE substr(a.published_at,1,10) = ? AND {cond}
        """, (target_date,))
        covered[table] = cur.fetchone()[0]

    # Same query as the packing step, so the "pending analysis" count equals the
    # number of articles `article_run.py --date` will pick. Thin articles (fewer
    # than two paragraphs of citation length) are dropped by the packer and are
    # counted separately, not as pending.
    _candidates = load_candidates(conn, date=target_date, limit=1_000_000,
                                  only_pending=True, exclude_thin=False)
    _thin = [r for r in _candidates if is_thin_row(r)]
    pending_today = len(_candidates) - len(_thin)
    thin_today = len(_thin)

    source_deleted = "(metadata_json LIKE '%\"source_deleted\": true%' " \
                     "OR metadata_json LIKE '%\"source_deleted\":true%')"
    cur.execute(f"SELECT count(1) FROM articles WHERE substr(published_at,1,10) = ? "
                f"AND {source_deleted}", (target_date,))
    source_deleted_count = cur.fetchone()[0]
    # Deleted articles are usually DETECTED later than the publish date, so include the cumulative total.
    cur.execute(f"SELECT count(1) FROM articles WHERE {source_deleted}")
    source_deleted_total = cur.fetchone()[0]

    # Failure ledger of the Bronze->Silver derive (ADR 0007). Dead-letter content
    # never reaches analysis or users.
    try:
        cur.execute("""
            SELECT sum(CASE WHEN dead_letter=0 THEN 1 ELSE 0 END),
                   sum(CASE WHEN dead_letter=1 THEN 1 ELSE 0 END)
            FROM silver_failures
        """)
        _r = cur.fetchone()
        silver_blocking, silver_dead = int(_r[0] or 0), int(_r[1] or 0)
    except sqlite3.OperationalError:
        silver_blocking = silver_dead = 0

    # Capture coverage (rule 10): articles reported by the independent sitemap versus the store.
    try:
        cur.execute("""
            SELECT source_domain, sum(ref_n), sum(missing_n)
            FROM capture_coverage WHERE day >= date(?, '-1 day') GROUP BY source_domain
            ORDER BY source_domain
        """, (target_date,))
        coverage = [(r[0], int(r[1] or 0), int(r[2] or 0)) for r in cur.fetchall()]
        cur.execute("SELECT count(1) FROM discovered_urls WHERE state='discovered'")
        capture_pending = int(cur.fetchone()[0])
        # Count only rows whose article is still stored: `recapture` re-scrapes by the
        # article URL, so orphan rows (article re-keyed or deleted) cannot be recovered
        # and are not actionable.
        cur.execute("SELECT count(1) FROM silver_failures f WHERE f.dead_letter=1 "
                    "AND f.last_error LIKE '%raw_missing%' AND EXISTS (SELECT 1 FROM "
                    "articles a WHERE a.url_title_hash = f.url_title_hash)")
        raw_lost = int(cur.fetchone()[0])
    except sqlite3.OperationalError:
        coverage, capture_pending, raw_lost = [], 0, 0

    # Duplicates by story cluster (ADR 0016) and the abnormal-attention signal of the latest session.
    try:
        cur.execute("""
            SELECT cm.role, count(1) FROM cluster_members cm
            JOIN articles a ON a.url_title_hash = cm.article_id
            WHERE substr(a.published_at,1,10) = ? GROUP BY cm.role
        """, (target_date,))
        dup_roles = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("""
            SELECT count(1) FROM l1_outputs o JOIN articles a ON a.url_title_hash = o.article_id
            WHERE o.l1_source = 'inherited' AND substr(a.published_at,1,10) = ?
        """, (target_date,))
        inherited_today = int(cur.fetchone()[0])
        cur.execute("""
            SELECT trade_date, entity_id, ama_z, n_articles, n_sources FROM signal_daily
            WHERE trade_date = (SELECT max(trade_date) FROM signal_daily)
              AND n_articles >= 3 AND n_sources >= 2 AND ama_z IS NOT NULL
            ORDER BY ama_z DESC LIMIT 3
        """)
        attention = cur.fetchall()
    except sqlite3.OperationalError:
        dup_roles, inherited_today, attention = {}, 0, []

    # A 404/410 spike concentrated in ONE domain is almost always a site that changed
    # its URL structure or selectors, not articles that were really removed.
    cur.execute(f"""
        SELECT source_domain, sum(CASE WHEN {source_deleted} THEN 1 ELSE 0 END), count(1)
        FROM articles WHERE substr(published_at,1,10) = ? GROUP BY source_domain
    """, (target_date,))
    deleted_by_domain = [(r[0], r[1], r[2]) for r in cur.fetchall() if r[1]]

    cur.execute("""
        SELECT max(o.created_at) FROM agent_outputs o
        JOIN articles a ON a.url_title_hash = o.article_id
        WHERE substr(a.published_at,1,10) = ? AND o.dod_pass = 1
    """, (target_date,))
    last_gold_ts = cur.fetchone()[0]

    manifest = latest_wave()
    wave = wave_state(conn, manifest) if manifest else None
    conn.close()

    pct = (100.0 * covered["l1_outputs"] / crawled_count) if crawled_count else 0.0
    print("1. DỮ LIỆU TẠI KHO")
    print(f"   • Bài đăng trong ngày            : {crawled_count:,}")
    print(f"   • Đã phân tích (mô hình, đạt)    : {covered['l1_outputs']:,}/{crawled_count:,} "
          f"({pct:.1f}%) · nội dung đạt {covered['agent_outputs']:,}")
    print(f"   • Chờ phân tích                  : {pending_today:,} bài có gói Silver, "
          f"chưa được mô hình phân tích (bản code-first không tính)")
    if thin_today:
        print(f"   • Bài mỏng chờ Silver             : {thin_today:,} bài không đủ hai "
              f"đoạn đạt độ dài trích dẫn, packer loại khỏi đợt (không tốn token)")
    print(f"   • Bài bị nguồn xóa (404/410)     : {source_deleted_count:,} bài đăng hôm nay / "
          f"{source_deleted_total:,} tổng tích lũy")
    _silver_tag = "🟢" if not (silver_blocking or silver_dead) else (
        "🔴" if silver_dead else "🟡")
    print(f"   • Bronze kẹt ở Silver (ADR 0007) : {_silver_tag} {silver_blocking:,} đang chặn "
          f"watermark / {silver_dead:,} dead-letter")
    if coverage:
        red_cov = [(d, 100.0 * m / r) for d, r, m in coverage if r and 100.0 * m / r > 2.0]
        cov_tag = "🔴" if red_cov else "🟢"
        worst = ", ".join(f"{d.split('.')[0]} thiếu {p:.0f}%" for d, p in
                          sorted(red_cov, key=lambda x: -x[1])[:4]) or "đủ trong ngưỡng 2%"
        print(f"   • Độ phủ thu thập (2 ngày)       : {cov_tag} {worst} · chờ cào bù "
              f"{capture_pending:,}")
    else:
        print("   • Độ phủ thu thập                : ⚪ chưa đối chiếu sitemap "
              "(scripts/capture_reconcile.py reconcile)")
    if dup_roles:
        print(f"   • Trùng lặp trong ngày           : {dup_roles.get('copy', 0):,} bài chép "
              f"(đã kế thừa {inherited_today:,}) · {dup_roles.get('candidate', 0):,} bài cùng sự kiện")
    if attention:
        top = ", ".join(f"{r[1].split(':')[-1]} z={r[2]:.0f} ({r[3]} bài/{r[4]} nguồn)"
                        for r in attention)
        print(f"   • Chú ý bất thường (phiên {attention[0][0]}): {top}")
    if scrape_delay_minutes is not None:
        delay_str = (f"{scrape_delay_minutes} phút" if scrape_delay_minutes < 60
                     else f"{scrape_delay_minutes // 60}h {scrape_delay_minutes % 60}m")
        freshness_tag = ("🟢 Tươi mới" if scrape_delay_minutes <= 30 else
                         "🟡 Chậm nhẹ" if scrape_delay_minutes <= 120 else
                         "🔴 Gián đoạn / Khoảng trống đêm")
        print(f"   • Độ tươi cào tin                : {freshness_tag} (cách đây {delay_str})")
    print(f"   • Cơ sở dữ liệu                  : {'✅' if probe.ok else '❌'} {probe.reason} "
          f"— {probe.path}")
    print()

    print("2. ĐỢT ARTICLE LANE GẦN NHẤT")
    if wave:
        n = wave["n"] or 1
        print(f"   • Mã đợt      : {wave['wave']} (đóng gói {wave['created_at']}) · "
              f"{wave['n']:,} bài · {wave['batches']} lô gồm cả lô vá")
        print(f"   • Đầu ra      : {wave['have']}/{wave['batches']} lô · nhận "
              f"{wave['received']:,}/{wave['n']:,} bài")
        print(f"   • Vào DB      : nhận diện {wave['l1_ok']:,} ({wave['l1_ok'] / n:.1%}) · "
              f"nội dung {wave['gold_ok']:,} ({wave['gold_ok'] / n:.1%})")
        print(f"   • Trạng thái  : {wave['phase']}")
    else:
        print("   • Chưa có đợt nào được đóng gói.")
    print()

    ops = ops_summary()
    print("3. VẬN HÀNH TỰ CHỦ (ops_daemon, ADR 0012)")
    if ops is None:
        print("   • Chưa cài: python scripts/ops_daemon.py once · scripts/ops_install.ps1")
    else:
        alive = ("🟢 sống" if ops["alive"] else
                 (f"🔴 im lặng {ops['age'] / 60:.0f} phút" if ops["age"] is not None
                  else "⚪ chưa chạy"))
        print(f"   • Daemon      : {alive} · mức {ops['level']}"
              f"{' · TẠM DỪNG' if ops['paused'] else ''}")
        if ops["active"]:
            a = ops["active"]
            print(f"   • Đợt tự động : {a['wave_id']} · {a['status']}/{a['step']}")
        for b in ops["open_breakers"]:
            print(f"   • Breaker     : {b.provider} {b.state} ({b.reason}) mở lại "
                  f"{b.reopen_at or 'khi reset'}")
        print(f"   • Cảnh báo    : {ops['unsent']} chưa gửi · bảng điều khiển: "
              f"python scripts/ops_console.py")
    print()

    print("4. ĐIỂM CHẠM & LỆNH KẾ TIẾP")
    recs: list[tuple[str, str, str]] = []
    daemon_owns_waves = bool(ops and ops["alive"] and ops["level"] != "L0"
                             and not ops["paused"])
    if ops is not None and not ops["alive"]:
        recs.append(("HIGH", "ops_daemon không chạy: không ai tự mở đợt hay báo sự cố.",
                     "schtasks /Run /TN news-scape-ops"))

    if not probe.ok:
        recs.append(("MEDIUM", f"Phiên này không ghi được DB ({probe.reason}). Chuẩn bị đợt "
                               f"và chạy mô hình vẫn làm được; `--finish` và giao hàng phải "
                               f"chạy với danger-full-access.",
                     f"{PY} scripts/article_run.py --where"))

    if scrape_delay_minutes is not None and scrape_delay_minutes > 120:
        recs.append(("HIGH", f"Khoảng trống cào tin {scrape_delay_minutes // 60}h (máy sleep "
                             f"hoặc scheduler dừng). Cào vét bù ngay.",
                     f"{PY} scripts/run_once.py"))
    elif scrape_delay_minutes is not None and scrape_delay_minutes > 45:
        recs.append(("MEDIUM", f"Cào tin chậm ({scrape_delay_minutes} phút chưa có nhịp mới).",
                     f"{PY} scripts/run_once.py"))

    if coverage:
        red_cov = [(d, 100.0 * m / r) for d, r, m in coverage if r and 100.0 * m / r > 2.0]
        if red_cov:
            recs.append(("HIGH", f"Thu thập thiếu so với sitemap ở {len(red_cov)} nguồn "
                                 f"(vượt ngưỡng 2%); {capture_pending:,} URL chờ cào bù.",
                         f"{PY} scripts/capture_reconcile.py run --limit 100 --budget 600"))

    if silver_dead and raw_lost:
        recs.append(("HIGH", f"{raw_lost} bài còn trong kho nhưng đã mất tệp Bronze (raw_missing). "
                             f"Cào lại theo URL để phục hồi raw.",
                     f"{PY} scripts/capture_reconcile.py recapture --limit 100 --budget 600"))
    elif silver_dead:
        recs.append(("HIGH", f"{silver_dead} tệp Bronze DEAD-LETTER ở Silver: nội dung không "
                             f"bao giờ tới được bước phân tích. Đây là mất dữ liệu thật.",
                     "SELECT meta_path, attempts, last_error FROM silver_failures "
                     "WHERE dead_letter=1; — sửa gốc rồi xoá hàng đó để derive thử lại"))
    elif silver_blocking:
        recs.append(("MEDIUM", f"{silver_blocking} tệp Bronze đang chặn watermark Silver.",
                     "SELECT meta_path, attempts, last_error FROM silver_failures "
                     "WHERE dead_letter=0;"))

    for dom, deleted, total in deleted_by_domain:
        if deleted > 10 and total and (deleted / total) > 0.3:
            recs.append(("HIGH", f"Domain {dom}: {deleted}/{total} bài trả 404/410 — nghi site "
                                 f"đổi cấu trúc URL/selector, không phải tin bị gỡ thật.",
                         f"{PY} scripts/validate_capture.py {dom.split('.')[0]}"))

    # One wave at a time: do not open a new wave while the latest one is unfinished.
    wave_open = bool(wave and wave["next"])
    if daemon_owns_waves and (wave_open or pending_today):
        recs.append(("INFO", f"ops_daemon ({ops['level']}) đang giữ việc mở và chạy đợt; "
                             f"không mở đợt tay song song.",
                     f"{PY} scripts/ops_daemon.py status"))
    elif wave_open:
        recs.append(("HIGH", f"Đợt {wave['wave']}: {wave['phase']}.", wave["next"]))
    elif pending_today:
        new_wave = f"W{datetime.now():%m%d%H%M}"
        # Do not pass `--batch`: `article_pack` picks the batch size from the real article
        # count so the wave fits one parallel round. A hard-coded value here would override it.
        recs.append(("HIGH", f"{pending_today:,} bài đăng ngày {target_date} chờ phân tích.",
                     f"{PY} scripts/article_run.py --wave {new_wave} --date {target_date} "
                     f"--limit {pending_today}"))

    if not wave_open and covered["agent_outputs"]:
        files = list(USER_OUTPUT_DIR.glob(f"*/{target_date}.xlsx"))
        newest = max((f.stat().st_mtime for f in files), default=0.0)
        stale = False
        if files and last_gold_ts:
            try:
                stale = _local_naive(last_gold_ts).timestamp() > newest
            except ValueError:
                pass
        if not files or stale:
            why = ("chưa xuất tệp giao hàng" if not files
                   else "tệp giao hàng cũ hơn kết quả phân tích mới nhất")
            recs.append(("HIGH", f"Đã có bài phân tích ngày {target_date} nhưng {why}.",
                         f"{PY} scripts/write_user_output.py --date {target_date}"))

    if not recs:
        recs.append(("INFO", "Ngày này đã xử lý và giao hàng xong.", "Không cần thao tác thêm."))

    for priority, desc, cmd in recs:
        icon = "🔴" if priority == "HIGH" else ("🟡" if priority == "MEDIUM" else "🟢")
        print(f"   {icon} [{priority}] {desc}")
        print(f"      👉 {cmd}")
    print()
    print("   Mọi lệnh chạy với cwd = project/. Đường xử lý duy nhất là Article Lane")
    print("   (article_run.py). Không dùng l1_route, l1_ingest --code-first, requeue hay")
    print("   agent_l1/agent_gold: lane L1/Gold cũ đã ngừng.")
    print("=" * 80 + "\n")


def _utc_window(date: str) -> tuple[str, str]:
    """Convert a machine-local date into a UTC range for ledger queries.

    Args:
        date: Local date as `YYYY-MM-DD`.

    Returns:
        Pair of start and end ISO UTC timestamps, formatted like the ledger `ts` column.
    """
    start = datetime.strptime(date, "%Y-%m-%d").astimezone()
    end = start + timedelta(days=1)
    fmt = lambda d: d.astimezone(timezone.utc).isoformat(timespec="seconds")
    return fmt(start), fmt(end)


def _ledger_rows(date: str | None, wave: str | None) -> list[sqlite3.Row]:
    """Read token ledger rows by date or by wave.

    Args:
        date: Local date filter as `YYYY-MM-DD`, ignored when a wave is given.
        wave: Wave id filter.

    Returns:
        Ledger rows, empty when the ledger is missing or nothing matches.
    """
    if not HARNESS_DB.exists():
        return []
    conn = open_ro(HARNESS_DB)
    conn.row_factory = sqlite3.Row
    try:
        if wave:
            sql, params = "SELECT * FROM token_ledger WHERE wave = ?", (wave,)
        else:
            # The ledger stores UTC timestamps while operators think in local dates.
            # Comparing `substr(ts,1,10)` with the local date is off by seven hours:
            # waves run before 07:00 Vietnam time fall on the previous UTC day. Convert
            # the local date to a UTC range before comparing.
            lo, hi = _utc_window(date)
            sql, params = ("SELECT * FROM token_ledger WHERE ts >= ? AND ts < ?",
                           (lo, hi))
        rows = list(conn.execute(sql + " ORDER BY id", params))
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    # The ledger stores cumulative snapshots per wave, so deduplicate before summing.
    # Shares the definition in `token_ledger.py` so both tools report the same figures
    # for a wave.
    return latest_snapshots(rows)


def cmd_token(args: argparse.Namespace) -> None:
    """Report the measured token usage and cost of the article processing path.

    All figures come from two measured sources: the `token_ledger` for closed
    waves and the DSH session checkpoints for the running part. No fixed
    per-article quota is used. Cache-hit tokens are priced separately from
    cache-miss and output tokens.

    Args:
        args: Parsed command-line arguments; uses `date` and optionally `wave`.

    Returns:
        None. The report is printed to stdout.
    """
    target_date = args.date or f"{datetime.now():%Y-%m-%d}"
    wave = getattr(args, "wave", None)
    scope = f"đợt {wave}" if wave else f"ngày {target_date}"
    pricing = load_pricing()

    print("=" * 96)
    print(f" 🪙  TOKEN & CHI PHÍ THẬT — {scope}")
    print("=" * 96)
    print("Thước đo: `quota` đếm cả token trúng cache; `USD` là tiền thật theo ba rổ "
          "rời rạc. Hai thước lệch nhau rất xa và không thay thế được nhau.")
    print()

    rows = _ledger_rows(target_date, wave)
    if rows:
        print("1. ĐỢT ĐÃ CHỐT SỔ")
        print("-" * 96)
        print(f"{'thời điểm':17} {'đợt':>6} {'bài':>5} {'miss':>10} {'hit':>11} "
              f"{'out':>9} {'quota':>11} {'lượt':>5} {'USD':>9}")
        for r in rows:
            print(f"{r['ts'][:16]:17} {str(r['wave'] or '-'):>6} {r['n_items']:>5} "
                  f"{r['miss_tokens']:>10,} {r['hit_tokens']:>11,} "
                  f"{r['out_tokens']:>9,} {r['quota_tokens']:>11,} "
                  f"{r['turns_max']:>5} ${r['billed_usd']:>8.4f}")

        miss = sum(r["miss_tokens"] for r in rows)
        hit = sum(r["hit_tokens"] for r in rows)
        out = sum(r["out_tokens"] for r in rows)
        items = sum(r["n_items"] for r in rows)
        usd = sum(r["billed_usd"] for r in rows)
        reasoning = sum(r["reasoning_tokens"] or 0 for r in rows)
        print("-" * 96)
        print(f"CỘNG {len(rows)} dòng · {items:,} bài · quota {miss + hit + out:,} "
              f"token · ${usd:.4f}")

        print()
        print("2. PHÂN RÃ HOÁ ĐƠN THEO RỔ")
        print("-" * 96)
        # Price each row by its own pricing window. Using the window at report time
        # would double the cost of an off-peak wave viewed during peak hours.
        def _table(row) -> dict:
            window = "peak" if row["peak_window"] else "off_peak"
            return pricing["models"]["deepseek-flash"][window]

        cost = {"miss": 0.0, "hit": 0.0, "out": 0.0}
        for r in rows:
            t = _table(r)
            cost["miss"] += r["miss_tokens"] * t["input_cache_miss"] / 1e6
            cost["hit"] += r["hit_tokens"] * t["input_cache_hit"] / 1e6
            cost["out"] += r["out_tokens"] * t["output"] / 1e6
        table = _table(rows[-1])
        buckets = (("đầu vào mới (miss)", miss, cost["miss"]),
                   ("đầu vào tái dùng (hit)", hit, cost["hit"]),
                   ("đầu ra", out, cost["out"]))
        total_cost = sum(cost.values())
        for label, tok, money in buckets:
            share = (money / total_cost * 100) if total_cost else 0.0
            print(f"   {label:26} {tok:>12,} token  ${money:>9.4f}  "
                  f"{share:>5.1f}% hoá đơn")
        if miss + hit:
            print(f"   {'tỷ lệ trúng cache':26} {hit / (miss + hit):>12.1%}")
        if reasoning:
            print(f"   ⚠️ reasoning {reasoning:,} token: suy luận chưa tắt cho worker")

        print()
        print("3. BỘ NHỚ ĐỆM CÓ THẬT SỰ TRÚNG KHÔNG")
        print("-" * 96)
        pfx = cached_prefix_tokens()
        # Count by worker CALLS read from the wave manifest. Counting sessions would
        # include the Conductor session, which uses a different persona, never reads
        # the worker prefix, and would inflate the expected cache floor.
        floor = 0
        for r in rows:
            calls = worker_calls(r["wave"]) or max(0, r["n_sessions"] - 1)
            floor += pfx * max(0, calls - 1)
        if floor:
            gap = max(0, floor - hit)
            verdict = "ĐẠT" if not gap else f"HỤT {gap:,} token"
            print(f"   tiền tố tĩnh {pfx:,} token · sàn tối thiểu {floor:,} · "
                  f"đo được {hit:,} → {verdict}")
            if gap:
                delta = gap * (table["input_cache_miss"]
                               - table["input_cache_hit"]) / 1e6
                print(f"   ≈ ${delta:.4f} trả thừa. Kiểm `build_article_prefix.py "
                      f"--check` trước; persona lệch prefix là nguyên nhân hay gặp nhất.")
        else:
            print("   chưa đủ hai lượt gọi để đối chiếu")

        est_miss = sum(r["est_miss"] or 0 for r in rows)
        est_out = sum(r["est_out"] or 0 for r in rows)
        if est_miss or est_out:
            print()
            print("4. SAI SỐ DỰ TOÁN")
            print("-" * 96)
            for label, est, act in (("đầu vào mới", est_miss, miss),
                                    ("đầu ra", est_out, out)):
                if not est:
                    continue
                print(f"   {label:14} dự toán {est:>10,} · thật {act:>10,} · "
                      f"lệch {(act - est) / est * 100:>+7.1f}%")

        if items:
            print()
            print(f"Mỗi bài: {(miss + hit + out) / items:,.0f} token quota · "
                  f"${usd / items:.6f}")
    else:
        print(f"Chưa có dòng sổ cái nào cho {scope}.")
        print("Sau mỗi đợt, `article_run.py --wave <mã> --finish` sẽ ghi sổ.")

    # When viewing a wave, the session date must be the wave's own date. Using today
    # would show "no session" for a wave run last week, which looks like data loss.
    session_date = target_date
    if wave and rows:
        try:
            session_date = (datetime.fromisoformat(rows[-1]["ts"])
                            .astimezone().strftime("%Y-%m-%d"))
        except (TypeError, ValueError):
            pass
    today = [s for s in iter_sessions("news-scape")
             if datetime.fromtimestamp(s.mtime).strftime("%Y-%m-%d") == session_date]
    print()
    print(f"5. PHIÊN DSH NGÀY {session_date} (gồm cả phần chưa chốt sổ)")
    print("-" * 96)
    if not today:
        print("   Không có phiên nào sửa đổi trong ngày.")
    else:
        print(f"   {'phiên':14} {'miss':>10} {'hit':>11} {'out':>9} {'lượt':>5} "
              f"{'áp suất':>8}")
        for s in today[:12]:
            print(f"   {s.session_id[:12]:14} {s.uncached_input:>10,} "
                  f"{s.cache_read:>11,} {s.output:>9,} {s.turns:>5} "
                  f"{s.pressure_ratio:>7.1%}")
        live_usd = sum(billed_usd(s.uncached_input, s.cache_read, s.output,
                                  pricing=pricing) for s in today)
        worst = max(today, key=lambda s: s.pressure_ratio)
        print(f"   {len(today)} phiên · ${live_usd:.4f} · áp suất cao nhất "
              f"{worst.pressure_ratio:.1%}")
        thresholds = pricing.get("watch_thresholds") or {}
        amber = float(thresholds.get("context_pressure_amber", 0.25))
        red = float(thresholds.get("context_pressure_red", 0.40))
        # Action advice applies to TODAY only. Printing it for a past date would
        # urge stopping a session that closed last week.
        live = session_date == datetime.now().strftime("%Y-%m-%d")
        if not live:
            print(f"   ⓘ  ngày đã qua — áp suất ở trên là số lịch sử, không phải "
                  f"trạng thái đang chạy")
        elif worst.pressure_ratio >= red:
            print("   🔴 vượt ngưỡng đỏ: dừng ngay sau lô hiện tại.")
        elif worst.pressure_ratio >= amber:
            print("   🟡 vượt ngưỡng vàng: xong đợt này thì đóng phiên, "
                  "không mở đợt mới.")
    print("=" * 96)
    print()


def cmd_backlog(args: argparse.Namespace) -> None:
    """Report the warehouse overview and the distribution of backlog articles.

    Args:
        args: Parsed command-line arguments; unused.
    """
    conn = get_db_connection()
    try:
        total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        gold_done = conn.execute(
            "SELECT COUNT(DISTINCT article_id) FROM agent_outputs WHERE dod_pass = 1"
        ).fetchone()[0]
        llm_l1 = conn.execute(
            "SELECT COUNT(DISTINCT article_id) FROM l1_outputs WHERE l1_source != 'code_first' AND dod_pass = 1"
        ).fetchone()[0]
        code_first_l1 = conn.execute(
            "SELECT COUNT(DISTINCT article_id) FROM l1_outputs WHERE l1_source = 'code_first'"
        ).fetchone()[0]

        has_clusters = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cluster_members'"
        ).fetchone()
        cluster_copies = (
            conn.execute("SELECT COUNT(*) FROM cluster_members WHERE role='copy'").fetchone()[0]
            if has_clusters else 0
        )

        gold_pending = total_articles - gold_done

        work_items_raw = conn.execute(
            "SELECT status, COUNT(*) FROM work_items GROUP BY status"
        ).fetchall()
        work_items = {r[0]: r[1] for r in work_items_raw}

        from scripts.article_pack import watchlist_universe, tier_of
        from src.agent.entities import load_registry

        reg = load_registry()
        watched, industries = watchlist_universe(reg)

        rows_pending = conn.execute("""
            SELECT a.title FROM articles a
            WHERE NOT EXISTS (
                SELECT 1 FROM agent_outputs g 
                WHERE g.article_id = a.url_title_hash AND g.dod_pass = 1
            )
        """).fetchall()

        tier1_cnt = 0
        tier2_cnt = 0
        for r in rows_pending:
            t, _ = tier_of(r[0], reg, watched, industries)
            if t == 1:
                tier1_cnt += 1
            else:
                tier2_cnt += 1

        sql_summary_period = """
        SELECT 
            CASE 
                WHEN a.published_at IS NULL OR a.published_at = '' THEN 'Khuyết ngày đăng'
                WHEN substr(a.published_at, 1, 10) >= '2026-10-09' THEN substr(a.published_at, 1, 10)
                WHEN substr(a.published_at, 1, 7) = '2026-10' THEN '2026-10 (01->08)'
                WHEN substr(a.published_at, 1, 7) = '2026-09' THEN '2026-09'
                WHEN substr(a.published_at, 1, 7) = '2026-08' THEN '2026-08'
                ELSE 'Lịch sử (< 2026-08)'
            END as period_group,
            COUNT(*) as total,
            SUM(CASE WHEN EXISTS (SELECT 1 FROM agent_outputs g WHERE g.article_id = a.url_title_hash AND g.dod_pass = 1) THEN 1 ELSE 0 END) as done,
            SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM agent_outputs g WHERE g.article_id = a.url_title_hash AND g.dod_pass = 1) THEN 1 ELSE 0 END) as pending
        FROM articles a
        GROUP BY period_group
        ORDER BY 
            CASE 
                WHEN period_group = 'Khuyết ngày đăng' THEN '0000-00-00'
                WHEN period_group LIKE 'Lịch sử%' THEN '0001-01-01'
                ELSE period_group
            END DESC
        """
        period_rows = conn.execute(sql_summary_period).fetchall()

        sql_domain = """
        SELECT 
            a.source_domain,
            COUNT(*) as total,
            SUM(CASE WHEN EXISTS (SELECT 1 FROM agent_outputs g WHERE g.article_id = a.url_title_hash AND g.dod_pass = 1) THEN 1 ELSE 0 END) as done,
            SUM(CASE WHEN NOT EXISTS (SELECT 1 FROM agent_outputs g WHERE g.article_id = a.url_title_hash AND g.dod_pass = 1) THEN 1 ELSE 0 END) as pending
        FROM articles a
        GROUP BY a.source_domain
        ORDER BY pending DESC
        """
        domain_rows = conn.execute(sql_domain).fetchall()

    finally:
        conn.close()

    sep = "=" * 80
    print(sep)
    print(" TOÀN CẢNH KHO DỮ LIỆU & BẢN ĐỒ BÀI VIẾT TỒN ĐỌNG (WAREHOUSE BACKLOG RADAR)")
    print(sep)
    print("1. TỔNG QUAN KHO & CÁC TẦNG DỮ LIỆU:")
    print(f"   • Tổng số bài thu thập trong kho (articles): {total_articles:,} bài")
    pct_gold = (gold_done / total_articles * 100) if total_articles else 0
    pct_pending = (gold_pending / total_articles * 100) if total_articles else 0
    print(f"   • Đã phân tích Gold đạt chuẩn DoD          : {gold_done:,} bài ({pct_gold:.1f}%)")
    print(f"   • TỒN ĐỌNG CHƯA PHÂN TÍCH GOLD (PENDING)   : {gold_pending:,} bài ({pct_pending:.1f}%)")
    pct_l1 = (llm_l1 / total_articles * 100) if total_articles else 0
    print(f"   • Đã phân tích L1 bằng LLM đạt chuẩn       : {llm_l1:,} bài ({pct_l1:.1f}%)")
    print(f"   • L1 Code-First nạp nhanh (chưa qua LLM)   : {code_first_l1:,} bài")
    print(f"   • Bài kế thừa cụm tin trùng (cluster copy) : {cluster_copies:,} bài")
    print(f"   • Trạng thái work_items (hàng đợi)         : " + ", ".join(f"{k}={v:,}" for k, v in work_items.items()))
    print()

    print("2. PHÂN LOẠI THEO MỨC ĐỘ ƯU TIÊN (PRIORITY TIERS):")
    pct_t1 = (tier1_cnt / gold_pending * 100) if gold_pending else 0
    pct_t2 = (tier2_cnt / gold_pending * 100) if gold_pending else 0
    print(f"   • TIER 1 (Ưu tiên cao nhất - Watchlist & Vĩ mô khẩn) : {tier1_cnt:,} bài ({pct_t1:.1f}%)")
    print(f"   • TIER 2 & 3 (Hàng đợi nền - Tin thị trường chung)   : {tier2_cnt:,} bài ({pct_t2:.1f}%)")
    print()

    print("3. PHÂN BỔ TỒN ĐỌNG THEO TRỤC THỜI GIAN:")
    print(f"   {'Giai đoạn / Ngày':<24} | {'Tổng bài':>10} | {'Đã xử lý':>10} | {'Tồn đọng':>10} | {'Tỷ lệ tồn':>10}")
    print(f"   {'-'*24}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")
    for r in period_rows:
        grp = r[0]
        tot = r[1]
        dn = r[2] or 0
        pnd = r[3] or 0
        ratio = (pnd / tot * 100) if tot else 0
        print(f"   {grp:<24} | {tot:>10,d} | {dn:>10,d} | {pnd:>10,d} | {ratio:>9.1f}%")
    print()

    print("4. PHÂN BỔ TỒN ĐỌNG THEO NGUỒN THU THẬP (SOURCE DOMAINS):")
    print(f"   {'Tên miền (Domain)':<28} | {'Tổng bài':>10} | {'Đã xử lý':>10} | {'Tồn đọng':>10} | {'Tỷ lệ tồn':>10}")
    print(f"   {'-'*28}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")
    for r in domain_rows[:10]:
        dom = r[0] or "N/A"
        tot = r[1]
        dn = r[2] or 0
        pnd = r[3] or 0
        ratio = (pnd / tot * 100) if tot else 0
        print(f"   {dom:<28} | {tot:>10,d} | {dn:>10,d} | {pnd:>10,d} | {ratio:>9.1f}%")
    print()

    print("5. CHIẾN LƯỢC ĐIỀU PHỐI ĐỢT CUỐN CHIẾU (RECOMMENDED ROLLING WAVES):")
    est_cost = (gold_pending / 1000) * 0.23
    est_waves = (gold_pending + 499) // 500
    print(f"   • Định mức chi phí dự toán (Gemini 3.8 Flash) : ~${est_cost:.2f} USD cho {gold_pending:,} bài")
    print(f"   • Quy mô đợt khuyến nghị (Wave Size)         : 500 bài / wave (~{est_waves} waves)")
    print()
    print("   [Pha 1] Xử lý dữ liệu nóng gần nhất theo ngày (Tháng 10/2026):")
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/article_run.py --wave W_OCT15 --date 2026-10-15 --runner agy')
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/article_run.py --wave W_OCT15 --runner agy --analyze --concurrency 1')
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/article_run.py --wave W_OCT15 --finish --force')
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/write_user_output.py --date 2026-10-15 --force')
    print()
    print("   [Pha 2] Xử lý gom đợt lớn tồn đọng (500 bài / wave):")
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/article_run.py --wave W_BACKLOG500 --limit 500 --runner agy')
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/article_run.py --wave W_BACKLOG500 --runner agy --analyze --concurrency 1')
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/article_run.py --wave W_BACKLOG500 --finish --force')
    print('      & "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/write_user_output.py --force')
    print(sep)


def cmd_users(args: argparse.Namespace) -> None:
    """Report registered users and detect subscription files missing from the manifest.

    Args:
        args: Parsed command-line arguments; unused.
    """
    print(f"================================================================================")
    print(f" 👥  NEWS-SCAPE USER WATCHLIST & ENTITY MONITOR")
    print(f"================================================================================")

    manifest = load_user_manifest()
    users = manifest["users"]
    active_users = [u for u, is_active in users.items() if is_active]
    inactive_users = [u for u, is_active in users.items() if not is_active]

    print(f"1. DANH SÁCH NGƯỜI DÙNG TRONG HỆ THỐNG:")
    print(f"   • Đang kích hoạt (Active) : {len(active_users)} ({', '.join(active_users)})")
    print(f"   • Đang tạm dừng (Inactive): {len(inactive_users)} ({', '.join(inactive_users) if inactive_users else 'Không có'})")
    print()

    # Find subscription Excel files that are not yet registered in the manifest.
    subs_dir = paths.subscriptions_dir()
    if subs_dir.exists():
        excel_files = glob.glob(str(subs_dir / "*_news.xlsx"))
        unregistered = []
        for ef in excel_files:
            uname = os.path.basename(ef).replace("_news.xlsx", "")
            if uname.startswith("_") or uname.lower() in ("template", "_template"):
                continue
            if uname not in users:
                unregistered.append(uname)

        print(f"2. PHÁT HIỆN TẬP TIN ĐĂNG KÝ MỚI (SUBSCRIPTION DISCOVERY):")
        if unregistered:
            print(f"   ⚠️  Phát hiện {len(unregistered)} người dùng có file đăng ký nhưng CHƯA khai báo trong subscriptions/manifest.yaml:")
            for u in unregistered:
                print(f"      👉 User: '{u}' -> Cần thêm vào subscriptions/manifest.yaml")
        else:
            print(f"   ✅ Toàn bộ file đăng ký đã được đồng bộ chuẩn với manifest.yaml.")
    print(f"================================================================================\n")


def main() -> None:
    """Parse the subcommand and dispatch it."""
    parser = argparse.ArgumentParser(description="Hệ thống Công cụ Giám sát & Quản trị Tự động News-Scape.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: status.
    p_status = subparsers.add_parser("status", help="Truy vấn điểm chạm hiện tại và đề xuất hành động kế tiếp.")
    p_status.add_argument("--date", help="Ngày cần quan sát (YYYY-MM-DD), mặc định là hôm nay.")

    # Subcommand: token.
    p_token = subparsers.add_parser("token", help="Đo lường token burn và đánh giá tiết kiệm chi phí.")
    p_token.add_argument("--date", help="Ngày cần đo lường (YYYY-MM-DD), mặc định là hôm nay.")
    p_token.add_argument("--wave", help="Chỉ xem một đợt, bỏ qua bộ lọc ngày.")

    # Subcommand: users.
    subparsers.add_parser("users", help="Quan sát và tra soát trạng thái người dùng & danh mục theo dõi.")

    # Subcommand: backlog.
    subparsers.add_parser("backlog", help="Quan sát toàn cảnh kho dữ liệu và phân bổ bài viết tồn đọng.")

    args = parser.parse_args()
    if args.command == "status":
        cmd_status(args)
    elif args.command == "token":
        cmd_token(args)
    elif args.command == "users":
        cmd_users(args)
    elif args.command == "backlog":
        cmd_backlog(args)


if __name__ == "__main__":
    main()

