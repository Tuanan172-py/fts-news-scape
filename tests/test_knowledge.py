"""Tests for the ADR-0021 knowledge document contract and Schema v2 linter."""

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
    schema_data = k.load_schema(tmp_path)
    for entry in schema_data.get("exempt", []):
        p_str = entry["path"] if isinstance(entry, dict) else str(entry)
        target = tmp_path / p_str
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# Exempt placeholder\n", encoding="utf-8")
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
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], "\n".join(str(f) for f in errors)


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


# ---------------------------------------------------------------------------
# Migrated presentation and doc_lint tests (ADR-0021 / Schema v2)
# ---------------------------------------------------------------------------

def test_unified_repo_has_no_blocking_errors() -> None:
    findings = k.lint(ROOT_DIR)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == []


def test_k21_vietnamese_banned_phrases(repo: Path) -> None:
    content = VALID_ADR.replace("lang: en", "lang: vi\nsummary_vi: Mẫu").replace("Nothing.", "Nhìn chung hệ thống ổn.")
    _write(repo, "docs/decisions/0001-sample.md", content)
    assert "K21" in _codes(repo)
    assert "L01" in [f.rule for f in k.lint_markdown("x.md", "Nhìn chung hệ thống ổn.")]


def test_k21_k10_emoji_detection(repo: Path) -> None:
    content = VALID_ADR.replace("Nothing.", "Trạng thái ✅ xong.")
    _write(repo, "docs/decisions/0001-sample.md", content)
    assert "K10" in _codes(repo)
    assert "L02" in [f.rule for f in k.lint_markdown("x.md", "Trạng thái ✅ xong.")]


def test_k19_retired_terms(repo: Path) -> None:
    content = VALID_ADR.replace("Nothing.", "Cấp standing order mới.")
    _write(repo, "docs/decisions/0001-sample.md", content)
    assert "K19" in _codes(repo)
    content2 = VALID_ADR.replace("Nothing.", "Run article with l1_route pipeline.")
    _write(repo, "docs/decisions/0001-sample.md", content2)
    assert "K19" in _codes(repo)
    content3 = VALID_ADR.replace("Nothing.", "Operations run 24/7.")
    _write(repo, "docs/decisions/0001-sample.md", content3)
    assert "K19" in _codes(repo)


def test_k20_internal_code_leakage(repo: Path) -> None:
    user_doc = """---
id: REF-user-guide
type: reference
title: User Guide
status: active
created: 2026-10-06
updated: 2026-10-06
lang: vi
audience: user
summary: Hướng dẫn người dùng.
---

# REF-user-guide — User Guide

## Overview

Tài liệu này hướng dẫn người dùng sử dụng hệ thống một cách hiệu quả và thuận tiện nhất có thể.

## Details

Xem US-031 để biết thêm.

## References

None.
"""
    _write(repo, "docs/user-guide.md", user_doc)
    assert "K20" in _codes(repo)
    assert "L04" in [f.rule for f in k.lint_markdown("x.md", "Xem US-031 để biết thêm.")]


def test_k21_vietnamese_sentence_length(repo: Path) -> None:
    long_sentence = " ".join(["từ"] * 30) + "."
    content = VALID_ADR.replace("lang: en", "lang: vi\nsummary_vi: Mẫu").replace("Nothing.", long_sentence)
    _write(repo, "docs/decisions/0001-sample.md", content)
    assert "K21" in _codes(repo)
    assert "L08" in [f.rule for f in k.lint_markdown("x.md", long_sentence)]


def test_clean_prose_passes_all_checks() -> None:
    assert k.lint_markdown("x.md", "Hệ thống chạy ổn định.") == []


def test_code_fences_and_inline_backticks_exempt(repo: Path) -> None:
    text = "```\nNhìn chung US-031\n```\nDùng `US-031` khi cần."
    assert k.lint_markdown("x.md", text) == []


def test_presentation_python_ast_docstrings_comments() -> None:
    src = 'def f():\n    """Nhìn chung."""\n    return "xong ✅"  # tôi làm\n'
    rules = {f.rule for f in k.lint_python("x.py", src)}
    assert {"L01", "L02"} <= rules
    assert {f.rule for f in k.lint_python("x.py", "def (:)")} == {"L00"}


def test_presentation_html_ui() -> None:
    rules = {f.rule for f in k.lint_html("x.html", "<p>Xong ✅ US-031</p>")}
    assert {"L02", "L04"} <= rules
    assert k.lint_html("x.html", "<p>Đã xong.</p>") == []


# ---------------------------------------------------------------------------
# New Schema v2 Rule Tests (K14, K15, K16, K17, K18, K22, Warning Mode)
# ---------------------------------------------------------------------------

def test_k14_unmanaged_markdown_file(repo: Path) -> None:
    _write(repo, "unmanaged.md", "# Unmanaged doc\n")
    subprocess.run(["git", "add", "unmanaged.md"], cwd=repo, check=True)
    assert "K14" in _codes(repo)


def test_k15_exempt_validation(repo: Path) -> None:
    schema_path = repo / k.SCHEMA_PATH
    raw = schema_path.read_text(encoding="utf-8")
    bad_schema = raw + "\n  - path: nonexistent.md\n    rationale: Bad file\n"
    schema_path.write_text(bad_schema, encoding="utf-8")
    assert "K15" in _codes(repo)


def test_k16_audience_language_consistency(repo: Path) -> None:
    text = VALID_ADR.replace("lang: en", "lang: vi\nsummary_vi: Mẫu")
    _write(repo, "docs/decisions/0001-sample.md", text)
    assert "K16" in _codes(repo)


def test_k17_pointer_document_floors(repo: Path) -> None:
    ptr = """---
id: REF-pointer-sample
type: reference
title: Pointer Sample
status: pointer
created: 2026-10-06
updated: 2026-10-06
lang: en
audience: agent
summary: A pointer sample.
---

# REF-pointer-sample — Pointer Sample

## Overview

Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7
Line 8
Line 9
Line 10
Line 11
Line 12
Line 13
Line 14
Line 15
Line 16

## Details

None.

## References

None.
"""
    _write(repo, "docs/pointer-sample.md", ptr)
    assert "K17" in _codes(repo)


def test_k18_canonical_topic_uniqueness(repo: Path) -> None:
    doc1 = VALID_ADR.replace("evidence: [commit:abc1234]", "evidence: [commit:abc1234]\ncanonical_for: architecture")
    doc2 = VALID_ADR.replace("id: ADR-0001", "id: ADR-0002").replace("evidence: [commit:abc1234]", "evidence: [commit:abc1234]\ncanonical_for: architecture")
    _write(repo, "docs/decisions/0001-sample.md", doc1)
    _write(repo, "docs/decisions/0002-sample.md", doc2)
    assert "K18" in _codes(repo)


def test_k22_broken_relative_links(repo: Path) -> None:
    broken = VALID_ADR.replace("Nothing.", "See [missing](nonexistent.md).")
    _write(repo, "docs/decisions/0001-sample.md", broken)
    assert "K22" in _codes(repo)


def test_transitional_warning_mode(repo: Path) -> None:
    broken = VALID_ADR.replace("Nothing.", "See [missing](nonexistent.md).")
    _write(repo, "docs/decisions/0001-sample.md", broken)
    findings = k.lint(repo)
    k22 = [f for f in findings if f.code == "K22"]
    assert len(k22) == 1
    assert k22[0].severity == "warning"


def test_glob_match_exhaustive() -> None:
    """Assert glob_match handles globstar (**), single wildcards (*), and path segments correctly."""
    assert k.glob_match(".git/config", "**/.git/**") is True
    assert k.glob_match(".agents/teamwork/challenger_m2_1/README.md", ".agents/teamwork/**") is True
    assert k.glob_match("node_modules/pkg/index.js", "**/node_modules/**") is True
    assert k.glob_match("scratch/notes.md", "**/scratch/**") is True
    assert k.glob_match("project/docs/guides/advanced/setup.md", "project/docs/**/*.md") is True
    assert k.glob_match("project/domains/market/analysis/tickers.md", "project/domains/**/*.md") is True
    assert k.glob_match("docs/ledgers/2026/w-a/summary.md", "docs/ledgers/**/*.md") is True
    assert k.glob_match("okf/core/specs/catalog.md", "okf/**/*.md") is True
    assert k.glob_match("docs/decisions/0029-unified-documentation-lifecycle.md", "docs/decisions/*.md") is True

    # Negative matches
    assert k.glob_match("docs/decisions/sub/0029.md", "docs/decisions/*.md") is False
    assert k.glob_match("docs/stories/US-001.md", "docs/decisions/*.md") is False
    assert k.glob_match("project/docs/setup.md", "docs/*.md") is False
    assert k.glob_match("scratch.md", "**/scratch/**") is False
    assert k.glob_match("docs/README.md", "*.md") is False

    # Scalar globs and root files
    assert k.glob_match("README.md", "*.md") is True
    assert k.glob_match("README.md", "**/*.md") is True
    assert k.glob_match("docs/README.md", "**/*.md") is True

    # Windows path separators and relative prefixes
    assert k.glob_match(r".git\config", "**/.git/**") is True
    assert k.glob_match(r"scratch\notes.md", "**/scratch/**") is True
    assert k.glob_match("./.git/config", "**/.git/**") is True


def test_is_excluded_globstar() -> None:
    """Assert is_excluded handles schema dictionary and list patterns with globstars."""
    schema = k.load_schema(ROOT_DIR)
    assert k.is_excluded(".git/config", schema) is True
    assert k.is_excluded(".agents/teamwork/challenger_m2_1/README.md", schema) is True
    assert k.is_excluded("node_modules/pkg/index.js", schema) is True
    assert k.is_excluded("scratch/notes.md", schema) is True
    assert k.is_excluded("docs/decisions/0001-sample.md", schema) is False

    # List pattern support
    excludes = ["**/.git/**", "**/scratch/**"]
    assert k.is_excluded(".git/HEAD", excludes) is True
    assert k.is_excluded("scratch/temp.txt", excludes) is True
    assert k.is_excluded("docs/decisions/0001.md", excludes) is False


def test_classify_doc_recursive() -> None:
    """Assert classify_doc correctly identifies nested doc types and honors exclusions."""
    schema = k.load_schema(ROOT_DIR)
    assert k.classify_doc("project/docs/guides/advanced/setup.md", schema) == "reference"
    assert k.classify_doc("project/domains/market/analysis/tickers.md", schema) == "reference"
    assert k.classify_doc("okf/core/specs/catalog.md", schema) == "okf"
    assert k.classify_doc("docs/ledgers/2026/w-a/summary.md", schema) == "ledger"
    assert k.classify_doc("docs/decisions/0029-unified.md", schema) == "adr"

    # Excluded files must return None
    assert k.classify_doc(".agents/teamwork/challenger_m2_1/README.md", schema) is None
    assert k.classify_doc("docs/INDEX.md", schema) is None


def test_k18_inactive_canonical_topic_allowed(repo: Path) -> None:
    """Assert K18 does not collide when previous canonical doc is retired/superseded."""
    doc1 = (VALID_ADR.replace("status: accepted", "status: superseded")
            .replace("evidence: [commit:abc1234]", "evidence: [commit:abc1234]\ncanonical_for: architecture"))
    doc2 = (VALID_ADR.replace("id: ADR-0001", "id: ADR-0002")
            .replace("evidence: [commit:abc1234]", "evidence: [commit:abc1234]\ncanonical_for: architecture"))
    _write(repo, "docs/decisions/0001-sample.md", doc1)
    _write(repo, "docs/decisions/0002-sample.md", doc2)
    assert "K18" not in _codes(repo)


def test_k19_superseded_and_archived_excluded(repo: Path) -> None:
    """Assert K19 allows retired terms in superseded and archived documents."""
    doc_superseded = VALID_ADR.replace("status: accepted", "status: superseded").replace("Nothing.", "Contains l1_route here.")
    _write(repo, "docs/decisions/0001-sample.md", doc_superseded)
    assert "K19" not in _codes(repo)
