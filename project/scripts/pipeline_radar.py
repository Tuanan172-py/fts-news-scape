"""Bộ công cụ CLI trinh sát, quan sát và kiểm soát trạng thái vận hành News-Scape."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Cấu hình UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.token_ledger import (                         # noqa: E402
    latest_snapshots,
    worker_calls,
)
from src.agent.prefix import cached_prefix_tokens          # noqa: E402
from src.db.preflight import probe_write, resolve_db_path  # noqa: E402
from src.telemetry.dsh_usage import (                      # noqa: E402
    billed_usd,
    is_peak,
    iter_sessions,
    load_pricing,
)

DATA_ROOT = PROJECT_ROOT / "data"
ARTICLE_TASK_DIR = DATA_ROOT / "agent_tasks" / "article"
USER_OUTPUT_DIR = PROJECT_ROOT.parent / "users" / "output"
MANIFEST_YAML = PROJECT_ROOT / "config" / "entities" / "manifest.yaml"
HARNESS_DB = PROJECT_ROOT.parent / "harness.db"
PY = '& "C:\\venvs\\news-scape\\Scripts\\python.exe"'


def get_db_connection() -> sqlite3.Connection:
    """Mở kết nối chỉ đọc tới đúng cơ sở dữ liệu mà bước nạp ghi vào.

    Returns:
        Kết nối SQLite ở chế độ `mode=ro`.
    """
    uri = f"file:{resolve_db_path().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _local_naive(ts: str) -> datetime:
    """Đổi chuỗi ISO có hoặc không có múi giờ thành giờ máy không kèm múi giờ.

    Args:
        ts: Chuỗi thời điểm dạng ISO.

    Returns:
        Thời điểm theo giờ máy.
    """
    clean = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean)
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def latest_wave() -> dict | None:
    """Đọc mô tả của đợt Article Lane được đóng gói gần nhất.

    Returns:
        Nội dung tệp `wave_<mã>.json` mới nhất, hoặc None khi chưa có đợt nào.
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
    """Xác định đợt đang ở nửa nào của vòng đời và lệnh kế tiếp của nó.

    Bốn trạng thái theo đúng thứ tự vòng đời: còn lô chưa có đầu ra (chạy chương
    trình điều phối), có bài gửi đi mà chưa nhận được bản ghi (vá), đủ bản ghi nhưng
    cơ sở dữ liệu chưa đủ (hoàn tất), và đã xong.

    Args:
        conn: Kết nối SQLite chỉ đọc.
        manifest: Mô tả đợt do bước đóng gói sinh ra.

    Returns:
        Từ điển số đo của đợt kèm khoá `phase` và `next` (lệnh kế tiếp, rỗng khi xong).
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


def cmd_status(args: argparse.Namespace) -> None:
    """Truy vấn điểm chạm hiện tại của Article Lane và đề xuất đúng lệnh kế tiếp.

    Article Lane là đường xử lý duy nhất. Radar không đọc và không khuyến nghị gì
    thuộc lane L1/Gold cũ (`l1_tasks`, hàng đợi `work_items`, packet `agent_tasks/l1`),
    vì mọi khuyến nghị ấy dẫn phía điều phối đi sai đường.

    Args:
        args: Tham số dòng lệnh đã phân tích.
    """
    from scripts.article_pack import ANALYZED_L1, load_candidates

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

    # Độ phủ theo NGÀY ĐĂNG, cùng định nghĩa với `handoff.py`. Bản code-first không
    # tính là đã phân tích.
    covered = {}
    for table, cond in (("l1_outputs", ANALYZED_L1), ("agent_outputs", "o.dod_pass = 1")):
        cur.execute(f"""
            SELECT count(distinct o.article_id) FROM {table} o
            JOIN articles a ON a.url_title_hash = o.article_id
            WHERE substr(a.published_at,1,10) = ? AND {cond}
        """, (target_date,))
        covered[table] = cur.fetchone()[0]

    # Cùng một câu truy vấn với bước đóng gói, nên số "chờ phân tích" ở đây đúng bằng
    # số bài mà `article_run.py --date` sẽ lấy.
    pending_today = len(load_candidates(conn, date=target_date, limit=1_000_000,
                                        only_pending=True))

    source_deleted = "(metadata_json LIKE '%\"source_deleted\": true%' " \
                     "OR metadata_json LIKE '%\"source_deleted\":true%')"
    cur.execute(f"SELECT count(1) FROM articles WHERE substr(published_at,1,10) = ? "
                f"AND {source_deleted}", (target_date,))
    source_deleted_count = cur.fetchone()[0]
    # Bài bị xóa thường được PHÁT HIỆN muộn hơn ngày đăng, nên kèm tổng tích lũy.
    cur.execute(f"SELECT count(1) FROM articles WHERE {source_deleted}")
    source_deleted_total = cur.fetchone()[0]

    # Sổ lỗi derive Bronze→Silver (ADR 0007). Dead-letter là nội dung không bao giờ
    # tới được bước phân tích hay người dùng.
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

    # Tăng vọt 404/410 tập trung ở MỘT domain hầu như luôn là site đổi cấu trúc URL
    # hoặc selector chứ không phải tin bị gỡ thật.
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
    print(f"   • Bài bị nguồn xóa (404/410)     : {source_deleted_count:,} bài đăng hôm nay / "
          f"{source_deleted_total:,} tổng tích lũy")
    _silver_tag = "🟢" if not (silver_blocking or silver_dead) else (
        "🔴" if silver_dead else "🟡")
    print(f"   • Bronze kẹt ở Silver (ADR 0007) : {_silver_tag} {silver_blocking:,} đang chặn "
          f"watermark / {silver_dead:,} dead-letter")
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

    print("3. ĐIỂM CHẠM & LỆNH KẾ TIẾP")
    recs: list[tuple[str, str, str]] = []

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

    if silver_dead:
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

    # Một đợt tại một thời điểm: đợt gần nhất chưa xong thì không mở đợt mới.
    wave_open = bool(wave and wave["next"])
    if wave_open:
        recs.append(("HIGH", f"Đợt {wave['wave']}: {wave['phase']}.", wave["next"]))
    elif pending_today:
        new_wave = f"W{datetime.now():%m%d%H%M}"
        recs.append(("HIGH", f"{pending_today:,} bài đăng ngày {target_date} chờ phân tích.",
                     f"{PY} scripts/article_run.py --wave {new_wave} --date {target_date} "
                     f"--limit {pending_today} --batch 100"))

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
    """Đổi một ngày theo đồng hồ máy thành khoảng mốc UTC để tra sổ cái.

    Args:
        date: Ngày dạng YYYY-MM-DD theo giờ địa phương.

    Returns:
        Cặp mốc đầu và cuối dạng ISO UTC, cùng định dạng với cột `ts` của sổ cái.
    """
    start = datetime.strptime(date, "%Y-%m-%d").astimezone()
    end = start + timedelta(days=1)
    fmt = lambda d: d.astimezone(timezone.utc).isoformat(timespec="seconds")
    return fmt(start), fmt(end)


def _ledger_rows(date: str | None, wave: str | None) -> list[sqlite3.Row]:
    """Đọc các dòng sổ cái token theo ngày hoặc theo đợt.

    Args:
        date: Ngày cần lọc dạng YYYY-MM-DD, bỏ qua khi đã chỉ định đợt.
        wave: Mã đợt cần lọc.

    Returns:
        Danh sách dòng sổ cái, rỗng khi chưa có sổ cái hoặc không dòng nào khớp.
    """
    if not HARNESS_DB.exists():
        return []
    conn = sqlite3.connect(f"file:{HARNESS_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if wave:
            sql, params = "SELECT * FROM token_ledger WHERE wave = ?", (wave,)
        else:
            # Sổ cái ghi mốc theo UTC, còn người vận hành nghĩ theo ngày của đồng hồ
            # máy. So thẳng `substr(ts,1,10)` với ngày máy là sai đúng bảy tiếng: mọi
            # đợt chạy trước 07:00 giờ VN bị ghi vào ngày hôm trước theo UTC, nên
            # radar báo "chưa có dòng nào" cho một ngày vừa chạy xong. Vì vậy đổi
            # ngày địa phương thành một khoảng UTC rồi mới so.
            lo, hi = _utc_window(date)
            sql, params = ("SELECT * FROM token_ledger WHERE ts >= ? AND ts < ?",
                           (lo, hi))
        rows = list(conn.execute(sql + " ORDER BY id", params))
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    # Sổ cái ghi ảnh chụp tích luỹ cho mỗi đợt, nên phải khử trước khi cộng. Dùng
    # chung đúng một định nghĩa với `token_ledger.py` để hai công cụ không bao giờ
    # nói hai con số khác nhau về cùng một đợt.
    return latest_snapshots(rows)


def cmd_token(args: argparse.Namespace) -> None:
    """Báo cáo token và chi phí thật của đường xử lý bài đăng.

    Lệnh này từng nhân số bài với hai định mức chết — 450 token mỗi bài tầng L1 và
    1.470 tầng Gold — rồi nhân tiếp với một đơn giá gõ thẳng trong mã. Cả ba con số
    đều sai: hai định mức lệch thực tế 21 đến 41 lần, còn đơn giá thì không phân biệt
    ba rổ token mà nhà cung cấp tính riêng. Tệ hơn cả sai số là việc nó **không biết
    bộ nhớ đệm tồn tại**, trong khi token trúng cache rẻ hơn token mới năm mươi lần;
    radar và sổ cái vì thế đưa ra hai con số mâu thuẫn cho cùng một đợt.

    Nay mọi con số đến từ hai nguồn đo thật: sổ cái `token_ledger` cho các đợt đã
    chốt, và checkpoint phiên DSH cho phần đang chạy. Không còn định mức nào.

    Args:
        args: Tham số dòng lệnh đã phân tích.
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
        # Mỗi dòng tính theo khung giá của chính nó. Dùng khung giá lúc chạy báo cáo
        # sẽ thổi phồng một đợt off-peak đem ra xem vào giờ cao điểm đúng gấp đôi.
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
        # Đếm theo LƯỢT GỌI worker đọc từ mô tả đợt. Đếm theo số phiên là tính cả
        # phiên Conductor — phiên ấy mang persona khác nên không đọc tiền tố của
        # worker, và sàn sẽ đòi một khoản cache không bao giờ tồn tại.
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

    # Khi xem theo đợt, ngày của phiên phải là ngày của chính đợt ấy. Lấy hôm nay
    # thì một đợt chạy tuần trước luôn hiện "không có phiên nào", nghe như mất dữ
    # liệu trong khi chỉ là so nhầm ngày.
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
        # Lời khuyên hành động chỉ có nghĩa cho HÔM NAY. In nó khi đang xem một
        # ngày đã qua là hô "dừng ngay" về một phiên đóng từ tuần trước.
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


def cmd_users(args: argparse.Namespace) -> None:
    """Quan sát và phát hiện các thay đổi đăng ký người dùng mới / thiếu hụt thực thể."""
    print(f"================================================================================")
    print(f" 👥  NEWS-SCAPE USER WATCHLIST & ENTITY MONITOR")
    print(f"================================================================================")

    if not MANIFEST_YAML.exists():
        print(f"❌ Không tìm thấy tệp manifest tại: {MANIFEST_YAML}")
        return

    import yaml
    with open(MANIFEST_YAML, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f) or {}

    users = manifest.get("users", {})
    active_users = [u for u, is_active in users.items() if is_active]
    inactive_users = [u for u, is_active in users.items() if not is_active]

    print(f"1. DANH SÁCH NGƯỜI DÙNG TRONG HỆ THỐNG:")
    print(f"   • Đang kích hoạt (Active) : {len(active_users)} ({', '.join(active_users)})")
    print(f"   • Đang tạm dừng (Inactive): {len(inactive_users)} ({', '.join(inactive_users) if inactive_users else 'Không có'})")
    print()

    # Kiểm tra xem có file subscription excel mới nào chưa được kích hoạt không
    subs_dir = PROJECT_ROOT.parent / "users" / "subscriptions"
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
            print(f"   ⚠️  Phát hiện {len(unregistered)} người dùng có file đăng ký nhưng CHƯA khai báo trong manifest.yaml:")
            for u in unregistered:
                print(f"      👉 User: '{u}' -> Cần thêm vào config/entities/manifest.yaml")
        else:
            print(f"   ✅ Toàn bộ file đăng ký đã được đồng bộ chuẩn với manifest.yaml.")
    print(f"================================================================================\n")


def main() -> None:
    """Điểm nhập lệnh điều phối CLI."""
    parser = argparse.ArgumentParser(description="Hệ thống Công cụ Giám sát & Quản trị Tự động News-Scape.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Lệnh status
    p_status = subparsers.add_parser("status", help="Truy vấn điểm chạm hiện tại và đề xuất hành động kế tiếp.")
    p_status.add_argument("--date", help="Ngày cần quan sát (YYYY-MM-DD), mặc định là hôm nay.")

    # Lệnh token
    p_token = subparsers.add_parser("token", help="Đo lường token burn và đánh giá tiết kiệm chi phí.")
    p_token.add_argument("--date", help="Ngày cần đo lường (YYYY-MM-DD), mặc định là hôm nay.")
    p_token.add_argument("--wave", help="Chỉ xem một đợt, bỏ qua bộ lọc ngày.")

    # Lệnh users
    subparsers.add_parser("users", help="Quan sát và tra soát trạng thái người dùng & danh mục theo dõi.")

    args = parser.parse_args()
    if args.command == "status":
        cmd_status(args)
    elif args.command == "token":
        cmd_token(args)
    elif args.command == "users":
        cmd_users(args)


if __name__ == "__main__":
    main()
