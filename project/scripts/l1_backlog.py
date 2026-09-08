"""
l1_backlog.py — Kiểm kê TỒN ĐỌNG toàn pipeline + in kế hoạch rút backlog theo mức "lời".

CHỈ ĐỌC. Không sửa DB, không phát packet, không gọi agent.

Trả lời đúng 1 câu hỏi: *còn bao nhiêu việc, và nên làm cái nào trước để ra hàng nhanh nhất?*

Xếp hạng ưu tiên (cao → thấp):
  T1 gold-ready  — có trong `articles`, Gold đã đạt DoD, THIẾU L1.
                   Gold đã trả tiền rồi mà không giao được (định tuyến cần entity của L1).
                   Chạy L1 xong là vào thẳng final.csv, gold_status=GOLD. Tốn 0 token Gold.
  T2 l1-only     — có trong `articles`, chưa L1 chưa Gold.
                   Chạy L1 xong ra final.csv dạng L1_ONLY (thiếu summary/key_points),
                   đồng thời MỞ KHOÁ cho agent_export (mặc định --require-l1) bốc Gold.
  T3 gold-next   — có trong `articles`, ĐÃ có L1, work_item còn pending.
                   Sẵn sàng cho Gold ngay; đây là nơi token Gold sinh lời chắc chắn.
  T4 orphan      — có work_item/l1_task nhưng KHÔNG có dòng nào trong `articles`.
                   Gate export là `articles ⨝ l1_outputs` nên nhóm này VĨNH VIỄN không ra
                   được final.csv. Chạy agent cho chúng là phí. Cần sửa Bronze/Silver.

Usage:
    python scripts/l1_backlog.py
    python scripts/l1_backlog.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings              # noqa: E402
from src.core.stdio import force_utf8_stdio            # noqa: E402
from src.db.store import ArticleStore                  # noqa: E402

force_utf8_stdio()

# Điều kiện dùng lại nhiều lần — giữ 1 chỗ để không lệch định nghĩa giữa các truy vấn.
_NO_L1 = ("NOT EXISTS (SELECT 1 FROM l1_outputs l1 "
          "WHERE l1.article_id = a.url_title_hash AND l1.dod_pass = 1)")
_HAS_L1 = ("EXISTS (SELECT 1 FROM l1_outputs l1 "
           "WHERE l1.article_id = a.url_title_hash AND l1.dod_pass = 1)")
_NO_GOLD = ("NOT EXISTS (SELECT 1 FROM agent_outputs ag "
            "WHERE ag.article_id = a.url_title_hash AND ag.dod_pass = 1)")
_HAS_GOLD = ("EXISTS (SELECT 1 FROM agent_outputs ag "
             "WHERE ag.article_id = a.url_title_hash AND ag.dod_pass = 1)")

QUERIES: dict[str, str] = {
    # -- đã qua gate export ----------------------------------------------------
    "delivered_gold": f"SELECT COUNT(*) FROM articles a WHERE {_HAS_L1} AND {_HAS_GOLD}",
    "delivered_l1_only": f"SELECT COUNT(*) FROM articles a WHERE {_HAS_L1} AND {_NO_GOLD}",

    # -- T1..T3: việc còn tồn, còn cứu được ------------------------------------
    "t1_gold_ready": f"SELECT COUNT(*) FROM articles a WHERE {_NO_L1} AND {_HAS_GOLD}",
    "t2_l1_only": f"SELECT COUNT(*) FROM articles a WHERE {_NO_L1} AND {_NO_GOLD}",
    "t2_has_packet": f"""SELECT COUNT(*) FROM articles a
        JOIN l1_tasks t ON t.article_id = a.url_title_hash AND t.status = 'pending'
        WHERE {_NO_L1} AND {_NO_GOLD}""",
    "t3_gold_next": f"""SELECT COUNT(DISTINCT a.url_title_hash) FROM articles a
        JOIN work_items w ON w.article_id = a.url_title_hash AND w.status = 'pending'
        WHERE {_HAS_L1} AND {_NO_GOLD}""",

    # -- T4: rò rỉ — đã tốn công agent nhưng không bao giờ giao được ------------
    "t4_l1task_orphan": """SELECT COUNT(*) FROM l1_tasks t WHERE NOT EXISTS
        (SELECT 1 FROM articles a WHERE a.url_title_hash = t.article_id)""",
    "t4_l1out_orphan": """SELECT COUNT(*) FROM l1_outputs l1 WHERE l1.dod_pass = 1 AND NOT EXISTS
        (SELECT 1 FROM articles a WHERE a.url_title_hash = l1.article_id)""",
    "t4_gold_orphan": """SELECT COUNT(DISTINCT ag.article_id) FROM agent_outputs ag
        WHERE ag.dod_pass = 1 AND NOT EXISTS
        (SELECT 1 FROM articles a WHERE a.url_title_hash = ag.article_id)""",

    # -- hàng đợi thô ----------------------------------------------------------
    "l1_tasks_pending": "SELECT COUNT(*) FROM l1_tasks WHERE status = 'pending'",
    "l1_tasks_failed": "SELECT COUNT(*) FROM l1_tasks WHERE status = 'failed'",
    "l1_out_dod_fail": "SELECT COUNT(*) FROM l1_outputs WHERE dod_pass = 0",
    "work_items_pending": "SELECT COUNT(*) FROM work_items WHERE status = 'pending'",
    "work_items_claimed": "SELECT COUNT(*) FROM work_items WHERE status = 'claimed'",
    "gold_out_dod_fail": "SELECT COUNT(*) FROM agent_outputs WHERE dod_pass = 0",
}


def collect(store) -> dict[str, int]:
    conn = store._connect_ro()
    try:
        return {k: conn.execute(q).fetchone()[0] for k, q in QUERIES.items()}
    finally:
        conn.close()


def count_packets(task_dir: Path, pattern: str) -> int:
    return len(list(task_dir.glob(pattern))) if task_dir.is_dir() else 0


def render(m: dict[str, int], packets: dict[str, int]) -> str:
    gate_now = m["delivered_gold"] + m["delivered_l1_only"]
    recoverable = m["t1_gold_ready"] + m["t2_l1_only"]
    L: list[str] = []
    add = L.append

    add("=" * 78)
    add("KIEM KE TON DONG — pipeline news-scape")
    add("=" * 78)
    add("")
    add(f"ĐÃ QUA GATE EXPORT (vào được final.csv): {gate_now}")
    add(f"   ├─ đầy đủ (gold_status=GOLD)      : {m['delivered_gold']}")
    add(f"   └─ thiếu Gold (L1_ONLY)           : {m['delivered_l1_only']}")
    add("")
    add("-" * 78)
    add("CÒN TỒN — xếp theo mức lời")
    add("-" * 78)
    add(f"T1  gold-ready  {m['t1_gold_ready']:>6}  Gold XONG, thiếu L1 -> chạy L1 = giao NGAY, đủ.")
    add("                        Tốn 0 token Gold. LÀM TRƯỚC.")
    add(f"T2  l1-only     {m['t2_l1_only']:>6}  chưa L1 chưa Gold -> L1 ra L1_ONLY + mở khoá Gold")
    add(f"                        (trong đó {m['t2_has_packet']} đã có packet L1 chờ sẵn)")
    add(f"T3  gold-next   {m['t3_gold_next']:>6}  ĐÃ có L1, work_item pending -> Gold bốc được ngay")
    add("")
    add("T4  orphan               KHÔNG có dòng trong `articles` => VĨNH VIỄN không ra final.csv")
    add(f"    ├─ l1_tasks        {m['t4_l1task_orphan']:>6}  (chạy L1 cho nhóm này là phí)")
    add(f"    ├─ l1_outputs xong {m['t4_l1out_orphan']:>6}  ĐÃ tốn công agent, vẫn không giao được")
    add(f"    └─ gold xong       {m['t4_gold_orphan']:>6}  ĐÃ tốn token Gold, vẫn không giao được")
    add("")
    add("-" * 78)
    add("HÀNG ĐỢI THÔ")
    add("-" * 78)
    add(f"l1_tasks   pending={m['l1_tasks_pending']:<6} failed={m['l1_tasks_failed']:<6} "
        f"l1_outputs dod_pass=0: {m['l1_out_dod_fail']}")
    add(f"work_items pending={m['work_items_pending']:<6} claimed={m['work_items_claimed']:<6} "
        f"agent_outputs dod_pass=0: {m['gold_out_dod_fail']}")
    add(f"packet trên đĩa: L1 lẻ={packets['l1_single']}  L1 lô={packets['l1_batch']}  "
        f"Gold lẻ={packets['gold_single']}  Gold lô={packets['gold_batch']}")
    add("")
    add("=" * 78)
    add(f"KẾ HOẠCH — cứu được ngay: {recoverable} bài (T1+T2)")
    add("=" * 78)
    add("")
    add(f"# BƯỚC 1 — T1 ({m['t1_gold_ready']} bài): lời nhất, 0 token Gold")
    add("python scripts/l1_route.py --only gold-ready --all --mini-batch 25")
    add("#   -> agent L1 xử lý data/agent_tasks/l1/l1_batch_XX.task.json")
    add("python scripts/l1_ingest.py data/agent_outputs_l1")
    add("python scripts/write_user_output.py --date all")
    add("")
    add(f"# BƯỚC 2 — T2 ({m['t2_l1_only']} bài): loại sẵn nhóm orphan T4")
    add("python scripts/l1_route.py --only in-articles --all --mini-batch 25")
    add("python scripts/l1_ingest.py data/agent_outputs_l1")
    add("")
    add(f"# BƯỚC 3 — T3 ({m['t3_gold_next']} bài): Gold, chỉ bốc bài đã có L1")
    add("python scripts/agent_export.py --limit 50 --mini-batch 10   # --require-l1 mặc định BẬT")
    add("#   -> agent Gold xử lý data/agent_tasks/batch_XX.task.json")
    add("python scripts/agent_ingest.py data/agent_outputs")
    add("python scripts/write_user_output.py --date all")
    add("")
    if m["t4_l1task_orphan"] or m["t4_gold_orphan"]:
        add("# T4 — KHÔNG chạy agent. Đây là lỗi ghi `articles` ở Bronze/Silver, phải sửa code.")
        add("#   Xem docs/SESSION-LATEST.md mục 'rò rỉ dữ liệu'.")
    return "\n".join(L)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Kiểm kê tồn đọng pipeline (chỉ đọc)")
    ap.add_argument("--json", action="store_true", help="Xuất JSON thay vì bảng")
    args = ap.parse_args(argv)

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    m = collect(ArticleStore(db_path=db_path))

    l1_dir, gold_dir = Path("data/agent_tasks/l1"), Path("data/agent_tasks")
    packets = {
        "l1_single": count_packets(l1_dir, "*.task.json") - count_packets(l1_dir, "l1_batch_*.task.json"),
        "l1_batch": count_packets(l1_dir, "l1_batch_*.task.json"),
        "gold_single": count_packets(gold_dir, "*.task.json") - count_packets(gold_dir, "batch_*.task.json"),
        "gold_batch": count_packets(gold_dir, "batch_*.task.json"),
    }

    if args.json:
        print(json.dumps({"metrics": m, "packets": packets}, ensure_ascii=False, indent=2))
    else:
        print(render(m, packets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
