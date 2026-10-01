"""Đo bài chờ phân tích và quyết định thời điểm mở đợt Article Lane."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from src.ops.store import VN_TZ, now_vn, parse_iso


@dataclass
class SensorReading:
    """Kết quả đo bài chờ trong phạm vi ngày theo dõi.

    Attributes:
        per_date: Số bài chờ theo ngày xuất bản, cũ trước.
        oldest_fetched_at: Thời điểm cào của bài chờ lâu nhất.
        backlog_all: Tổng bài chờ mọi ngày (chỉ để báo cáo).
    """

    per_date: list[tuple[str, int]] = field(default_factory=list)
    oldest_fetched_at: datetime | None = None
    backlog_all: int | None = None

    @property
    def total(self) -> int:
        """Tổng bài chờ trong phạm vi theo dõi."""
        return sum(n for _, n in self.per_date)

    @property
    def target_date(self) -> str | None:
        """Ngày cũ nhất còn bài chờ, là ngày đợt kế tiếp sẽ lấy bài."""
        for d, n in self.per_date:
            if n > 0:
                return d
        return None

    def oldest_age_minutes(self, now: datetime | None = None) -> float | None:
        """Tính tuổi của bài chờ lâu nhất.

        Args:
            now: Thời điểm so sánh.

        Returns:
            Số phút, hoặc None khi không có bài chờ.
        """
        if self.oldest_fetched_at is None:
            return None
        return ((now or now_vn()) - self.oldest_fetched_at).total_seconds() / 60.0


def scope_dates(lookback_days: int, now: datetime | None = None) -> list[str]:
    """Liệt kê các ngày xuất bản trong phạm vi theo dõi, cũ trước.

    Args:
        lookback_days: Số ngày lùi lại ngoài hôm nay.
        now: Thời điểm tham chiếu.

    Returns:
        Danh sách chuỗi YYYY-MM-DD.
    """
    today = (now or now_vn()).date()
    return [(today - timedelta(days=i)).isoformat()
            for i in range(max(0, int(lookback_days)), -1, -1)]


def read_pending(db_path: Path, lookback_days: int, *, now: datetime | None = None,
                 with_backlog: bool = False,
                 exclude: set[str] | None = None) -> SensorReading:
    """Đếm bài chờ theo đúng bộ chọn của `article_pack.load_candidates`.

    Bài trong `exclude` (đang thuộc một đợt chưa xong hoặc đã hết lượt thử) không
    được tính, kể cả vào tuổi bài chờ lâu nhất, nên luật tuổi T2 không bắn lại vô hạn
    vì một bài không bao giờ qua được cổng DoD.

    Args:
        db_path: Đường dẫn `monocle.db`.
        lookback_days: Số ngày lùi lại ngoài hôm nay.
        now: Thời điểm tham chiếu.
        with_backlog: Đếm thêm tổng bài chờ mọi ngày.
        exclude: Định danh bài phải bỏ qua.

    Returns:
        SensorReading.
    """
    from scripts.article_pack import load_candidates

    reading = SensorReading()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        oldest: datetime | None = None
        for d in scope_dates(lookback_days, now):
            rows = load_candidates(conn, date=d, limit=1_000_000, only_pending=True,
                                   exclude=exclude, with_content=False)
            reading.per_date.append((d, len(rows)))
            ids = [r["article_id"] for r in rows]
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                row = conn.execute(f"SELECT MIN(fetched_at) FROM articles "
                                   f"WHERE url_title_hash IN ({marks})", chunk).fetchone()
                ts = parse_iso(row[0]) if row else None
                if ts and (oldest is None or ts < oldest):
                    oldest = ts
        reading.oldest_fetched_at = oldest
        if with_backlog:
            reading.backlog_all = len(load_candidates(conn, date=None, limit=10_000_000,
                                                      only_pending=True, exclude=exclude,
                                                      with_content=False))
    finally:
        conn.close()
    return reading


def in_windows(now: datetime, windows: list[str]) -> str | None:
    """Kiểm tra thời điểm có nằm trong một khung giờ `HH:MM-HH:MM` không.

    Args:
        now: Thời điểm kiểm tra.
        windows: Danh sách khung giờ.

    Returns:
        Chuỗi khung giờ khớp, hoặc None.
    """
    minutes = now.hour * 60 + now.minute
    for w in windows:
        try:
            a, b = w.split("-")
            ah, am = (int(x) for x in a.split(":"))
            bh, bm = (int(x) for x in b.split(":"))
        except ValueError:
            continue
        if ah * 60 + am <= minutes <= bh * 60 + bm:
            return w
    return None


def decide(reading: SensorReading, cfg: dict, *, now: datetime | None = None,
           force: bool = False) -> tuple[bool, str, str]:
    """Áp ba luật kích hoạt T1 khối lượng, T2 tuổi, T3 khung giờ.

    Args:
        reading: Kết quả đo bài chờ.
        cfg: Mục `sensor` của cấu hình.
        now: Thời điểm đánh giá.
        force: Bỏ qua luật, mở đợt khi còn bài chờ.

    Returns:
        Bộ ba (mở đợt, mã luật, lý do).
    """
    now = now or now_vn()
    if now.tzinfo is None:
        now = now.replace(tzinfo=VN_TZ)
    n = reading.total
    if n <= 0:
        return False, "", "Không có bài chờ trong phạm vi theo dõi."
    if force:
        return True, "manual", f"Người vận hành yêu cầu ({n} bài chờ)."
    threshold = int(cfg.get("threshold", 100))
    if n >= threshold:
        return True, "T1", f"Đủ ngưỡng khối lượng ({n} ≥ {threshold} bài)."
    h0, h1 = (cfg.get("age_rule_hours") or [0, 24])[:2]
    age = reading.oldest_age_minutes(now)
    max_age = float(cfg.get("max_age_minutes", 90))
    if age is not None and age > max_age and h0 <= now.hour < h1:
        return True, "T2", f"Bài chờ lâu nhất {age:.0f} phút > {max_age:.0f} phút ({n} bài)."
    window = in_windows(now, cfg.get("flush_windows") or [])
    if window:
        return True, "T3", f"Khung giờ vét {window} ({n} bài)."
    age_txt = f", lâu nhất {age:.0f} phút" if age is not None else ""
    return False, "", f"Chưa đủ điều kiện ({n}/{threshold} bài{age_txt})."
