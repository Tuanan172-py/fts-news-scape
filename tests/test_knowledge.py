"""Tests for the ADR-0021 knowledge document contract."""

import shutil
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import knowledge as k  # noqa: E402

VALID_ADR = """---
id: ADR-0001
type: adr
title: Sample decision
status: accepted
lane: normal
created: 2026-10-06
updated: 2026-10-06
lang: en
approvers: [operator 2026-10-06]
evidence: [commit:abc1234]
summary: A sample decision used by tests.
summary_vi: "Mẫu cho test."
---

# ADR-0001 — Sample decision

## Context

- The system writes documents in many shapes and nobody can parse them reliably across models.
- Agents from several vendors write project knowledge and each one follows its own habits.
- A shared contract with a validator removes the ambiguity and lets tools read the same fields.
- Measurements from the audit show most records drift from the template within a few weeks.

## Decision

- D1. Every document MUST carry frontmatter with the keys defined in the schema file.
- D2. The lint gate MUST run before every commit and block documents that break the contract.
- D3. The index MUST be generated from frontmatter so that agents read summaries before bodies.

## Alternatives

| Option | Why rejected |
|---|---|
| Prose templates | Drifted within weeks. |
| Database records | Not visible to every tool. |

## Consequences

- Documents become machine readable for every model and the index can be generated from them.
- Writers spend a little more time on structure, which the scaffolding command offsets.

## Rollback

- Remove the lint step from the pre-commit hook and revert the commits of each phase.

## Follow-up

- [ ] Nothing.
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Create a throwaway git repository holding the schema and templates."""
    (tmp_path / "docs/knowledge").mkdir(parents=True)
    shutil.copy(ROOT_DIR / k.SCHEMA_PATH, tmp_path / k.SCHEMA_PATH)
    shutil.copytree(ROOT_DIR / k.TEMPLATE_DIR, tmp_path / k.TEMPLATE_DIR)
    for folder in ("docs/decisions", "docs/stories", ".agents/rules"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "core.autocrlf=false",
                    "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _codes(repo: Path) -> list[str]:
    return [f.code for f in k.lint(repo)]


def test_valid_adr_passes(repo: Path) -> None:
    _write(repo, "docs/decisions/0001-sample.md", VALID_ADR)
    assert k.lint(repo) == []


def test_missing_frontmatter_needs_legacy_entry(repo: Path) -> None:
    _write(repo, "docs/decisions/0002-old.md", "# Old\n")
    assert _codes(repo) == ["K00"]
    _write(repo, k.LEGACY_PATH, "docs/decisions/0002-old.md\n")
    assert k.lint(repo) == []


def test_missing_and_misordered_sections(repo: Path) -> None:
    text = VALID_ADR.replace("## Rollback", "## Undo")
    _write(repo, "docs/decisions/0001-sample.md", text)
    assert "K05" in _codes(repo)
    swapped = VALID_ADR.replace("## Context", "## TMP").replace("## Decision", "## Context").replace("## TMP", "## Decision")
    _write(repo, "docs/decisions/0001-sample.md", swapped)
    assert "K05" in _codes(repo)


def test_vietnamese_prose_flagged_but_quotes_allowed(repo: Path) -> None:
    quoted = VALID_ADR.replace("Nothing.", 'Operator said "lấy về tất cả".')
    _write(repo, "docs/decisions/0001-sample.md", quoted)
    assert k.lint(repo) == []
    _write(repo, "docs/decisions/0001-sample.md", VALID_ADR.replace("Nothing.", "Việc còn lại."))
    assert "K09" in _codes(repo)


def test_floors_enforced(repo: Path) -> None:
    thin = VALID_ADR.replace("| Database records | Not visible to every tool. |\n", "")
    _write(repo, "docs/decisions/0001-sample.md", thin)
    assert "K06" in _codes(repo)


def test_bad_status_id_and_evidence(repo: Path) -> None:
    text = (VALID_ADR.replace("status: accepted", "status: done")
            .replace("commit:abc1234", "abc1234"))
    _write(repo, "docs/decisions/0001-sample.md", text)
    codes = _codes(repo)
    assert "K02" in codes and "K08" in codes
    _write(repo, "docs/decisions/0009-sample.md", VALID_ADR)
    assert "K03" in _codes(repo)


def test_duplicate_and_broken_links(repo: Path) -> None:
    _write(repo, "docs/decisions/0001-sample.md", VALID_ADR)
    _write(repo, "docs/decisions/0001-copy.md", VALID_ADR)
    assert "K04" in _codes(repo)
    (repo / "docs/decisions/0001-copy.md").unlink()
    _write(repo, "docs/decisions/0001-sample.md", VALID_ADR.replace("lang: en", "lang: en\namends: [ADR-0042]"))
    assert "K07" in _codes(repo)


def test_superseded_requires_terminal_status(repo: Path) -> None:
    _write(repo, "docs/decisions/0001-sample.md", VALID_ADR)
    newer = VALID_ADR.replace("ADR-0001", "ADR-0002").replace("lang: en", "lang: en\nsupersedes: [ADR-0001]")
    _write(repo, "docs/decisions/0002-sample.md", newer)
    findings = k.lint(repo)
    assert [f.code for f in findings] == ["K11"]
    assert findings[0].path == "docs/decisions/0001-sample.md"
    index = k.build_index(repo)
    assert "accepted (by ADR-0002)" in index


def test_allocator_scans_branches_and_db(repo: Path) -> None:
    subprocess.run(["git", "checkout", "-q", "-b", "other"], cwd=repo, check=True)
    _write(repo, "docs/decisions/0007-elsewhere.md", "# x\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "x"],
                   cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    assert not (repo / "docs/decisions/0007-elsewhere.md").exists()
    res = k.new_doc(repo, "adr", "Next decision", today=date(2026, 10, 6))
    assert res["id"] == "ADR-0008"
    db = repo / "harness.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE story (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO story VALUES ('US-041')")
    res = k.new_doc(repo, "story", "Next story", db_path=str(db))
    assert res["id"] == "US-042"
    with pytest.raises(FileExistsError):
        _create_twice(repo)


def _create_twice(repo: Path) -> None:
    """Create the same scaffold path twice to prove creation never overwrites."""
    k.new_doc(repo, "fact", "Same fact")
    k.new_doc(repo, "fact", "Same fact")


def test_adopt_rejects_existing_file(repo: Path) -> None:
    _write(repo, "docs/decisions/0001-sample.md", VALID_ADR)
    with pytest.raises(ValueError):
        k.new_doc(repo, "adr", "Again", adopt_id="ADR-0001")


def test_scaffold_has_contract_shape(repo: Path) -> None:
    res = k.new_doc(repo, "story", "Do a thing", today=date(2026, 10, 6))
    codes = set(_codes(repo))
    assert res["path"] == "docs/stories/US-001-do-a-thing.md"
    assert codes <= {"K06"}, codes


def test_staged_filter(repo: Path) -> None:
    _write(repo, "docs/decisions/0001-bad.md", "# no frontmatter\n")
    assert k.lint(repo, only=set()) == []
    assert _codes(repo) == ["K00"]


def test_sync_db_upserts_and_reports_drift(repo: Path) -> None:
    res = k.new_doc(repo, "story", "Do a thing", today=date(2026, 10, 6))
    db = repo / "harness.db"
    with sqlite3.connect(db) as conn:
        conn.executescript((ROOT_DIR / "scripts/schema/001-init.sql").read_text(encoding="utf-8"))
        conn.execute("INSERT INTO story (id, title, created_at, updated_at) VALUES ('US-099','x','t','t')")
    out = k.sync_db(repo, str(db))
    assert out["stories"] == 1 and out["db_only_stories"] == ["US-099"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status FROM story WHERE id=?", (res["id"],)).fetchone()[0] == "planned"


def test_doc_lint_defers_contract_files() -> None:
    sys.path.insert(0, str(ROOT_DIR / "project/scripts"))
    import doc_lint

    assert doc_lint._CONTRACT_FM_RE.match(VALID_ADR)
    assert not doc_lint._CONTRACT_FM_RE.match("# ADR 0013\n- **Ngày:** 2026-10-01\n")


def test_repository_passes_contract() -> None:
    findings = k.lint(ROOT_DIR)
    assert findings == [], "\n".join(str(f) for f in findings)


def test_wip_is_per_branch(repo: Path) -> None:
    for n, branch in ((1, "feat/a"), (2, "feat/b")):
        res = k.new_doc(repo, "story", f"Story {n}", today=date(2026, 10, 6))
        p = repo / res["path"]
        p.write_text(p.read_text(encoding="utf-8").replace(
            "status: planned", f"status: in_progress\nbranch: {branch}"), encoding="utf-8")
    assert "K13" not in _codes(repo)
    p = repo / "docs/stories/US-002-story-2.md"
    p.write_text(p.read_text(encoding="utf-8").replace("branch: feat/b", "branch: feat/a"), encoding="utf-8")
    assert _codes(repo).count("K13") == 2
    p.write_text(p.read_text(encoding="utf-8").replace("branch: feat/a\n", ""), encoding="utf-8")
    assert "K01" in _codes(repo)
