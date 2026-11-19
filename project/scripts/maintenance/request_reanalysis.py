"""Request a fresh analysis for articles that already passed the DoD.

The Article Lane selects only articles not yet analysed (ADR-0010), so a better contract, a
validator fix or a changed entity regime never reaches old articles by itself. This script
opens a re-analysis request per article and nothing else: the old outputs stay valid and
published, and the unattended `ops_daemon` picks the article up through its normal selector
(T4 backlog rule), so no manual wave is opened in parallel with the daemon.

A request closes by itself once both layers hold a passing output newer than the request. A
failing new output never replaces the older passing one while the request is open. The
script is not a retry tool for failed articles (see `requeue.py`, retired) and writes nothing
to the Gold layer; it archives the current outputs in `reanalysis_archive` first.

Selection: `--ids-csv FILE` (column `article_id`) and/or `--date-range FROM..TO`
(publication or capture date). The default is a dry run; add `--apply` to write.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.agent.article_contract import analyzed_l1_sql      # noqa: E402
from src.core.config import load_settings                    # noqa: E402
from src.core.models import now_vn_iso                       # noqa: E402
from src.core.stdio import force_utf8_stdio                  # noqa: E402
from src.db.store import ArticleStore                        # noqa: E402

force_utf8_stdio()


def ids_from_csv(path: Path, column: str) -> list[str]:
    """Read article ids from a CSV file.

    Args:
        path: CSV file with a header row.
        column: Name of the column that holds the article id.

    Returns:
        Article ids in file order, without blanks.

    Raises:
        SystemExit: When the column is missing.
    """
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if column not in (reader.fieldnames or []):
            raise SystemExit(f"CSV {path} không có cột `{column}`; cột hiện có: {reader.fieldnames}")
        return [r[column].strip() for r in reader if (r.get(column) or "").strip()]


def ids_from_range(store: ArticleStore, date_range: str) -> list[str]:
    """List analysed articles whose publication (or capture) date falls inside a range.

    Args:
        store: Article store.
        date_range: Inclusive `FROM..TO` in `YYYY-MM-DD`.

    Returns:
        Article ids that hold a passing output in both layers.
    """
    start, end = date_range.split("..", 1)
    conn = store._connect_ro()
    try:
        rows = conn.execute(
            "SELECT a.url_title_hash FROM articles a "
            "WHERE substr(COALESCE(NULLIF(a.published_at, ''), a.fetched_at), 1, 10) BETWEEN ? AND ? "
            f"AND EXISTS (SELECT 1 FROM l1_outputs o WHERE o.article_id = a.url_title_hash "
            f"AND {analyzed_l1_sql('o')}) "
            "AND EXISTS (SELECT 1 FROM agent_outputs g WHERE g.article_id = a.url_title_hash "
            "AND g.dod_pass = 1) ORDER BY a.url_title_hash", (start, end)).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def progress(store: ArticleStore, tag: str | None) -> list[dict]:
    """Report how many requests are closed or still open, per batch tag.

    Args:
        store: Article store.
        tag: Restrict to one batch tag, or None for all tags.

    Returns:
        One dict per tag with `total`, `closed` and `open`.
    """
    conn = store._connect_ro()
    try:
        try:
            rows = conn.execute(
                "SELECT r.batch_tag, count(*), sum(CASE WHEN "
                f"EXISTS (SELECT 1 FROM l1_outputs o WHERE o.article_id = r.article_id AND "
                f"{analyzed_l1_sql('o')} AND o.created_at >= r.requested_at) AND "
                "EXISTS (SELECT 1 FROM agent_outputs g WHERE g.article_id = r.article_id AND "
                "+g.dod_pass = 1 AND +g.created_at >= r.requested_at) THEN 1 ELSE 0 END) "  # see article_pack
                "FROM reanalysis_requests r "
                + ("WHERE r.batch_tag = ? " if tag else "") + "GROUP BY r.batch_tag",
                (tag,) if tag else ()).fetchall()
        except Exception:                                    # table not created yet
            return []
    finally:
        conn.close()
    return [{"batch_tag": t, "total": n, "closed": int(c or 0), "open": n - int(c or 0)}
            for t, n, c in rows]


def main(argv: list[str] | None = None) -> int:
    """Open re-analysis requests or report their progress.

    Args:
        argv: Command-line arguments; defaults to `sys.argv[1:]`.

    Returns:
        Process exit code: 0 on success, 2 on invalid arguments.
    """
    p = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    p.add_argument("--ids-csv", type=Path, help="CSV chứa danh sách bài cần phân tích lại")
    p.add_argument("--id-column", default="article_id")
    p.add_argument("--date-range", help="FROM..TO (YYYY-MM-DD..YYYY-MM-DD), gồm cả hai đầu")
    p.add_argument("--reason", help="Lý do phân tích lại, ghi vào sổ kiểm toán")
    p.add_argument("--batch-tag", help="Nhãn nhóm một quyết định, ví dụ us053-mismatch")
    p.add_argument("--apply", action="store_true", help="Thực sự ghi; mặc định chỉ đếm")
    p.add_argument("--status", action="store_true", help="Chỉ báo tiến độ các yêu cầu đang có")
    p.add_argument("--db-path", default=None)
    args = p.parse_args(argv)

    store = ArticleStore(args.db_path or load_settings()["database"]["path"])
    if args.status:
        for row in progress(store, args.batch_tag):
            print(f"{row['batch_tag']}: {row['closed']}/{row['total']} đã xong, {row['open']} còn chờ")
        return 0

    if not (args.ids_csv or args.date_range) or not args.reason or not args.batch_tag:
        print("Cần --reason, --batch-tag và ít nhất một trong --ids-csv, --date-range.")
        return 2
    ids: list[str] = []
    if args.ids_csv:
        ids += ids_from_csv(args.ids_csv, args.id_column)
    if args.date_range:
        ids += ids_from_range(store, args.date_range)
    ids = list(dict.fromkeys(ids))
    print(f"Chọn {len(ids)} bài (nhãn {args.batch_tag}).")
    if not args.apply:
        print("DRY-RUN: chưa ghi gì. Thêm --apply để mở yêu cầu phân tích lại.")
        return 0

    counts = store.request_reanalysis(ids, args.reason, args.batch_tag, now_vn_iso())
    from src.ops.config import resolve_paths                    # noqa: E402
    from src.ops.store import OpsStore                          # noqa: E402
    ops_paths = resolve_paths()
    reset = OpsStore(ops_paths.ops_db, log_dir=ops_paths.log_dir).reset_attempts(ids)
    print(f"Đã mở {counts['requested']} yêu cầu; đã mở sẵn {counts['already_open']}; "
          f"không có kết quả đạt DoD {counts['no_passing_output']}; đặt lại bộ đếm lượt {reset}.")
    print("Daemon sẽ xử lý theo luật tồn đọng T4; không mở đợt thủ công song song.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
