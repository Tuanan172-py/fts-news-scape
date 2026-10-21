"""Write to the database asynchronously through a single-writer thread."""

from __future__ import annotations

import queue
import threading

from loguru import logger

from src.core.models import Article
from src.db.store import ArticleStore


class DBWriter:
    """Queue articles and write them to the database in batches on a dedicated thread.

    Attributes:
        store: ArticleStore that manages the database.
        batch_size: Maximum size of each write batch.
        flush_interval: Maximum interval in seconds between queue flushes.
    """

    def __init__(self, store: ArticleStore, batch_size: int = 50,
                 flush_interval: float = 2.0):
        """Create the writer and start its background thread.

        Args:
            store: ArticleStore that manages the database.
            batch_size: Maximum size of each write batch.
            flush_interval: Maximum interval in seconds between queue flushes.
        """
        self.store = store
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: queue.Queue[Article] = queue.Queue()
        self._stop = threading.Event()
        self._inserted = 0
        self._lock = threading.Lock()
        self._pending = 0
        self._done = threading.Condition()
        self._thread = threading.Thread(target=self._run, name="db-writer", daemon=True)
        self._thread.start()

    @property
    def inserted(self) -> int:
        """Number of rows inserted so far."""
        with self._lock:
            return self._inserted

    def enqueue(self, article: Article) -> None:
        """Put a new article in the queue to be written.

        Args:
            article: Article to store.
        """
        with self._done:
            self._pending += 1
        self._queue.put(article)

    def flush(self, timeout: float = 10.0) -> bool:
        """Wait until every queued item has been written to the database.

        Args:
            timeout: Maximum wait in seconds.

        Returns:
            True if the queue drained before the timeout, otherwise False.
        """
        with self._done:
            return self._done.wait_for(lambda: self._pending <= 0, timeout=timeout)

    def _drain_batch(self) -> list[Article]:
        """Collect queued items into one batch list."""
        batch: list[Article] = []
        try:
            batch.append(self._queue.get(timeout=self.flush_interval))
        except queue.Empty:
            return batch
        while len(batch) < self.batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _run(self) -> None:
        conn = self.store._connect()
        try:
            while True:
                batch = self._drain_batch()
                if batch:
                    n = self.store.insert_batch(batch, conn=conn)
                    with self._lock:
                        self._inserted += n
                    with self._done:
                        self._pending -= len(batch)
                        if self._pending <= 0:
                            self._done.notify_all()
                    logger.debug("DBWriter: {} queued -> {} new rows", len(batch), n)
                elif self._stop.is_set() and self._queue.empty():
                    break
        finally:
            conn.close()

    def stop(self, timeout: float = 30.0) -> None:
        """Stop the writer thread after draining the queue.

        Args:
            timeout: Maximum wait in seconds for the thread to stop.
        """
        self._stop.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("DBWriter did not stop within {}s ({} items left)",
                           timeout, self._queue.qsize())
