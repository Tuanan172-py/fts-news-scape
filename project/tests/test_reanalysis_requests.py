"""Kiểm tra cơ chế yêu cầu phân tích lại bài đã đạt DoD (US-054)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.article_pack import load_candidates  # noqa: E402
from scripts.maintenance import request_reanalysis as rr  # noqa: E402
from src.db.store import ArticleStore  # noqa: E402

OLD = "2026-11-10T08:00:00+07:00"
REQ = "2026-11-17T09:00:00+07:00"
NEW = "2026-11-17T10:00:00+07:00"


@pytest.fixture
def store(tmp_path: Path) -> ArticleStore:
    """Kho tạm có hai bài đã đạt DoD ở cả hai lớp."""
    st = ArticleStore(str(tmp_path / "m.db"))
    conn = st._connect()
    try:
        for aid in ("a1", "a2"):
            conn.execute(
                "INSERT INTO articles (url_title_hash, url, title, source_domain, published_at, "
                "fetched_at, content_text) VALUES (?, ?, 'Tiêu đề', 'x.vn', '2026-11-10T07:00:00+07:00', "
                "'2026-11-10T07:30:00+07:00', ?)", (aid, f"https://x/{aid}", "Nội dung " * 30))
        conn.commit()
    finally:
        conn.close()
    for aid in ("a1", "a2"):
        st.insert_l1_output({"article_id": aid, "output_json": "{\"v\":\"old\"}", "dod_pass": 1,
                             "created_at": OLD})
        st.insert_agent_output({"article_id": aid, "raw_sha256": "sha", "output_json": "{\"v\":\"old\"}",
                                "dod_pass": 1, "created_at": OLD})
    return st


def _picked(store: ArticleStore) -> set[str]:
    conn = store._connect_ro()
    try:
        return {r["article_id"] for r in load_candidates(
            conn, date="2026-11-10", limit=10, only_pending=True, exclude_thin=False)}
    finally:
        conn.close()


def test_bai_da_phan_tich_khong_duoc_chon_khi_chua_co_yeu_cau(store):
    assert _picked(store) == set()


def test_yeu_cau_dua_bai_tro_lai_hang_doi_va_luu_ban_cu(store):
    counts = store.request_reanalysis(["a1", "zzz"], "đổi chế độ thực thể", "t1", REQ)
    assert counts == {"requested": 1, "already_open": 0, "no_passing_output": 1}
    assert _picked(store) == {"a1"}
    conn = store._connect_ro()
    try:
        layers = sorted(r["layer"] for r in conn.execute(
            "SELECT layer FROM reanalysis_archive WHERE article_id='a1'"))
    finally:
        conn.close()
    assert layers == ["agent", "l1"]
    again = store.request_reanalysis(["a1"], "lần hai", "t1", REQ)
    assert again["already_open"] == 1 and again["requested"] == 0


def test_ban_moi_hong_khong_ghi_de_ban_cu_va_bai_van_cho(store):
    store.request_reanalysis(["a1"], "r", "t1", REQ)
    store.insert_agent_output({"article_id": "a1", "raw_sha256": "sha", "output_json": "{\"v\":\"bad\"}",
                               "dod_pass": 0, "created_at": NEW})
    store.insert_l1_output({"article_id": "a1", "output_json": "{\"v\":\"bad\"}", "dod_pass": 0,
                           "created_at": NEW})
    assert store.get_agent_output("a1", "sha")["output_json"] == "{\"v\":\"old\"}"
    assert store.get_l1_output("a1")["dod_pass"] == 1
    assert _picked(store) == {"a1"}


def test_hong_van_ghi_binh_thuong_khi_khong_co_yeu_cau(store):
    """Ngoài phạm vi yêu cầu, hành vi cũ giữ nguyên: bản hỏng thay bản đạt."""
    store.insert_l1_output({"article_id": "a2", "output_json": "{}", "dod_pass": 0, "created_at": NEW})
    assert store.get_l1_output("a2")["dod_pass"] == 0


def test_ban_moi_dat_hai_lop_thi_yeu_cau_tu_dong(store):
    store.request_reanalysis(["a1"], "r", "t1", REQ)
    store.insert_l1_output({"article_id": "a1", "output_json": "{\"v\":\"new\"}", "dod_pass": 1,
                            "created_at": NEW})
    assert _picked(store) == {"a1"}, "mới một lớp mới thì vẫn chờ"
    store.insert_agent_output({"article_id": "a1", "raw_sha256": "sha", "output_json": "{\"v\":\"new\"}",
                               "dod_pass": 1, "created_at": NEW})
    assert _picked(store) == set()
    assert store.reanalysis_since("a1") is None
    assert store.get_agent_output("a1", "sha")["output_json"] == "{\"v\":\"new\"}"


def test_ingest_khong_tra_ket_qua_cu_trong_bo_nho_dem_khi_co_yeu_cau(store, monkeypatch):
    from src.agent import l1_runner

    monkeypatch.setattr(l1_runner, "check_l1_dod", lambda *a, **k: (True, []))
    store.upsert_l1_task({"article_id": "a1", "domain": "x.vn", "title": "Tiêu đề", "code_first_json": "{}",
                          "route": "article_lane", "packet_path": "", "enqueued_at": OLD})
    runner = l1_runner.L1Runner(store, registry=object())
    assert runner.ingest_output({"article_id": "a1"}).get("cached") is True, "chưa có yêu cầu: dùng bản cũ"
    store.request_reanalysis(["a1"], "r", "t1", REQ)
    res = runner.ingest_output({"article_id": "a1", "recognized": True})
    assert res["dod_pass"] and "cached" not in res
    assert store.get_l1_output("a1")["created_at"] >= REQ


def test_tien_do_va_dat_lai_bo_dem_lan(store, tmp_path):
    store.request_reanalysis(["a1", "a2"], "r", "t1", REQ)
    store.insert_l1_output({"article_id": "a1", "output_json": "{}", "dod_pass": 1, "created_at": NEW})
    store.insert_agent_output({"article_id": "a1", "raw_sha256": "sha", "output_json": "{}",
                               "dod_pass": 1, "created_at": NEW})
    assert rr.progress(store, "t1") == [{"batch_tag": "t1", "total": 2, "closed": 1, "open": 1}]

    from src.ops.store import OpsStore

    ops = OpsStore(tmp_path / "ops.db")
    with ops.conn() as c:
        c.execute("INSERT INTO ops_article_attempts(article_id, attempts) VALUES ('a2', 2)")
    assert ops.reset_attempts(["a2", "a1"]) == 1
    assert ops.exhausted_article_ids(2) == set()


def test_cli_dry_run_khong_ghi(store, tmp_path, capsys):
    csv_path = tmp_path / "ids.csv"
    csv_path.write_text("article_id,title\na1,x\na2,y\n", encoding="utf-8")
    rc = rr.main(["--db-path", store.db_path, "--ids-csv", str(csv_path), "--reason", "r",
                  "--batch-tag", "t1"])
    assert rc == 0 and "DRY-RUN" in capsys.readouterr().out
    assert rr.progress(store, "t1") == []
    assert rr.ids_from_range(store, "2026-11-10..2026-11-10") == ["a1", "a2"]


def test_goi_viec_cu_tu_rss_duoc_dung_lai_tu_silver_khi_phan_tich_lai(store, tmp_path, monkeypatch):
    """Sự cố W11171902: gói việc cũ giữ đoạn trích RSS, mô hình đọc Silver đầy đủ, mọi trích dẫn hỏng."""
    from src.agent import runner as runner_mod
    from src.agent import silver_source
    from src.core import paths

    monkeypatch.setattr(paths, "work_packages_dir", lambda: tmp_path / "wp")
    monkeypatch.setattr(runner_mod, "verify_preconditions", lambda wp: (True, []))
    monkeypatch.setattr(runner_mod, "check_dod", lambda out, wp: (
        out["span"] in wp["cleaned_text"], [] if out["span"] in wp["cleaned_text"] else ["not grounded"]))
    full = "Đoạn mở đầu. " + "Câu chỉ có trong bản Silver đầy đủ về lợi nhuận quý ba. " * 3
    monkeypatch.setattr(silver_source, "read_silver_text", lambda *a: "")
    runner = runner_mod.AgentRunner(store, task_dir=tmp_path / "tasks")
    item = runner._register_article_lane_item("a1")          # lần đầu: chỉ có văn bản RSS
    assert "Silver" not in (tmp_path / "wp" / "a1.json").read_text(encoding="utf-8")

    monkeypatch.setattr(silver_source, "read_silver_text", lambda *a: full)
    store.request_reanalysis(["a1"], "r", "t1", REQ)
    res = runner.ingest_output({"article_id": "a1", "span": "Câu chỉ có trong bản Silver đầy đủ"})
    assert res["dod_pass"], res
    assert res["work_item_id"] == item["id"]
