"""Capture NSO (General Statistics Office) periodic socio-economic reports by parsing the period from titles, storing HTML and downloading binary attachments (.xlsx, .docx, .pdf)."""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger

from src.core import paths
from src.core.models import now_vn_iso
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate

BASE_URL = "https://www.nso.gov.vn"
API_POSTS = f"{BASE_URL}/wp-json/wp/v2/posts"
SOURCE = "nso"
SOURCE_DOMAIN = "nso.gov.vn"
KTXH_TAG = 727

_ATTACH_EXT = (".xlsx", ".xls", ".docx", ".doc", ".pdf")

_MONTH_WORDS = {
    "một": 1, "mot": 1, "giêng": 1, "gieng": 1,
    "hai": 2, "ba": 3, "tư": 4, "tu": 4, "bốn": 4, "bon": 4,
    "năm": 5, "nam": 5, "sáu": 6, "sau": 6, "bảy": 7, "bay": 7,
    "tám": 8, "tam": 8, "chín": 9, "chin": 9, "mười": 10, "muoi": 10,
    "mười một": 11, "muoi mot": 11, "mười hai": 12, "muoi hai": 12,
}
_QUARTER_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


def _strip_accents(text: str) -> str:
    """Remove Vietnamese diacritics from a string."""
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def parse_period(title: str) -> tuple[str, str] | None:
    """Parse a Vietnamese report title to determine the report type and time period.

    Args:
        title: Title of the post announcing the report.

    Returns:
        Tuple of the report type ('monthly', 'quarterly', 'annual') and the period (for
        example '2026-08', '2026-Q2'), or None when the period cannot be identified with
        certainty.
    """
    if not title:
        return None
    raw = " ".join(title.split())
    low = _strip_accents(raw).lower()

    m_year = re.search(r"\bnam\s+(\d{4})\b", low) or re.search(r"\b(20\d{2})\b", low)
    if not m_year:
        return None
    year = int(m_year.group(1))

    m_q = re.search(r"\bquy\s+(i{1,3}v?|iv)\b", low)
    if m_q:
        q = _QUARTER_ROMAN.get(m_q.group(1))
        if q:
            return "quarterly", f"{year}-Q{q}"

    m_num = re.search(r"\bthang\s+(\d{1,2})\b", low)
    if m_num:
        mo = int(m_num.group(1))
        if 1 <= mo <= 12:
            return "monthly", f"{year}-{mo:02d}"

    m_word = re.search(r"\bthang\s+(muoi hai|muoi mot|muoi|mot|hai|ba|tu|bon|nam|"
                       r"sau|bay|tam|chin|gieng)\b", low)
    if m_word:
        mo = _MONTH_WORDS.get(m_word.group(1))
        if mo:
            return "monthly", f"{year}-{mo:02d}"

    if re.search(r"\bca\s+nam\b|\bnam\s+\d{4}\b", low) and "thang" not in low:
        return "annual", str(year)
    return None


def extract_attachments(html: str, page_url: str) -> list[dict]:
    """Extract attachment links (.xlsx, .docx, .pdf) from HTML source.

    Args:
        html: HTML source of the article detail page.
        page_url: URL of the original article page.

    Returns:
        One dict per attachment with its URL, file name and label.
    """
    out: list[dict] = []
    seen: set[str] = set()
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[nso] attachment parse failed: {}", e)
        return out
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(page_url, href)
        path = urlparse(absolute).path
        # Lowercase only to match the extension; the file name keeps its original case for Bronze.
        if not path.lower().endswith(_ATTACH_EXT):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append({"url": absolute,
                    "filename": path.rsplit("/", 1)[-1],
                    "label": a.get_text(" ", strip=True)[:200]})
    return out


def _safe_key(period: str, filename: str) -> str:
    """Build the storage key without a file extension.

    `save_binary` appends the extension from the Content-Type, so the extension is dropped
    here to avoid `.xlsx.xlsx`.
    """
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-")[:80]
    return f"{period}__{stem}"


class PeriodicReportSource:
    """Drive the capture of NSO periodic reports; errors are collected in `errors` and never raised.

    Attributes:
        http: HTTP client used for all requests.
        store: Store that provides the operational DB connection.
        raw_store: RawStore that writes the Bronze report files.
        tag: WordPress tag id of the socio-economic reports.
        timeout: Per-request timeout in seconds.
        fetch_attachments: Whether binary attachments are downloaded.
        robots: RobotsGate, or None when robots.txt is not respected.
        errors: Error messages collected during the last run.
    """

    def __init__(self, http, store, *, raw_dir: str | None = None,
                 tag: int = KTXH_TAG, respect_robots: bool = True,
                 timeout: int = 30, fetch_attachments: bool = True):
        """Initialize the report source.

        Args:
            http: HTTP client used for all requests.
            store: Store that provides the operational DB connection.
            raw_dir: Directory for raw report files; defaults to `paths.raw_reports_dir()`.
            tag: WordPress tag id of the socio-economic reports.
            respect_robots: Check robots.txt before each request.
            timeout: Per-request timeout in seconds.
            fetch_attachments: Download binary attachments.
        """
        self.http = http
        self.store = store
        self.raw_store = RawStore(raw_dir or paths.raw_reports_dir())
        self.tag = tag
        self.timeout = timeout
        self.fetch_attachments = fetch_attachments
        self.robots = RobotsGate(http) if respect_robots else None
        self.errors: list[str] = []

    # -- 1. DISCOVER ---------------------------------------------------------
    def discover(self, *, after: str = "", per_page: int = 20,
                 pages: int = 1) -> list[dict]:
        """List posts under the KTXH tag.

        Args:
            after: ISO date for incremental sync; empty fetches without a lower bound.
            per_page: Number of posts per API page.
            pages: Maximum number of API pages to fetch.

        Returns:
            Raw post dicts from the WordPress API.
        """
        found: list[dict] = []
        for page in range(1, pages + 1):
            params = {"tags": self.tag, "per_page": per_page, "page": page,
                      "orderby": "date", "order": "desc"}
            if after:
                params["after"] = after
            resp = self.http.get_response(API_POSTS, params=params,
                                          headers={"Accept": "application/json"},
                                          timeout=self.timeout)
            if resp is None or getattr(resp, "status_code", None) != 200:
                self.errors.append(
                    f"discover failed page {page}: "
                    f"HTTP {getattr(resp, 'status_code', None)}")
                break
            try:
                posts = json.loads(resp.content.decode(
                    getattr(resp, "encoding", None) or "utf-8", errors="replace"))
            except (ValueError, AttributeError):
                self.errors.append(f"discover invalid JSON page {page}")
                break
            if not isinstance(posts, list) or not posts:
                break
            found.extend(posts)
            if len(posts) < per_page:
                break
        return found

    # -- 2/3. IDENTIFY + DEDUP ----------------------------------------------
    @staticmethod
    def identify(post: dict) -> tuple[str, str] | None:
        """Identify the report type and period of a post from its title.

        Args:
            post: Post dict from the WordPress API.

        Returns:
            Tuple of report type and period, or None when the period cannot be parsed.
        """
        title = ((post.get("title") or {}).get("rendered") or "").strip()
        # WordPress returns HTML entities in the title (&#8211;), so unescape before parsing.
        try:
            title = BeautifulSoup(title, "lxml").get_text(" ", strip=True)
        except Exception:  # pragma: no cover - defensive
            pass
        return parse_period(title)

    def _existing(self, report_type: str, period: str) -> dict | None:
        conn = self.store.connect()
        try:
            row = conn.execute(
                "SELECT * FROM periodic_reports WHERE source=? AND report_type=? "
                "AND period=? ORDER BY revision DESC LIMIT 1",
                (SOURCE, report_type, period)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # -- 4. CAPTURE ----------------------------------------------------------
    def _capture_report(self, post: dict, report_type: str, period: str,
                        revision: int) -> dict:
        link = (post.get("link") or "").strip()
        fetched_at = now_vn_iso()
        result = {"capture_status": "failed", "html_path": "", "attachments": []}

        if self.robots is not None and not self.robots.allowed(link):
            result["capture_status"] = "skipped_robots"
            self.errors.append(f"robots disallow: {link}")
            return result

        key = f"{report_type}-{period}-r{revision}"
        resp = self.http.get_response(link, timeout=self.timeout)
        cap = self.raw_store.save(SOURCE_DOMAIN, link, key, resp,
                                  fetched_at=fetched_at)
        result["capture_status"] = cap.get("capture_status", "failed")
        result["html_path"] = paths.to_data_relative(cap["html_path"]) if cap.get("html_path") else ""
        if cap.get("capture_status") != "ok" or resp is None:
            self.errors.append(f"report capture failed: {link}")
            return result

        html = resp.content.decode(getattr(resp, "encoding", None) or "utf-8",
                                   errors="replace")
        attach = extract_attachments(html, link)
        if not attach:
            logger.info("[nso] no attachment found for {} {}", report_type, period)
        if not self.fetch_attachments:
            result["attachments"] = [dict(a, path="", sha256="") for a in attach]
            return result

        saved: list[dict] = []
        for item in attach:
            if self.robots is not None and not self.robots.allowed(item["url"]):
                self.errors.append(f"robots disallow attachment: {item['url']}")
                continue
            aresp = self.http.get_response(item["url"], timeout=self.timeout)
            acap = self.raw_store.save_binary(
                SOURCE_DOMAIN, item["url"], _safe_key(key, item["filename"]),
                aresp, fetched_at=fetched_at)
            if acap.get("capture_status") != "ok":
                self.errors.append(f"attachment failed: {item['url']}")
            saved.append({**item,
                          "path": (paths.to_data_relative(acap["binary_path"])
                                   if acap.get("binary_path") else ""),
                          "sha256": acap.get("content_sha256"),
                          "bytes": acap.get("content_length_bytes", 0),
                          "content_type": acap.get("content_type", ""),
                          "capture_status": acap.get("capture_status")})
        result["attachments"] = saved
        return result

    # -- orchestration -------------------------------------------------------
    def run(self, *, after: str = "", per_page: int = 20, pages: int = 1,
            limit: int = 0) -> dict:
        """Run discover, identify, dedup and capture in order.

        Args:
            after: ISO date for incremental sync.
            per_page: Number of posts per API page.
            pages: Maximum number of API pages to fetch.
            limit: Maximum number of posts to process; 0 means no limit.

        Returns:
            Counter dict with keys discovered, captured, revised, skipped_unchanged,
            held_unparsed, failed, attachments.
        """
        self.errors = []
        summary = {"discovered": 0, "captured": 0, "revised": 0,
                   "skipped_unchanged": 0, "held_unparsed": 0, "failed": 0,
                   "attachments": 0}
        posts = self.discover(after=after, per_page=per_page, pages=pages)
        summary["discovered"] = len(posts)
        if limit:
            posts = posts[:limit]

        for post in posts:
            ident = self.identify(post)
            if ident is None:
                # Never guess the report period: hold the post and warn for manual review.
                title = ((post.get("title") or {}).get("rendered") or "")[:120]
                summary["held_unparsed"] += 1
                self.errors.append(f"cannot parse period from title: {title!r}")
                logger.warning("[nso] HELD — không parse được kỳ: {!r}", title)
                continue
            report_type, period = ident
            modified = (post.get("modified") or "").strip()
            prev = self._existing(report_type, period)

            if prev and (prev.get("modified_at") or "") == modified:
                summary["skipped_unchanged"] += 1
                continue

            revision = (prev.get("revision", 1) + 1) if prev else 1
            cap = self._capture_report(post, report_type, period, revision)
            if cap["capture_status"] not in ("ok", "partial"):
                summary["failed"] += 1
                continue

            self._upsert(post, report_type, period, revision, cap)
            summary["attachments"] += len(cap["attachments"])
            if prev:
                summary["revised"] += 1
                logger.info("[nso] BẢN HIỆU ĐÍNH {} {} → revision {}",
                            report_type, period, revision)
            else:
                summary["captured"] += 1
        return summary

    def _upsert(self, post: dict, report_type: str, period: str, revision: int,
                cap: dict) -> None:
        title = ((post.get("title") or {}).get("rendered") or "").strip()
        now = now_vn_iso()
        conn = self.store.connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO periodic_reports "
                "(source, report_type, period, title, source_url, remote_id, "
                " published_at, modified_at, html_path, attachments_json, "
                " capture_status, revision, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (SOURCE, report_type, period, title, (post.get("link") or ""),
                 str(post.get("id") or ""), (post.get("date") or ""),
                 (post.get("modified") or ""), cap["html_path"],
                 json.dumps(cap["attachments"], ensure_ascii=False),
                 cap["capture_status"], revision, now, now))
            conn.commit()
        finally:
            conn.close()
