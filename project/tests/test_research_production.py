"""Kiểm thử production FRA - Data/news: cổng kiểm nghiệm, phân vùng ngày, tự chữa, lịch khung giờ và tương thích plugin."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.core.models import VN_TZ, Article
from src.db.store import ArticleStore
from src.lakehouse.storage import LocalOneDriveStorageAdapter
from src.ops.probes import probe_publish
from src.research_db import master, production, schedule

DAY = "2026-11-09"
TS = f"{DAY}T09:00:00+07:00"
PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "fpts-market-intel" / "tools" / "lakehouse_client.py"


def _agent_doc(aid: str, **over) -> str:
    """Tạo output_json lớp nội dung hợp lệ."""
    doc = {"article_id": aid, "summary": "Tóm tắt bài.", "key_points": ["Ý một"],
           "implication": "Hàm ý tới dòng tiền của cổ phiếu trong ngắn hạn là tích cực.",
           "sentiment": "positive", "time_sensitivity": "today",
           "citations": ["Đoạn trích nguyên văn đủ dài để hợp lệ."]}
    doc.update(over)
    return json.dumps(doc, ensure_ascii=False)


def _l1_doc(aid: str) -> str:
    """Tạo output_json lớp thực thể hợp lệ."""
    return json.dumps({"article_id": aid, "entities": [
        {"surface": "FPT", "entity_id": "TICKER:FPT", "type": "TICKER", "method": "exact_code",
         "in_list": True, "confidence": 0.99}]})


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Dựng DB vận hành nhỏ với các trường hợp cổng và một thư mục production 'news' tạm."""
    data = tmp_path / "data"
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(data))
    monkeypatch.delenv(production.TARGET_ENV, raising=False)
    monkeypatch.setattr(master, "DEFAULT_MAX_RETRACT_RATIO", 1.0)
    db = data / "monocle.db"
    store = ArticleStore(db_path=db)
    keys = ("ok", "codefirst", "nodod", "bad", "inh", "agentonly", "nextday")
    for key in keys:
        ts = "2026-11-10T08:00:00+07:00" if key == "nextday" else TS
        store.insert(Article(url=f"https://a.vn/{key}", title=f"FPT tin {key}", source_domain="a.vn",
                             content_text="nội dung", fetched_at=ts, published_at=ts,
                             symbols=["FPT"]))
    conn = sqlite3.connect(db)
    ids = {r[0].rsplit("/", 1)[1]: r[1] for r in conn.execute("SELECT url, url_title_hash FROM articles")}
    conn.close()

    def both(key, ag_dod=1, l1_dod=1, l1_source="agent", **over):
        aid = ids[key]
        store.insert_agent_output({"article_id": aid, "raw_sha256": f"s-{key}",
                                   "output_json": _agent_doc(aid, **over), "dod_pass": ag_dod,
                                   "agent_provider": "agy", "created_at": TS})
        store.insert_l1_output({"article_id": aid, "output_json": _l1_doc(aid), "dod_pass": l1_dod,
                                "created_at": TS, "l1_source": l1_source})

    both("ok")
    both("codefirst", l1_source="code_first")
    both("nodod", ag_dod=0)
    both("bad", summary="")
    both("inh", l1_source="inherited", inherited_from=ids["ok"])
    store.insert_agent_output({"article_id": ids["agentonly"], "raw_sha256": "s",
                               "output_json": _agent_doc(ids["agentonly"]), "dod_pass": 1,
                               "created_at": TS})
    return {"db": db, "ids": ids, "store": store, "both": both,
            "target": tmp_path / "FRA - Data" / "news"}


def _publish(env, **kw):
    """Gọi publish với đích tạm."""
    kw.setdefault("target", env["target"])
    return production.publish(env["db"], **kw)


def _files(root: Path) -> list[str]:
    """Liệt kê tệp dưới một thư mục, đường dẫn tương đối."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_gate_admits_only_fully_processed(env):
    res = master.sync_master(env["db"])
    assert res.candidates == 3 and res.upserted == 2 and res.rejected == 1
    again = master.sync_master(env["db"])
    assert again.upserted == 0 and again.held == 1 and again.rejects_file is None


def test_production_folder_holds_data_only(env):
    out = _publish(env)
    assert out.status == "published", out.message
    assert _files(env["target"]) == ["_manifest/latest.json",
                                     "parquet/articles/year=2026/month=11/part-20261109.parquet"]
    man = json.loads((env["target"] / production.MANIFEST).read_text(encoding="utf-8"))
    assert man["total_unique_articles"] == 2 and man["files"][0]["rows"] == 2
    assert production.verify(env["target"])["ok"]


def test_unchanged_publish_touches_nothing(env):
    _publish(env)
    part = env["target"] / production.partition_path(DAY)
    before = (part.stat().st_mtime_ns, (env["target"] / production.MANIFEST).stat().st_mtime_ns)
    out = _publish(env)
    assert out.status == "unchanged" and not out.written
    assert before == (part.stat().st_mtime_ns, (env["target"] / production.MANIFEST).stat().st_mtime_ns)


def test_only_changed_day_is_rewritten(env):
    _publish(env)
    env["both"]("nextday")
    out = _publish(env)
    assert out.written == [production.partition_path("2026-11-10")]
    assert out.articles == 3


def test_retracted_day_partition_is_removed(env):
    env["both"]("nextday")
    _publish(env)
    conn = sqlite3.connect(env["db"])
    conn.execute("UPDATE agent_outputs SET dod_pass = 0 WHERE article_id = ?", (env["ids"]["nextday"],))
    conn.commit()
    conn.close()
    out = _publish(env)
    assert out.deleted == [production.partition_path("2026-11-10")]
    assert production.verify(env["target"])["ok"]


def test_retraction_guard_blocks_mass_removal(env, monkeypatch):
    _publish(env)
    monkeypatch.setattr(master, "DEFAULT_MAX_RETRACT_RATIO", 0.05)
    conn = sqlite3.connect(env["db"])
    conn.execute("UPDATE agent_outputs SET dod_pass = 0")
    conn.commit()
    conn.close()
    out = _publish(env)
    assert out.status == "failed" and "RetractionGuardError" in out.message
    assert (env["target"] / production.partition_path(DAY)).is_file()


def test_deleted_partition_heals_on_next_publish(env):
    _publish(env)
    part = env["target"] / production.partition_path(DAY)
    part.unlink()
    out = _publish(env)
    assert out.written == [production.partition_path(DAY)] and part.is_file()


def test_target_rules(env, tmp_path):
    with pytest.raises(production.PublishError):
        production.resolve_target(None)
    with pytest.raises(production.PublishError):
        production.resolve_target(tmp_path / "other")
    assert _publish(env, target=tmp_path / "data" / "news").status == "failed"


def test_plugin_reads_production_unchanged(env):
    duckdb = pytest.importorskip("duckdb")
    assert duckdb
    _publish(env)
    spec = importlib.util.spec_from_file_location("lakehouse_client", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    client = mod.NewsLakehouseClient(root=env["target"])
    assert client.data_range()["n_articles"] == 2
    ents = client._rows("SELECT DISTINCT entity_id FROM article_entities")
    assert {"entity_id": "TICKER:FPT"} in ents


def test_strict_adapter_never_writes_side_file(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    root = tmp_path / "FRA - Data" / "news"
    st = LocalOneDriveStorageAdapter(root, allow_official=True, strict=True)
    st.write_atomic("parquet/a.parquet", b"one")
    with open(root / "parquet" / "a.parquet", "rb"):
        if os.name == "nt":
            with pytest.raises(PermissionError):
                st.write_atomic("parquet/a.parquet", b"two")
    assert _files(root) == ["parquet/a.parquet"]
    with pytest.raises(PermissionError):
        LocalOneDriveStorageAdapter(tmp_path / "FRA - Data" / "x")


def test_research_probe_creates_no_files(tmp_path):
    root = tmp_path / "news"
    (root / "_manifest").mkdir(parents=True)
    (root / "_manifest" / "latest.json").write_text(json.dumps({"updated_at": datetime.now(VN_TZ).isoformat()}))
    res = probe_publish(root, {"stale_hours": 12}, onedrive_running=lambda: True,
                        name="research", write_test=False)
    assert res.ok and res.name == "research"
    assert _files(root) == ["_manifest/latest.json"]


CFG = {"slots": [{"name": "sang-som", "at": "07:50"}, {"name": "truoc-ato", "at": "08:45"},
                 {"name": "sau-phien", "at": "15:50"}],
       "wait_wave_max_minutes": 15, "catchup_lookback_hours": 24,
       "express": {"enabled": True, "min_interval_minutes": 30}}


def _at(hh: int, mm: int, day: int = 10) -> datetime:
    """Tạo thời điểm giờ Việt Nam ngày 2026-11-<day>."""
    return datetime(2026, 11, day, hh, mm, tzinfo=VN_TZ)


def _decide(now, done=(), wave=False, last=None, urgent=0):
    """Gọi schedule.decide với trạng thái giả."""
    return schedule.decide(now, CFG, is_done=lambda k: k in done, wave_active=wave,
                           last_publish_at=last, urgent_since=lambda t: urgent)


def test_slot_fires_once_and_waits_for_running_wave():
    d = _decide(_at(7, 51), done={f"research:slot:2026-11-09:{n}" for n in ("sang-som", "truoc-ato", "sau-phien")})
    assert d.reason == "slot:sang-som" and d.slot_keys == ["research:slot:2026-11-10:sang-som"]
    yesterday = {f"research:slot:2026-11-09:{n}" for n in ("sang-som", "truoc-ato", "sau-phien")}
    assert _decide(_at(7, 55), done=yesterday, wave=True) is None
    assert _decide(_at(8, 6), done=yesterday, wave=True).reason == "slot:sang-som"
    assert _decide(_at(8, 0), done=yesterday | set(d.slot_keys)) is None


def test_missed_slots_collapse_into_one_catchup():
    d = _decide(_at(9, 30), done={"research:slot:2026-11-09:sang-som", "research:slot:2026-11-09:truoc-ato"})
    assert d.reason == "catchup:truoc-ato+2"
    assert set(d.slot_keys) == {"research:slot:2026-11-09:sau-phien", "research:slot:2026-11-10:sang-som",
                                "research:slot:2026-11-10:truoc-ato"}


def test_express_needs_urgent_news_and_interval():
    done = {f"research:slot:2026-11-{d}:{n}" for d in ("09", "10") for n in ("sang-som", "truoc-ato")}
    done.add("research:slot:2026-11-09:sau-phien")
    assert _decide(_at(10, 0), done, last=_at(9, 50), urgent=3) is None
    assert _decide(_at(10, 30), done, last=_at(9, 50), urgent=0) is None
    assert _decide(_at(10, 30), done, last=_at(9, 50), urgent=2).reason == "express"


def test_catalog_is_published_with_its_sha256(env):
    """The live entity catalog travels with the partitions, its SHA-256 in the manifest (US-057)."""
    import hashlib
    cat = Path(os.environ["MONOCLE_DATA_DIR"]) / "entities" / "entities.json"
    cat.parent.mkdir(parents=True, exist_ok=True)
    cat.write_bytes(b'{"entities": []}')
    out = _publish(env)
    assert out.status == "published", out.message
    assert production.CATALOG in _files(env["target"])
    assert (env["target"] / production.CATALOG).read_bytes() == cat.read_bytes()
    man = json.loads((env["target"] / production.MANIFEST).read_text(encoding="utf-8"))
    assert man["catalog"]["sha256"] == hashlib.sha256(cat.read_bytes()).hexdigest()
    assert man["catalog"]["path"] == production.CATALOG

    manifest_mtime = (env["target"] / production.MANIFEST).stat().st_mtime_ns
    assert _publish(env).status == "unchanged"
    assert (env["target"] / production.MANIFEST).stat().st_mtime_ns == manifest_mtime

    cat.write_bytes(b'{"entities": [1]}')
    assert _publish(env).status == "published"
    man = json.loads((env["target"] / production.MANIFEST).read_text(encoding="utf-8"))
    assert man["catalog"]["sha256"] == hashlib.sha256(b'{"entities": [1]}').hexdigest()


def test_no_catalog_leaves_the_manifest_block_empty(env):
    out = _publish(env)
    assert out.status == "published", out.message
    man = json.loads((env["target"] / production.MANIFEST).read_text(encoding="utf-8"))
    assert man["catalog"] is None
