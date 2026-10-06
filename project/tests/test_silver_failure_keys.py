"""Kiểm thử chuẩn hoá khoá sổ lỗi Silver để dòng cũ không ghim watermark."""

from __future__ import annotations

from src.core import paths
from src.db.store import ArticleStore

REL = "raw_html/fireant.vn/20260925/x.meta.json"
LEGACY = "data/" + REL
TS = "2026-09-25T14:53:28+07:00"


def test_khoa_tuong_doi_va_tuyet_doi_ve_cung_dang():
    absolute = str(paths.resolve_data_path(REL))
    assert ArticleStore.canonical_meta_key(absolute) == REL
    assert ArticleStore.canonical_meta_key(REL.replace("/", "\\")) == REL
    assert ArticleStore.canonical_meta_key(LEGACY.replace("/", "\\")) == REL


def test_xoa_theo_khoa_tuyet_doi_xoa_dong_khoa_tuong_doi(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    store.record_silver_failure(LEGACY.replace("/", "\\"), TS, "raw_missing", 5)
    assert store.count_silver_failures() == (1, 0)
    store.clear_silver_failure(str(paths.resolve_data_path(REL)))
    assert store.count_silver_failures() == (0, 0)


def test_chuan_hoa_gop_dong_trung_giu_so_lan_thu_lon_nhat(tmp_path):
    store = ArticleStore(db_path=str(tmp_path / "t.db"))
    conn = store._connect()
    conn.execute("INSERT INTO silver_failures VALUES (?,?,?,?,?,?,?)",
                 (LEGACY.replace("/", "\\"), "", TS, 3, "e", TS, 0))
    conn.execute("INSERT INTO silver_failures VALUES (?,?,?,?,?,?,?)",
                 (REL, "", TS, 29, "e", TS, 1))
    conn.commit()
    conn.close()

    assert store.normalize_silver_failure_keys() == 1
    conn = store._connect()
    rows = conn.execute("SELECT meta_path, attempts, dead_letter FROM silver_failures").fetchall()
    conn.close()
    assert [tuple(r) for r in rows] == [(REL, 29, 1)]
    assert store.blocking_silver_failure_ts() == ""
