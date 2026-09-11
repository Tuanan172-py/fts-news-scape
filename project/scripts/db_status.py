"""Hiển thị bảng tổng hợp trạng thái hoạt động của hệ thống thu thập tin tức."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings          # noqa: E402
from src.core.models import VN_TZ                   # noqa: E402
from src.core.stdio import force_utf8_stdio        # noqa: E402

force_utf8_stdio()


def _rows(c, sql, params=()):
    try:
        return [dict(r) for r in c.execute(sql, params)]
    except sqlite3.OperationalError as e:
        return [{"_error": str(e)}]


def _print(title, rows, cols=None):
    print(f"\n=== {title} ===")
    if not rows:
        print("  (trống)")
        return
    if rows and "_error" in rows[0]:
        print(f"  [bảng chưa có / lỗi: {rows[0]['_error']}]")
        return
    cols = cols or list(rows[0].keys())
    print("  " + " | ".join(cols))
    for r in rows:
        print("  " + " | ".join(str(r.get(c, "")) for c in cols))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=load_settings().get("database", {}).get("path", "data/monocle.db"))
    ap.add_argument("--date", help="YYYY-MM-DD (mặc định: hôm nay giờ VN)")
    args = ap.parse_args(argv)
    day = args.date or f"{datetime.now(VN_TZ):%Y-%m-%d}"

    c = sqlite3.connect(args.db)
    c.row_factory = sqlite3.Row
    print(f"# DB STATUS — {args.db} — ngày {day} (giờ VN)")

    _print("1) Scraper heartbeat (nhịp tim)",
           _rows(c, "select scraper_name,last_run_ts,status,consecutive_failures cf,cycle_count cyc,"
                    "substr(coalesce(error_msg,''),1,40) err from scraper_heartbeat order by scraper_name"))

    _print(f"2) Sản lượng cycle gần nhất (metrics)",
           _rows(c, "select substr(ts,1,19) ts,scraper_name,articles_fetched fetched,articles_new new,errors "
                    "from scraper_metrics order by ts desc limit 8"))

    _print(f"3) Article thu hôm nay ({day}) theo domain",
           _rows(c, "select source_domain,count(*) n,substr(max(fetched_at),1,19) last_fetch "
                    "from articles where fetched_at>=? group by source_domain order by n desc", (day,)))

    _print("4) Watermark Bronze→Silver + lock scheduler",
           _rows(c, "select key,substr(value,1,25) value,substr(updated_at,1,19) updated_at from pipeline_state "
                    "where key in ('silver_watermark','silver_checkpoint','lock:scheduler')"))

    # 5) Độ trễ capture↔derive: max fetched (articles) vs watermark silver
    wm = _rows(c, "select value from pipeline_state where key='silver_watermark'")
    wm_val = wm[0]["value"] if wm and "value" in wm[0] else "—"
    _print(f"5) Độ trễ capture↔derive (watermark silver = {wm_val})",
           _rows(c, "select source_domain, substr(max(fetched_at),1,19) last_article, "
                    "case when max(fetched_at) > ? then 'CHỜ DERIVE' else 'đã silver' end trang_thai "
                    "from articles group by source_domain order by source_domain", (wm_val,)))

    _print(f"6) Change-detection hôm nay ({day}) — chú ý SELECTOR_BROKEN/TEMPLATE_DRIFT",
           _rows(c, "select source_domain,state,count(*) n from article_versions where captured_at>=? "
                    "group by source_domain,state order by source_domain,state", (day,)))

    _print("7) Hàng đợi handoff — work_items theo status",
           _rows(c, "select status,count(*) n from work_items group by status order by n desc"))

    _print("8) Lớp L1 (nhận diện entity) — l1_tasks & l1_outputs (theo provider)",
           _rows(c, "select 'l1_tasks' bang, '-' provider, '-' model, status trang_thai, count(*) n from l1_tasks group by status "
                    "union all select 'l1_outputs', coalesce(agent_provider, 'unknown'), coalesce(model_used, 'unknown'), ('dod_pass='||dod_pass), count(*) from l1_outputs group by agent_provider, model_used, dod_pass"))

    _print("9) Lớp bóc tách — agent_outputs (theo provider & DoD)",
           _rows(c, "select coalesce(agent_provider, 'unknown') provider, coalesce(model_used, 'unknown') model, ('dod_pass='||dod_pass) trang_thai, count(*) n from agent_outputs group by agent_provider, model_used, dod_pass"))

    c.close()
    print("\n(gợi ý) tin mới chưa lên Silver → chạy: python -m src.morninger --once derive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
