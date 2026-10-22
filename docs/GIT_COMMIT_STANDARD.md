# GIT_COMMIT_STANDARD.md — Commit Standard and Progressive Disclosure

Purpose: a standalone reference that defines the commit standard (Conventional Commits 1.0.0 and Semantic Versioning) for the whole News-Scape project under the harness.

> [!NOTE]
> **Progressive disclosure:**
> This file is a static tier-2 reference. Developers and agents do not reread it in daily work. The CLI (`harness_cli.py git template`, `harness_cli.py story complete --commit`, `harness_cli.py session close`) generates compliant messages at zero token cost. Open this file only to resolve a dispute or to write release notes.

---

## 1. Message structure (Conventional Commits 1.0.0)

A commit has up to three blocks separated by a blank line:

```text
<type>(<scope>): <subject> (US-NNN)

[body: context, WHY the change is needed, technical trade-offs]

[footer: breaking changes, ADR or issue references]
```

### A. Header line (required)
- **Maximum length**: 72 characters (ideal 50–60).
- **Format**: lowercase `<type>` and `<scope>`. The first letter of `<subject>` is lowercase, and the line **never ends with a period**.
- **Harness id**: every commit of a Normal or High-Risk story carries `(US-NNN)` at the end of the header.

### B. Body (optional, recommended for large changes)
- Answer **why** the change exists and how it affects the architecture. Do not list changed files; `git diff` shows them.
- Wrap at about 72–80 characters.

### C. Footer (breaking changes and decisions)
- Breaking change: `BREAKING CHANGE: <migration or impact>`
- Decision reference: `Refs: ADR-NNNN`

---

## 2. Commit type taxonomy

| Type | Meaning | Criterion | Example |
| :--- | :--- | :--- | :--- |
| **`feat`** | New feature | Adds a capability a user or consumer can use. | `feat(export): add intent columns to deliverable Excel (US-002)` |
| **`fix`** | Bug fix | Fixes behaviour that deviates from the agreed specification. | `fix(article_pack): check content_text column existence (US-025)` |
| **`refactor`** | Restructuring | Reorganises code **without changing external behaviour**. | `refactor(l1_router): extract regex patterns to compile time constant (US-010)` |
| **`perf`** | Performance | Improves speed, memory, LLM tokens or I/O with identical logic. | `perf(tokenizer): use morphological compact array for tokens (US-009)` |
| **`docs`** | Documentation | Changes only Markdown, docstrings, rules or guides. | `docs(governance): add ADR 0010 Article Lane unified architecture (US-027)` |
| **`test`** | Tests | Adds or changes unit tests, integration tests or fixtures. | `test(harness_cli): add test cases for git lifecycle and clean status (US-030)` |
| **`chore`** | Maintenance | Tooling config, ignore files, internal migrations, file hygiene. | `chore(hygiene): clean dangling worktree and update .gitignore` |

---

## 3. Grammar and style rules

1. **Imperative mood**:
   - Write the subject as a direct command.
   - **Right**: `add`, `fix`, `refactor`, `remove`, `update`, `optimize`.
   - **Wrong**: `added`, `fixes`, `fixing`, `refactored`, `improving`.
2. **No vague wording**:
   - Avoid: `update various files`, `fix minor bug`, `wip`, `clean code`.
   - Name the entity or module affected: `fix(dedup): prevent false-positive url merge on trailing slash`.
3. **Standard News-Scape scopes**:
   - `core`: shared infrastructure (`src/core/`, staging, stdio).
   - `bronze`: capture and raw storage.
   - `silver`: DOM extraction and text normalisation.
   - `article-lane`: LLM analysis and citations (`src/article_lane/`, `src/agent/`).
   - `ops`: wave flow, daemon and console (`src/ops/`).
   - `export` / `delivery`: user delivery (`.xlsx`) and publish.
   - `harness`: governance CLI, tracking, tests.
   - `governance`: rules, ADRs, system policies.

---

## 4. Zero-token tools in the harness CLI

Generate a compliant message without spending LLM tokens:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git template --type feat --scope core --story US-030 --title "integrate git lifecycle"
```

When a story is completed through the harness, `--commit` applies this standard:
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py story complete --id US-NNN --run-verify --commit
```
