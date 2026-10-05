"""
Silver phải giải ĐÚNG tiêu đề bài, không rơi về `<h1>` đầu tiên.

Bối cảnh: work-package trước đây không có trường `title`, nên `title_of()` (l1_classifier)
rơi về heading level 1. Với trang công bố thông tin của cafef, `<h1>` là header trang HỒ SƠ
DOANH NGHIỆP ("Ngân hàng TMCP Phát triển T.P Hồ Chí Minh (HOSE)") chứ không phải tiêu đề bài
("HDB: Thông báo thay đổi địa điểm..."). Đo trên monocle.db: 122/1.320 bài lệch — và bài HDB
vì thế MẤT cả `TICKER:HDB`, vốn khớp ngay bằng mã nếu dùng tiêu đề thật.

Cách sửa: `url_title_hash` = sha256(url + title) do scraper tính lúc cào, nằm sẵn trong
meta.json. Silver đối chiếu từng ứng viên với hash đó → CHỨNG MINH được tiêu đề nào đúng,
vẫn thuần tuý/offline/tất định.
"""
from __future__ import annotations

import pytest

from src.agent.entities import EntityRegistry
from src.agent.l1_classifier import title_of
from src.core.models import sha256_hash
from src.handoff.work_package import WorkPackageBuilder
from src.pipeline.silver_builder import SilverBuilder

URL = "https://cafef.vn/hdb-thong-bao-thay-doi-dia-diem-chi-nhanh-quang-ngai-188260825.chn"
REAL_TITLE = "HDB: Thông báo về việc thay đổi địa điểm của Chi nhánh Quảng Ngãi"
PROFILE_H1 = "Ngân hàng TMCP Phát triển T.P Hồ Chí Minh (HOSE)"

HTML = f"""<html><head>
<title>{REAL_TITLE} | CafeF.vn</title>
<meta property="og:title" content="{REAL_TITLE}"/>
</head><body>
<h1>{PROFILE_H1}</h1>
<h2>{REAL_TITLE}</h2>
<p>Ngân hàng thông báo thay đổi địa điểm chi nhánh kể từ ngày 01/09/2026 theo quyết định của
Hội đồng quản trị, địa chỉ mới nằm trên trục đường chính của thành phố Quảng Ngãi.</p>
<p>Việc thay đổi không ảnh hưởng tới hoạt động giao dịch của khách hàng hiện hữu.</p>
</body></html>"""


def _meta(**over) -> dict:
    m = {
        "source_url": URL,
        "url_title_hash": sha256_hash(URL, REAL_TITLE),
        "content_sha256": "x" * 64,
        "html_path": "data/raw_html/cafef.vn/20260825/x.html",
        "fetch_ts": "2026-08-25T10:00:00+07:00",
        "encoding": "utf-8",
        "capture_status": "ok",
    }
    m.update(over)
    return m


@pytest.fixture
def silver() -> dict:
    return SilverBuilder().build(_meta(), HTML.encode("utf-8"))


def test_title_resolved_against_hash_not_first_h1(silver):
    assert silver["title"] == REAL_TITLE
    assert silver["title"] != PROFILE_H1
    assert silver["title_verified"] is True


def test_work_package_carries_title(silver):
    wp = WorkPackageBuilder().build(silver, _meta(), "NEW")
    assert wp["title"] == REAL_TITLE
    # title_of() ưu tiên trường `title`; không có nó sẽ rơi về h1 = header trang hồ sơ
    assert title_of(wp) == REAL_TITLE


def test_ticker_recovered_from_correct_title(silver):
    """Hồi quy cho đúng thiệt hại đã đo: tiêu đề sai làm mất mã cổ phiếu."""
    reg = EntityRegistry([
        {"entity_id": "TICKER:HDB", "type": "TICKER", "code": "HDB",
         "canonical_name": "Ngân hàng TMCP Phát triển Thành phố Hồ Chí Minh",
         "aliases": ["Ngân hàng TMCP Phát triển Thành phố Hồ Chí Minh"],
         "attributes": {}, "sources": []},
    ])
    assert "TICKER:HDB" in [d["entity_id"] for d in reg.detect(silver["title"])]
    assert "TICKER:HDB" not in [d["entity_id"] for d in reg.detect(PROFILE_H1)]


def test_falls_back_when_no_candidate_matches_hash():
    """Toà soạn sửa tít sau khi cào → không ứng viên nào khớp hash.

    Vẫn phải trả tiêu đề tốt nhất (og:title) và đánh dấu CHƯA kiểm chứng để còn truy vết,
    tuyệt đối không rơi về `<h1>` header trang hồ sơ.
    """
    s = SilverBuilder().build(_meta(url_title_hash="0" * 64), HTML.encode("utf-8"))
    assert s["title"] == REAL_TITLE
    assert s["title_verified"] is False


def test_no_hash_available_still_prefers_og_title():
    s = SilverBuilder().build(_meta(url_title_hash=""), HTML.encode("utf-8"))
    assert s["title"] == REAL_TITLE
    assert s["title_verified"] is False
