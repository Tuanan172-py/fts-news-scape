"""Kiểm thử cổng chạy tay: đăng ký đợt, khoá provider, va chạm, giữ chỗ và bench."""

from __future__ import annotations

import os

import pytest

from src.ops import manual as _manual
from src.ops import trace as tracing
from src.ops.config import resolve_paths
from src.ops.store import OpsStore

TRACE_KEYS = (tracing.ENV_DB, tracing.ENV_WAVE, tracing.ENV_PARENT)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MONOCLE_DATA_DIR", str(tmp_path / "data"))
    for k in TRACE_KEYS:
        monkeypatch.delenv(k, raising=False)
    paths = resolve_paths()
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    yield OpsStore(paths.ops_db, log_dir=paths.log_dir)
    for k in TRACE_KEYS:
        os.environ.pop(k, None)


class manual:  # noqa: N801 — mỗi lần gọi mô phỏng một tiến trình mới, chưa có biến vết
    @staticmethod
    def begin(*a, **kw):
        for k in TRACE_KEYS:
            os.environ.pop(k, None)
        return _manual.begin(*a, **kw)


def kinds(store):
    return [e["kind"] for e in store.events(limit=50)]


def test_new_manual_wave_is_registered_with_trace_env(store):
    gate = manual.begin("W1", "backlog", "prepare", "openrouter", target_date="2026-09-20")
    assert gate.refusal is None
    row = store.wave("W1")
    assert row["trigger"] == "backlog" and row["provider"] == "openrouter"
    assert row["target_date"] == "2026-09-20" and "wave.manual_opened" in kinds(store)
    assert os.environ[tracing.ENV_DB] == str(store.path) and os.environ[tracing.ENV_WAVE] == "W1"


def test_default_mode_is_adhoc(store):
    manual.begin("W1", None, "prepare", "agy")
    assert store.wave("W1")["trigger"] == "adhoc"


def test_provider_is_locked_per_wave_and_force_is_logged(store):
    store.upsert_wave("W1", status="FAILED", trigger="T1", provider="agy", level="L1")
    gate = manual.begin("W1", None, "repair", "openrouter")
    assert gate.refusal and "khoá provider agy" in gate.refusal
    assert store.wave("W1")["provider"] == "agy"
    forced = manual.begin("W1", None, "repair", "openrouter", force=True)
    assert forced.refusal is None and "provider.override" in kinds(store)


def test_same_provider_repair_of_failed_daemon_wave_is_allowed(store):
    store.upsert_wave("W1", status="FAILED", trigger="T1", provider="agy", level="L1")
    assert manual.begin("W1", None, "repair", "agy").refusal is None


def test_lanes_run_in_parallel_and_block_only_within_the_same_lane(store):
    store.upsert_wave("W0", status="ANALYZING", trigger="T1", provider="agy", level="L1")
    assert manual.begin("WB1", "backlog", "prepare", "openrouter").refusal is None
    assert manual.begin("WB2", "backlog", "prepare", "openrouter").refusal is not None
    assert manual.begin("WX", "bench", "prepare", "openrouter").refusal is None
    assert manual.begin("WX2", "bench", "prepare", "openrouter").refusal is not None
    assert manual.begin("WB2", "backlog", "prepare", "openrouter", force=True).refusal is None


def test_active_waves_filter_by_lane(store):
    store.upsert_wave("A", status="ANALYZING", trigger="T2", provider="agy", level="L1")
    store.upsert_wave("B", status="ANALYZING", trigger="backlog", provider="openrouter", level="manual")
    store.upsert_wave("C", status="PARKED", trigger="bench", provider="openrouter", level="manual")
    assert [w["wave_id"] for w in store.active_waves("auto")] == ["A"]
    assert [w["wave_id"] for w in store.active_waves("backlog")] == ["B"]
    assert store.active_wave("bench") is None
    assert {w["wave_id"] for w in store.active_waves()} == {"A", "B"}


def test_daemon_owned_active_wave_cannot_be_touched(store):
    store.upsert_wave("W1", status="ANALYZING", trigger="T1", provider="agy", level="L1")
    gate = manual.begin("W1", None, "analyze", "agy")
    assert gate.refusal


def test_bench_has_no_reservation_no_exclusion_and_refuses_finish(store):
    store.upsert_wave("W0", status="PARKED", trigger="T1", provider="agy", level="L1")
    store.record_wave_articles("W0", ["held"])
    bench = manual.begin("WB", "bench", "prepare", "openrouter")
    assert bench.refusal is None and bench.exclude_ids() == set()
    bench.finish(0, lambda: ["held", "x"])
    assert store.reserved_article_ids() == {"held"}
    assert store.wave("WB")["status"] == "DONE"
    assert manual.begin("WB", "bench", "finish", "openrouter").refusal
    assert bench.bench_dir.name == "WB"


def test_backlog_reserves_excludes_others_and_keeps_exhausted_selectable(store):
    store.upsert_wave("W0", status="PARKED", trigger="T1", provider="agy", level="L1")
    store.record_wave_articles("W0", ["held"])
    store.upsert_wave("W9", status="DONE", trigger="T1", provider="agy", level="L1")
    store.record_wave_articles("W9", ["tired"])
    store.record_wave_articles("W8", ["tired"])  # đủ hai lượt: daemon coi là cạn
    gate = manual.begin("WL", "backlog", "prepare", "openrouter")
    assert gate.exclude_ids() == {"held"}
    gate.finish(0, lambda: ["a", "tired"])
    assert {"a", "tired"} <= store.reserved_article_ids()
    assert store.wave("WL")["status"] == "PARKED"


def test_repair_phase_counts_round_and_attempts_then_finish_closes(store):
    gate = manual.begin("WL", "backlog", "repair", "openrouter")
    gate.finish(0, lambda: ["m1", "m2"])
    assert store.get_state("repair_rounds:WL") == "1"
    assert store.exhausted_article_ids(1) == {"m1", "m2"}
    done = manual.begin("WL", "backlog", "finish", "openrouter")
    done.finish(0)
    assert store.wave("WL")["status"] == "DONE"
    failed = manual.begin("WL", "backlog", "finish", "openrouter")
    failed.finish(1)
    assert store.wave("WL")["status"] == "FAILED"


def test_daemon_launched_call_is_not_gated(store, monkeypatch):
    monkeypatch.setenv(tracing.ENV_DB, str(store.path))
    gate = _manual.begin("W1", None, "analyze", "openrouter")
    assert gate.refusal is None and gate.store is None
    assert store.wave("W1") is None


def test_openrouter_run_batch_writes_agent_span(store, tmp_path, monkeypatch):
    from src.agent.openrouter_runner import OpenRouterExecutionResult, OpenRouterRunner

    gate = manual.begin("WS", "adhoc", "analyze", "openrouter")
    assert gate.refusal is None
    runner = OpenRouterRunner.__new__(OpenRouterRunner)
    runner.model = "test/model"
    monkeypatch.setattr(OpenRouterRunner, "_run_batch_impl",
                        lambda self, b, t, o, m, f: OpenRouterExecutionResult(
                            ok=True, batch_id=b, status="PARTIAL", records=[{"i": 0}],
                            usage={"input_tokens": 5}, latency_seconds=1.5))
    res = runner.run_batch("article_WS_01", tmp_path / "t.json", tmp_path)
    assert res.status == "PARTIAL"
    with store.conn() as c:
        row = c.execute("SELECT status, actor_id, parent_id FROM ops_spans "
                        "WHERE trace_id='WS' AND kind='agent'").fetchone()
    assert row["status"] == "partial" and row["actor_id"] == "article-processor"
    assert row["parent_id"] == "WS.manual.analyze"
