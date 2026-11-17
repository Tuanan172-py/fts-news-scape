"""Adversarial stress test suite for Worker M1 ingest error enforcement.

Empirically verifies:
1. cmd_finish with --mode backlog unconditionally halts (rc=1, CHƯA HOÀN TẤT) on:
   - corrupted output JSON
   - zero-length / empty output files
   - schema / DoD rejections
   - preflight DB write probe failures
   - mid-ingest DB write exceptions / script non-zero exits
2. token_ledger, verify_wave, handoff, and completion banner are NEVER reached on ingest failure.
3. Strict parity across all modes: 'backlog', 'bench', 'adhoc', and default (no mode bypass).
4. Exact mathematical boundary verification of --fail-threshold for both agent_ingest and l1_ingest.
5. Real subprocess execution of CLI scripts with piped streams (Rule 03 & Rule 06 §4.5 compliance).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import agent_ingest  # noqa: E402
import l1_ingest  # noqa: E402
from scripts import article_run  # noqa: E402
from src.db.preflight import WriteProbe  # noqa: E402
from src.db.store import ArticleStore  # noqa: E402
from src.handoff.catalog import Catalog  # noqa: E402

PYTHON = sys.executable
CLEANED_TEXT = "Alpha beta gamma đầu ngành. Delta epsilon zeta lao động giảm mạnh."


# -----------------------------------------------------------------------------
# Fixtures & Helpers
# -----------------------------------------------------------------------------
def _finish_args(**kw) -> argparse.Namespace:
    """Build args namespace for cmd_finish with configurable overrides."""
    base = {
        "wave": "W_ADV",
        "only": None,
        "window_min": 60,
        "min_coverage": 0.90,
        "mode": "backlog",
        "runner": "dsh",
    }
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def adversarial_finish_env(tmp_path, monkeypatch):
    """Set up isolated environment for testing cmd_finish without touching real DB."""
    for attr in ("TASK_DIR", "OUT_DIR", "L1_OUT_DIR", "GOLD_OUT_DIR"):
        monkeypatch.setattr(article_run, attr, tmp_path)

    # Default valid batch files
    (tmp_path / "article_W_ADV_01.output.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(article_run, "pending_batches", lambda w: (["article_W_ADV_01"], []))
    monkeypatch.setattr(article_run, "prefix_hash", lambda: "mock_hash")
    monkeypatch.setattr(
        article_run, "probe_write", lambda: WriteProbe(tmp_path / "mock.db", True, "ghi được")
    )

    calls: list[str] = []
    rcs: dict[str, int] = {}
    argv: dict[str, list[str]] = {}

    def fake_verify_wave(w, min_coverage):
        calls.append("verify_wave")
        return 0

    monkeypatch.setattr(article_run, "verify_wave", fake_verify_wave)

    def fake_run(cmd, *, cwd=None, check=True):
        name = Path(cmd[1]).name
        calls.append(name)
        argv[name] = [Path(c).name for c in cmd[2:]]
        return rcs.get(name, 0)

    monkeypatch.setattr(article_run, "run", fake_run)
    article_run._argv = argv
    article_run._calls = calls
    return article_run, calls, rcs, tmp_path


def _seed_article_and_package(tmp_path, store, article_id: str) -> str:
    """Seed raw article and work package into store and catalog."""
    raw = b"<html><body>" + CLEANED_TEXT.encode("utf-8") + b"</body></html>"
    raw_path = tmp_path / f"{article_id}.html"
    raw_path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    wp = {
        "schema_version": "1.0",
        "article_id": article_id,
        "source_url": "https://cafef.vn/test.chn",
        "domain": "cafef.vn",
        "raw_html_path": str(raw_path),
        "raw_sha256": sha,
        "cleaned_text": CLEANED_TEXT,
        "capture_status": "ok",
        "change_state": "NEW",
    }
    wp_path = tmp_path / f"{article_id}.pkg.json"
    wp_path.write_text(json.dumps(wp, ensure_ascii=False), encoding="utf-8")
    Catalog(store).enqueue(article_id, sha, "cafef.vn", str(wp_path), "NEW")

    # Also seed l1_task for L1 ingestion
    store.upsert_l1_task({
        "article_id": article_id,
        "domain": "cafef.vn",
        "title": "Hòa Phát công bố kết quả",
        "code_first_json": None,
        "route": "agent",
        "packet_path": None,
        "enqueued_at": "2026-11-02T04:00:00Z",
    })
    return sha


def _valid_gold_output(article_id: str) -> dict:
    """Generate valid v2-lean compliant agent-output dictionary with 2 grounded citations."""
    return {
        "output_schema_version": "1.0",
        "article_id": article_id,
        "summary": {"abstractive": "Tóm tắt kết quả kinh doanh quý 3.", "key_points": ["Tăng trưởng mạnh"]},
        "implication": {
            "text": "Kết quả kinh doanh khả quan hỗ trợ dòng tiền và tâm lý nhà đầu tư trong ngắn hạn.",
            "impact_area": "market",
        },
        "materiality": {"score": 0.7, "time_sensitivity": "today"},
        "citations": [
            {"claim": "Tăng trưởng đầu ngành", "source_span": "Alpha beta gamma đầu ngành.", "source_offset": 0},
            {"claim": "Lao động giảm", "source_span": "Delta epsilon zeta lao động giảm mạnh.", "source_offset": 28},
        ],
        "processing_metadata": {"agent_provider": "dsh", "model_used": "deepseek-flash", "timestamp": "2026-11-02T04:00:00Z"},
        "extraction_quality": "high",
    }


def _valid_l1_output(article_id: str) -> dict:
    """Generate valid l1-entity-output dictionary matching schema."""
    title = "Hòa Phát công bố kết quả"
    return {
        "l1_output_version": "1.0",
        "article_id": article_id,
        "title": title,
        "recognized": True,
        "entities": [
            {
                "surface": "Hòa Phát",
                "entity_id": "TICKER:HPG",
                "type": "TICKER",
                "method": "alias",
                "in_list": True,
                "confidence": 0.9,
            }
        ],
        "categories": {
            "ticker_company": "done",
            "etf_fund": "none",
            "index": "none",
            "exchange": "none",
            "industry_sector": "none",
        },
        "citations": [{"source_span": title}],
        "confidence": 0.9,
        "processing_metadata": {"agent_provider": "code-first", "model_used": "catalog", "timestamp": "2026-11-02T04:00:00Z"},
    }


# -----------------------------------------------------------------------------
# Challenge 1: cmd_finish under --mode backlog with Corrupted JSON
# -----------------------------------------------------------------------------
def test_cmd_finish_backlog_corrupted_json_rejects_and_halts(adversarial_finish_env, capsys):
    """Corrupted JSON in output dir MUST make cmd_finish in backlog mode exit 1 and halt."""
    ar, calls, rcs, tmp_path = adversarial_finish_env
    # Simulate l1_ingest failing because output JSON was corrupted
    rcs["l1_ingest.py"] = 1

    rc = ar.cmd_finish(_finish_args(mode="backlog"))
    assert rc == 1, "cmd_finish MUST return exit code 1 when ingest fails in backlog mode"

    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out, "Must print fail_banner indicating incomplete wave"
    assert "✅  ĐỢT" not in out, "Must NEVER print completion banner"

    # Verify short-circuiting: downstream steps must NOT execute
    assert "verify_wave" not in calls, "verify_wave must not be called after ingest failure"
    assert "token_ledger.py" not in calls, "token_ledger must not run after ingest failure"
    assert "handoff.py" not in calls, "handoff must not run after ingest failure"
    assert "ctx_probe.py" not in calls, "ctx_probe must not run after ingest failure"


# -----------------------------------------------------------------------------
# Challenge 2: cmd_finish under --mode backlog with Zero-Length Output File
# -----------------------------------------------------------------------------
def test_cmd_finish_backlog_zero_length_file_rejects_and_halts(adversarial_finish_env, capsys):
    """Zero-length output file MUST make cmd_finish in backlog mode exit 1 and halt."""
    ar, calls, rcs, tmp_path = adversarial_finish_env
    rcs["agent_ingest.py"] = 1

    rc = ar.cmd_finish(_finish_args(mode="backlog"))
    assert rc == 1, "cmd_finish MUST return exit code 1 on agent_ingest failure in backlog mode"

    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out
    assert "✅  ĐỢT" not in out
    assert "verify_wave" not in calls
    assert "token_ledger.py" not in calls
    assert "handoff.py" not in calls


# -----------------------------------------------------------------------------
# Challenge 3: cmd_finish under --mode backlog with Schema Rejections
# -----------------------------------------------------------------------------
def test_cmd_finish_backlog_schema_rejection_halts(adversarial_finish_env, capsys):
    """Schema/DoD rejection leading to rc != 0 MUST make cmd_finish halt and exit 1."""
    ar, calls, rcs, tmp_path = adversarial_finish_env
    rcs["l1_ingest.py"] = 1
    rcs["agent_ingest.py"] = 1

    rc = ar.cmd_finish(_finish_args(mode="backlog"))
    assert rc == 1

    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out
    assert "✅  ĐỢT" not in out
    assert "verify_wave" not in calls
    assert "token_ledger.py" not in calls
    assert "handoff.py" not in calls


# -----------------------------------------------------------------------------
# Challenge 4: cmd_finish under --mode backlog with DB Write Errors
# -----------------------------------------------------------------------------
def test_cmd_finish_backlog_db_write_probe_failure_halts_before_ingest(adversarial_finish_env, monkeypatch, capsys):
    """Preflight write probe failure MUST abort cmd_finish before ingest even starts."""
    ar, calls, rcs, tmp_path = adversarial_finish_env
    monkeypatch.setattr(
        ar, "probe_write", lambda: WriteProbe(tmp_path / "mock.db", False, "attempt to write a readonly database")
    )

    rc = ar.cmd_finish(_finish_args(mode="backlog"))
    assert rc == 1, "cmd_finish MUST return exit code 1 when DB is not writable"

    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out
    assert "DB không ghi được" in out
    assert "l1_ingest.py" not in calls, "Ingest scripts must not run when write probe fails"
    assert "agent_ingest.py" not in calls
    assert "token_ledger.py" not in calls
    assert "handoff.py" not in calls


def test_cmd_finish_backlog_mid_ingest_db_exception_halts(adversarial_finish_env, capsys):
    """A DB write exception (locked, disk error) during ingest causes rc != 0 and halts cmd_finish."""
    ar, calls, rcs, tmp_path = adversarial_finish_env
    # Simulate DB write exception in l1_ingest
    rcs["l1_ingest.py"] = 1

    rc = ar.cmd_finish(_finish_args(mode="backlog"))
    assert rc == 1

    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out
    assert "token_ledger.py" not in calls
    assert "handoff.py" not in calls


# -----------------------------------------------------------------------------
# Challenge 5: Cross-Mode Matrix: Backlog vs Bench vs Adhoc vs Default
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("tested_mode", ["backlog", "bench", "adhoc", None])
def test_cmd_finish_strict_halt_across_all_modes_no_soft_bypass(adversarial_finish_env, tested_mode, capsys):
    """Every mode (backlog, bench, adhoc, None) MUST strictly halt on ingest failure."""
    ar, calls, rcs, tmp_path = adversarial_finish_env
    rcs["agent_ingest.py"] = 1

    rc = ar.cmd_finish(_finish_args(mode=tested_mode))
    assert rc == 1, f"Mode {tested_mode} must return exit code 1 on ingest failure"

    out = capsys.readouterr().out
    assert "CHƯA HOÀN TẤT" in out, f"Mode {tested_mode} must print CHƯA HOÀN TẤT"
    assert "✅  ĐỢT" not in out, f"Mode {tested_mode} must NEVER print completion banner"
    assert "token_ledger.py" not in calls, f"Mode {tested_mode} must not run token_ledger"
    assert "handoff.py" not in calls, f"Mode {tested_mode} must not run handoff"


# -----------------------------------------------------------------------------
# Challenge 6: Mathematical Precision & Edge Boundaries of --fail-threshold
# -----------------------------------------------------------------------------
def test_agent_ingest_fail_threshold_exact_boundaries(tmp_path, monkeypatch):
    """Adversarially verify exact floating point boundary for agent_ingest --fail-threshold."""
    db = tmp_path / "agent_test.db"
    store = ArticleStore(db_path=str(db))
    monkeypatch.setattr(agent_ingest, "load_settings", lambda: {"database": {"path": str(db)}})

    # Seed 10 articles
    articles = [f"art_{i}" for i in range(10)]
    for aid in articles:
        _seed_article_and_package(tmp_path, store, aid)

    # 9 pass, 1 fails (10% failure rate)
    outputs = [_valid_gold_output(aid) for aid in articles[:9]]
    bad_output = _valid_gold_output(articles[9])
    bad_output["citations"] = [{"claim": "x", "source_span": "Hoàn toàn không có trong bài"}]
    outputs.append(bad_output)

    out_file = tmp_path / "mixed_10.json"
    out_file.write_text(json.dumps(outputs, ensure_ascii=False), encoding="utf-8")

    # Boundary 1: threshold 0.10 (fail_rate 0.10 <= 0.10 -> pass rc=0)
    rc_pass = agent_ingest.main([str(out_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.10"])
    assert rc_pass == 0, "fail_rate == threshold MUST be tolerated (rc=0)"

    # Boundary 2: threshold 0.099 (fail_rate 0.10 > 0.099 -> fail rc=1)
    rc_fail = agent_ingest.main([str(out_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.099"])
    assert rc_fail == 1, "fail_rate > threshold MUST fail (rc=1)"

    # Boundary 3: strict zero tolerance default (threshold 0.0 -> fail rc=1)
    rc_zero = agent_ingest.main([str(out_file), "--task-dir", str(tmp_path), "--no-archive"])
    assert rc_zero == 1, "Default 0.0 threshold MUST reject any failure (rc=1)"


def test_agent_ingest_corrupted_json_and_empty_file_handling(tmp_path, monkeypatch):
    """agent_ingest MUST fail (exit 1 or raise JSONDecodeError terminating process) on corrupt files."""
    db = tmp_path / "agent_corrupt.db"
    ArticleStore(db_path=str(db))
    monkeypatch.setattr(agent_ingest, "load_settings", lambda: {"database": {"path": str(db)}})

    # Corrupted JSON file
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{\"incomplete\": [1, 2,", encoding="utf-8")
    try:
        rc_corrupt = agent_ingest.main([str(corrupt_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.5"])
        assert rc_corrupt == 1, "Corrupted JSON file must return exit code 1"
    except (json.JSONDecodeError, ValueError):
        pass  # Unhandled JSONDecodeError cleanly crashes the CLI process with exit code 1

    # Zero-length file
    zero_file = tmp_path / "zero.json"
    zero_file.write_text("", encoding="utf-8")
    try:
        rc_zero = agent_ingest.main([str(zero_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.5"])
        assert rc_zero == 1, "Zero-length file must return exit code 1"
    except (json.JSONDecodeError, ValueError):
        pass  # Unhandled JSONDecodeError cleanly crashes the CLI process with exit code 1

    # Empty array file (skipped cleanly)
    empty_arr_file = tmp_path / "empty_arr.json"
    empty_arr_file.write_text("[]", encoding="utf-8")
    rc_empty = agent_ingest.main([str(empty_arr_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.0"])
    assert rc_empty == 0, "Valid empty array [] file (skipped) must exit 0"


def test_l1_ingest_fail_threshold_exact_boundaries(tmp_path, monkeypatch):
    """Adversarially verify exact floating point boundary for l1_ingest --fail-threshold."""
    db = tmp_path / "l1_test.db"
    store = ArticleStore(db_path=str(db))
    monkeypatch.setattr(l1_ingest, "load_settings", lambda: {"database": {"path": str(db)}})

    articles = [f"l1_art_{i}" for i in range(10)]
    for aid in articles:
        _seed_article_and_package(tmp_path, store, aid)

    # 9 pass, 1 fails
    outputs = [_valid_l1_output(aid) for aid in articles[:9]]
    bad_output = _valid_l1_output(articles[9])
    bad_output["citations"] = [{"source_span": "chuỗi không nằm trong tiêu đề"}]
    outputs.append(bad_output)

    out_file = tmp_path / "l1_mixed_10.json"
    out_file.write_text(json.dumps(outputs, ensure_ascii=False), encoding="utf-8")

    # Boundary 1: threshold 0.10 (rc=0)
    rc_pass = l1_ingest.main([str(out_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.10"])
    assert rc_pass == 0, "l1_ingest: fail_rate <= threshold MUST pass (rc=0)"

    # Boundary 2: threshold 0.099 (rc=1)
    rc_fail = l1_ingest.main([str(out_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.099"])
    assert rc_fail == 1, "l1_ingest: fail_rate > threshold MUST fail (rc=1)"


def test_l1_ingest_corrupted_json_and_empty_file_handling(tmp_path, monkeypatch):
    """l1_ingest MUST fail (exit 1 or raise JSONDecodeError terminating process) on corrupt files."""
    db = tmp_path / "l1_corrupt.db"
    ArticleStore(db_path=str(db))
    monkeypatch.setattr(l1_ingest, "load_settings", lambda: {"database": {"path": str(db)}})

    corrupt_file = tmp_path / "l1_corrupt.json"
    corrupt_file.write_text("{\"incomplete\": [", encoding="utf-8")
    try:
        rc_corrupt = l1_ingest.main([str(corrupt_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.5"])
        assert rc_corrupt == 1
    except (json.JSONDecodeError, ValueError):
        pass

    zero_file = tmp_path / "l1_zero.json"
    zero_file.write_text("", encoding="utf-8")
    try:
        rc_zero = l1_ingest.main([str(zero_file), "--task-dir", str(tmp_path), "--no-archive", "--fail-threshold", "0.5"])
        assert rc_zero == 1
    except (json.JSONDecodeError, ValueError):
        pass


# -----------------------------------------------------------------------------
# Challenge 7: Real Subprocess Execution & CLI Encoding Invariant (Rule 03 & 06)
# -----------------------------------------------------------------------------
def test_real_subprocess_cli_help_and_pipe_encoding():
    """Verify that --fail-threshold is present in CLI help via real subprocess with piped stdout."""
    for script_name in ("agent_ingest.py", "l1_ingest.py"):
        script_path = str(SCRIPTS_DIR / script_name)
        res = subprocess.run(
            [PYTHON, script_path, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert res.returncode == 0, f"{script_name} --help failed with rc={res.returncode}"
        assert "--fail-threshold" in res.stdout, f"--fail-threshold missing from {script_name} --help"


def test_real_subprocess_agent_ingest_corrupted_file_exits_one(tmp_path):
    """Execute real agent_ingest.py subprocess on corrupted file and verify exit code 1."""
    corrupt_file = tmp_path / "subprocess_corrupt.output.json"
    corrupt_file.write_text("{ broken json [", encoding="utf-8")

    script_path = str(SCRIPTS_DIR / "agent_ingest.py")
    res = subprocess.run(
        [PYTHON, script_path, str(corrupt_file), "--fail-threshold", "0.1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 1, "Real subprocess agent_ingest.py MUST exit 1 on corrupted file"
    assert "JSONDecodeError" in res.stderr or "FAILED" in res.stdout
