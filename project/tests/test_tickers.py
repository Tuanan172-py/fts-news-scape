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


def test_location_context_not_tagged():
    wl = WATCHLIST + ["HCM"]
    for title in ("WB phê duyệt gói tín dụng 125 triệu USD cho TP.HCM",
                  "Ông Tô Duy Lâm thôi giữ chức Giám đốc NHNN chi nhánh TP.HCM",
                  "Nhà trọ TP HCM tăng giá", "Tp. HCM công bố quy hoạch",
                  "Ông Lê Quốc Phong làm Chủ tịch UBND HCM",
                  "Giá nhà ở Thành phố HCM tăng", "HCM City metro opens", "HCMC office market"):
        assert tag_tickers(title, wl) == [], title


def test_securities_ticker_still_tagged_next_to_city():
    wl = WATCHLIST + ["HCM"]
    assert tag_tickers("HCM báo lãi quý 3, TP.HCM tăng trưởng", wl) == ["HCM"]
    assert tag_tickers("Cổ phiếu HCM tăng trần", wl) == ["HCM"]
    assert tag_tickers("SSI, HCM, VND: dòng tiền vào nhóm chứng khoán", wl) == ["SSI", "HCM"]
