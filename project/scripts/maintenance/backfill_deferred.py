"""Backfill full text and publication dates for articles whose detail extraction was deferred."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

from src.core import paths
from src.core.config import (
    load_domain_config,
    load_secrets,
    load_settings,
    resolve_source_domain,
)
from src.core.logging import setup_logging
from src.core.models import VN_TZ, now_vn_iso
from src.core.stdio import force_utf8_stdio
from src.crawler.backoff import SourceBackoff
from src.crawler.http_client import HTTPClient
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate
from src.db.store import ArticleStore
from src.pipeline.silver_builder import _html_from_json
from src.processor.extractor import extract_text

# The scheduler calls this script via subprocess with capture_output=True, so stdout is a
# pipe that defaults to the system encoding (cp1252) and crashes on Vietnamese text/emoji.
force_utf8_stdio()


DEFAULT_MAX_ATTEMPTS = 5

# Articles confirmed gone for good (source deleted, 404/410) or retried the allowed number
# of times are no longer pursued. Without this filter the 5-minute automated job would
# re-fetch a dead URL forever.
_EXCLUDE_DEAD = ("metadata_json NOT LIKE '%\"source_deleted\": true%' "
                 "AND metadata_json NOT LIKE '%\"source_deleted\":true%' "
                 "AND metadata_json NOT LIKE '%\"capture_giveup\": true%' "
                 "AND metadata_json NOT LIKE '%\"capture_giveup\":true%'")

# Articles beyond `max_details_per_cycle`: the detail page was never fetched.
_DEFERRED_WHERE = ("((metadata_json LIKE '%\"detail_deferred\": true%' "
                   "OR metadata_json LIKE '%\"detail_deferred\":true%') "
                   f"AND {_EXCLUDE_DEAD})")

# Articles fetched but transiently broken during the live capture (timeout, 5xx, 403, empty
# body). `backfilled_from_bronze` excludes recovered articles from the rescan.
_FAILED_WHERE = ("(metadata_json LIKE '%\"capture_status\": \"failed\"%' "
                 "AND metadata_json NOT LIKE '%backfilled_from_bronze%' "
                 f"AND {_EXCLUDE_DEAD})")


def _find_bronze(domain: str, url_title_hash: str,
                 raw_dir: str | None = None) -> str | None:
    """Find the usable Bronze .html file of an article.

    `RawStore.save` still writes the body on HTTP errors (kept for inspection), so a
    404/500 page also produces an .html file. The `.meta.json` sidecar must be checked to
    exclude them; otherwise a later backfill would extract the error page as article
    content. A missing sidecar is accepted (legacy or hand-placed artifact).

    Args:
        domain: Source domain directory under the Bronze root.
        url_title_hash: Hash that names the Bronze file.
        raw_dir: Bronze root directory; defaults to `paths.bronze_dir()`.

    Returns:
        Path of the newest usable .html file, or None if none exists or none is valid.
    """
    raw_dir = raw_dir or str(paths.bronze_dir())
    hits = sorted(glob.glob(os.path.join(raw_dir, domain, "*",
                                         f"{url_title_hash}.html")))
    for html_path in reversed(hits):      # newest first
        meta_path = html_path[:-len(".html")] + ".meta.json"
        try:
            status = json.loads(
                Path(meta_path).read_text(encoding="utf-8")).get("capture_status")
        except (OSError, ValueError):
            return html_path              # sidecar missing or unreadable: trust the file
        if status in ("ok", "partial"):
            return html_path
    return None


def _content_selector_for(domain_cfg_name: str) -> str:
    try:
        cfg = load_domain_config(domain_cfg_name)
    except (FileNotFoundError, ValueError):
        return ""
    return (cfg.get("detail", {}) or {}).get("content_selector", "") or ""


def _detail_endpoint(domain_cfg_name: str, row) -> tuple[str, dict]:
    """Resolve the URL and headers used to fetch an article detail.

    The default URL is `articles.url`. An API source that declares
    `api.detail_url_template` (for example fireant `/posts/{post_id}`) has a web page that
    is only an SPA, so the API endpoint must be fetched; the template is filled from the
    article `metadata`. A Bearer token is added when the config declares `auth.secret_key`.

    Args:
        domain_cfg_name: Domain config name.
        row: `articles` table row.

    Returns:
        Tuple of the URL to fetch and the request headers.
    """
    url = row["url"]
    headers: dict = {}
    try:
        cfg = load_domain_config(domain_cfg_name)
    except (FileNotFoundError, ValueError):
        return url, headers

    template = (cfg.get("api", {}) or {}).get("detail_url_template", "")
    if template:
        try:
            meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            url = template.format(**meta)
            headers["Accept"] = "application/json, text/plain, */*"
        except (KeyError, IndexError, ValueError):
            url = row["url"]          # missing field: fall back to the web URL, no guessing

    secret_key = (cfg.get("auth", {}) or {}).get("secret_key", "")
    if secret_key:
        token = (load_secrets().get(secret_key) or "").strip()
        if token[:7].lower() == "bearer ":
            token = token[7:].strip()
        if token and not token.startswith("PASTE_"):
            headers["Authorization"] = f"Bearer {token}"
    return url, headers


def _extract_from_bronze(html_path: str, selector: str) -> tuple[str, str]:
    """Extract content HTML and text from a Bronze file without network access.

    Bronze files of API sources (for example fireant) are JSON rather than HTML, so the
    HTML field is unwrapped first, as `SilverBuilder` does. Without this step
    content_text would include JSON keys and brackets.

    Args:
        html_path: Path of the Bronze file.
        selector: CSS selector of the article body; empty to use the whole document.

    Returns:
        Tuple of content_html and content_text; empty strings if the file is unreadable.
    """
    try:
        html = Path(html_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("read bronze failed {}: {}", html_path, e)
        return "", ""

    inner = _html_from_json(html)
    if inner is not None:
        html = inner
        selector = ""          # already the article body HTML, no selector needed

    node_html = html
    if selector:
        try:
            from bs4 import BeautifulSoup
            node = BeautifulSoup(html, "lxml").select_one(selector)
            if node is not None and node.get_text(strip=True):
                node_html = str(node)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("selector {} failed on {}: {}", selector, html_path, e)
    return node_html, extract_text(node_html)


_DATE_TEXT_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})\b")


def _date_scope_for(domain_cfg_name: str) -> str:
    try:
        cfg = load_domain_config(domain_cfg_name)
    except (FileNotFoundError, ValueError):
        return ""
    return (cfg.get("detail", {}) or {}).get("date_scope_selector", "") or ""


def recover_published_at(html_path: str, date_scope: str = "") -> str:
    """Recover published_at from a Bronze file, returning empty when uncertain.

    Sources are tried in order, generic first and config-specific last:
      1. `<meta property="article:published_time">` / `itemprop="datePublished"`
      2. `<time datetime="...">`
      3. JSON-LD `"datePublished"`
      4. Config `date_scope_selector` plus text `dd/MM/yyyy HH:mm` (for example baodautu,
         whose pages carry no date metadata at all)

    Args:
        html_path: Path of the Bronze file.
        date_scope: CSS selector of the node holding the visible date text.

    Returns:
        ISO timestamp string, or an empty string if no date is found. Dates are never guessed.
    """
    try:
        html = Path(html_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - defensive
        return ""

    for attrs in ({"property": "article:published_time"},
                  {"itemprop": "datePublished"},
                  {"name": "pubdate"}):
        tag = soup.find("meta", attrs=attrs)
        val = (tag.get("content") or "").strip() if tag else ""
        if val:
            return val
    tag = soup.find("time", attrs={"datetime": True})
    if tag and (tag.get("datetime") or "").strip():
        return tag["datetime"].strip()
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1).strip()

    if date_scope:
        node = soup.select_one(date_scope)
        if node is not None:
            m = _DATE_TEXT_RE.search(node.get_text(" ", strip=True))
            if m:
                d, mo, y, hh, mm = (int(g) for g in m.groups())
                try:
                    return datetime(y, mo, d, hh, mm,
                                    tzinfo=VN_TZ).isoformat(timespec="seconds")
                except ValueError:
                    return ""
    return ""


def _record_attempt(conn, row, cap: dict, max_attempts: int) -> None:
    """Record a failed content recovery attempt in the article `metadata_json`.

    Without this record a permanently broken article is selected again on every cycle
    (the automated job runs every 5 minutes). `ArticleStore._INSERT_SQL` is
    `INSERT OR IGNORE`, so an existing row is never updated automatically and an explicit
    UPDATE is required here.

    Args:
        conn: Open SQLite connection.
        row: `articles` table row being processed.
        cap: Capture status dict returned by `RawStore.save` (empty if nothing was fetched).
        max_attempts: Maximum attempts before the give-up flag is set.
    """
    meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    retry = meta.setdefault("capture_retry", {})
    retry["attempts"] = int(retry.get("attempts", 0)) + 1
    retry["last_at"] = now_vn_iso()
    retry["last_status"] = cap.get("http_status")
    if cap.get("capture_status") == "deleted_at_source":
        meta["source_deleted"] = True
    elif retry["attempts"] >= max_attempts:
        meta["capture_giveup"] = True
    conn.execute(
        "UPDATE articles SET metadata_json=?, processed_at=? WHERE id=?",
        (json.dumps(meta, ensure_ascii=False), now_vn_iso(), row["id"]))
    conn.commit()


def main(domain: str | None, limit: int, do_fetch: bool, dry_run: bool,
         db_path: str | None = None, raw_dir: str | None = None,
         dates_only: bool = False, mode: str = "deferred",
         max_attempts: int = DEFAULT_MAX_ATTEMPTS,
         retry_window_hours: int = 0, budget_seconds: int = 0) -> int:
    """Backfill content and publication dates for deferred or failed articles.

    Args:
        domain: Config name or host to restrict to; None for all sources.
        limit: Maximum number of articles to process.
        do_fetch: Allow fetching (and writing Bronze) when an article has no artifact.
        dry_run: Count candidates without writing to the database.
        db_path: Database path override for isolated tests; defaults to settings.
        raw_dir: Bronze root override for isolated tests; defaults to `paths.bronze_dir()`.
        dates_only: Only repair empty published_at for articles that already have Bronze.
        mode: `deferred` (articles beyond the cap), `failed` (transient failures), `all` (both).
        max_attempts: Maximum attempts before `capture_giveup` is set.
        retry_window_hours: Only pursue articles whose `fetched_at` is within the last N
            hours; 0 means unlimited (manual bulk backfill behavior).
        budget_seconds: Runtime ceiling; when exceeded, stop cleanly between two articles
            and report the work done. 0 means unlimited. Needed because the scheduler
            calls the job with a timeout and a kill loses the report.

    Returns:
        Process exit code, always 0.
    """
    settings = load_settings()
    raw_dir = raw_dir or str(paths.bronze_dir())
    setup_logging(settings["logging"]["level"], settings["logging"]["dir"])
    store = ArticleStore(db_path or settings["database"]["path"])

    # The domain argument accepts both a config name and a host (vietnambiz | vietnambiz.vn).
    host = resolve_source_domain(domain) if domain else None
    cfg_name = domain.split(".")[0] if domain else ""
    selector = _content_selector_for(cfg_name) if cfg_name else ""
    date_scope = _date_scope_for(cfg_name) if cfg_name else ""

    conn = store.connect()
    # --dates-only repairs empty published_at for articles that already have Bronze, even
    # without the detail_deferred flag, because the first backfill cleared the flag
    # without filling the date.
    if dates_only:
        where = "WHERE (published_at IS NULL OR published_at = '')"
    elif mode == "failed":
        where = f"WHERE {_FAILED_WHERE}"
    elif mode == "all":
        where = f"WHERE ({_DEFERRED_WHERE} OR {_FAILED_WHERE})"
    else:
        where = f"WHERE {_DEFERRED_WHERE}"
    params: list = []
    if retry_window_hours > 0 and not dates_only:
        cutoff = (datetime.now(VN_TZ)
                  - timedelta(hours=retry_window_hours)).isoformat(timespec="seconds")
        where += " AND fetched_at >= ?"      # fixed +07:00 ISO offset makes string comparison safe
        params.append(cutoff)
    if host:
        where += " AND source_domain = ?"
        params.append(host)
    params.append(limit)
    rows = conn.execute(
        f"SELECT id, url, url_title_hash, source_domain, summary, published_at, "
        f"metadata_json "
        f"FROM articles {where} LIMIT ?", params).fetchall()

    logger.info("{} rows: {} (domain={}, selector={!r}, date_scope={!r})",
                "date-repair" if dates_only else mode,
                len(rows), host or "ALL", selector, date_scope)

    # Skip building the HTTP client/robots when there is no work. One line is still printed:
    # a silent job is indistinguishable from a dead one, and the scheduler logs only the
    # last stdout line.
    if not rows:
        print(f"backfill [{mode}]: candidates=0 (không có việc)")
        conn.close()
        return 0

    raw_store = RawStore(raw_dir)
    http = robots = backoff = None
    if do_fetch:
        http = HTTPClient(rate_limit_delay=settings["http"]["rate_limit"],
                          max_retries=settings["http"]["max_retries"])
        robots = RobotsGate(http)
        backoff = SourceBackoff()

    stats = {"from_bronze": 0, "fetched": 0, "no_bronze": 0,
             "empty": 0, "skipped_robots": 0, "failed": 0,
             "date_recovered": 0, "date_missing": 0, "gave_up": 0,
             "budget_stopped": 0}

    started = time.monotonic()
    for r in rows:
        if budget_seconds > 0 and (time.monotonic() - started) >= budget_seconds:
            stats["budget_stopped"] = 1
            logger.info("[backfill] hết ngân sách {}s — dừng sạch, phần còn lại để "
                        "chu kỳ sau", budget_seconds)
            break
        dom = r["source_domain"]
        sel = selector or _content_selector_for(dom.split(".")[0])
        dscope = date_scope or _date_scope_for(dom.split(".")[0])
        html_path = _find_bronze(dom, r["url_title_hash"], raw_dir)

        if html_path is None:
            if not do_fetch:
                stats["no_bronze"] += 1
                continue
            # No Bronze: write Bronze first, never bare content. For API sources (for
            # example fireant) `articles.url` is a web SPA page without a body, so the API
            # endpoint from api.detail_url_template must be fetched.
            fetch_url, extra_headers = _detail_endpoint(dom.split(".")[0], r)
            if robots is not None and not robots.allowed(fetch_url):
                stats["skipped_robots"] += 1
                continue
            if backoff is not None:
                backoff.before_fetch(dom)
            resp = http.get_response(fetch_url, headers=extra_headers or None,
                                     timeout=settings["http"]["timeout"])
            cap = raw_store.save(dom, fetch_url, r["url_title_hash"], resp,
                                 fetched_at=now_vn_iso())
            if backoff is not None:
                backoff.observe(dom, cap.get("http_status"))
            if cap.get("capture_status") not in ("ok", "partial") \
                    or not (cap.get("html_path") or "") \
                    or not os.path.exists(cap.get("html_path") or ""):
                stats["failed"] += 1
                if not dry_run:
                    _record_attempt(conn, r, cap, max_attempts)
                    if cap.get("capture_status") == "deleted_at_source":
                        stats["gave_up"] += 1
                continue
            html_path = cap["html_path"]
            stats["fetched"] += 1
        else:
            stats["from_bronze"] += 1

        if dates_only:
            recovered = recover_published_at(html_path, dscope)
            if not recovered:
                stats["date_missing"] += 1
                continue
            stats["date_recovered"] += 1
            if dry_run:
                continue
            conn.execute("UPDATE articles SET published_at=?, processed_at=? "
                         "WHERE id=?", (recovered, now_vn_iso(), r["id"]))
            conn.commit()
            continue

        content_html, content_text = _extract_from_bronze(html_path, sel)
        if not content_text.strip():
            # Bronze exists but extraction is empty (selector drift or blocked page). It still
            # counts as an attempt so a permanently broken article does not stay queued.
            stats["empty"] += 1
            if not dry_run:
                _record_attempt(conn, r, {}, max_attempts)
            continue

        if dry_run:
            continue

        # published_at: sources such as baodautu expose the date only on the detail page, and
        # deferred articles never passed enrich(), so the column is empty. Recover it from
        # Bronze without guessing.
        published = (r["published_at"] or "").strip()
        if not published:
            published = recover_published_at(html_path, dscope)
            if published:
                stats["date_recovered"] += 1
            else:
                stats["date_missing"] += 1

        meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
        meta.pop("detail_deferred", None)
        meta.pop("capture_retry", None)          # recovery done: clear the retry tracking
        meta["backfilled_from_bronze"] = html_path.replace("\\", "/")
        conn.execute(
            "UPDATE articles SET content_html=?, content_text=?, published_at=?, "
            "processed_at=?, metadata_json=? WHERE id=?",
            (content_html, content_text, published, now_vn_iso(),
             json.dumps(meta, ensure_ascii=False), r["id"]))
        conn.commit()

    conn.close()
    updated = stats["from_bronze"] + stats["fetched"] - stats["empty"]
    logger.info("backfill done{}: updated~{} {}",
                " (DRY RUN)" if dry_run else "", max(updated, 0), stats)
    print(f"backfill{' (dry-run)' if dry_run else ''} [{mode}]: "
          f"candidates={len(rows)} from_bronze={stats['from_bronze']} "
          f"fetched={stats['fetched']} no_bronze={stats['no_bronze']} "
          f"empty={stats['empty']} skipped_robots={stats['skipped_robots']} "
          f"failed={stats['failed']} deleted_at_source={stats['gave_up']} "
          f"date_recovered={stats['date_recovered']} "
          f"date_missing={stats['date_missing']} "
          f"budget_stopped={stats['budget_stopped']}")
    if stats["no_bronze"]:
        print(f"  ⚠️  {stats['no_bronze']} bài CHƯA có Bronze — chạy "
              f"`python scripts/refresh_watchlist.py <n> {host or '<host>'}` trước, "
              f"hoặc thêm --fetch.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    p.add_argument("domain", nargs="?", default=None,
                   help="tên config (vietnambiz) hoặc host (vietnambiz.vn)")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--fetch", action="store_true",
                   help="cho phép fetch (ghi Bronze) khi bài chưa có artifact")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--dates-only", action="store_true",
                   help="chỉ sửa published_at rỗng (bài đã có Bronze), không đụng content")
    p.add_argument("--mode", choices=["deferred", "failed", "all"], default="deferred",
                   help="deferred: bài vượt cap (mặc định) · failed: bài fetch lỗi tạm "
                        "thời (timeout/5xx/403) · all: cả hai")
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
                   help="số lần thử tối đa trước khi gắn cờ capture_giveup")
    p.add_argument("--retry-window-hours", type=int, default=0,
                   help="chỉ truy đuổi bài có fetched_at trong N giờ gần đây (0 = không giới hạn)")
    p.add_argument("--budget-seconds", type=int, default=0,
                   help="trần thời gian chạy, dừng sạch giữa hai bài (0 = không giới hạn)")
    a = p.parse_args()
    sys.exit(main(a.domain, a.limit, a.fetch, a.dry_run, dates_only=a.dates_only,
                  mode=a.mode, max_attempts=a.max_attempts,
                  retry_window_hours=a.retry_window_hours,
                  budget_seconds=a.budget_seconds))
