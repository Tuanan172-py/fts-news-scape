"""
Generic RSS scraper — 1 class, N domain configs (method: rss).

Domain RSS mới = 1 file YAML, zero code (spec §12 config-driven).
Feed-level isolation: 1 feed chết → WARN + tiếp feed khác.
Nếu feed có content:encoded đủ dài (vd VnEconomy) → dùng luôn, khỏi fetch detail.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser
from loguru import logger

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import VN_TZ, Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_content, extract_text
from src.scrapers import register

_MIN_INLINE_CONTENT = 500  # content:encoded ngắn hơn → vẫn fetch detail


_XML_DECL_ENC = re.compile(r'(<\?xml[^>]*?)\s+encoding=["\'][^"\']*["\']', re.I)
_HTML_TAG = re.compile(r"<[^>]+>")


def _clean_title(raw: str) -> str:
    """Strip tag HTML (hose bọc <span>) + unescape entity double-encoded
    (thanhnien '&aacute;', vietnambiz '&#225;' — feedparser chỉ decode 1 lớp).
    Title dùng cho dedup-hash + tag mã CK + sentiment nên phải sạch."""
    return html.unescape(_HTML_TAG.sub("", raw)).strip()


def _decode_feed(raw: bytes) -> str:
    """Encoding hardening — vietnambiz utf-16, dantri/fed BOM, baodautu blank lines.

    Heuristic null-byte chỉ soi 400 bytes đầu (vùng XML declaration).
    """
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")                        # BOM utf-16
    elif b"\x00" in raw[:400]:
        text = raw.decode("utf-16", errors="replace")      # utf-16 không BOM
    else:
        text = raw.decode("utf-8-sig", errors="replace")   # strip BOM utf-8 nếu có
    text = text.lstrip("﻿ \t\r\n")   # BOM escape tường minh + blank lines (baodautu)
    # vietnambiz khai encoding="utf-16" nhưng serve utf-8 — feedparser tôn trọng
    # declaration kể cả với str input → đã decode xong thì bỏ encoding attr
    head, rest = text[:200], text[200:]
    return _XML_DECL_ENC.sub(r"\1", head, count=1) + rest


def _parse_raw_date(raw: str) -> str:
    """Fallback cho format phi chuẩn feedparser bó tay (verified 2026-07-25):
    vietnambiz 'GMT+7', cafebiz '+07', tuoitre '7/25/2026 7:39:00 PM'."""
    from email.utils import parsedate_to_datetime

    raw = raw.replace(" ", " ").strip()
    if not raw:
        return ""
    # GMT+7 / GMT+10 → +0700 / +1000
    normalized = re.sub(r"GMT([+-])(\d{1,2})$",
                        lambda m: f"{m.group(1)}{int(m.group(2)):02d}00", raw)
    normalized = re.sub(r"([+-]\d{2})$", r"\g<1>00", normalized)  # +07 → +0700
    # ('+0700' đầy đủ không match rule trên — sign không nằm ở vị trí -3)
    dt = None
    try:
        dt = parsedate_to_datetime(normalized)
    except (ValueError, TypeError):
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):  # tuoitre US-style
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)   # không có tz → coi là giờ VN
    return dt.astimezone(VN_TZ).isoformat(timespec="seconds")


def _parse_entry_date(entry: dict) -> str:
    """struct_time (UTC-normalized bởi feedparser) → ISO giờ VN; fallback raw string."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        dt = datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(VN_TZ)
        return dt.isoformat(timespec="seconds")
    return _parse_raw_date(entry.get("published") or entry.get("updated") or "")


def _inline_content(entry: dict) -> str:
    """Lấy content:encoded nếu có (feedparser: entry.content[0].value)."""
    content = entry.get("content")
    if content and isinstance(content, list):
        value = content[0].get("value", "")
        if len(value) >= _MIN_INLINE_CONTENT:
            return value
    return ""


@register("_rss")
class RSSScraper(BaseScraper):
    """Scraper cho mọi domain method: rss. Registry key '_rss' = generic."""

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        self.feeds = config.get("rss", {}).get("feeds", [])
        detail = config.get("detail", {})
        self.extract_full = detail.get("extract_full", True)
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        # sửa link hỏng trong feed (vd HNX kèm port nội bộ :7978)
        self.link_rewrites = [(re.compile(r["pattern"]), r["replace"])
                              for r in config.get("link_rewrites", [])]
        filter_cfg = config.get("filter") or {}
        self.filter_terms = [str(t).lower() for t in filter_cfg.get("any", [])]
        self.drop_unmatched = filter_cfg.get("drop_unmatched", True)
        # block-list: bài chứa BẤT KỲ term nào bị loại (vd Yahoo lifestyle/retail-finance)
        self.block_terms = [str(t).lower() for t in filter_cfg.get("none", [])]
        self._details_fetched = 0
        self._filtered = 0

    def fetch_list(self) -> list[dict]:
        self._details_fetched = 0
        self._filtered = 0
        items: list[dict] = []
        for feed_cfg in self.feeds:
            feed_url = feed_cfg["url"]
            feed_name = feed_cfg.get("name", feed_url)
            raw = self.http.get_bytes(feed_url, timeout=self.config.get("timeout", 30))
            if raw is None:
                self.errors.append(f"feed fetch failed: {feed_name}")
                continue
            feed = feedparser.parse(_decode_feed(raw))
            if feed.bozo and not feed.entries:
                self.errors.append(f"feed parse failed: {feed_name}")
                continue
            for e in feed.entries:
                items.append({
                    "link": (e.get("link") or "").strip(),
                    "title": (e.get("title") or "").strip(),
                    "summary": (e.get("summary") or "").strip(),
                    "author": (e.get("author") or "").strip(),
                    "published_parsed": e.get("published_parsed"),
                    "updated_parsed": e.get("updated_parsed"),
                    "published": e.get("published"),
                    "updated": e.get("updated"),
                    "content": e.get("content"),
                    "_feed_name": feed_name,
                })
        return items

    def parse_item(self, raw: dict) -> Article | None:
        url, title = raw["link"], _clean_title(raw["title"])
        if not url or not title:
            return None
        for pattern, replace in self.link_rewrites:
            url = pattern.sub(replace, url)
        summary_text = extract_text(raw["summary"]) if "<" in raw["summary"] \
            else html.unescape(raw["summary"])

        if self.block_terms or (self.filter_terms and self.drop_unmatched):
            haystack = f"{title} {summary_text}".lower()
            if any(t in haystack for t in self.block_terms):
                self._filtered += 1
                logger.debug("[{}] blocked: {}", self.name, title[:60])
                return None
            if self.filter_terms and self.drop_unmatched \
                    and not any(t in haystack for t in self.filter_terms):
                self._filtered += 1
                logger.debug("[{}] filtered out: {}", self.name, title[:60])
                return None

        return Article(
            url=url,
            title=title,
            source_domain=urlparse(url).netloc.removeprefix("www."),
            summary=summary_text,
            published_at=_parse_entry_date(raw),
            author=raw["author"],
            symbols=tag_tickers(f"{title} {summary_text}", self.watchlist),
            categories=[raw["_feed_name"]],
            metadata={"feed_name": raw["_feed_name"],
                      "language": self.language,
                      "_inline_html": _inline_content(raw)},
        )

    def enrich(self, article: Article) -> None:
        inline = article.metadata.pop("_inline_html", "")
        if inline:
            # content:encoded đầy đủ trong feed — không cần fetch
            article.content_html = inline
            article.content_text = extract_text(inline) or article.summary
            return
        if not self.extract_full:
            article.content_text = article.summary
            return
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self.http.get(article.url, timeout=self.config.get("timeout", 30))
        if html is None:
            article.content_text = article.summary
            self.errors.append(f"detail fetch failed: {article.url}")
            return
        self._details_fetched += 1
        result = extract_content(article.url, html=html)
        article.content_html = result["raw_html"]
        article.content_text = result["content"] or article.summary
