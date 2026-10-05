"""Test kế thừa kết quả cho bài chép lại và việc bộ chọn bài giữ bài chép chờ bài gốc."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.core.models import Article
from src.db.store import ArticleStore
from src.pipeline.cluster_job import refresh
from src.pipeline.inherit import apply_inheritance, hold_cutoff

VN = timezone(timedelta(hours=7))
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=VN)


def _article(url, title, text, hours=0):
    ts = (NOW - timedelta(hours=hours)).isoformat(timespec="seconds")
    return Article(url=url, title=title, source_domain="cafef.vn", content_text=text,
                   published_at=ts, fetched_at=ts)


@pytest.fixture
def world(tmp_path):
    st = ArticleStore(db_path=str(tmp_path / "w.db"))
    body = " ".join(f"w{i}" for i in range(150))
    src = _article("https://cafef.vn/g-188261002000000001.chn", "Bài gốc về lãi suất", body, 5)
    cpy = _article("https://vietstock.vn/2026/10/ban-chep-1498001.htm", "Bản chép về lãi suất", body, 3)
    st.insert_batch([src, cpy])
    conn = st._connect()
    now = NOW.isoformat(timespec="seconds")
    conn.execute("INSERT INTO cluster_members (article_id, cluster_id, role, method, score, evidence, decided_at) "
                 "VALUES (?, 'S1', 'canonical', 'single', NULL, '{}', ?)", (src.url_title_hash, now))
    conn.execute("INSERT INTO cluster_members (article_id, cluster_id, role, method, score, evidence, decided_at) "
                 "VALUES (?, 'S1', 'copy', 'sha', 1.0, ?, ?)",
                 (cpy.url_title_hash, json.dumps({"inherit_from": src.url_title_hash}), now))
    conn.commit()
    conn.close()
    return st, src, cpy


def _analyse_source(st, src, dod=1):
    st.insert_l1_output({"article_id": src.url_title_hash, "recognized": 1, "agent_provider": "x",
                         "model_used": "m", "confidence": 0.9, "dod_pass": dod, "dod_reasons": "",
                         "created_at": "2026-10-02T09:00:00+07:00",
                         "output_json": json.dumps({"article_id": src.url_title_hash, "title": src.title,
                                                    "entities": [{"entity_id": "TICKER:VCB"}],
                                                    "processing_metadata": {"model_used": "m"}})})
    st.insert_agent_output({"article_id": src.url_title_hash, "raw_sha256": "r1", "work_item_id": None,
                            "agent_provider": "x", "model_used": "m", "confidence": 0.9, "dod_pass": dod,
                            "dod_reasons": "", "created_at": "2026-10-02T09:00:00+07:00",
                            "output_json": json.dumps({"article_id": src.url_title_hash, "sentiment": "positive",
                                                       "summary": "tóm tắt"})})


def test_copy_inherits_both_layers_from_analysed_source(world):
    st, src, cpy = world
    _analyse_source(st, src)
    conn = st._connect()
    stats = apply_inheritance(conn, NOW)
    assert stats["inherited"] == 1
    l1 = conn.execute("SELECT l1_source, dod_pass, output_json FROM l1_outputs WHERE article_id=?",
                      (cpy.url_title_hash,)).fetchone()
    assert l1["l1_source"] == "inherited" and l1["dod_pass"] == 1
    doc = json.loads(l1["output_json"])
    assert doc["article_id"] == cpy.url_title_hash and doc["inherited_from"] == src.url_title_hash
    assert doc["title"] == cpy.title
    ag = conn.execute("SELECT output_json, agent_provider FROM agent_outputs WHERE article_id=?",
                      (cpy.url_title_hash,)).fetchone()
    assert json.loads(ag["output_json"])["sentiment"] == "positive" and ag["agent_provider"] == "inherited"
    conn.close()


def test_idempotent_and_never_overwrites_real_analysis(world):
    st, src, cpy = world
    _analyse_source(st, src)
    conn = st._connect()
    apply_inheritance(conn, NOW)
    assert apply_inheritance(conn, NOW)["candidates"] == 0          # đã có kết quả đạt: không làm lại
    conn.close()


def test_real_model_result_on_copy_is_kept(world):
    st, src, cpy = world
    _analyse_source(st, src)
    st.insert_l1_output({"article_id": cpy.url_title_hash, "recognized": 1, "agent_provider": "real",
                         "model_used": "real", "confidence": 1.0, "dod_pass": 1, "dod_reasons": "",
                         "created_at": "2026-10-02T09:30:00+07:00", "output_json": "{}"})
    conn = st._connect()
    assert apply_inheritance(conn, NOW)["inherited"] == 0
    assert conn.execute("SELECT agent_provider FROM l1_outputs WHERE article_id=?",
                        (cpy.url_title_hash,)).fetchone()[0] == "real"
    conn.close()


def test_source_not_ready_is_reported_not_guessed(world):
    st, src, cpy = world
    conn = st._connect()
    assert apply_inheritance(conn, NOW) == {"candidates": 1, "inherited": 0, "source_not_ready": 1}
    _analyse_source(st, src, dod=0)                                     # bài gốc trượt DoD
    assert apply_inheritance(conn, NOW)["inherited"] == 0
    conn.close()


def test_code_first_row_on_copy_does_not_block_inheritance(world):
    st, src, cpy = world
    _analyse_source(st, src)
    st.insert_l1_output({"article_id": cpy.url_title_hash, "recognized": 1, "agent_provider": "code_first",
                         "model_used": "-", "confidence": 0.5, "dod_pass": 1, "dod_reasons": "",
                         "created_at": "2026-10-02T09:30:00+07:00", "output_json": "{}",
                         "l1_source": "code_first"})
    conn = st._connect()
    assert apply_inheritance(conn, NOW)["inherited"] == 1
    conn.close()


# -- bộ chọn bài ---------------------------------------------------------------
def test_pack_holds_copy_then_releases_after_expiry(world, monkeypatch):
    from scripts import article_pack
    st, src, cpy = world
    conn = st._connect()
    conn.execute("UPDATE cluster_members SET decided_at=? WHERE article_id=?",
                 (datetime.now(VN).isoformat(timespec="seconds"), cpy.url_title_hash))
    conn.commit()
    ids = {r["article_id"] for r in article_pack.load_candidates(
        conn, date=None, limit=10, only_pending=True, with_content=False)}
    assert src.url_title_hash in ids and cpy.url_title_hash not in ids       # bài chép bị giữ
    old = (datetime.now(VN) - timedelta(hours=60)).isoformat(timespec="seconds")
    conn.execute("UPDATE cluster_members SET decided_at=? WHERE article_id=?", (old, cpy.url_title_hash))
    conn.commit()
    ids = {r["article_id"] for r in article_pack.load_candidates(
        conn, date=None, limit=10, only_pending=True, with_content=False)}
    assert cpy.url_title_hash in ids                                          # hết hạn giữ thì trả về
    conn.close()


def test_hold_cutoff_is_48_hours_back():
    assert hold_cutoff(NOW) == (NOW - timedelta(hours=48)).isoformat(timespec="seconds")


def test_refresh_end_to_end_clusters_then_inherits(tmp_path):
    st = ArticleStore(db_path=str(tmp_path / "e.db"))
    body = " ".join(f"z{i}" for i in range(150))
    first = _article("https://cafef.vn/a-188261002000000007.chn", "Tin chính về trái phiếu", body, 4)
    second = _article("https://vietnambiz.vn/b-202610021200001.htm", "Tin chính về trái phiếu hôm nay", body, 2)
    st.insert_batch([first, second])
    _analyse_source(st, first)
    conn = st._connect()
    stats = refresh(conn, days=3)
    assert stats["copy"] == 1 and stats["inherit_inherited"] == 1
    assert conn.execute("SELECT COUNT(*) FROM l1_outputs WHERE l1_source='inherited'").fetchone()[0] == 1
    conn.close()
