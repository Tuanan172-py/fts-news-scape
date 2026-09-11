"""
Test EntityRegistry — đăng ký theo người dùng (select/subscribers_for) + nhận diện text.
Dùng registry nhỏ dựng tay để không phụ thuộc data/entities/entities.json.
"""
from __future__ import annotations

import pytest

from src.agent.entities import EntityRegistry, _user_enabled

ENTITIES = [
    {"entity_id": "TICKER:HPG", "type": "TICKER", "code": "HPG",
     "canonical_name": "CTCP Tập đoàn Hòa Phát",
     "aliases": ["CTCP Tập đoàn Hòa Phát", "Hòa Phát"],
     "attributes": {"gics1": "Nguyên vật liệu"}, "sources": []},
    {"entity_id": "TICKER:VCB", "type": "TICKER", "code": "VCB",
     "canonical_name": "Ngân hàng TMCP Ngoại thương Việt Nam",
     "aliases": ["Ngân hàng TMCP Ngoại thương Việt Nam", "Ngoại thương Việt Nam", "Vietcombank"],
     "attributes": {"gics1": "Tài chính"}, "sources": []},
    {"entity_id": "INDEX:VNINDEX", "type": "INDEX", "code": "VNINDEX",
     "canonical_name": "VN-Index", "aliases": ["VN-Index", "VNINDEX"],
     "attributes": {"exchange": "HOSE"}, "sources": []},
    {"entity_id": "IND_GICS3:THEP", "type": "INDUSTRY_GICS3", "code": "THEP",
     "canonical_name": "Thép", "aliases": ["Thép"], "attributes": {"parent": "x"}, "sources": []},
    {"entity_id": "MACRO_GEO:MY", "type": "MACRO_GEO", "code": "MY",
     "canonical_name": "Mỹ", "aliases": ["Mỹ", "Hoa Kỳ", "US", "USA"],
     "attributes": {}, "sources": []},
    {"entity_id": "MACRO_GEO:NGA", "type": "MACRO_GEO", "code": "NGA",
     "canonical_name": "Nga", "aliases": ["Nga", "Russia"],
     "attributes": {}, "sources": []},
    {"entity_id": "TICKER:VND", "type": "TICKER", "code": "VND",
     "canonical_name": "CTCP Chứng khoán VNDIRECT", "aliases": ["VNDirect", "VNDIRECT"],
     "attributes": {}, "sources": []},
    {"entity_id": "TICKER:PGD", "type": "TICKER", "code": "PGD",
     "canonical_name": "CTCP Phân phối Khí thấp áp Dầu khí Việt Nam", "aliases": ["Khí thấp áp"],
     "attributes": {}, "sources": []},
    {"entity_id": "TICKER:MWG", "type": "TICKER", "code": "MWG",
     "canonical_name": "CTCP Đầu tư Thế Giới Di Động", "aliases": ["Thế Giới Di Động", "Bách Hóa Xanh"],
     "attributes": {}, "sources": []},
    {"entity_id": "TICKER:VIC", "type": "TICKER", "code": "VIC",
     "canonical_name": "Tập đoàn Vingroup", "aliases": ["Vingroup", "VinFast"],
     "attributes": {}, "sources": []},
    {"entity_id": "TICKER:VPB", "type": "TICKER", "code": "VPB",
     "canonical_name": "Ngân hàng TMCP Việt Nam Thịnh Vượng", "aliases": ["VPBank", "FE Credit"],
     "attributes": {}, "sources": []},
    {"entity_id": "TICKER:MSN", "type": "TICKER", "code": "MSN",
     "canonical_name": "CTCP Tập đoàn Masan", "aliases": ["Masan", "WinCommerce"],
     "attributes": {}, "sources": []},
    {"entity_id": "TICKER:BCM", "type": "TICKER", "code": "BCM",
     "canonical_name": "Tổng Công ty Đầu tư và Phát triển Công nghiệp", "aliases": ["Becamex", "Becamex Tokyu"],
     "attributes": {}, "sources": []},
]



@pytest.fixture
def reg():
    return EntityRegistry(ENTITIES)


# ---- select: ánh xạ file đăng ký (liệt kê theo nhóm) -> entity_id ----------
def test_select_tickers_and_index(reg):
    ids, unknown = reg.select({"tickers": ["HPG", "VCB"], "indices": ["VNINDEX"]})
    assert ids == {"TICKER:HPG", "TICKER:VCB", "INDEX:VNINDEX"} and unknown == []


def test_select_industry_by_code(reg):
    ids, unknown = reg.select({"industries": ["THEP"]})   # chuẩn: dùng code ngành
    assert ids == {"IND_GICS3:THEP"} and unknown == []


def test_select_industry_code_case_insensitive(reg):
    ids, unknown = reg.select({"industries": ["thep"]})   # code viết thường vẫn khớp
    assert ids == {"IND_GICS3:THEP"} and unknown == []


def test_select_industry_by_name_rejected(reg):
    # đồng bộ: industries CHỈ nhận code, tên ngành bị coi là unknown (không còn fallback theo tên)
    ids, unknown = reg.select({"industries": ["Thép"]})
    assert ids == set() and ("industries", "Thép") in unknown


def test_select_unknown_reported(reg):
    ids, unknown = reg.select({"tickers": ["ZZZ"], "industries": ["Không Có"]})
    assert ids == set()
    assert ("tickers", "ZZZ") in unknown and ("industries", "Không Có") in unknown


# ---- subscribers_for: người dùng nào chạm tới entity của tin ---------------
def test_subscribers_for():
    subs = {
        "AnPT": {"TICKER:HPG", "INDEX:VNINDEX"},
        "A": {"TICKER:VCB"},
    }
    reg = EntityRegistry(ENTITIES, subs)
    assert reg.subscribers_for(["TICKER:HPG"]) == {"AnPT"}
    assert reg.subscribers_for(["TICKER:VCB", "INDEX:VNINDEX"]) == {"A", "AnPT"}
    assert reg.subscribers_for(["IND_GICS3:THEP"]) == set()


def test_resolve_subscription_filters_invalid():
    reg = EntityRegistry(ENTITIES, {"X": {"TICKER:HPG", "TICKER:NOPE"}})
    assert reg.resolve_subscription("X") == {"TICKER:HPG"}


# ---- manifest: công tắc DEV bật/tắt từng người dùng ------------------------
def test_manifest_per_user_toggle():
    man = {"enabled": True, "default": False, "users": {"AnPT": True, "B": False}}
    assert _user_enabled(man, "AnPT") is True      # bật rõ ràng
    assert _user_enabled(man, "B") is False        # tắt rõ ràng
    assert _user_enabled(man, "C") is False        # chưa liệt kê -> theo default (False)


def test_manifest_global_off_overrides():
    man = {"enabled": False, "default": True, "users": {"AnPT": True}}
    assert _user_enabled(man, "AnPT") is False      # enabled=False tắt tất
    assert _user_enabled(man, "X") is False


# ---- nhận diện text --------------------------------------------------------
def test_match_by_code(reg):
    ids = [e["entity_id"] for e in reg.match("Cổ phiếu HPG tăng trần, VCB dẫn dắt")]
    assert "TICKER:HPG" in ids and "TICKER:VCB" in ids


def test_match_by_alias_diacritic_insensitive(reg):
    ids = [e["entity_id"] for e in reg.match("Tập đoàn Hoa Phat báo lãi")]  # thiếu dấu
    assert "TICKER:HPG" in ids


def test_macro_geo_my_false_positives_blocked(reg):
    """Chặn triệt để các danh từ riêng ghép tiếng Việt (địa danh, tên người, thương hiệu)."""
    fp_titles = [
        "CII chào bán 6.7 ngàn tỷ đồng trái phiếu để triển khai cao tốc Trung Lương - Mỹ Thuận",
        "Cảng Mỹ Thủy gần 15.000 tỷ đồng đang triển khai đến đâu?",
        "Tuyên Quang khánh thành tuyến đường hơn 480 tỷ đồng kết nối Khu du lịch suối khoáng Mỹ Lâm với cao tốc",
        "Bà Phạm Thị Mỹ Diệu thao túng cổ phiếu",
        "Vietcap: Á Mỹ Grupo sẵn sàng bước vào chu kỳ tăng trưởng mới",
        "Khu công nghiệp Mỹ Phước 3 thu hút vốn FDI",
        "Thị trường bất động sản Nam Mỹ và Bắc Mỹ",
    ]
    for t in fp_titles:
        dets = reg.detect(t)
        eids = [d["entity_id"] for d in dets]
        assert "MACRO_GEO:MY" not in eids, f"MACRO_GEO:MY bị nhận nhầm trong: {t}"


def test_macro_geo_my_true_positives_kept(reg):
    """Giữ nguyên các trường hợp thực sự nói về nước Mỹ / lãnh đạo / kinh tế Mỹ."""
    tp_titles = [
        "Tổng thống Mỹ Trump tuyên bố hoàn tất sứ mệnh ở Iran",
        "Các số liệu kinh tế Mỹ có thể tiếp tục chi phối giá vàng trong tuần này",
        "Chứng khoán Mỹ tăng 3 tuần liên tiếp, giá dầu tăng 5% cả tuần",
        "Số liệu lạm phát Mỹ làm dịu nỗi lo Fed tăng lãi suất",
        "Vì sao Mỹ bất ngờ ra tay cứu đồng Yên sau gần 30 năm?",
        "Mỹ và Nhật xác nhận phối hợp cứu đồng Yên, sẵn sàng hành động tiếp",
    ]
    for t in tp_titles:
        dets = reg.detect(t)
        eids = [d["entity_id"] for d in dets]
        assert "MACRO_GEO:MY" in eids, f"MACRO_GEO:MY bị bỏ sót trong: {t}"


def test_vnd_disclosure_positional_exemption(reg):
    """VND ở đầu tiêu đề CBTT được miễn trừ khỏi STOPLIST, trong khi VND giữa câu bị chặn."""
    # Tin CBTT chính thức ở đầu tiêu đề -> Khớp TICKER:VND
    cbtt_title = "VND: Báo cáo tình hình Quản trị công ty 6 tháng đầu năm 2026"
    cbtt_eids = [d["entity_id"] for d in reg.detect(cbtt_title)]
    assert "TICKER:VND" in cbtt_eids, "VND: ở đầu tiêu đề phải khớp TICKER:VND"

    # VND ở giữa câu đóng vai trò tiền tệ -> Bị chặn bởi CODE_STOPLIST
    currency_title = "Doanh nghiệp thu về gần 500 tỷ VND trong quý 2"
    currency_eids = [d["entity_id"] for d in reg.detect(currency_title)]
    assert "TICKER:VND" not in currency_eids, "VND giữa câu (tiền tệ) phải bị chặn"


def test_pgd_bank_false_positives_blocked(reg):
    """PGD trong thông báo của ngân hàng là 'Phòng giao dịch', không phải Khí thấp áp."""
    bank_pgd_titles = [
        "MBB: Quyết định của HĐQT về việc thành lập PGD Chợ Tân Bình",
        "TCB: Quyết định của HĐQT về việc thay đổi địa điểm và tên PGD Phan Văn Hớn",
        "STB: Nghị quyết HĐQT về việc chấp thuận chủ trương thay đổi địa chỉ Chi nhánh/PGD",
        "MBB: Thành lập Chi nhánh Tây Thủ Đức, PGD Long Bình",
    ]
    for t in bank_pgd_titles:
        dets = reg.detect(t)
        eids = [d["entity_id"] for d in dets]
        assert "TICKER:PGD" not in eids, f"TICKER:PGD bị nhận nhầm trong ngân hàng: {t}"


def test_macro_geo_nga_person_names_blocked(reg):
    """Chặn match MACRO_GEO:NGA khi là tên riêng lãnh đạo hoặc cá nhân mạng xã hội."""
    person_titles = [
        "SAB: Bổ nhiệm bà Trần Kim Nga, bà Nguyễn Thanh Hương làm Thành viên HĐQT",
        "Công an điều tra tài khoản “Nga Rose”, bắt Phạm Hoàng Hà SN 1994",
        "Bà Thúy Nga chia sẻ kinh nghiệm đầu tư",
    ]
    for t in person_titles:
        dets = reg.detect(t)
        eids = [d["entity_id"] for d in dets]
        assert "MACRO_GEO:NGA" not in eids, f"MACRO_GEO:NGA bị nhận nhầm tên người trong: {t}"

    # Khớp đúng khi là Nước Nga
    geo_titles = [
        "Kinh tế Nga vẫn tăng trưởng nhưng đối mặt nhiều sức ép",
        "Doanh nghiệp Nga hướng đến hợp tác sản xuất tại Việt Nam",
    ]
    for t in geo_titles:
        dets = reg.detect(t)
        eids = [d["entity_id"] for d in dets]
        assert "MACRO_GEO:NGA" in eids, f"MACRO_GEO:NGA bị bỏ sót trong: {t}"


def test_ecosystem_brand_aliases_match(reg):
    """Các thương hiệu con chủ lực của tập đoàn phải match đúng Ticker công ty mẹ."""
    cases = [
        ("“Cứ mở cửa hàng là lãi”, lợi nhuận Bách Hóa Xanh lập kỷ lục", "TICKER:MWG"),
        ("VinFast công bố doanh số kỷ lục trong tháng 7", "TICKER:VIC"),
        ("FE Credit kiếm hơn 10.000 tỷ đồng, lãi 152 tỷ", "TICKER:VPB"),
        ("WinCommerce khẳng định doanh thu vẫn tăng trên 10%", "TICKER:MSN"),
        ("Becamex Tokyu khởi công dự án mới tại Bình Dương", "TICKER:BCM"),
    ]
    for text, expected_eid in cases:
        dets = reg.detect(text)
        eids = [d["entity_id"] for d in dets]
        assert expected_eid in eids, f"Không khớp {expected_eid} cho: {text}"


