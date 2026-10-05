"""Mô hình dữ liệu lõi và định nghĩa mã băm chống trùng lặp."""

from __future__ import annotations

import hashlib
import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


def sha256_hash(url: str, title: str) -> str:
    """Tính chuỗi mã băm SHA-256 từ URL và tiêu đề bài viết.

    Args:
        url: Địa chỉ liên kết của bài viết.
        title: Tiêu đề của bài viết.

    Returns:
        Chuỗi hex biểu diễn mã băm SHA-256.
    """
    return hashlib.sha256(f"{url}{title}".encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    """Chuẩn hóa tiêu đề bài viết về dạng chữ thường và khoảng trắng đơn.

    Args:
        title: Tiêu đề gốc cần xử lý.

    Returns:
        Chuỗi tiêu đề đã chuẩn hóa.
    """
    return re.sub(r"\s+", " ", str(title).strip().lower())


def now_vn_iso() -> str:
    """Lấy mốc thời gian hiện tại theo múi giờ Việt Nam (UTC+7) định dạng ISO 8601.

    Returns:
        Chuỗi thời gian chuẩn ISO 8601.
    """
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


@dataclass
class Article:
    """Đối tượng lưu trữ thông tin bài viết chuẩn hóa.

    Attributes:
        url: Đường dẫn truy cập bài viết.
        title: Tiêu đề bài viết.
        source_domain: Tên miền của nguồn tin.
        summary: Đoạn tóm tắt hoặc nội dung sapo.
        content_html: Nội dung HTML nguyên bản đã bóc tách.
        content_text: Văn bản thuần của bài viết.
        published_at: Thời điểm phát hành định dạng ISO 8601 (+07:00).
        author: Tên tác giả hoặc cơ quan phát hành.
        symbols: Danh sách mã cổ phiếu liên quan.
        categories: Danh sách chuyên mục phân loại.
        sentiment: Nhãn sắc thái (positive, negative, neutral).
        sentiment_score: Điểm định lượng sắc thái.
        fetched_at: Thời điểm thu thập dữ liệu.
        processed_at: Thời điểm hoàn tất xử lý.
        metadata: Từ điển chứa siêu dữ liệu và trạng thái capture Bronze.
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
        """Chuyển đổi đối tượng Article thành dictionary tương thích schema bảng articles.

        Returns:
            Dictionary chứa các trường dữ liệu tương ứng với cột trong SQLite.
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
        """Khôi phục đối tượng Article từ bản ghi sqlite3.Row.

        Args:
            row: Bản ghi dữ liệu từ cơ sở dữ liệu SQLite.

        Returns:
            Đối tượng Article đã được khôi phục.
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
    """Kết quả thực thi một chu kỳ thu thập dữ liệu của scraper.

    Attributes:
        scraper: Tên định danh của scraper.
        fetched: Tổng số bài viết tìm thấy.
        new: Danh sách các bài viết mới thu thập.
        errors: Danh sách thông điệp lỗi phát sinh.
        duration_s: Thời gian thực thi tính bằng giây.
    """

    scraper: str
    fetched: int = 0
    new: list[Article] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.errors
