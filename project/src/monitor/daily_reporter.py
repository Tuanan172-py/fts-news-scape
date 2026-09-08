"""
daily_reporter.py — Core Analytics Engine: Báo cáo giám sát toàn diện hệ thống theo mốc thời gian.

Tổng hợp Phễu Dữ liệu 5 Tầng (Data Conversion Funnel):
1. Bronze Raw (articles, scraper_heartbeat, scraper_metrics)
2. Silver & Drift (article_versions, silver_watermark, pipeline lag)
3. Work Packets (l1_tasks, work_items)
4. AI Agents Quality & DoD (l1_outputs, agent_outputs, dod_pass, models)
5. User Deliverables (users/output/<user>/<date>.csv, _master audit)

Thiết kế an toàn:
- Mở SQLite chế độ Read-Only (file:...mode=ro) với busy_timeout=30s.
- Hỗ trợ ngày cụ thể (YYYY-MM-DD), 'today', 'yesterday', hoặc khoảng ngày (--days N).
- Xuất định dạng Markdown báo cáo quản trị và in tóm tắt Terminal.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.config import load_settings
from src.core.models import VN_TZ
from src.core.staging import safe_atomic_write


def resolve_date_range(date_str: str | None = None, days: int = 0) -> tuple[str, str, list[str]]:
    """Phân giải tham số ngày thành (start_date, end_date, list_dates)."""
    now = datetime.now(VN_TZ)
    if not date_str or date_str == "today":
        target = now.strftime("%Y-%m-%d")
    elif date_str == "yesterday":
        target = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_str == "all":
        return "", "", []
    else:
        target = date_str[:10]

    if days > 1:
        start_dt = datetime.strptime(target, "%Y-%m-%d").replace(tzinfo=VN_TZ) - timedelta(days=days - 1)
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = target
        date_list = [
            (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(days)
        ]
        return start_date, end_date, date_list

    return target, target, [target]


class DailyReporter:
    def __init__(self, db_path: str | None = None, users_output_dir: str | Path | None = None):
        settings = load_settings()
        self.db_path = db_path or settings.get("database", {}).get("path", "data/monocle.db")
        if users_output_dir:
            self.users_output_dir = Path(users_output_dir)
        else:
            # Tìm users/output: ưu tiên repo root ../users/output, fallback users/output
            p1 = Path(__file__).resolve().parent.parent.parent.parent / "users" / "output"
            p2 = Path("users/output")
            self.users_output_dir = p1 if p1.exists() else p2

    def _connect_ro(self) -> sqlite3.Connection:
        """Kết nối DB chế độ Read-Only an toàn, không tranh chấp lock."""
        resolved = Path(self.db_path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")
        uri_path = f"file:{resolved.as_posix()}?mode=ro"
        con = sqlite3.connect(uri_path, uri=True, timeout=30.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            with self._connect_ro() as con:
                return [dict(r) for r in con.execute(sql, params)]
        except sqlite3.OperationalError as e:
            logger.debug(f"Query skipped or table missing: {e}")
            return []

    def collect_metrics(self, date_str: str | None = "today", days: int = 0) -> dict[str, Any]:
        """Thu thập đầy đủ số liệu 5 tầng cho ngày hoặc khoảng ngày chỉ định."""
        start_date, end_date, date_list = resolve_date_range(date_str, days)
        is_range = len(date_list) > 1
        filter_label = f"{start_date} -> {end_date}" if is_range else (start_date or "Toàn bộ lịch sử")

        # 1. Tầng Bronze: Thu thập & Raw
        if start_date and end_date:
            articles_by_domain = self._query(
                """
                SELECT source_domain, count(*) as count,
                       min(fetched_at) as first_fetch, max(fetched_at) as last_fetch
                FROM articles
                WHERE substr(fetched_at, 1, 10) >= ? AND substr(fetched_at, 1, 10) <= ?
                GROUP BY source_domain
                ORDER BY count DESC
                """,
                (start_date, end_date),
            )
            raw_total = sum(r["count"] for r in articles_by_domain)
        else:
            articles_by_domain = self._query(
                """
                SELECT source_domain, count(*) as count,
                       min(fetched_at) as first_fetch, max(fetched_at) as last_fetch
                FROM articles
                GROUP BY source_domain
                ORDER BY count DESC
                """
            )
            raw_total = sum(r["count"] for r in articles_by_domain)

        # Scraper heartbeat & metrics
        heartbeats = self._query(
            """
            SELECT scraper_name, status, last_run_ts, consecutive_failures, cycle_count,
                   substr(coalesce(error_msg, ''), 1, 50) as error_snippet
            FROM scraper_heartbeat
            ORDER BY scraper_name
            """
        )

        metrics_recent = self._query(
            """
            SELECT scraper_name, sum(articles_fetched) as total_fetched,
                   sum(articles_new) as total_new, sum(errors) as total_errors
            FROM scraper_metrics
            WHERE substr(ts, 1, 10) >= ? AND substr(ts, 1, 10) <= ?
            GROUP BY scraper_name
            """,
            (start_date or "1970-01-01", end_date or "9999-12-31"),
        )

        # 2. Tầng Silver & Change Detection
        if start_date and end_date:
            versions_stats = self._query(
                """
                SELECT source_domain, state, count(*) as count
                FROM article_versions
                WHERE substr(captured_at, 1, 10) >= ? AND substr(captured_at, 1, 10) <= ?
                GROUP BY source_domain, state
                ORDER BY source_domain, count DESC
                """,
                (start_date, end_date),
            )
        else:
            versions_stats = self._query(
                """
                SELECT source_domain, state, count(*) as count
                FROM article_versions
                GROUP BY source_domain, state
                ORDER BY source_domain, count DESC
                """
            )

        silver_states: dict[str, int] = {}
        for row in versions_stats:
            silver_states[row["state"]] = silver_states.get(row["state"], 0) + row["count"]

        # Watermark & Pipeline Lag
        watermark_row = self._query("SELECT value FROM pipeline_state WHERE key='silver_watermark'")
        silver_watermark = watermark_row[0]["value"] if watermark_row else "—"

        checkpoint_row = self._query("SELECT value FROM pipeline_state WHERE key='silver_checkpoint'")
        silver_checkpoint = checkpoint_row[0]["value"] if checkpoint_row else "—"

        lag_rows = self._query(
            """
            SELECT source_domain, max(fetched_at) as last_article,
                   CASE WHEN max(fetched_at) > ? THEN 'CHỜ DERIVE' ELSE 'đã silver' END as lag_status
            FROM articles
            GROUP BY source_domain
            ORDER BY source_domain
            """,
            (silver_watermark,),
        )

        # 3. Tầng Work Packets (Hàng đợi tác vụ)
        if start_date and end_date:
            l1_tasks_summary = self._query(
                """
                SELECT status, route, count(*) as count
                FROM l1_tasks
                WHERE substr(enqueued_at, 1, 10) >= ? AND substr(enqueued_at, 1, 10) <= ?
                GROUP BY status, route
                """,
                (start_date, end_date),
            )
            gold_items_summary = self._query(
                """
                SELECT status, count(*) as count
                FROM work_items
                WHERE substr(enqueued_at, 1, 10) >= ? AND substr(enqueued_at, 1, 10) <= ?
                GROUP BY status
                """,
                (start_date, end_date),
            )
        else:
            l1_tasks_summary = self._query(
                "SELECT status, route, count(*) as count FROM l1_tasks GROUP BY status, route"
            )
            gold_items_summary = self._query(
                "SELECT status, count(*) as count FROM work_items GROUP BY status"
            )

        l1_tasks_total = sum(r["count"] for r in l1_tasks_summary)
        gold_items_total = sum(r["count"] for r in gold_items_summary)

        # 4. Tầng AI Agents Review & DoD Quality
        if start_date and end_date:
            l1_outputs_summary = self._query(
                """
                SELECT agent_provider, model_used, dod_pass, count(*) as count
                FROM l1_outputs
                WHERE substr(created_at, 1, 10) >= ? AND substr(created_at, 1, 10) <= ?
                GROUP BY agent_provider, model_used, dod_pass
                """,
                (start_date, end_date),
            )
            gold_outputs_summary = self._query(
                """
                SELECT agent_provider, model_used, dod_pass, count(*) as count
                FROM agent_outputs
                WHERE substr(created_at, 1, 10) >= ? AND substr(created_at, 1, 10) <= ?
                GROUP BY agent_provider, model_used, dod_pass
                """,
                (start_date, end_date),
            )
        else:
            l1_outputs_summary = self._query(
                """
                SELECT agent_provider, model_used, dod_pass, count(*) as count
                FROM l1_outputs
                GROUP BY agent_provider, model_used, dod_pass
                """
            )
            gold_outputs_summary = self._query(
                """
                SELECT agent_provider, model_used, dod_pass, count(*) as count
                FROM agent_outputs
                GROUP BY agent_provider, model_used, dod_pass
                """
            )

        l1_passed = sum(r["count"] for r in l1_outputs_summary if r["dod_pass"] == 1)
        l1_failed = sum(r["count"] for r in l1_outputs_summary if r["dod_pass"] == 0)
        gold_passed = sum(r["count"] for r in gold_outputs_summary if r["dod_pass"] == 1)
        gold_failed = sum(r["count"] for r in gold_outputs_summary if r["dod_pass"] == 0)

        # 5. Tầng User Deliverables (Bàn giao người dùng cuối)
        user_files: list[dict] = []
        user_delivered_total = 0
        if self.users_output_dir.exists():
            target_dates = set(date_list) if date_list else None
            for user_folder in sorted(self.users_output_dir.iterdir()):
                if user_folder.is_dir() and not user_folder.name.startswith("."):
                    for csv_file in sorted(user_folder.glob("*.csv")):
                        # csv_file name is YYYY-MM-DD.csv hoặc YYYY-MM-DD_L1.csv
                        stem_date = csv_file.stem.split("_")[0]
                        if target_dates and stem_date not in target_dates:
                            continue
                        try:
                            with csv_file.open(encoding="utf-8-sig") as f:
                                reader = csv.reader(f)
                                header = next(reader, None)
                                row_count = sum(1 for _ in reader)
                        except Exception:
                            row_count = 0
                        user_files.append({
                            "user": user_folder.name,
                            "date": stem_date,
                            "file_name": csv_file.name,
                            "relative_path": str(csv_file.relative_to(self.users_output_dir.parent)),
                            "row_count": row_count,
                            "size_bytes": csv_file.stat().st_size,
                        })
                        if user_folder.name != "_master" and "_" not in csv_file.stem:
                            user_delivered_total += row_count

        return {
            "query_time": datetime.now(VN_TZ).isoformat(timespec="seconds"),
            "filter_label": filter_label,
            "start_date": start_date,
            "end_date": end_date,
            "is_range": is_range,
            "funnel": {
                "bronze_raw_total": raw_total,
                "silver_processed_total": sum(v for k, v in silver_states.items() if k != "UNCHANGED"),
                "silver_new": silver_states.get("NEW", 0),
                "silver_unchanged": silver_states.get("UNCHANGED", 0),
                "l1_tasks_total": l1_tasks_total,
                "l1_passed": l1_passed,
                "l1_failed": l1_failed,
                "gold_items_total": gold_items_total,
                "gold_passed": gold_passed,
                "gold_failed": gold_failed,
                "user_delivered_rows": user_delivered_total,
            },
            "bronze": {
                "by_domain": articles_by_domain,
                "heartbeats": heartbeats,
                "metrics_recent": metrics_recent,
            },
            "silver": {
                "states": silver_states,
                "versions_stats": versions_stats,
                "watermark": silver_watermark,
                "checkpoint": silver_checkpoint,
                "lag_rows": lag_rows,
            },
            "packets": {
                "l1_summary": l1_tasks_summary,
                "gold_summary": gold_items_summary,
            },
            "agents": {
                "l1_outputs": l1_outputs_summary,
                "gold_outputs": gold_outputs_summary,
            },
            "deliverables": {
                "user_files": user_files,
                "total_rows": user_delivered_total,
            },
        }

    def generate_markdown(self, m: dict[str, Any]) -> str:
        """Tạo báo cáo Markdown chuẩn hóa, trực quan."""
        fn = m["funnel"]
        q_time = m["query_time"]
        label = m["filter_label"]

        # Tính tỷ lệ phần trăm an toàn
        raw_cnt = fn["bronze_raw_total"] or 1
        l1_pass_rate = (fn["l1_passed"] / (fn["l1_passed"] + fn["l1_failed"]) * 100) if (fn["l1_passed"] + fn["l1_failed"]) > 0 else 0
        gold_pass_rate = (fn["gold_passed"] / (fn["gold_passed"] + fn["gold_failed"]) * 100) if (fn["gold_passed"] + fn["gold_failed"]) > 0 else 0

        # Kiểm tra cảnh báo rủi ro
        alerts: list[str] = []
        broken_cnt = m["silver"]["states"].get("SELECTOR_BROKEN", 0)
        drift_cnt = m["silver"]["states"].get("TEMPLATE_DRIFT", 0)
        if broken_cnt > 0:
            alerts.append(f"🔴 **SELECTOR_BROKEN:** Phát hiện {broken_cnt} bài lỗi cấu trúc trích xuất. Cần kiểm tra selector.")
        if drift_cnt > 0:
            alerts.append(f"🟡 **TEMPLATE_DRIFT:** Phát hiện {drift_cnt} bài có dấu hiệu thay đổi giao diện HTML.")
        for hb in m["bronze"]["heartbeats"]:
            if hb.get("consecutive_failures", 0) > 0 or hb.get("status") == "failed":
                alerts.append(f"🔴 **Scraper lỗi:** `{hb['scraper_name']}` trạng thái `{hb['status']}` (thất bại liên tiếp: {hb.get('consecutive_failures')}).")

        alert_section = "\n".join(f"- {a}" for a in alerts) if alerts else "- 🟢 Toàn bộ crawler và hệ thống hoạt động ổn định, không phát hiện lỗi bất thường."

        # Bảng Domain Bronze
        domain_rows = []
        for d in m["bronze"]["by_domain"]:
            domain_rows.append(f"| `{d['source_domain']}` | {d['count']} | {d.get('first_fetch', '')[11:19]} | {d.get('last_fetch', '')[11:19]} |")
        domain_table = "\n".join(domain_rows) if domain_rows else "| — | 0 | — | — |"

        # Bảng Scraper Heartbeat
        hb_rows = []
        for h in m["bronze"]["heartbeats"]:
            status_icon = "🟢" if h["status"] == "ok" else ("🟡" if h["status"] == "running" else "🔴")
            hb_rows.append(f"| `{h['scraper_name']}` | {status_icon} `{h['status']}` | {h['cycle_count']} | {h['consecutive_failures']} | {h.get('last_run_ts', '')[11:19]} | {h.get('error_snippet', '')} |")
        hb_table = "\n".join(hb_rows) if hb_rows else "| — | — | — | — | — | — |"

        # Bảng User Deliverables
        deliv_rows = []
        for uf in m["deliverables"]["user_files"]:
            deliv_rows.append(f"| **{uf['user']}** | `{uf['file_name']}` | {uf['row_count']} dòng | {uf['size_bytes'] / 1024:.1f} KB |")
        deliv_table = "\n".join(deliv_rows) if deliv_rows else "| — | Không có file bàn giao | 0 | 0 |"

        # Bảng Models & DoD
        model_rows = []
        for l1 in m["agents"]["l1_outputs"]:
            model_rows.append(f"| L1 Matcher | `{l1['agent_provider']}` | `{l1['model_used']}` | `dod_pass={l1['dod_pass']}` | {l1['count']} |")
        for g in m["agents"]["gold_outputs"]:
            model_rows.append(f"| Gold Analyst | `{g['agent_provider']}` | `{g['model_used']}` | `dod_pass={g['dod_pass']}` | {g['count']} |")
        model_table = "\n".join(model_rows) if model_rows else "| — | — | — | — | 0 |"

        md = f"""# 🛡️ BÁO CÁO GIÁM SÁT TOÀN DIỆN HỆ THỐNG NEWS-SCAPE
**Thời gian lập báo cáo:** {q_time} (Giờ VN)
**Kỳ phân tích:** `{label}`

---

## 1. PHỄU CHUYỂN ĐỔI DỮ LIỆU TOÀN TRÌNH (PIPELINE FUNNEL)

| Tầng Dữ Liệu | Số lượng Thực Tế | Tỷ Lệ Chuyển Đổi | Trạng Thái Giám Sát |
| :--- | :---: | :---: | :--- |
| **1. Tin Raw về (Bronze)** | **{fn['bronze_raw_total']} bài** | 100% | Thu thập từ các domain kích hoạt |
| **2. Tin tinh chế (Silver NEW)** | **{fn['silver_new']} bài** | {fn['silver_new'] / raw_cnt * 100:.1f}% | Đã lọc khối thẻ `<p>`, loại trùng lặp |
| **3. L1 Work Tasks phát ra** | **{fn['l1_tasks_total']} tasks** | — | Tạo packet cho L1 Entity Matcher |
| **4. L1 Hoàn thành DoD Pass** | **{fn['l1_passed']} bài** | Pass: **{l1_pass_rate:.1f}%** | L1 DoD Pass Rate (`dod_pass=1`) |
| **5. Gold Work Items phát ra** | **{fn['gold_items_total']} items** | — | Tạo packet cho Gold Deep Analyst |
| **6. Gold Hoàn tất DoD Pass** | **{fn['gold_passed']} bài** | Pass: **{gold_pass_rate:.1f}%** | Gold DoD Pass Rate (`dod_pass=1`) |
| **7. Tin giao nộp User (Deliverables)** | **{fn['user_delivered_rows']} dòng** | — | Xuất vào `users/output/<user>/<date>.csv` |

---

## 2. CẢNH BÁO RỦI RO & BẤT THƯỜNG (RED FLAGS)
{alert_section}

---

## 3. CHI TIẾT TẦNG CRAWLER & SCRIPTS THU THẬP
### 3.1. Sản lượng tin theo Domain
| Domain Nguồn | Số Tin Thu Thập | Bản tin đầu ngày | Bản tin cuối ngày |
| :--- | :---: | :---: | :---: |
{domain_table}

### 3.2. Nhịp tim & Tình trạng Scraper (Heartbeats)
| Scraper | Trạng Thái | Số Cycles | Thất Bại Liên Tiếp | Lần Chạy Cuối | Lỗi Ghi Nhận |
| :--- | :---: | :---: | :---: | :---: | :--- |
{hb_table}

---

## 4. TIẾN ĐỘ TINH CHẾ SILVER & ĐỘ TRỄ PIPELINE
- **Silver Watermark:** `{m['silver']['watermark']}`
- **Silver Checkpoint:** `{m['silver']['checkpoint']}`
- **Phân loại Change-Detection:**
  - `NEW`: {m['silver']['states'].get('NEW', 0)} bài
  - `UNCHANGED`: {m['silver']['states'].get('UNCHANGED', 0)} bài
  - `CONTENT_CHANGED`: {m['silver']['states'].get('CONTENT_CHANGED', 0)} bài
  - `TEMPLATE_DRIFT`: {drift_cnt} bài
  - `SELECTOR_BROKEN`: {broken_cnt} bài

---

## 5. NĂNG LỰC & CHẤT LƯỢNG AI AGENTS (DoD QUALITY)
| Tầng Phân Tích | Provider | Model Sử Dụng | Tiêu Chuẩn DoD | Số Lượng Bài |
| :--- | :--- | :--- | :---: | :---: |
{model_table}

---

## 6. TÌNH TRẠNG BÀN GIAO NGƯỜI DÙNG CUỐI (USER DELIVERABLES)
| Đối tượng Nhận Tin | Tên File Bàn Giao | Số Dòng Tin | Kích Thước File |
| :--- | :--- | :---: | :---: |
{deliv_table}
"""
        return md

    def save_report_markdown(self, m: dict[str, Any], out_dir: str | Path = "reports/daily") -> Path:
        """Lưu báo cáo ra file Markdown vĩnh viễn an toàn với Staging."""
        target_dir = Path(out_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        if m["is_range"]:
            filename = f"report-{m['start_date']}_to_{m['end_date']}.md"
        else:
            filename = f"report-{m['start_date'] or 'all'}.md"

        target_file = target_dir / filename
        content = self.generate_markdown(m)
        safe_atomic_write(target_file, content, encoding="utf-8")
        logger.info(f"Đã lưu báo cáo giám sát tại: {target_file}")
        return target_file

    def print_terminal_summary(self, m: dict[str, Any]) -> None:
        """In tóm tắt trực quan ra màn hình Console."""
        fn = m["funnel"]
        print("\n" + "=" * 70)
        print(f"  NEWS-SCAPE MONITOR DASHBOARD — {m['filter_label']}")
        print("=" * 70)
        print(f"  [1] Tin Raw về (Bronze)     : {fn['bronze_raw_total']:>5} bài")
        print(f"  [2] Tin Tinh chế (Silver NEW): {fn['silver_new']:>5} bài (UNCHANGED: {fn['silver_unchanged']})")
        print(f"  [3] L1 Tasks phát ra         : {fn['l1_tasks_total']:>5} tasks (Pass DoD: {fn['l1_passed']}, Fail: {fn['l1_failed']})")
        print(f"  [4] Gold Items phát ra       : {fn['gold_items_total']:>5} items (Pass DoD: {fn['gold_passed']}, Fail: {fn['gold_failed']})")
        print(f"  [5] Bàn giao User cuối       : {fn['user_delivered_rows']:>5} dòng (final.csv)")
        print("-" * 70)

        # Scrapers
        print("  SỨC KHỎE CRAWLER SCRAPERS:")
        for hb in m["bronze"]["heartbeats"]:
            status_symbol = "OK" if hb["status"] == "ok" else hb["status"].upper()
            print(f"    - {hb['scraper_name']:<12}: status={status_symbol:<7} cyc={hb['cycle_count']:<3} cf={hb['consecutive_failures']:<2} last={hb.get('last_run_ts', '')[11:19]}")

        # Deliverables
        print("-" * 70)
        print("  BÀN GIAO FILE NGƯỜI DÙNG (users/output/):")
        for uf in m["deliverables"]["user_files"]:
            print(f"    - {uf['user']:<10} -> {uf['file_name']:<16} ({uf['row_count']:>3} dòng, {uf['size_bytes'] / 1024:.1f} KB)")
        print("=" * 70 + "\n")
