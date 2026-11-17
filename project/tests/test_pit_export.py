"""Kiểm thử hợp đồng xuất point-in-time ADR-0033: cột thời gian, cụm câu chuyện và khối độ tươi của manifest."""

from __future__ import annotations

import io
import json
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.lakehouse.consolidator import consolidate_dropzone
from src.lakehouse.ingest import LAKEHOUSE_ARTICLE_SCHEMA, PIT_COLUMNS, published_precision
from src.lakehouse.storage import LocalOneDriveStorageAdapter
from src.research_db import production
from tests.test_research_production import DAY, _publish, env  # noqa: F401  (fixture)


@pytest.mark.parametrize("raw, want", [
    (None, "missing"), ("", "missing"), ("2026-11-09", "date"),
    ("2026-11-09T00:00:00+07:00", "date"), ("2026-11-09 00:00", "date"),
    ("2026-11-09T09:15:00+07:00", "datetime"), ("2026-11-09T00:01:00+07:00", "datetime"),
])
def test_published_precision(raw, want):
    assert published_precision(raw) == want


def test_schema_appends_pit_columns_at_the_end():
    names = [f.name for f in LAKEHOUSE_ARTICLE_SCHEMA]
    assert tuple(names[-len(PIT_COLUMNS):]) == PIT_COLUMNS
    assert names[:2] == ["article_id", "url"]


def _partition_rows(env) -> list[dict]:
    part = env["target"] / production.partition_path(DAY)
    return pq.read_table(part).to_pylist()


def _add_cluster(db, members: list[tuple[str, str]], cluster_id: str, n_sources: int) -> None:
    conn = sqlite3.connect(db)
    with conn:
        conn.execute("INSERT OR REPLACE INTO story_clusters (cluster_id, canonical_id, n_members, "
                     "n_sources) VALUES (?, ?, ?, ?)", (cluster_id, members[0][0], len(members),
                                                        n_sources))
        for aid, role in members:
            conn.execute("INSERT OR REPLACE INTO cluster_members (article_id, cluster_id, role, "
                         "method) VALUES (?, ?, ?, 'shingle')", (aid, cluster_id, role))
    conn.close()


def test_partition_carries_pit_and_story_columns(env):
    ids = env["ids"]
    _add_cluster(env["db"], [(ids["ok"], "canonical"), (ids["inh"], "copy")], "c-1", 3)
    out = _publish(env)
    assert out.status == "published", out.message
    rows = {r["article_id"]: r for r in _partition_rows(env)}
    ok = rows[ids["ok"]]
    assert ok["first_seen_at"] == "2026-11-09T09:00:00+07:00"
    assert ok["published_at_precision"] == "datetime"
    assert ok["analyzed_at"]
    assert (ok["story_id"], ok["story_role"], ok["story_n_sources"]) == ("c-1", "canonical", 3)
    assert rows[ids["inh"]]["story_role"] == "copy"


def test_story_change_rewrites_the_day(env):
    ids = env["ids"]
    _publish(env)
    assert _publish(env).status == "unchanged"
    _add_cluster(env["db"], [(ids["ok"], "canonical")], "c-2", 5)
    out = _publish(env)
    assert out.status == "published" and out.sync["stories_changed"] == 1
    rows = {r["article_id"]: r for r in _partition_rows(env)}
    assert rows[ids["ok"]]["story_n_sources"] == 5
    assert _publish(env).status == "unchanged"


def test_manifest_reports_schema_and_freshness(env):
    _publish(env)
    man = json.loads((env["target"] / production.MANIFEST).read_text(encoding="utf-8"))
    assert man["obt_schema"] == production.OBT_SCHEMA
    assert man["columns"][-1] == "story_n_sources"
    fr = man["freshness"]
    assert fr["newest_first_seen_at"] == "2026-11-09T09:00:00+07:00"
    assert fr["date_only_share"] == 0.0
    assert isinstance(fr["unpublished_captured"], int)
    assert production.verify(env["target"])["ok"]


def test_consolidator_fills_null_for_old_fragments(tmp_path):
    storage = LocalOneDriveStorageAdapter(root_dir=tmp_path)
    old_schema = pa.schema([f for f in LAKEHOUSE_ARTICLE_SCHEMA if f.name not in PIT_COLUMNS])
    row = {f.name: ([] if pa.types.is_list(f.type) else "x") for f in old_schema}
    row.update(article_id="a1", published_at="2026-10-08T07:00:00+07:00",
               updated_at="2026-10-08T08:00:00+07:00")
    buf = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([row], schema=old_schema), buf)
    storage.write_atomic("dropzone/2026/10/08/part-20261008-old-b1.parquet", buf.getvalue())
    res = consolidate_dropzone("2026-10-08", storage)
    table = pq.read_table(storage.get_local_path(res.partition_file))
    assert [f.name for f in table.schema] == [f.name for f in LAKEHOUSE_ARTICLE_SCHEMA]
    assert table.to_pylist()[0]["story_id"] is None


def _yield_db(tmp_path, per_day: dict[str, int], today: int):
    """Tạo DB nhỏ có bảng articles với số bài theo nguồn trong khung 08:30-10:30 của 10 ngày làm việc."""
    from datetime import datetime, timedelta
    from src.core.models import VN_TZ
    db = tmp_path / "y.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE articles (source_domain TEXT, fetched_at TEXT)")
    now = datetime(2026, 11, 17, 10, 30, tzinfo=VN_TZ)
    d, n = now, 0
    while n < 10:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n += 1
            for dom, k in per_day.items():
                for i in range(k):
                    conn.execute("INSERT INTO articles VALUES (?, ?)", (dom, (d - timedelta(minutes=5 + i)).isoformat()))
    for i in range(today):
        conn.execute("INSERT INTO articles VALUES ('a.vn', ?)", ((now - timedelta(minutes=5 + i)).isoformat(),))
    conn.commit()
    conn.close()
    return db, now


def test_probe_yield_flags_silent_source(tmp_path):
    from src.ops.probes import probe_yield
    db, now = _yield_db(tmp_path, {"a.vn": 20}, today=0)
    r = probe_yield(db, {}, now=now)
    assert not r.ok and "a.vn" in r.message


def test_probe_yield_accepts_normal_yield_and_weekend(tmp_path):
    from datetime import timedelta
    from src.ops.probes import probe_yield
    db, now = _yield_db(tmp_path, {"a.vn": 20}, today=18)
    assert probe_yield(db, {}, now=now).ok
    assert probe_yield(db, {}, now=now - timedelta(days=3)).ok  # Saturday


def test_urgent_digest_groups_by_story_and_moves_watermark(env):
    from datetime import datetime
    from src.core.models import VN_TZ
    ids = env["ids"]
    env["store"].insert_agent_output({"article_id": ids["ok"], "raw_sha256": "s-ok-urgent",
                                      "output_json": _agent(ids["ok"], time_sensitivity="urgent"),
                                      "dod_pass": 1, "agent_provider": "agy",
                                      "created_at": "2026-11-09T09:30:00+07:00"})
    _add_cluster(env["db"], [(ids["ok"], "canonical"), (ids["inh"], "copy")], "c-9", 4)
    _publish(env)
    now = datetime(2026, 11, 9, 12, 0, tzinfo=VN_TZ)
    text, mark = production.urgent_digest(None, now=now)
    assert text and text.count("\n- ") == 1 and "4 nguồn" in text and "[FPT]" in text
    again, mark2 = production.urgent_digest(mark, now=now)
    assert again is None and mark2 == mark
    late, _ = production.urgent_digest(None, now=datetime(2026, 11, 10, 9, 0, tzinfo=VN_TZ))
    assert late is None


def _agent(aid: str, **over) -> str:
    from tests.test_research_production import _agent_doc
    return _agent_doc(aid, **over)


def test_capture_channels_paused_source_is_reported_not_red(tmp_path):
    """CAP-1: an operator-paused reference channel does not keep the probe red."""
    import sqlite3
    from datetime import datetime

    from src.ops.probes import probe_capture_channels
    from src.pipeline.reconcile import REFERENCE_DOMAINS

    db = tmp_path / "m.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE capture_coverage (source_domain TEXT, checked_at TEXT)")
    conn.execute("CREATE TABLE pipeline_state (key TEXT, value TEXT)")
    for d in REFERENCE_DOMAINS:
        if d != "baodautu.vn":
            conn.execute("INSERT INTO capture_coverage VALUES (?, '2026-11-17T18:00:00+07:00')", (d,))
    conn.commit()
    conn.close()
    now = datetime.fromisoformat("2026-11-17T19:00:00+07:00")
    assert not probe_capture_channels(db, now=now).ok
    res = probe_capture_channels(db, now=now, paused={"baodautu.vn": "sitemap hỏng"})
    assert res.ok and "tạm dừng baodautu.vn" in res.message
