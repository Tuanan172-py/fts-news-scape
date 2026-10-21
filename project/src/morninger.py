"""Schedule and run the daytime pipeline processing cycles."""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Keep the project root on sys.path when running `python morninger.py` directly.
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

_SCRIPTS_DIR = Path(_project_root) / "scripts"

from loguru import logger

from src.core.config import load_settings
from src.core.logging import setup_logging
from src.core.models import VN_TZ
from src.core.proclock import SCHEDULER_LOCK_STALE_SECONDS, capture_lock, lock_owner
from src.db.store import ArticleStore
from src.pipeline.derive import rederive_incremental
from src.pipeline.drift import list_drift
from src.orchestrator import Orchestrator


def _force_utf8_stdio() -> None:
    """Reconfigure the standard streams to UTF-8 to avoid character encoding errors."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def build_scheduler(capture_fn, derive_fn, drift_fn, cfg: dict, reclaim_fn=None):
    """Build the BlockingScheduler with the periodic jobs.

    There is no code-first L1 routing job. That job belongs to the discontinued L1/Gold lane
    (ADR 0010): it writes lookup results into `l1_outputs`, and the old article selector
    treats them as analyzed and skips the article permanently.

    Args:
        capture_fn: Callable that runs Bronze capture.
        derive_fn: Callable that runs incremental Silver derivation.
        drift_fn: Callable that checks layout template drift.
        cfg: Morninger runtime configuration.
        reclaim_fn: Callable that releases work packages stuck in `claimed` past the limit. None skips registering the job.

    Returns:
        BlockingScheduler with every job registered.
    """
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    cap_interval = int(cfg.get("capture_interval_minutes", 15))
    rederive_interval = int(cfg.get("rederive_interval_minutes", 30))
    drift_hour = int(cfg.get("drift_hour", 6))
    drift_minute = int(cfg.get("drift_minute", 0))

    scheduler = BlockingScheduler()
    now = datetime.now(VN_TZ)
    scheduler.add_job(
        capture_fn,
        IntervalTrigger(minutes=cap_interval),
        id="capture",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now,
    )
    # Re-derive starts about 1 minute after capture (head start), then runs regularly.
    scheduler.add_job(
        derive_fn,
        IntervalTrigger(minutes=rederive_interval),
        id="derive",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(seconds=60),
    )
    scheduler.add_job(
        drift_fn,
        CronTrigger(hour=drift_hour, minute=drift_minute),
        id="drift",
        coalesce=True,
        max_instances=1,
    )
    if reclaim_fn is not None:
        # Without a worker claiming, nothing would release stuck packages, so a dedicated job is needed.
        scheduler.add_job(
            reclaim_fn,
            IntervalTrigger(minutes=int(cfg.get("reclaim_interval_minutes", 30))),
            id="reclaim",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=300,
            next_run_time=now + timedelta(seconds=120),
        )
    return scheduler


class Morninger:
    """Coordinate the scheduled daytime news capture and refinement.

    Attributes:
        settings: Shared system settings.
        store: ArticleStore holding the base data.
        cfg: Configuration specific to the morninger module.
        orch: Orchestrator that runs the capture cycle.
    """

    def __init__(self):
        """Load settings, set up logging and create the store and orchestrator."""
        self.settings = load_settings()
        setup_logging(
            self.settings["logging"]["level"], self.settings["logging"]["dir"]
        )
        self.store = ArticleStore(self.settings["database"]["path"])
        self.cfg = self.settings.get("morninger", {})
        self.orch = Orchestrator()
        self._lock_owner = lock_owner()
        self._capture_lock = capture_lock()
        self._stopped = False

    # -- jobs -----------------------------------------------------------------
    def run_capture(self) -> int:
        """Run the Bronze source capture cycle, then immediately backfill `detail_deferred` articles.

        Backfilling right away (articles over the per-cycle cap) narrows the window in which
        the source may delete an article before its full content is fetched, a trait of
        Vietnamese news.

        Returns:
            Number of new articles recorded by the main capture cycle.
        """
        n = self.orch.run_cycle()
        self.run_backfill_deferred()
        self.run_capture_gap()
        return n

    def run_capture_gap(self) -> int:
        """Reconcile against the sitemap and backfill missing URLs right after capture (rule 10, ADR 0013).

        The reconcile phase runs only when the previous one is older than `gap_reconcile_minutes`.
        A failure does not block the cycle.

        Returns:
            Exit code of the child process, or -1 if it could not run.
        """
        limit = int(self.cfg.get("gap_backfill_limit", 40))
        budget = int(self.cfg.get("gap_budget_seconds", 120))
        every = int(self.cfg.get("gap_reconcile_minutes", 30))
        script = _SCRIPTS_DIR / "capture_reconcile.py"
        try:
            proc = subprocess.run(
                [sys.executable, str(script), "run", "--limit", str(limit),
                 "--budget", str(budget), "--min-interval-minutes", str(every)],
                cwd=_project_root, capture_output=True, text=True, timeout=budget + 180,
                encoding="utf-8", errors="replace",
            )
            for line in (proc.stdout or "").strip().splitlines()[-5:]:
                logger.info("[morninger] capture_gap: {}", line)
            if proc.returncode != 0:
                logger.warning("[morninger] capture_gap exit={}: {}",
                               proc.returncode, proc.stderr[-500:])
            return proc.returncode
        except Exception as e:  # noqa: BLE001 - auxiliary job must not break capture
            logger.error("[morninger] capture_gap lỗi (bỏ qua): {}", e)
            return -1

    def run_backfill_deferred(self) -> int:
        """Run backfill_deferred.py right after capture to fetch the full content of deferred articles.

        Covers articles deferred past `max_details_per_cycle` AND articles whose fetch failed
        transiently (timeout or 5xx). A failure does not block the cycle.

        Returns:
            Exit code of the child process, or -1 if it could not run.
        """
        limit = int(self.cfg.get("deferred_backfill_limit", 60))
        max_attempts = int(self.cfg.get("deferred_max_attempts", 5))
        window = int(self.cfg.get("deferred_retry_window_hours", 24))
        budget = int(self.cfg.get("deferred_budget_seconds", 90))
        script = _SCRIPTS_DIR / "maintenance" / "backfill_deferred.py"
        try:
            proc = subprocess.run(
                [sys.executable, str(script), "--fetch", "--limit", str(limit),
                 "--mode", "all", "--max-attempts", str(max_attempts),
                 "--retry-window-hours", str(window),
                 "--budget-seconds", str(budget)],
                # The timeout must exceed the budget so the script can stop cleanly and report;
                # a kill by timeout loses the statistics of that run.
                # The encoding must be explicit: the child emits UTF-8, and without it the parent
                # decodes as cp1252, the reader thread dies and stdout becomes None.
                cwd=_project_root, capture_output=True, text=True, timeout=budget + 60,
                encoding="utf-8", errors="replace",
            )
            if (proc.stdout or "").strip():
                logger.info("[morninger] backfill_deferred: {}",
                           proc.stdout.strip().splitlines()[-1])
            if proc.returncode != 0:
                logger.warning("[morninger] backfill_deferred exit={}: {}",
                               proc.returncode, proc.stderr[-500:])
            return proc.returncode
        except Exception as e:  # noqa: BLE001 - auxiliary job must not break capture
            logger.error("[morninger] backfill_deferred lỗi (bỏ qua): {}", e)
            return -1

    def run_derive(self) -> dict:
        """Run the incremental Bronze-to-Silver conversion cycle.

        Returns:
            Progress report dict, with manifest information when the checkpoint is reached.
        """
        s = rederive_incremental(self.store)
        self.run_story_cluster()
        if s["checkpoint_reached"]:
            try:
                from src.export.silver_manifest import export_silver_manifest

                path, n = export_silver_manifest(self.store, today=True)
                s["manifest"] = str(path)
                s["manifest_count"] = n
                logger.info("[morninger] silver manifest: {} bài -> {}", n, path)
            except Exception as e:  # noqa: BLE001 - the export is an auxiliary utility
                logger.error("silver manifest export lỗi (bỏ qua): {}", e)
        return s

    def run_story_cluster(self) -> dict:
        """Cluster duplicates and write the derived signals after the Silver derive (ADR 0016).

        Returns:
            Clustering and signal statistics; an empty dict on error. Never blocks the derive.
        """
        try:
            from src.analytics.signals import build_all
            from src.pipeline.cluster_job import refresh

            conn = self.store._connect()
            try:
                stats = refresh(conn, days=int(self.cfg.get("cluster_days", 3)))
                every = float(self.cfg.get("signal_build_minutes", 30))
                last = self.store.get_state("signals_last_ts")
                if last is None or time.time() - float(last) >= every * 60:
                    built = build_all(conn, days=int(self.cfg.get("signal_days", 30)))
                    self.store.set_state("signals_last_ts", str(time.time()))
                    stats["signal_rows"] = len(built["signal_daily"])
            finally:
                conn.close()
            logger.info("[morninger] story_cluster: {}", stats)
            return stats
        except Exception as e:  # noqa: BLE001 - auxiliary job must not break derive
            logger.error("[morninger] story_cluster lỗi (bỏ qua): {}", e)
            return {}

    def run_reclaim(self) -> int:
        """Release work packages stuck in `claimed` past the limit back to `pending`.

        `reclaim_stale()` otherwise runs only inside `Catalog.claim()`, so when no worker comes
        to claim work nothing releases the rows and `claimed` rows hang forever.

        Returns:
            Number of work packages returned to the queue, or -1 on error.
        """
        try:
            from src.handoff.catalog import Catalog

            n = Catalog(self.store).reclaim_stale()
            if n:
                logger.info("[morninger] reclaim: nhả {} work_item kẹt ở 'claimed'", n)
            return n
        except Exception as e:  # noqa: BLE001 - auxiliary job must not break the scheduler
            logger.error("[morninger] reclaim lỗi (bỏ qua): {}", e)
            return -1

    def run_drift(self) -> int:
        """Check and warn about articles with template or selector drift.

        Returns:
            Number of articles found in a drift state.
        """
        rows = list_drift(self.store, limit=int(self.cfg.get("drift_limit", 100)))
        if not rows:
            logger.info("[morninger] drift report: không có bài drift/broken ✅")
            return 0
        logger.warning("[morninger] drift report: {} bài cần reconcile", len(rows))
        for r in rows[:20]:
            logger.warning(
                "  {}  {}  {}  {}",
                r["state"],
                r["source_domain"] or "",
                r["captured_at"] or "",
                r["url_title_hash"][:16],
            )
        if len(rows) > 20:
            logger.warning("  ... (+{} more)", len(rows) - 20)
        return len(rows)

    # -- scheduler ------------------------------------------------------------
    def acquire_capture_lock(self) -> bool:
        """Take the file lock shared by every scraping process on the machine.

        Returns:
            True if the lock was taken, False if another scraping process is running.
        """
        if self._capture_lock.acquire():
            return True
        logger.error("Tiến trình cào tin khác đang chạy ({}), giữ khoá {}. Từ chối khởi "
                     "động để tránh cào song song.", self._capture_lock.holder() or "?",
                     self._capture_lock.path)
        return False

    def start_scheduler(self) -> bool:
        """Take the capture lock, then run the scheduler until a stop signal arrives.

        Returns:
            False if another scraping process holds the lock, True if the scheduler ran and stopped.
        """
        if not self.acquire_capture_lock():
            return False
        # Only one scheduler may run. Take the lock and hand the heartbeat to the internal
        # orchestrator (same pid): run_capture -> orch.run_cycle refreshes the lock every cycle.
        if not self.store.try_acquire_lock("scheduler", self._lock_owner,
                                           SCHEDULER_LOCK_STALE_SECONDS):
            logger.error("Scheduler khác đang chạy (lock trong pipeline_state). "
                         "Từ chối khởi động morninger để tránh double-scrape.")
            self._capture_lock.release()
            return False
        self.orch._lock_owner = self._lock_owner
        self.orch._owns_scheduler_lock = True

        scheduler = build_scheduler(
            self.run_capture, self.run_derive, self.run_drift, self.cfg,
            self.run_reclaim,
        )

        def handle_signal(signum, frame):
            logger.warning("Signal {} — stopping morninger...", signum)
            scheduler.shutdown(wait=False)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        cap = int(self.cfg.get("capture_interval_minutes", 15))
        rederive = int(self.cfg.get("rederive_interval_minutes", 30))
        drift_hour = int(self.cfg.get("drift_hour", 6))
        drift_minute = int(self.cfg.get("drift_minute", 0))
        reclaim = int(self.cfg.get("reclaim_interval_minutes", 30))
        logger.info(
            "Morninger started: capture/{}min (+backfill_deferred nối tiếp), "
            "derive/{}min, reclaim/{}min, drift/{}:{}",
            cap,
            rederive,
            reclaim,
            drift_hour,
            drift_minute,
        )
        try:
            scheduler.start()
        finally:
            self.shutdown()
        return True

    def shutdown(self) -> None:
        """Flush the orchestrator and release the capture lock; repeated calls are safe."""
        if self._stopped:
            return
        self._stopped = True
        logger.info("Morninger shutdown — flushing orchestrator...")
        self.orch.shutdown()
        self._capture_lock.release()
        logger.info("Morninger shutdown complete.")


def main(argv: list[str]) -> int:
    """Run morninger once (`--once`) or start the scheduler.

    Args:
        argv: Command-line arguments without the program name. The first positional argument
            selects the `--once` target: capture, derive (default) or drift.

    Returns:
        Process exit code: 0 on success, 1 if the capture lock is held, 2 for an unknown target.
    """
    _force_utf8_stdio()
    args = [a for a in argv if not a.startswith("--")]
    once = "--once" in argv
    m = Morninger()

    if once:
        sub = args[0] if args else "derive"
        try:
            if sub == "capture":
                if not m.acquire_capture_lock():
                    return 1
                print("🔄 [morninger] Đang thực thi Capture cycle...", flush=True)
                n = m.run_capture()
                print(f"✅ capture done: {n} new articles")
            elif sub == "derive":
                print("🔄 [morninger] Bắt đầu tiến trình Re-derive Silver từ Bronze...", flush=True)
                s = m.run_derive()
                print(
                    f"✅ derive done: processed={s['processed']} ok={s['ok']} "
                    f"held={s['held']} backlog={s['backlog']} "
                    f"checkpoint={s['checkpoint_reached']} "
                    f"watermark={s['watermark_new']}"
                )
                if s.get("manifest"):
                    print(f"manifest: {s['manifest_count']} bài -> {s['manifest']}")
            elif sub == "drift":
                n = m.run_drift()
                print(f"drift done: {n} bài cần reconcile")
            else:
                print(f"unknown --once target: {sub} (capture|derive|drift)")
                return 2
        finally:
            m.shutdown()
        return 0

    return 0 if m.start_scheduler() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
