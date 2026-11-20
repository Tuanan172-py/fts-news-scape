"""Kiểm thử phục hồi thu thập sau sự cố: ngày đăng bài cào bù, phân trang, mốc đọc lùi, đối soát, cảnh báo, tồn đọng."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from scripts import capture_reconcile  # noqa: E402
from src.core import catchup  # noqa: E402
from src.core.htmldate import extract_published_at, normalize_iso  # noqa: E402
from src.core.models import ScrapeResult  # noqa: E402
from src.core.pagination import CAP_MARK, paginate_until_known  # noqa: E402
from src.db.dedup import DedupCache  # noqa: E402
from src.db.store import ArticleStore  # noqa: E402
from src.monitor.heartbeat import Heartbeat  # noqa: E402
from src.ops.probes import probe_capture_channels  # noqa: E402
from src.ops.sensor import backlog_window, pick_backlog_date  # noqa: E402
from src.pipeline import reconcile as rc  # noqa: E402
from src.scrapers.fireant import FireAntScraper  # noqa: E402

VN = catchup.VN_TZ


# ── Ngày đăng của bài dựng từ URL ────────────────────────────────────────────
def test_published_at_prefers_meta_over_wrong_jsonld():
    page = ('<meta property="article:published_time" content="2026-11-11T10:30:00" />'
            '<script>{"datePublished":"2026-11-11T10:30:00+00:00"}</script>')
    assert extract_published_at(page) == "2026-11-11T10:30:00+07:00"


@pytest.mark.parametrize("raw,want", [
    ("2026-11-11T10:50:32+0700", "2026-11-11T10:50:32+07:00"),
    ("2026-11-11T11:30:41&#x2B;07:00", "2026-11-11T11:30:41+07:00"),
    ("2026-11-11T03:00:00Z", "2026-11-11T10:00:00+07:00"),
    ("không phải ngày", ""),
])
def test_normalize_iso(raw, want):
    assert normalize_iso(raw) == want


def test_published_at_from_itemprop_and_missing():
    assert extract_published_at('<meta content="2026-11-11T11:22:05+07:00" itemprop="datePublished">') \
        == "2026-11-11T11:22:05+07:00"
    assert extract_published_at("<html><title>x</title></html>") == ""


# ── Phân trang theo mốc ──────────────────────────────────────────────────────
def _pages(pages):
    return lambda n: pages[n - 1] if n <= len(pages) else []


def test_featured_item_on_every_page_does_not_hit_cap():
    hot = {"k": "hot"}
    pages = [[hot, {"k": "a"}], [hot, {"k": "b"}], [hot, {"k": "c"}]]
    errors: list[str] = []
    out = paginate_until_known(_pages(pages), lambda i: i["k"], lambda ks: set(ks) & {"b", "c"},
                               max_pages=3, errors=errors, label="x")
    assert [i["k"] for i in out] == ["hot", "a", "b"] and errors == []


def test_cap_message_and_reached_replaces_watermark():
    pages = [[{"k": "a", "d": 3}], [{"k": "b", "d": 2}], [{"k": "c", "d": 1}], [{"k": "z", "d": 0}]]
    errors: list[str] = []
    out = paginate_until_known(_pages(pages), lambda i: i["k"], lambda ks: set(ks),
                               max_pages=4, errors=errors, label="x",
                               reached=lambda page: page[0]["d"] <= 1)
    assert [i["k"] for i in out] == ["a", "b", "c"] and errors == []
    errors.clear()
    paginate_until_known(_pages(pages), lambda i: i["k"], lambda ks: set(),
                         max_pages=2, errors=errors, label="x")
    assert CAP_MARK in errors[0]


# ── Mốc đọc lùi cho API ──────────────────────────────────────────────────────
@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return ArticleStore(db_path=str(tmp_path / "t.db"))


def test_catchup_cutoff_follows_last_complete_run(store):
    now = datetime(2026, 11, 11, 9, 0, tzinfo=VN)
    assert catchup.catchup_cutoff(store, "x", now=now) == now - timedelta(days=1, hours=2)
    catchup.mark_complete(store, "x", now - timedelta(days=3))
    assert catchup.catchup_cutoff(store, "x", now=now) == now - timedelta(days=3, hours=2)
    catchup.mark_complete(store, "x", now - timedelta(days=60))
    assert catchup.catchup_cutoff(store, "x", now=now) == now - timedelta(days=14)


class _Resp:
    status_code = 200

    def __init__(self, posts):
        self._posts = posts

    def json(self):
        return self._posts


class _OffsetHTTP:
    """API FireAnt giả: 20 bài mỗi trang, mỗi bài cách nhau 1 giờ, mới nhất trước."""

    def __init__(self, now):
        self.now, self.offsets = now, []

    def get_response(self, url, params=None, **kw):
        off = params["offset"]
        self.offsets.append(off)
        return _Resp([{"postID": off + i, "title": f"bài {off + i}",
                       "date": (self.now - timedelta(hours=off + i)).isoformat()}
                      for i in range(params["limit"])])


def test_fireant_pages_back_to_cutoff_after_outage(store):
    now = datetime.now(VN)
    catchup.mark_complete(store, "fireant", now - timedelta(hours=50))
    http = _OffsetHTTP(now)
    dedup = DedupCache(store, legacy_json_path="")
    try:
        s = FireAntScraper({"name": "fireant", "watchlist": ["VCB"],
                            "_secrets": {"fireant_token": "t"},
                            "api": {"params": {"type": 1, "offset": 0, "limit": 20}}}, http, dedup)
        items = s.fetch_list()
    finally:
        dedup.close()
    assert http.offsets == [0, 20, 40]          # 60 giờ > 50 giờ + biên 2 giờ
    assert len(items) == 60
    assert catchup.catchup_cutoff(store, "fireant", now=now) > now - timedelta(hours=3)


# ── Kênh đối soát ────────────────────────────────────────────────────────────
VNB_PAGE = """
<div class="list-news">
  <div class="item"><a href="/bai-mot-2026111015480499.htm"><img src="https://cdn/images/2026/11/10/a.jpg"></a>
    <h3 class="title"><a href="/bai-mot-2026111015480499.htm">Bài một</a></h3>
    <span class="timeago need-get-timeago" title="2026-11-10T15:48:00">x</span></div>
  <div class="item"><a href="https://vietnambiz.vn/bai-hai-202611099000001.htm"><img src="https://cdn/images/2026/11/9/b.jpg"></a>
    <h3 class="title">Bài hai</h3></div>
</div>
<div class="sidebar"><div class="item"><a href="/khac-202611111111111.htm">x</a></div></div>
"""


def test_vietnambiz_listing_days_from_stamp_or_thumbnail():
    assert rc.parse_vietnambiz_listing(VNB_PAGE) == [
        ("https://vietnambiz.vn/bai-mot-2026111015480499.htm", "2026-11-10"),
        ("https://vietnambiz.vn/bai-hai-202611099000001.htm", "2026-11-09")]


def test_vietnambiz_stops_when_page_is_older_than_window():
    calls = []

    def fetch(url):
        calls.append(url)
        return VNB_PAGE

    ref = rc.collect_vietnambiz(date(2026, 11, 10), date(2026, 11, 11), fetch, max_pages=5)
    assert len(calls) == 5 * len(rc.VIETNAMBIZ_SECTIONS)   # mỗi trang còn bài trong cửa sổ
    assert list(ref) == ["2026-11-10"]
    calls.clear()
    rc.collect_vietnambiz(date(2026, 11, 11), date(2026, 11, 11), fetch, max_pages=5)
    assert len(calls) == len(rc.VIETNAMBIZ_SECTIONS)       # trang 1 đã cũ hơn cửa sổ


def test_new_sitemap_sources_and_vietstock_pr_filter():
    urls = rc.sitemap_urls("thoibaotaichinhvietnam.vn", date(2026, 10, 30), date(2026, 11, 2),
                           lambda u: None)
    assert [u.rsplit("/", 1)[1] for u in urls] == ["sitemap-month-2026-10.xml", "sitemap-month-2026-11.xml"]
    big = "<urlset>" + "".join(
        f"<url><loc>https://vietstock.vn/2026/11/bai-{i}-{cat}-{i}.htm</loc><lastmod>2026-11-10T08:00:00+07:00</lastmod></url>"
        for i, cat in enumerate(["757", "4511"] * 20000)) + "</urlset>"
    assert len(big) > rc._FAST_PARSE_BYTES
    ref = rc.collect_reference("vietstock.vn", date(2026, 11, 9), date(2026, 11, 11),
                               lambda u: big, date(2026, 11, 11))
    assert len(ref["2026-11-10"]) == 20000
    assert all("-757-" in u for u in ref["2026-11-10"].values())


def test_adaptive_reconcile_window():
    now = datetime(2026, 11, 9, 7, 0, tzinfo=VN).timestamp()
    friday = datetime(2026, 11, 6, 18, 0, tzinfo=VN).timestamp()
    assert capture_reconcile.adaptive_days(None, now) == 3
    assert capture_reconcile.adaptive_days(now - 600, now) == 3
    assert capture_reconcile.adaptive_days(friday, now) == 5        # thứ Hai đọc lại tối thứ Sáu
    assert capture_reconcile.adaptive_days(now - 90 * 86400, now) == capture_reconcile.MAX_DAYS


def test_reconcile_due_respects_domain_floor(store):
    now = 1_000_000.0
    for d in ("cafef.vn", "vietstock.vn"):
        store.set_state(f"reconcile_last_ts:{d}", str(now - 3600))
    due = capture_reconcile.reconcile_due(store, ("cafef.vn", "vietstock.vn", "vietnambiz.vn"),
                                          min_interval=30, fixed_days=None, force=False, now=now)
    assert due == {"cafef.vn": 3, "vietnambiz.vn": 3}
    forced = capture_reconcile.reconcile_due(store, ("vietstock.vn",), min_interval=30,
                                             fixed_days=10, force=True, now=now)
    assert forced == {"vietstock.vn": 10}


# ── Cảnh báo ─────────────────────────────────────────────────────────────────
def test_probe_flags_dead_reference_and_recent_cap(store, tmp_path):
    # The cap state is stamped with the real clock, so the coverage rows must be too.
    now = datetime.now(VN).replace(microsecond=0)
    conn = sqlite3.connect(tmp_path / "t.db")
    for d in rc.REFERENCE_DOMAINS:
        checked = "2026-10-23T17:19:27+07:00" if d == "baodautu.vn" else now.isoformat()
        conn.execute("INSERT INTO capture_coverage (day, source_domain, ref_n, in_db_n, missing_n, "
                     "backfilled_n, checked_at) VALUES (?, ?, 1, 1, 0, 0, ?)",
                     (now.date().isoformat(), d, checked))
    conn.commit()
    conn.close()
    res = probe_capture_channels(tmp_path / "t.db", now=now)
    assert not res.ok and "baodautu.vn" in res.message and "23/10" in res.message
    Heartbeat(store).record_result(ScrapeResult(scraper="baodautu", fetched=10,
                                                errors=[f"baodautu/X: {CAP_MARK} 8 trang"]))
    assert json.loads(store.get_state("pagination_cap:baodautu"))["n"] == 1
    res = probe_capture_channels(tmp_path / "t.db", now=now)
    assert "baodautu chạm trần" in res.message


# ── Phạm vi xử lý và tồn đọng ────────────────────────────────────────────────
def test_backlog_window_wraps_midnight_and_weekend():
    cfg = {"enabled": True, "hours": [19, 7], "weekend_all_day": True}
    assert backlog_window(datetime(2026, 11, 11, 23, 0), cfg)
    assert backlog_window(datetime(2026, 11, 11, 6, 0), cfg)
    assert not backlog_window(datetime(2026, 11, 11, 12, 0), cfg)
    assert backlog_window(datetime(2026, 11, 14, 12, 0), cfg)         # thứ Bảy
    assert not backlog_window(datetime(2026, 11, 11, 23, 0), {**cfg, "enabled": False})


def _pending_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE articles (url_title_hash TEXT, title TEXT, published_at TEXT,
                               source_domain TEXT, content_text TEXT, fetched_at TEXT);
        CREATE TABLE work_items (article_id TEXT, package_path TEXT);
        CREATE TABLE l1_outputs (article_id TEXT, dod_pass INTEGER, l1_source TEXT);
    """)
    thick = "Đoạn văn thứ nhất đủ dài để làm trích dẫn.\n\nĐoạn văn thứ hai đủ dài để làm trích dẫn." * 3
    thin = "Tin ngắn một dòng. " * 25
    rows = [("cu", "2026-10-01T08:00:00+07:00", thick, "2026-10-01T09:00:00+07:00"),
            ("mong", "2026-10-20T08:00:00+07:00", thin, "2026-10-20T09:00:00+07:00"),
            ("khongngay", "", thick, "2026-10-15T09:00:00+07:00"),
            ("moi", "2026-11-11T08:00:00+07:00", thick, "2026-11-11T09:00:00+07:00")]
    for aid, pub, body, fetched in rows:
        conn.execute("INSERT INTO articles VALUES (?,?,?,?,?,?)", (aid, "t", pub, "d", body, fetched))
        conn.execute("INSERT INTO work_items VALUES (?, NULL)", (aid,))
    conn.commit()
    conn.close()


def test_undated_article_belongs_to_capture_day_and_backlog_picks_newest(tmp_path):
    from scripts.article_pack import load_candidates

    db = tmp_path / "m.db"
    _pending_db(db)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    assert [r["article_id"] for r in load_candidates(conn, date="2026-10-15", limit=10,
                                                     only_pending=True)] == ["khongngay"]
    conn.close()
    now = datetime(2026, 11, 11, 22, 0, tzinfo=VN)
    assert pick_backlog_date(db, 3, now=now) == ("2026-10-15", 1)      # 10-20 chỉ có bài mỏng
    assert pick_backlog_date(db, 3, now=now, exclude={"khongngay"}) == ("2026-10-01", 1)
    assert pick_backlog_date(db, 3, now=now, exclude={"khongngay", "cu"}) is None


def test_block_page_is_a_failed_capture_and_bronze_lookup_skips_it(tmp_path):
    from types import SimpleNamespace

    from scripts.maintenance.backfill_deferred import _find_bronze
    from src.crawler.raw_store import RawStore, looks_blocked

    notice = ("<html><body><p>Để đảm bảo máy tính của quý bạn đọc không bị đối tượng xấu lợi "
              "dụng làm công cụ tấn công từ chối dịch vụ (DDoS) vào Cafef, chúng tôi đề nghị "
              "bạn đọc vui lòng đi tiếp.</p></body></html>")
    article = "<html><body>" + "<p>Bài viết dài về an ninh mạng và DDoS.</p>" * 800 + "</body></html>"
    assert looks_blocked(notice)
    assert not looks_blocked(article)          # long real page mentioning DDoS stays content

    store = RawStore(str(tmp_path))
    resp = SimpleNamespace(status_code=200, content=notice.encode("utf-8"), encoding="utf-8",
                           headers={}, url="https://cafef.vn/a.chn")
    cap = store.save("cafef.vn", "https://cafef.vn/a.chn", "h1", resp,
                     fetched_at="2026-11-11T10:00:00+07:00")
    assert cap["capture_status"] == "failed"
    assert cap["error"]["type"] == "blocked"

    # A notice stored earlier as "ok" (before this rule) is not reused as Bronze.
    day = tmp_path / "cafef.vn" / "20261011"
    day.mkdir(parents=True)
    (day / "h2.html").write_text(notice, encoding="utf-8")
    (day / "h2.meta.json").write_text('{"capture_status": "ok"}', encoding="utf-8")
    assert _find_bronze("cafef.vn", "h2", str(tmp_path)) is None


def test_backlog_range_fills_one_wave_across_sparse_dates(tmp_path):
    from scripts.article_pack import load_candidates

    db = tmp_path / "m.db"
    _pending_db(db)
    now = datetime(2026, 11, 11, 22, 0, tzinfo=VN)
    picked = pick_backlog_date(db, 3, now=now, as_range=True)
    assert picked == ("2026-10-01..2026-10-15", 2)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    ids = {r["article_id"] for r in load_candidates(conn, date=picked[0], limit=10,
                                                    only_pending=True)}
    conn.close()
    assert ids == {"khongngay", "cu"}


def test_backlog_skips_dates_whose_candidates_yield_no_paragraphs(tmp_path, monkeypatch):
    import scripts.article_pack as ap

    db = tmp_path / "m.db"
    _pending_db(db)
    now = datetime(2026, 11, 11, 22, 0, tzinfo=VN)
    real = ap.row_paragraphs
    # "khongngay" (2026-10-15) has a body that distills to nothing, like a 4-character stub.
    monkeypatch.setattr(ap, "row_paragraphs",
                        lambda row, **kw: [] if row["article_id"] == "khongngay" else real(row, **kw))
    assert pick_backlog_date(db, 3, now=now) == ("2026-10-01", 1)


def test_candidates_use_the_newest_package_of_a_recaptured_article(tmp_path):
    from scripts.article_pack import load_candidates

    db = tmp_path / "m.db"
    _pending_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO work_items VALUES ('cu', 'work_packages/d/20260904/cu.json')")
    conn.execute("INSERT INTO work_items VALUES ('cu', 'work_packages/d/20261111/cu.json')")
    conn.commit()
    conn.row_factory = sqlite3.Row
    rows = load_candidates(conn, date="2026-10-01", limit=10, only_pending=True,
                           exclude_thin=False)
    conn.close()
    assert [(r["article_id"], r["package_path"]) for r in rows] == [
        ("cu", "work_packages/d/20261111/cu.json")]


def test_collect_baodautu_dates_listing_urls_from_store_then_detail():
    from datetime import date

    from src.pipeline.reconcile import collect_baodautu

    def art(i):
        return f'<article><a href="/bai-so-{i}-d{i}.html">Bai {i}</a></article>'

    pages = {
        "https://baodautu.vn/toan-canh-dau-tu-d2/": art(101) + art(102) + art(103),
        "https://baodautu.vn/toan-canh-dau-tu-d2/p2": art(690) + art(691),
        "https://baodautu.vn/bai-so-102-d102.html": '<span class="post-time">19/11/2026 08:30</span>',
    }
    fetched = []

    def fetch(url):
        fetched.append(url)
        return pages.get(url)

    known = {"baodautu.vn#101": "2026-11-20", "baodautu.vn#103": "2026-11-17",
             "baodautu.vn#690": "2026-11-10", "baodautu.vn#691": "2026-11-11"}
    ref = collect_baodautu(date(2026, 11, 18), date(2026, 11, 20), fetch, known)
    assert set(ref["2026-11-20"]) == {"baodautu.vn#101"}
    assert ref["2026-11-19"] == {"baodautu.vn#102": "https://baodautu.vn/bai-so-102-d102.html"}
    assert "2026-11-17" not in ref
    # Page 2 is wholly older than the window, so paging stops there for this category.
    assert "https://baodautu.vn/toan-canh-dau-tu-d2/p3" not in fetched
    # Only the unknown URL needs a detail page.
    assert [u for u in fetched if u.endswith(".html")] == ["https://baodautu.vn/bai-so-102-d102.html"]
