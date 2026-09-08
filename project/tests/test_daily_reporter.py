"""
test_daily_reporter.py — Kiểm thử tự động cho module DailyReporter & CLI monitor_daily.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.monitor.daily_reporter import DailyReporter, resolve_date_range


def test_resolve_date_range():
    # 1. Single specific date
    s, e, dlist = resolve_date_range("2026-08-18", days=0)
    assert s == "2026-08-18"
    assert e == "2026-08-18"
    assert dlist == ["2026-08-18"]

    # 2. Date with days=3
    s, e, dlist = resolve_date_range("2026-08-20", days=3)
    assert s == "2026-08-18"
    assert e == "2026-08-20"
    assert dlist == ["2026-08-18", "2026-08-19", "2026-08-20"]

    # 3. 'all'
    s, e, dlist = resolve_date_range("all", days=0)
    assert s == "" and e == "" and dlist == []


def _seed_mock_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE articles (
        id INTEGER PRIMARY KEY,
        url TEXT UNIQUE,
        url_title_hash TEXT UNIQUE,
        title TEXT,
        source_domain TEXT,
        fetched_at TEXT
    );
    CREATE TABLE scraper_heartbeat (
        scraper_name TEXT PRIMARY KEY,
        last_run_ts TEXT,
        status TEXT,
        consecutive_failures INTEGER,
        cycle_count INTEGER,
        error_msg TEXT
    );
    CREATE TABLE scraper_metrics (
        ts TEXT,
        scraper_name TEXT,
        articles_fetched INTEGER,
        articles_new INTEGER,
        errors INTEGER,
        duration_ms INTEGER
    );
    CREATE TABLE article_versions (
        id INTEGER PRIMARY KEY,
        url_title_hash TEXT,
        source_domain TEXT,
        captured_at TEXT,
        state TEXT
    );
    CREATE TABLE pipeline_state (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
    );
    CREATE TABLE l1_tasks (
        id INTEGER PRIMARY KEY,
        article_id TEXT UNIQUE,
        status TEXT,
        route TEXT,
        enqueued_at TEXT
    );
    CREATE TABLE work_items (
        id INTEGER PRIMARY KEY,
        article_id TEXT,
        raw_sha256 TEXT,
        status TEXT,
        enqueued_at TEXT,
        UNIQUE(article_id, raw_sha256)
    );
    CREATE TABLE l1_outputs (
        id INTEGER PRIMARY KEY,
        article_id TEXT UNIQUE,
        agent_provider TEXT,
        model_used TEXT,
        dod_pass INTEGER,
        created_at TEXT
    );
    CREATE TABLE agent_outputs (
        id INTEGER PRIMARY KEY,
        article_id TEXT,
        raw_sha256 TEXT,
        agent_provider TEXT,
        model_used TEXT,
        dod_pass INTEGER,
        created_at TEXT,
        UNIQUE(article_id, raw_sha256)
    );

    -- Seed data for 2026-08-18
    INSERT INTO articles (url, url_title_hash, title, source_domain, fetched_at)
    VALUES ('http://a.com/1', 'hash1', 'Tin 1', 'cafef.vn', '2026-08-18T10:00:00+07:00'),
           ('http://a.com/2', 'hash2', 'Tin 2', 'vietstock.vn', '2026-08-18T11:00:00+07:00');

    INSERT INTO scraper_heartbeat (scraper_name, last_run_ts, status, consecutive_failures, cycle_count, error_msg)
    VALUES ('cafef', '2026-08-18T10:00:00+07:00', 'ok', 0, 10, ''),
           ('vietstock', '2026-08-18T11:00:00+07:00', 'ok', 0, 10, '');

    INSERT INTO scraper_metrics (ts, scraper_name, articles_fetched, articles_new, errors, duration_ms)
    VALUES ('2026-08-18T10:00:00', 'cafef', 50, 1, 0, 500);

    INSERT INTO article_versions (url_title_hash, source_domain, captured_at, state)
    VALUES ('hash1', 'cafef.vn', '2026-08-18T10:00:00+07:00', 'NEW'),
           ('hash2', 'vietstock.vn', '2026-08-18T11:00:00+07:00', 'NEW');

    INSERT INTO pipeline_state (key, value, updated_at)
    VALUES ('silver_watermark', '2026-08-18T11:00:00+07:00', '2026-08-18T11:00:00');

    INSERT INTO l1_tasks (article_id, status, route, enqueued_at)
    VALUES ('hash1', 'done', 'resolved', '2026-08-18T10:05:00+07:00');

    INSERT INTO work_items (article_id, raw_sha256, status, enqueued_at)
    VALUES ('hash1', 'rawsha1', 'done', '2026-08-18T10:10:00+07:00');

    INSERT INTO l1_outputs (article_id, agent_provider, model_used, dod_pass, created_at)
    VALUES ('hash1', 'antigravity', 'flash', 1, '2026-08-18T10:06:00+07:00');

    INSERT INTO agent_outputs (article_id, raw_sha256, agent_provider, model_used, dod_pass, created_at)
    VALUES ('hash1', 'rawsha1', 'antigravity', 'gold-financial-analyst', 1, '2026-08-18T10:15:00+07:00');
    """)
    conn.commit()
    conn.close()


def test_daily_reporter_metrics(tmp_path):
    db_file = tmp_path / "monocle.db"
    _seed_mock_db(db_file)

    users_dir = tmp_path / "users_out"
    user_a = users_dir / "AnPT"
    user_a.mkdir(parents=True)
    csv_file = user_a / "2026-08-18.csv"
    csv_file.write_text("date,title\n2026-08-18,Tin 1\n", encoding="utf-8-sig")

    reporter = DailyReporter(db_path=str(db_file), users_output_dir=users_dir)
    m = reporter.collect_metrics(date_str="2026-08-18")

    # Check 5-tier funnel
    fn = m["funnel"]
    assert fn["bronze_raw_total"] == 2
    assert fn["silver_new"] == 2
    assert fn["l1_tasks_total"] == 1
    assert fn["l1_passed"] == 1
    assert fn["gold_items_total"] == 1
    assert fn["gold_passed"] == 1
    assert fn["user_delivered_rows"] == 1

    # Check markdown output
    md = reporter.generate_markdown(m)
    assert "BÁO CÁO GIÁM SÁT TOÀN DIỆN HỆ THỐNG NEWS-SCAPE" in md
    assert "2026-08-18" in md
    assert "cafef.vn" in md
    assert "vietstock.vn" in md
    assert "AnPT" in md

    # Check save markdown
    saved = reporter.save_report_markdown(m, out_dir=tmp_path / "reports")
    assert saved.exists()
    assert saved.name == "report-2026-08-18.md"

    # Check terminal print does not crash
    reporter.print_terminal_summary(m)
