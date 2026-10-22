"""Pack articles into worker packets with priority tiering and a cost estimate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.distill import (                      # noqa: E402
    DEFAULT_MAX_TOKENS_PER_ARTICLE,
    distill_stats,
    estimate_tokens,
)
from src.agent.article_contract import MIN_CITATION_CHARS, analyzed_l1_sql  # noqa: E402
from src.agent.silver_source import read_silver_text  # noqa: E402
from src.agent.entities import load_registry          # noqa: E402
from src.agent.prefix import (                        # noqa: E402
    SYSTEM_OVERHEAD_TOKENS,
    cached_prefix_tokens,
    persona_tokens,
)
from src.core import paths                             # noqa: E402
from src.core.stdio import force_utf8_stdio           # noqa: E402
from src.db.preflight import resolve_db_path          # noqa: E402
from src.pipeline.cluster_job import refresh as refresh_clusters  # noqa: E402
from src.pipeline.inherit import hold_cutoff          # noqa: E402
from src.db.connect import open_ro, open_rw  # noqa: E402

force_utf8_stdio()

TASK_DIR = paths.article_packets_dir()

# The three ceilings below are the real limits of the DSH read tool, taken from
# the `dsh-tool-fs` README: `readMaxLineLength` 2000 characters per line,
# `readMaxBytes` 51,200 bytes per call, `readLimit` 2000 lines per call. Packets
# must be written so the orchestrator can read them back intact; otherwise data
# is silently truncated.
READ_MAX_LINE_CHARS = 2000
READ_MAX_BYTES = 51_200
READ_MAX_LINES = 2000
LINE_SAFETY_MARGIN = 100

CONTEXT_WINDOW = 1_000_000

# Measured on 2026-09-21 over the 400 most recent real records of each table:
#   l1_outputs     mean   872 chars  ~ 291 tokens, p90 370
#   agent_outputs  mean 1,946 chars  ~ 649 tokens, p90 859
# The merged Article Lane record carries both parts, so it weighs about 900
# tokens, p90 about 1,200. The old constant was 300 because it was calibrated on
# the L1 tier alone; it underestimated output by a factor of three and hid the
# truncation ceiling below.
DEFAULT_OUT_TOKENS_PER_ARTICLE = 900

# Per-call output reference, used only to ESTIMATE cost.
#
# 256,000 is the DSH default `maxTokens` (`DEFAULT_MAX_TOKENS = 256e3` in
# `dsh-llm-deepseek`), source: `docs/proposals/20260918-dsh-surface-verified.md`
# sections 6.1-6.2. It is the `max_tokens` of one request, NOT a wave gate.
#
# Reaching this value neither errors nor cancels the call: the adapter maps
# `finish_reason` `"length"` to `{kind:"max-tokens"}` (`dsh-llm-deepseek`), the
# agent loop ends the turn normally (`dsh-agent-loop`), and `salvage_records`
# extracts every complete record already generated. `--repair` repacks the
# missing part.
#
# The number is therefore used only to print the estimate. No code branch may
# stop, split or reduce the article count based on it.
INFO_OUTPUT_REFERENCE = 256_000

# Maximum parallel batches DSH runs at once in one orchestration call:
# `maxParallelSubCalls` defaults to 10 (`dsh-tools`). Batches above this
# threshold wait for a full wave, so the target batch count is always 10.
MAX_PARALLEL_BATCHES = 10

# Standard batch size for every provider (ADR 0017 D5). Long batches make the
# last records drift because they are generated in a context that already holds
# all earlier records. Other sizes are set only through `--batch`.
DEFAULT_BATCH_SIZE = 50

# Urgent macro signals: an article containing these terms always enters the
# priority tier even when it matches no watchlist code, because they affect the
# whole market.
_MACRO_URGENT_RE = re.compile(
    r"(?:ngân\s*hàng\s*nhà\s*nước|nhnn|lãi\s*suất|tỷ\s*giá|room\s*tín\s*dụng"
    r"|lạm\s*phát|cpi|gdp|thuế\s*quan|thuế\s*chống\s*bán\s*phá\s*giá|thuế\s*tự\s*vệ"
    r"|fed|fomc|nâng\s*hạng|ftse|msci|trái\s*phiếu\s*doanh\s*nghiệp)",
    re.IGNORECASE,
)


def get_db_connection() -> sqlite3.Connection:
    """Open a connection to the same database the ingest step writes to.

    Returns:
        SQLite connection to `monocle.db`.
    """
    return open_rw(resolve_db_path(), row_factory=True)


def watchlist_universe(reg) -> tuple[set[str], set[str]]:
    """Build the watched entity set and the industries related to it.

    The industry set is a deliberate extension for inclusive matching: an
    article about the steel industry still deserves priority for a user who
    watches a steel ticker, even when the article does not mention the ticker.

    Args:
        reg: `EntityRegistry` instance with user subscriptions loaded.

    Returns:
        Pair of the watched entity id set and the related industry name set.
    """
    watched: set[str] = set()
    for subs in (reg.subscriptions or {}).values():
        watched |= set(subs)

    industries: set[str] = set()
    for eid in watched:
        ent = reg.entities.get(eid) or {}
        attrs = ent.get("attributes") or {}
        for key in ("gics1", "gics2", "gics3"):
            if attrs.get(key):
                industries.add(str(attrs[key]).strip().lower())
    return watched, industries


def tier_of(title: str, reg, watched: set[str], industries: set[str]) -> tuple[int, str]:
    """Assign an article to a priority tier using inclusive matching.

    Args:
        title: Article title.
        reg: `EntityRegistry` instance.
        watched: Set of watched entity ids.
        industries: Set of industry names related to the watchlist.

    Returns:
        Pair of the tier number (1 is highest priority) and the tiering reason.
    """
    detected = reg.detect(title or "")
    ids = {d["entity_id"] for d in detected}

    hit = ids & watched
    if hit:
        return 1, f"watchlist:{sorted(hit)[0]}"

    for d in detected:
        attrs = (reg.entities.get(d["entity_id"]) or {}).get("attributes") or {}
        for key in ("gics1", "gics2", "gics3"):
            val = str(attrs.get(key) or "").strip().lower()
            if val and val in industries:
                return 1, f"industry:{val}"

    if _MACRO_URGENT_RE.search(title or ""):
        return 1, "macro-urgent"

    return 2, "background"


# Condition "article was analyzed by the model" on table `l1_outputs` aliased
# `o`. The code-first record is a temporary-table lookup (ADR 0003), not an
# analysis: counting it as done makes the selector skip the article forever and
# the article never gets a content part. Measured on 2026-09-23: 2,915 articles
# of 10-17/09 were stuck this way.
ANALYZED_L1 = analyzed_l1_sql("o")


def load_candidates(conn: sqlite3.Connection, *, date: str | None, limit: int,
                    only_pending: bool, exclude: set[str] | None = None,
                    with_content: bool = True,
                    exclude_thin: bool = True) -> list[sqlite3.Row]:
    """Select articles to process together with their silver package paths.

    Args:
        conn: Database connection.
        date: Publication date filter YYYY-MM-DD, or None for all dates.
        limit: Maximum number of articles.
        only_pending: Select only articles not yet analyzed to standard by the
            model.
        exclude: Article ids to skip (articles in another wave or out of
            retries). Filtered in SQL before `LIMIT`, so the wave still gets
            its full article count.
        with_content: When False, the `content_text` column is not returned;
            counters need only the ids.
        exclude_thin: When True, drop thin articles (fewer than two paragraphs
            long enough to cite, so Gold fails deterministically). Filtering
            uses the same paragraph array the packing step will send, so every
            caller (radar, sensor, packing) sees the same count. Reads package
            files on disk, so time grows with the article count.

    Returns:
        List of article rows.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(articles)").fetchall()}
    has_content = "content_text" in cols

    if has_content:
        sql = [
            "SELECT a.url_title_hash AS article_id, a.title, a.published_at,",
            "       a.source_domain, w.package_path"
            + (", a.content_text" if with_content else ""),
            "FROM articles a",
            "LEFT JOIN work_items w ON w.article_id = a.url_title_hash",
            "WHERE (w.package_path IS NOT NULL OR (a.content_text IS NOT NULL AND length(a.content_text) > 100))",
        ]
    else:
        sql = [
            "SELECT a.url_title_hash AS article_id, a.title, a.published_at,",
            "       a.source_domain, w.package_path",
            "FROM articles a",
            "JOIN work_items w ON w.article_id = a.url_title_hash",
            "WHERE w.package_path IS NOT NULL",
        ]
    params: list = []
    if only_pending:
        sql.append(f"  AND NOT EXISTS (SELECT 1 FROM l1_outputs o "
                   f"WHERE o.article_id = a.url_title_hash AND {ANALYZED_L1})")
        has_clusters = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cluster_members'").fetchone()
        if has_clusters:
            # A copied article waits to inherit the original's result at no
            # token cost (ADR 0016). Once the hold expires it returns to the
            # selector so it is never stuck forever.
            sql.append("  AND NOT EXISTS (SELECT 1 FROM cluster_members cm "
                       "WHERE cm.article_id = a.url_title_hash AND cm.role = 'copy' "
                       "AND cm.decided_at >= ?)")
            params.append(hold_cutoff())
    if date:
        sql.append("  AND substr(a.published_at,1,10) = ?")
        params.append(date)
    if exclude:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pack_exclude (id TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM _pack_exclude")
        conn.executemany("INSERT OR IGNORE INTO _pack_exclude(id) VALUES (?)",
                         [(x,) for x in exclude])
        sql.append("  AND a.url_title_hash NOT IN (SELECT id FROM temp._pack_exclude)")
    sql.append("GROUP BY a.url_title_hash")
    # The secondary key `url_title_hash` makes the article order deterministic.
    # The provider cache matches by prefix from token 0, so two packings of the
    # same article set must produce byte-identical packets for a rerun to hit
    # the cache. With `published_at DESC` alone, articles with equal timestamps
    # swap places depending on the query plan, and every token after the first
    # swapped article misses.
    sql.append("ORDER BY a.published_at DESC, a.url_title_hash")
    if not exclude_thin:
        sql.append("LIMIT ?")
        params.append(limit)
        return list(conn.execute("\n".join(sql), params))

    # With exclude_thin=True: collect `limit` non-thin articles and stop as soon
    # as the count is reached. This avoids a starvation bug: with LIMIT in SQL,
    # short items at the head of the list would consume the whole quota, valid
    # articles further down would never be reached and the result would be empty.
    rows: list[sqlite3.Row] = []
    for r in conn.execute("\n".join(sql), params):
        if not is_thin_row(r):
            rows.append(r)
            if len(rows) >= limit:
                break
    return rows


def read_cleaned_text(package_path: str) -> str:
    """Read the normalized text from a silver package.

    Args:
        package_path: Package path, relative to the data root or absolute.

    Returns:
        Article text, or an empty string when it cannot be read.
    """
    p = paths.resolve_data_path(package_path)
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f) or {}).get("cleaned_text") or ""
    except (OSError, json.JSONDecodeError):
        return ""


def resolve_body_text(*, source_domain=None, published_at=None, article_id=None,
                      package_path=None, content_text=None) -> str:
    """Get the full article body using one priority order everywhere.

    Full Silver first, then the RSS work package, then the content stored in
    the DB. This order is the lane's implicit contract: the packet, the thin
    filter and the check gate must all see the same body for citations to match.

    Args:
        source_domain: Source domain used to locate the Silver package.
        published_at: Publication timestamp used to locate the Silver package.
        article_id: Article identifier hash.
        package_path: Fallback RSS work package path.
        content_text: DB content used when no file can be read.

    Returns:
        Article body, or an empty string when no source is readable.
    """
    text = ""
    if article_id:
        text = read_silver_text(source_domain, published_at, article_id)
    if not text and package_path:
        text = read_cleaned_text(package_path)
    if not text and content_text:
        text = content_text
    return text or ""


def row_paragraphs(row: sqlite3.Row,
                   *, max_tokens: int = DEFAULT_MAX_TOKENS_PER_ARTICLE) -> list[str]:
    """Get the paragraphs exactly as the packing step will send them to the model.

    The body comes from the full Silver package first, then the RSS work
    package and the DB content, in the same order as the packing loop. Model
    citations match only when the packet and the check gate read the same body,
    so an old packet built from a short RSS excerpt counts as stale once Silver
    has the full body. The default budget equals the default of
    `--max-tokens-per-article`, so the thin filter and the packer see the same
    paragraph array.

    Args:
        row: Article row from `load_candidates`.
        max_tokens: Token ceiling when distilling paragraphs.

    Returns:
        Paragraph array, empty when no content is readable.
    """
    def _col(name: str):
        try:
            return row[name]
        except (IndexError, KeyError, TypeError):
            return None

    text = resolve_body_text(
        source_domain=_col("source_domain"), published_at=_col("published_at"),
        article_id=_col("article_id"), package_path=_col("package_path"),
        content_text=_col("content_text"))
    if not text:
        return []
    return distill_stats(text, max_tokens=max_tokens)["paragraphs"] or []


def is_thin(paragraphs: list[str]) -> bool:
    """Check whether an article is thin: fewer than two paragraphs long enough to cite.

    The Gold gate demands two verbatim citations, each a paragraph reaching
    `MIN_CITATION_CHARS`. A thin article passes entity recognition but fails
    Gold deterministically, so it must be excluded from the packet instead of
    burning tokens.

    Args:
        paragraphs: Paragraph array to be sent to the model.

    Returns:
        True when the content part can never be built for the article.
    """
    return sum(1 for p in paragraphs if len(p) >= MIN_CITATION_CHARS) < 2


def is_thin_row(row) -> bool:
    """Check whether the content is readable and determined to be thin.

    When facts are missing (a tuple row without keys, an unreadable file), the
    function returns False so the packing loop excludes the article later as
    before: fail-open, without hiding the backlog.

    Args:
        row: Article row from `load_candidates` (Row or tuple).

    Returns:
        True only when the content part is certain to be unbuildable.
    """
    try:
        paras = row_paragraphs(row)
    except (TypeError, IndexError, KeyError):
        return False
    return bool(paras) and is_thin(paras)


def fresh_wave_paragraphs(article_ids: set[str]) -> dict[str, list[str]]:
    """Get the current paragraph arrays of wave articles, read from full Silver.

    Used to detect stale packets: a packet built when Silver did not exist yet
    (or the RSS was still a short excerpt) carries far fewer paragraphs than
    the current body. Such an article must be repacked instead of patched
    around the old record, because old citations cannot be matched against the
    new body.

    Args:
        article_ids: Set of article id hashes to check.

    Returns:
        Dict mapping article id to its current paragraph array. An article
        whose body cannot be read is absent from the dict.
    """
    fresh: dict[str, list[str]] = {}
    ids = [a for a in article_ids if a]
    if not ids:
        return fresh
    try:
        conn = open_ro(resolve_db_path())
    except (sqlite3.Error, TypeError, ValueError):
        return fresh
    try:
        conn.row_factory = sqlite3.Row
        step = 200
        rows: dict[str, sqlite3.Row] = {}
        for i in range(0, len(ids), step):
            chunk = ids[i:i + step]
            cur = conn.execute(
                "SELECT url_title_hash AS article_id, title, published_at, "
                "source_domain FROM articles WHERE url_title_hash IN (%s)"
                % ",".join("?" * len(chunk)), chunk)
            for row in cur.fetchall():
                rows[row["article_id"]] = row
    finally:
        conn.close()
    for aid, row in rows.items():
        try:
            paras = row_paragraphs(row)
        except (TypeError, IndexError, KeyError):
            continue
        if paras:
            fresh[aid] = paras
    return fresh


def suggest_batch_size(n_articles: int) -> int:
    """Choose the batch size when the operator does not set `--batch`.

    Args:
        n_articles: Number of articles in the whole wave.

    Returns:
        Standard batch size, identical for every provider and wave size.
    """
    return DEFAULT_BATCH_SIZE


def plan_calls(n_articles: int, *, batch_cap: int) -> list[int]:
    """Split a wave into calls of even size, bounded only by the operator's cap.

    `--batch` is the only splitting gate. No token ceiling intervenes here
    anymore: context is not a constraint (a hundred-article wave takes about 15%
    of the window), and the output ceiling is not yet measured, so it cannot
    serve as a batching rule.

    The split is even rather than overflow-based: calls run in parallel, so the
    wave finishes only when the longest call finishes; a very short leftover
    call shortens nothing and only skews the load between calls.

    Args:
        n_articles: Number of articles in the whole wave.
        batch_cap: Maximum articles per call set by the operator.

    Returns:
        Article count per call, summing exactly to `n_articles`.
    """
    if n_articles <= 0:
        return []
    cap = max(1, batch_cap)
    n_calls = max(1, math.ceil(n_articles / cap))
    base, extra = divmod(n_articles, n_calls)
    return [base + (1 if i < extra else 0) for i in range(n_calls)]


def write_packet(batch_id: str, items: list[dict], mapping: dict,
                 out_dir: Path) -> tuple[Path, Path, dict]:
    """Write the packet to disk in a form that reads back intact, with the index map.

    The packet is written with a **line break per element** instead of a single
    line. The read tool cuts each line at 2,000 characters, so a compact JSON
    file on one line would be almost entirely truncated. With one paragraph per
    line, the longest line equals the longest paragraph, which measured over
    4,493 real paragraphs is only 954 characters.

    Args:
        batch_id: Batch id.
        items: Packed article list.
        mapping: Mapping from local index to article id.
        out_dir: Destination directory.

    Returns:
        Triple of the packet path, the map path and the read budget figures.

    Raises:
        ValueError: If the packet has a line above the read tool's line cut.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "d": datetime.now().strftime("%Y-%m-%d"),
        "n": len(items),
        "a": items,
    }
    text = json.dumps(packet, ensure_ascii=False, indent=1)

    lines = text.splitlines()
    longest = max((len(line) for line in lines), default=0)
    limit = READ_MAX_LINE_CHARS - LINE_SAFETY_MARGIN
    if longest > limit:
        raise ValueError(
            f"packet {batch_id} có dòng dài {longest} ký tự, vượt ngưỡng an toàn {limit}. "
            "Công cụ đọc sẽ cắt cụt dòng này và phía điều phối nhận dữ liệu thiếu. "
            "Hạ MAX_PARAGRAPH_CHARS trong src/agent/distill.py rồi đóng gói lại."
        )

    packet_path = out_dir / f"{batch_id}.task.json"
    packet_path.write_text(text, encoding="utf-8")

    map_path = out_dir / f"{batch_id}.map.json"
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")

    size = len(text.encode("utf-8"))
    budget = {
        "bytes": size,
        # Packet hash: verifiable evidence of determinism. If repacking the same
        # article set changes the hash, a rerun will miss the cache.
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "lines": len(lines),
        "longest_line": longest,
        "windows": read_windows(lines),
    }
    budget["read_calls"] = len(budget["windows"])
    return packet_path, map_path, budget


def read_windows(lines: list[str]) -> list[list[int]]:
    """Split the file into line windows that each read fully in one call.

    The read tool caps at 51,200 bytes and 2,000 lines per call, so a
    hundred-article packet needs several reads. The windows are precomputed
    here so the orchestrator only iterates the list and never guesses
    thresholds at run time. These reads run inside the same program, so they
    cost the model **no extra step**.

    Args:
        lines: Line list of the packet file.

    Returns:
        List of `[start line counted from 1, line count]` pairs.
    """
    budget = READ_MAX_BYTES - 4096          # reserve room for the envelope and line numbers
    windows: list[list[int]] = []
    start = 1
    used = 0
    count = 0
    for idx, line in enumerate(lines, start=1):
        cost = len(line.encode("utf-8")) + 12
        if count and (used + cost > budget or count >= READ_MAX_LINES):
            windows.append([start, count])
            start = idx
            used = 0
            count = 0
        used += cost
        count += 1
    if count:
        windows.append([start, count])
    return windows or [[1, 1]]


def histogram(values: list[int], *, buckets: int = 6) -> list[str]:
    """Build a text distribution chart for tokens per article.

    Args:
        values: Token count of each article.
        buckets: Number of intervals.

    Returns:
        List of chart lines.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [f"  {lo:>5} token │ {'█' * 40} {len(values)}"]
    width = (hi - lo) / buckets
    lines = []
    for b in range(buckets):
        start = lo + width * b
        end = start + width
        n = sum(1 for v in values if (start <= v < end or (b == buckets - 1 and v == hi)))
        bar = "█" * int(40 * n / len(values)) if values else ""
        lines.append(f"  {int(start):>5}-{int(end):<5} │ {bar} {n}")
    return lines


def main(argv=None) -> int:
    """Run the command-line interface that packs articles.

    Args:
        argv: Command-line argument list. Defaults to `sys.argv`.

    Returns:
        Exit code 0 when packing succeeds, 2 when no article qualifies.
    """
    ap = argparse.ArgumentParser(description="Đóng gói bài đăng thành packet cho worker")
    ap.add_argument("--wave", default=datetime.now().strftime("%Y%m%dT%H%M"),
                    help="Mã đợt, dùng làm tiền tố tên lô")
    ap.add_argument("--batch", type=int, default=0,
                    help="Số bài mỗi lô; 0 = tự chọn để đợt gọn trong một sóng song song")
    ap.add_argument("--limit", type=int, default=300, help="Tổng số bài tối đa của đợt")
    ap.add_argument("--date", help="Chỉ lấy bài xuất bản trong ngày YYYY-MM-DD")
    ap.add_argument("--today", action="store_true", help="Tương đương --date hôm nay")
    ap.add_argument("--all-articles", action="store_true",
                    help="Lấy cả bài đã có kết quả nhận diện đạt chuẩn")
    ap.add_argument("--max-tokens-per-article", type=int,
                    default=DEFAULT_MAX_TOKENS_PER_ARTICLE,
                    help="Trần token phần nội dung mỗi bài")
    ap.add_argument("--out-tokens-per-article", type=int,
                    default=DEFAULT_OUT_TOKENS_PER_ARTICLE,
                    help="Cỡ bản ghi đầu ra mỗi bài, chỉ dùng để ước lượng token")
    ap.add_argument("--out-dir", default=str(TASK_DIR), help="Thư mục ghi packet")
    ap.add_argument("--json", action="store_true", help="Xuất mô tả đợt dạng JSON")
    ap.add_argument("--no-cluster", action="store_true",
                    help="Không làm mới cụm trùng lặp trước khi chọn bài")
    ap.add_argument("--exclude-file",
                    help="Tệp định danh bài phải bỏ qua, mỗi dòng một định danh")
    args = ap.parse_args(argv)

    date = args.date or (datetime.now().strftime("%Y-%m-%d") if args.today else None)
    exclude: set[str] = set()
    if args.exclude_file:
        exclude = {ln.strip() for ln in Path(args.exclude_file).read_text(
            encoding="utf-8").splitlines() if ln.strip()}

    conn = get_db_connection()
    if not args.no_cluster:
        try:
            print(f"Cụm hoá trùng lặp: {refresh_clusters(conn)}")
        except sqlite3.Error as e:
            print(f"Bỏ qua cụm hoá (DB không ghi được hoặc chưa có bảng): {e}")
    rows = load_candidates(conn, date=date, limit=args.limit,
                           only_pending=not args.all_articles, exclude=exclude)
    conn.close()
    if not rows:
        print("Không có bài nào thoả điều kiện. Kiểm lại --date hoặc hàng đợi work_items.")
        return 2

    reg = load_registry()
    watched, industries = watchlist_universe(reg)

    packed: list[dict] = []
    n_thin = 0
    for r in rows:
        text = resolve_body_text(
            source_domain=r["source_domain"], published_at=r["published_at"],
            article_id=r["article_id"], package_path=r["package_path"],
            content_text=r["content_text"] if "content_text" in r.keys() else None)
        if not text:
            continue
        stats = distill_stats(text, max_tokens=args.max_tokens_per_article)
        if not stats["paragraphs"]:
            continue
        if is_thin(stats["paragraphs"]):
            n_thin += 1
            continue
        tier, reason = tier_of(r["title"], reg, watched, industries)
        packed.append({
            "article_id": r["article_id"],
            "title": r["title"] or "",
            "paragraphs": stats["paragraphs"],
            "tokens": stats["tokens_after"] + estimate_tokens(r["title"] or ""),
            "tier": tier,
            "reason": reason,
            "domain": r["source_domain"],
        })

    if not packed:
        print("Có bài nhưng không đọc được nội dung nào. Kiểm lại work_packages trên đĩa.")
        return 2

    # Priority tier runs first; within a tier the newest-first order is kept.
    # Python's `sort` is stable and the query is already deterministic, so the
    # final order depends only on the data and not on the run: the condition for
    # a repack to yield an identical packet and hit the cache.
    packed.sort(key=lambda a: a["tier"])

    # The static prefix includes the part the harness appends itself (AGENTS.md,
    # tool/SDK section), not only the project persona. Both precede the packet
    # and are static, so both hit the cache; omitting the harness part makes
    # `est_hit` fall short by about 4,800 tokens per call and leaves the
    # estimate unreconcilable with the real `cacheRead` in the ledger.
    pfx = cached_prefix_tokens()

    # `--batch 0` lets the wave pick the batch size from the real article count.
    # The operator sets a fixed number only to force a specific split.
    batch_size = args.batch if args.batch > 0 else suggest_batch_size(len(packed))
    chunk_cap = max(1, batch_size)

    # Split evenly instead of overflowing. Overflow leaves a very short leftover
    # call, and since calls run in parallel the wave finishes only when the
    # longest call finishes: the leftover shortens nothing and only skews the
    # load between calls.
    sizes = plan_calls(len(packed), batch_cap=batch_size)

    # A single-batch wave has no cache warm-up call: with no second batch to
    # reuse the prefix, a warm-up call would only move the same miss tokens to
    # another request and add one output record. The only batch pays the fresh
    # token cost for the prefix itself.
    warmed = len(sizes) >= 2

    batches: list[dict] = []
    out_dir = Path(args.out_dir)
    cursor = 0
    seq = 1
    for size in sizes:
        chunk = packed[cursor:cursor + size]

        batch_id = f"article_{args.wave}_{seq:02d}"
        items = [{"i": i, "t": a["title"], "p": a["paragraphs"]}
                 for i, a in enumerate(chunk)]
        mapping = {
            "batch_id": batch_id,
            "wave": args.wave,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "index": {str(i): a["article_id"] for i, a in enumerate(chunk)},
            "tier": {str(i): a["tier"] for i, a in enumerate(chunk)},
            "reason": {str(i): a["reason"] for i, a in enumerate(chunk)},
        }
        packet_path, map_path, budget = write_packet(batch_id, items, mapping, out_dir)

        est_in = pfx + sum(a["tokens"] for a in chunk)
        est_out = len(chunk) * args.out_tokens_per_article
        batches.append({
            "batch_id": batch_id,
            "path": paths.to_data_relative(packet_path),
            "map": paths.to_data_relative(map_path),
            "n": len(chunk),
            "tier1": sum(1 for a in chunk if a["tier"] == 1),
            "est_miss": est_in - pfx,
            "est_hit": pfx if warmed else 0,
            "est_out": est_out,
            "est_ctx_peak": est_in + est_out,
            "bytes": budget["bytes"],
            "sha256": budget["sha256"],
            "read_calls": budget["read_calls"],
            "longest_line": budget["longest_line"],
            "windows": budget["windows"],
        })
        cursor += len(chunk)
        seq += 1

    summary = {
        "wave": args.wave,
        # This timestamp anchors cost attribution in the ledger: only DSH
        # sessions created AFTER packing belong to the wave. A wider anchor would
        # wrongly merge unrelated sessions and inflate the per-article cost.
        "created_epoch": datetime.now().timestamp(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "articles": len(packed),
        "thin_skipped": n_thin,
        "batches": batches,
        "tier1": sum(b["tier1"] for b in batches),
        "prefix_tokens": pfx,
        "persona_tokens": persona_tokens(),
        "system_overhead_tokens": SYSTEM_OVERHEAD_TOKENS,
        # The cache warm-up call precedes every batch: it pays the fresh token
        # cost for the prefix exactly once, so every later batch hits the cache
        # and none has to wait.
        "est_warm_miss": pfx,
        "warmed": warmed,
        "per_call": chunk_cap,
        "out_tokens_per_article": args.out_tokens_per_article,
        "output_reference_tokens": INFO_OUTPUT_REFERENCE,
        "max_parallel_batches": MAX_PARALLEL_BATCHES,
        "est_miss_total": sum(b["est_miss"] for b in batches) + pfx,
        "est_hit_total": sum(b["est_hit"] for b in batches),
        "est_out_total": sum(b["est_out"] for b in batches),
    }
    summary["est_quota_total"] = (summary["est_miss_total"] + summary["est_hit_total"]
                                  + summary["est_out_total"])

    manifest = Path(args.out_dir) / f"wave_{args.wave}.json"
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    summary["manifest"] = str(manifest)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    tokens = [a["tokens"] for a in packed]
    print("=" * 84)
    print(f" 📦  ĐÓNG GÓI ĐỢT {args.wave}")
    print("=" * 84)
    lot = (f"{len(batches)} lượt gọi song song trong MỘT bước điều phối"
           if len(batches) > 1 else "MỘT lượt gọi duy nhất")
    print(f"Bài đóng gói : {len(packed):,} ({summary['tier1']:,} tầng ưu tiên) → {lot}")
    if n_thin:
        print(f"Bài mỏng     : {n_thin:,} bài không đủ hai đoạn đạt độ dài trích dẫn "
              f"nên không vào packet (Gold trượt tất định, không tốn token); "
              f"chờ gói Silver.")
    cache_note = ("mọi lô trúng cache nhờ lượt hâm đi trước" if warmed
                  else "một lô nên không hâm; lô này trả giá token mới")
    print(f"Prefix tĩnh  : {pfx:,} token = persona {persona_tokens():,} + harness "
          f"{SYSTEM_OVERHEAD_TOKENS:,} ({cache_note})")
    worst_out = max((b["est_out"] for b in batches), default=0)
    print(f"Chia lô      : {len(batches)} lô, {chunk_cap} bài mỗi lô "
          f"(song song tối đa {MAX_PARALLEL_BATCHES}).")
    print(f"Đầu ra ước   : {worst_out:,} token cho lượt nặng nhất "
          f"(bản ghi {args.out_tokens_per_article} token/bài). Số ước lượng, "
          f"không phải trần.")
    print()
    print(f"{'lô':26} {'bài':>4} {'ưu tiên':>8} {'miss':>9} {'out':>7} "
          f"{'ctx đỉnh':>9} {'KB':>6} {'đọc':>4}")
    print("-" * 84)
    for b in batches:
        print(f"{b['batch_id']:26} {b['n']:>4} {b['tier1']:>8} "
              f"{b['est_miss']:>9,} {b['est_out']:>7,} "
              f"{b['est_ctx_peak'] / CONTEXT_WINDOW:>8.1%} "
              f"{b['bytes'] / 1024:>6.0f} {b['read_calls']:>4}")
    print("-" * 84)
    print(f"Dự toán đợt  : quota {summary['est_quota_total']:,} token "
          f"(miss {summary['est_miss_total']:,} · hit {summary['est_hit_total']:,} · "
          f"out {summary['est_out_total']:,})")
    print()
    print("Phân bố token mỗi bài:")
    for line in histogram(tokens):
        print(line)

    reads = sum(b["read_calls"] for b in batches)
    longest = max(b["longest_line"] for b in batches)
    print()
    print(f"Ngân sách đọc: {reads} lần gọi `read` cho cả đợt "
          f"(mỗi lần tối đa {READ_MAX_BYTES // 1024} KB) · dòng dài nhất {longest} ký tự "
          f"trên trần {READ_MAX_LINE_CHARS}")
    if reads > len(batches):
        print("  Lô nào cần hơn một lần đọc thì phía điều phối phải phân trang bằng "
              "`offset`/`limit` ngay trong cùng một chương trình; việc này KHÔNG tốn "
              "thêm bước nào của mô hình.")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
