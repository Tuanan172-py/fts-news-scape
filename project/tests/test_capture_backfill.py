"""Test cào bù URL đã phát hiện và phục hồi Bronze đã mất."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.base_scraper import BaseScraper
from src.core.models import Article
from src.db import registry
from src.db.dedup import DedupCache
from src.db.store import ArticleStore
from src.pipeline.backfill import backfill_pending, recapture_lost_bronze


class _Http:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, referer=None, timeout=30, **kw):
        return self.pages.get(url)


class _Scraper(BaseScraper):
    enriched: list[str] = []

    def fetch_list(self):
        return []

    def parse_item(self, raw):
        return None

    def enrich(self, article):
        article.content_text = "nội dung đầy đủ"
        article.metadata["capture"] = {"capture_status": "ok"}
        type(self).enriched.append(article.url)


@pytest.fixture
def env(tmp_path):
    st = ArticleStore(db_path=str(tmp_path / "b.db"))
    d = DedupCache(st, legacy_json_path="")
    yield st, d
    d.close()


def _factory(d, pages):
    s = _Scraper({"name": "baodautu", "enabled": True}, _Http(pages), d)
    return lambda domain: s


def _page(title):
    return f'<html><head><meta property="og:title" content="{title}"></head></html>'


def test_backfill_turns_discovered_into_captured_article(env):
    st, d = env
    conn = st._connect()
    url = "https://baodautu.vn/bai-mot-d710001.html"
    registry.discover(conn, url, "baodautu.vn", "reconcile")
    conn.commit()
    conn.close()
    stats = backfill_pending(st, _factory(d, {url: _page("Tiêu đề bài số một")}), limit=10)
    assert stats["captured"] == 1 and stats["failed"] == 0
    assert st.get_by_hash(Article(url=url, title="Tiêu đề bài số một",
                                  source_domain="baodautu.vn").url_title_hash) is not None
    conn = st._connect()
    assert conn.execute("SELECT state FROM discovered_urls").fetchone()[0] == "captured"
    conn.close()


def test_failed_url_is_retried_then_dead_lettered_never_dropped(env):
    st, d = env
    conn = st._connect()
    url = "https://baodautu.vn/loi-d710009.html"
    registry.discover(conn, url, "baodautu.vn", "reconcile")
    conn.commit()
    conn.close()
    for _ in range(3):
        backfill_pending(st, _factory(d, {}), limit=10, max_attempts=3)
    conn = st._connect()
    row = conn.execute("SELECT state, attempts, last_error FROM discovered_urls").fetchone()
    assert row["state"] == "dead_letter" and row["attempts"] == 3 and row["last_error"]
    conn.close()


def test_backfill_respects_time_budget(env):
    st, d = env
    conn = st._connect()
    for i in range(3):
        registry.discover(conn, f"https://baodautu.vn/b{i}-d71000{i}.html", "baodautu.vn", "reconcile")
    conn.commit()
    conn.close()
    ticks = iter([0.0, 0.0, 999.0, 999.0, 999.0])
    stats = backfill_pending(st, _factory(d, {}), limit=10, budget_seconds=10,
                             clock=lambda: next(ticks))
    assert stats["tried"] == 1                 # hết ngân sách thì dừng sạch


def test_recapture_uses_stored_title_and_clears_dead_letter(env):
    st, d = env
    art = Article(url="https://baodautu.vn/cu-d710100.html", title="Bài cũ còn trong kho",
                  source_domain="baodautu.vn")
    st.insert_batch([art])
    st.record_silver_failure("data/raw_html/baodautu.vn/20260929/x.meta.json", "2026-09-29T10:00:00+07:00",
                             "state=raw_missing silver_ok=None pkg_ok=False", 1)
    # biến hàng thành dead-letter bằng đúng API của store
    conn = st._connect()
    h = art.url_title_hash
    conn.execute("UPDATE silver_failures SET url_title_hash=?, dead_letter=1", (h,))
    conn.commit()
    conn.close()
    _Scraper.enriched.clear()
    stats = recapture_lost_bronze(st, _factory(d, {}), limit=10)
    assert stats["recaptured"] == 1
    assert _Scraper.enriched == [art.url]
    conn = st._connect()
    assert conn.execute("SELECT COUNT(*) FROM silver_failures").fetchone()[0] == 0
    conn.close()
