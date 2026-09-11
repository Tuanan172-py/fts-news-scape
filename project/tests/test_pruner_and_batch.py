"""
Tests for Pruner, Lean Task Packet, Batch Handoff, and Batch Ingestion.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.agent.batch_handoff import (
    build_batch_packet, split_tasks_into_batches, unpack_batch_output, write_batch_packet,
)
from src.agent.dod import check_dod
from src.agent.packet import build_gold_input, build_task_packet
from src.agent.pruner import clean_article_paragraphs, is_boilerplate_paragraph
from src.agent.runner import AgentRunner
from src.db.store import ArticleStore

SAMPLE_DIRTY_TEXT = """
Theo Dân trí

Thị trường chứng khoán ngày 05/09 ghi nhận áp lực bán gia tăng trên diện rộng khi chỉ số VN-Index điều chỉnh nhẹ.
Các nhóm ngành vốn hóa lớn như ngân hàng và bất động sản có sự phân hóa rõ rệt trong phiên chiều.

Bài liên quan: Xem thêm diễn biến phiên giao dịch hôm qua tại đây.

Tổng công ty Cổ phần Vinaconex vừa công bố kế hoạch đầu tư dự án mới tại khu vực miền Trung với tổng mức đầu tư hàng nghìn tỷ đồng.
Dự kiến dự án sẽ đem lại dòng tiền ổn định cho doanh nghiệp trong giai đoạn 2026-2030.

Ban biên tập Tạp chí Điện tử Doanh nhân
Hotline: 0912345678 - Email: toasoan@example.com
© Copyright 2026 - Giấy phép thiết lập mạng thông tin điện tử số 123/GP-BTTTT
"""


def test_boilerplate_detection():
    assert is_boilerplate_paragraph("Bài liên quan: Xem thêm tin tức") is True
    assert is_boilerplate_paragraph("Xem thêm các dự án mới") is True
    assert is_boilerplate_paragraph("Hotline: 0901234567") is True
    assert is_boilerplate_paragraph("Email: contact@news.vn") is True
    assert is_boilerplate_paragraph("© Copyright 2026 Công ty ABC") is True
    assert is_boilerplate_paragraph("Ban biên tập Tòa soạn") is True
    assert is_boilerplate_paragraph("Theo HOSE") is True
    assert is_boilerplate_paragraph("---") is True
    # Doan noi dung that phai duoc giu lai
    assert is_boilerplate_paragraph(
        "VN-Index tăng 12 điểm trong phiên sáng nhờ sức kéo của nhóm ngân hàng."
    ) is False


def test_clean_article_paragraphs_and_verbatim_citations():
    cleaned = clean_article_paragraphs(SAMPLE_DIRTY_TEXT)

    # Boilerplate bi loai sach
    assert "Bài liên quan" not in cleaned
    assert "Hotline" not in cleaned
    assert "toasoan@example.com" not in cleaned
    assert "Ban biên tập" not in cleaned
    assert "Giấy phép" not in cleaned

    # Noi dung cot loi duoc giu
    assert "Thị trường chứng khoán ngày 05/09" in cleaned
    assert "Tổng công ty Cổ phần Vinaconex" in cleaned

    # BAT BIEN: doan giu lai phai NGUYEN VAN => source_span luon la exact substring
    span = ("Thị trường chứng khoán ngày 05/09 ghi nhận áp lực bán gia tăng trên diện rộng "
            "khi chỉ số VN-Index điều chỉnh nhẹ.")
    assert span in cleaned
    assert span in SAMPLE_DIRTY_TEXT


def test_lean_task_packet_size(tmp_path):
    # Work-package "ban" voi hang nghin link menu + anh — dung rac DOM co tinh
    wp = {
        "article_id": "test_art_001",
        "source_url": "https://cafef.vn/art1.chn",
        "domain": "cafef.vn",
        "published_at": "2026-09-07T08:00:00+07:00",
        "raw_html_path": str(tmp_path / "raw.html"),
        "raw_sha256": hashlib.sha256(b"x").hexdigest(),
        "title": "VN-Index giằng co quanh vùng 1.280 điểm",
        "cleaned_text": SAMPLE_DIRTY_TEXT,
        "structure": {
            "headings": [{"level": 1, "text": "VN-Index giằng co"}],
            "links": [{"url": f"https://example.com/item/{i}", "text": f"Menu link {i}"}
                      for i in range(2000)],
            "tables": [{"rows": [["a", "b"]]}],
            "images": [{"url": f"https://example.com/img/{i}.jpg", "caption": f"Img {i}"}
                       for i in range(2000)],
        },
    }

    packet = build_task_packet(wp, l1_entities=["VCB", "VIC"])
    inp = packet["input"]

    # Zero-Waste: KHONG duoc mang links / images sang agent
    assert "links" not in inp.get("structure", {})
    assert "images" not in inp.get("structure", {})
    assert inp["l1_entities"] == ["VCB", "VIC"]
    assert "Ban biên tập" not in inp["cleaned_text"]

    # Packet phai gon — muc tieu duoi 10 KB, o day sample nho nen < 3 KB
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2)
    assert len(packet_json.encode("utf-8")) < 3000


def test_batch_handoff_and_unpack(tmp_path):
    tasks = [
        {
            "article_id": f"art_{i}",
            "input": {
                "article_id": f"art_{i}",
                "title": f"Tiêu đề bài {i}",
                "domain": "cafef.vn",
                "published_at": "2026-09-07T09:00:00+07:00",
                "cleaned_text": f"Nội dung bài viết {i} với độ dài đủ lớn để test.",
                "l1_entities": ["CP"],
            },
        }
        for i in range(25)
    ]

    batch_paths = split_tasks_into_batches(tasks, batch_size=10, base_dir=str(tmp_path))
    assert len(batch_paths) == 3                       # 10 + 10 + 5

    first = json.loads(Path(batch_paths[0]).read_text(encoding="utf-8"))
    assert first["batch_id"] == "batch_01"
    assert first["task_count"] == 10
    assert len(first["tasks"]) == 10

    # Agent tra ve 1 mang JSON cho ca lo
    batch_output = [
        {
            "output_schema_version": "1.0",
            "article_id": f"art_{i}",
            "summary": {"abstractive": "Tóm tắt", "key_points": ["a"]},
        }
        for i in range(3)
    ]
    batch_out_path = tmp_path / "batch_01.output.json"
    batch_out_path.write_text(json.dumps(batch_output, ensure_ascii=False), encoding="utf-8")

    unpacked = unpack_batch_output(batch_out_path)
    assert len(unpacked) == 3
    assert unpacked[0]["article_id"] == "art_0"


def test_dod_pass_with_pruned_packet(tmp_path):
    raw_path = tmp_path / "art_pruned.html"
    raw_path.write_bytes(b"<html>dummy</html>")
    sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()

    wp = {
        "article_id": "art_pruned",
        "source_url": "https://cafef.vn/art1.chn",
        "domain": "cafef.vn",
        "raw_html_path": str(raw_path),
        "raw_sha256": sha,
        "cleaned_text": SAMPLE_DIRTY_TEXT,
        "change_state": "OK",
    }
    packet = build_task_packet(wp)
    gold_cleaned = packet["input"]["cleaned_text"]

    # 2 citation lay NGUYEN VAN tu ban da prune
    s1 = ("Thị trường chứng khoán ngày 05/09 ghi nhận áp lực bán gia tăng trên diện rộng "
          "khi chỉ số VN-Index điều chỉnh nhẹ.")
    assert s1 in gold_cleaned
    s2 = ("Tổng công ty Cổ phần Vinaconex vừa công bố kế hoạch đầu tư dự án mới tại khu vực "
          "miền Trung với tổng mức đầu tư hàng nghìn tỷ đồng.")
    assert s2 in gold_cleaned

    output = {
        "output_schema_version": "1.0",
        "article_id": "art_pruned",
        "summary": {"abstractive": "Tóm tắt", "key_points": ["a"]},
        "implication": {"text": "Chi phí đầu vào hạ nhiệt có thể nới biên lợi nhuận quý tới của nhóm doanh nghiệp liên quan, hỗ trợ định giá cổ phiếu.", "impact_area": "market"},
        "materiality": {"score": 0.65, "time_sensitivity": "today"},
        "confidence": 0.85,
        "sentiment": {"overall": 0.2, "polarity": "positive"},
        "event_type": "earnings",
        "extraction_quality": "high",
        "citations": [
            {"claim": "thị trường điều chỉnh", "source_span": s1, "source_offset": 0},
            {"claim": "Vinaconex công bố đầu tư", "source_span": s2, "source_offset": 0},
        ],
        "processing_metadata": {
            "agent_provider": "antigravity",
            "model_used": "flash",
            "timestamp": "2026-09-07T15:00:00+07:00",
        },
    }

    # Citation phai khop CA work-package goc LAN input da prune
    ok, reasons = check_dod(output, wp)
    assert ok, f"DoD failed against wp: {reasons}"
    ok2, reasons2 = check_dod(output, packet["input"])
    assert ok2, f"DoD failed against packet input: {reasons2}"


def test_batch_ingest_end_to_end(tmp_path):
    from src.handoff.catalog import Catalog

    db_path = str(tmp_path / "t.db")
    store = ArticleStore(db_path=db_path)

    raw = b"<html>dummy</html>"
    raw_path = tmp_path / "art_b.html"
    raw_path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()

    text = ("Thị trường chứng khoán ngày 05/09 ghi nhận áp lực bán gia tăng trên diện rộng "
            "khi chỉ số VN-Index điều chỉnh nhẹ. Nhóm bất động sản phân hóa.")
    wp1 = {
        "article_id": "art_b1",
        "source_url": "https://cafef.vn/1.chn",
        "domain": "cafef.vn",
        "raw_html_path": str(raw_path),
        "raw_sha256": sha,
        "cleaned_text": text,
        "change_state": "OK",
    }
    wp1_path = tmp_path / "art_b1.pkg.json"
    wp1_path.write_text(json.dumps(wp1, ensure_ascii=False), encoding="utf-8")

    Catalog(store).enqueue("art_b1", sha, "cafef.vn", str(wp1_path), "NEW")

    tasks_dir = tmp_path / "agent_tasks"
    runner = AgentRunner(store, task_dir=str(tasks_dir))
    runner.export_tasks(limit=10, require_l1=False)

    s1 = ("Thị trường chứng khoán ngày 05/09 ghi nhận áp lực bán gia tăng trên diện rộng "
          "khi chỉ số VN-Index điều chỉnh nhẹ.")
    s2 = "Nhóm bất động sản phân hóa."
    batch_output = [{
        "output_schema_version": "1.0",
        "article_id": "art_b1",
        "summary": {"abstractive": "Tóm tắt", "key_points": ["a"]},
        "implication": {"text": "Chi phí đầu vào hạ nhiệt có thể nới biên lợi nhuận quý tới của nhóm doanh nghiệp liên quan, hỗ trợ định giá cổ phiếu.", "impact_area": "market"},
        "materiality": {"score": 0.6, "time_sensitivity": "today"},
        "confidence": 0.8,
        "sentiment": {"overall": 0.1, "polarity": "neutral"},
        "event_type": "other",
        "extraction_quality": "high",
        "citations": [
            {"claim": "c1", "source_span": s1, "source_offset": 0},
            {"claim": "c2", "source_span": s2, "source_offset": 0},
        ],
        "processing_metadata": {
            "agent_provider": "antigravity",
            "model_used": "flash",
            "timestamp": "2026-09-07T15:00:00+07:00",
        },
    }]
    batch_out_path = tmp_path / "batch_01.output.json"
    batch_out_path.write_text(json.dumps(batch_output, ensure_ascii=False), encoding="utf-8")

    unpacked = unpack_batch_output(batch_out_path)
    assert len(unpacked) == 1

    res = runner.ingest_output(unpacked[0])
    assert res["dod_pass"] is True
    assert store.get_agent_output("art_b1", sha)["dod_pass"] == 1


def test_clean_article_paragraphs_max_chars_and_entities():
    # Giả lập bài báo dài với nhiều đoạn văn
    paras = [
        "Đoạn 1: Mở đầu bài viết về thị trường tài chính với các diễn biến chung.",
        "Đoạn 2: VN-Index dao động giằng co với thanh khoản duy trì ở mức cao trên 15.000 tỷ đồng.",
    ]
    # Thêm 20 đoạn văn dài
    for i in range(3, 20):
        paras.append(f"Đoạn {i}: Diễn biến bình luận thị trường tổng quát không mang nhiều thông tin số liệu cụ thể nhưng khá dài dòng {'.' * 150}")
    # Đoạn mang mã CP quan trọng
    paras.append("Đoạn cuối: Tập đoàn HPG thông báo doanh thu tăng trưởng 25% đạt mức kỷ lục mới.")

    full_text = "\n\n".join(paras)
    assert len(full_text) > 3500

    # Clean không có entities
    c1 = clean_article_paragraphs(full_text, max_chars=2200)
    assert len(c1) <= 2300
    assert "Đoạn 1" in c1
    assert "Đoạn 2" in c1

    # Clean có l1_entities ưu tiên HPG
    c2 = clean_article_paragraphs(full_text, max_chars=2200, l1_entities=["TICKER:HPG"])
    assert len(c2) <= 2700
    assert "Tập đoàn HPG" in c2


def test_export_tasks_user_and_date_filters(tmp_path):
    """Kiểm tra AgentRunner.export_tasks lọc đúng theo user, date, days và dry_run."""
    from src.agent.runner import AgentRunner
    from src.db.store import ArticleStore

    db_path = str(tmp_path / "test_export.db")
    store = ArticleStore(db_path=db_path)
    conn = store.connect()
    # Tạo dữ liệu test
    conn.execute("""
        INSERT INTO articles (url, url_title_hash, title, published_at, fetched_at, source_domain)
        VALUES 
            ('url1', 'h1', 'HPG tăng mạnh', '2026-09-07T08:00:00+07:00', '2026-09-07T08:30:00+07:00', 'cafef.vn'),
            ('url2', 'h2', 'VHM mở bán đại đô thị', '2026-08-20T08:00:00+07:00', '2026-08-20T08:30:00+07:00', 'cafef.vn')
    """)
    conn.execute("""
        INSERT INTO work_items (article_id, raw_sha256, domain, package_path, status, enqueued_at)
        VALUES 
            ('h1', 's1', 'cafef.vn', 'wp1.json', 'pending', '2026-09-07T09:00:00+07:00'),
            ('h2', 's2', 'cafef.vn', 'wp2.json', 'pending', '2026-08-20T09:00:00+07:00')
    """)
    conn.execute("""
        INSERT INTO l1_outputs (article_id, output_json, dod_pass, l1_source)
        VALUES 
            ('h1', '{"entities":[{"entity_id":"TICKER:HPG"}]}', 1, 'code_first'),
            ('h2', '{"entities":[{"entity_id":"TICKER:VHM"}]}', 1, 'code_first')
    """)
    conn.commit()
    conn.close()


    runner = AgentRunner(store, task_dir=str(tmp_path / "tasks"))

    # 1. Test lọc ngày cụ thể
    exp_date = runner.export_tasks(limit=10, date="2026-09-07", require_l1=True, subscriber_only=False, dry_run=True)
    assert len(exp_date) == 1
    assert exp_date[0]["article_id"] == "h1"

    # 2. Test lọc ngày quá cũ bị loại bởi date
    exp_old = runner.export_tasks(limit=10, date="2026-08-20", require_l1=True, subscriber_only=False, dry_run=True)
    assert len(exp_old) == 1
    assert exp_old[0]["article_id"] == "h2"


