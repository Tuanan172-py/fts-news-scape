"""Tests cho core/tickers.py — tag_tickers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.tickers import tag_tickers

WATCHLIST = ["HPG", "VNM", "FPT", "SSI", "VND"]


def test_basic_match():
    assert tag_tickers("HPG tăng trần, VNM giảm nhẹ", WATCHLIST) == ["HPG", "VNM"]


def test_stoplist_excludes_common_terms():
    # GDP/CPI/CEO không phải mã dù viết hoa 3 chữ; VND bị stoplist (tiền tệ)
    assert tag_tickers("GDP tăng 8%, CPI ổn định, CEO từ nhiệm, 5 tỷ VND",
                       WATCHLIST + ["GDP"]) == []


def test_no_partial_word_match():
    # "FPTS" không match FPT (word boundary)
    assert tag_tickers("FPTS công bố KQKD", WATCHLIST) == []


def test_dedupe_preserves_order():
    assert tag_tickers("SSI rồi HPG rồi lại SSI", WATCHLIST) == ["SSI", "HPG"]


def test_empty_input():
    assert tag_tickers("", WATCHLIST) == []
    assert tag_tickers("HPG", []) == []
