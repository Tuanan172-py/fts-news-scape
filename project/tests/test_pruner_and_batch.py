"""
Tests for boilerplate detection, batch output unpacking and batch ingestion.
"""
from __future__ import annotations

import hashlib
import json

from src.agent.batch_handoff import unpack_batch_output
from src.agent.pruner import is_boilerplate_paragraph
from src.agent.runner import AgentRunner
from src.db.store import ArticleStore

def test_boilerplate_detection():
    assert is_boilerplate_paragraph("Bài liên quan: Xem thêm tin tức") is True
    assert is_boilerplate_paragraph("Xem thêm các dự án mới") is True
    assert is_boilerplate_paragraph("Hotline: 0901234567") is True
    assert is_boilerplate_paragraph("Email: contact@news.vn") is True
    assert is_boilerplate_paragraph("© Copyright 2026 Công ty ABC") is True
    assert is_boilerplate_paragraph("Ban biên tập Tòa soạn") is True
    assert is_boilerplate_paragraph("Theo HOSE") is True
    assert is_boilerplate_paragraph("---") is True
    # US-012: Disclaimer, Hồ sơ công ty, Chú thích ảnh, Chữ ký phóng viên
    assert is_boilerplate_paragraph("Tuyên bố miễn trừ: Báo cáo này chỉ mang tính tham khảo cho nhà đầu tư.") is True
    assert is_boilerplate_paragraph("Khuyến cáo miễn trừ trách nhiệm đầu tư tài chính.") is True
    assert is_boilerplate_paragraph("Thông tin doanh nghiệp: CTCP Tập đoàn Vingroup thành lập năm 1993.") is True
    assert is_boilerplate_paragraph("Ảnh: Toàn cảnh dự án nhìn từ trên cao.") is True
    assert is_boilerplate_paragraph("Hình ảnh: Lễ ký kết hợp tác giữa hai tập đoàn.") is True
    assert is_boilerplate_paragraph("Bài và ảnh: Minh Khang - Phóng viên Báo Đầu tư") is True
    # Doan noi dung that phai duoc giu lai
    assert is_boilerplate_paragraph(
        "VN-Index tăng 12 điểm trong phiên sáng nhờ sức kéo của nhóm ngân hàng."
    ) is False


def test_unpack_batch_output(tmp_path):
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
