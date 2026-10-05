"""Bộ thu thập và xử lý báo cáo định kỳ kinh tế - xã hội của Tổng cục Thống kê (NSO).

Driver xử lý chuyên biệt cho các báo cáo định kỳ theo tháng, quý, năm; bóc tách kỳ
báo cáo từ tiêu đề, lưu trữ nội dung HTML và tải tệp đính kèm nhị phân (.xlsx, .docx, .pdf).
"""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger

from src.core.models import now_vn_iso
from src.crawler.raw_store import RawStore
from src.crawler.robots import RobotsGate

BASE_URL = "https://www.nso.gov.vn"
API_POSTS = f"{BASE_URL}/wp-json/wp/v2/posts"
SOURCE = "nso"
SOURCE_DOMAIN = "nso.gov.vn"
KTXH_TAG = 727

_ATTACH_EXT = (".xlsx", ".xls", ".docx", ".doc", ".pdf")
RAW_REPORTS_DIR = "data/raw_reports"

_MONTH_WORDS = {
    "một": 1, "mot": 1, "giêng": 1, "gieng": 1,
    "hai": 2, "ba": 3, "tư": 4, "tu": 4, "bốn": 4, "bon": 4,
    "năm": 5, "nam": 5, "sáu": 6, "sau": 6, "bảy": 7, "bay": 7,
    "tám": 8, "tam": 8, "chín": 9, "chin": 9, "mười": 10, "muoi": 10,
    "mười một": 11, "muoi mot": 11, "mười hai": 12, "muoi hai": 12,
}
_QUARTER_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


def _strip_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt khỏi chuỗi văn bản."""
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def parse_period(title: str) -> tuple[str, str] | None:
    """Phân tích tiêu đề báo cáo tiếng Việt để xác định loại báo cáo và kỳ thời gian.

    Args:
        title: Tiêu đề bài viết thông báo báo cáo.

    Returns:
        Tuple gồm loại báo cáo ('monthly', 'quarterly', 'annual') và kỳ báo cáo (ví dụ: '2026-08', '2026-Q2'),
        hoặc None nếu không nhận diện chắc chắn được kỳ.
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
    """Trích xuất danh sách liên kết tệp đính kèm (.xlsx, .docx, .pdf) từ mã nguồn HTML.

    Args:
        html: Mã nguồn HTML chi tiết bài viết.
        page_url: Đường dẫn URL trang bài viết gốc.

    Returns:
        Danh sách đối tượng từ điển chứa URL, tên tệp và nhãn của tệp đính kèm.
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
        # chỉ hạ chữ để SO KHỚP đuôi — tên file giữ nguyên case gốc cho Bronze
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
    """`save_binary` tự gắn đuôi theo Content-Type → bỏ đuôi ở đây, tránh `.xlsx.xlsx`."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-")[:80]
    return f"{period}__{stem}"


class PeriodicReportSource:
    """Driver báo cáo định kỳ NSO. Không raise ra ngoài — lỗi gom vào self.errors."""

    def __init__(self, http, store, *, raw_dir: str = RAW_REPORTS_DIR,
                 tag: int = KTXH_TAG, respect_robots: bool = True,
                 timeout: int = 30, fetch_attachments: bool = True):
        self.http = http
        self.store = store
        self.raw_store = RawStore(raw_dir)
        self.tag = tag
        self.timeout = timeout
        self.fetch_attachments = fetch_attachments
        self.robots = RobotsGate(http) if respect_robots else None
        self.errors: list[str] = []

    # -- 1. DISCOVER ---------------------------------------------------------
    def discover(self, *, after: str = "", per_page: int = 20,
                 pages: int = 1) -> list[dict]:
        """Danh sách post theo tag KTXH. `after` = ISO date để sync tăng dần."""
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
        title = ((post.get("title") or {}).get("rendered") or "").strip()
        # WordPress trả HTML entity trong title (&#8211;) → unescape trước khi parse
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
        result["html_path"] = cap.get("html_path", "")
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
                          "path": acap.get("binary_path", ""),
                          "sha256": acap.get("content_sha256"),
                          "bytes": acap.get("content_length_bytes", 0),
                          "content_type": acap.get("content_type", ""),
                          "capture_status": acap.get("capture_status")})
        result["attachments"] = saved
        return result

    # -- orchestration -------------------------------------------------------
    def run(self, *, after: str = "", per_page: int = 20, pages: int = 1,
            limit: int = 0) -> dict:
        """Discover → identify → dedup → capture. Trả summary dict."""
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
                # KHÔNG đoán bừa kỳ báo cáo — held + cảnh báo để người xem lại
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
