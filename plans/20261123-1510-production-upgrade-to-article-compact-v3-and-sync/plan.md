---
id: PLN-20261123-1510-production-upgrade-to-article-compact-v3-and-sync
type: plan
title: Production upgrade to article-compact-v3 and sync M1 for fpa-toolkit
status: approved
lane: high-risk
created: 2026-11-23
updated: 2026-11-23
lang: en
authors: [agent]
adr: [ADR-0030, ADR-0031, ADR-0033]
story: [US-056, US-057, US-058]
evidence:
  - "url: https://github.com/Research-FPA/news-scraper/issues/10#issuecomment-7090987629 (roadmap M0-M3)"
  - "url: https://github.com/Research-FPA/news-scraper/issues/10#issuecomment-7095092085 (AnPT commits M1 to 2026-11-27, agrees to the 5-point x spec)"
  - "url: https://github.com/Research-FPA/news-scraper/issues/9#issuecomment-7005616576 (operator conditions; step 3 needs one clean publish day)"
  - "url: https://github.com/Research-FPA/news-scraper/issues/8 (catalog check and publishing asks)"
  - "commit: f1d655c (common base with fpa-toolkit main 0d0cf3c1)"
  - "url: fpa-toolkit 9229581f (ADR-0027 code), 01e117c2 (article-compact-v3), main e2d37ae4 (packages/news unchanged since 26abbd8d)"
  - "path: project/src/research_db/production.py day_records (builds entities from article_entities, bypasses lakehouse ingest)"
  - "path: project/tests/test_empirical_challenger_m2_2_wave_concurrency.py:108 (truncates the live WAL from a subprocess, outside the conftest sqlite guard)"
  - "metric: ops.db, agy DONE articles per day 2026-11-16..23: 2003, 5497, 6077, 685, 794, (none 21-22), 1183; waves of ~60 articles take 2-5 min"
  - "operator: 2026-11-23 scope cut to M1, reviewers from the agy model family, catalog published in M1, a clean day 2026-11-25 on FRA - Data/news accepted as the clean-publish evidence"
  - "operator: 2026-11-23 the project runs directly on FRA - Data/news (sandbox retired as a target); agy quota limits models to gemini-4-hydrogen and gemini-3.8-flash; G0 windows and class (c) handling approved as proposed"
  - "metric: ops.db 2026-11-23, research.published about every 30 min with 0 partition errors; sandbox publish.ok once a day"
summary: Approved lean plan to the M1 sync SHA on 2026-11-27, run directly on FRA - Data/news (ADR-0027 live, prefix and catalog, test safety, v3 code with flag off, agy cost sample), with gates, reviewers and a split rule.
---

# PLN-20261123-1510 — Production upgrade to article-compact-v3 and sync M1

## Context

Step 2 of the fpa-toolkit integration is merged (fpa-toolkit PR #610, merge `0d0cf3c1`, ancestor `f1d655c`). DucNN folded the rest into one sync round (issue #10):

| Milestone | Owner | Done when | Date |
|---|---|---|---|
| M1 | AnPT | One SHA on `import/clean-<date>` carrying ADR-0027 on production, regenerated prefix files, HSG test and ADR-0031.D4 amendment, challenger test markers, `x` columns, and an `agy` cost report | **2026-11-27** |
| M2 | DucNN | `satellite_sync pull`, xfail on HSG removed, `--check-prefix` green, merged | 1 working day after M1 |
| M3 | AnPT approves, DucNN confirms | v3 flag on in `ops_daemon` config, v3 running | After M2 |

**This plan ends at M1.** M3 work goes to a follow-up plan (see "After M1"). All work runs on the current laptop production host. Today is Monday 2026-11-23; M1 leaves 4.5 working days and no buffer.

State at planning time (2026-11-23):
- `dev/us038` local head `3d85247`, not pushed: `fpa` and `origin` are at `3931ac9`. `86b1e1a` (PARKED fixture fix) is not on `dev/us038`.
- fpa-toolkit `main` is `e2d37ae4`; `packages/news` has not changed since `26abbd8d`. Against base `f1d655c`: 21 files changed on production, 117 under `packages/news` on `main`, 14 on both sides, 1 conflict (`scripts/git_hooks/pre-commit`, take `main`).
- ADR-0027 is `accepted` (2026-11-15) on `main`.
- `main` carries the v3 contract and the prefix generator (`--impacts` writes `ARTICLE_SYSTEM_CORE_V3.md`), but no runner wiring and no stamps.

The project runs directly on FRA - Data/news (operator, 2026-11-23); the sandbox is no longer a target. Two code paths still publish:

| Output | Path in code | Target | Role in M1 |
|---|---|---|---|
| **Research lakehouse (ADR-0030)** | `src/research_db/production.py`, five slots a day plus express, about every 30 min | `NEWS_SCAPE_RESEARCH_DB_DIR` (FRA - Data/news) | **The live target.** Users read it through skills. |
| Sandbox lakehouse | `scripts/publish.py` through `src/lakehouse/ingest.py` and `consolidator.py`, daily at 01:00 | `NEWS_SCAPE_PUBLISH_DIR` (sandbox) | Legacy. Unchanged in M1; its code is copied for sync parity and covered by tests only. |

Correction found in P3 (2026-11-23): the research path builds its records in `day_records`, then `records_to_parquet_bytes` passes every record through `sanitize_article_record` (`ingest.py:297`). Copying `ingest.py` from `main` therefore applies ADR-0027 to FRA - Data/news without a further change. The planning-time claim that the research path bypasses `ingest` was wrong.

FRA - Data/news is the lakehouse that keeps updating, and users read it through skills. No distribution feature is needed in this phase.

## Decisions

- D1. Keep ADR-0027: `entities` carries only model-named ids; `CODE_ONLY` stays in `intent_code`. Through the copied `ingest.py`, it applies to both FRA - Data/news and the sandbox path. ADR-0031.D4 is amended to match.
- D2. One-way flow: `dev/us038` → `import/clean-<date>` → news-scraper `main`. Never merge fpa-toolkit `main` or news-scraper `main` back into `dev/us038`. For M1 only, `import/clean-20261127` is the `dev/us038` head plus a merge of the P5 branch. P5 reaches `dev/us038` at M3 by a merge of that same branch, never by cherry-pick or rebase. Every later fix to P5 is committed on the P5 branch, so the next sync sees each change once.
- D3. Port by whole-file copy from `main`. Every other `main` change a copied file brings is listed and checked (P2).
- D4. `x` is stored as a nullable JSON string. Four new columns go last in `LAKEHOUSE_ARTICLE_SCHEMA`: `x`, `contract_version`, `rubric_version`, `prompt_hash`. `processed_at`, `runner` and `model` reuse `analyzed_at`, `agent_provider` and `model_used`. `OBT_SCHEMA` moves `obt/2` → `obt/3`; old partitions read NULL.
- D5. v3 replaces the v2 pass (no extra run), stays inside the L1 batch limit, and is off by default behind one config flag.
- D6. Deadline 2026-11-27. Split checkpoint **2026-11-26 12:00**: if R2 has not passed, the M1 SHA carries P1, P3, P4 and P6 only. P5 and P7 then go in a second round, and the issue #10 table is updated the same day.
- D7. P7 measures v3 on a stratified sample of about 400 real articles, at the live wave size and concurrency. The report states N and projects to a day. The first live waves at M3 confirm the figures at full volume.
- D8. Reviews R1 and R2 run on `agy` with `gemini-4-hydrogen-high`, a different family from the implementer (Claude), as in the v3 rubric evaluation. The `agy` quota allows only `gemini-4-hydrogen` and `gemini-3.8-flash` in this plan.
- D9. The live catalog is published in M1 to FRA - Data/news. The research publisher copies `entities.json` next to the partitions and records its path, size and SHA-256 in `_manifest/latest.json` (issue #8, operator 2026-11-23).
- D10. P3 replay thresholds, on the FRA - Data/news output: P6 is blocked only by a lost row or a lost model-named entity. Any other difference is recorded with its cause. The PR #7 changes in `ingest.py` also reach the research path, so the replay measures them.

## Design

1. Make tests safe first: P1a removes the live WAL write before any full-suite run; P1b extends the existing guard.
2. Land ADR-0027 on both outputs with the new prefix and the catalog (P2, P3, P4). Go live in one window (P6).
3. In parallel, write v3 behind a flag that stays off (P5) on its own branch. It is never deployed before M3.
4. Measure v3 on a sample from live articles (P7). Package one SHA (P8).

## Safety rules for every implementing agent

1. Never write under `C:\data\news-scape` from tests, scripts or analysis. Set `MONOCLE_DATA_DIR` to a temp directory; scripts that write also get `--out` in a temp directory. Live databases are opened read-only (`file:...?mode=ro`).
2. **No full-suite run, in any worktree, on a base without P1a.** P1a is the first commit on `dev/us038`; every phase branch is cut after it.
3. WIP=1 per worktree (ADR-0022). Each phase runs in its own worktree; never check out in the production worktree `C:\src\news-scraper` while the daemon runs.
4. No bare `git stash`; park work as a commit.
5. Run only the test files a phase touches, then the full suite once before its review.
6. Every commit follows `docs/GIT_COMMIT_STANDARD.md` and names its story.
7. Nothing is posted to GitHub without the operator's word "gửi".
8. The live daemon is stopped only in the P6 window, outside the flush windows in `config/ops.yaml` (07:15-07:45, 08:15-08:40, 12:15-12:45, 15:15-15:45, 17:15-17:45).
9. P7 shares the `agy` account with the daemon. It stops if the `agy` provider breaker leaves `CLOSED` or a live wave ends `PARKED`.
10. Only the daemon's research publisher writes to FRA - Data/news. Tests, replays and P7 set `NEWS_SCAPE_RESEARCH_DB_DIR` and `NEWS_SCAPE_PUBLISH_DIR` to temp directories.
11. `agy` calls use only `gemini-4-hydrogen-high` (reviews) and `gemini-3.8-flash-low` (P7, the production runner).

## Review process

Reviews copy the method of the v3 rubric evaluation (fpa-toolkit `eval-u12-rubric-r3.md`). There, the labellers worked blind and came from a different model family than the producer. The most reliable judge was a third family at high reasoning, while raising effort on the producer's own model did not help.

| Rule | R1 and R2 |
|---|---|
| Different family | Implementer is Claude; reviewer is `gemini-4-hydrogen-high` through `agy`. No second Gemini 4 seat fits the quota, so the operator breaks ties. |
| Blind | The reviewer gets the diff, the acceptance list and the touched tests, never the implementer's conclusion or evidence text. |
| No tools | `agy -p --model <id> --output-format json --json-schema <findings schema>`, sandboxed. The diff is in the prompt, not read from disk. |
| Objection round | The implementer answers each blocking finding once, with quotes from code or test output. The reviewer rules; a finding still open goes to the operator. |
| Fail closed | A finding is blocking until resolved. A malformed reviewer reply is rerun, never read as a pass. |
| Quota | R1 runs Wed morning and R2 Thu morning, both before P7 starts; the prompt carries the diff only. |

| Gate | Covers | Status | Due | Note |
|---|---|---|---|---|
| G0 | Plan approval | **PASS** | 2026-11-23 | Operator approved scope, target, reviewers, windows and class (c) handling |
| R1 | Review of P1a, P1b, P3, P4 | **PASS** | 2026-11-23 | `gemini-4-hydrogen-high`. Round 1: fail, 1 blocking (PR #7 defaults), 4 minor. Objection round with quotes and replay: all withdrawn. The ruling saw the quotes, not the diff again |
| G6 | P6 window, ADR-0027 live | pending | 2026-11-25 13:00-15:00 | operator-run |
| R2 | Review of P5 | pending | 2026-11-26 12:00 | `gemini-4-hydrogen-high`, D8; split checkpoint (D6) |
| G7 | P7 start | pending | 2026-11-26 14:00 | operator-run |
| G8 | P8 SHA posted | pending | 2026-11-27 17:00 | operator posts ("gửi") |

## Roadmap

| Phase | Name | Lane | Size | Depends on | Window | Acceptance (summary) |
|---|---|---|---|---|---|---|
| P0 | Approval and intake | tiny | 1 h | — | Mon 23 PM | Stories open, plan committed, `dev/us038` pushed |
| P1a | WAL test hotfix | high-risk | 1 h | P0 | Mon 23 PM | No test writes the live `monocle.db` |
| P2 | Port inventory | normal | 0.5 d | P0 | Mon 23 PM - Tue 24 12:00 | Every incoming `main` change classified |
| P1b | Test safety, rest | high-risk | 0.5 d | P1a | Tue 24 | Markers set; no marked test writes live data |
| P3 | ADR-0027 on FRA - Data/news | high-risk | 0.5 d | P1a, P2 | Tue 24 | HSG test without xfail; replay within D10 |
| P4 | Prefix files and catalog publish | normal | 0.5 d | P2 | Tue 24 PM | `--check-prefix` green; catalog in the FRA - Data/news manifest |
| P5 | v3 code, `x` columns, flag | high-risk | 2 d | P1a, P2 | Tue 24 - Thu 26 12:00 | v2 path unchanged with flag off |
| P6 | ADR-0027 live | high-risk | 0.5 d | R1 | Wed 25 13:00-15:00 | Two waves DONE; 0 partition errors from restart to end of 25/11 |
| P7 | `agy` cost sample | high-risk | 1 d | P6, R2 | Thu 26 14:00 - Fri 27 10:00 | Cost report |
| P8 | M1 package and SHA | normal | 0.5 d | P1-P7 | Fri 27 | SHA posted by 17:00 |

Pacing (operator, 2026-11-23): phases overlap. Each phase starts as soon as its dependencies pass; the windows and due times are latest-by deadlines, not start times. Flush windows still apply to daemon stops.

Parallel lanes: P1b, P3 and P4 run in one worktree lane (they feed R1). P5 runs in its own worktree from Tuesday morning and is the critical path.

---

## P0 — Approval and intake

Tasks:
1. Done 2026-11-23: operator approved (G0 PASS).
2. Done 2026-11-23, stories opened: US-056 test safety (P1a, P1b), US-057 ADR-0027 and catalog on FRA - Data/news (P2-P4, P6), US-058 article-compact-v3 code and cost (P5, P7).
3. Merge this plan into `dev/us038`; remove the untracked copy from `C:\src\news-scraper` afterwards.
4. Push `dev/us038` to `fpa` and `origin`.

Acceptance: stories in `harness.db`; plan committed; `dev/us038` pushed.

## P1a — WAL test hotfix (US-A)

Rule: FACT-tests-must-not-write-operational-db. `test_monocle_db_integrity_and_journal_mode` runs `audit_and_truncate_wal` on the hardcoded live `monocle.db` from a subprocess. The conftest `_guarded_connect` guard only covers the pytest process, so it does not stop this.

Tasks:
1. Rewrite the test to build a synthetic WAL database in `tmp_path` and run `audit_and_truncate_wal` on it.
2. Commit straight on `dev/us038` before any other phase branch is cut.

Acceptance:
- [x] `grep -rn "audit_and_truncate_wal" project/tests` shows only `tmp_path` targets.
- [x] The rewritten test passes, run alone.

Evidence: commit `1ff2dc5` on `dev/us038` (pushed with P0 later). The grep missed one more live write, the `audit_m4_m5_integrity.py` CLI run by a challenger test; P1b fixes it.

## P1b — Test safety, rest (US-A)

Tasks:
1. Cherry-pick `86b1e1a` (PARKED fixture, `min_free_gb = 0`).
2. Remove the remaining live writes in marked tests. `test_ops_store_reservation_queue_zero_held_in_ops_db` builds `OpsStore(paths.ops_db)` in a subprocess, which runs `PRAGMA journal_mode=WAL` and `executescript(SCHEMA)` on the live `ops.db`. Replace it with a `mode=ro` query. List the CLI scripts run through `clean_ops_env()` (`test_empirical_challenger_m2.py`) and confirm each only reads, or mark and stub it.
3. Register a `production_host` marker in `pytest.ini`. A marked test runs only when `NEWS_SCAPE_PRODUCTION_HOST=1` and the live DB exists, otherwise it skips with a reason. A marked test only reads.
4. Mark the tests that read a live path in the five challenger files (`test_empirical_challenger_m2.py`, `_m2_2_wave_concurrency.py`, `_m2_ops_queue.py`, `_m3_m5.py`, `_m4_1_grounding.py`).
5. Remove the personal OneDrive and SharePoint paths (`test_empirical_challenger_m3_m5.py:80-84`); resolve paths through `src.core.paths`.
6. Optional, only if Tuesday has time: extend the conftest guard to subprocesses through a `sitecustomize.py` on the `PYTHONPATH` that conftest sets.

Acceptance:
- [x] In the five challenger files, every `sqlite3.connect` on a live path uses `mode=ro`, and no `OpsStore(` runs on a live path (`grep`).
- [x] Full suite passes; result recorded in `docs/TEST_MATRIX.md` (1175 passed, 21 skipped at `8753312`).
- [x] No personal path remains in code, tests or config under `project/`. Two how-to documents and the reference folder `thamkhao/` still name the operator's machine paths; they are documentation, not code.
- [x] With `NEWS_SCAPE_PRODUCTION_HOST` unset, the five challenger files skip their live tests (21 skipped, 60 passed on the touched files).

Evidence: commits `cdc60ad` (cherry-pick of `86b1e1a`) and `8753312` on `m1/us056-test-safety`.
- Three more live writers fixed: the `audit_m4_m5_integrity.py` CLI gains `--read-only`; `verify_ops_queue.py` and the reservation test query `ops.db` read-only instead of building an `OpsStore`; the snapshot check reads an existing snapshot only.
- With `NEWS_SCAPE_PRODUCTION_HOST=1` the two `m3_m5` live tests pass on this host; the live WAL was not truncated.
- The marker lives in `conftest.py` (no `pytest.ini` exists). The optional subprocess guard (task 6) was not built.

## P2 — Port inventory

Read-only; may start before P1a.

Tasks:
1. Sparse clone of fpa-toolkit `main` (`packages/news` only); record the SHA. Re-check that `packages/news` is unchanged since `26abbd8d`.
2. Files to take:
   - ADR-0027 set from `9229581f`: `project/src/lakehouse/ingest.py`, `project/src/lakehouse/consolidator.py`, `docs/decisions/0027-*.md`, `project/tests/test_lakehouse_model_entities.py`.
   - v3 set from `01e117c2`: `project/src/agent/article_contract.py`, `project/src/agent/impact_contract.py`, `project/scripts/impact_labels.py`, `project/scripts/build_article_prefix.py`, `plugins/fpts-market-intel/tools/lakehouse_client.py`, `docs/decisions/0028-*.md`, `project/tests/test_impact_contract.py`, `project/tests/test_impact_labels.py`, `project/tests/test_plugin_lakehouse_client.py`.
   - The merged `project/assets/prefix/ARTICLE_SYSTEM_CORE.md`.
3. For each file, list every commit in `f1d655c..origin/main` besides `9229581f` and `01e117c2`. Known: `4e93cfe7` (naive timestamps as UTC), `4e216b47`, `06c05682`, `454c162d`, `90f4a403`.
4. Classify each extra change. (a) Safe: take it. (b) Changes production behaviour: needs a check in P3. (c) Imports a module missing on `dev/us038`: needs that module or an operator decision.
5. Known class (b), from the PR #7 hardening in `main`'s `ingest.py` and `consolidator.py`: `sentiment = ""` and no `"GOLD"` default for unanalysed rows; a hash fallback for an empty `article_id`; a timestamp suffix on fragment files; DuckDB in `TimeZone = 'UTC'` with `TRY_CAST` ordering. The `ingest.py` items reach the research path through `records_to_parquet_bytes`; the P3 replay measures them. The `consolidator.py` items touch only the sandbox path.
6. Check imports of every copied file resolve on `dev/us038`. Check that ADR-0027 and ADR-0028 pass `doc lint`, appear in `doc index`, and that `doc new --type adr` still allocates 0034.
7. Decide where P3 and P4 copy and where P5 copies: `article_contract.py`, `build_article_prefix.py` and `lakehouse_client.py` belong to P5 (v3 branch) unless a P3/P4 change needs them; record the split.

Acceptance:
- [x] Inventory table (file, extra commits, class, check, phase) under Evidence.
- [x] Class (c) items handled as approved at G0: none found, so no operator message is needed.

Evidence (2026-11-23, fpa-toolkit `main` `7c582c80`; `packages/news` unchanged since `26abbd8d`):

| File | Extra commits besides `9229581f`/`01e117c2` | Class | Check | Phase |
|---|---|---|---|---|
| `project/src/lakehouse/ingest.py` | `90f4a403` (PR #7: `sentiment ""`, `gold_status RAW`, `article_id` hash, fragment suffix) | b, both outputs | Research records pass through `sanitize_article_record`; measured by the P3 replay | P3 |
| `project/src/lakehouse/consolidator.py` | `90f4a403`, `4e93cfe7` (UTC) | b, sandbox only | Not used by the research path; covered by its tests | P3 |
| `docs/decisions/0027-*.md` | `a4b48bc9`, `4c8b7422` (accepted) | a | `doc lint` | P3 |
| `project/tests/test_lakehouse_model_entities.py` | none | a | runs in P3 | P3 |
| `project/scripts/build_article_prefix.py` | `454c162d` (sector rule and few-shot), merge resolutions | b, live prompt | v2 prompt gains the sector rule; prefix rebuilt and checked in P4. Drops production's trailing newline on the meta file (whitespace) | **P4** (needed for the v2 prefix) |
| `project/src/agent/article_contract.py` | `4e216b47`, `06c05682` (misassignment checks) | b, live validation | Lands with P5; live only at M3 | P5 |
| `project/src/agent/impact_contract.py`, `project/scripts/impact_labels.py` | none | a | v3 tests | P5 |
| `plugins/fpts-market-intel/tools/lakehouse_client.py`, `project/tests/test_plugin_lakehouse_client.py` | merge resolutions (`table` parameter) | a | plugin tests | P5 |
| `docs/decisions/0028-*.md` | ADR text commits only | a | `doc lint` | P5 |
| `project/tests/test_impact_contract.py`, `test_impact_labels.py` | none | a | run in P5 | P5 |
| `project/assets/prefix/ARTICLE_SYSTEM_CORE.md` | `078c1174` (regenerated on the sandbox catalog) | — | Not copied: P4 regenerates it from the live catalog | P4 |

Every `src`, `scripts` and `tools` import of the copied files resolves on `dev/us038`. No class (c) item.

## P3 — ADR-0027 on FRA - Data/news (US-B)

Tasks:
1. Copy the ADR-0027 set per P2, one commit.
2. Not needed: the research path already calls `keep_model_entities` through `records_to_parquet_bytes`. The HSG test in task 3 publishes through `production.publish` and proves it.
3. Change `test_master_db_migration_candidates_log_and_user_routing` (`project/tests/test_ner_entity_db_v2.py:259`): HSG is readable through `intent_code`; `include_mentions=True` does not return HSG. No xfail.
4. Amend ADR-0031.D4: `include_mentions` widens only to model-named `role = 'mentioned'` ids and never returns `CODE_ONLY` ids; cite ADR-0027.
5. Replay on a copy: the latest week of analysed records in a temp `MONOCLE_DATA_DIR`. Run the research publisher with old and new code into a temp `NEWS_SCAPE_RESEARCH_DB_DIR` and compare.

Acceptance:
- [x] `test_lakehouse_model_entities.py`, `test_ner_entity_db_v2.py`, `test_article_lane_hardening.py`, `test_research_production.py` pass (72 tests with the lakehouse files).
- [x] Replay report on the research output: rows per day, articles whose `entities` changed, `CODE_ONLY` ids removed, 10 hand-checked articles.
- [x] D10 holds: no lost row and no lost model-named id; no other field changed.
- [x] The PR #7 changes listed under Evidence, with the tests that cover them.

Evidence: commits `ece8f62` (whole-file copy) and `f85eba4` (HSG test, ADR-0034) on `m1/us057-adr0027`.
- ADR-0031 is accepted, so its body is frozen (K-R8). The D4 amendment is ADR-0034 (`amends: [ADR-0031]`), approved by the operator's commitment on issue #10.
- Replay: the live research master (read-only), days 2026-11-17 to 23, the same records through `sanitize_article_record` at `8753312` and at `ece8f62`.

| Measure | Value |
|---|---|
| Rows | 4,665 in, 4,665 out |
| Articles whose `entities` changed | 4,368 (94%) |
| Ids removed | 27,960, every one `CODE_ONLY` with role `mentioned` |
| Model-named ids lost | 0 |
| `sentiment`, `gold_status`, `article_id`, other fields changed | 0 |

- Hand check of 10 articles: removed ids are mostly matcher noise (`TICKER:MA1`, `TICKER:BAX`, `TICKER:HAN` on a housing story, sectors matched by keyword). A few plausible ids also go, such as `MACRO_GEO:DONG_NAM_A` on an ASEAN story; they stay in `intent_code`, the recall cost ADR-0027 accepts.
- PR #7 items: `day_records` always sets `sentiment`, `gold_status` and `article_id`, so the new defaults never fire on research rows. Covered by `test_lakehouse_contract_fixes.py`, copied from `main` in `ece8f62`.

## P4 — Prefix files and catalog publish (US-B)

Runs on the production host; the generator only reads `C:\data\news-scape\entities\entities.json`.

Tasks:
1. Take the merged `ARTICLE_SYSTEM_CORE.md` source changes per P2.
2. Run `project/scripts/build_article_prefix.py`. It writes `ARTICLE_SYSTEM_CORE.md`, `ARTICLE_SYSTEM_CORE.meta.json`, and the persona block of the preset under `.agents/dsh/presets/news-scape-conductor/`. Confirm with a diff that nothing else changed.
3. Run `build_article_prefix.py --check` and `article_run.py --check-prefix`.
4. Catalog publish (D9): the research publisher (`src/research_db/production.py`) copies `entities.json` to the FRA - Data/news target and adds its path, size and SHA-256 to `_manifest/latest.json`. The copy is skipped when the SHA-256 is unchanged. Test it on a temp target.

Acceptance:
- [x] `--check-prefix` green; meta hash matches the `.md`; the three prefix files in one commit.
- [x] SHA-256 and date of the live `entities.json` recorded under Evidence.
- [x] A publish to a temp target lists `entities.json` with the same SHA-256.

Evidence: commits `cfb4115` (prefix) and `fb365a1` (catalog publish) on `m1/us057-adr0027`.
- Live catalog: `entities.json` modified 2026-11-17 15:03, SHA-256 `485b4650a79fe7193363d46656b2ada9cf6dcbf6f4e89f82f1e5f9b9e1ffe81e`.
- New prefix hash `80c6edfe7891330b`, 20,972 characters. Its committed blob equals `main`'s `ARTICLE_SYSTEM_CORE.md` (`c54fd690`), so M2 needs only the new `.meta.json`.
- The catalog goes to `_catalog/entities.json` on FRA - Data/news; the manifest gains a `catalog` block. Tests: two new cases in `test_research_production.py` (16 pass).

## P5 — v3 code, `x` columns, flag (US-C)

Critical path, own worktree and branch, from Tue 24 morning after P1a and P2. Never merged into `dev/us038` before M3 (D2).

Tasks:
1. Copy the v3 set per P2, one commit; `test_impact_contract.py`, `test_impact_labels.py`, `test_plugin_lakehouse_client.py` pass.
2. Flag `article.contract: v2 | v3` in `project/config/ops.yaml`, default `v2`, read in one place.
3. Prefix by contract: replace the hardcoded v2 paths (`CORE_PATH` in `agy_runner.py:30`, `opencode_runner.py:30`, `openrouter_runner.py:31`; `PREFIX_PATH`, `PREFIX_META` in `prefix.py:21-22`). Generate `ARTICLE_SYSTEM_CORE_V3.md` and its meta with `--impacts` on this host. The DSH preset persona stays v2.
4. `check_prefix()` (`article_run.py:83`) checks the catalog side of both files, and the preset side for v2 only.
5. `validate_record` (`article_contract.py:513`) gets `impacts=True` when the flag is `v3`.
6. Stamps set where `agent_provider` and `model_used` are set (`article_contract.py:585`, `agy_runner.py:581`): `contract_version`, `rubric_version` (`r3` for v3, NULL for v2), `prompt_hash` from `prefix_hash()` of the active variant.
7. The four columns last in `LAKEHOUSE_ARTICLE_SCHEMA` per D4, filled in both outputs; `x` as a JSON string; `OBT_SCHEMA = "obt/3"`.
8. Tests: flag off gives byte-identical v2 output; flag on validates `x` and fills the stamps; `obt/2` and `obt/3` partitions read together (`union_by_name = true`).

Acceptance:
- [ ] All touched test files pass; full suite once before R2.
- [ ] Flag off: a replayed v2 batch gives the same rows as before P5, except the four new columns.
- [ ] R2 confirms new columns last, default `v2`, and no remaining hardcoded v2 prefix path.

Evidence: _(implementer fills in)_

## P6 — ADR-0027 live (operator-run)

Window: Wed 25, 13:00-15:00.

Tasks:
1. Before the window: write the rollback recipe (`git revert` of the P3 and P4 commits, rebuild prefix, restart, let the research publisher rewrite the touched partitions). Record the previous-week baseline from `ops.db` read-only: contract failures per wave, `CODE_ONLY` share, entities per article.
2. Stop the daemon; merge P1a, P1b, P3, P4 into `dev/us038`; restart. Record the restart time.
3. Watch 2 waves and the next research publishes: wave status, contract failures, publish errors, entities per article against the baseline.

Acceptance:
- [ ] Two waves DONE, no new failure class in traces.
- [ ] Before/after numbers recorded.
- [ ] Clean publish (operator's step 3 in issue #9), one criterion on FRA - Data/news: every `research.published` event from the restart to the end of 2026-11-25 reports 0 partition errors. The day mixes rows from before and after the restart; the operator accepts it as the evidence.
- [ ] The FRA - Data/news manifest lists `entities.json` with the SHA-256 from P4.

Evidence (window opened 2026-11-23 after the 17:50 research slot, under the operator's overlap pacing):
- Baseline, waves opened 2026-11-16 to 23 (`ops.db`, read-only): 422 DONE, 2 CANCELLED, 16,478 articles; 160 waves (38%) needed `repair1`. Replay baseline for `entities`: see P3.
- Procedure: `ops_daemon.py send /pause`; wait for no active wave; `git merge --ff-only m1/us057-adr0027` in `C:\src\news-scraper`; `schtasks /End` then `/Run` on `news-scape-ops`; `send /resume`.
- Rollback recipe: `send /pause`; in `C:\src\news-scraper` revert the code commits `fb365a1 cfb4115 f85eba4 ece8f62` (newest first); run `build_article_prefix.py --sync-preset`; restart the task; mark the days published since the restart dirty (`master.mark_dirty`) so the research publisher rewrites them; `send /resume`.

## P7 — `agy` cost sample (operator-run)

Method (D7): v3 runs from the P5 branch on a sample of live articles in a temp `MONOCLE_DATA_DIR`. The v2 arm is the live traces of the same articles, so v2 is not rerun.

Tasks:
1. Set `NEWS_SCAPE_RESEARCH_DB_DIR` and `NEWS_SCAPE_PUBLISH_DIR` to temp directories (safety rule 10). Pick N ≈ 400 articles from DONE waves opened after the P6 restart and before Thu 26 12:00, stratified by source in proportion to live volume. Copy them read-only into the temp directory.
2. Run v3 through `agy` (`gemini-3.8-flash-low`, the production runner) in batches of the live wave size, at the daemon's concurrency, inside the L1 batch limit.
3. From the agent span attrs (`usage.input_tokens`, `output_tokens`, `total_tokens`, `latency_s`, `runner_status`, `attempts`) and repair steps: per-article tokens, time per article, contract failure, repair and retry rates, for v2 and v3.
   Tokens are the primary measure. Time per article is a reference only: v2 comes from live daemon waves, and v3 runs as a separate batch beside the running daemon.
4. Project to one day at the measured volume and at the 2026-11-18 peak (6,077 articles); state N, the host, the model and the spend.

Acceptance:
- [ ] Report with N, source spread, per-article and per-day figures at both volumes, failure rates, host and spend; tokens marked primary and time marked as reference, with the measurement conditions.
- [ ] No write to the live data directory (guard from P1b; temp `MONOCLE_DATA_DIR`).
- [ ] Breaker stayed `CLOSED` and no live wave ended `PARKED`, or the stop is recorded.

Evidence: _(operator fills in)_

## P8 — M1 package and SHA

Fri 27; message ready for "gửi" by 15:00, posted by 17:00.

Tasks:
1. Worktree from the `dev/us038` head; branch `import/clean-20261127`; merge the P5 branch (merge commit). Skip the merge if D6 split applies.
2. Restore `docs/SESSION-LATEST.md` and the machine-local `.gitignore` lines to their `f1d655c` versions, one commit.
3. Run `~/.claude/skills/issue-reply-workflow/scripts/overlap.py` against base `f1d655c` and the current fpa-toolkit `main`; expected conflict only `scripts/git_hooks/pre-commit`.
4. Push to `fpa`. Draft one message on issue #10 with:
   - the four items DucNN asked for: files changed, tests run and results, files changed on both sides, decisions needed;
   - the P7 report; v3 stays off until M3; the HSG xfail can be removed; ADR-0027 is `accepted`;
   - ADR-0027 coverage: the research path reaches `keep_model_entities` through `records_to_parquet_bytes`, so `main`'s code applies to FRA - Data/news unchanged. `production.py` changes in this sync only for the catalog publish (D9);
   - one line each on side threads. Issue #8: catalog published to FRA - Data/news with its SHA-256; no external dropzone producer, since `dev_id` is the analysis runner name. PR #7 and issue #5: content now in production through P3, so both can close.
5. Post after "gửi".

Acceptance:
- [ ] Overlap numbers in the message match the script output.
- [ ] Message reviewed by the operator before posting.

Evidence: _(implementer fills in)_

## After M1 (follow-up plan, not in scope)

- M3 enable: set `article.contract: v3` in an approved window; watch 3 waves against the P7 projection; test the rollback once.
- Merge the P5 branch into `dev/us038` before M3, and bump `obt/3` live then.
- `low-confidence` flag on non-ticker `direction` in the reading skills and `lakehouse_client` (ADR-0028 consumer rule), before v3 data reaches readers.
- Re-consolidate published history under ADR-0027.
- PR `import/clean-20261120` → news-scraper `main`; close PR #7 and issue #5.

## Verification

- Each phase: touched test files, then one full-suite run before its review, recorded in `docs/TEST_MATRIX.md`.
- Data safety: P1a and P1b remove every live write from tests; P7 writes only to temp directories.
- Schedule: gate due times; split decision recorded at the R2 row on Thu 26 12:00.
- Sync: P8 overlap result; M2 result from DucNN (`--check-prefix` green, HSG xfail removed).

## Out of Scope

- Everything under "After M1".
- Move of production to the server.
- Alias fixes: VIC "Vinpearl", TCB "TCBS"/"Chứng khoán Kỹ thương", DGC "Đức Giang".
- `build_entities.py` failure on FRA data (`DataFrame has no attribute 'ticker'`).
- New shared name cores `fpt telecom` (FOX/FPT) and `sai gon - ha noi` (SHB/SHS).
- New gold set for non-ticker `direction` (fpa-toolkit side).

## Risks

| Risk | Mitigation |
|---|---|
| No buffer: any slip moves M1 | Split checkpoint Thu 26 12:00 (D6); issue table updated the same day |
| P5 wiring larger than estimated | Exact touch list; starts Tue morning in its own worktree; R2 scoped to that list |
| A test writes live data from a subprocess | P1a first; P1b removes the known live writers and checks the rest by `grep`; subprocess guard optional |
| ADR-0027 removes more than expected on FRA - Data/news | P3 replay on the research records: only `CODE_ONLY` ids removed |
| Copied files change published rows (`sentiment`, `gold_status`, dedup) | P2 class (b); P3 replay; D10 thresholds |
| P7 competes with the daemon for `agy` quota and spends money | N ≈ 400; breaker watch and stop rule; spend in the report |
| A sample is challenged as not "real volume" | D7: live sizing and concurrency, projection to the peak, live confirmation at M3 |
| Reviewer misses a defect the implementer shares | D8: different model family, blind input, objection round, tie-break seat |
| Laptop sleep or update during P6 or P7 | Disable sleep and defer updates for the window |

## G0 decisions (2026-11-23)

1. Windows confirmed: P6 Wed 25 13:00-15:00; P7 Thu 26 14:00 - Fri 27 10:00.
2. P2 class (c) items: sent to the operator in one message by Tue 24 12:00; the phase continues without the file until decided.
3. Target: FRA - Data/news only; the sandbox is legacy.
4. Models: `gemini-4-hydrogen-high` for R1 and R2, `gemini-3.8-flash-low` for P7; nothing else on `agy`.
