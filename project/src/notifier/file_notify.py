"""
File-based notify (spec §11: chỉ log file + stdout, không Telegram phase này).

Rules từ config/notifications.yaml: match.any keywords trên title + symbols.
Matched article → dòng vào data/notifications/YYYY-MM-DD.log + stdout.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

from src.core.models import VN_TZ, Article, ScrapeResult


class FileNotifier:
    def __init__(
        self,
        config_path: str = "config/notifications.yaml",
        out_dir: str = "data/notifications",
    ):
        self.out_dir = Path(out_dir)
        self.rules = []
        p = Path(config_path)
        if p.exists():
            cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            self.rules = cfg.get("rules", [])
        # Precompile regex whole-word cho rule dùng `tickers` (tránh SSI⊂passive,
        # VIC⊂Vicem…). Case-SENSITIVE: mã CK viết hoa, không khớp chữ thường.
        for rule in self.rules:
            ticks = rule.get("tickers")
            if ticks:
                rule["_ticker_re"] = re.compile(
                    r"\b(" + "|".join(re.escape(t) for t in ticks) + r")\b"
                )

    def _log_path(self) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        return self.out_dir / f"{datetime.now(VN_TZ):%Y-%m-%d}.log"

    def _matches(self, article: Article) -> str | None:
        """Trả tag của rule ĐẦU TIÊN match, None nếu không rule nào match.

        Mỗi rule hỗ trợ 4 kiểu điều kiện (OR trong 1 rule), ưu tiên theo thứ tự:
        - tickers: [MÃ...]      → khớp mã CK nguyên-token (whole-word, phân biệt hoa/thường)
                                  trên title + symbols → tránh SSI⊂passive, VIC⊂Vicem.
        - sources: [domain...]  → khớp nếu article.source_domain thuộc list
                                  (nguồn chuyên tài chính/quốc tế → ghi tất, khỏi sót).
        - has_symbol: true      → khớp nếu bài gắn BẤT KỲ mã CK nào (kể cả ngoài watchlist).
        - match.any: [kw...]     → khớp substring trên title + symbols (match:true = tất).
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

    SENTIMENT_MARKER = {"positive": "[+]", "negative": "[-]", "neutral": "[~]"}

    def format_article(self, a: Article, tag: str = "") -> str:
        """1 dòng/bài, tối giản theo thiết kế gốc:
        <marker> <title> (chi tiết (<url>))
        Metadata (giờ, tag, symbols, nguồn) đã có trong DB — log chỉ để đọc lướt.
        """
        marker = self.SENTIMENT_MARKER.get(a.sentiment, "[~]")
        return f"{marker} {a.title} (chi tiết ({a.url}))"

    def notify_articles(self, articles: list[Article]) -> int:
        """Ghi 1 dòng/bài match rule (1 dòng/bài, không cách trống). Trả số match."""
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
        """1 dòng tổng kết cycle: scraper nào mấy bài mới, scraper nào fail.

        Chỉ in stdout + logger — KHÔNG ghi vào file notify để log tin gọn,
        chỉ toàn bài viết (thiết kế tối giản).
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
