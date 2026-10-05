"""Test phân trang theo watermark, đối chiếu sitemap và cào bù theo URL (rule 10)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.base_scraper import BaseScraper
from src.core.htmltitle import extract_page_title, is_valid_title
from src.core.models import Article
from src.core.pagination import paginate_until_known
from src.db import registry
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.pipeline.reconcile import parse_urlset, reconcile, sitemap_urls
from src.scrapers.baodautu import _slug_title


# -- phân trang ---------------------------------------------------------------
def _pages(data):
    return lambda p: data.get(p, [])


def test_pagination_stops_at_first_fully_known_page():
    pages = {1: [{"k": "a"}, {"k": "b"}], 2: [{"k": "c"}, {"k": "d"}], 3: [{"k": "e"}]}
    out = paginate_until_known(_pages(pages), lambda i: i["k"], lambda ks: {"c", "d"} & set(ks),
                               max_pages=5)
    assert [i["k"] for i in out] == ["a", "b", "c", "d"]        # dừng sau trang 2, không đọc trang 3


def test_pagination_reads_past_page_one_when_page_one_is_new():
    pages = {1: [{"k": "a"}], 2: [{"k": "b"}], 3: [{"k": "c"}]}
    out = paginate_until_known(_pages(pages), lambda i: i["k"], lambda ks: set(), max_pages=3)
    assert len(out) == 3


def test_pagination_cap_is_reported_not_silent():
    pages = {p: [{"k": str(p)}] for p in range(1, 6)}
    errors: list[str] = []
    paginate_until_known(_pages(pages), lambda i: i["k"], lambda ks: set(), max_pages=3,
                         errors=errors, label="x")
    assert errors and "chạm trần" in errors[0]


def test_pagination_page_failure_is_reported():
    errors: list[str] = []
    out = paginate_until_known(lambda p: [{"k": "a"}] if p == 1 else None,
                               lambda i: i["k"], lambda ks: set(), max_pages=4, errors=errors)
    assert len(out) == 1 and "lỗi" in errors[0]


def test_min_pages_forces_reading_even_when_known():
    pages = {1: [{"k": "a"}], 2: [{"k": "b"}]}
    out = paginate_until_known(_pages(pages), lambda i: i["k"], lambda ks: set(ks),
                               min_pages=2, max_pages=5)
    assert len(out) == 2


# -- tiêu đề ------------------------------------------------------------------
def test_slug_title_drops_article_id():
    assert _slug_title("/ha-noi-thong-nhat-lap-cong-d710855.html") == "ha noi thong nhat lap cong"


@pytest.mark.parametrize("t,ok", [("1", False), ("2", False), ("", False),
                                  ("12345678", False), ("Giá vàng giảm mạnh", True)])
def test_valid_title(t, ok):
    assert is_valid_title(t) is ok


def test_extract_title_prefers_og_then_h1_then_title():
    html = ('<html><head><meta property="og:title" content="Bài về lãi suất ngân hàng">'
            "<title>x | Báo A</title></head><body><h1>Khác</h1></body></html>")
    assert extract_page_title(html) == "Bài về lãi suất ngân hàng"
    assert extract_page_title("<html><head><title>Tin chứng khoán hôm nay | CafeF</title></head></html>") \
        == "Tin chứng khoán hôm nay"
    assert extract_page_title("<html><head><title>1</title></head></html>") == ""


# -- sitemap ------------------------------------------------------------------
BAO_SITEMAP = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://baodautu.vn</loc><lastmod>2026-10-02T10:00:00+07:00</lastmod></url>
<url><loc>https://baodautu.vn/bai-mot-d710001.html</loc><lastmod>2026-10-01T09:00:00+07:00</lastmod></url>
<url><loc>https://baodautu.vn/bai-hai-d710002.html</loc><lastmod>2026-10-02T09:00:00+07:00</lastmod></url>
<url><loc>https://baodautu.vn/bai-ba-d710003.html</loc><lastmod>2026-10-02T11:00:00+07:00</lastmod></url>
<url><loc>https://baodautu.vn/cu-d1.html</loc><lastmod>2026-08-01T11:00:00+07:00</lastmod></url>
</urlset>"""


def test_parse_urlset_handles_namespace():
    got = parse_urlset(BAO_SITEMAP)
    assert got[1] == ("https://baodautu.vn/bai-mot-d710001.html", "2026-10-01T09:00:00+07:00")
    assert parse_urlset("<not xml") == []


def test_sitemap_urls_per_month_and_cafef_windows():
    fetch = lambda u: ('<sitemapindex xmlns="x"><sitemap><loc>https://cafef.vn/sitemaps/sitemaps-2026-10-1-5.xml</loc></sitemap>'
                       '<sitemap><loc>https://cafef.vn/sitemaps/sitemaps-2026-9-26-30.xml</loc></sitemap>'
                       '<sitemap><loc>https://cafef.vn/sitemaps/sitemaps-2026-8-1-5.xml</loc></sitemap></sitemapindex>')
    assert sitemap_urls("baodautu.vn", date(2026, 9, 29), date(2026, 10, 2), fetch) == [
        "https://baodautu.vn/sitemaps/news-2026-9.xml", "https://baodautu.vn/sitemaps/news-2026-10.xml"]
    cf = sitemap_urls("cafef.vn", date(2026, 9, 29), date(2026, 10, 2), fetch)
    assert "https://cafef.vn/sitemaps/sitemaps-2026-10-1-5.xml" in cf
    assert "https://cafef.vn/sitemaps/sitemaps-2026-9-26-30.xml" in cf
    assert "https://cafef.vn/sitemaps/sitemaps-2026-8-1-5.xml" not in cf


@pytest.fixture
def store(tmp_path):
    return ArticleStore(db_path=str(tmp_path / "r.db"))


def test_reconcile_reports_missing_and_registers_them(store):
    store.insert_batch([Article(url="https://baodautu.vn/bai-mot-d710001.html",
                                title="Bài một đủ dài", source_domain="baodautu.vn",
                                fetched_at="2026-10-01T10:00:00+07:00")])
    conn = store._connect()
    rep = reconcile(conn, lambda u: BAO_SITEMAP if "news-2026-10" in u else None,
                    domains=("baodautu.vn",), days=2, today=date(2026, 10, 2))
    assert rep["baodautu.vn"]["2026-10-01"] == {"ref_n": 1, "in_db_n": 1, "missing_n": 0}
    assert rep["baodautu.vn"]["2026-10-02"] == {"ref_n": 2, "in_db_n": 0, "missing_n": 2}
    pend = {r["url_canonical"] for r in registry.pending(conn, "baodautu.vn")}
    assert pend == {"baodautu.vn#710002", "baodautu.vn#710003"}      # gốc "/" và ngày cũ bị loại
    row = conn.execute("SELECT missing_n FROM capture_coverage WHERE day='2026-10-02'").fetchone()
    assert row[0] == 2
    conn.close()


def test_reconcile_is_idempotent_and_counts_backfill(store):
    conn = store._connect()
    fetch = lambda u: BAO_SITEMAP if "news-2026-10" in u else None
    reconcile(conn, fetch, domains=("baodautu.vn",), days=1, today=date(2026, 10, 2))
    reconcile(conn, fetch, domains=("baodautu.vn",), days=1, today=date(2026, 10, 2))
    assert conn.execute("SELECT COUNT(*) FROM discovered_urls WHERE state='discovered'").fetchone()[0] == 2
    conn.close()


# -- cào bù theo URL ----------------------------------------------------------
class _FakeHttp:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, referer=None, timeout=30, **kw):
        return self.pages.get(url)


class _S(BaseScraper):
    def fetch_list(self):
        return []

    def parse_item(self, raw):
        return None

    def enrich(self, article):
        article.content_text = "nội dung"


def test_backfill_url_builds_article_with_real_title(tmp_path):
    st = ArticleStore(db_path=str(tmp_path / "b.db"))
    d = DedupCache(st, legacy_json_path="")
    url = "https://baodautu.vn/bai-hai-d710002.html"
    http = _FakeHttp({url: '<html><head><meta property="og:title" content="Tiêu đề thật của bài hai"></head></html>'})
    s = _S({"name": "baodautu", "enabled": True}, http, d)
    a = s.backfill_url(url)
    assert a is not None and a.title == "Tiêu đề thật của bài hai"
    assert a.source_domain == "baodautu.vn" and a.processed_at
    assert a.content_text == "nội dung"
    assert s.backfill_url("https://baodautu.vn/loi-d1.html") is None      # tải lỗi
    d.close()
