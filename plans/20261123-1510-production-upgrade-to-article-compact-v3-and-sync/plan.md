---
id: PLN-20261123-1510-production-upgrade-to-article-compact-v3-and-sync
type: plan
title: Production upgrade to article-compact-v3 and sync M1 for fpa-toolkit
status: draft
lane: high-risk
created: 2026-11-23
updated: 2026-11-23
lang: en
authors: [agent]
adr: [ADR-0031, ADR-0033]
story: []
evidence:
  - "url: https://github.com/Research-FPA/news-scraper/issues/10#issuecomment-7090987629 (roadmap M0-M3)"
  - "url: https://github.com/Research-FPA/news-scraper/issues/10#issuecomment-7095092085 (AnPT commits M1 to 2026-11-27, agrees to the 5-point x spec)"
  - "commit: f1d655c (common base with fpa-toolkit main 0d0cf3c1)"
  - "url: fpa-toolkit 9229581f (ADR-0027 code), 01e117c2 (article-compact-v3), main e2d37ae4 (packages/news unchanged since 26abbd8d)"
  - "path: project/tests/test_empirical_challenger_m2_2_wave_concurrency.py:108 (runs audit_and_truncate_wal on the live monocle.db, hardcoded path)"
  - "metric: ops.db ops_waves, agy DONE articles per day 2026-11-16..23: 2003, 5497, 6077, 685, 794, (no waves 21-22), 1183; waves of ~60 articles take 2-5 min"
  - "metric: ops.db ops_spans agent attrs carry usage.input_tokens, output_tokens, total_tokens, latency_s, prefix_hash per batch"
  - "operator: 2026-11-23 keep ADR-0027; upgrade to v3 on the current laptop production host; server move after M3; audit approach agreed"
summary: Plan for every open AnPT item from news-scraper issue 10, in gated phases from test safety through the M1 sync SHA on 2026-11-27 to v3 enabled in ops_daemon, written for handoff to implementing agents.
---

# PLN-20261123-1510 — Production upgrade to article-compact-v3 and sync M1

## Context

Step 2 of the fpa-toolkit integration is merged (fpa-toolkit PR #610, merge `0d0cf3c1`, ancestor `f1d655c`). DucNN folded the rest into one sync round (issue #10):

| Milestone | Owner | Done when | Date |
|---|---|---|---|
| M1 | AnPT | One SHA on `import/clean-<date>` carrying ADR-0027 on production, regenerated prefix files, HSG test and ADR-0031.D4 amendment, challenger test markers, `x` columns, and an `agy` cost report | **2026-11-27 (committed on the issue)** |
| M2 | DucNN | `satellite_sync pull`, xfail on HSG removed, `--check-prefix` green, merged | 1 working day after M1 |
| M3 | AnPT approves, DucNN confirms | v3 flag on in `ops_daemon` config, v3 running | After M2 |

All work runs on the current laptop production host. Today is Monday 2026-11-23; M1 leaves 4.5 working days and no buffer.

State at audit time (2026-11-23):
- `dev/us038` local head `3d85247` (whitespace trim), not pushed: `fpa` and `origin` are at `3931ac9`.
- `86b1e1a` (PARKED fixture fix) is on `import/clean-20261120` but not on `dev/us038`.
- PR `import/clean-20261120` → news-scraper `main` (promised in issue #10, answer 3) is not open.
- fpa-toolkit `main` is `e2d37ae4`; `packages/news` has not changed since `26abbd8d`. Against base `f1d655c`: 21 files changed on production, 117 under `packages/news` on `main`, 14 on both sides, 13 merge cleanly, 1 conflict (`scripts/git_hooks/pre-commit`, take `main`).
- ADR-0027 is `accepted` (2026-11-15) on `main`; DucNN's comments still say "proposed". The M1 message states the real status.
- `main` carries the v3 contract and the prefix generator (`build_article_prefix.py --impacts` writes `ARTICLE_SYSTEM_CORE_V3.md`), but no runner wiring, no stamps and no reader flag. The wiring is new work on this side (P5).

Thread history that binds this plan (news-scraper issues):

| Thread | State | What it leaves for this plan |
|---|---|---|
| #5 satellite integration, PR #7 handback | Both open | PR #7 (`task/monorepo-satellite-init`) predates the one-way flow (D2) and is superseded by the step-2 sync. Its contract hardening already sits in `main`'s `ingest.py` and `consolidator.py`, so P3 brings it in (P2 class b). |
| #8 ADR-0027 landed | Open, unanswered | Four asks: check the prefix against the live catalog (P4); publish `entities.json` with its SHA-256 in the manifest; notify dropzone producers; re-consolidate published partitions. P8 answers all four. |
| #9 ADR-0028 approval | Closed | The operator's own step 3: ADR-0027 is live when one publish day through `publish.py` passes without error (P6). Step 4: v3 is enabled only after the `agy` measurement at real volume and operator approval (P7, P9). The 429 was a spending limit, so P7 spends real money. |
| #10 step 2 and roadmap | Open | M1 to M3 above; the 5-point `x` spec. |

The live catalog `C:\data\news-scape\entities\entities.json` dates from 2026-11-17. The sandbox copy DucNN rebuilt from dates from 2026-09-14. `publish.py` does not publish the catalog, so fpa-toolkit cannot run the catalog side of `--check-prefix` for M2 without it.

## Decisions

- D1. Keep ADR-0027: `entities` carries only model-named ids; `CODE_ONLY` stays in `intent_code`. ADR-0031.D4 is amended to match.
- D2. One-way flow: `dev/us038` → `import/clean-<date>` → news-scraper `main`. Never merge fpa-toolkit `main` or news-scraper `main` back into `dev/us038`.
- D3. Port by whole-file copy: a file needed from fpa-toolkit is taken byte-for-byte from `main` (`git show origin/main:packages/news/<path>`). It also brings every other `main` change in that file; each such change is listed and checked (P2).
- D4. `x` is stored as a nullable JSON string. Four new columns go last in `LAKEHOUSE_ARTICLE_SCHEMA`: `x`, `contract_version`, `rubric_version`, `prompt_hash`. `processed_at`, `runner` and `model` reuse `analyzed_at`, `agent_provider` and `model_used`. `OBT_SCHEMA` moves `obt/2` → `obt/3`; old partitions read NULL.
- D5. v3 replaces the v2 pass (no extra run), stays inside the L1 batch limit, and is off by default behind one config flag.
- D6. The server move happens after M3 and is out of scope here.
- D7. Deadline and split. M1 ships on 2026-11-27. Split checkpoint: **2026-11-26 12:00**. If R2 (review of P5) has not passed by then, AnPT updates the roadmap table on issue #10 the same day, and the 2026-11-27 SHA carries P1, P3, P4 and P6 only. P5 and P7 then go in a second round.
- D8. "Real volume" (ADR-0028 condition 3) means v3 runs on every article of one real production window, not on a sample projected to a day. The v2 arm comes from the live traces of the same articles after P6, so v2 is not rerun.
- D9. Reader rule from the ADR-0028 approval (agreed 5-point spec, item 5): `lakehouse_client` flags `direction` on non-ticker entities in `x` as `low-confidence`. This is part of M1 (P5). The new gold set stays out of scope.
- D10. Gate load fits 4.5 days. Two independent reviews: R1 (P1, P3, P4) and R2 (P5). Operator gates: G0, G6 (window), G7 (start of the measurement), G8 ("gửi"), G9.
- D11. The catalog travels with M1. The M1 message gives the SHA-256 of the live `entities.json` the prefix was built from. Whether `publish.py` also publishes the catalog (issue #8) is an operator decision at G0; publishing it lets M2 run the catalog side of `--check-prefix`.

## Design

ADR-0027 and ADR-0028 live in fpa-toolkit `packages/news/docs/decisions/` and arrive in this repo in P3 and P5. The flow has three parts:

1. Make tests safe first (P1a hotfix before any full-suite run), and list what the copies bring (P2).
2. Land ADR-0027 with its prefix (P3, P4) and go live with it (P6). In parallel, add v3 behind a flag that stays off (P5), merged live with the flag off in a second window.
3. Measure v3 on the articles that live v2 processed after P6 (P7), package one SHA (P8), and turn v3 on after DucNN merges (P9).

## Safety rules for every implementing agent

1. Never write under `C:\data\news-scape` from tests, scripts or analysis. Set `MONOCLE_DATA_DIR` to a temp directory. Scripts that write (`build_entities.py`, replays, the P7 batch) also get `--out` in a temp directory. Live databases are opened read-only (`file:...?mode=ro`).
2. **No full-suite run, in any worktree, on a base without P1a.** P1a is the first commit on `dev/us038`; every phase branch is cut after it.
3. WIP=1 per worktree (ADR-0022). Each phase runs in its own worktree from `dev/us038`; never check out in the production worktree `C:\src\news-scraper` while the daemon runs.
4. No bare `git stash`; park work as a commit.
5. Run only the test files a phase touches, then the full suite once before its review.
6. Every commit follows `docs/GIT_COMMIT_STANDARD.md` and names its story.
7. Nothing is posted to GitHub without the operator's word "gửi".
8. The live daemon is stopped only in the P6 and P6b windows, outside the flush windows in `config/ops.yaml` (07:15-07:45, 08:15-08:40, 12:15-12:45, 15:15-15:45, 17:15-17:45).
9. P7 shares the `agy` account with the daemon. It runs throttled and stops if the `agy` provider breaker leaves `CLOSED` or a live wave ends `PARKED`.

## Review process

| Step | Who | Output |
|---|---|---|
| 1. Implement | Implementing agent | Commits on the phase branch, evidence block filled in this plan (phase section, "Evidence") |
| 2. Self-check | Implementing agent | Each acceptance item ticked with the command and its result |
| 3. Independent review (R1, R2) | A second agent that did not implement, given the diff and the acceptance list, not the implementer's conclusion | Findings list; blocking findings fixed and re-reviewed |
| 4. Operator gate | AnPT | PASS / FAIL written in the gate table, with date |

| Gate | Covers | Status | Due | Note |
|---|---|---|---|---|
| G0 | P0 plan approval | pending | 2026-11-23 | Approach agreed 2026-11-23; text sign-off pending |
| R1 | Review of P1, P3, P4 | pending | 2026-11-25 11:00 | Independent agent |
| G6 | P6 window, ADR-0027 live | pending | 2026-11-25 13:00-15:00 | operator-run |
| R2 | Review of P5 | pending | 2026-11-26 12:00 | Split checkpoint (D7) |
| G7 | P7 start | pending | 2026-11-26 14:00 | operator-run |
| G8 | P8 SHA posted | pending | 2026-11-27 17:00 | operator posts ("gửi") |
| G9 | P9 v3 enabled | pending | after M2 | operator-run |

## Roadmap

| Phase | Name | Lane | Size | Depends on | Window | Acceptance (summary) |
|---|---|---|---|---|---|---|
| P0 | Plan approval and intake | tiny | 1 h | — | Mon 23 PM | Stories open, plan `approved`, plan committed |
| P1a | WAL test hotfix | high-risk | 1 h | P0 | Mon 23 PM | No test writes the live `monocle.db` |
| P1b | Test safety, rest | high-risk | 0.5 d | P1a | Tue 24 | No test touches live data |
| P2 | Port inventory | normal | 0.5 d | P0 | Mon 23 PM - Tue 24 AM | Every incoming `main` change listed and classified |
| P3 | ADR-0027 port | high-risk | 0.5 d | P1a, P2 | Tue 24 | HSG test passes without xfail; replay report |
| P4 | Prefix files (v2) | normal | 2 h | P2 | Tue 24 PM | `--check-prefix` green |
| P5 | v3 wiring, `x` columns, flag, reader flag | high-risk | 2 d | P1a, P2 | Tue 24 - Thu 26 12:00 | v2 path unchanged with flag off |
| P6 | ADR-0027 live | high-risk | 0.5 d | R1 | Wed 25 13:00-15:00 | Two waves DONE, before/after numbers |
| P6b | P5 live with flag off | high-risk | 1 h | R2, P6 | Thu 26 13:00-14:00 | Two waves DONE, `obt/3` partitions readable |
| P7 | `agy` cost measurement | high-risk | 1 d | P6, R2 | Thu 26 14:00 - Fri 27 10:00 | Cost report at real volume |
| P8 | M1 package and SHA | normal | 0.5 d | P1-P7 | Fri 27 | SHA posted by 17:00 |
| P9 | M3 enable v3 | high-risk | after M2 | P8, M2 | after M2 | v3 live, rollback tested |

Parallel lanes: P1b, P3 and P4 run in one worktree lane (they feed R1); P5 runs in its own worktree from Tuesday morning. P5 is the critical path.

---

## P0 — Plan approval and intake

Tasks:
1. Operator signs off this text, answers the open questions at the end, sets `status: approved`.
2. Open stories with `harness_cli.py doc new --type story`: US-A test safety (P1a, P1b), US-B ADR-0027 on production (P2-P4, P6), US-C article-compact-v3 on production (P5, P6b, P7, P9). Write their ids into `story:` above.
3. Commit this plan on a branch and merge it into `dev/us038`; remove the untracked copy from the production worktree `C:\src\news-scraper` afterwards.
4. Push `dev/us038` (`3d85247`) to `fpa` and `origin`.
5. Not gating M1: settle PR #7 first. It is superseded by the step-2 sync, and its content reaches production through P3. Draft a closing note for PR #7 and issue #5; post after "gửi". Then open the PR `import/clean-20261120` → news-scraper `main` (merge commit, no squash), as promised in issue #10 answer 3.

Done already: the M1 date reply on issue #10 (comment `7095092085`, 2026-11-23).

Acceptance: stories exist in `harness.db`; plan committed; `dev/us038` pushed.

## P1a — WAL test hotfix (US-A)

Rule: FACT-tests-must-not-write-operational-db. Problem: `test_monocle_db_integrity_and_journal_mode` in `test_empirical_challenger_m2_2_wave_concurrency.py` runs `audit_and_truncate_wal` on the hardcoded `C:\data\news-scape\monocle.db` (a write). `MONOCLE_DATA_DIR` does not redirect it.

Tasks:
1. Rewrite the test to build a synthetic WAL database in `tmp_path` and run `audit_and_truncate_wal` on it.
2. Commit straight on `dev/us038` before any other phase branch is cut.

Acceptance:
- [ ] `grep -rn "audit_and_truncate_wal" project/tests` shows only `tmp_path` targets.
- [ ] The rewritten test passes; it is run alone, not through the full suite.

Evidence: _(implementer fills in)_

## P1b — Test safety, rest (US-A)

Problem: the five challenger files (`test_empirical_challenger_m2.py`, `_m2_2_wave_concurrency.py`, `_m2_ops_queue.py`, `_m3_m5.py`, `_m4_1_grounding.py`) read hardcoded live paths. `test_empirical_challenger_m3_m5.py:80-84` hardcodes personal OneDrive and SharePoint paths, already copied to fpa-toolkit `main`. On Linux the suite creates a relative `C:\data\news-scape/` directory (suspect: `test_empirical_challenger_m2_ops_queue.py:127` `paths.data_dir.mkdir`, not yet reproduced). `test_article_lane_hardening.py` and `conftest.py` only name the live path as a forbidden target; they stay.

Tasks:
1. Cherry-pick `86b1e1a` (PARKED fixture, `min_free_gb = 0`) onto `dev/us038`.
2. Register a `production_host` marker in `pytest.ini`. A test with it runs only when `NEWS_SCAPE_PRODUCTION_HOST=1` and the live DB exists; otherwise it skips with a reason. A marked test may only read, never write.
3. Mark every test in the five challenger files that reads a live path.
4. Remove the personal paths; resolve paths through `src.core.paths`.
5. Reproduce the stray directory: run each challenger file with `MONOCLE_DATA_DIR` unset and `DEFAULT_DATA_ROOT` patched to a temp path, record which file creates it. Then make `paths.data_root()` raise when running under pytest without `MONOCLE_DATA_DIR`, and add a regression test.

Acceptance:
- [ ] With a filesystem watcher on `C:\data\news-scape` (daemon running, no rename), the full suite creates, opens for write, or modifies nothing there.
- [ ] `grep -rn "Users\\\\anpt" project/` returns nothing.
- [ ] The stray-directory source is named with the reproducing command.
- [ ] Full suite result recorded in `docs/TEST_MATRIX.md`.

Evidence: _(implementer fills in)_

## P2 — Port inventory

Goal: know exactly what whole-file copies bring in, before any copy. Read-only; may start before P1a.

Tasks:
1. Sparse clone of fpa-toolkit `main` (`packages/news` only), record the SHA used (expected `e2d37ae4` or later; re-check that `packages/news` is still unchanged since `26abbd8d`).
2. Files to take:
   - ADR-0027 set from `9229581f`: `project/src/lakehouse/ingest.py`, `project/src/lakehouse/consolidator.py`, `docs/decisions/0027-*.md`, `project/tests/test_lakehouse_model_entities.py`.
   - v3 set, `packages/news` part of `01e117c2`: `project/src/agent/article_contract.py`, `project/src/agent/impact_contract.py`, `project/scripts/impact_labels.py`, `project/scripts/build_article_prefix.py`, `plugins/fpts-market-intel/tools/lakehouse_client.py`, `docs/decisions/0028-*.md`, `project/tests/test_impact_contract.py`, `project/tests/test_impact_labels.py`, `project/tests/test_plugin_lakehouse_client.py`.
   - The merged `project/assets/prefix/ARTICLE_SYSTEM_CORE.md`.
3. For each file, `git log f1d655c..origin/main -- packages/news/<file>` and the diff against `f1d655c`; list every commit besides `9229581f` and `01e117c2`. Known at planning time: `4e93cfe7` (consolidation reads naive timestamps as UTC), `4e216b47` and `06c05682` (misassignment checks), `454c162d` (sector few-shot), `90f4a403` (lakehouse contract fixes).
4. Classify each extra change. (a) Safe: take it. (b) Changes production behaviour: needs a check in P3 or P6. (c) Imports a module missing on `dev/us038`: needs that module or an operator decision.
5. Check imports of every copied file resolve on `dev/us038`.
6. Check that the imported ADR-0027 and ADR-0028 (ids issued in fpa-toolkit; this repo has 0029-0033 but no 0027/0028) pass `harness_cli.py doc lint` and appear in `doc index`, and that `doc new --type adr` still allocates 0034.
7. Known class (b) items, from the PR #7 hardening carried in `main`'s `ingest.py` and `consolidator.py`:
   - an unanalysed row gets `sentiment = ""` instead of `"neutral"`, and `gold_status` from the record instead of a `"GOLD"` default;
   - an empty `article_id` gets a hash fallback instead of collapsing in deduplication;
   - fragment file names get a timestamp suffix;
   - DuckDB runs with `TimeZone = 'UTC'`, and `updated_at` is ordered through `TRY_CAST`.

   Each one changes published rows read by the per-user Excel delivery and by Research, so each gets a replay check in P3.

Acceptance:
- [ ] Inventory table (file, extra commits, class, check needed) added under Evidence.
- [ ] No class (c) item left without a decision from the operator (asked in one message, by Tue 24 12:00).
- [ ] `4e93cfe7` has a concrete check defined: partition dates of a replayed sample before and after.

Evidence: _(implementer fills in)_

## P3 — ADR-0027 port (US-B)

Tasks:
1. Copy the ADR-0027 set per P2, one commit.
2. Change `test_master_db_migration_candidates_log_and_user_routing` (`project/tests/test_ner_entity_db_v2.py:259`): HSG is readable through `intent_code`; `include_mentions=True` does not return HSG. No xfail.
3. Amend ADR-0031.D4: `include_mentions` widens only to model-named `role = 'mentioned'` ids and never returns `CODE_ONLY` ids; cite ADR-0027. Record it under `amends`/references through the harness CLI rules.
4. Replay check on a copy: take the latest week of analysed records into a temp `MONOCLE_DATA_DIR`, export with old and new code, compare the `entities` column. Report: articles changed, `CODE_ONLY` ids removed per article, 10 hand-checked articles.

Acceptance:
- [ ] `test_lakehouse_model_entities.py`, `test_ner_entity_db_v2.py`, `test_article_lane_hardening.py`, `test_plugin_lakehouse_client.py` pass.
- [ ] Replay report attached; no model-named id lost.
- [ ] `4e93cfe7` check from P2 run on the same replay: partition dates unchanged, or every change explained.
- [ ] The same replay compares `sentiment`, `gold_status`, `article_id` and the row count per day. Every difference is explained, and the operator accepts the published-output change before P6.

Evidence: _(implementer fills in)_

## P4 — Prefix files, v2 (US-B)

Runs on the production host. The generator only reads `C:\data\news-scape\entities\entities.json`, so an agent on this host runs it; the operator approves the diff in R1. Depends on P2 only, not on P3.

Tasks:
1. Copy the merged `ARTICLE_SYSTEM_CORE.md` source changes from `main` (generator and prompt text per P2).
2. Run `project/scripts/build_article_prefix.py`. It writes `project/assets/prefix/ARTICLE_SYSTEM_CORE.md`, `ARTICLE_SYSTEM_CORE.meta.json`, and the persona block of the preset under `.agents/dsh/presets/news-scape-conductor/`. Confirm with a diff that nothing outside those three changed.
3. Run `build_article_prefix.py --check` and `article_run.py --check-prefix`.

Acceptance:
- [ ] `--check-prefix` green; meta hash matches the `.md`.
- [ ] The three files committed together in one commit.
- [ ] SHA-256 and date of the live `entities.json` recorded under Evidence (D11).

Evidence: _(implementer fills in)_

## P5 — v3 wiring, `x` columns, flag, reader flag (US-C)

Critical path. Starts Tue 24 morning in its own worktree after P1a and P2; must pass R2 by Thu 26 12:00 (D7).

Tasks:
1. Copy the v3 set per P2, one commit; `test_impact_contract.py`, `test_impact_labels.py` and `test_plugin_lakehouse_client.py` pass.
2. Flag `article.contract: v2 | v3` in `project/config/ops.yaml`, default `v2`, read in one place.
3. Prefix selection. Replace the hardcoded v2 paths with a lookup by contract: `CORE_PATH` in `src/agent/agy_runner.py:30`, `opencode_runner.py:30`, `openrouter_runner.py:31`, and `PREFIX_PATH`/`PREFIX_META` in `src/agent/prefix.py:21-22`. Generate `ARTICLE_SYSTEM_CORE_V3.md` and its meta with `build_article_prefix.py --impacts` on this host. The DSH preset persona stays v2 (`agy` reads the core file directly).
4. Prefix check. `check_prefix()` in `scripts/article_run.py:83` checks the catalog side of both v2 and v3 files and the preset side for v2 only.
5. Validation. The call to `validate_record` (`src/agent/article_contract.py:513`) passes `impacts=True` when the flag is `v3`.
6. Stamps, set by the runner where `agent_provider` and `model_used` are set (`article_contract.py:585`, `agy_runner.py:581`): `contract_version` (`article-compact-v2` or `-v3`), `rubric_version` (`r3` for v3, NULL for v2), `prompt_hash` from `prefix_hash()` of the active variant (16 hex, already logged per batch as `prefix_hash`).
7. Schema. Add the four columns last in `LAKEHOUSE_ARTICLE_SCHEMA` (`project/src/lakehouse/ingest.py`) per D4; fill them in record conversion; `x` serialized as a JSON string. `OBT_SCHEMA = "obt/3"` in `project/src/research_db/production.py`.
8. Reader flag (D9). `lakehouse_client.py` marks `direction` of `x` items whose group is not a ticker as `low-confidence`; test it.
9. Tests: flag off gives byte-identical v2 output and schema-compatible Parquet; flag on validates `x` through `impact_contract` and fills the stamps; an `obt/2` partition reads with NULLs next to `obt/3` (`read_parquet(..., union_by_name = true)`).
10. Draft the notice to the Research team (ADR-0030 `research_publish`): four NULL columns and `obt/3` from P6b on. Post only after "gửi".

Acceptance:
- [ ] All touched test files pass; full suite once before R2.
- [ ] Flag off: a replayed v2 batch produces the same rows as before P5, except the four new columns (`x`, `rubric_version` NULL; `contract_version`, `prompt_hash` filled).
- [ ] R2 checks schema order (new columns last), the default `v2`, and that no path still hardcodes the v2 prefix.

Evidence: _(implementer fills in)_

## P6 — ADR-0027 live (operator-run)

Window: Wed 25, 13:00-15:00 (between the 12:15 and 15:15 flush windows).

Tasks:
1. Before the window: write the rollback recipe (`git revert` of the P3 and P4 commits, rebuild prefix, restart) and record the previous-week baseline from `ops.db` read-only (contract failures per wave, `CODE_ONLY` share, entities per article).
2. Stop the daemon; merge P1a, P1b, P3, P4 into `dev/us038`; restart. P5 is not merged here.
3. Watch 2 waves: wave status, contract failures, `CODE_ONLY` share, entities per article versus the baseline.
4. Record the restart time: it opens the P7 article window.

Acceptance:
- [ ] Two waves DONE, no new failure class in traces.
- [ ] Before/after numbers recorded.
- [ ] One publish day through `publish.py` passes without error after the restart (operator's step 3 in issue #9). The first eligible publish window is 2026-11-25 or the morning of 2026-11-26.

Evidence: _(operator fills in)_

## P6b — P5 live with flag off (operator-run)

Window: Thu 26, 13:00-14:00, after R2 passes.

Tasks:
1. Stop the daemon; merge P5 into `dev/us038` with `article.contract: v2`; restart.
2. Watch 2 waves; open the newest partition and check the four columns are present, last, and NULL where expected.
3. Rollback: `git revert` of the P5 merge, restart.

Acceptance:
- [ ] Two waves DONE; `obt/3` partition reads next to `obt/2` through `lakehouse_client`.

Evidence: _(operator fills in)_

## P7 — `agy` cost measurement at real volume (operator-run)

Method (D8): v3 runs on every article that live v2 analysed between the P6 restart and a cut-off. Expected ~800-1,200 articles at current volume. The v2 arm is the live traces of the same articles (same prefix, same ADR-0027 code), so only v3 is run.

Tasks:
1. Fix the article set: ids from `ops_wave_articles` of DONE waves opened after the P6 restart and before the cut-off (Thu 26 12:00). Copy those articles read-only into a temp `MONOCLE_DATA_DIR`.
2. Run v3 through `agy` on that set in the temp directory, in batches of the same size as live waves, inside the L1 batch limit, throttled per safety rule 9.
3. From `ops_spans` agent attrs (`usage.input_tokens`, `output_tokens`, `total_tokens`, `latency_s`, `runner_status`, `attempts`) and repair steps: per-article input and output tokens, time per article, contract failure, repair and retry rates, for v2 (live) and v3 (temp).
4. Project to one day at the measured volume and at the 2026-11-18 peak (6,077 articles); name the host (current laptop) and the `agy` model.

Acceptance:
- [ ] Report with N, source spread, per-article and per-day figures at both volumes, failure rates, and the host.
- [ ] No write to the live data directory during the batch (watcher from P1b).
- [ ] Breaker stayed `CLOSED` and no live wave ended `PARKED` during the run, or the run was stopped and the stop recorded.

Evidence: _(operator fills in)_

## P8 — M1 package and SHA

Fri 27; message ready for "gửi" by 15:00, posted by 17:00.

Tasks:
1. Worktree from the `dev/us038` head; branch `import/clean-20261127`.
2. Restore `docs/SESSION-LATEST.md` and the machine-local `.gitignore` lines to their `f1d655c` versions, one commit.
3. Run `~/.claude/skills/issue-reply-workflow/scripts/overlap.py` against base `f1d655c` and the current fpa-toolkit `main`; expected conflict only `scripts/git_hooks/pre-commit`.
4. Push to `fpa`. Draft the issue #10 message with the four items DucNN asked for: files changed, tests run and results, files changed on both sides, decisions needed. Attach the P7 report; state that ADR-0027 is `accepted`, that v3 stays off until M3, and that the HSG xfail can be removed.
5. Draft one reply on issue #8 that closes its four asks:
   - prefix checked against the live catalog, with the catalog SHA-256 (D11);
   - catalog publishing, as decided at G0;
   - the dropzone producers notified (list or "none besides this pipeline");
   - re-consolidation of history: out of scope here, own story.
6. Post both messages after "gửi".

Acceptance:
- [ ] Overlap numbers in the message match the script output.
- [ ] Issue #8 reply drafted with all four asks answered.
- [ ] Message reviewed by the operator before posting.

Evidence: _(implementer fills in)_

## P9 — M3 enable v3 (after M2, operator-run)

Tasks:
1. After DucNN merges M2, set `article.contract: v3`, restart the daemon in an approved window.
2. Watch 3 waves: cost per wave against the P7 projection, contract failures, `x` fill rate.
3. Rollback: flag back to `v2`, restart. Test the rollback once on a single wave before leaving v3 on.
4. Post approval on issue #10; DucNN confirms.

Acceptance:
- [ ] v3 running, figures within the P7 projection or explained.
- [ ] Rollback tested.

Evidence: _(operator fills in)_

## Verification

- Each phase: touched test files, then one full-suite run before its review, recorded in `docs/TEST_MATRIX.md`.
- Data safety: P1b watcher check repeated before P6 and during P7.
- Schedule: gate table due times; split decision recorded at the R2 row on Thu 26 12:00.
- Sync: P8 overlap result; M2 result from DucNN (`--check-prefix` green, HSG xfail removed).

## Out of Scope

- Move of production to the server (after M3, own plan).
- Alias fixes: VIC "Vinpearl", TCB "TCBS"/"Chứng khoán Kỹ thương", DGC "Đức Giang" (after M3, own story).
- `build_entities.py` failure on FRA data (`DataFrame has no attribute 'ticker'`).
- New shared name cores `fpt telecom` (FOX/FPT) and `sai gon - ha noi` (SHB/SHS).
- New gold set for non-ticker `direction` (fpa-toolkit side). The `low-confidence` reader flag is in scope (D9).
- Re-consolidation of published history under ADR-0027 (ADR-0027 follow-up).

## Risks

| Risk | Mitigation |
|---|---|
| No buffer: any phase slip moves M1 | Split checkpoint Thu 26 12:00 (D7); issue table updated the same day |
| P5 wiring larger than estimated | Exact touch list in P5; starts Tue morning in its own worktree; R2 scoped to that list |
| A full-suite run truncates the live WAL | P1a first; safety rule 2 |
| Whole-file copies bring unreviewed `main` changes (UTC consolidation) | P2 inventory and P3 replay check |
| ADR-0027 on live data drops more than expected | P3 replay before P6; rollback recipe |
| P7 competes with the daemon for `agy` quota (5 quota/429 events in the 7 days to 2026-11-23) | Throttle, breaker watch, stop rule (safety rule 9) |
| Low volume after P6 gives a thin v3 set | Projection to the 6,077 peak; cut-off may extend to Thu 26 14:00 |
| `obt/3` reaches Research readers unannounced | Notice drafted in P5, posted before P6b |
| Copied `ingest.py`/`consolidator.py` change `sentiment`, `gold_status` and dedup on published rows | P2 class (b) list; P3 replay on those columns; operator accepts before P6 |
| M2 `--check-prefix` cannot run without the catalog | D11: catalog SHA-256 in the M1 message; publishing decision at G0 |
| The P7 v3 run spends real money (the earlier 429 was a spending limit) | Bounded to one window of articles; spend reported with the cost figures |
| PR #7 merged by mistake on news-scraper `main` | P0 closes it as superseded before the `import/clean` PR opens |
| Laptop sleep or update during P6, P6b, P7, P9 | Disable sleep and defer updates for the window |
| Numbers measured on the laptop differ after the server move | Report names the host; rerun a small A/B after the move |

## Open questions for the operator (answer at G0)

1. Independent reviewer for R1 and R2: which agent or model.
2. Confirm the windows: P6 Wed 25 13:00-15:00, P6b Thu 26 13:00-14:00, P7 Thu 26 14:00 - Fri 27 10:00.
3. Who posts the Research notice for `obt/3`, and to which channel.
4. P2 class (c) items: decide per item when the inventory is ready (by Tue 24 12:00).
5. Catalog publishing (issue #8, D11): should `publish.py` also publish `entities.json` with its SHA-256 in the manifest, in M1 or later?
6. PR #7 and issue #5: close both as superseded by the step-2 sync?
7. Dropzone producers (issue #8): is this pipeline the only producer, or were others (for example `dev_id antigravity`) notified?
