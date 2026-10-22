"""Orchestrate the news capture cycle across the enabled sources."""

from __future__ import annotations

from src.core import paths
import signal
import sys
import time
from datetime import datetime

from src.core.models import VN_TZ
from src.export.csv_export import export as export_csv

from loguru import logger

from src.core.config import list_domains, load_domain_config, load_settings
from src.core.logging import setup_logging
from src.core.proclock import SCHEDULER_LOCK_STALE_SECONDS, capture_lock, lock_owner
from src.core.retry import run_with_retry, run_with_fallback
from src.crawler.http_client import HTTPClient
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.db.writer import DBWriter
from src.monitor.heartbeat import Heartbeat
from src.notifier.file_notify import FileNotifier
from src.processor.classifier import classify_rule_based

import src.scrapers  # noqa: F401 - triggers @register
from src.scrapers import REGISTRY


def _force_utf8_stdio() -> None:
    """Reconfigure the standard streams to UTF-8 to avoid character encoding errors."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_scraper(cfg: dict, http: HTTPClient, dedup: DedupCache):
    """Create the scraper instance that matches a domain configuration.

    Args:
        cfg: Domain configuration dict.
        http: Shared HTTPClient instance.
        dedup: DedupCache used for duplicate checks.

    Returns:
        A scraper instance derived from BaseScraper.

    Raises:
        KeyError: If no matching scraper class is found.
    """
    cls = REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")
    if cls is None:
        raise KeyError(f"No scraper for '{cfg['name']}' (method={cfg['method']})")
    return cls(cfg, http, dedup)


class Orchestrator:
    """Coordinate capture, processing and storage of data from the news sources.

    Attributes:
        settings: Shared system settings.
        store: ArticleStore holding the base data.
        writer: Asynchronous DBWriter.
        http: HTTPClient for network access.
        dedup: DedupCache used for duplicate checks.
        heartbeat: Heartbeat status tracker.
        notifier: FileNotifier that writes notifications.
    """

    def __init__(self):
        """Load settings and create the store, writer, HTTP client and helpers."""
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
        notif_dir = self.settings.get("notifications", {}).get("dir")
        self.notifier = FileNotifier(out_dir=notif_dir)
        self._stopped = False
        self._lock_owner = lock_owner()          # identity that holds the scheduler lock
        self._owns_scheduler_lock = False
        removed = self.dedup.cleanup(max_age_days=30)
        if removed:
            logger.info("Dedup cleanup: removed {} entries >30d", removed)

    def run_cycle(self, names: list[str] | None = None) -> int:
        """Run one capture cycle sequentially across the enabled sources.

        Args:
            names: Domain names to run. Defaults to every enabled source.

        Returns:
            Total number of new articles recorded.
        """
        names = names or list_domains()
        if not names:
            logger.warning("No enabled domain configs in config/domains/")
            return 0
        if self._owns_scheduler_lock:  # heartbeat keeps the lock fresh
            self.store.refresh_lock("scheduler", self._lock_owner)
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
                # Sentiment is not computed here: the article-processor agent sets it in the
                # output layer. Only rule-based categories are attached at capture time.
                for cat in classify_rule_based(a.title, a.content_text):
                    if cat not in a.categories and cat != "uncategorized":
                        a.categories.append(cat)
                self.writer.enqueue(a)
            self.heartbeat.record_result(result)
            results.append(result)
            all_new.extend(result.new)

        try:
            self.notifier.notify_articles(all_new)
            if results:
                self.notifier.notify_cycle_summary(results)
        except Exception as e:
            # Notification is an auxiliary utility and must not break the export (graceful degradation).
            logger.error("Notify lỗi (bỏ qua): {}: {}", type(e).__name__, e)
        self.writer.flush()  # make sure this cycle's articles are committed before export and checkpoint
        self._export_csv()
        self._wal_checkpoint()
        logger.info(
            "=== Cycle done: {} new articles in {:.0f}s ===",
            len(all_new),
            time.monotonic() - cycle_start,
        )
        return len(all_new)

    def _export_csv(self) -> None:
        """Export today's articles to a CSV file."""
        exp = self.settings.get("export", {})
        if not exp.get("enabled", True):
            return
        out_dir = exp.get("dir")
        try:
            root = paths.resolve_data_path(out_dir) if out_dir else paths.exports_dir()
            out = root / f"articles-{datetime.now(VN_TZ):%Y-%m-%d}.csv"
            _, n = export_csv(
                db_path=self.settings["database"]["path"], today=True, out=str(out)
            )
            logger.info("CSV export: {} bài hôm nay -> {}", n, out)
        except Exception as e:
            logger.error("CSV export lỗi (bỏ qua): {}: {}", type(e).__name__, e)

    def _wal_checkpoint(self) -> None:
        """Keep the -wal file small (Windows); runs when idle at the end of a cycle."""
        try:
            conn = self.store._connect()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception as e:
            logger.warning("WAL checkpoint failed: {}", e)

    def shutdown(self) -> None:
        """Flush the writer, release the scheduler lock and checkpoint the WAL; repeated calls are safe."""
        if self._stopped:  # idempotent: may be called from both the signal handler and finally
            return
        self._stopped = True
        logger.info("Shutting down — flushing writer + WAL checkpoint...")
        if self._owns_scheduler_lock:
            self.store.release_lock("scheduler", self._lock_owner)
            self._owns_scheduler_lock = False
        self.writer.stop()
        self.dedup.close()
        self._wal_checkpoint()
        logger.info("Shutdown complete.")

    def start_scheduler(self) -> None:
        """Take the capture and scheduler locks, then run the interval scheduler until a stop signal."""
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        file_lock = capture_lock()
        if not file_lock.acquire():
            logger.error("Tiến trình cào tin khác đang chạy ({}). Từ chối khởi động để "
                         "tránh double-scrape.", file_lock.holder() or "?")
            return
        # Only one scheduler may run (prevents orchestrator and morninger running together).
        if not self.store.try_acquire_lock("scheduler", self._lock_owner,
                                           SCHEDULER_LOCK_STALE_SECONDS):
            logger.error("Scheduler khác đang chạy (lock trong pipeline_state). "
                         "Từ chối khởi động để tránh double-scrape.")
            file_lock.release()
            return
        self._owns_scheduler_lock = True

        interval = self.settings["scheduler"]["interval_minutes"]
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.run_cycle,
            IntervalTrigger(minutes=interval),
            coalesce=True,  # merge missed runs into one
            max_instances=1,  # singleton: cycles never overlap
            misfire_grace_time=300,
            next_run_time=datetime.now(VN_TZ),  # run immediately the first time (tz-aware)
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
            file_lock.release()


def main(argv: list[str]) -> int:
    """Run the orchestrator once (`--once`) or start the interval scheduler.

    Args:
        argv: Command-line arguments without the program name. Positional arguments name the
            domains to run; `--once` runs a single cycle.

    Returns:
        Process exit code: 0 on success, 1 if another scraping process holds a lock.
    """
    _force_utf8_stdio()
    once = "--once" in argv
    names = [a for a in argv if not a.startswith("--")] or None

    orch = Orchestrator()
    if once:
        # The file lock reliably blocks while morninger runs; the lock in pipeline_state
        # depends on a heartbeat and may be wrongly judged stale.
        file_lock = capture_lock()
        if not file_lock.acquire():
            logger.error("Tiến trình cào tin khác đang chạy ({}). Từ chối chạy --once để "
                         "tránh cào song song.", file_lock.holder() or "?")
            orch.shutdown()
            return 1
        # Run standalone but take the scheduler lock to avoid scraping in parallel with morninger.
        if not orch.store.try_acquire_lock("scheduler", orch._lock_owner, SCHEDULER_LOCK_STALE_SECONDS):
            logger.error("Scheduler khác (morninger hoặc orchestrator) đang chạy. Từ chối chạy --once để tránh cào song song.")
            orch.shutdown()
            file_lock.release()
            return 1
        orch._owns_scheduler_lock = True

        def handle_signal(signum, frame):
            orch.shutdown()
            sys.exit(1)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        try:
            orch.run_cycle(names)
        finally:
            orch.shutdown()
            file_lock.release()
        return 0
    orch.start_scheduler()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
