"""Define the core data models and the dedup hash."""

from __future__ import annotations

import hashlib
import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


def sha256_hash(url: str, title: str) -> str:
    """Compute the SHA-256 hash of an article URL and title.

    Args:
        url: Article URL.
        title: Article title.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    return hashlib.sha256(f"{url}{title}".encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    """Normalize an article title to lowercase with single spaces.

    Args:
        title: Original title.

    Returns:
        Normalized title.
    """
    return re.sub(r"\s+", " ", str(title).strip().lower())


def now_vn_iso() -> str:
    """Return the current time in the Vietnam time zone (UTC+7) as an ISO 8601 string.

    Returns:
        ISO 8601 timestamp with second precision.
    """
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


@dataclass
class Article:
    """Hold the normalized data of one article.

    Attributes:
        url: Article URL.
        title: Article title.
        source_domain: Domain of the news source.
        summary: Summary or lead paragraph (`sapo`).
        content_html: Extracted original HTML content.
        content_text: Plain text of the article.
        published_at: Publication time in ISO 8601 (+07:00).
        author: Author or publishing body.
        symbols: Related stock tickers.
        categories: Section categories.
        sentiment: Sentiment label (positive, negative, neutral).
        sentiment_score: Numeric sentiment score.
        fetched_at: Time the article was fetched.
        processed_at: Time processing finished.
        metadata: Metadata and Bronze capture state.
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
        """Hash of the URL and title used as the dedup key."""
        return sha256_hash(self.url, self.title)

    def to_row(self) -> dict:
        """Convert the Article to a dict matching the `articles` table schema.

        Returns:
            Dict of field values keyed by SQLite column name.
        """
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
        """Rebuild an Article from a sqlite3.Row.

        Args:
            row: Row read from the SQLite database.

        Returns:
            The restored Article.
        """
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
    """Hold the outcome of one scrape cycle of a scraper.

    Attributes:
        scraper: Scraper name.
        fetched: Total number of articles found.
        new: Newly collected articles.
        errors: Error messages raised during the cycle.
        duration_s: Execution time in seconds.
    """

    scraper: str
    fetched: int = 0
    new: list[Article] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        """Whether the cycle finished without errors."""
        return not self.errors
