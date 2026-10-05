"""Sổ đăng ký tập trung các bộ thu thập dữ liệu nguồn tin (Scraper Registry)."""

from __future__ import annotations

from src.core.base_scraper import BaseScraper

REGISTRY: dict[str, type[BaseScraper]] = {}


def register(name: str):
    """Decorator đăng ký một lớp scraper vào sổ đăng ký hệ thống theo tên định danh.

    Args:
        name: Tên định danh của nguồn tin.

    Returns:
        Hàm bọc lớp scraper cần đăng ký.
    """
    def wrap(cls: type[BaseScraper]) -> type[BaseScraper]:
        REGISTRY[name] = cls
        return cls
    return wrap


# Import cuối file để trigger @register (an toàn circular: register đã định nghĩa)
from src.scrapers import (  # noqa: E402,F401
    baodautu,
    cafef,
    fireant,
    rss_capture,
    rss_generic,
    tnck,
    vietstock,
    vndirect,
    vneconomy,
)
