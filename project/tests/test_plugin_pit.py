"""Kiểm thử lớp point-in-time của plugin (ADR-0033): available_at, mốc cắt, lịch nghỉ HOSE, story_key và cache cục bộ."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PLUGIN_TOOLS_DIR = Path(__file__).resolve().parents[2] / "plugins" / "fpts-market-intel" / "tools"
sys.path.insert(0, str(PLUGIN_TOOLS_DIR))

import lakehouse_pit  # noqa: E402
from lakehouse_client import NewsLakehouseClient, normalize_cutoff  # noqa: E402

ROWS = [
    # article_id, published_at, first_seen_at, story_id, title
    ("a1", "2026-04-29T15:10:00+07:00", "2026-04-29T15:12:00+07:00", "s-1", "Tin sau ATC trước nghỉ lễ"),
    ("a2", "2026-04-29T15:20:00+07:00", "2026-04-29T15:25:00+07:00", "s-1", "Bản đăng lại khác tiêu đề"),
    ("a3", "2026-05-04T09:05:00+07:00", "2026-05-04T11:40:00+07:00", None, "Tin cào trễ"),
    ("a4", "2026-05-04T09:30:00+07:00", None, None, "Phân vùng cũ không có first_seen"),
]


@pytest.fixture
def lake(tmp_path: Path) -> Path:
    """Tạo Lakehouse giả lập obt/2 với một phân vùng."""
    root = tmp_path / "news"
    part = root / "parquet" / "articles" / "year=2026" / "month=05"
    part.mkdir(parents=True)
    (root / "_manifest").mkdir()
    (root / "_manifest" / "latest.json").write_text(
        '{"day": "2026-05-04", "updated_at": "2026-05-04T12:00:00+07:00", "obt_schema": "obt/2",'
        ' "freshness": {"newest_first_seen_at": "2026-05-04T11:40:00+07:00"}}', encoding="utf-8")
    n = len(ROWS)
    table = pa.table({
        "article_id": [r[0] for r in ROWS], "published_at": [r[1] for r in ROWS],
        "first_seen_at": [r[2] for r in ROWS], "story_id": [r[3] for r in ROWS],
        "title": [r[4] for r in ROWS], "url": [f"https://x.vn/{r[0]}" for r in ROWS],
        "source_domain": ["x.vn"] * n, "summary": ["s"] * n, "implication": ["i"] * n,
        "sentiment": ["positive"] * n, "time_sensitivity": ["today"] * n,
        "entities": pa.array([["TICKER:VCB [TICKER|primary|BOTH]"]] * n, pa.list_(pa.string())),
        "gold_status": ["GOLD"] * n,
    })
    pq.write_table(table, part / "part-20260504.parquet")
    return root


def _client(root: Path, **kw) -> NewsLakehouseClient:
    return NewsLakehouseClient(root=root, master_db=None, **kw)


def test_next_trading_rows_skip_weekend_and_holidays():
    rows = dict(lakehouse_pit.next_trading_rows({date(2026, 4, 30), date(2026, 5, 1)},
                                                start=date(2026, 4, 29), end=date(2026, 5, 5)))
    assert rows[date(2026, 4, 30)] == date(2026, 5, 4)
    assert rows[date(2026, 5, 2)] == date(2026, 5, 4)
    assert rows[date(2026, 4, 29)] == date(2026, 4, 29)


def test_trade_date_uses_holiday_calendar(lake):
    c = _client(lake)
    got = {r["article_id"]: r["trade_date"] for r in c._rows(
        "SELECT article_id, trade_date FROM articles")}
    # 29/4 sau 14:45 -> 30/4 và 1/5 nghỉ lễ, 2-3/5 cuối tuần -> 4/5.
    assert got["a1"] == date(2026, 5, 4)
    assert got["a3"] == date(2026, 5, 4)


def test_available_at_and_cutoff(lake):
    c = _client(lake)
    rows = {r["article_id"]: r for r in c._rows(
        "SELECT article_id, available_at, capture_lag_min, story_key FROM articles")}
    assert rows["a3"]["capture_lag_min"] == 155.0
    assert str(rows["a4"]["available_at"]).startswith("2026-05-04 09:30")
    assert rows["a1"]["story_key"] == rows["a2"]["story_key"] == "s-1"
    cut = _client(lake, cutoff="2026-05-04T10:00")
    ids = {r["article_id"] for r in cut._rows("SELECT article_id FROM articles")}
    # a3 được đăng 09:05 nhưng tới 11:40 mới cào được, nên chưa có ở mốc 10:00.
    assert ids == {"a1", "a2", "a4"}


def test_normalize_cutoff_defaults_to_ict():
    assert normalize_cutoff("2026-05-04T10:00") == "2026-05-04T10:00:00+07:00"
    assert normalize_cutoff(None) is None


def test_status_reports_pit_coverage_and_calendar(lake):
    st = _client(lake).status()
    assert st["obt_schema"] == "obt/2" and st["freshness"]["newest_first_seen_at"]
    assert st["pit_coverage"]["first_seen_share"] == 0.75
    assert st["pit_coverage"]["story_share"] == 0.5
    assert any("2026" in w for w in st["warnings"])


def test_cache_miss_then_hit_and_invalidation(lake, tmp_path, monkeypatch):
    monkeypatch.setenv("NEWS_LAKEHOUSE_CACHE_DIR", str(tmp_path / "cache"))
    first = _client(lake, cache=True)
    assert not first.cache_hit
    n = first._rows("SELECT count(*) AS n FROM articles")[0]["n"]
    first.con.close()
    second = _client(lake, cache=True)
    assert second.cache_hit
    assert second._rows("SELECT count(*) AS n FROM articles")[0]["n"] == n
    assert second._rows("SELECT count(*) AS n FROM article_entities")[0]["n"] == n
    second.con.close()
    other_cutoff = _client(lake, cache=True, cutoff="2026-05-04T10:00")
    assert not other_cutoff.cache_hit
    other_cutoff.con.close()
    # A cutoff session must not evict the live cache.
    assert _client(lake, cache=True).cache_hit
    assert _client(lake, cache=True, cutoff="2026-05-04T10:00").cache_hit
