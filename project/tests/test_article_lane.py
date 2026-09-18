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
