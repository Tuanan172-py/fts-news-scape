"""Bản code-first ở `l1_outputs` không lọt vào đường sống nào của pipeline (US-040, ADR 0010 D4)."""
from __future__ import annotations

import csv
import sqlite3
from datetime import date

import _userkit as k
import pytest

from src.agent.article_contract import (
    CODE_FIRST_SOURCE,
    analyzed_l1_sql,
    not_code_first_sql,
)
from src.export.user_output import UserOutputWriter

DATE = "2026-08-18"
REAL, CF = "a_real", "a_cf"


def _mark_code_first(store, aid: str) -> None:
    conn = store.connect()
    conn.execute("UPDATE l1_outputs SET l1_source = ? WHERE article_id = ?",
                 (CODE_FIRST_SOURCE, aid))
    conn.commit()
    conn.close()


@pytest.fixture
def world(tmp_path):
    """Dựng DB tạm có một bài phân tích thật và một bài chỉ có bản code-first, cả hai có Gold."""
    store = k.make_store(tmp_path)
    for aid in (REAL, CF):
        k.seed_article(store, aid)
        k.seed_l1(store, aid, ["TICKER:HPG"])
        k.seed_agent(store, aid)
    _mark_code_first(store, CF)
    return store


def test_sql_helpers_exclude_code_first():
    assert analyzed_l1_sql("o") == ("o.dod_pass = 1 AND "
                                    "COALESCE(o.l1_source, 'agent') <> 'code_first'")
    assert analyzed_l1_sql() == "dod_pass = 1 AND COALESCE(l1_source, 'agent') <> 'code_first'"
    assert not_code_first_sql("l1") == "COALESCE(l1.l1_source, 'agent') <> 'code_first'"


def test_delivery_never_contains_code_first(world, tmp_path):
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    writer = UserOutputWriter(world, reg, output_root=tmp_path / "out")
    assert {r["article_id"] for r in writer.gated_rows(date="all")} == {REAL}

    counts = writer.write(date=DATE)
    assert counts == {"AnPT": 1}
    rows = k.read_delivery(tmp_path / "out" / "AnPT" / f"{DATE}.xlsx")
    assert [r["article_id"] for r in rows] == [REAL]
    for path in (tmp_path / "out" / "_master").glob("*.csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            ids = {r.get("article_id") for r in csv.DictReader(f)}
        assert CF not in ids, path.name


def test_insight_signals_skip_code_first(world):
    from src.analytics.signals import load_data

    conn = world.connect()
    try:
        arts, _ = load_data(conn, "2026-01-01")
    finally:
        conn.close()
    assert {a.id for a in arts} == {REAL}


def test_selector_keeps_code_first_article_pending(world):
    from scripts.article_pack import load_candidates

    conn = world.connect()
    conn.execute("UPDATE articles SET content_text = ?", ("x" * 200,))
    conn.commit()
    try:
        rows = load_candidates(conn, date=None, limit=10, only_pending=True,
                               exclude_thin=False)
    finally:
        conn.close()
    assert {r["article_id"] for r in rows} == {CF}


def test_wave_coverage_ignores_code_first(world):
    from scripts.article_run import coverage_of

    conn = world.connect()
    try:
        cov = coverage_of(conn, [REAL, CF])
    finally:
        conn.close()
    assert cov["l1_ok"] == {REAL}
    assert CF not in cov["l1_fail"]


def test_claim_require_l1_skips_code_first(world):
    from src.handoff.catalog import Catalog

    cat = Catalog(world)
    cat.enqueue(CF, "h_cf", "cafef.vn", "p_cf", "NEW")
    assert cat.claim("w", require_l1=True) is None
    cat.enqueue(REAL, "h_real", "cafef.vn", "p_real", "NEW")
    got = cat.claim("w", require_l1=True)
    assert got is not None and got["article_id"] == REAL


def test_daily_report_l1_counts_skip_code_first(world, tmp_path):
    from src.monitor.daily_reporter import DailyReporter

    rep = DailyReporter(db_path=world.db_path, users_output_dir=tmp_path / "none")
    m = rep.collect_metrics("all")
    assert sum(r["count"] for r in m["agents"]["l1_outputs"] if r["dod_pass"] == 1) == 1


def test_packet_cleaner_keeps_code_first_packet(world):
    from scripts.maintenance.clean_completed_packets import _is_done

    conn = world.connect()
    try:
        assert _is_done(conn, REAL, True) is True
        assert _is_done(conn, CF, True) is False
    finally:
        conn.close()


def test_backlog_counts_skip_code_first(world):
    from scripts.l1_backlog import collect

    m = collect(world)
    assert m["delivered_gold"] == 1
    assert m["t1_gold_ready"] == 1


def test_tick_counts_code_first_as_pending(world, tmp_path):
    from pathlib import Path

    from scripts.article_tick import count_pending_articles

    conn = world.connect()
    for aid in (REAL, CF):
        conn.execute("INSERT INTO work_items (article_id, raw_sha256, domain, package_path, "
                     "change_state, status, enqueued_at) VALUES (?,?,?,?,?,?,?)",
                     (aid, "h_" + aid, "cafef.vn", "p_" + aid, "NEW", "pending", "t"))
    conn.commit()
    conn.close()
    assert count_pending_articles(Path(world.db_path)) == 1


def test_published_mentions_skip_code_first(world, tmp_path):
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    from pathlib import Path

    from src.export.publisher import _build_parquet

    conn = world.connect()
    conn.execute("UPDATE l1_outputs SET created_at = ?", (f"{DATE}T10:00:00+07:00",))
    conn.commit()
    conn.close()
    out = tmp_path / "m.parquet"
    n = _build_parquet(Path(world.db_path), "l1_outputs", "created_at",
                       date.fromisoformat(DATE), out)
    assert n == 1
    assert list(pd.read_parquet(out)["article_id"]) == [REAL]


def test_seed_really_wrote_code_first(world):
    conn = sqlite3.connect(world.db_path)
    try:
        src = dict(conn.execute("SELECT article_id, l1_source FROM l1_outputs"))
    finally:
        conn.close()
    assert src == {REAL: "agent", CF: CODE_FIRST_SOURCE}
