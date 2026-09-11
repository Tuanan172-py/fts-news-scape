"""Luồng ghi cơ sở dữ liệu bất đồng bộ theo mẫu Single-Writer."""

from __future__ import annotations

import queue
import threading

from loguru import logger

from src.core.models import Article
from src.db.store import ArticleStore


class DBWriter:
    """Hàng đợi gom lô và ghi bài viết vào cơ sở dữ liệu trong luồng riêng.

    Attributes:
        store: Đối tượng ArticleStore quản lý cơ sở dữ liệu.
        batch_size: Kích thước tối đa của mỗi lô ghi.
        flush_interval: Chu kỳ thời gian tối đa xả hàng đợi tính bằng giây.
    """

    def __init__(self, store: ArticleStore, batch_size: int = 50,
                 flush_interval: float = 2.0):
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
        with self._lock:
            return self._inserted

    def enqueue(self, article: Article) -> None:
        """Đưa một bài viết mới vào hàng đợi chờ ghi.

        Args:
            article: Đối tượng Article cần lưu trữ.
        """
        with self._done:
            self._pending += 1
        self._queue.put(article)

    def flush(self, timeout: float = 10.0) -> bool:
        """Chờ xả toàn bộ các mục đang chờ trong hàng đợi vào cơ sở dữ liệu.

        Args:
            timeout: Thời gian chờ tối đa tính bằng giây.

        Returns:
            True nếu xả thành công trước khi hết thời gian chờ, ngược lại False.
        """
        with self._done:
            return self._done.wait_for(lambda: self._pending <= 0, timeout=timeout)

    def _drain_batch(self) -> list[Article]:
        """Gom các mục trong hàng đợi thành một danh sách lô."""
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
        """Dừng hoạt động luồng ghi và xả toàn bộ hàng đợi trước khi đóng.

        Args:
            timeout: Thời gian chờ tối đa cho luồng dừng tính bằng giây.
        """
        self._stop.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("DBWriter did not stop within {}s ({} items left)",
                           timeout, self._queue.qsize())
