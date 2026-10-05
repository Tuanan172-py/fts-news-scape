"""Test sổ phát hiện URL và quy tắc không bỏ sót ở tầng cào (rule 10, ADR 0013)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.base_scraper import BaseScraper
from src.core.models import Article
from src.core.urlnorm import canonical_url, url_key
from src.db import registry
from src.db.dedup import DedupCache
from src.db.store import ArticleStore


def test_canonical_strips_tracking_and_trailing_slash():
    a = canonical_url("https://www.Example.com/a/b/?utm_source=x&fbclid=1&id=7#frag")
    assert a == "https://example.com/a/b?id=7"


def test_cafef_key_is_article_id_even_when_slug_differs():
    u1 = "https://cafef.vn/tap-doan-my-he-lo-188260928105418328.chn?utm_source=du-lieu"
    u2 = "https://cafef.vn/tap-doan-my-chi-mua-499-msr-188260928105418328.chn"
    assert url_key(u1) == url_key(u2) == "cafef.vn#188260928105418328"


def test_baodautu_key_uses_d_id():
    assert url_key("https://baodautu.vn/ten-bai-d710855.html") == "baodautu.vn#710855"


def test_unknown_domain_falls_back_to_canonical():
    assert url_key("https://x.vn/a/?utm_medium=z") == "https://x.vn/a"
    assert url_key("http://x.vn/a") == url_key("https://www.x.vn/a/")        # scheme và www không tách khoá


@pytest.mark.parametrize("u,key", [
    ("https://vietnambiz.vn/mbs-loi-nhuan-thep-202610210924242.htm", "vietnambiz.vn#202610210924242"),
    ("https://vietnambiz.vn/tieu-de-khac-hoan-toan-202610210924242.htm", "vietnambiz.vn#202610210924242"),
    ("http://vietstock.vn/2026/10/co-hoi-an-cu-4220-1498243.htm", "vietstock.vn#1498243"),
    ("https://www.tinnhanhchungkhoan.vn/pnj-duoc-giai-cuu-post398707.html", "tinnhanhchungkhoan.vn#398707"),
    ("https://thoibaotaichinhvietnam.vn/gia-dau-giam-204741.html", "thoibaotaichinhvietnam.vn#204741"),
    ("https://fireant.vn/dashboard/content/42068124", "fireant.vn#42068124"),
])
def test_source_ids_for_every_listed_domain(u, key):
    assert url_key(u) == key


def test_rekey_merges_rows_and_keeps_most_advanced_state(store):
    conn = store._connect()
    now = "2026-10-02T10:00:00+07:00"
    for k, st in (("https://vietnambiz.vn/a-202610210924242.htm", "discovered"),
                  ("https://vietnambiz.vn/b-202610210924242.htm", "captured")):
        conn.execute("INSERT INTO discovered_urls (url_canonical, source_domain, first_url, first_seen_via, "
                     "first_seen_at, last_seen_at, state, article_hash) VALUES (?, 'vietnambiz.vn', ?, 'rss', ?, ?, ?, 'h')",
                     (k, k, now, now, st))
    stats = registry.rekey(conn)
    conn.commit()
    assert stats["merged"] == 1
    rows = conn.execute("SELECT url_canonical, state FROM discovered_urls").fetchall()
    assert [tuple(r) for r in rows] == [("vietnambiz.vn#202610210924242", "captured")]
    conn.close()


@pytest.fixture
def store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "t.db"))


def test_discover_new_then_alias(store):
    conn = store._connect()
    k, is_new, alias = registry.discover(conn, "https://cafef.vn/a-188260928105418328.chn?utm_source=q", "cafef.vn")
    assert is_new and not alias
    k2, is_new2, alias2 = registry.discover(conn, "https://cafef.vn/b-188260928105418328.chn", "cafef.vn")
    conn.commit()
    assert k2 == k and not is_new2 and alias2
    assert conn.execute("SELECT COUNT(*) FROM url_aliases").fetchone()[0] == 1
    assert conn.execute("SELECT n_seen FROM discovered_urls").fetchone()[0] == 2
    conn.close()


def test_insert_batch_marks_captured(store):
    art = Article(url="https://baodautu.vn/x-d710855.html", title="Tin dài đủ chữ để hợp lệ",
                  source_domain="baodautu.vn")
    store.insert_batch([art])
    conn = store._connect()
    row = conn.execute("SELECT state, article_hash FROM discovered_urls").fetchone()
    assert row["state"] == "captured" and row["article_hash"] == art.url_title_hash
    conn.close()


def test_backfill_from_existing_articles(tmp_path):
    p = str(tmp_path / "old.db")
    s = ArticleStore(db_path=p)
    s.insert_batch([Article(url="https://baodautu.vn/a-d111111.html", title="Bài cũ số một", source_domain="baodautu.vn")])
    conn = s._connect()
    conn.execute("DELETE FROM discovered_urls")      # giả lập DB trước khi có sổ
    conn.commit()
    conn.close()
    ArticleStore(db_path=p)                          # init_schema chạy lại, nạp bù sổ
    conn = sqlite3.connect(p)
    assert conn.execute("SELECT state FROM discovered_urls").fetchone()[0] == "captured"
    conn.close()


def test_mark_failed_progresses_to_dead_letter(store):
    conn = store._connect()
    k, _, _ = registry.discover(conn, "https://baodautu.vn/z-d222222.html", "baodautu.vn")
    states = [registry.mark_failed(conn, k, "boom", max_attempts=3) for _ in range(3)]
    assert states == ["discovered", "discovered", "dead_letter"]
    assert registry.mark_failed(conn, k, "404", gone=True) == "gone"
    conn.close()


class _Scraper(BaseScraper):
    ITEMS: list[tuple[str, str]] = []

    def fetch_list(self):
        return list(self.ITEMS)

    def parse_item(self, raw):
        return Article(url=raw[0], title=raw[1], source_domain="d.com")

    def enrich(self, article):
        article.content_text = article.title


@pytest.fixture
def dedup(tmp_path):
    st = ArticleStore(db_path=str(tmp_path / "s.db"))
    d = DedupCache(st, legacy_json_path="")
    yield d
    d.close()


def _run(dedup, items):
    cls = type("S", (_Scraper,), {"ITEMS": items})
    return cls({"name": "d", "enabled": True}, http=None, dedup=dedup).run()


def test_near_duplicate_titles_are_never_dropped(dedup):
    """Tiêu đề giống nhau gần hết vẫn phải được giữ: trùng ngữ nghĩa xử lý sau Bronze."""
    res = _run(dedup, [
        ("https://d.com/1", "Giá vàng sập mạnh sau 1 tháng"),
        ("https://d.com/2", "Giá vàng sập mạnh sau 1 tháng liên tiếp"),
        ("https://d.com/3", "1"),
        ("https://d.com/4", "Giá vàng sập mạnh sau 1 tháng"),
    ])
    assert len(res.new) == 4


def test_every_discovered_url_is_in_registry(dedup):
    _run(dedup, [("https://d.com/1", "Một"), ("https://d.com/2", "Hai")])
    conn = dedup.store._connect()
    assert conn.execute("SELECT COUNT(*) FROM discovered_urls").fetchone()[0] == 2
    conn.close()


def test_alias_form_of_captured_article_is_skipped(dedup):
    st = dedup.store
    first = Article(url="https://cafef.vn/a-188260928105418328.chn?utm_source=q", title="Tin A", source_domain="cafef.vn")
    st.insert_batch([first])
    res = _run(dedup, [("https://cafef.vn/a-188260928105418328.chn", "Tin A")])
    assert res.new == []                      # bản sao kỹ thuật cùng mã bài
    conn = st._connect()
    assert conn.execute("SELECT COUNT(*) FROM url_aliases").fetchone()[0] == 1
    conn.close()


def test_same_cycle_alias_pair_yields_one_article(dedup):
    res = _run(dedup, [
        ("https://cafef.vn/a-188260928105418328.chn?utm_source=q", "Tin A"),
        ("https://cafef.vn/a-188260928105418328.chn", "Tin A"),
    ])
    assert len(res.new) == 1


def test_seen_hash_without_article_row_is_recovered(dedup):
    """Bài từng bị đánh dấu đã thấy mà không có dòng `articles` (lọc mờ cũ) phải được lấy lại."""
    dedup.mark_seen("https://d.com/lost", "Bài bị lọc nhầm trước đây", "d.com")
    res = _run(dedup, [("https://d.com/lost", "Bài bị lọc nhầm trước đây")])
    assert len(res.new) == 1


def test_seen_hash_with_captured_article_is_skipped(dedup):
    dedup.store.insert_batch([Article(url="https://d.com/ok", title="Bài đã lưu đủ", source_domain="d.com")])
    assert _run(dedup, [("https://d.com/ok", "Bài đã lưu đủ")]).new == []


def test_same_url_with_new_title_still_recaptured(dedup):
    """Đổi tiêu đề trên cùng URL vẫn đi qua enrich để Bronze ghi bản mới (change detection)."""
    dedup.store.insert_batch([Article(url="https://d.com/9", title="Cũ", source_domain="d.com")])
    res = _run(dedup, [("https://d.com/9", "Mới")])
    assert len(res.new) == 1
