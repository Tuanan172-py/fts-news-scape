"""
Audit fixes: A (TEMPLATE_DRIFT giả), B/C (refresh hardening), D (DoD span), F (scheduler lock).
"""

from __future__ import annotations

from _fakes import FakeHTTP

from src.agent.dod import check_dod
from src.crawler.raw_store import RawStore
from src.db.store import ArticleStore
from src.pipeline.change_detect import classify, dom_path_sig
from src.pipeline.refresh import refresh_row, refresh_watchlist

_HTML = "<html><body><article><h1>T</h1><p>" + "alpha " * 60 + "</p></article></body></html>"


# -- Fix A: TEMPLATE_DRIFT giả ----------------------------------------------
def test_dom_sig_empty_for_degenerate_structure():
    assert dom_path_sig({"headings": [], "paragraphs": [], "tables": [], "links": []}) == ""
    assert dom_path_sig({"headings": [{"level": 1}], "paragraphs": [], "tables": []}) != ""


def test_classify_no_false_template_drift_on_empty_cur_sig():
    prev = {"content_sha256": "old", "simhash64": "0",
            "dom_path_sig": "realsig123456", "selector_ok": True}
    cur = {"content_sha256": "new", "simhash64": "0",
           "dom_path_sig": "", "selector_ok": True}  # extraction hụt cấu trúc
    state, _ = classify(prev, cur)
    assert state == "CONTENT_CHANGED"  # KHÔNG phải TEMPLATE_DRIFT


# -- Fix C: refresh bỏ qua capture trùng ngày -------------------------------
def test_refresh_row_skips_same_day_existing(tmp_path):
    raw_store = RawStore(str(tmp_path / "raw"))
    http = FakeHTTP(detail_html=_HTML)
    row = {"url": "https://cafef.vn/x.chn", "url_title_hash": "h1", "source_domain": "cafef.vn"}
    r1 = refresh_row(http, raw_store, None, row, fetched_at="2026-08-17T00:00:00+07:00")
    assert r1["capture_status"] == "ok" and http.detail_calls == 1
    r2 = refresh_row(http, raw_store, None, row, fetched_at="2026-08-17T09:00:00+07:00")
    assert r2["capture_status"] == "skipped_exists" and http.detail_calls == 1  # không fetch lại


# -- Fix B: 1 URL lỗi không làm sập cả watch-list ---------------------------
class _BoomHTTP:
    def get_response(self, url, **kw):
        raise RuntimeError("network down")


def test_refresh_watchlist_survives_bad_url(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    conn = store.connect()
    conn.execute(
        "INSERT INTO articles (url, url_title_hash, title, source_domain, fetched_at) "
        "VALUES (?,?,?,?,?)",
        ("https://cafef.vn/a.chn", "a", "A", "cafef.vn", "2026-08-17T00:00:00+07:00"))
    conn.commit()
    conn.close()
    summary = refresh_watchlist(store, _BoomHTTP(), limit=5, respect_robots=False,
                                raw_dir=str(tmp_path / "raw"), do_process=False)
    assert summary["selected"] == 1 and summary["skipped"] == 1  # không raise ra ngoài


# -- Fix D: DoD từ chối span quá ngắn ---------------------------------------
def test_dod_rejects_short_span():
    wp = {"cleaned_text": "Nội dung bài viết rất dài và đầy đủ về thị trường chứng khoán."}
    out = {
        "output_schema_version": "1.0", "article_id": "a",
        "summary": {"abstractive": "x"}, "implication": {"text": "y"},
        "materiality": {"score": 0.5}, "confidence": 0.9,
        "citations": [{"claim": "c", "source_span": "."},
                      {"claim": "d", "source_span": "VN"}],
        "processing_metadata": {"agent_provider": "p", "model_used": "m", "timestamp": "t"},
        "extraction_quality": "high",
    }
    ok, reasons = check_dod(out, wp)
    assert not ok and any("too short" in r for r in reasons)


# -- Fix F: advisory scheduler lock -----------------------------------------
def test_scheduler_lock_mutual_exclusion(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    assert store.try_acquire_lock("scheduler", "ownerA", 2400) is True
    assert store.try_acquire_lock("scheduler", "ownerB", 2400) is False  # A đang giữ
    assert store.try_acquire_lock("scheduler", "ownerA", 2400) is True   # chính chủ re-acquire
    assert store.try_acquire_lock("scheduler", "ownerB", -1) is True     # stale → B chiếm lại
