"""Empirical Challenger test suite for citation grounding and anti-copy quality.

Adversarially validates:
1. 100% exact verbatim substring containment of citations.
2. 0.00% copied key points from citations.
3. Market implication length (>= 40 chars) and absence of boilerplate.
4. Complete absence of stubs, dummy values, or placeholders in agent_outputs.
5. Strict adherence to financial domain semantic enums across executed waves:
   - W_BKL_01_10301528
   - W_BKL_01_11021118
   - W_BKL_01_11021334
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXECUTED_WAVES = [
    "W_BKL_01_10301528",
    "W_BKL_01_11021118",
    "W_BKL_01_11021334",
]


def clean_ops_env() -> dict[str, str]:
    """Build environment for subprocesses pointing to operational data root.

    Strips pytest-induced MONOCLE_* environment overrides so child scripts
    reach the actual operational data in C:\\data\\news-scape.

    Returns:
        Environment dictionary with operational defaults and UTF-8 encoding.
    """
    env = dict(os.environ)
    env.pop("MONOCLE_DATA_DIR", None)
    env.pop("MONOCLE_DB_PATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.mark.production_host
@pytest.mark.parametrize("wave_id", EXECUTED_WAVES)
def test_verify_wave_citations_cli_verdict(wave_id: str) -> None:
    """Verify that verify_wave_citations CLI returns APPROVE with 100% grounding and 0% copy."""
    script_path = PROJECT_ROOT / "scripts" / "maintenance" / "verify_wave_citations.py"
    proc = subprocess.run(
        [sys.executable, str(script_path), "--wave", wave_id, "--json"],
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"verify_wave_citations failed for {wave_id}:\n{proc.stderr}"
    data = json.loads(proc.stdout)

    assert data.get("verdict") == "APPROVE"
    assert data.get("dod_pass_rate", 0) >= 0.95

    c = data.get("citations", {})
    assert c.get("total_checked", 0) > 0
    assert c.get("exact_grounding_rate") == 1.0
    assert c.get("failures_count") == 0
    assert c.get("min_length", 0) >= 20

    kp = data.get("key_points", {})
    assert kp.get("total_checked", 0) > 0
    assert kp.get("copied_count") == 0
    assert kp.get("copy_rate") == 0.0

    imp = data.get("implications", {})
    assert imp.get("violations_count") == 0
    assert imp.get("min_length", 0) >= 40
    assert imp.get("avg_length", 0) >= 100


@pytest.mark.production_host
def test_no_stubs_or_placeholders_in_wave_agent_outputs() -> None:
    """Audit all records in agent_outputs across executed waves for stubs or placeholders."""
    code = (
        "import sys, sqlite3, json\n"
        "from scripts.article_run import wave_article_ids\n"
        "from src.db.preflight import resolve_db_path\n"
        "waves = ['W_BKL_01_10301528', 'W_BKL_01_11021118', 'W_BKL_01_11021334']\n"
        "aids = []\n"
        "for w in waves: aids.extend(wave_article_ids(w))\n"
        "db_file = resolve_db_path()\n"
        "conn = sqlite3.connect(f'file:{db_file.as_posix()}?mode=ro', uri=True, timeout=30.0)\n"
        "q = 'SELECT article_id, output_json FROM agent_outputs WHERE article_id IN (' + ','.join('?'*len(aids)) + ')'\n"
        "rows = conn.execute(q, aids).fetchall()\n"
        "conn.close()\n"
        "assert len(rows) > 0, 'No rows found'\n"
        "stubs = ['todo', 'fixme', 'n/a', 'placeholder', 'dummy', 'lorem ipsum', 'test output', '[none]']\n"
        "violations = []\n"
        "for aid, raw_json in rows:\n"
        "    data = json.loads(raw_json)\n"
        "    s = str(data.get('summary') or '').lower()\n"
        "    im = str(data.get('implication') or '').lower()\n"
        "    kps = [str(k).lower() for k in (data.get('key_points') or [])]\n"
        "    for stub in stubs:\n"
        "        if stub in s: violations.append((aid, 'summary', stub))\n"
        "        if stub in im: violations.append((aid, 'implication', stub))\n"
        "        for kp in kps:\n"
        "            if stub in kp: violations.append((aid, 'key_points', stub))\n"
        "assert len(violations) == 0, f'Found stubs: {violations[:10]}'\n"
        "print('STUB_AUDIT_OK', len(rows))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"test_no_stubs failed:\n{proc.stderr}\n{proc.stdout}"
    assert "STUB_AUDIT_OK" in proc.stdout


@pytest.mark.production_host
def test_market_implication_depth_and_anti_boilerplate() -> None:
    """Assert all implications have length >= 40 and zero boilerplate across all wave outputs."""
    code = (
        "import sys, sqlite3, json\n"
        "from scripts.article_run import wave_article_ids\n"
        "from src.db.preflight import resolve_db_path\n"
        "waves = ['W_BKL_01_10301528', 'W_BKL_01_11021118', 'W_BKL_01_11021334']\n"
        "aids = []\n"
        "for w in waves: aids.extend(wave_article_ids(w))\n"
        "db_file = resolve_db_path()\n"
        "conn = sqlite3.connect(f'file:{db_file.as_posix()}?mode=ro', uri=True, timeout=30.0)\n"
        "q = 'SELECT article_id, output_json FROM agent_outputs WHERE article_id IN (' + ','.join('?'*len(aids)) + ')'\n"
        "rows = conn.execute(q, aids).fetchall()\n"
        "conn.close()\n"
        "assert len(rows) > 0, 'No rows found'\n"
        "boilerplates = [\n"
        "    'nội dung bài viết phản ánh thông tin và diễn biến quan trọng',\n"
        "    'thông tin phản ánh diễn biến hoạt động kinh doanh, cơ cấu tài chính',\n"
        "    'nội dung bài viết tác động tới nhận định thị trường',\n"
        "]\n"
        "for aid, raw_json in rows:\n"
        "    data = json.loads(raw_json)\n"
        "    impl = data.get('implication') or ''\n"
        "    text = impl if isinstance(impl, str) else (impl.get('text', '') if isinstance(impl, dict) else '')\n"
        "    text = text.strip()\n"
        "    assert len(text) >= 40, f'Implication too short ({len(text)}) for {aid}'\n"
        "    for b in boilerplates:\n"
        "        assert b not in text.lower(), f'Boilerplate in {aid}'\n"
        "print('IMPLICATION_AUDIT_OK', len(rows))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"test_implication failed:\n{proc.stderr}\n{proc.stdout}"
    assert "IMPLICATION_AUDIT_OK" in proc.stdout


@pytest.mark.production_host
def test_semantic_enums_and_group_codes() -> None:
    """Verify sentiment and time_sensitivity conform to valid enum specifications."""
    code = (
        "import sys, sqlite3, json\n"
        "from scripts.article_run import wave_article_ids\n"
        "from src.db.preflight import resolve_db_path\n"
        "waves = ['W_BKL_01_10301528', 'W_BKL_01_11021118', 'W_BKL_01_11021334']\n"
        "aids = []\n"
        "for w in waves: aids.extend(wave_article_ids(w))\n"
        "db_file = resolve_db_path()\n"
        "conn = sqlite3.connect(f'file:{db_file.as_posix()}?mode=ro', uri=True, timeout=30.0)\n"
        "q = 'SELECT article_id, output_json FROM agent_outputs WHERE article_id IN (' + ','.join('?'*len(aids)) + ')'\n"
        "rows = conn.execute(q, aids).fetchall()\n"
        "conn.close()\n"
        "assert len(rows) > 0, 'No rows found'\n"
        "valid_sentiments = {'pos', 'neg', 'neu', 'positive', 'negative', 'neutral'}\n"
        "valid_ts = {'urg', 'today', 'week', 'month', 'arch', 'urgent', 'this_week', 'this_month', 'archive'}\n"
        "for aid, raw_json in rows:\n"
        "    data = json.loads(raw_json)\n"
        "    sn = data.get('sentiment') or data.get('sn')\n"
        "    assert sn in valid_sentiments, f'Invalid sentiment {sn} in {aid}'\n"
        "    ts = data.get('time_sensitivity') or data.get('ts')\n"
        "    assert ts in valid_ts, f'Invalid time_sensitivity {ts} in {aid}'\n"
        "print('ENUMS_AUDIT_OK', len(rows))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=clean_ops_env(),
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"test_semantic_enums failed:\n{proc.stderr}\n{proc.stdout}"
    assert "ENUMS_AUDIT_OK" in proc.stdout
