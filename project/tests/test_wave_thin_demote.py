"""Kiểm định miễn demote cho đợt hỏng thiếu Gold nhưng L1 đủ (ADR 0018).

L1 đủ 100% nghĩa mô hình chạy, bung và nạp đều xong; phần thiếu ở lớp nội dung
không phản ánh sức khoẻ provider nên không được góp vào `fail_streak` làm daemon
tự hạ mức.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ops.config import load_config  # noqa: E402
from src.ops import wave_flow  # noqa: E402
from src.ops.wave_flow import drive_wave  # noqa: E402


class _FakeOps:
    def __init__(self, *, finish_ok=True):
        self._finish_ok = finish_ok
        self.final: tuple | None = None

    def preflight(self, spec):
        return [True, "", False]

    def prepare(self, spec):
        return 100

    def analyze(self, spec, round_no):
        return dict(received=100, total=100, worst="OK", step_outcome="ok")

    def stop_requested(self, spec):
        return False

    def finish(self, spec):
        return [self._finish_ok, "ok" if self._finish_ok else "failed", "tail"]

    def finalize(self, spec, status, reason, flags):
        self.final = (status, reason, flags)
        return status


def _spec():
    return {"wave_id": "W-THIN-1", "target_date": "2026-10-05", "trigger": "T1",
            "level": "L1", "provider": "agy", "attempt": 0, "order_hash": ""}


def test_finish_fail_l1_du_thi_mien_demoted(monkeypatch):
    """L1 đủ mà Gold thiếu: FAILED nhưng không tính vào chuỗi hỏng."""
    monkeypatch.setattr(wave_flow, "l1_full_gold_short", lambda wave_id: True)
    ops = _FakeOps(finish_ok=False)
    assert drive_wave(_spec(), ops, load_config()) == "FAILED"
    assert ops.final[2]["failure"] is False
    assert "ADR 0018" in ops.final[1]


def test_finish_fail_thieu_l1_thi_van_demoted(monkeypatch):
    """Thiếu cả L1: giữ hành vi cũ, vẫn tính vào chuỗi hỏng."""
    monkeypatch.setattr(wave_flow, "l1_full_gold_short", lambda wave_id: False)
    ops = _FakeOps(finish_ok=False)
    assert drive_wave(_spec(), ops, load_config()) == "FAILED"
    assert ops.final[2]["failure"] is True
    assert "ADR 0018" not in ops.final[1]


def test_dot_khong_ton_tai_thi_khong_mien():
    """Đợt không có bảng ánh xạ thì không đủ dữ kiện, giữ hành vi cũ."""
    assert wave_flow.l1_full_gold_short("W-KHONG-TON-TAI-XYZ") is False
