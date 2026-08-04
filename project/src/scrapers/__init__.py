"""
Scraper registry — map tên domain → class.

Thêm domain mới: viết module trong src/scrapers/ + đăng ký vào REGISTRY
+ tạo config/domains/<name>.yaml. Không sửa orchestrator (spec §12).
"""

from __future__ import annotations

from src.core.base_scraper import BaseScraper

REGISTRY: dict[str, type[BaseScraper]] = {}


def register(name: str):
    """Decorator: @register("cafef") trên subclass BaseScraper."""
    def wrap(cls: type[BaseScraper]) -> type[BaseScraper]:
        REGISTRY[name] = cls
        return cls
    return wrap


# Import cuối file để trigger @register (an toàn circular: register đã định nghĩa)
from src.scrapers import cafef, fireant, rss_generic, tnck, vndirect  # noqa: E402,F401
