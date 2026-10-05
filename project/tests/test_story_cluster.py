"""Test cụm hoá trùng lặp: gộp đúng bản chép, không gộp nhầm các ca đã quan sát thật."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.models import Article
from src.db.store import ArticleStore
from src.pipeline import story_cluster as sc

VN = timezone(timedelta(hours=7))
T0 = datetime(2026, 9, 30, 9, 0, tzinfo=VN)


def words(prefix: str, n: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def doc(i, title, text, src="cafef.vn", hours=0.0, symbols=()):
    return sc.make_doc(f"a{i}", title, src, (T0 + timedelta(hours=hours)).timestamp(), text,
                       frozenset(symbols))


def roles(rows):
    return {r["article_id"]: r for r in rows}


def test_identical_body_is_copy_by_sha():
    body = words("x", 120)
    rows = roles(sc.build_clusters([
        doc(1, "Tin về lãi suất", body, hours=0), doc(2, "Tin về lãi suất", body, src="vietstock.vn", hours=1)]))
    assert rows["a1"]["role"] == "canonical" and rows["a2"]["role"] == "copy"
    assert rows["a2"]["method"] == "sha" and rows["a2"]["evidence"]["inherit_from"] == "a1"
    assert rows["a1"]["cluster_id"] == rows["a2"]["cluster_id"]


def test_near_verbatim_reprint_with_same_numbers_and_tickers_is_copy():
    base = words("t", 200)
    other = words("t", 196) + " " + words("z", 4)              # chồng trên 95%
    rows = roles(sc.build_clusters([
        doc(1, "AgriS SBT vượt kế hoạch 500 tỷ", "SBT 500 " + base, hours=0, symbols=["SBT"]),
        doc(2, "AgriS SBT vượt kế hoạch 500 tỷ đẩy mạnh đầu tư", "SBT 500 " + other, src="vietstock.vn",
            hours=3, symbols=["SBT"])]))
    assert rows["a2"]["role"] == "copy" and rows["a2"]["method"] == "shingle"


def test_rewrite_at_85_percent_is_candidate_not_copy():
    """Bản viết lại không được kế thừa kết quả vì trích dẫn nguyên văn sẽ không còn đúng."""
    base = words("t", 200)
    other = words("t", 170) + " " + words("z", 30)
    rows = roles(sc.build_clusters([
        doc(1, "AgriS SBT vượt kế hoạch 500 tỷ", "SBT 500 " + base, hours=0, symbols=["SBT"]),
        doc(2, "AgriS SBT vượt kế hoạch 500 tỷ đẩy mạnh đầu tư", "SBT 500 " + other, src="vietstock.vn",
            hours=3, symbols=["SBT"])]))
    assert rows["a2"]["role"] == "candidate"


def test_tiny_boilerplate_pages_are_not_merged():
    """Hai infographics khác địa phương gần như chỉ có văn mẫu: thiếu shingle để tin containment."""
    boiler = words("i", 30)
    rows = sc.build_clusters([
        doc(1, "Infographics Những con số kinh tế Hà Nội 9 tháng năm 2026", boiler, hours=0),
        doc(2, "Infographics Bức tranh kinh tế TP Hồ Chí Minh 9 tháng năm 2026", boiler + " khác", hours=1)])
    assert len({r["cluster_id"] for r in rows}) == 2


def test_ticker_chain_does_not_bridge_unrelated_events():
    """Nhiều tin cùng mã PNJ nhưng khác sự kiện không được nối thành một cụm lớn."""
    bg = words("bg", 90)                                         # đoạn nền chung dài
    docs = [
        doc(1, "PNJ muốn phát hành riêng lẻ tối đa 550 triệu cổ phiếu", "PNJ 550 " + bg + words("e1_", 120),
            hours=0, symbols=["PNJ"]),
        doc(2, "PNJ bổ nhiệm giám đốc cao cấp chiến lược", "PNJ " + bg + words("e2_", 120), hours=2, symbols=["PNJ"]),
        doc(3, "Vốn hóa PNJ giảm hơn 5.000 tỷ đồng chỉ vài ngày", "PNJ 5000 " + bg + words("e3_", 120),
            hours=4, symbols=["PNJ"])]
    rows = sc.build_clusters(docs)
    assert len({r["cluster_id"] for r in rows}) == 3


def test_update_with_new_number_is_candidate_not_copy():
    """PVcomBank: cùng mã, số liệu đổi 60% thành 40% là tin mới, không được gộp."""
    base = words("p", 200)
    rows = roles(sc.build_clusters([
        doc(1, "PVcomBank PCB muốn bán cổ phiếu giá cao hơn 60% thị giá", "PCB 60 " + base, hours=0, symbols=["PCB"]),
        doc(2, "PVcomBank PCB chốt giá chào bán 13.628 đồng cao hơn gần 40%",
            "PCB 13628 40 " + words("p", 130) + " " + words("n", 70), hours=20, symbols=["PCB"])]))
    assert rows["a1"]["role"] == "canonical"
    assert rows["a2"]["role"] == "candidate"
    assert rows["a2"]["evidence"]["same_event_as"] == "a1"
    assert rows["a1"]["cluster_id"] == rows["a2"]["cluster_id"]


def test_boilerplate_between_different_companies_is_not_related():
    """MBB, MSN, HCM dùng chung văn mẫu công bố thông tin: không phải cùng sự kiện."""
    boiler = words("b", 60)
    docs = [doc(i, f"{t}: Nghị quyết HĐQT số {i}", f"{t} {boiler} " + words(f"u{i}_", 80),
                hours=i, symbols=[t])
            for i, t in enumerate(["MBB", "MSN", "HCM", "HDB", "VPB", "GAS", "MWG", "FPT"], start=1)]
    rows = sc.build_clusters(docs)
    assert len({r["cluster_id"] for r in rows}) == len(docs)
    assert all(r["role"] == "canonical" for r in rows)


def test_periodic_column_different_days_never_merged():
    template = words("g", 150)
    rows = sc.build_clusters([
        doc(1, "Giá vàng miếng sáng 28/9 đồng loạt giảm", template + " 143800", hours=0),
        doc(2, "Giá vàng miếng sáng 29/9 đồng loạt giảm", template + " 141500", hours=24)])
    assert len({r["cluster_id"] for r in rows}) == 2
    assert all(r["role"] == "canonical" for r in rows)
    assert {r["method"] for r in rows} == {"series"}            # được đánh dấu là chuyên mục định kỳ


def test_candidate_outside_time_window_is_not_linked():
    base = words("q", 200)
    rows = sc.build_clusters([
        doc(1, "VNM công bố kế hoạch chia cổ tức 20%", "VNM 20 " + base, hours=0, symbols=["VNM"]),
        doc(2, "VNM chia cổ tức tiền mặt 2000 đồng", "VNM 2000 " + words("q", 120) + words("r", 80),
            hours=200, symbols=["VNM"])])
    assert len({r["cluster_id"] for r in rows}) == 2


def test_canonical_is_earliest_regardless_of_input_order():
    body = words("e", 120)
    rows = roles(sc.build_clusters([
        doc(2, "Bản đăng lại", body, hours=5), doc(1, "Bản gốc", body, hours=0), doc(3, "Bản thứ ba", body, hours=9)]))
    assert rows["a1"]["role"] == "canonical"
    assert rows["a2"]["role"] == rows["a3"]["role"] == "copy"
    assert rows["a3"]["evidence"]["inherit_from"] == "a1"


def test_short_bodies_do_not_match_by_sha():
    rows = sc.build_clusters([doc(1, "Tin ngắn một", "ngắn", hours=0), doc(2, "Tin ngắn hai", "ngắn", hours=1)])
    assert len({r["cluster_id"] for r in rows}) == 2


def test_numbers_normalisation_and_significance():
    assert sc.numbers_of("lãi 10.000 tỷ, tăng 7,5%") == frozenset({"10000", "75"})
    assert sc.significant_numbers(frozenset({"28", "9", "2026", "13628", "500"})) == frozenset({"13628", "500"})


# -- DB -----------------------------------------------------------------------
@pytest.fixture
def store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "c.db"))


def _art(url, title, text, hours, src="cafef.vn", symbols=None):
    return Article(url=url, title=title, source_domain=src, content_text=text,
                   published_at=(T0 + timedelta(hours=hours)).isoformat(timespec="seconds"),
                   fetched_at=(T0 + timedelta(hours=hours)).isoformat(timespec="seconds"),
                   symbols=symbols or [])


def test_run_writes_cluster_tables_and_is_idempotent(store):
    body = words("d", 150)
    store.insert_batch([
        _art("https://cafef.vn/a-188260930010000001.chn", "Thương vụ M&A của Tasco", body, 0),
        _art("https://vietstock.vn/b.htm", "Thương vụ M&A của Tasco hôm nay", body, 2, "vietstock.vn"),
        _art("https://cafef.vn/c-188260930010000002.chn", "Tin hoàn toàn khác", words("o", 150), 1)])
    conn = store._connect()
    now = T0 + timedelta(hours=12)
    first = sc.run(conn, days=3, today=now)
    assert first["docs"] == 3 and first["clusters"] == 2 and first["copy"] == 1
    second = sc.run(conn, days=3, today=now)
    assert second == first
    sizes = dict(conn.execute("SELECT cluster_id, n_members FROM story_clusters").fetchall())
    assert sorted(sizes.values()) == [1, 2]
    n_src = conn.execute("SELECT n_sources FROM story_clusters WHERE n_members=2").fetchone()[0]
    assert n_src == 2
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 3     # không xoá bài nào
    conn.close()


def test_orphan_cluster_removed_when_membership_changes(store):
    conn = store._connect()
    conn.execute("INSERT INTO story_clusters (cluster_id, canonical_id) VALUES ('Sdead','zzz')")
    conn.commit()
    store.insert_batch([_art("https://cafef.vn/a-188260930010000009.chn", "Một bài lẻ loi", words("l", 150), 0)])
    sc.run(conn, days=3, today=T0 + timedelta(hours=1))
    assert conn.execute("SELECT COUNT(*) FROM story_clusters WHERE cluster_id='Sdead'").fetchone()[0] == 0
    conn.close()
