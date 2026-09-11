"""Định tuyến và phát gói công việc nhận diện thực thể L1."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.l1_runner import L1Runner              # noqa: E402
from src.core.config import load_settings             # noqa: E402
from src.core.stdio import force_utf8_stdio           # noqa: E402
from src.db.store import ArticleStore                 # noqa: E402

force_utf8_stdio()


def _iter_sources(source: str, reverse: bool = True):
    """Liệt kê danh sách tệp nguồn theo thời gian sửa đổi gần nhất.

    Args:
        source: Thư mục gốc chứa các gói công việc.
        reverse: Có sắp xếp thời gian giảm dần hay không. Mặc định True.

    Returns:
        Danh sách đường dẫn tệp JSON đã sắp xếp.
    """
    pats = [os.path.join(source, "*", "*", "*.json")]
    files = [f for p in pats for f in glob.glob(p)]
    if not files and source != "data/silver":
        files = glob.glob(os.path.join("data/silver", "*", "*", "*.json"))

    def _mtime(f: str) -> float:
        try:
            return os.path.getmtime(f)
        except OSError:
            return 0.0

    return sorted(files, key=_mtime, reverse=reverse)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/work_packages")
    ap.add_argument("--review", choices=["all", "missed"], default="missed",
                    help="missed: chỉ phát packet cho tin code-first KHÔNG khớp (needs_agent, mặc định); all: phát cho mọi tin")
    ap.add_argument("--batch-size", "-b", type=int, default=None, help="Kích thước block/lô việc cần xuất (mặc định 50)")
    ap.add_argument("--limit", "-n", type=int, default=None, help="Tối đa N việc")
    ap.add_argument("--order", choices=["desc", "asc"], default="desc", help="Thứ tự: desc (mới nhất trước), asc (cũ nhất trước)")
    ap.add_argument("--all", "-a", action="store_true", help="Xuất toàn bộ bài chưa hoàn thành")
    ap.add_argument("--no-skip-done", action="store_true", help="Không bỏ qua các bài đã có status=done")
    ap.add_argument("--only", choices=["all", "gold-ready", "in-articles"], default="all",
                    help="gold-ready: CHỈ bài đã có agent_outputs.dod_pass=1 nhưng thiếu L1 "
                         "— xong L1 là giao được NGAY, đầy đủ (ưu tiên #1). "
                         "in-articles: bài có mặt trong bảng `articles` — loại nhóm work-package "
                         "mồ côi (không có dòng `articles` ⇒ vĩnh viễn không vào final.csv)")
    ap.add_argument("--mini-batch", "-m", type=int, default=None,
                    help="Gom lô thành l1_batch_XX.task.json (khuyến nghị 25). Packet L1 chỉ có "
                         "tiêu đề nên lô lớn hơn Gold được; giảm ~96%% số tool call của agent")
    args = ap.parse_args(argv)

    if args.all:
        limit = None
    elif args.limit is not None:
        limit = args.limit
    elif args.batch_size is not None:
        limit = args.batch_size
    else:
        limit = 50

    db_path = load_settings().get("database", {}).get("path", "data/monocle.db")
    store = ArticleStore(db_path=db_path)
    runner = L1Runner(store)

    done_aids: set[str] = set()
    if not args.no_skip_done:
        conn = store.connect()
        try:
            rows = conn.execute("SELECT article_id FROM l1_tasks WHERE status = 'done'").fetchall()
            done_aids = {r["article_id"] for r in rows}
        finally:
            conn.close()

    # --only: thu hẹp phạm vi theo mức "lời" khi rút backlog.
    #   gold-ready  = Gold đã xong nhưng thiếu L1 → công Gold đang nằm không, xong L1 là giao ngay.
    #   in-articles = có dòng trong `articles` → loại work-package mồ côi (không có `articles`
    #                 thì gate `articles ⨝ l1_outputs` không bao giờ chạm tới, chạy L1 là phí).
    _ONLY_SQL = {
        "gold-ready": """
            SELECT DISTINCT a.url_title_hash AS article_id
            FROM articles a
            JOIN agent_outputs ag ON ag.article_id = a.url_title_hash AND ag.dod_pass = 1
            WHERE NOT EXISTS (SELECT 1 FROM l1_outputs l1
                              WHERE l1.article_id = a.url_title_hash AND l1.dod_pass = 1)
        """,
        "in-articles": """
            SELECT a.url_title_hash AS article_id
            FROM articles a
            WHERE NOT EXISTS (SELECT 1 FROM l1_outputs l1
                              WHERE l1.article_id = a.url_title_hash AND l1.dod_pass = 1)
        """,
    }
    only_aids: set[str] | None = None
    if args.only in _ONLY_SQL:
        conn = store.connect()
        try:
            only_aids = {r["article_id"] for r in conn.execute(_ONLY_SQL[args.only])}
        finally:
            conn.close()
        print(f"[only={args.only}] {len(only_aids)} bài lọt bộ lọc")

    n = 0
    route_ctr, rel_ctr = Counter(), Counter()
    seen: set[str] = set()
    exported_tasks: list[dict] = []
    for f in _iter_sources(args.source, reverse=(args.order == "desc")):
        if limit is not None and n >= limit:
            break
        try:
            art = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        aid = art.get("article_id")
        if not aid or aid in seen or aid in done_aids:
            continue
        if only_aids is not None and aid not in only_aids:
            continue
        seen.add(aid)
        rec = runner.route_and_export(art, review=args.review)
        n += 1
        route_ctr[rec["route"]] += 1
        rel_ctr[rec["relevance"]] += 1
        if rec.get("packet_path"):
            exported_tasks.append({
                "article_id": aid,
                "title": rec.get("title") or art.get("title", ""),
                "domain": art.get("domain", ""),
                "time": art.get("published_at") or art.get("fetch_ts") or art.get("captured_at") or "",
                "path": rec["packet_path"],
                # code_first đi kèm để packet gom lô giữ được nhiệm vụ TRA SOÁT
                "code_first": {
                    "route": rec.get("route"),
                    "relevance": rec.get("relevance"),
                    "entity_ids": rec.get("entity_ids", []),
                    "industries": rec.get("industries", []),
                },
            })

    print(f"== L1 route {n} tin (review={args.review}, order={args.order}, skipped_done={len(done_aids)}) ==")
    print(f"resolved (code-first khớp): {route_ctr['resolved']}")
    print(f"needs_agent (code không khớp): {route_ctr['needs_agent']}")
    print("relevance:", dict(rel_ctr))
    print(f"packets  -> data/agent_tasks/l1/<article_id>.task.json")
    print(f"trạng thái + code-first  -> DB l1_tasks (chờ agent tra soát → l1_ingest.py)")

    if exported_tasks:
        from src.agent.manifest import create_batch_manifest, print_batch_summary_table
        manifest = create_batch_manifest(exported_tasks, runner.task_dir, batch_type="l1", order=args.order)
        print_batch_summary_table(manifest)
        if args.mini_batch and args.mini_batch > 0:
            from src.agent.batch_handoff import split_l1_tasks_into_batches
            batches = split_l1_tasks_into_batches(
                exported_tasks, batch_size=args.mini_batch, base_dir=runner.task_dir)
            print(f"📦 Đã đóng gói {len(batches)} mini-batch L1 (size={args.mini_batch}) "
                  f"→ {runner.task_dir}/l1_batch_XX.task.json")
            print(f"   Agent đọc l1_batch_XX.task.json, ghi 1 mảng JSON vào "
                  f"data/agent_outputs_l1/l1_batch_XX.output.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
