"""Predicate `value_added` + `implication_specific` — cổng chặn output sao chép / template.

Bối cảnh: xem `docs/decisions/0004-gold-value-gate-va-du-lieu-gia-lap.md`. Trước 2026-09-08
cổng DoD chỉ đo tính CÓ CĂN CỨ; với output copy nguyên văn thì phép thử đó hiển nhiên đúng
nên 1.274/1.274 bản ghi đều pass.
"""
from __future__ import annotations

import hashlib
import json

from src.agent.dod import check_dod

CLEANED = (
    "Hòa Phát báo lãi quý 2 đạt 3.200 tỷ đồng, tăng 18% so với cùng kỳ.\n"
    "Sản lượng thép xây dựng đạt 1,2 triệu tấn trong kỳ.\n"
    "Doanh nghiệp cho biết giá quặng đầu vào hạ nhiệt từ tháng 5."
)
SPAN_A = "Hòa Phát báo lãi quý 2 đạt 3.200 tỷ đồng, tăng 18% so với cùng kỳ."
SPAN_B = "Sản lượng thép xây dựng đạt 1,2 triệu tấn trong kỳ."
GOOD_IMPLICATION = ("Biên lợi nhuận HPG nhiều khả năng cải thiện tiếp trong quý 3 nếu giá quặng "
                    "giữ xu hướng giảm, hỗ trợ nhóm cổ phiếu thép.")


def _wp(tmp_path):
    raw = b"<html>x</html>"
    p = tmp_path / "a.html"
    p.write_bytes(raw)
    wp = {"schema_version": "1.0", "article_id": "a", "source_url": "http://x", "domain": "d",
          "raw_html_path": str(p), "raw_sha256": hashlib.sha256(raw).hexdigest(),
          "cleaned_text": CLEANED, "capture_status": "OK", "change_state": "NEW"}
    (tmp_path / "a.pkg.json").write_text(json.dumps(wp, ensure_ascii=False), encoding="utf-8")
    return wp


def _out(**over):
    o = {
        "output_schema_version": "1.0", "article_id": "a",
        "summary": {
            "abstractive": "HPG lãi tăng 18% nhờ sản lượng cao và chi phí quặng hạ.",
            "key_points": ["Lãi quý 2 vượt 3.200 tỷ", "Giá quặng hạ từ tháng 5"],
        },
        "implication": {"text": GOOD_IMPLICATION, "impact_area": "market"},
        "materiality": {"score": 0.7, "time_sensitivity": "this_week"},
        "citations": [{"claim": "c1", "source_span": SPAN_A, "source_offset": 0},
                      {"claim": "c2", "source_span": SPAN_B, "source_offset": 66}],
        "processing_metadata": {"agent_provider": "p", "model_used": "m",
                                "timestamp": "2026-09-08T09:00:00+07:00"},
        "extraction_quality": "high",
    }
    o.update(over)
    return o


def test_good_output_passes(tmp_path):
    ok, reasons = check_dod(_out(), _wp(tmp_path))
    assert ok, reasons


def test_abstractive_copied_verbatim_fails(tmp_path):
    """Nối vài câu đầu bài bằng ' ' — đúng cách script cũ sinh `abstractive`."""
    out = _out()
    out["summary"]["abstractive"] = f"{SPAN_A} {SPAN_B}"
    ok, reasons = check_dod(out, _wp(tmp_path))
    assert not ok
    assert any("abstractive" in r for r in reasons)


def test_key_points_copying_citations_fails(tmp_path):
    """Mẫu hỏng phổ biến nhất: key_points = chính các source_span (100% bản ghi cũ)."""
    out = _out()
    out["summary"]["key_points"] = [SPAN_A, SPAN_B]
    ok, reasons = check_dod(out, _wp(tmp_path))
    assert not ok
    assert any("key_points" in r for r in reasons)


def test_boilerplate_implication_fails(tmp_path):
    out = _out()
    out["implication"]["text"] = ("Nội dung bài viết phản ánh thông tin và diễn biến quan trọng "
                                  "đối với các doanh nghiệp, ngành nghề và thị trường liên quan.")
    ok, reasons = check_dod(out, _wp(tmp_path))
    assert not ok
    assert any("boilerplate" in r for r in reasons)


def test_short_implication_fails(tmp_path):
    out = _out()
    out["implication"]["text"] = "Hàm ý"
    ok, reasons = check_dod(out, _wp(tmp_path))
    assert not ok
    assert any("implication.text <" in r for r in reasons)


def test_implication_copied_from_source_fails(tmp_path):
    out = _out()
    out["implication"]["text"] = SPAN_A
    ok, reasons = check_dod(out, _wp(tmp_path))
    assert not ok
    assert any("trích nguyên văn" in r for r in reasons)


def test_thresholds_are_configurable_without_code_change():
    """Ngưỡng + blocklist đọc từ schemas/task-lifecycle-v1.yaml (sửa spec, không sửa code)."""
    from src.agent.dod import load_thresholds

    t = load_thresholds()
    assert t["min_implication_len"] >= 40
    assert any("phản ánh thông tin và diễn biến quan trọng" in b
               for b in t["boilerplate_implications"])


def test_canonical_sample_passes_the_new_gate():
    """Mẫu trong schemas/samples là thứ agent bắt chước — nó PHẢI qua được cổng mới."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sample = json.loads((root / "schemas" / "samples" / "agent-output-sample.json")
                        .read_text(encoding="utf-8"))
    spans = {c["source_span"] for c in sample["citations"]}
    assert not (set(sample["summary"]["key_points"]) & spans), \
        "sample tự vi phạm value_added — agent sẽ bắt chước đúng lỗi đó"
    assert len(sample["implication"]["text"]) >= 40
