"""Kiểm thử nguồn đường dẫn dữ liệu duy nhất `src.core.paths` và chuyển đổi DB (US-038)."""

from __future__ import annotations

import io
import json
import re
import sqlite3
import tokenize
from pathlib import Path

import pytest

from src.core import paths

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Tệp được phép giữ chuỗi đường dẫn `data/...` hoặc phép ghép `/ "data"`, kèm lý do.
SCAN_EXCEPTIONS = {
    "src/core/paths.py": "định nghĩa tiền tố kiểu cũ để resolve_data_path bỏ đi",
    "scripts/maintenance/cleanup_legacy_tasks.py": "đọc thư mục cũ ở gốc kho mã để dọn, không ghi",
}


def test_data_root_theo_bien_moi_truong(tmp_path, monkeypatch):
    """`data_root()` đọc lại biến môi trường ở mỗi lần gọi."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "a"))
    assert paths.data_root() == tmp_path / "a"
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "b"))
    assert paths.data_root() == tmp_path / "b"
    assert paths.bronze_dir() == tmp_path / "b" / "raw_html"
    assert paths.article_packets_dir() == tmp_path / "b" / "agent_tasks" / "article"
    assert paths.agent_outputs_dir("_article") == tmp_path / "b" / "agent_outputs_article"
    assert paths.db_path() == tmp_path / "b" / "monocle.db"


def test_mac_dinh_la_o_cuc_bo(monkeypatch):
    """Không có biến môi trường thì gốc dữ liệu là `C:\\data\\news-scape`."""
    monkeypatch.delenv("MONOCLE_DATA_DIR", raising=False)
    assert paths.data_root() == paths.DEFAULT_DATA_ROOT


@pytest.mark.parametrize("root", [
    r"C:\Users\x\OneDrive - fpts.com.vn\data",
    r"C:\Users\x\SharePoint\FRA\news",
])
def test_tu_choi_goc_trong_onedrive(root, monkeypatch):
    """Gốc dữ liệu trong OneDrive hoặc SharePoint bị từ chối."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", root)
    with pytest.raises(paths.UnsafeDataRootError):
        paths.data_root()


def test_ops_resolve_paths_dung_chung_goc(tmp_path, monkeypatch):
    """`ops.config.resolve_paths` lấy gốc từ `data_root()` và giữ chốt chặn OneDrive."""
    from src.ops.config import resolve_paths

    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path))
    assert resolve_paths().ops_db == tmp_path / "ops.db"
    with pytest.raises(RuntimeError):
        resolve_paths(Path(r"C:\Users\x\OneDrive - fpts.com.vn\d"))


def test_subscriptions_dir_theo_bien_rieng(tmp_path, monkeypatch):
    """Thư mục đăng ký đọc `NEWS_SCAPE_SUBSCRIPTIONS_DIR`, mặc định dưới gốc dữ liệu."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("NEWS_SCAPE_SUBSCRIPTIONS_DIR", raising=False)
    assert paths.subscriptions_dir() == tmp_path / "subscriptions"
    monkeypatch.setenv("NEWS_SCAPE_SUBSCRIPTIONS_DIR", str(tmp_path / "subs"))
    assert paths.subscriptions_dir() == tmp_path / "subs"


@pytest.mark.parametrize("stored", [
    "raw_html/cafef.vn/20261005/x.meta.json",
    "data/raw_html/cafef.vn/20261005/x.meta.json",
    "project/data/raw_html/cafef.vn/20261005/x.meta.json",
    "data\\raw_html\\cafef.vn\\20261005\\x.meta.json",
])
def test_resolve_data_path_ba_dang_tuong_doi(stored, tmp_path, monkeypatch):
    """Dạng mới và dạng cũ có tiền tố đều trỏ về cùng tệp dưới gốc dữ liệu."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path))
    assert paths.resolve_data_path(stored) == (
        tmp_path / "raw_html" / "cafef.vn" / "20261005" / "x.meta.json")


def test_resolve_data_path_giu_nguyen_tuyet_doi(tmp_path, monkeypatch):
    """Đường dẫn tuyệt đối cũ đọc được nguyên trạng."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "root"))
    absolute = tmp_path / "old" / "project" / "data" / "x.json"
    assert paths.resolve_data_path(str(absolute)) == absolute


def test_to_data_relative(tmp_path, monkeypatch):
    """Tệp dưới gốc ra dạng tương đối xuôi, tệp ngoài gốc giữ nguyên."""
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path))
    inside = tmp_path / "silver" / "a" / "b.json"
    assert paths.to_data_relative(inside) == "silver/a/b.json"
    outside = tmp_path.parent / "khac" / "c.json"
    assert paths.to_data_relative(outside) == str(outside)
    assert paths.to_data_relative("raw_html\\x.html") == "raw_html/x.html"
    assert paths.resolve_data_path(paths.to_data_relative(inside)) == inside


def _path_violations(source: str) -> list[str]:
    """Tìm chuỗi bắt đầu bằng `data/` và phép ghép `/ "data"` trong mã nguồn.

    Args:
        source: Nội dung tệp Python.

    Returns:
        Danh sách mô tả vi phạm kèm số dòng.
    """
    found: list[str] = []
    toks = [t for t in tokenize.generate_tokens(io.StringIO(source).readline)
            if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT)]
    literal = re.compile(r"""^[rRbBuUfF]{0,2}(['"])data[/\\]""")
    for i, tok in enumerate(toks):
        if tok.type == tokenize.STRING and literal.match(tok.string):
            found.append(f"{tok.start[0]}: {tok.string[:40]}")
        if getattr(tokenize, "FSTRING_START", None) == tok.type and i + 1 < len(toks):
            nxt = toks[i + 1]
            if nxt.type == tokenize.FSTRING_MIDDLE and re.match(r"data[/\\]", nxt.string):
                found.append(f"{tok.start[0]}: f-string {nxt.string[:40]}")
        if (tok.type == tokenize.OP and tok.string == "/" and i + 1 < len(toks)
                and toks[i + 1].type == tokenize.STRING
                and toks[i + 1].string.strip("'\"") == "data"):
            found.append(f"{tok.start[0]}: / \"data\"")
    return found


def test_khong_con_tu_ghep_duong_dan_data():
    """Mã sản phẩm không tự ghép đường dẫn dữ liệu ngoài `src/core/paths.py`."""
    bad: dict[str, list[str]] = {}
    for base in ("src", "scripts"):
        for p in sorted((PROJECT_ROOT / base).rglob("*.py")):
            rel = p.relative_to(PROJECT_ROOT).as_posix()
            if rel in SCAN_EXCEPTIONS or "__pycache__" in rel:
                continue
            hits = _path_violations(p.read_text(encoding="utf-8"))
            if hits:
                bad[rel] = hits
    assert not bad, f"Còn đường dẫn dữ liệu tự ghép, dùng src.core.paths: {bad}"


def test_bo_quet_bat_duoc_vi_pham():
    """Bộ quét nhận ra cả ba dạng vi phạm và bỏ qua comment."""
    src = ('A = "data/raw_html"\nB = ROOT / "data" / "x"\nC = f"data/{x}"\n'
           '# "data/comment"\nD = {"data": 1}\n')
    lines = {int(v.split(":")[0]) for v in _path_violations(src)}
    assert lines == {1, 2, 3}


def _seed_db(db: Path) -> None:
    """Tạo DB tạm với các cột đường dẫn ở dạng cũ.

    Args:
        db: Đường dẫn DB tạm.
    """
    from src.db.store import ArticleStore

    ArticleStore(db_path=str(db))
    conn = sqlite3.connect(str(db))
    old_abs = r"C:\Users\x\OneDrive - fpts.com.vn\repo\project\data\work_packages\a\b\1.json"
    conn.execute("INSERT INTO work_items (article_id, raw_sha256, domain, "
                 "package_path, status) VALUES ('1', 's', 'd', ?, 'pending')", (old_abs,))
    conn.execute("INSERT INTO work_items (article_id, raw_sha256, domain, "
                 "package_path, status) VALUES ('2', 's', 'd', "
                 "'data/work_packages/a/b/2.json', 'pending')")
    conn.execute("INSERT INTO work_items (article_id, raw_sha256, domain, "
                 "package_path, status) VALUES ('3', 's', 'd', "
                 "'work_packages/a/b/3.json', 'pending')")
    conn.execute("INSERT INTO silver_failures (meta_path, url_title_hash, fetch_ts, attempts, "
                 "last_error, last_at, dead_letter) VALUES "
                 "('data/raw_html/a/1/x.meta.json', 'x', 't', 2, 'e', 't', 0)")
    conn.execute("INSERT INTO silver_failures (meta_path, url_title_hash, fetch_ts, attempts, "
                 "last_error, last_at, dead_letter) VALUES "
                 "('raw_html/a/1/x.meta.json', 'x', 't', 3, 'e', 't', 1)")
    conn.execute("INSERT INTO periodic_reports (source, report_type, period, title, "
                 "source_url, html_path, attachments_json) VALUES ('nso', 'monthly', "
                 "'2026-08', 't', 'u', 'data/raw_reports/nso.gov.vn/1/r.html', ?)",
                 (json.dumps([{"url": "u", "path": "data/raw_reports/nso.gov.vn/1/r.xlsx"}]),))
    conn.commit()
    conn.close()


def test_migrate_dry_run_khong_ghi(tmp_path, monkeypatch):
    """Dry-run đếm đúng số dòng cần đổi và không đụng dữ liệu."""
    from scripts.maintenance import migrate_data_root as mig

    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "root"))
    db = tmp_path / "m.db"
    _seed_db(db)
    before = db.read_bytes()
    counts = mig.migrate(db)
    assert counts["work_items.package_path"] == 2
    assert counts["silver_failures.meta_path"] == 1
    assert counts["periodic_reports.html_path"] == 1
    assert counts["periodic_reports.attachments_json"] == 1
    assert db.read_bytes() == before


def test_migrate_apply_viet_lai_va_gop_trung(tmp_path, monkeypatch):
    """Apply viết lại về dạng mới, gộp khoá trùng của silver_failures, chạy lại không đổi gì."""
    from scripts.maintenance import migrate_data_root as mig

    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "root"))
    db = tmp_path / "m.db"
    _seed_db(db)
    mig.migrate(db, apply=True)
    conn = sqlite3.connect(str(db))
    pkgs = sorted(r[0] for r in conn.execute("SELECT package_path FROM work_items"))
    assert pkgs == ["work_packages/a/b/1.json", "work_packages/a/b/2.json",
                    "work_packages/a/b/3.json"]
    fails = conn.execute("SELECT meta_path, attempts, dead_letter FROM silver_failures").fetchall()
    assert fails == [("raw_html/a/1/x.meta.json", 3, 1)]
    html, att = conn.execute("SELECT html_path, attachments_json FROM periodic_reports").fetchone()
    assert html == "raw_reports/nso.gov.vn/1/r.html"
    assert json.loads(att)[0]["path"] == "raw_reports/nso.gov.vn/1/r.xlsx"
    conn.close()
    assert sum(mig.migrate(db).values()) == 0


def test_migrate_cli_mac_dinh_la_dry_run(tmp_path, monkeypatch, capsys):
    """Lệnh không cờ chỉ in số đếm."""
    from scripts.maintenance import migrate_data_root as mig

    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "root"))
    db = tmp_path / "m.db"
    _seed_db(db)
    assert mig.main(["--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "work_items.package_path" in out
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT count(*) FROM work_items WHERE package_path LIKE 'data/%'"
                        ).fetchone()[0] == 1
    conn.close()
