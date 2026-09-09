"""
CLI `scripts/agent_ingest.py` — vùng trước đây không có test (regression `done_aids`).

Bug đã sửa: `done_aids` không hề khởi tạo → NameError ngay output Gold ĐẦU TIÊN đạt DoD,
làm hỏng cả run ingest (và do đó chặn toàn bộ luồng giao hàng).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import agent_ingest  # noqa: E402

from src.db.store import ArticleStore  # noqa: E402
from src.handoff.catalog import Catalog  # noqa: E402

CLEANED = "Alpha beta gamma đầu ngành. Delta epsilon zeta lao động giảm mạnh."


def _seed_work_item(tmp_path, store, article_id="art1"):
    raw = b"<html><body>raw bytes</body></html>"
    raw_path = tmp_path / f"{article_id}.html"
    raw_path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    wp = {"schema_version": "1.0", "article_id": article_id,
          "source_url": "https://cafef.vn/x.chn", "domain": "cafef.vn",
          "raw_html_path": str(raw_path), "raw_sha256": sha,
          "cleaned_text": CLEANED, "capture_status": "ok", "change_state": "NEW"}
    wp_path = tmp_path / f"{article_id}.pkg.json"
    wp_path.write_text(json.dumps(wp, ensure_ascii=False), encoding="utf-8")
    Catalog(store).enqueue(article_id, sha, "cafef.vn", str(wp_path), "NEW")
    return sha


def _output(article_id="art1"):
    return {
        "output_schema_version": "1.0", "article_id": article_id,
        "summary": {"abstractive": "tóm tắt", "key_points": ["a"]},
        "implication": {"text": "Chi phí đầu vào hạ nhiệt có thể nới biên lợi nhuận quý tới của nhóm doanh nghiệp liên quan, hỗ trợ định giá cổ phiếu.", "impact_area": "market"},
        "materiality": {"score": 0.6, "time_sensitivity": "this_week"},
        "citations": [
            {"claim": "c1", "source_span": "Alpha beta gamma đầu ngành.", "source_offset": 0},
            {"claim": "c2", "source_span": "Delta epsilon zeta lao động giảm mạnh.", "source_offset": 28},
        ],
        "processing_metadata": {"agent_provider": "p", "model_used": "m", "timestamp": "t"},
        "extraction_quality": "high",
    }


def _run(tmp_path, monkeypatch, target):
    db = tmp_path / "t.db"
    store = ArticleStore(db_path=str(db))
    sha = _seed_work_item(tmp_path, store)
    monkeypatch.setattr(agent_ingest, "load_settings",
                        lambda: {"database": {"path": str(db)}})
    rc = agent_ingest.main([str(target), "--task-dir", str(tmp_path / "tasks"), "--no-archive"])
    return rc, store, sha


def test_ingest_single_output_no_nameerror(tmp_path, monkeypatch):
    out = tmp_path / "out.json"
    out.write_text(json.dumps(_output(), ensure_ascii=False), encoding="utf-8")
    rc, store, sha = _run(tmp_path, monkeypatch, out)
    assert rc == 0
    assert store.get_agent_output("art1", sha)["dod_pass"] == 1


def test_ingest_batch_array(tmp_path, monkeypatch):
    out = tmp_path / "batch_01.json"
    out.write_text(json.dumps([_output()], ensure_ascii=False), encoding="utf-8")
    rc, store, sha = _run(tmp_path, monkeypatch, out)
    assert rc == 0
    assert store.get_agent_output("art1", sha)["dod_pass"] == 1


def test_output_carrying_dod_pass_key_is_not_trusted(tmp_path, monkeypatch):
    """Output thô mang sẵn key `dod_pass` KHÔNG được bypass DoD — phải chấm lại thật."""
    bad = _output()
    bad["dod_pass"] = True
    bad["citations"] = [{"claim": "c", "source_span": "không nằm trong cleaned_text"}]
    out = tmp_path / "bad.json"
    out.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    rc, store, sha = _run(tmp_path, monkeypatch, out)
    assert rc == 0
    assert store.get_agent_output("art1", sha)["dod_pass"] == 0
