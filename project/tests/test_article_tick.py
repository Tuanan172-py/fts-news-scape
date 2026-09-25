"""Kiểm thử đơn vị cho bộ điều phối tự động article_tick."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.article_tick import (
    PipelineLock,
    check_kill_switch,
    evaluate_trigger,
    is_flush_window,
    load_standing_order,
)


def test_is_flush_window():
    """Kiểm tra các khung giờ gom vét thị trường."""
    # 07:30 sáng -> Khung pre-market
    dt_morning = datetime(2026, 9, 25, 7, 30)
    in_win, name = is_flush_window(dt_morning)
    assert in_win is True
    assert "pre_market" in name

    # 12:25 trưa -> Khung midday
    dt_noon = datetime(2026, 9, 25, 12, 25)
    in_win, name = is_flush_window(dt_noon)
    assert in_win is True
    assert "midday" in name

    # 15:30 chiều -> Khung post-market
    dt_afternoon = datetime(2026, 9, 25, 15, 30)
    in_win, name = is_flush_window(dt_afternoon)
    assert in_win is True
    assert "post_market" in name

    # 17:30 tối -> Khung eod
    dt_eod = datetime(2026, 9, 25, 17, 30)
    in_win, name = is_flush_window(dt_eod)
    assert in_win is True
    assert "eod" in name

    # 10:00 sáng -> Ngoài khung giờ gom vét
    dt_idle = datetime(2026, 9, 25, 10, 0)
    in_win, name = is_flush_window(dt_idle)
    assert in_win is False
    assert name == ""


def test_evaluate_trigger():
    """Kiểm tra logic đánh giá điều kiện kích hoạt mở đợt."""
    dt_idle = datetime(2026, 9, 25, 10, 0)
    dt_flush = datetime(2026, 9, 25, 12, 30)

    # 1. Backlog vượt ngưỡng 50 bài -> Kích hoạt ngay (Fast Path)
    run, reason = evaluate_trigger(55, threshold=50, now=dt_idle)
    assert run is True
    assert "vượt mức" in reason

    # 2. Backlog dưới ngưỡng (20 bài) nhưng ngoài giờ gom vét -> Bỏ qua
    run, reason = evaluate_trigger(20, threshold=50, now=dt_idle)
    assert run is False
    assert "Chưa đủ ngưỡng" in reason

    # 3. Backlog dưới ngưỡng (20 bài) nhưng chạm khung giờ gom vét -> Kích hoạt
    run, reason = evaluate_trigger(20, threshold=50, now=dt_flush)
    assert run is True
    assert "Khung giờ gom vét" in reason

    # 4. Không có bài nào chờ (0 bài) -> Bỏ qua kể cả trong giờ gom vét
    run, reason = evaluate_trigger(0, threshold=50, now=dt_flush)
    assert run is False

    # 5. Cờ ép buộc (force) -> Luôn kích hoạt
    run, reason = evaluate_trigger(5, threshold=50, force=True, now=dt_idle)
    assert run is True
    assert reason == "forced"


def test_pipeline_lock(tmp_path):
    """Kiểm tra cơ chế khóa đơn tiến trình."""
    lock_file = tmp_path / ".test.lock"
    lock1 = PipelineLock(lock_file)
    lock2 = PipelineLock(lock_file)

    assert lock1.acquire() is True
    assert lock_file.exists()

    # Tiến trình thứ 2 thử acquire khi khóa đang bị giữ bởi tiến trình sống (chính nó)
    assert lock2.acquire() is False

    lock1.release()
    assert not lock_file.exists()
    assert lock2.acquire() is True
    lock2.release()
