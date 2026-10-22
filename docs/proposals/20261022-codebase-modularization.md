---
id: PRP-20261022-codebase-modularization
type: proposal
title: "Codebase modularization: assess options and target structure"
status: decided
lane: high-risk
created: 2026-10-22
updated: 2026-10-22
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0027]
story: [US-049]
plan: []
related: [ADR-0010, ADR-0024, ADR-0026, FACT-tests-must-not-write-operational-db]
evidence:
  - commit:ec4e7fe
  - path:plans/20260924-1627-codebase-audit-cleanup-modularization/plan.md
  - "metric:ast import graph and reachability from 21 live entry points, 2026-10-22: 66 of 219 code files unreachable, 8,778 LOC"
  - "metric:7 scripts-to-scripts imports and 2 src-to-scripts imports (src/ops/daemon.py, src/ops/sensor.py)"
  - "metric:30 PROJECT_ROOT definitions, 69 files with sys.path.insert, 24 files calling sqlite3.connect outside src/db"
summary: Should the codebase be restructured into modules, and how? Yes, but by moving logic inward behind stable CLI paths (option B), not by a full package rewrite; the 2026-09-24 audit plan is refreshed and split into five gated stories.
summary_vi: Có nên module hoá lại codebase không? Có, theo hướng dời logic vào src/ và giữ nguyên đường dẫn CLI (phương án B), không viết lại thành package mới; plan kiểm toán 24/09 được cập nhật và chia thành năm story có cổng duyệt.
---

# PRP-20261022-codebase-modularization — Codebase modularization: assess options and target structure

## Question

- The operator finds the codebase flat and hard to follow, and suspects dead scripts accumulated during development.
- Should the directory structure be modularized, and if so, which approach is safe for a system that runs 24/7 from the canonical tree (ADR-0024.D1)?

## Findings

- All numbers come from a static scan of commit `ec4e7fe` on branch `dev/us049-codebase-modularization`.
- The scan builds an `ast` import graph, adds textual script references found in `.py`, `.ps1`, `.ts` and `.yaml` code, and walks reachability from 21 live entry points.
- Entry points: AGENTS.md §4 commands, `.agents/pipeline.yaml` CLIs, `ops_install.ps1`, the ADR-0026 publish path and `harness_cli.py`. The scan scripts lived in a scratchpad, outside the repository.

### F1. The flatness is in three places, not everywhere

- `project/src/` already has 17 packages with a mostly sane direction (`scrapers`, `pipeline`, `export`, `ops` depend on `core` and `db`).
- Flat zones: `project/scripts/` (61 top-level files plus 17 in `maintenance/`), `project/tests/` (103 files in one folder, no `pytest.ini`), `src/ops/` (27 modules) and `src/agent/` (21 modules that mix live runners, the article contract and retired L1 code).

### F2. Business logic lives in scripts, so the layering is inverted

| Script | LOC | Role |
|---|---|---|
| `article_run.py` | 1,177 | wave lifecycle and `--finish` gate |
| `pipeline_radar.py` | 940 | state report and next command |
| `article_pack.py` | 843 | selection, tiers, packets |
| `article_expand.py` | 608 | compact record expansion |
| `token_ledger.py` | 599 | ledger |

- 7 imports go script to script (`pipeline_radar` → `token_ledger`, `article_pack`; `article_run`, `handoff` → `article_pack`; others).
- 2 imports go from `src` back to `scripts`: `src/ops/daemon.py:145` (`article_tick.PipelineLock`) and `src/ops/sensor.py:88` (`article_pack.load_candidates`).
- `src/ops/wave_flow.py` drives the lane by `subprocess` on `scripts/article_run.py` and `scripts/write_user_output.py`.
- Package cycles: `agent ↔ ops`, `agent ↔ handoff`, `export ↔ lakehouse`, `core → db`, `core → crawler`, `ops → morninger`.

### F3. Path and DB plumbing is duplicated

- 30 modules define their own `PROJECT_ROOT`; 69 files call `sys.path.insert`; 24 files outside `src/db` call `sqlite3.connect`. `src/core/paths.py` exists but is not the only source.

### F4. Dead code is measurable: 66 files, 8,778 LOC unreachable from live entry points

| Group | Files | Note |
|---|---|---|
| Retired L1/Gold lane (ADR-0010) | `run_daily.ps1`, `run_pipeline.ps1`, `auto_pilot`, `agent_export`, `l1_backlog`, `run_agent_hierarchy`, `process_l1_pipeline`, `run_validation`, `verify_gold_quality`, `maintenance/requeue`, `maintenance/route_today_l1`, `maintenance/cleanup_legacy_tasks`, `run_user_workflow` + `src/pipeline/user_workflow.py` | Deletion is already decided by ADR-0010 |
| One-off maintenance already applied | `migrate_data_root`, `migrate_users_output`, `relativize_paths`, `repair_dates`, `fix_backlog_manifest`, `clean_yahoo_lifestyle`, `clean_onedrive_conflicts`, `backfill_missing_traces`, `heal_orphans`, `audit_alias_false_positives` | Need per-item operator review |
| Manual operator tools | `dbq`, `db_status`, `db_snapshot`, `diagnose_sources`, `domain_check` (+ `src/monitor/domain_*`), `monitor_daily` (+ `daily_reporter`), `export_csv`, `export_silver`, `sample_articles` (+ `processor/sentiment`, `segment`), `watch_24h`, `report_drift`, `validate_e2e`, `verify_quality`, `make_user_template`, `opencode_native_run`, `fetch_periodic_reports` (+ `pipeline/periodic_reports`) | Unreachable from automation but may be used by hand |
| Duplicates | `.agents/skills/git-codebase-governance/scripts/audit_codebase.py` (diverged copy), `project/scripts/doc_lint.py` (superseded by `harness_cli doc lint`) | Delete |

- `scripts/knowledge.py` shows as unreachable only because `harness_cli.py` imports it by `sys.path`; it is live.
- Execution check (S2): `project/scripts/doc_lint.py` is live through `test_doc_lint.py` and stays. `migrate_users_output.py` stays because the US-045 migration has not run (607 files remain in `users_output`).

### F5. Retired code is still wired into the live `--finish` path

- `article_run --finish` → `l1_ingest.py` → `src/agent/l1_runner.L1Runner`, whose class still carries `route_and_export`, `ingest_code_first` and `drain_code_first`, and textually references `l1_route.py`.
- `agent_ingest.py` and `l1_ingest.py` import `src/agent/batch_handoff` and `archive` from the retired lane.
- Deleting files without first splitting these classes breaks the wave gate. The 2026-09-24 audit (R1) reached the same conclusion and fixed an order of removal.

### F6. The 2026-09-24 audit plan was only partly executed

- Done: test isolation in `tests/conftest.py` (sets `MONOCLE_DATA_DIR` and `MONOCLE_DB_PATH` before any import), ADR-0015, the canonical tree (ADR-0024).
- Not done: retired-lane removal (S2), `paths.py` as the single source (S4), `tests/repo/test_architecture.py` and `src/article_lane/` (S5), the module-boundary rule.
- Since then US-038 added `opencode_runner`, `run_backlog_opencode` and the ops daemon modules, so the counts above supersede the old ones.

### F7. CLI paths are a public contract

- `scripts/<name>.py` paths are referenced by `.agents/pipeline.yaml` (11 CLIs), Task Scheduler (`ops_install.ps1`), `src/ops/wave_flow.py`, generated conductor `.ts` files, AGENTS.md §4, rules, skills and 236 Markdown documents. `article_run.py` alone has 34 references in `docs/` and 17 in `.agents/`.
- The daemon runs from `C:\src\news-scraper` and reloads scripts from disk, so a merge changes running production.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Hygiene only: remove dead code, add an architecture test, no moves | Lowest risk; removes about 9K LOC of noise | Inverted layering stays; `scripts/` keeps 4K LOC of lane logic; the codebase still reads flat |
| B. Move logic inward behind stable CLI paths (refreshed R2 plan of 2026-09-24) | Clear layers (`core` → `db` → domain packages → thin CLIs); every CLI path, Task Scheduler entry and document stays valid; each step is one revertible commit checked by golden tests | Five stories of work; needs quiet merge windows; thin shims remain in `scripts/` |
| C. Full rewrite into an installable package (`news_scape/`, `pyproject.toml`, `python -m` entry points, domain folders bronze/silver/lane/delivery/ops) | Textbook structure, no `sys.path` hacks | Breaks every CLI path in F7 at once; Task Scheduler, DSH presets, conductor generator, runbooks and 236 documents change in one release; a big-bang change to a 24/7 system with no staging environment |
| D. Reorganize the repository root too (`other/`, `openrouter/`, `okf/`, `project/thamkhao/`) | Tidier top level | Mostly documents and prototypes; low value for code comprehension; can ride along with B as a small chore |

## Recommendation

Option B. It fixes what makes the code hard to follow (logic in scripts, inverted imports, retired code mixed with live code) without touching the contract in F7. Option C buys little beyond B and its risk lands on the running daemon. `pyproject.toml` and `python -m` entry points stay possible later, once all logic is in `src/` and the scripts are three-line shims.

### Target structure

| Layer | Packages | May import |
|---|---|---|
| L0 | `src/core` (`paths.py` is the only place that computes the project root, data root and DB path) | stdlib, third party |
| L1 | `src/db` (the only place that calls `sqlite3.connect`) | L0 |
| L2 | `src/crawler`, `src/scrapers`, `src/processor`, `src/pipeline`, `src/agent/runners/` (agy, opencode, openrouter), `src/agent/contract/`, new `src/article_lane/` (select, pack, expand, finish, ledger, radar `decide()`), `src/export`, `src/lakehouse`, `src/ops/` split into `daemon/`, `wave/`, `supervision/`, `console/` | L0, L1, other L2 without cycles |
| L3 | `project/scripts/*.py`: parse arguments, call one `src` function; paths unchanged | L0-L2 |

Rules, enforced by `project/tests/repo/test_architecture.py` with an allowlist frozen at today's state that may only shrink: no `scripts → scripts`, no `src → scripts`, no new `sys.path.insert`, no `sqlite3.connect` outside `src/db`, no package cycle. `project/tests/` mirrors `src/` in subfolders.

### Rollout: five stories, each in its own worktree branched from `dev/us038`

| Story | Scope | Gate before merge |
|---|---|---|
| S1 Guardrails | `test_architecture.py` with frozen allowlist; golden snapshots of packet, conductor `.ts` and expand output; reachability check added to `harness_cli audit --codebase` | Full `pytest` green; no behavior change |
| S2 Retired lane removal | Split `L1Runner` and `batch_handoff` so `--finish` keeps only live methods, then delete group 1 of F4 with its tests; delete duplicates | Golden unchanged; one `--finish` on a temp DB; operator approves group lists 2 and 3 item by item |
| S3 One source of paths and DB | `src/core/paths.py` and `src/db` replace the 30 `PROJECT_ROOT`, 24 `sqlite3.connect` sites | Tests run from three working directories with the same resolved paths |
| S4 Article Lane into `src/article_lane/` | Move logic from the five scripts in F2; remove `src → scripts` and `scripts → scripts`; `wave_flow` calls Python functions instead of `subprocess` where safe | Golden unchanged; stop at the first golden diff |
| S5 Package split and test layout | Split `src/ops` and `src/agent` into subpackages; mirror tests into subfolders | Full `pytest` green; `pipeline_radar.py status` and `article_run.py --where` unchanged |

- Merge each story only when `pipeline_radar.py status` shows no wave in flight and the daemon is at L0; restart the daemon after the merge; rollback is `git revert` of that merge.
- Old imports get no long-lived re-export shims; tests are updated in the same commit as the move.

## Outcome

- 2026-10-22 operator: option B approved, to be executed through S5; deletion lists of F4 groups 2 and 3 approved; branch push approved. Decision recorded in ADR-0027; work tracked in US-049, phases S1-S5 on branch `dev/us049-codebase-modularization`.
- 2026-10-22 result: S1-S5 done in one branch, one story (sequential phases instead of five worktrees, since each phase builds on the previous one). `project/scripts` went from 78 files and 14,922 LOC to 37 files and 4,451 LOC; test suite unchanged at 898 passed. Merge into `dev/us038` waits for a quiet window (`docs/OPEN-ITEMS.md`).
