"""Match articles against configured notification rules (ticker, source domain, keyword) and write them to the console and a daily log file."""

from __future__ import annotations

from src.core import paths
import re
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

from src.core.models import VN_TZ, Article, ScrapeResult


class FileNotifier:
    """Filter articles by rule and send matching notifications to a log file or stdout.

    Attributes:
        out_dir: Directory of the daily notification log files.
        rules: Rules that filter and tag notifications.
        SENTIMENT_MARKER: Marker shown in front of an article line, keyed by sentiment label.
    """

    def __init__(
        self,
        config_path: str = "config/notifications.yaml",
        out_dir: str | None = None,
    ):
        """Load the notification rules and prepare the output directory.

        Args:
            config_path: Path of the notification rules YAML; missing file means no rules.
            out_dir: Output directory for the daily logs. Defaults to `paths.notifications_dir()`.
        """
        self.out_dir = paths.resolve_data_path(out_dir) if out_dir else paths.notifications_dir()
        self.rules = []
        p = Path(config_path)
        if p.exists():
            cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            self.rules = cfg.get("rules", [])
        for rule in self.rules:
            ticks = rule.get("tickers")
            if ticks:
                rule["_ticker_re"] = re.compile(
                    r"\b(" + "|".join(re.escape(t) for t in ticks) + r")\b"
                )

    def _log_path(self) -> Path:
        """Return the log file path for the current day."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return self.out_dir / f"{datetime.now(VN_TZ):%Y-%m-%d}.log"

    def _matches(self, article: Article) -> str | None:
        """Check whether an article matches any notification rule.

        Args:
            article: Article to check.

        Returns:
            Tag of the first matching rule, or None if no rule matches.
        """
        text = f"{article.title} {' '.join(article.symbols)}"
        haystack = text.lower()
        for rule in self.rules:
            tag = rule.get("tag", "match")
            tre = rule.get("_ticker_re")
            if tre is not None and tre.search(text):
                return tag
            srcs = rule.get("sources")
            if srcs and article.source_domain in srcs:
                return tag
            if rule.get("has_symbol") and article.symbols:
                return tag
            match = rule.get("match", {})
            if match is True or match == "all":
                return tag
            if isinstance(match, dict):
                for kw in match.get("any", []):
                    if str(kw).lower() in haystack:
                        return tag
        return None

    SENTIMENT_MARKER = {"positive": "🟢", "negative": "🔴", "neutral": "🟡"}

    def format_article(self, a: Article, tag: str = "") -> str:
        """Format an article as a one-line notification.

        Args:
            a: Article to format.
            tag: Tag of the matching notification rule.

        Returns:
            One-line text describing the article.
        """
        marker = self.SENTIMENT_MARKER.get(a.sentiment, "🟡")
        return f"{marker} {a.title} (chi tiết ({a.url}))"

    def notify_articles(self, articles: list[Article]) -> int:
        """Write the articles that match a rule to the console and the log file.

        Args:
            articles: Articles to filter and notify.

        Returns:
            Number of articles that matched a notification rule.
        """
        matched = 0
        lines = []
        for a in articles:
            tag = self._matches(a)
            if tag is None:
                continue
            matched += 1
            line = self.format_article(a, tag)
            lines.append(line)
            print(line)
        if lines:
            with self._log_path().open("a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        return matched

    def notify_cycle_summary(self, results: list[ScrapeResult]) -> None:
        """Print the scrape cycle summary to the console and the logger.

        Args:
            results: ScrapeResult of each source.
        """
        parts = []
        for r in results:
            if r.fetched == 0 and r.errors:
                err = r.errors[0]
                if len(err) > 80:
                    err = err[:80] + "…"
                parts.append(f"{r.scraper}: FAILED ({err})")
            else:
                parts.append(f"{r.scraper}: {len(r.new)} new")
        line = f"{datetime.now(VN_TZ):%H:%M:%S} [cycle] " + " | ".join(parts)
        print(line)
        logger.info("Cycle summary: {}", " | ".join(parts))
