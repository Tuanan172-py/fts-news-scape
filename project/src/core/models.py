"""
Core models — Article, ScrapeResult và dedup hash.

Đây là nguồn sự thật duy nhất cho schema article và hash dedup
(SHA-256 của url + title, spec §9 bước 5).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


def sha256_hash(url: str, title: str) -> str:
    """SHA-256 của url + title — dùng thống nhất cho dedup toàn hệ thống."""
    return hashlib.sha256(f"{url}{title}".encode("utf-8")).hexdigest()


def now_vn_iso() -> str:
    """Thời điểm hiện tại theo giờ VN, ISO 8601."""
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


@dataclass
class Article:
    """Bản ghi bài viết chuẩn hoá — mọi scraper đều trả về model này.

    content_html giữ HTML nguyên bản (spec §9: không throw away data);
    content_text là text sạch đã bóc tách.

    metadata["capture"] (điền bởi RawStore qua CaptureMixin): con trỏ tới raw
    artifact + trạng thái thu thập. Keys: html_path, content_sha256, http_status,
    response_headers (subset), fetch_ts, render_method, capture_status
    (ok|partial|failed|skipped_robots), missing[], error, images[] (read-only
    manifest: outer_tag/resolved_url/alt/title/caption). Raw .html là byte-exact,
    KHÔNG bao giờ bị sửa.
    """

    url: str
    title: str
    source_domain: str
    summary: str = ""
    content_html: str = ""
    content_text: str = ""
    published_at: str = ""          # ISO 8601, timezone VN
    author: str = ""
    symbols: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sentiment: str = ""             # positive | negative | neutral (Phase 4)
    sentiment_score: float | None = None
    fetched_at: str = field(default_factory=now_vn_iso)
    processed_at: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def url_title_hash(self) -> str:
        return sha256_hash(self.url, self.title)

    def to_row(self) -> dict:
        """Dict theo tên cột bảng `articles` (schema v2)."""
        return {
            "url": self.url,
            "url_title_hash": self.url_title_hash,
            "title": self.title,
            "summary": self.summary,
            "content_html": self.content_html,
            "content_text": self.content_text,
            "published_at": self.published_at,
            "author": self.author,
            "source_domain": self.source_domain,
            "symbols": ",".join(self.symbols),
            "categories": ",".join(self.categories),
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
            "fetched_at": self.fetched_at,
            "processed_at": self.processed_at,
            "metadata_json": json.dumps(self.metadata, ensure_ascii=False) if self.metadata else "",
        }

    @classmethod
    def from_row(cls, row) -> "Article":
        """Khôi phục Article từ sqlite3.Row."""
        return cls(
            url=row["url"],
            title=row["title"],
            source_domain=row["source_domain"],
            summary=row["summary"] or "",
            content_html=row["content_html"] or "",
            content_text=row["content_text"] or "",
            published_at=row["published_at"] or "",
            author=row["author"] or "",
            symbols=[s for s in (row["symbols"] or "").split(",") if s],
            categories=[c for c in (row["categories"] or "").split(",") if c],
            sentiment=row["sentiment"] or "",
            sentiment_score=row["sentiment_score"],
            fetched_at=row["fetched_at"] or "",
            processed_at=row["processed_at"] or "",
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
        )


@dataclass
class ScrapeResult:
    """Kết quả 1 lần chạy scraper — orchestrator dùng cho metrics/monitoring."""

    scraper: str
    fetched: int = 0
    new: list[Article] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.errors
