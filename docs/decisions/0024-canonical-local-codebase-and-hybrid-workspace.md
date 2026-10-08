---
id: ADR-0024
type: adr
title: Canonical Local Codebase Standardization and Hybrid Workspace Governance
status: accepted
lane: high-risk
created: 2026-10-08
updated: 2026-10-08
lang: en
authors: [operator, antigravity]
approvers: [operator 2026-10-08]
story: [US-038]
amends: [ADR-0001, ADR-0022]
evidence:
  - path:C:/src/news-scraper
  - path:C:/gitdirs/news-scraper.git
  - path:C:/venvs/news-scape
  - commit:cab26a0
  - "operator:2026-10-08 canonical repository consolidated at C:/src/news-scraper and OneDrive tree deprecated"
summary: Establishes C:/src/news-scraper as the sole canonical worktree, isolates git database and virtual environment outside OneDrive, and deprecates development on cloud-synced folders.
summary_vi: Quy chuẩn C:/src/news-scraper là worktree chính thức duy nhất, cách ly git database và venv ra khỏi OneDrive, và ngừng toàn bộ phát triển trên thư mục đồng bộ đám mây.
---

# ADR-0024 — Canonical Local Codebase Standardization and Hybrid Workspace Governance

## Context

- Prior to 2026-10-08, development occurred inside the OneDrive synchronization directory `FRA_DataIngestion - news-scape`.
- Operating directly within active cloud-synced folders caused persistent file-locking friction, hydration delays during compilation, OneDrive conflict forks (`*-DESKTOP-*`), and background sync corruption of SQLite databases and Git metadata.
- In addition, multiple concurrent subagent worktrees (`news-scape-us039`, `news-scape-us040`, `news-scape-us041`, `news-scraper-dev`) had accumulated under `C:\src`, causing code fragmentation and divergent copies of `harness.db`.
- A definitive operational standard is required to establish a single source of truth for the codebase, isolate Git and virtual environments from cloud sync engines, and maintain a pristine local developer experience.

## Decision

- **ADR-0024.D1 (Single Canonical Local Worktree):** All agent sessions, commands, and operator coding MUST execute exclusively within `C:\src\news-scraper` on local NVMe/SSD storage. Active development within the legacy OneDrive directory `FRA_DataIngestion - news-scape` is permanently deprecated.
- **ADR-0024.D2 (Isolated Git Directory):** The Git internal database MUST reside outside cloud-synchronized paths at `C:\gitdirs\news-scraper.git` using `--separate-git-dir`. Within the repository root, `.git` MUST exist only as a static text pointer.
- **ADR-0024.D3 (Isolated Virtual Environment):** The Python execution environment MUST reside exclusively at `C:\venvs\news-scape\Scripts\python.exe`. Creating or storing `.venv` directories inside cloud-synchronized folders is strictly prohibited.
- **ADR-0024.D4 (Worktree Lifecycle and Pruning):** Temporary git worktrees allocated for isolated subagent execution MUST be fully pruned (`git worktree remove`) immediately after branch integration into `dev/us038`. Only the primary worktree `C:\src\news-scraper` remains persistent.
- **ADR-0024.D5 (Unified Harness Source of Truth):** A single authoritative `harness.db` database MUST govern development state at `C:\src\news-scraper\harness.db`. Fragmented local copies MUST be reconciled and synchronized to `C:\data\news-scape\harness.db`.

## Alternatives

| Option | Why rejected |
|---|---|
| Developing inside OneDrive sync tree | Severe file locks during git operations, delayed hydration, and risk of sync watcher corrupting Python caches. |
| Persistent multiple worktrees under C:\src | Fragmented git state, divergent database records across multiple harness instances, and merge overhead. |
| Storing in-repo .venv environments | Thousands of virtual environment packages trigger massive OneDrive synchronization traffic and CPU exhaustion. |

## Consequences

- Complete elimination of OneDrive file-locking conflicts and sync lag during test execution and git commits.
- Absolute reproducibility of the Python runtime via dedicated `C:\venvs\news-scape`.
- Clean, unfragmented codebase with exactly one active working tree tracked on remote `Research-FPA/news-scraper`.
- Accepted constraint: Developers must run terminal commands and launch agents with current working directory explicitly rooted at `C:\src\news-scraper`.

## Rollback

In the event of local disk failure or workspace corruption, clone a fresh copy from GitHub remote `https://github.com/Research-FPA/news-scraper.git` to `C:\src\news-scraper` and reconnect the external gitdir at `C:\gitdirs\news-scraper.git`.

## Follow-up

- [ ] Ensure Windows Task Scheduler jobs and automation scripts reference `C:\src\news-scraper` and `C:\venvs\news-scape\Scripts\python.exe`.
- [ ] Maintain pre-commit hooks to verify `clean_for_closure` status via `harness_cli.py git status`.
