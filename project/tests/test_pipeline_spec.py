"""Kiểm thử chống lệch giữa khối ops_spec, registry và mã vận hành."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import yaml

from src.ops import pipeline_spec, supervision, trace
from src.ops.wave_flow import WaveOps

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "scripts"))
import article_run  # noqa: E402

REGISTRY = yaml.safe_load((PROJECT.parent / ".agents" / "registry.yaml").read_text(encoding="utf-8"))
AGENT_IDS = {a["id"] for a in REGISTRY["agents"]}


def test_code_constants_come_from_spec():
    assert supervision.MAIN_CHAIN == pipeline_spec.main_chain()
    assert article_run.FINISH_STEPS == pipeline_spec.finish_steps()
    assert trace.SCRIPT_ACTORS == pipeline_spec.script_actors()


def test_every_actor_exists_in_registry():
    named = set(pipeline_spec.main_chain()) | set(pipeline_spec.script_actors().values())
    assert named - AGENT_IDS == set()


def test_every_script_in_actor_table_exists():
    missing = [s for s in pipeline_spec.script_actors() if not (PROJECT / "scripts" / s).exists()]
    assert missing == []


def test_finish_steps_are_accepted_by_parse_steps():
    steps = list(pipeline_spec.finish_steps())
    assert article_run.parse_steps(None) == steps
    assert article_run.parse_steps(",".join(reversed(steps))) == steps


def test_wave_ops_match_protocol():
    declared = {n for n, _ in inspect.getmembers(WaveOps, inspect.isfunction) if not n.startswith("_")}
    assert declared == set(pipeline_spec.wave_ops())


def test_pipeline_stages_reference_registry_agents():
    data = yaml.safe_load(pipeline_spec.PIPELINE_PATH.read_text(encoding="utf-8"))
    refs = {s["agent"] for s in data["stages"]}
    refs |= {s["agent"] for key in ("governance_loop", "ops_loop") for s in data.get(key, [])}
    assert refs - AGENT_IDS == set()
