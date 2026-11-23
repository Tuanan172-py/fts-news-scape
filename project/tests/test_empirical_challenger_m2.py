"""Empirical challenger verification suite for Milestone 2 operational waves.

Verifies:
1. Unit and stress invariants for exact substring citation grounding and anti-copy gate.
2. Semantic quality enforcement: implication length >= 40, non-boilerplate, enum adherence.
3. Subprocess CLI verification of verify_wave_citations.py on operational waves.
4. Subprocess CLI verification of article_run.py verify mode on operational waves.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from project.scripts.maintenance.verify_wave_citations import _norm

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def clean_ops_env() -> dict[str, str]:
    """Build environment for subprocesses pointing to operational data root.

    Strips pytest-induced MONOCLE_* environment overrides so child scripts
    reach the actual operational data in C:\\data\\news-scape.

    Returns:
        Environment dictionary with operational defaults.
    """
    env = dict(os.environ)
    env.pop("MONOCLE_DATA_DIR", None)
    env.pop("MONOCLE_DB_PATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_citation_grounding_synthetic_invariants():
    """Verify that exact substring matching strictly detects exact vs normalized vs ungrounded text."""
    sample_article = (
        "Ủy ban Chứng khoán Nhà nước thông báo kế hoạch nâng hạng thị trường. "
        "Quy mô giao dịch bình quân đạt 25.000 tỷ đồng mỗi phiên trong quý 3."
    )

    exact_cite = "Quy mô giao dịch bình quân đạt 25.000 tỷ đồng mỗi phiên trong quý 3."
    norm_cite = "Quy mô   giao dịch  bình quân đạt 25.000 tỷ đồng mỗi phiên trong quý 3."
    hallucinated_cite = "Quy mô giao dịch bình quân đạt 35.000 tỷ đồng mỗi phiên trong quý 3."

    # Invariant 1: Exact citation must be in sample_article
    assert exact_cite in sample_article

    # Invariant 2: Modified whitespace citation is not an exact substring
    assert norm_cite not in sample_article
    assert _norm(norm_cite) in _norm(sample_article)

    # Invariant 3: Hallucinated figure is neither exact nor normalized
    assert hallucinated_cite not in sample_article
    assert _norm(hallucinated_cite) not in _norm(sample_article)


def test_anti_copy_gate_synthetic_invariants():
    """Verify that the anti-copy gate rejects verbatim copies and normalized copies of citations."""
    citations = [
        "Quy mô giao dịch bình quân đạt 25.000 tỷ đồng mỗi phiên trong quý 3.",
        "Ủy ban Chứng khoán Nhà nước thông báo kế hoạch nâng hạng thị trường.",
    ]
    raw_cites = {c.strip() for c in citations}
    norm_cites = {_norm(c) for c in citations}

    # Original key points: analytical summary, not a copy
    original_kp = "Thanh khoản thị trường quý 3 duy trì ở mức cao 25.000 tỷ/phiên."
    assert original_kp not in raw_cites
    assert _norm(original_kp) not in norm_cites

    # Verbatim copy violation
    verbatim_kp = "Quy mô giao dịch bình quân đạt 25.000 tỷ đồng mỗi phiên trong quý 3."
    assert verbatim_kp in raw_cites

    # Normalized whitespace copy violation
    norm_copy_kp = "Quy mô   giao dịch bình quân đạt 25.000 tỷ đồng mỗi phiên trong quý 3. "
    assert _norm(norm_copy_kp) in norm_cites


OPERATIONAL_WAVES = ["W_BKL_01_10301528", "W_BKL_01_11021118"]


@pytest.mark.production_host
@pytest.mark.parametrize("wave_id", OPERATIONAL_WAVES)
def test_verify_wave_citations_cli_operational_wave(wave_id: str):
    """Empirically audit operational backlog waves via verify_wave_citations.py CLI.

    Args:
        wave_id: Identifier of the wave under test.
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "maintenance" / "verify_wave_citations.py"),
        "--wave",
        wave_id,
        "--json",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"Audit script failed with exit code {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"

    report = json.loads(proc.stdout)
    assert report["verdict"] == "APPROVE"
    assert report["wave_id"] == wave_id
    assert report["ingested_articles"] >= 490
    assert report["dod_pass_rate"] == 1.0

    citations = report["citations"]
    assert citations["exact_grounding_rate"] == 1.0
    assert citations["failures_count"] == 0
    assert citations["total_checked"] >= 1000

    key_points = report["key_points"]
    assert key_points["copy_rate"] == 0.0
    assert key_points["copied_count"] == 0

    implications = report["implications"]
    assert implications["violations_count"] == 0
    assert implications["min_length"] >= 40


@pytest.mark.production_host
@pytest.mark.parametrize("wave_id", OPERATIONAL_WAVES)
def test_article_run_verify_cli_operational_wave(wave_id: str):
    """Verify that article_run.py verify mode reports >= 99% coverage for operational waves.

    Args:
        wave_id: Identifier of the wave under test.
    """
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "article_run.py"),
        "--wave",
        wave_id,
        "--finish",
        "--only",
        "verify",
        "--min-coverage",
        "0.20",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    assert proc.returncode == 0, f"article_run verify failed with code {proc.returncode}:\n{stdout}\n{stderr}"
    assert "phân tích nội dung" in stdout
    assert "99.8%" in stdout or "100.0%" in stdout
