"""
Tests cho fuzzy dedup lớp 2 — reprint cross-domain, không false-positive
trên series title (vd "Phân tích kỹ thuật phiên chiều DD/MM").
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.dedup import DedupCache
from src.db.store import ArticleStore


@pytest.fixture
def cache(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    c = DedupCache(store, legacy_json_path="")
    yield c
    c.close()


def test_reprint_cross_domain_detected(cache):
    cache.mark_seen("https://vietstock.vn/1",
                    "Coteccons hút thành công 1.4 ngàn tỷ đồng từ trái phiếu",
                    "vietstock")
    # Cùng tin, nguồn khác, xáo nhẹ thứ tự — phải bắt được
    assert cache.is_similar_title(
        "Coteccons hút thành công 1.4 ngàn tỷ đồng từ trái phiếu doanh nghiệp",
        "tnck")


def test_same_domain_not_checked(cache):
    cache.mark_seen("https://a.com/1", "Tin ABC quan trọng về thị trường", "cafef")
    # Cùng domain → lớp fuzzy bỏ qua (hash layer xử lý)
    assert not cache.is_similar_title("Tin ABC quan trọng về thị trường", "cafef")


def test_series_titles_not_false_positive(cache):
    cache.mark_seen("https://vietstock.vn/pt1",
                    "Phân tích kỹ thuật phiên chiều 21/01: Điều chỉnh ngắn hạn",
                    "vietstock")
    # Cùng series khác ngày + khác nhận định → KHÔNG phải duplicate
    assert not cache.is_similar_title(
        "Phân tích kỹ thuật phiên chiều 10/02: Đà giảm chững lại", "tnck")


def test_different_stories_not_matched(cache):
    cache.mark_seen("https://a.com/1", "HPG lãi kỷ lục quý 2", "cafef")
    assert not cache.is_similar_title("VNM chia cổ tức tiền mặt 12%", "tnck")


def test_old_titles_outside_window(cache):
    cache.mark_seen("https://a.com/1", "Tin cũ hơn 48 giờ về HPG tăng trần", "cafef")
    # Window 0 giờ → không còn candidate nào
    assert not cache.is_similar_title("Tin cũ hơn 48 giờ về HPG tăng trần",
                                      "tnck", hours=0)
