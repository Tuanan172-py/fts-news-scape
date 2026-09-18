"""P2 — writer: gate đủ 2 layer, định tuyến subscriber, flatten null-safe.

Deliverable user là .xlsx đơn sắc (US-101, 2026-09-08); `_master/*.csv` giữ nguyên hợp đồng
máy đọc. Test đọc xlsx qua `_userkit.read_delivery` (trả về khoá field nội bộ).
"""
from __future__ import annotations

import csv

import _userkit as k

from src.export.user_output import MASTER_COLUMNS, UserOutputWriter
from src.export.xlsx_delivery import DELIVERY_FIELDS

DATE = "2026-08-18"

# Trường bị loại khỏi deliverable NGƯỜI đọc (vẫn còn đủ trong _master).
DROPPED = ("impact_area", "event_type", "agent_provider", "model_used", "materiality_score")


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_gate_and_routing(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}, "Bob": {"TICKER:VCB"}})
    # a1: đủ 2 layer, HPG → chỉ AnPT
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    # a2: chỉ L1, HPG → gate nới lỏng: AnPT vẫn nhận, các trường gold để trống ""
    k.seed_article(store, "a2"); k.seed_l1(store, "a2", ["TICKER:HPG"])
    # a3: đủ 2 layer nhưng VNM (không ai đăng ký) → loại
    k.seed_article(store, "a3"); k.seed_l1(store, "a3", ["TICKER:VNM"]); k.seed_agent(store, "a3")

    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    assert counts == {"AnPT": 2}

    out_file = tmp_path / "out" / "AnPT" / f"{DATE}.xlsx"
    assert out_file.exists()

    # Header = English labels, correct block order: navigation → intent provenance →
    # classification → source → long text → tech.
    # Ba cột Intent nằm ngay sau Matched Entities: người đọc tra thực thể ở đó, nên
    # nguồn nhận diện phải đứng cạnh để so được ngay mô hình thấy gì mà mã không thấy.
    assert k.delivery_labels(out_file) == [
        "Date", "Matched Entities", "Intent — LLM", "Intent — Code", "Intent Source",
        "Title", "Sentiment", "Time Sensitivity", "Gold Status", "Source",
        "Summary", "Key Points", "Market Implication", "URL", "Article ID",
    ]

    rows = k.read_delivery(out_file)
    assert len(rows) == 2
    row_map = {r["article_id"]: r for r in rows}

    # a1: full gold — enums mapped to English labels
    assert row_map["a1"]["date"] == DATE
    assert row_map["a1"]["matched_entities"] == "HPG"
    assert row_map["a1"]["summary"].startswith("Tóm tắt")
    assert row_map["a1"]["key_points"].startswith("- ")
    assert row_map["a1"]["sentiment"] == "Negative"
    assert row_map["a1"]["time_sensitivity"] == "This Week"
    assert row_map["a1"]["gold_status"] == "Full"

    # a2: L1 only, missing gold → gold fields empty
    assert row_map["a2"]["summary"] == ""
    assert row_map["a2"]["key_points"] == ""
    assert row_map["a2"]["implication"] == ""
    assert row_map["a2"]["time_sensitivity"] == ""
    assert row_map["a2"]["sentiment"] == ""
    assert row_map["a2"]["gold_status"] == "Preliminary"

    # Cột bị loại khỏi deliverable — không được xuất hiện dưới bất kỳ dạng nào
    for r in rows:
        for f in DROPPED:
            assert f not in r

    # Bob không có bài → không tạo thư mục
    assert not (tmp_path / "out" / "Bob").exists()
    # Thư mục user phẳng, không lồng subfolder ngày, không còn CSV
    assert not (tmp_path / "out" / "AnPT" / DATE).exists()
    assert not (tmp_path / "out" / "AnPT" / f"{DATE}.csv").exists()

    # _master giữ nguyên hợp đồng máy đọc: CSV, snake_case tiếng Anh, đủ cột
    master = tmp_path / "out" / "_master" / f"{DATE}.csv"
    assert master.exists()
    with open(master, encoding="utf-8-sig", newline="") as f:
        assert next(csv.reader(f)) == MASTER_COLUMNS
    assert (tmp_path / "out" / "_master" / f"{DATE}_L1.csv").exists()
    assert (tmp_path / "out" / "_master" / f"{DATE}_agent.csv").exists()
    master_agents = _read_csv(tmp_path / "out" / "_master" / f"{DATE}_agent.csv")
    assert {r["article_id"] for r in master_agents} == {"a1", "a3"}


def test_master_keeps_english_machine_contract(tmp_path):
    """_master KHÔNG đi theo deliverable: đổi cách giao hàng cho người không được làm gãy audit."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)

    row = _read_csv(tmp_path / "out" / "_master" / f"{DATE}.csv")[0]
    assert row["impact_area"] == "market"          # còn đủ trong audit
    assert row["event_type"] == "macro"
    assert row["agent_provider"] == "p" and row["model_used"] == "m"
    assert row["gold_status"] == "GOLD"            # enum thô, KHÔNG dịch
    assert row["sentiment"] == "negative"
    assert "noise_signals" in row


def test_enabled_filter(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}, "Bob": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    # chỉ bật AnPT → Bob bị loại dù cùng đăng ký HPG
    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out",
                              enabled={"AnPT"}).write(date=DATE)
    assert counts == {"AnPT": 1}
    assert not (tmp_path / "out" / "Bob").exists()


def test_flatten_null_safe(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"])
    k.seed_agent(store, "a1", with_optional=False)          # thiếu sentiment/event_type
    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert rows[0]["sentiment"] == ""
    assert rows[0]["summary"].startswith("Tóm tắt")         # field bắt buộc vẫn có


def test_date_filter_excludes_other_day(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1", published="2026-08-17T09:00:00+07:00")
    k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    counts = UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    assert counts == {}                                     # bài ngày 17 không vào ngày 18


def test_l1_only_export_fallback_empty_gold(tmp_path):
    """Bài chỉ có L1 (chưa có Gold) vẫn đạt gate export, mọi trường Gold đều rỗng."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "art_l1_only", title="Bài viết thử nghiệm")
    k.seed_l1(store, "art_l1_only", ["TICKER:HPG"])

    writer = UserOutputWriter(store, reg, output_root=tmp_path / "out")
    assert writer.write(date=DATE) == {"AnPT": 1}

    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert len(rows) == 1
    r = rows[0]
    assert r["article_id"] == "art_l1_only"
    assert r["title"] == "Bài viết thử nghiệm"
    assert r["matched_entities"] == "HPG"
    assert r["summary"] == "" and r["key_points"] == "" and r["implication"] == ""
    assert r["time_sensitivity"] == "" and r["sentiment"] == ""
    assert r["gold_status"] == "Preliminary"


def test_noise_filter_broad_entity_no_gold_dependency(tmp_path):
    """Bài chỉ match entity diện rộng: quyết định CHỈ dựa alias-in-title, không đọc trường Gold."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"ASSET_CLASS:VANG"}})

    # alias "vàng" CÓ trong title + không có Gold  -> vẫn lọt
    k.seed_article(store, "b_pass", title="Giá vàng lập đỉnh mới")
    k.seed_l1(store, "b_pass", ["ASSET_CLASS:VANG"], title="Giá vàng lập đỉnh mới",
              etype="ASSET_CLASS")
    # alias KHÔNG trong title, dù ĐÃ có Gold materiality 0.6 -> bị loại
    k.seed_article(store, "b_drop", title="Thị trường phiên chiều")
    k.seed_l1(store, "b_drop", ["ASSET_CLASS:VANG"], title="Thị trường phiên chiều",
              etype="ASSET_CLASS")
    k.seed_agent(store, "b_drop")

    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert {r["article_id"] for r in rows} == {"b_pass"}
    assert rows[0]["gold_status"] == "Preliminary"


def test_multiple_gold_rows_picks_latest(tmp_path):
    """Bài tái-capture có nhiều dòng agent_outputs dod_pass=1 -> chọn bản MỚI NHẤT, xác định."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "dup")
    k.seed_l1(store, "dup", ["TICKER:HPG"])
    k.seed_agent(store, "dup", raw_sha256="sha_old", summary="BAN CU")
    k.seed_agent(store, "dup", raw_sha256="sha_new", summary="BAN MOI")

    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert len(rows) == 1
    assert rows[0]["summary"] == "BAN MOI"
    assert rows[0]["gold_status"] == "Full"


def test_matched_entities_deduped(tmp_path):
    """Nhiều entity_id ánh xạ cùng 1 code → chỉ hiện MỘT lần (bug 22% dòng, sửa 2026-09-08)."""
    from src.agent.entities import EntityRegistry

    store = k.make_store(tmp_path)
    alt = {"entity_id": "TICKER:HPG_ALT", "type": "TICKER", "code": "HPG",
           "canonical_name": "Hòa Phát", "aliases": [], "attributes": {}, "sources": []}
    reg = EntityRegistry(k.ENTITIES + [alt], {"AnPT": {"TICKER:HPG", "TICKER:HPG_ALT"}})
    k.seed_article(store, "a1")
    k.seed_l1(store, "a1", ["TICKER:HPG", "TICKER:HPG_ALT"])
    k.seed_agent(store, "a1")

    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert rows[0]["matched_entities"] == "HPG"


def test_rows_sorted_urgent_then_materiality(tmp_path):
    """Thứ tự đọc tất định: mới nhất lên đầu, cùng giờ thì materiality cao trước."""
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    # aid, published_at, score
    for aid, pub, score in (("old", "2026-08-18T08:00:00+07:00", 0.9),
                            ("mid_low_score", "2026-08-18T10:00:00+07:00", 0.3),
                            ("mid_high_score", "2026-08-18T10:00:00+07:00", 0.8),
                            ("newest", "2026-08-18T15:30:00+07:00", 0.2)):
        k.seed_article(store, aid, published=pub)
        k.seed_l1(store, aid, ["TICKER:HPG"])
        k.seed_agent(store, aid, materiality=score)

    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert [r["article_id"] for r in rows] == ["newest", "mid_high_score", "mid_low_score", "old"]
    assert all("materiality_score" not in r for r in rows)


def test_formula_injection_is_neutralised(tmp_path):
    """Tiêu đề mở đầu bằng '=' / '-' KHÔNG được thành công thức Excel (OWASP CSV Injection)."""
    from openpyxl import load_workbook

    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1", title="=HYPERLINK(\"http://evil\",\"click\")")
    k.seed_l1(store, "a1", ["TICKER:HPG"], title="=HYPERLINK(\"http://evil\",\"click\")")
    k.seed_agent(store, "a1")

    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    wb = load_workbook(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    try:
        ws = wb.active
        # Tra cột theo nhãn thay vì theo chỉ số cứng: hợp đồng giao hàng còn được bổ
        # sung cột về sau, và một chỉ số cứng sẽ âm thầm kiểm nhầm ô khác.
        labels = [c.value for c in ws[1]]
        title_cell = ws.cell(row=2, column=labels.index("Title") + 1)
        # Ô phải là văn bản, KHÔNG phải công thức ('f'). openpyxl trả 's' cho chuỗi
        # trong bảng chia sẻ và 'inlineStr' cho chuỗi nội tuyến; cả hai đều là văn bản.
        assert title_cell.data_type in ("s", "inlineStr")
        assert title_cell.value.startswith("=HYPERLINK")
    finally:
        wb.close()


def test_workbook_is_monochrome_and_navigable(tmp_path):
    """Quy chuẩn trình bày: 1 dòng header đậm, freeze A2, AutoFilter, KHÔNG tô màu nền."""
    from openpyxl import load_workbook

    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)

    wb = load_workbook(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    try:
        ws = wb.active
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref.startswith("A1:")
        assert ws.cell(row=1, column=1).font.bold is True
        # đơn sắc: không ô nào có nền tô
        for row in ws.iter_rows():
            for c in row:
                assert c.fill.fill_type in (None, "none")
        # cột dài có wrap, cột ngắn thì không
        wrap_by_key = {key: wrap for key, _l, _w, wrap in DELIVERY_FIELDS}
        cols = [key for key, _l, _w, _wrap in DELIVERY_FIELDS]
        for idx, key in enumerate(cols, start=1):
            # openpyxl round-trip wrap_text=False thành None → so sánh theo bool
            assert bool(ws.cell(row=2, column=idx).alignment.wrap_text) is wrap_by_key[key]
            assert ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width > 0
    finally:
        wb.close()


def test_lean_v2_output_excel_delivery(tmp_path):
    """Bản ghi agent-output-v2-lean (chuỗi phẳng) xuất Excel đầy đủ các cột."""
    import json
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "lean1", title="Hòa Phát tăng sản lượng thép")
    k.seed_l1(store, "lean1", ["TICKER:HPG"])
    lean_json = json.dumps({
        "article_id": "lean1",
        "summary": "Tập đoàn Hòa Phát đạt kỷ lục sản lượng thép trong tháng 8.",
        "key_points": ["Sản lượng tăng 15% svck", "Xuất khẩu thép cuộn cán nóng tăng mạnh"],
        "implication": "Doanh thu Q3 dự kiến tăng trưởng mạnh, biên lợi nhuận mở rộng.",
        "sentiment": "positive",
        "time_sensitivity": "today",
        "citations": ["Tập đoàn Hòa Phát đạt kỷ lục sản lượng", "Sản lượng tăng 15% svck"],
    }, ensure_ascii=False)
    store.insert_agent_output({
        "article_id": "lean1", "raw_sha256": "sha_lean1", "work_item_id": 1,
        "output_json": lean_json, "agent_provider": "antigravity", "model_used": "flash",
        "confidence": 0.9, "dod_pass": 1, "dod_reasons": "[]",
        "created_at": "2026-08-18T10:00:00+07:00",
    })

    UserOutputWriter(store, reg, output_root=tmp_path / "out").write(date=DATE)
    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert len(rows) == 1
    r = rows[0]
    assert r["article_id"] == "lean1"
    assert r["summary"] == "Tập đoàn Hòa Phát đạt kỷ lục sản lượng thép trong tháng 8."
    assert "Sản lượng tăng 15% svck" in r["key_points"]
    assert r["implication"] == "Doanh thu Q3 dự kiến tăng trưởng mạnh, biên lợi nhuận mở rộng."
    assert r["sentiment"] == "Positive"
    assert r["time_sensitivity"] == "Today"
    assert r["gold_status"] == "Full"
