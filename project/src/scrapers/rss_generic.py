"""Bộ thu thập dữ liệu RSS feed chung dựa trên cấu hình khai báo (Generic RSS Scraper)."""

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
    """Làm sạch tiêu đề bằng cách loại bỏ thẻ HTML và giải mã các thực thể ký tự.

    Args:
        raw: Chuỗi tiêu đề gốc thô.

    Returns:
        Chuỗi tiêu đề đã làm sạch.
    """
    return html.unescape(_HTML_TAG.sub("", raw)).strip()


def _decode_feed(raw: bytes) -> str:
    """Giải mã dữ liệu nhị phân của RSS feed và chuẩn hóa khai báo XML.

    Args:
        raw: Mảng byte dữ liệu RSS feed tải về.

    Returns:
        Chuỗi văn bản XML của feed.
    """
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif b"\x00" in raw[:400]:
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    text = text.lstrip("﻿ \t\r\n")
    head, rest = text[:200], text[200:]
    return _XML_DECL_ENC.sub(r"\1", head, count=1) + rest


def _parse_raw_date(raw: str) -> str:
    """Phân tích chuỗi ngày tháng từ feed sang mốc thời gian ISO 8601 theo giờ Việt Nam.

    Args:
        raw: Chuỗi thời gian thô từ feed.

    Returns:
        Chuỗi thời gian chuẩn ISO 8601 hoặc rỗng nếu không phân tích được.
    """
    from email.utils import parsedate_to_datetime

    raw = raw.replace(" ", " ").strip()
    if not raw:
        return ""
    normalized = re.sub(r"GMT([+-])(\d{1,2})$",
                        lambda m: f"{m.group(1)}{int(m.group(2)):02d}00", raw)
    normalized = re.sub(r"([+-]\d{2})$", r"\g<1>00", normalized)
    dt = None
    try:
        dt = parsedate_to_datetime(normalized)
    except (ValueError, TypeError):
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    return dt.astimezone(VN_TZ).isoformat(timespec="seconds")


def _parse_entry_date(entry: dict) -> str:
    """Trích xuất và chuẩn hóa thời gian phát hành từ đối tượng RSS entry.

    Args:
        entry: Bản ghi entry từ feedparser.

    Returns:
        Chuỗi thời gian chuẩn ISO 8601.
    """
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        dt = datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(VN_TZ)
        return dt.isoformat(timespec="seconds")
    return _parse_raw_date(entry.get("published") or entry.get("updated") or "")


def _inline_content(entry: dict) -> str:
    """Trích xuất nội dung toàn văn nhúng sẵn trong thẻ content:encoded của feed nếu đạt kích thước tối thiểu.

    Args:
        entry: Bản ghi entry từ feedparser.

    Returns:
        Chuỗi nội dung toàn văn hoặc rỗng.
    """
    content = entry.get("content")
    if content and isinstance(content, list):
        value = content[0].get("value", "")
        if len(value) >= _MIN_INLINE_CONTENT:
            return value
    return ""


@register("_rss")
class RSSScraper(BaseScraper):
    """Lớp thu thập dữ liệu tổng quát cho các nguồn tin cung cấp giao diện RSS.

    Attributes:
        feeds: Danh sách cấu hình các RSS feed.
        extract_full: Cờ cho phép tải trang chi tiết bài viết.
        max_details: Số lượng bài chi tiết tối đa tải trong một chu kỳ.
        watchlist: Danh sách mã cổ phiếu theo dõi.
        language: Ngôn ngữ chính của nguồn tin.
        link_rewrites: Quy tắc viết lại đường dẫn liên kết nếu có lỗi cổng hoặc định dạng.
        filter_terms: Tập từ khóa lọc bài viết quan tâm.
        drop_unmatched: Cờ bỏ qua bài viết không khớp từ khóa lọc.
        block_terms: Tập từ khóa chặn bài viết rác.
    """

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        self.feeds = config.get("rss", {}).get("feeds", [])
        detail = config.get("detail", {})
        self.extract_full = detail.get("extract_full", True)
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self.link_rewrites = [(re.compile(r["pattern"]), r["replace"])
                              for r in config.get("link_rewrites", [])]
        filter_cfg = config.get("filter") or {}
        self.filter_terms = [str(t).lower() for t in filter_cfg.get("any", [])]
        self.drop_unmatched = filter_cfg.get("drop_unmatched", True)
        self.block_terms = [str(t).lower() for t in filter_cfg.get("none", [])]
        self._details_fetched = 0
        self._filtered = 0

    def fetch_list(self) -> list[dict]:
        """Lấy danh sách các bản ghi entry từ tất cả các RSS feed được cấu hình.

        Returns:
            Danh sách các dictionary chứa dữ liệu entry thô.
        """
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
        """Chuyển đổi một bản ghi RSS thô thành đối tượng Article sau khi lọc và làm sạch.

        Args:
            raw: Bản ghi dữ liệu thô của RSS entry.

        Returns:
            Đối tượng Article hoàn chỉnh hoặc None nếu không hợp lệ hoặc bị lọc bỏ.
        """
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
        """Bổ sung nội dung chi tiết bài viết từ thẻ inline hoặc tải trực tiếp từ trang nguồn.

        Args:
            article: Đối tượng Article cần bổ sung nội dung.
        """
        inline = article.metadata.pop("_inline_html", "")
        if inline:
            article.content_html = inline
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
