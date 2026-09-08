"""
Tests PeriodicReportSource (NSO) — design 16.

Bất biến chính:
- dedup theo (report_type, period), KHÔNG theo URL/slug
- `modified` đổi → revision MỚI, không ghi đè bản cũ
- không parse được kỳ → HELD + cảnh báo, TUYỆT ĐỐI không đoán bừa
- attachment nhị phân lưu byte-exact, không parse
- Bronze ở ROOT RIÊNG data/raw_reports/ — derive của bài báo không nuốt nhầm
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.db.store import ArticleStore
from src.pipeline.periodic_reports import (
    PeriodicReportSource,
    _safe_key,
    extract_attachments,
    parse_period,
)

REPORT_HTML = (
    '<html><body><main>'
    '<h1>Báo cáo</h1>'
    '<a href="/wp-content/uploads/2026/09/01-Loi-van-T8.2026-final.docx">Lời văn</a>'
    '<a href="https://www.nso.gov.vn/wp-content/uploads/2026/09/02-Bieu-T8.2026.xlsx">Biểu</a>'
    '<a href="/tin-tuc/khac/">Không phải file</a>'
    '<a href="/wp-content/uploads/2026/09/01-Loi-van-T8.2026-final.docx">Trùng</a>'
    '</main></body></html>'
)
XLSX_BYTES = b"PK\x03\x04" + b"fake-xlsx-payload" * 40
DOCX_BYTES = b"PK\x03\x04" + b"fake-docx-payload" * 40


def _post(pid, title, date, modified=None, slug="x"):
    return {"id": pid, "slug": slug, "date": date,
            "modified": modified or date,
            "link": f"https://www.nso.gov.vn/bai-top/2026/09/{slug}/",
            "title": {"rendered": title}, "tags": [727]}


class FakeResp:
    def __init__(self, body=b"", status=200, ctype="text/html; charset=utf-8"):
        self.status_code = status
        self.ok = 200 <= status < 300
        self.content = body if isinstance(body, bytes) else body.encode("utf-8")
        self.text = self.content.decode("utf-8", errors="replace")
        self.encoding = "utf-8"
        self.headers = {"content-type": ctype}


class FakeHTTP:
    """API JSON cho /wp-json; HTML cho trang báo cáo; bytes cho attachment."""

    XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    DOCX_CT = ("application/vnd.openxmlformats-officedocument."
               "wordprocessingml.document")

    def __init__(self, posts=None, report_html=REPORT_HTML, api_status=200):
        self.posts = posts if posts is not None else []
        self.report_html = report_html
        self.api_status = api_status
        self.calls = {"api": 0, "report": 0, "attach": 0}

    def get_response(self, url, **kw):
        if "/wp-json/" in url:
            self.calls["api"] += 1
            if self.api_status != 200:
                return FakeResp(b"", self.api_status)
            page = (kw.get("params") or {}).get("page", 1)
            body = json.dumps(self.posts if page == 1 else [], ensure_ascii=False)
            return FakeResp(body, 200, "application/json; charset=utf-8")
        low = url.lower()
        if low.endswith(".xlsx"):
            self.calls["attach"] += 1
            return FakeResp(XLSX_BYTES, 200, self.XLSX_CT)
        if low.endswith(".docx"):
            self.calls["attach"] += 1
            return FakeResp(DOCX_BYTES, 200, self.DOCX_CT)
        self.calls["report"] += 1
        return FakeResp(self.report_html, 200)

    def get(self, url, **kw):          # RobotsGate
        return ""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    yield store, tmp_path


def _src(http, store, **kw):
    # root RIENG data/raw_reports (mac dinh) - derive cua bai bao KHONG quet vao day
    return PeriodicReportSource(http, store, respect_robots=False, **kw)


# -- parse_period -----------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Báo cáo tình hình kinh tế – xã hội tháng Tám và 8 tháng năm 2026",
     ("monthly", "2026-08")),
    ("Báo cáo tình hình kinh tế - xã hội tháng Bảy và 7 tháng năm 2026",
     ("monthly", "2026-07")),
    ("Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026", ("monthly", "2026-08")),
    ("Báo cáo tình hình kinh tế - xã hội tháng Một năm 2026", ("monthly", "2026-01")),
    ("Báo cáo tình hình kinh tế - xã hội tháng Mười Hai và năm 2025",
     ("monthly", "2025-12")),
    ("Báo cáo tình hình kinh tế - xã hội tháng Mười Một và 11 tháng năm 2025",
     ("monthly", "2025-11")),
    ("Báo cáo tình hình kinh tế – xã hội Quý II và sáu tháng đầu năm 2026",
     ("quarterly", "2026-Q2")),
    ("Báo cáo tình hình kinh tế - xã hội quý IV và năm 2025", ("quarterly", "2025-Q4")),
    ("Báo cáo tình hình kinh tế - xã hội quý I năm 2026", ("quarterly", "2026-Q1")),
    ("Tiêu đề vô nghĩa", None),
    ("", None),
])
def test_parse_period(title, expected):
    assert parse_period(title) == expected


def test_parse_period_never_guesses():
    """Không có năm → None. KHÔNG được suy diễn từ ngày đăng hay slug."""
    assert parse_period("Báo cáo tình hình kinh tế - xã hội tháng Tám") is None


def test_safe_key_no_double_extension():
    """save_binary tự gắn đuôi → key phải bỏ đuôi, tránh `.xlsx.xlsx`."""
    assert _safe_key("monthly-2026-08-r1", "02-Bieu-T8.2026.xlsx") \
        == "monthly-2026-08-r1__02-Bieu-T8.2026"


# -- extract_attachments ----------------------------------------------------

def test_extract_attachments():
    got = extract_attachments(REPORT_HTML, "https://www.nso.gov.vn/bai-top/x/")
    urls = [a["url"] for a in got]
    assert len(got) == 2, "phải bỏ link không phải file và link trùng"
    assert any(u.endswith("02-Bieu-T8.2026.xlsx") for u in urls)
    assert all(u.startswith("https://www.nso.gov.vn/") for u in urls)  # đã urljoin
    # tên file GIỮ NGUYÊN case gốc (chỉ hạ chữ khi so khớp đuôi)
    assert any(a["filename"] == "02-Bieu-T8.2026.xlsx" for a in got)


# -- run() ------------------------------------------------------------------

def test_capture_creates_bronze_html_and_binaries(env):
    store, tmp = env
    http = FakeHTTP([_post(1, "Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026",
                           "2026-09-03T09:00:02")])
    s = _src(http, store)
    summary = s.run()
    assert summary["captured"] == 1 and summary["attachments"] == 2
    assert summary["held_unparsed"] == 0 and summary["failed"] == 0

    files = sorted(p.name for p in (tmp / "data/raw_reports/nso.gov.vn").rglob("*")
                   if p.is_file())
    assert "monthly-2026-08-r1.html" in files
    assert "monthly-2026-08-r1__02-Bieu-T8.2026.xlsx" in files
    assert "monthly-2026-08-r1__01-Loi-van-T8.2026-final.docx" in files
    # byte-exact + sha khớp
    xlsx = next(p for p in (tmp / "data/raw_reports/nso.gov.vn").rglob("*.xlsx"))
    assert xlsx.read_bytes() == XLSX_BYTES
    meta = json.loads((xlsx.parent / (xlsx.name + ".binmeta.json")).read_text("utf-8"))
    assert meta["content_sha256"] == hashlib.sha256(XLSX_BYTES).hexdigest()
    assert meta["capture_status"] == "ok"


def test_dedup_by_period_not_url(env):
    """Cùng (type, period) nhưng slug/URL/id KHÁC → vẫn coi là một, không capture lại."""
    store, _ = env
    title = "Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026"
    http = FakeHTTP([_post(1, title, "2026-09-03T09:00:02", slug="ban-goc")])
    assert _src(http, store).run()["captured"] == 1

    # slug sai năm + hậu tố -2 (đúng như NSO thật), id khác → vẫn cùng kỳ
    http2 = FakeHTTP([_post(999, title, "2026-09-03T09:00:02",
                            slug="bao-cao-...-2025-2")])
    s2 = _src(http2, store)
    summary = s2.run()
    assert summary["skipped_unchanged"] == 1
    assert summary["captured"] == 0
    assert http2.calls["report"] == 0, "không được fetch lại trang báo cáo"


def test_modified_creates_new_revision(env):
    """Bản hiệu đính (`modified` đổi) → revision mới, GIỮ bản cũ."""
    store, tmp = env
    title = "Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026"
    _src(FakeHTTP([_post(1, title, "2026-09-03T09:00:02")]), store).run()
    summary = _src(FakeHTTP([_post(1, title, "2026-09-03T09:00:02",
                                   modified="2026-09-05T10:00:00")]), store).run()
    assert summary["revised"] == 1 and summary["captured"] == 0

    conn = store.connect()
    rows = conn.execute("SELECT revision FROM periodic_reports WHERE period='2026-08' "
                        "ORDER BY revision").fetchall()
    conn.close()
    assert [r["revision"] for r in rows] == [1, 2], "bản cũ phải còn nguyên"
    names = {p.name for p in (tmp / "data/raw_reports/nso.gov.vn").rglob("*.html")}
    assert {"monthly-2026-08-r1.html", "monthly-2026-08-r2.html"} <= names


def test_unparsable_title_is_held_not_guessed(env):
    """Không đọc được kỳ → held + error, KHÔNG capture, KHÔNG bịa kỳ."""
    store, _ = env
    http = FakeHTTP([_post(1, "Thông cáo báo chí về một chủ đề nào đó", "2026-09-03")])
    s = _src(http, store)
    summary = s.run()
    assert summary["held_unparsed"] == 1
    assert summary["captured"] == 0
    assert http.calls["report"] == 0
    assert any("cannot parse period" in e for e in s.errors)
    conn = store.connect()
    assert conn.execute("SELECT COUNT(*) c FROM periodic_reports").fetchone()["c"] == 0
    conn.close()


def test_no_attachments_flag(env):
    store, tmp = env
    http = FakeHTTP([_post(1, "Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026",
                           "2026-09-03T09:00:02")])
    summary = _src(http, store, fetch_attachments=False).run()
    assert summary["captured"] == 1
    assert http.calls["attach"] == 0
    assert not list((tmp / "data/raw_reports/nso.gov.vn").rglob("*.xlsx"))


def test_discover_failure_is_graceful(env):
    store, _ = env
    s = _src(FakeHTTP(api_status=503), store)
    summary = s.run()
    assert summary == {"discovered": 0, "captured": 0, "revised": 0,
                       "skipped_unchanged": 0, "held_unparsed": 0, "failed": 0,
                       "attachments": 0}
    assert any("discover failed" in e for e in s.errors)


def test_quarterly_and_monthly_coexist(env):
    store, _ = env
    http = FakeHTTP([
        _post(1, "Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026",
              "2026-09-03T09:00:02", slug="a"),
        _post(2, "Báo cáo tình hình kinh tế – xã hội Quý II và sáu tháng đầu năm 2026",
              "2026-07-03T08:56:25", slug="b"),
    ])
    summary = _src(http, store).run()
    assert summary["captured"] == 2
    conn = store.connect()
    rows = {(r["report_type"], r["period"]) for r in
            conn.execute("SELECT report_type, period FROM periodic_reports")}
    conn.close()
    assert rows == {("monthly", "2026-08"), ("quarterly", "2026-Q2")}


def test_bronze_root_is_separate_from_articles(env):
    """Bao cao NSO KHONG duoc nam trong data/raw_html - derive cua bai bao quet root do
    va se dung work_item voi article_id khong join duoc voi bang articles."""
    store, tmp = env
    http = FakeHTTP([_post(1, "Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026",
                           "2026-09-03T09:00:02")])
    _src(http, store).run()
    assert (tmp / "data/raw_reports/nso.gov.vn").exists()
    assert not (tmp / "data/raw_html").exists(), "KHONG duoc ghi vao raw_html"


def test_binary_meta_suffix_not_scanned_by_derive(env):
    """File nhi phan dung .binmeta.json - derive rglob('*.meta.json') se KHONG khop,
    tranh dem nham 'raw_missing' cho moi attachment."""
    store, tmp = env
    http = FakeHTTP([_post(1, "Báo cáo tình hình kinh tế - xã hội tháng 8 năm 2026",
                           "2026-09-03T09:00:02")])
    _src(http, store).run()
    root = tmp / "data/raw_reports/nso.gov.vn"
    plain = sorted(p.name for p in root.rglob("*.meta.json")
                   if not p.name.endswith(".binmeta.json"))
    assert plain == ["monthly-2026-08-r1.meta.json"], \
        "chi trang HTML moi dung .meta.json"
    assert len(list(root.rglob("*.binmeta.json"))) == 2
