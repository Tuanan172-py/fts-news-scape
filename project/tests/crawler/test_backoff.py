"""
Tests SourceBackoff (D4) — exponential 2→4→8→16s trên 429/503, reset khi 2xx.
Kiểm state (next_allowed_ts) thay vì sleep thật để nhanh + deterministic.
"""

import time

from src.crawler.backoff import SourceBackoff

D = "cafef.vn"


def _pending(bo, domain):
    return bo._state[domain]["next_allowed_ts"] - time.time()


def test_exponential_growth_then_cap():
    bo = SourceBackoff()
    for expected in (2, 4, 8, 16, 16):  # lần 5 vẫn cap 16
        bo.observe(D, 429)
        assert abs(_pending(bo, D) - expected) < 0.5


def test_reset_on_success():
    bo = SourceBackoff()
    bo.observe(D, 503)
    bo.observe(D, 503)
    assert _pending(bo, D) > 0
    bo.observe(D, 200)
    assert bo._state[D]["consecutive"] == 0
    assert bo._state[D]["next_allowed_ts"] == 0.0


def test_before_fetch_no_pause_when_clear():
    bo = SourceBackoff()
    start = time.time()
    bo.before_fetch(D)  # chưa có state → không ngủ
    assert time.time() - start < 0.2


def test_non_throttle_status_ignored():
    bo = SourceBackoff()
    bo.observe(D, 404)  # không phải 429/503, không phải 2xx → không đổi backoff
    assert D not in bo._state or bo._state[D]["next_allowed_ts"] == 0.0
