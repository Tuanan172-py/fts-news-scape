"""Kiểm định bộ lọc bài mỏng của packer: Gold trượt tất định thì khỏi đốt token.

Một bài không đủ hai đoạn văn đạt độ dài trích dẫn thì qua được nhận diện thực
thể nhưng không bao giờ dựng được phần nội dung. Packer loại các bài này khỏi
đợt (đếm riêng chờ Silver), thay vì để mô hình phân tích rồi expand loại.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import article_pack  # noqa: E402
from scripts import article_expand  # noqa: E402
from src.agent import article_contract  # noqa: E402

LONG_A = "Đoạn văn thứ nhất đủ dài để làm trích dẫn nguyên văn."
LONG_B = "Đoạn văn thứ hai đủ dài để làm trích dẫn nguyên văn."


def test_nguong_trich_dan_dung_chung_mot_hang():
    """Packer, expander và hợp đồng dùng chung một ngưỡng trích dẫn."""
    assert article_pack.MIN_CITATION_CHARS == article_contract.MIN_CITATION_CHARS == 20
    assert article_expand.MIN_CITATION_CHARS == article_contract.MIN_CITATION_CHARS


def test_is_thin_doi_hai_doan_dat_do_dai():
    """Mỏng khi không đủ hai đoạn đạt độ dài trích dẫn."""
    assert not article_pack.is_thin([LONG_A, LONG_B])
    assert not article_pack.is_thin([LONG_A, LONG_B, "ngắn"])
    assert article_pack.is_thin([LONG_A])
    assert article_pack.is_thin(["quá ngắn", "cũng ngắn"])
    assert article_pack.is_thin([])


def test_is_thin_row_thieu_du_kien_thi_giu_lai():
    """Không đọc được nội dung thì giữ bài (fail-open), để vòng đóng gói loại sau."""
    assert article_pack.is_thin_row(("day",)) is False


def _db(thick_text, thin_text):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE articles (url_title_hash TEXT, title TEXT, published_at TEXT,
                               source_domain TEXT, content_text TEXT);
        CREATE TABLE work_items (article_id TEXT, package_path TEXT);
        CREATE TABLE l1_outputs (article_id TEXT, dod_pass INTEGER, l1_source TEXT);
    """)
    conn.execute("INSERT INTO articles VALUES ('day', 't', '2026-09-15T08:00', 'x', ?)",
                 (thick_text,))
    conn.execute("INSERT INTO articles VALUES ('mong', 't', '2026-09-15T08:00', 'x', ?)",
                 (thin_text,))
    conn.execute("INSERT INTO work_items VALUES ('day', NULL)")
    conn.execute("INSERT INTO work_items VALUES ('mong', NULL)")
    return conn


def test_load_candidates_loai_bai_mong():
    """Mặc định loại bài mỏng; tắt cờ thì giữ đủ để radar đếm riêng."""
    thick = f"{LONG_A * 3}\n\n{LONG_B * 3}"
    # Dài hơn 100 ký tự để qua lọc SQL, nhưng chỉ một đoạn văn nên Gold trượt.
    thin = "Tin ngắn một dòng. " * 25
    conn = _db(thick, thin)

    picked = {r["article_id"] for r in article_pack.load_candidates(
        conn, date="2026-09-15", limit=10, only_pending=True)}
    assert picked == {"day"}

    kept = {r["article_id"] for r in article_pack.load_candidates(
        conn, date="2026-09-15", limit=10, only_pending=True, exclude_thin=False)}
    assert kept == {"day", "mong"}
    conn.close()


def test_row_paragraphs_uu_tien_goi_silver(tmp_path, monkeypatch):
    """Có gói Silver thì đọc gói, không thì dùng nội dung RSS trong DB."""
    import json

    pkg = tmp_path / "w.json"
    pkg.write_text(json.dumps({"cleaned_text": f"{LONG_A}\n\n{LONG_B}"}),
                   encoding="utf-8")
    monkeypatch.setattr(article_pack, "PROJECT_ROOT", tmp_path)

    class Row(dict):
        pass

    paras = article_pack.row_paragraphs(Row({"package_path": "w.json",
                                            "content_text": "ngắn"}))
    assert len([p for p in paras if len(p) >= 20]) >= 2

    paras = article_pack.row_paragraphs(Row({"package_path": None,
                                            "content_text": "ngắn"}))
    assert paras == [] or article_pack.is_thin(paras)
