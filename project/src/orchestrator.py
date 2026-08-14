"""
Orchestrator — điều phối tất cả scrapers (spec §11).

Singleton cycle: APScheduler coalesce=True + max_instances=1 + misfire 300s
→ "1 cycle chạy xong mới chạy cycle tiếp".

Usage:
    python -m src.orchestrator            # scheduler 15 phút/cycle, chạy ngay lần đầu
    python -m src.orchestrator --once     # 1 cycle rồi thoát
    python -m src.orchestrator --once cafef tnck
"""

from __future__ import annotations

import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from src.core.models import VN_TZ
from src.export.csv_export import export as export_csv

from loguru import logger

from src.core.config import list_domains, load_domain_config, load_settings
from src.core.logging import setup_logging
from src.core.retry import run_with_retry, run_with_fallback
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.db.writer import DBWriter
from src.monitor.heartbeat import Heartbeat
from src.notifier.file_notify import FileNotifier
from src.processor.classifier import classify_rule_based
from src.processor.sentiment import SentimentEngine

import src.scrapers  # noqa: F401 — trigger @register
from src.scrapers import REGISTRY


def _force_utf8_stdio() -> None:
    """Ép stdout/stderr sang UTF-8 (Windows: print tiếng Việt qua Task Scheduler
    bị redirect vào file dùng cp1252 → UnicodeEncodeError làm crash pipeline)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_scraper(cfg: dict, http: HTTPClient, dedup: DedupCache):
    """Factory: domain config → scraper instance. Per-name class > generic method class."""
    cls = REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")
    if cls is None:
        raise KeyError(f"No scraper for '{cfg['name']}' (method={cfg['method']})")
    return cls(cfg, http, dedup)


class Orchestrator:
    def __init__(self):
        self.settings = load_settings()
        setup_logging(
            self.settings["logging"]["level"], self.settings["logging"]["dir"]
        )
        self.store = ArticleStore(self.settings["database"]["path"])
        self.writer = DBWriter(self.store)
        self.http = HTTPClient(
            rate_limit_delay=self.settings["http"]["rate_limit"],
            max_retries=self.settings["http"]["max_retries"],
        )
        self.dedup = DedupCache(self.store)
        self.heartbeat = Heartbeat(self.store)
        notif_dir = self.settings.get("notifications", {}).get(
            "dir", "data/notifications"
        )
        self.notifier = FileNotifier(out_dir=notif_dir)
        self.sentiment = SentimentEngine()
        self._stopped = False
        removed = self.dedup.cleanup(max_age_days=30)
        if removed:
            logger.info("Dedup cleanup: removed {} entries >30d", removed)

    def run_cycle(self, names: list[str] | None = None) -> int:
        """1 cycle tuần tự qua mọi domain enabled. Trả về số article mới."""
        names = names or list_domains()
        if not names:
            logger.warning("No enabled domain configs in config/domains/")
            return 0
        cycle_start = time.monotonic()
        logger.info("=== Cycle start: {} domains: {} ===", len(names), ", ".join(names))

        results, all_new = [], []
        for name in names:
            try:
                cfg = load_domain_config(name)
            except (FileNotFoundError, ValueError) as e:
                logger.error("Bad domain config '{}': {}", name, e)
                continue
            if not cfg.get("enabled", True):
                logger.info("[{}] disabled, skipping", name)
                continue
            try:
                primary = build_scraper(cfg, self.http, self.dedup)
            except KeyError as e:
                logger.error("{}", e)
                continue

            fallback = None
            fb_method = cfg.get("fallback")
            if fb_method and REGISTRY.get(f"_{fb_method}"):
                fallback = REGISTRY[f"_{fb_method}"](cfg, self.http, self.dedup)

            self.heartbeat.record_start(name)
            result = (
                run_with_fallback(primary, fallback)
                if fallback
                else run_with_retry(primary)
            )
            for a in result.new:
                for cat in classify_rule_based(a.title, a.content_text):
                    if cat not in a.categories and cat != "uncategorized":
                        a.categories.append(cat)
                if a.metadata.get("language", "vi") == "vi":
                    a.sentiment, a.sentiment_score = self.sentiment.analyze(
                        a.title, a.content_text
                    )
                else:
                    # lexicon VN không áp dụng cho tiếng Anh (Phase 2 decision)
                    a.sentiment, a.sentiment_score = "neutral", 0.0
                self.writer.enqueue(a)
            self.heartbeat.record_result(result)
            results.append(result)
            all_new.extend(result.new)

        try:
            self.notifier.notify_articles(all_new)
            if results:
                self.notifier.notify_cycle_summary(results)
        except Exception as e:
            # notify là tiện ích — không được làm hỏng export (graceful degradation)
            logger.error("Notify lỗi (bỏ qua): {}: {}", type(e).__name__, e)
        self.writer.flush()  # đảm bảo bài cycle này đã commit trước export/checkpoint
        self._export_csv()
        self._wal_checkpoint()
        logger.info(
            "=== Cycle done: {} new articles in {:.0f}s ===",
            len(all_new),
            time.monotonic() - cycle_start,
        )
        return len(all_new)

    def _export_csv(self) -> None:
        """Tự xuất CSV 'hôm nay' cuối mỗi cycle (data/exports/articles-YYYY-MM-DD.csv).
        Ghi đè mỗi cycle → luôn phản ánh data mới nhất. Lỗi export không làm hỏng cycle."""
        exp = self.settings.get("export", {})
        if not exp.get("enabled", True):
            return
        out_dir = exp.get("dir", "data/exports")
        try:
            out = Path(out_dir) / f"articles-{datetime.now(VN_TZ):%Y-%m-%d}.csv"
            _, n = export_csv(
                db_path=self.settings["database"]["path"], today=True, out=str(out)
            )
            logger.info("CSV export: {} bài hôm nay -> {}", n, out)
        except Exception as e:
            logger.error("CSV export lỗi (bỏ qua): {}: {}", type(e).__name__, e)

    def _wal_checkpoint(self) -> None:
        """Giữ file -wal nhỏ (Windows) — chạy lúc idle cuối cycle."""
        try:
            conn = self.store._connect()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception as e:
            logger.warning("WAL checkpoint failed: {}", e)

    def shutdown(self) -> None:
        if self._stopped:  # idempotent — có thể bị gọi từ cả signal handler lẫn finally
            return
        self._stopped = True
        logger.info("Shutting down — flushing writer + WAL checkpoint...")
        self.writer.stop()
        self.dedup.close()
        self._wal_checkpoint()
        logger.info("Shutdown complete.")

    def start_scheduler(self) -> None:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        interval = self.settings["scheduler"]["interval_minutes"]
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.run_cycle,
            IntervalTrigger(minutes=interval),
            coalesce=True,  # dồn các lần miss thành 1
            max_instances=1,  # singleton: không chồng cycle
            misfire_grace_time=300,
            next_run_time=datetime.now(VN_TZ),  # chạy ngay lần đầu (tz-aware)
        )

        def handle_signal(signum, frame):
            logger.warning("Signal {} — stopping scheduler...", signum)
            scheduler.shutdown(wait=False)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        logger.info("Scheduler started: every {} min (coalesce, singleton)", interval)
        try:
            scheduler.start()
        finally:
            self.shutdown()


def main(argv: list[str]) -> int:
    _force_utf8_stdio()
    once = "--once" in argv
    names = [a for a in argv if not a.startswith("--")] or None

    orch = Orchestrator()
    if once:

        def handle_signal(signum, frame):
            orch.shutdown()
            sys.exit(1)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        try:
            orch.run_cycle(names)
        finally:
            orch.shutdown()
        return 0
    orch.start_scheduler()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
