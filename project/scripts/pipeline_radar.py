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
from src.telemetry.dsh_usage import (                      # noqa: E402
    billed_usd,
    is_peak,
    iter_sessions,
    load_pricing,
)

DATA_ROOT = PROJECT_ROOT / "data"
AGENT_TASKS_DIR = DATA_ROOT / "agent_tasks"
AGENT_OUTPUTS_DIR = DATA_ROOT / "agent_outputs"
L1_TASKS_DIR = AGENT_TASKS_DIR / "l1"
L1_OUTPUTS_DIR = DATA_ROOT / "agent_outputs_l1"
USER_OUTPUT_DIR = PROJECT_ROOT.parent / "users" / "output"
MANIFEST_YAML = PROJECT_ROOT / "config" / "entities" / "manifest.yaml"
DB_PATH = Path("C:/data/news-scape/monocle.db")
HARNESS_DB = PROJECT_ROOT.parent / "harness.db"


def get_db_connection() -> sqlite3.Connection:
    """Khởi tạo kết nối SQLite ở chế độ Read-Only an toàn."""
    db_file = DB_PATH if DB_PATH.exists() else (DATA_ROOT / "monocle.db")
    uri = f"file:{db_file.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def cmd_status(args: argparse.Namespace) -> None:
    """Truy vấn điểm chạm hiện tại của pipeline và đề xuất hành động kế tiếp."""
    target_date = args.date or f"{datetime.now():%Y-%m-%d}"
    print(f"================================================================================")
    print(f" 🛰️  NEWS-SCAPE PIPELINE OBSERVABILITY & STATUS REPORT — [{target_date}]")
    print(f"================================================================================")

    conn = get_db_connection()
    cur = conn.cursor()

    # 0. Kiểm tra độ tươi cào tin (Scraper Freshness & Gap Detection)
    cur.execute("SELECT max(last_run_ts) FROM scraper_heartbeat WHERE scraper_name NOT LIKE '%-%'")
    last_hb_row = cur.fetchone()
    last_scrape_ts_str = last_hb_row[0] if last_hb_row and last_hb_row[0] else None

    cur.execute("SELECT max(fetched_at) FROM articles")
    last_fetch_row = cur.fetchone()
    last_fetch_ts_str = last_fetch_row[0] if last_fetch_row and last_fetch_row[0] else None

    # Tính độ trễ cào tin
    scrape_delay_minutes = None
    now_dt = datetime.now()
    ref_ts_str = last_scrape_ts_str or last_fetch_ts_str
    if ref_ts_str:
        try:
            # Hỗ trợ ISO string có hoặc không có timezone
            ref_clean = ref_ts_str.replace("Z", "+00:00")
            if "+" in ref_clean[10:] or "-" in ref_clean[10:]:
                ref_dt = datetime.fromisoformat(ref_clean).astimezone().replace(tzinfo=None)
            else:
                ref_dt = datetime.fromisoformat(ref_clean)
            scrape_delay_minutes = max(0, int((now_dt - ref_dt).total_seconds() / 60))
        except Exception:
            pass

    # 1. Thống kê bài viết cào về
    cur.execute("SELECT count(*) FROM articles WHERE date(published_at) = ?", (target_date,))
    crawled_count = cur.fetchone()[0]

    # 2. Thống kê L1
    cur.execute("""
        SELECT count(distinct article_id)
        FROM l1_outputs
        WHERE date(created_at) = ?
    """, (target_date,))
    l1_done_count = cur.fetchone()[0]

    # 3. Thống kê Gold
    cur.execute("""
        SELECT count(distinct article_id)
        FROM agent_outputs
        WHERE date(created_at) = ?
    """, (target_date,))
    gold_done_count = cur.fetchone()[0]

    # 3b. Thống kê trạng thái hàng đợi L1 trong DB
    cur.execute("""
        SELECT count(1)
        FROM articles a
        WHERE date(a.published_at) = ?
        AND NOT EXISTS (SELECT 1 FROM l1_tasks lt WHERE lt.article_id = a.url_title_hash)
    """, (target_date,))
    l1_unrouted_count = cur.fetchone()[0]

    cur.execute("""
        SELECT count(1)
        FROM l1_tasks lt
        JOIN articles a ON lt.article_id = a.url_title_hash
        WHERE date(a.published_at) = ? AND lt.route = 'resolved' AND lt.status = 'pending'
    """, (target_date,))
    l1_resolved_pending = cur.fetchone()[0]

    # 3c-override. Bao phủ L1 theo NGÀY ĐĂNG (khác l1_done_count vốn đếm theo created_at):
    # trong bài đăng hôm nay, bao nhiêu đã có l1_outputs dod_pass=1, còn bao nhiêu needs_agent chờ.
    cur.execute("""
        SELECT count(distinct lo.article_id)
        FROM l1_outputs lo
        JOIN articles a ON a.url_title_hash = lo.article_id
        WHERE date(a.published_at) = ? AND lo.dod_pass = 1
    """, (target_date,))
    l1_today_covered = cur.fetchone()[0]

    cur.execute("""
        SELECT count(1)
        FROM l1_tasks lt
        JOIN articles a ON a.url_title_hash = lt.article_id
        WHERE date(a.published_at) = ? AND lt.route <> 'resolved' AND lt.status = 'pending'
    """, (target_date,))
    l1_today_needs_agent = cur.fetchone()[0]

    # 3d. Bài bị nguồn xóa (404/410) trước khi kịp lấy nội dung đầy đủ — đặc trưng tin VN
    cur.execute("""
        SELECT count(1)
        FROM articles
        WHERE date(published_at) = ?
        AND (metadata_json LIKE '%"source_deleted": true%'
             OR metadata_json LIKE '%"source_deleted":true%')
    """, (target_date,))
    source_deleted_count = cur.fetchone()[0]

    # Bài bị xóa thường được PHÁT HIỆN muộn hơn ngày đăng (đường retry làm việc với bài
    # fetch trong 24h qua), nên con số lọc theo published_at của riêng hôm nay luôn thấp
    # hơn thực tế. Kèm tổng tích lũy để không bỏ sót tín hiệu.
    cur.execute("""
        SELECT count(1) FROM articles
        WHERE metadata_json LIKE '%"source_deleted": true%'
           OR metadata_json LIKE '%"source_deleted":true%'
    """)
    source_deleted_total = cur.fetchone()[0]

    # 3f. Sổ lỗi derive Bronze→Silver (ADR 0007). Dead-letter = nội dung KHÔNG lên được
    # Silver, tức không bao giờ tới L1/Gold/người dùng — phải nhìn thấy được.
    try:
        cur.execute("""
            SELECT sum(CASE WHEN dead_letter=0 THEN 1 ELSE 0 END) AS blocking,
                   sum(CASE WHEN dead_letter=1 THEN 1 ELSE 0 END) AS dead
            FROM silver_failures
        """)
        _r = cur.fetchone()
        silver_blocking, silver_dead = int(_r[0] or 0), int(_r[1] or 0)
    except sqlite3.OperationalError:
        silver_blocking = silver_dead = 0      # bảng chưa tạo (DB cũ chưa migrate)

    # 3g. Thống kê trạng thái hàng đợi kẹt (work_items held/claimed/failed và l1_tasks failed)
    cur.execute("SELECT status, count(1) FROM work_items GROUP BY status")
    wi_counts = dict(cur.fetchall())
    wi_held = wi_counts.get("held", 0)
    wi_claimed = wi_counts.get("claimed", 0)
    wi_failed = wi_counts.get("failed", 0)

    cur.execute("SELECT count(1) FROM l1_tasks WHERE status = 'failed'")
    l1_failed = cur.fetchone()[0]

    # 3e. Phân bố 404/410 theo domain. Tăng vọt tập trung ở MỘT domain hầu như luôn là
    # site đổi cấu trúc URL/selector (404 giả) chứ không phải tin bị gỡ thật.
    cur.execute("""
        SELECT source_domain,
               sum(CASE WHEN metadata_json LIKE '%"source_deleted": true%'
                          OR metadata_json LIKE '%"source_deleted":true%'
                        THEN 1 ELSE 0 END) AS deleted,
               count(1) AS total
        FROM articles
        WHERE date(published_at) = ?
        GROUP BY source_domain
    """, (target_date,))
    deleted_by_domain = [(r[0], r[1], r[2]) for r in cur.fetchall() if r[1]]

    # 3c. Thống kê bài Gold pending theo Subscriber Gating cho target_date
    gold_pending_subs_count = 0
    try:
        from src.agent.entities import load_registry
        reg = load_registry()
        active_subs = set()
        for user_subs in reg.subscriptions.values():
            active_subs.update(user_subs)

        cur.execute("""
            SELECT w.article_id, l1.output_json
            FROM work_items w
            JOIN articles a ON w.article_id = a.url_title_hash
            JOIN l1_outputs l1 ON l1.article_id = w.article_id AND l1.dod_pass = 1
            WHERE w.status = 'pending'
            AND date(COALESCE(NULLIF(a.published_at, ''), a.fetched_at)) = ?
        """, (target_date,))
        rows = cur.fetchall()
        for aid, out_json in rows:
            if not out_json:
                continue
            try:
                data = json.loads(out_json)
                eids = [e["entity_id"] for e in data.get("entities", []) if e.get("entity_id")]
                if any(eid in active_subs for eid in eids):
                    gold_pending_subs_count += 1
            except Exception:
                pass
    except Exception:
        pass

    # 4. Thống kê Task files đang treo trên đĩa (chỉ quét PROJECT_ROOT / "data")
    def _find_files(*relative_patterns: str) -> list[str]:
        found = []
        for pat in relative_patterns:
            found.extend(glob.glob(str(DATA_ROOT / pat)))
        return list(set(found))

    l1_tasks = _find_files("agent_tasks/l1/*.task.json")
    l1_tasks_pending = len(l1_tasks)
    gold_tasks = _find_files("agent_tasks/batch_*.task.json") + \
                 [f for f in _find_files("agent_tasks/*.task.json") if not os.path.basename(f).startswith("batch_")]
    gold_tasks_pending = len(set(gold_tasks))

    # 5. Thống kê Output files có bài chưa Ingest vào DB
    l1_outputs_waiting = 0
    for lf in _find_files("agent_outputs_l1/*.output.json"):
        try:
            with open(lf, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data if isinstance(data, list) else data.get("outputs", [])
                for it in items:
                    cur.execute("SELECT 1 FROM l1_outputs WHERE article_id = ?", (it.get("article_id"),))
                    if not cur.fetchone():
                        l1_outputs_waiting += 1
        except Exception:
            pass

    gold_outputs_waiting = 0
    for gf in _find_files("agent_outputs/*.output.json"):
        try:
            with open(gf, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data if isinstance(data, list) else data.get("outputs", [])
                for it in items:
                    cur.execute("SELECT 1 FROM agent_outputs WHERE article_id = ?", (it.get("article_id"),))
                    if not cur.fetchone():
                        gold_outputs_waiting += 1
        except Exception:
            pass

    conn.close()

    print(f"1. DỮ LIỆU TẠI KHO (DATABASE & BRONZE/SILVER):")
    print(f"   • Số bài cào xuất bản trong ngày : {crawled_count:,} bài")
    print(f"   • Số bài đã hoàn tất tầng L1     : {l1_done_count:,} bài")
    _cover_pct = (100.0 * l1_today_covered / crawled_count) if crawled_count else 0.0
    print(f"   • Bao phủ L1 bài đăng hôm nay    : {l1_today_covered:,}/{crawled_count:,} "
          f"({_cover_pct:.1f}%) · còn {l1_today_needs_agent:,} needs_agent chờ · "
          f"{l1_unrouted_count:,} chưa định tuyến")
    print(f"   • Số bài đã hoàn tất tầng Gold   : {gold_done_count:,} bài")
    print(f"   • Bài Gold đủ điều kiện chờ phân tích (Subscriber-Gated): {gold_pending_subs_count:,} bài")
    print(f"   • Bài bị nguồn xóa (404/410) trước khi lấy được nội dung: "
          f"{source_deleted_count:,} bài đăng hôm nay / {source_deleted_total:,} tổng tích lũy")
    _silver_tag = "🟢" if not (silver_blocking or silver_dead) else (
        "🔴" if silver_dead else "🟡")
    print(f"   • Bronze kẹt ở Silver (ADR 0007)  : {_silver_tag} "
          f"{silver_blocking:,} đang chặn watermark / {silver_dead:,} dead-letter")
    _queue_dead_tag = "🔴" if (wi_held or wi_failed or l1_failed) else ("🟡" if wi_claimed > 50 else "🟢")
    print(f"   • Hàng đợi kẹt (Phase 03)        : {_queue_dead_tag} "
          f"work_items: {wi_claimed:,} claimed, {wi_held:,} held, {wi_failed:,} failed | l1_tasks: {l1_failed:,} failed")
    if scrape_delay_minutes is not None:
        delay_str = f"{scrape_delay_minutes} phút" if scrape_delay_minutes < 60 else f"{scrape_delay_minutes // 60}h {scrape_delay_minutes % 60}m"
        last_time_str = ref_ts_str.split("T")[1][:8] if "T" in ref_ts_str else ref_ts_str
        freshness_tag = "🟢 Tươi mới" if scrape_delay_minutes <= 30 else ("🟡 Chậm nhẹ" if scrape_delay_minutes <= 120 else "🔴 Gián đoạn / Khoảng trống đêm")
        print(f"   • Độ tươi cào tin (Liveness)     : {freshness_tag} (lần cào cuối lúc {last_time_str}, cách đây {delay_str})")
    print()

    print(f"2. TRẠNG THÁI HÀNG ĐỢI FILE (TASK PACKETS & BATCHES):")
    print(f"   • Tác vụ L1 đang chờ Subagents   : {l1_tasks_pending} files/batches")
    print(f"   • Tác vụ Gold đang chờ Subagents : {gold_tasks_pending} files/batches")
    print(f"   • Bài L1 đã xuất chưa Ingest DB  : {l1_outputs_waiting} bài")
    print(f"   • Bài Gold đã xuất chưa Ingest DB: {gold_outputs_waiting} bài")
    print()

    # 6. Xác định điểm chạm và Đề xuất hành động tiếp theo
    print(f"3. ĐIỂM CHẠM VẬN HÀNH & ĐỀ XUẤT HÀNH ĐỘNG CỤ THỂ:")
    recommendations = []

    # Cảnh báo gián đoạn cào tin (qua đêm hoặc tiến trình ngắt)
    if scrape_delay_minutes is not None and scrape_delay_minutes > 120:
        delay_hrs = scrape_delay_minutes // 60
        recommendations.append((
            "HIGH",
            f"Phát hiện khoảng trống runtime cào tin ({delay_hrs}h qua chưa cào, máy sleep hoặc scheduler dừng). Cần cào vét bù tin ngay.",
            f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/run_once.py'
        ))
    elif scrape_delay_minutes is not None and scrape_delay_minutes > 45:
        recommendations.append((
            "MEDIUM",
            f"Tiến trình cào tin tự động đang chậm ({scrape_delay_minutes} phút chưa có nhịp cào mới).",
            f'Kiểm tra background morninger hoặc chạy bù: & "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/run_once.py'
        ))

    if silver_dead:
        recommendations.append((
            "HIGH",
            f"Có {silver_dead} tệp Bronze DEAD-LETTER ở Silver — nội dung không bao giờ "
            f"lên được Silver, tức không tới L1/Gold/người dùng. Đây là mất dữ liệu thật.",
            'Soi nguyên nhân: SELECT meta_path, attempts, last_error FROM silver_failures '
            'WHERE dead_letter=1; — sửa gốc rồi xoá hàng đó để derive thử lại'
        ))
    elif silver_blocking:
        recommendations.append((
            "MEDIUM",
            f"Có {silver_blocking} tệp Bronze đang chặn watermark Silver (chưa đủ ngưỡng "
            f"dead-letter). Watermark sẽ không tiến qua chúng cho tới khi xong hoặc bỏ cuộc.",
            'SELECT meta_path, attempts, last_error FROM silver_failures WHERE dead_letter=0;'
        ))

    if wi_failed > 0 or l1_failed > 0:
        recommendations.append((
            "HIGH",
            f"Có {wi_failed} work_items và {l1_failed} l1_tasks ở trạng thái 'failed' (trượt DoD).",
            '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/maintenance/requeue.py --state failed --layer all --apply'
        ))
    elif wi_held > 0:
        recommendations.append((
            "MEDIUM",
            f"Có {wi_held} work_items đang ở trạng thái 'held'. Sẽ tự động về pending khi derive lại thành công hoặc chạy requeue.",
            '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/maintenance/requeue.py --state held --layer gold --apply'
        ))

    # Nghi ngờ 404 giả: một domain vừa nhiều tuyệt đối vừa chiếm tỷ trọng lớn.
    for _dom, _deleted, _total in deleted_by_domain:
        if _deleted > 10 and _total and (_deleted / _total) > 0.3:
            recommendations.append((
                "HIGH",
                f"Domain {_dom}: {_deleted}/{_total} bài trả 404/410 — nghi site đổi "
                f"cấu trúc URL/selector chứ KHÔNG phải tin bị gỡ thật. Cần kiểm chứng "
                f"trước khi tin vào số liệu 'bài bị nguồn xóa'.",
                f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" '
                f'scripts/validate_capture.py {_dom.split(".")[0]}'
            ))

    if l1_outputs_waiting > 0:
        recommendations.append((
            "HIGH",
            f"Có {l1_outputs_waiting} bài L1 trong output files chưa Ingest vào DB.",
            f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/l1_ingest.py data/agent_outputs_l1'
        ))

    if gold_outputs_waiting > 0:
        recommendations.append((
            "HIGH",
            f"Có {gold_outputs_waiting} bài Gold trong output files chưa nạp DB.",
            f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/agent_ingest.py data/agent_outputs'
        ))

    if l1_tasks_pending > 0:
        recommendations.append((
            "MEDIUM",
            f"Có {l1_tasks_pending} task/batch L1 cần khởi động Subagent `l1_entity_matcher`.",
            f'Gọi Subagents Flash xử lý các batch trong data/agent_tasks/l1/'
        ))

    if gold_tasks_pending > 0:
        recommendations.append((
            "MEDIUM",
            f"Có {gold_tasks_pending} task/batch Gold cần khởi động Subagent `gold_financial_analyst`.",
            f'Gọi Subagents Flash xử lý các batch trong data/agent_tasks/'
        ))

    if not any(r[0] == "HIGH" for r in recommendations):
        if l1_unrouted_count > 0:
            recommendations.append((
                "HIGH",
                f"Có {l1_unrouted_count} bài viết đã cào về nhưng chưa định tuyến L1.",
                f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/l1_route.py --from-db --date {target_date} --mini-batch 25'
            ))
        elif l1_resolved_pending > 0:
            recommendations.append((
                "HIGH",
                f"Có {l1_resolved_pending} bài L1 resolved đang chờ vật chất hóa Code-First.",
                f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/l1_ingest.py --code-first'
            ))
        elif gold_done_count > 0 and not any(glob.glob(str(USER_OUTPUT_DIR / "*" / f"{target_date}.xlsx"))):
            recommendations.append((
                "HIGH",
                "Đã có bài phân tích Gold nhưng chưa xuất bản Deliverable Excel cho người dùng.",
                f'& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/write_user_output.py --date {target_date}'
            ))
        elif not recommendations:
            recommendations.append((
                "INFO",
                "Toàn bộ chuỗi vận hành ngày này đã hoàn tất 100% sạch sẽ. Deliverable đã sẵn sàng.",
                "Không cần thao tác thêm. Hệ thống ở trạng thái ổn định."
            ))

    for priority, desc, cmd in recommendations:
        icon = "🔴" if priority == "HIGH" else ("🟡" if priority == "MEDIUM" else "🟢")
        print(f"   {icon} [{priority}] {desc}")
        print(f"      👉 Hành động: {cmd}")
    print(f"================================================================================\n")


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
