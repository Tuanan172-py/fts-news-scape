"""Kiểm định đường xử lý bài đăng hợp nhất: chắt lọc, tra cứu và bung bản ghi.

Ba bất biến được canh ở đây, mỗi cái đều từng bị vi phạm và trả giá bằng token thật:

1. **Đoạn chắt lọc phải nguyên văn.** Cơ chế trích dẫn theo chỉ số chỉ đúng khi mỗi
   đoạn là chuỗi con đúng của bài gốc.
2. **Không dòng nào vượt ngưỡng cắt dòng của công cụ đọc.** Packet cũ vi phạm điều
   này và làm agent mất tin vào dữ liệu, tự mở vòng kiểm chứng tốn hàng trăm nghìn token.
3. **Bản ghi hỏng một phần không được làm mất cả lô.** Một lô mang cả trăm bài.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.article_expand import (          # noqa: E402
    build_gold_output,
    build_l1_output,
    salvage_records,
)
from src.agent.distill import (               # noqa: E402
    MAX_PARAGRAPH_CHARS,
    distill,
    estimate_tokens,
    split_paragraphs,
)
from src.agent.entities import load_registry  # noqa: E402
from src.agent.intent_resolve import (        # noqa: E402
    IntentResolver,
    ResolveReport,
    reconcile,
)
from src.agent.l1_router import check_l1_dod  # noqa: E402

SAMPLE = "\n".join([
    "Tập đoàn Hòa Phát công bố lợi nhuận sau thuế quý 3 đạt 3.200 tỷ đồng, tăng 25% so với cùng kỳ năm trước.",
    "Sản lượng thép cuộn cán nóng HRC tăng 32%, biên lợi nhuận gộp mở rộng lên mức 14,1% trong kỳ báo cáo.",
    "Ông Trần Đình Long cho biết chính sách thuế chống bán phá giá tạo dư địa tăng giá bán tại thị trường nội địa.",
    "Công ty được thành lập năm 1992 và có trụ sở chính đặt tại thành phố Hà Nội theo giấy phép đăng ký.",
    "Xem thêm các bài viết liên quan tại chuyên mục doanh nghiệp của chúng tôi.",
])


@pytest.fixture(scope="module")
def registry():
    """Nạp danh mục thực thể dùng chung cho cả tệp kiểm định.

    Returns:
        Thể hiện `EntityRegistry` đã nạp.
    """
    return load_registry()


@pytest.fixture(scope="module")
def resolver(registry):
    """Dựng bộ tra cứu định danh dùng chung.

    Args:
        registry: Danh mục thực thể.

    Returns:
        Thể hiện `IntentResolver`.
    """
    return IntentResolver(registry)


# --------------------------------------------------------------------------
# Chắt lọc đoạn
# --------------------------------------------------------------------------
def test_moi_doan_chat_loc_la_chuoi_con_nguyen_van():
    """Mọi đoạn trả về phải xuất hiện nguyên văn trong bài gốc."""
    for para in distill(SAMPLE):
        assert para in SAMPLE


def test_luon_giu_doan_mo_dau():
    """Đoạn mở đầu luôn được giữ vì nó mang phần lớn nội dung sự kiện."""
    kept = distill(SAMPLE)
    assert kept[0].startswith("Tập đoàn Hòa Phát")


def test_giu_nguyen_thu_tu_goc():
    """Thứ tự các đoạn giữ lại phải khớp thứ tự xuất hiện trong bài."""
    kept = distill(SAMPLE)
    positions = [SAMPLE.index(p) for p in kept]
    assert positions == sorted(positions)


def test_loai_bo_doan_rac():
    """Đoạn mời đọc thêm là rác và phải bị loại."""
    assert not any("Xem thêm" in p for p in distill(SAMPLE))


def test_ton_trong_tran_token():
    """Tổng token của phần giữ lại không được vượt trần đã đặt."""
    kept = distill(SAMPLE, max_tokens=60)
    assert sum(estimate_tokens(p) for p in kept[1:]) <= 60


def test_bo_nguyen_doan_thay_vi_cat_ngang():
    """Khi trần rất chặt, thuật toán bỏ bớt đoạn chứ không cắt ngang đoạn nào."""
    kept = distill(SAMPLE, max_tokens=10)
    assert len(kept) < len(split_paragraphs(SAMPLE))
    for para in kept:
        assert para in SAMPLE


def test_loai_doan_dai_hon_tran_ky_tu():
    """Đoạn dài hơn trần ký tự bị loại để không dòng nào bị công cụ đọc cắt cụt."""
    huge = "A" * (MAX_PARAGRAPH_CHARS + 50)
    text = f"{huge}\nĐoạn thứ hai có số liệu doanh thu tăng 12% trong quý vừa qua."
    assert all(len(p) <= MAX_PARAGRAPH_CHARS for p in split_paragraphs(text))


def test_bai_rong_tra_ve_danh_sach_rong():
    """Bài không có nội dung thì không sinh đoạn nào."""
    assert distill("") == []


# --------------------------------------------------------------------------
# Tra cứu định danh
# --------------------------------------------------------------------------
def test_ten_doanh_nghiep_ra_dung_ma(resolver):
    """Tên thương hiệu phải tra ra đúng mã chứng khoán của doanh nghiệp."""
    r = resolver.resolve_one("Hòa Phát", "COM", title="Hòa Phát báo lãi")
    assert r.entity_id == "TICKER:HPG"
    assert r.in_list is True


def test_ma_ba_ky_tu_ra_dung_dinh_danh(resolver):
    """Mã ba ký tự in hoa tra ra định danh theo đường khớp chính xác."""
    r = resolver.resolve_one("HPG", "TIC", title="HPG tăng trần")
    assert r.entity_id == "TICKER:HPG"
    assert r.method == "exact_code"


def test_tu_viet_tat_thong_dung_khong_thanh_ma(resolver):
    """Từ viết tắt thông dụng giữa câu không được nhận thành mã chứng khoán."""
    r = resolver.resolve_one("VND", "TIC", title="Giá trị giao dịch đạt 500 tỷ VND")
    assert r.entity_id is None


def test_mien_tru_cho_tin_cong_bo_thong_tin(resolver):
    """Mã mở đầu tiêu đề kèm dấu hai chấm là công bố thông tin nên được công nhận."""
    r = resolver.resolve_one("VND", "TIC", title="VND: Báo cáo tình hình quản trị")
    assert r.entity_id == "TICKER:VND"


def test_nganh_dung_tien_to_dinh_danh_rieng(resolver):
    """Ngành có tiền tố định danh khác với tên loại, đây là chỗ từng gây tốn token."""
    r = resolver.resolve_one("Vận tải đường bộ & đường sắt", "IND", title="")
    assert r.entity_id.startswith("IND_GICS")
    assert r.type.startswith("INDUSTRY_GICS")


def test_nhom_ten_nguoi_chua_co_bang_tra(resolver):
    """Nhóm tên người chưa có nguồn tra nên luôn nằm ngoài danh mục, đúng thiết kế."""
    r = resolver.resolve_one("ông Trần Đình Long", "PER", title="")
    assert r.in_list is False
    assert r.entity_id is None


def test_thuc_the_ngoai_danh_muc_khong_bi_bia(resolver):
    """Thực thể không có trong danh mục phải để trống định danh thay vì đoán."""
    r = resolver.resolve_one("Sun Group", "COM", title="Sun Group khởi công")
    assert r.entity_id is None
    assert r.in_list is False


def test_khu_trung_lap_khi_tra_hang_loat(resolver):
    """Cùng một cặp chuỗi và nhóm lặp lại chỉ được tính một lần."""
    out = resolver.resolve_many([["Hòa Phát", "COM"], ["Hòa Phát", "COM"]], title="Hòa Phát")
    assert len(out) == 1


def test_thong_ke_tra_cuu_theo_nhom(resolver):
    """Bộ đếm phải tách tỷ lệ tra cứu theo từng nhóm thay vì gộp chung."""
    rep = ResolveReport()
    resolver.resolve_many([["Hòa Phát", "COM"], ["Sun Group", "COM"]],
                          title="Hòa Phát và Sun Group", report=rep)
    assert rep.total["COM"] == 2
    assert rep.rate("COM") == 0.5


def test_doi_chieu_hai_nguon_nhan_dien(resolver):
    """Nhãn đối chiếu phân biệt được phần chỉ mô hình thấy và phần chỉ mã thấy."""
    out = resolver.resolve_many([["Hòa Phát", "COM"]], title="Hòa Phát")
    labels = reconcile(out, {"TICKER:HPG", "TICKER:VIC"})
    assert labels["TICKER:HPG"] == "BOTH"
    assert labels["TICKER:VIC"] == "CODE_ONLY"


# --------------------------------------------------------------------------
# Cứu bản ghi hỏng
# --------------------------------------------------------------------------
def test_doc_duoc_mang_json_binh_thuong():
    """Đầu ra hợp lệ được đọc trọn vẹn."""
    records, broken = salvage_records('[{"i":0,"s":"a"},{"i":1,"s":"b"}]')
    assert len(records) == 2
    assert broken == 0


def test_boc_duoc_rao_ma_bao_quanh():
    """Đầu ra bọc trong rào mã vẫn đọc được."""
    records, _ = salvage_records('```json\n[{"i":0,"s":"a"}]\n```')
    assert len(records) == 1


def test_cuu_duoc_phan_lanh_khi_dau_ra_cut():
    """Đầu ra cụt giữa chừng vẫn giữ được các bản ghi hoàn chỉnh phía trước."""
    records, broken = salvage_records('[{"i":0,"s":"a"},{"i":1,"s":"b"},{"i":2,"s":')
    assert len(records) == 2
    assert broken >= 1


def test_bo_qua_loi_dan_truoc_mang():
    """Lời dẫn đứng trước mảng JSON không làm hỏng việc đọc."""
    records, _ = salvage_records('Đây là kết quả:\n[{"i":0,"s":"a"}]')
    assert len(records) == 1


def test_dau_ra_rong_khong_gay_loi():
    """Đầu ra rỗng trả về danh sách rỗng thay vì ném ngoại lệ."""
    assert salvage_records("") == ([], 0)


# --------------------------------------------------------------------------
# Bung bản ghi và cổng nghiệm thu
# --------------------------------------------------------------------------
def test_ban_ghi_nhan_dien_vuot_cong_nghiem_thu(resolver, registry):
    """Bản ghi bung ra phải vượt cổng nghiệm thu thật, không phải cổng mô phỏng."""
    title = "Hòa Phát báo lãi quý 3 tăng 25%"
    resolved = resolver.resolve_many([["Hòa Phát", "COM"]], title=title)
    out = build_l1_output("abc123", title, resolved, {"TICKER:HPG": "BOTH"})
    passed, reasons = check_l1_dod(out, title, registry=registry)
    assert passed, reasons


def test_chi_lay_thuc_the_xuat_hien_trong_tieu_de(resolver):
    """Lược đồ nhận diện chỉ nhận chuỗi nằm trong tiêu đề, phần còn lại phải bị loại."""
    title = "Hòa Phát báo lãi quý 3"
    resolved = resolver.resolve_many(
        [["Hòa Phát", "COM"], ["thuế chống bán phá giá", "THM"]], title=title)
    out = build_l1_output("abc123", title, resolved, {})
    surfaces = {e["surface"] for e in out["entities"]}
    assert surfaces == {"Hòa Phát"}


def test_khong_nhan_dien_duoc_thi_moi_nhom_deu_trong(resolver, registry):
    """Bài không nhận ra thực thể nào phải khai rỗng nhất quán để không trượt cổng."""
    title = "Một tiêu đề không chứa thực thể nào đáng kể"
    out = build_l1_output("abc123", title, [], {})
    assert out["recognized"] is False
    assert out["entities"] == []
    assert all(v == "none" for v in out["categories"].values())
    passed, reasons = check_l1_dod(out, title, registry=registry)
    assert passed, reasons


def test_trich_dan_lay_nguyen_van_theo_chi_so():
    """Trích dẫn được dựng từ chỉ số đoạn nên luôn nguyên văn, không cần ai kiểm lại."""
    paragraphs = distill(SAMPLE)
    record = {
        "i": 0,
        "s": "Hòa Phát báo lãi quý 3 tăng 25% nhờ sản lượng cải thiện.",
        "k": ["Biên lợi nhuận mở rộng nhờ giá bán nội địa"],
        "im": "Kết quả vượt kỳ vọng củng cố định giá cổ phiếu trong ngắn hạn tới quý sau.",
        "sn": "pos", "ts": "today", "c": [0, 1],
    }
    out, reason = build_gold_output("abc123", record, paragraphs)
    assert out is not None, reason
    for citation in out["citations"]:
        assert citation in SAMPLE
        assert len(citation) >= 20


def test_chi_so_trich_dan_ngoai_pham_vi_khong_gay_loi():
    """Chỉ số trích dẫn sai phạm vi được bỏ qua và bù bằng đoạn hợp lệ."""
    paragraphs = distill(SAMPLE)
    record = {
        "i": 0, "s": "Tóm tắt.", "k": ["Luận điểm"],
        "im": "Hàm ý thị trường đủ dài để vượt qua ngưỡng bốn mươi ký tự theo hợp đồng.",
        "sn": "neu", "ts": "arch", "c": [99, 100],
    }
    out, reason = build_gold_output("abc123", record, paragraphs)
    assert out is not None, reason
    assert len(out["citations"]) >= 2


def test_ham_y_qua_ngan_thi_bo_qua_bai():
    """Hàm ý ngắn hơn hợp đồng thì bỏ qua bài thay vì nạp dữ liệu kém chất lượng."""
    out, reason = build_gold_output("abc123", {
        "s": "Tóm tắt.", "k": ["Luận điểm"], "im": "Ngắn.",
        "sn": "neu", "ts": "arch", "c": [0]}, distill(SAMPLE))
    assert out is None
    assert "40" in reason


def test_luan_diem_trung_trich_dan_bi_loai():
    """Luận điểm chép nguyên văn trích dẫn bị loại, đúng cổng chống sao chép."""
    paragraphs = distill(SAMPLE)
    out, reason = build_gold_output("abc123", {
        "s": "Tóm tắt.", "k": [paragraphs[0]],
        "im": "Hàm ý thị trường đủ dài để vượt qua ngưỡng bốn mươi ký tự theo hợp đồng.",
        "sn": "neu", "ts": "arch", "c": [0, 1]}, paragraphs)
    assert out is None
    assert "trùng" in reason


def test_nhan_sac_thai_va_do_khan_duoc_bung_day_du():
    """Nhãn viết tắt của mô hình được bung về đúng giá trị của lược đồ."""
    out, _ = build_gold_output("abc123", {
        "s": "Tóm tắt.", "k": ["Luận điểm"],
        "im": "Hàm ý thị trường đủ dài để vượt qua ngưỡng bốn mươi ký tự theo hợp đồng.",
        "sn": "pos", "ts": "urg", "c": [0, 1]}, distill(SAMPLE))
    assert out["sentiment"] == "positive"
    assert out["time_sensitivity"] == "urgent"


def test_ban_ghi_gold_dung_bay_truong():
    """Bản ghi nội dung phải đúng bảy trường của lược đồ, không thừa không thiếu."""
    out, _ = build_gold_output("abc123", {
        "s": "Tóm tắt.", "k": ["Luận điểm"],
        "im": "Hàm ý thị trường đủ dài để vượt qua ngưỡng bốn mươi ký tự theo hợp đồng.",
        "sn": "neu", "ts": "week", "c": [0, 1]}, distill(SAMPLE))
    assert set(out) == {"article_id", "summary", "key_points", "implication",
                        "sentiment", "time_sensitivity", "citations"}


# --------------------------------------------------------------------------
# Đóng gói và chương trình điều phối
# --------------------------------------------------------------------------
def test_khong_dong_nao_vuot_tran_cat_dong():
    """Packet phải ghi sao cho không dòng nào bị công cụ đọc cắt cụt.

    Đây là bất biến đắt giá nhất của khâu đóng gói: packet cũ vi phạm nó và làm agent
    mất tin vào dữ liệu, tự mở vòng kiểm chứng tốn hàng trăm nghìn token.
    """
    import json as _json

    from scripts.article_pack import READ_MAX_LINE_CHARS

    items = [{"i": i, "t": f"Tiêu đề bài {i}", "p": distill(SAMPLE)} for i in range(50)]
    text = _json.dumps({"d": "2026-09-18", "n": len(items), "a": items},
                       ensure_ascii=False, indent=1)
    assert max(len(line) for line in text.splitlines()) < READ_MAX_LINE_CHARS


def test_cua_so_doc_khong_vuot_tran_byte():
    """Mỗi cửa sổ đọc phải nằm gọn trong một lần gọi của công cụ đọc."""
    from scripts.article_pack import READ_MAX_BYTES, READ_MAX_LINES, read_windows

    lines = ["x" * 900] * 500
    windows = read_windows(lines)
    assert windows[0][0] == 1
    assert sum(count for _, count in windows) == len(lines)
    for start, count in windows:
        chunk = lines[start - 1:start - 1 + count]
        assert count <= READ_MAX_LINES
        assert sum(len(c.encode()) + 12 for c in chunk) <= READ_MAX_BYTES


def test_boc_duoc_lop_vo_ket_qua_cong_cu():
    """Tệp đầu ra mang lớp vỏ kết quả công cụ vẫn phải bung ra đúng bản ghi.

    Không bóc lớp vỏ thì bộ bung đọc `{"type":"text","text":...}` thành đúng một bản
    ghi rác và cả lô coi như mất. Đây là sự cố thật của các tệp `_cNN` đợt W1, W2.
    """
    import json as _json

    from scripts.article_expand import salvage_records

    inner = _json.dumps([{"i": 0, "e": [], "s": "x"}, {"i": 1, "e": [], "s": "y"}],
                        ensure_ascii=False)
    envelope = _json.dumps({"kind": "foreground", "runId": "abc",
                            "output": [{"type": "text", "text": inner}]},
                           ensure_ascii=False)
    records, broken = salvage_records(envelope)
    assert broken == 0
    assert [r["i"] for r in records] == [0, 1]


def test_dau_ra_tran_khong_co_lop_vo_van_boc_duoc():
    """Bóc lớp vỏ không được làm hỏng đường đầu ra trần vốn đang chạy đúng."""
    import json as _json

    from scripts.article_expand import salvage_records

    plain = _json.dumps([{"i": 0, "e": [], "s": "x"}], ensure_ascii=False)
    records, broken = salvage_records(plain)
    assert broken == 0 and [r["i"] for r in records] == [0]


def test_batch_la_cong_chia_duy_nhat():
    """`--batch` là cổng chia lô duy nhất; không trần token nào can thiệp.

    Trần ngữ cảnh chưa bao giờ chạm, còn trần đầu ra thì chưa đo được nên không đủ
    tư cách làm luật chia lô. Một đợt trăm bài phải ra đúng MỘT lượt gọi.
    """
    from scripts.article_pack import plan_calls

    assert plan_calls(100, batch_cap=100) == [100]
    assert plan_calls(250, batch_cap=250) == [250]
    assert plan_calls(0, batch_cap=100) == []


def test_cac_luot_duoc_chia_deu():
    """Khi đợt lớn hơn trần người vận hành đặt thì các lượt phải đều nhau."""
    from scripts.article_pack import plan_calls

    sizes = plan_calls(250, batch_cap=100)
    assert sum(sizes) == 250
    assert max(sizes) - min(sizes) <= 1
    assert max(sizes) <= 100


def test_tran_chat_loc_mac_dinh_da_tat():
    """Mặc định mô hình phải đọc trọn bài, không bị code cắt bớt trước."""
    from src.agent.distill import (DEFAULT_MAX_TOKENS_PER_ARTICLE, distill,
                                   split_paragraphs)

    assert DEFAULT_MAX_TOKENS_PER_ARTICLE == 0
    text = chr(10).join(f"Đoạn số {i} với nội dung đủ dài để vượt ngưỡng tối thiểu "
                      f"của bộ lọc cơ học." for i in range(40))
    assert distill(text) == split_paragraphs(text)


def test_doan_qua_dai_bi_tach_chu_khong_bi_bo():
    """Đoạn vượt trần cắt dòng phải được tách, không được vứt đi.

    Vứt nguyên đoạn dài là mất đúng phần thường mang nhiều thông tin nhất; tách tại
    ranh giới câu giữ được cả nội dung lẫn bất biến nguyên văn.
    """
    from src.agent.distill import (MAX_PARAGRAPH_CHARS, split_long_paragraph,
                                   split_paragraphs)

    long_para = "Câu có độ dài vừa phải để ghép lại thành đoạn rất dài. " * 60
    pieces = split_long_paragraph(long_para)
    assert len(pieces) > 1
    assert all(len(x) <= MAX_PARAGRAPH_CHARS for x in pieces)
    assert all(x in long_para for x in pieces)

    kept = split_paragraphs(long_para)
    assert kept, "đoạn dài không được biến mất khỏi kết quả"
    assert all(len(x) <= MAX_PARAGRAPH_CHARS for x in kept)


def test_phat_hien_dung_nhung_bai_con_thieu(tmp_path, monkeypatch):
    """Lô trả về thiếu bài phải lộ ra đúng những chỉ số chưa có bản ghi."""
    import json as _json

    from scripts import article_run

    monkeypatch.setattr(article_run, "TASK_DIR", tmp_path)
    monkeypatch.setattr(article_run, "OUT_DIR", tmp_path)

    packet = {"d": "2026-09-21", "n": 5,
              "a": [{"i": i, "t": f"Bài {i}", "p": ["Nội dung."]} for i in range(5)]}
    mapping = {"batch_id": "article_W_01", "wave": "W",
               "index": {str(i): f"id{i}" for i in range(5)},
               "tier": {str(i): 1 for i in range(5)},
               "reason": {str(i): "x" for i in range(5)}}
    (tmp_path / "article_W_01.task.json").write_text(
        _json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "article_W_01.map.json").write_text(
        _json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    # Mô hình chỉ trả về ba bài đầu: hai bài cuối bị cắt cụt.
    (tmp_path / "article_W_01.output.json").write_text(
        _json.dumps([{"i": i, "e": [], "s": "x"} for i in range(3)],
                    ensure_ascii=False), encoding="utf-8")

    missing, _packet, _mapping = article_run.missing_indices("article_W_01")
    assert missing == ["3", "4"]


def test_dong_goi_bu_chi_lay_phan_thieu(tmp_path, monkeypatch, capsys):
    """Đường vá phải sinh packet chỉ chứa phần thiếu, đánh lại chỉ số từ 0."""
    import argparse
    import json as _json

    from scripts import article_run

    monkeypatch.setattr(article_run, "TASK_DIR", tmp_path)
    monkeypatch.setattr(article_run, "OUT_DIR", tmp_path)

    packet = {"d": "2026-09-21", "n": 5,
              "a": [{"i": i, "t": f"Bài {i}", "p": ["Nội dung đủ dài cho gói tin."]}
                    for i in range(5)]}
    mapping = {"batch_id": "article_W_01", "wave": "W",
               "index": {str(i): f"id{i}" for i in range(5)},
               "tier": {str(i): 1 for i in range(5)},
               "reason": {str(i): "x" for i in range(5)}}
    (tmp_path / "article_W_01.task.json").write_text(
        _json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "article_W_01.map.json").write_text(
        _json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "article_W_01.output.json").write_text(
        _json.dumps([{"i": i, "e": [], "s": "x"} for i in range(3)],
                    ensure_ascii=False), encoding="utf-8")

    rc = article_run.cmd_repair(argparse.Namespace(wave="W"))
    assert rc == 0

    rmap = _json.loads((tmp_path / "article_W_01_r01.map.json").read_text(
        encoding="utf-8"))
    assert rmap["index"] == {"0": "id3", "1": "id4"}
    rpacket = _json.loads((tmp_path / "article_W_01_r01.task.json").read_text(
        encoding="utf-8"))
    assert [a["t"] for a in rpacket["a"]] == ["Bài 3", "Bài 4"]
    assert (tmp_path / "wave_W.repair.ts").exists()


def test_khong_thieu_bai_thi_khong_sinh_goi_bu(tmp_path, monkeypatch):
    """Lô trả về đủ bài thì đường vá không được đẻ ra việc thừa."""
    import argparse
    import json as _json

    from scripts import article_run

    monkeypatch.setattr(article_run, "TASK_DIR", tmp_path)
    monkeypatch.setattr(article_run, "OUT_DIR", tmp_path)

    packet = {"d": "2026-09-21", "n": 2,
              "a": [{"i": i, "t": f"Bài {i}", "p": ["Nội dung."]} for i in range(2)]}
    mapping = {"batch_id": "article_W_01", "wave": "W",
               "index": {str(i): f"id{i}" for i in range(2)},
               "tier": {}, "reason": {}}
    (tmp_path / "article_W_01.task.json").write_text(
        _json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "article_W_01.map.json").write_text(
        _json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "article_W_01.output.json").write_text(
        _json.dumps([{"i": i, "e": [], "s": "x"} for i in range(2)],
                    ensure_ascii=False), encoding="utf-8")

    assert article_run.cmd_repair(argparse.Namespace(wave="W")) == 0
    assert not list(tmp_path.glob("*_r01.task.json"))


def test_chuong_trinh_dieu_phoi_la_javascript_hop_le():
    """Chương trình sinh ra cho phía điều phối phải phân tích cú pháp được."""
    import subprocess
    import tempfile

    from scripts.article_run import conductor_program

    manifest = {"wave": "T", "articles": 1, "batches": [
        {"batch_id": "b1", "path": "p.json", "n": 1, "windows": [[1, 10]]}]}
    src = "async function __main(){\n" + conductor_program(manifest, concurrency=3) + "\n}"
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as f:
        f.write(src)
        path = f.name
    try:
        res = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    except FileNotFoundError:
        pytest.skip("không có Node trên máy này")
    finally:
        Path(path).unlink(missing_ok=True)
    assert res.returncode == 0, res.stderr


def test_chuong_trinh_dieu_phoi_khong_tra_noi_dung_ve_ngu_canh():
    """Chương trình chỉ được trả về con số; trả nội dung lô là làm phình ngữ cảnh cha."""
    from scripts.article_run import conductor_program

    manifest = {"wave": "T", "articles": 1, "batches": [
        {"batch_id": "b1", "path": "p.json", "n": 1, "windows": [[1, 10]]}]}
    program = conductor_program(manifest, concurrency=3)
    tail = program[program.rindex("return {"):]
    assert "packet" not in tail
    assert "text" not in tail


# --------------------------------------------------------------------------
# Bộ nhớ đệm phía nhà cung cấp
#
# Bốn bất biến dưới đây canh cùng một thứ: phần tiền tố tĩnh phải giống hệt nhau
# giữa các lượt gọi thì mới trúng bộ nhớ đệm. Hỏng ở đây không làm sai kết quả, chỉ
# làm hoá đơn đắt lên năm mươi lần ở phần lẽ ra rẻ nhất — tức không có triệu chứng
# nào ngoài tiền, và vì vậy phải kiểm bằng máy.
# --------------------------------------------------------------------------
def test_persona_trong_preset_giong_het_prefix_tren_dia():
    """Persona dán tay trong preset phải khớp từng byte với tệp prefix đã sinh."""
    from src.agent.prefix import PREFIX_PATH, compare_persona

    if not PREFIX_PATH.exists():
        pytest.skip("chưa sinh prefix trên máy này")
    ok, detail = compare_persona(PREFIX_PATH.read_text(encoding="utf-8"))
    assert ok, detail


def test_persona_lech_mot_dong_bi_bat():
    """Thêm đúng một dòng vào prefix là chế độ kiểm phải báo lệch."""
    from src.agent.prefix import PREFIX_PATH, compare_persona

    if not PREFIX_PATH.exists():
        pytest.skip("chưa sinh prefix trên máy này")
    doctored = PREFIX_PATH.read_text(encoding="utf-8") + "\nmột dòng thừa\n"
    ok, detail = compare_persona(doctored)
    assert not ok
    assert "dòng" in detail


def test_tien_to_tinh_gom_ca_phan_harness_noi_them():
    """Dự toán phải đếm cả AGENTS.md và section tool, không chỉ phần persona."""
    from src.agent.prefix import (
        SYSTEM_OVERHEAD_TOKENS,
        cached_prefix_tokens,
        persona_tokens,
    )

    assert cached_prefix_tokens() == persona_tokens() + SYSTEM_OVERHEAD_TOKENS
    assert cached_prefix_tokens() > persona_tokens()


def test_dong_goi_lai_cung_mot_tap_bai_cho_ra_packet_giong_het(tmp_path):
    """Packet phải tất định: lần chạy lại chỉ trúng cache khi giống hệt lần trước."""
    from scripts.article_pack import write_packet

    items = [{"i": 0, "t": "Hòa Phát báo lãi", "p": ["Đoạn một.", "Đoạn hai."]},
             {"i": 1, "t": "VND: báo cáo quản trị", "p": ["Đoạn ba."]}]
    mapping = {"batch_id": "b", "index": {"0": "x", "1": "y"}}
    _p1, _m1, first = write_packet("b", items, mapping, tmp_path / "a")
    _p2, _m2, second = write_packet("b", items, mapping, tmp_path / "b")
    assert first["sha256"] == second["sha256"]


def test_chuong_trinh_dieu_phoi_ham_cache_truoc_roi_tha_moi_lo():
    """Lượt hâm cache phải đi trước, và không lô nào bị bắt chạy một mình nữa."""
    from scripts.article_run import conductor_program

    manifest = {"wave": "T", "articles": 2, "batches": [
        {"batch_id": "b1", "path": "p1.json", "n": 1, "windows": [[1, 10]]},
        {"batch_id": "b2", "path": "p2.json", "n": 1, "windows": [[1, 10]]}]}
    program = conductor_program(manifest, concurrency=2)

    assert "const WARM" in program
    warm_call = program.index("prompt: WARM")
    loop = program.index("for (let i = 0; i < BATCHES.length")
    assert warm_call < loop, "phải hâm bộ nhớ đệm trước khi thả lô"
    assert "runBatch(BATCHES[0])" not in program, "lô đầu không còn phải chạy một mình"


def test_phat_hien_bo_nho_dem_truot_bang_san_toi_thieu():
    """Hụt so với sàn `tiền tố × (số lượt gọi − 1)` là tín hiệu cache trượt."""
    from scripts.token_ledger import cache_shortfall

    # Đợt hai lô có ba lượt gọi worker: một lượt hâm và hai lô.
    assert cache_shortfall(100_000, 4, 11_143, calls=3) == (22_286, 0)
    assert cache_shortfall(10_000, 4, 11_143, calls=3) == (22_286, 12_286)
    assert cache_shortfall(0, 1, 11_143, calls=1) == (0, 0), "một lượt thì không có sàn"


def test_san_cache_khong_tinh_phien_dieu_phoi_thanh_worker():
    """Phiên Conductor mang persona khác nên không được tính vào sàn của worker.

    Trước đây sàn lấy thẳng số phiên: đợt hai lô có bốn phiên nên sàn đòi
    `11.143 × 3`, trong khi chỉ có hai lô thật sự đọc lại tiền tố. Cảnh báo vì thế
    kêu oan ở mọi đợt bình thường — mà một cảnh báo luôn kêu thì không còn là tín hiệu.
    """
    from scripts.token_ledger import cache_shortfall

    hit_hoan_hao = 2 * 11_143          # hai lô, mỗi lô đọc lại trọn tiền tố
    _floor, thieu = cache_shortfall(hit_hoan_hao, 4, 11_143, calls=3)
    assert thieu == 0, "cache trúng hoàn hảo mà vẫn báo hụt"

    # Vẫn phải bắt được trường hợp hỏng thật: chỉ một lô trúng.
    _floor, thieu = cache_shortfall(11_143, 4, 11_143, calls=3)
    assert thieu == 11_143


def test_doc_so_luot_goi_worker_tu_mo_ta_dot(tmp_path, monkeypatch):
    """Số lượt gọi lấy từ mô tả đợt: số lô cộng lượt hâm nếu có."""
    import json as _json

    from scripts import token_ledger

    monkeypatch.setattr(token_ledger, "TASK_DIR", str(tmp_path))
    (tmp_path / "wave_A.json").write_text(
        _json.dumps({"batches": [{}, {}], "warmed": True}), encoding="utf-8")
    (tmp_path / "wave_B.json").write_text(
        _json.dumps({"batches": [{}], "warmed": False}), encoding="utf-8")

    assert token_ledger.worker_calls("A") == 3
    assert token_ledger.worker_calls("B") == 1
    assert token_ledger.worker_calls("KHONG_CO") is None
    assert token_ledger.worker_calls(None) is None


def test_ngay_cua_so_cai_la_gio_UTC_phai_doi_ve_gio_may():
    """Sổ cái ghi theo UTC; lọc theo ngày máy phải đổi thành khoảng UTC.

    Không đổi thì mọi đợt chạy trước 07:00 giờ VN rơi vào ngày hôm trước theo UTC,
    và radar báo "chưa có dòng nào" cho đúng ngày vừa chạy xong.
    """
    from datetime import datetime, timedelta

    from scripts.pipeline_radar import _utc_window

    lo, hi = _utc_window("2026-09-18")
    lo_dt, hi_dt = datetime.fromisoformat(lo), datetime.fromisoformat(hi)
    assert hi_dt - lo_dt == timedelta(days=1)
    assert lo_dt.astimezone().strftime("%Y-%m-%d %H:%M") == "2026-09-18 00:00"
    assert lo.endswith("+00:00") and hi.endswith("+00:00"), "phải cùng định dạng cột ts"


def test_radar_khong_cong_don_cac_anh_chup_tich_luy_cua_cung_mot_dot(tmp_path,
                                                                    monkeypatch):
    """Sổ cái ghi ảnh chụp tích luỹ; cộng thẳng chúng là đếm trùng nhiều lần."""
    import sqlite3 as _sq

    from scripts import pipeline_radar
    from scripts.token_ledger import SCHEMA

    db = tmp_path / "harness.db"
    conn = _sq.connect(db)
    conn.executescript(SCHEMA)
    for miss in (100, 200, 300):
        conn.execute(
            "INSERT INTO token_ledger (ts, wave, agent_id, n_items, n_sessions,"
            " miss_tokens, hit_tokens, out_tokens, quota_tokens, billed_usd)"
            " VALUES ('2026-09-18T11:21', 'W', 'article-processor', 200, 25,"
            f" {miss}, 0, 0, {miss}, 0.1)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(pipeline_radar, "HARNESS_DB", db)
    rows = pipeline_radar._ledger_rows("2026-09-18", "W")
    assert len(rows) == 1
    assert rows[0]["miss_tokens"] == 300, "phải giữ ảnh chụp mới nhất"


def test_dot_mot_lo_khong_ham_bo_nho_dem():
    """Một lô thì không có ai dùng lại tiền tố, nên lượt hâm chỉ là tốn thêm."""
    from scripts.article_run import conductor_program

    manifest = {"wave": "T", "articles": 1, "batches": [
        {"batch_id": "b1", "path": "p1.json", "n": 1, "windows": [[1, 10]]}]}
    assert "WARM" not in conductor_program(manifest, concurrency=1)


def test_khu_anh_chup_cu_cua_cung_mot_dot():
    """Sổ cái ghi ảnh chụp tích luỹ; phần cộng phải giữ đúng ảnh chụp cuối cùng."""
    from scripts.token_ledger import latest_snapshots

    rows = [{"wave": "W1", "batch_id": None, "agent_id": "a", "n_items": 100},
            {"wave": "W2", "batch_id": None, "agent_id": "a", "n_items": 200},
            {"wave": "W2", "batch_id": None, "agent_id": "a", "n_items": 200}]
    kept = latest_snapshots(rows)
    assert [r["wave"] for r in kept] == ["W1", "W2"]
    assert kept[-1] is rows[-1], "phải giữ ảnh chụp ghi sau cùng"


def test_chua_lo_nao_chay_thi_khong_bao_la_khong_can_va(tmp_path, monkeypatch):
    """Đợt chưa chạy lần nào phải nói thẳng, không được chúc mừng "không cần vá"."""
    import argparse
    import json as _json

    from scripts import article_run

    monkeypatch.setattr(article_run, "TASK_DIR", tmp_path)
    monkeypatch.setattr(article_run, "OUT_DIR", tmp_path)

    packet = {"d": "2026-09-21", "n": 1,
              "a": [{"i": 0, "t": "Bài 0", "p": ["Nội dung."]}]}
    (tmp_path / "article_W_01.task.json").write_text(
        _json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "article_W_01.map.json").write_text(
        _json.dumps({"batch_id": "article_W_01", "index": {"0": "id0"}},
                    ensure_ascii=False), encoding="utf-8")

    assert article_run.cmd_repair(argparse.Namespace(wave="W")) == 2
    assert not list(tmp_path.glob("*_r01.task.json"))
