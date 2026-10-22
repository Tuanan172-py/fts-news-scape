---
trigger: always_on
---
# 06 — Code Quality and Docstring Standards

Mandatory for every agent and subagent that writes, maintains or refactors source code in news-scape. Style: Google Python Style Guide, production-deliverable tone. Language: English (AGENTS.md §8, ADR-0021.D4). Vietnamese stays only in quoted data, regex/keyword literals and delivered user output.

---

## 1. Presentation

- A docstring defines the contract: what the entity takes, what it does, what it returns or raises.
- Declarative, imperative, objective, concise. Subject-less: start with an action verb ("Compute...", "Parse...", "Build...").
- No first person ("we", "I", "let's"), no tutorial tone, no rhetorical questions.
- Comments explain non-obvious business logic or algorithm choices (the why). No debugging diary, change history, personal narrative or commented-out code; Git keeps history.

## 2. Banned content

The dictionary is `.agents/rules/banned_phrases.json` (used by `scan_code_phrases.py --dict`). Categories:

1. Filler and vague generalization (`basically`, `in general`, `note that`).
2. Hype and subjective evaluation (`robust`, `comprehensive`, `powerful`, `elegant`).
3. First person and tutorial tone (`let's`, `we can`, `you should`).
4. Questions: a docstring or comment sentence ending in `?`.
5. Emoji and decorative pictographs, 100%.
6. Draft markers (`[LEGACY...`, `temp fix`) and bare `# TODO`. The only TODO form is `# TODO(US-NNN): <task>`.

## 3. Docstring structure (Google style)

### Module
Exactly one declarative sentence ending with a period.
```python
"""Orchestrate packing and hand-off of article analysis work packages."""
```

### Class
Line 1 states the role. Add `Attributes:` for public attributes.
```python
class AgentRunner:
    """Drive the export lifecycle of subagent tasks and collect results.

    Attributes:
        store: SQLite connection to the operational database.
        task_dir: Directory that receives the exported work packages.
    """
```

### Function and method
Line 1: imperative sentence ending with a period. Then, as applicable:
- `Args:` one entry per parameter (including keyword-only); meaning and constraints, not the type when the signature has a hint.
- `Returns:` meaning of the returned value. Omit for `None` and for `@property`.
- `Yields:` required for generators.
- `Raises:` every exception raised deliberately.
```python
def export_tasks(self, limit: int = 20, *, require_l1: bool = True) -> list[dict]:
    """Export pending jobs as JSON work packages.

    Args:
        limit: Maximum number of tasks to export.
        require_l1: Accept only articles that passed L1 validation.

    Returns:
        One dict per task exported successfully.

    Raises:
        RuntimeError: If the task directory is not writable.
    """
```

### Scripts with a CLI
A script that feeds `__doc__` to `argparse` keeps a first docstring line that is a complete sentence, because `__doc__.splitlines()[0]` is used as the description. Never reduce such a module docstring to an empty or multi-line-only string.

## 4. Verification gate

1. Signatures, logic, SQL, transactions and the `monocle.db` schema are never changed by a documentation edit.
2. Every touched Python file passes `ast.parse()`. For a docs-only refactor, the AST of each file with docstrings stripped is identical before and after.
3. Docstring gate (run from the repo root):
   ```powershell
   # External skill `codebase-docstring-refactoring`, not in this repository. Operator machine path:
   $s = "C:\Users\anpt\Documents\report_writing_skills\05_Style_Docstrings_and_Writing_Standards\codebase-docstring-refactoring\scripts"
   python $s\ast_docstring_linter.py project\src --min-coverage 100
   python $s\scan_code_phrases.py project\src --dict .agents\rules\banned_phrases.json
   ```
   Same for `project\scripts`. Required: 0 `MISSING_DOCSTRING` for public entities, 0 `EXTRA_PARAM`, scanner 0 ERROR. The scanner crashes with `--format json`; use text mode.
4. `pytest tests/` shows no new failure.
5. Real-execution proof, not only green pytest (incident 2026-09-17: 403 tests passed while three defects ran in production: `__doc__.split("\n")[1]` raised IndexError, `UnicodeEncodeError` on piped stdout, `subprocess` without `encoding` gave `stdout=None`; tests imported functions directly and never crossed the `if __name__ == "__main__"` or process boundary):
   - Edited script with a CLI: run it once the way automation calls it (real flags, stdout piped).
   - Changed time-based operating parameter (interval, timeout, limit, batch size): measure before setting. Incident: `capture_interval_minutes: 5` while a real cycle took 335 s made jobs overlap permanently.
   - New periodic background job: it needs an internal time budget that stops it cleanly; a `subprocess` timeout kill loses all statistics.
   - Done criterion: a story reaches `implemented` only with Platform-tier evidence (run in a real process) for any change touching an automation path.
6. A refactor commit that only changes docstrings is separate from logic commits, and its hash is appended to `.git-blame-ignore-revs`.
