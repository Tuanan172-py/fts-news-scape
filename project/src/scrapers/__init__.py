"""Hold the central registry of news-source scrapers."""

from __future__ import annotations

from src.core.base_scraper import BaseScraper

REGISTRY: dict[str, type[BaseScraper]] = {}


def register(name: str):
    """Register a scraper class in the system registry under an identifier.

    Args:
        name: Identifier of the news source.

    Returns:
        Decorator that registers the scraper class.
    """
    def wrap(cls: type[BaseScraper]) -> type[BaseScraper]:
        REGISTRY[name] = cls
        return cls
    return wrap


# Import at the end of the file to trigger @register (safe against circular import: register is already defined).
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
