"""
DBWriter — single-writer queue thread (research-02 §2).

Scraper không ghi bảng articles trực tiếp; chỉ enqueue().
Thread writer gom batch ≤50 hoặc mỗi 2s → 1 transaction BEGIN IMMEDIATE.
stop(flush=True) xả hết queue trước khi thoát → graceful shutdown (spec §12).
"""

from __future__ import annotations

import queue
import threading

from loguru import logger

from src.core.models import Article
from src.db.store import ArticleStore


class DBWriter:
    def __init__(self, store: ArticleStore, batch_size: int = 50,
                 flush_interval: float = 2.0):
        self.store = store
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: queue.Queue[Article] = queue.Queue()
        self._stop = threading.Event()
        self._inserted = 0
        self._lock = threading.Lock()
        self._pending = 0                       # item đã enqueue chưa commit
        self._done = threading.Condition()      # báo khi _pending về 0
        self._thread = threading.Thread(target=self._run, name="db-writer", daemon=True)
        self._thread.start()

    @property
    def inserted(self) -> int:
        with self._lock:
            return self._inserted

    def enqueue(self, article: Article) -> None:
        with self._done:
            self._pending += 1
        self._queue.put(article)

    def flush(self, timeout: float = 10.0) -> bool:
        """Chặn đến khi mọi item đã enqueue được commit (dùng trước export/checkpoint).
        Trả True nếu xả hết trong timeout, False nếu quá hạn. Idempotent."""
        with self._done:
            return self._done.wait_for(lambda: self._pending <= 0, timeout=timeout)

    def _drain_batch(self) -> list[Article]:
        """Chờ item đầu (timeout flush_interval), rồi gom tối đa batch_size."""
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
        conn = self.store._connect()  # connection thuộc riêng thread này
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
        """Dừng writer, xả hết queue. Idempotent."""
        self._stop.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("DBWriter did not stop within {}s ({} items left)",
                           timeout, self._queue.qsize())
