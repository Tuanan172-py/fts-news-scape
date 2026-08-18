"""P4 — orchestrator: output mode + user disabled → 0 output."""
from __future__ import annotations

import _userkit as k

from src.pipeline.user_workflow import run


def _setup_input(tmp_path, manifest: str):
    inp = tmp_path / "input"
    (inp / "AnPT").mkdir(parents=True)
    (inp / "manifest.yaml").write_text(manifest, encoding="utf-8")
    return inp


def test_workflow_writes_output(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    inp = _setup_input(tmp_path, "users:\n  AnPT: true\n")

    res = run(input_root=inp, output_root=tmp_path / "out", store=store, registry=reg,
              do_compile=False, date="2026-08-18")
    assert res["counts"] == {"AnPT": 1} and res["total"] == 1


def test_workflow_disabled_user(tmp_path):
    store = k.make_store(tmp_path)
    reg = k.make_registry({"AnPT": {"TICKER:HPG"}})
    k.seed_article(store, "a1"); k.seed_l1(store, "a1", ["TICKER:HPG"]); k.seed_agent(store, "a1")
    inp = _setup_input(tmp_path, "users:\n  AnPT: false\n")     # tắt AnPT

    res = run(input_root=inp, output_root=tmp_path / "out", store=store, registry=reg,
              do_compile=False, date="2026-08-18")
    assert res["counts"] == {} and res["total"] == 0
    assert not (tmp_path / "out" / "AnPT").exists()
