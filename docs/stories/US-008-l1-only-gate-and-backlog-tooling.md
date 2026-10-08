---
id: US-008
type: story
title: L1-only export gate, L1/Gold backlog drain tooling and lost module recovery
status: retired
lane: high-risk
created: 2026-09-07
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010]
related: [US-002, US-007]
evidence: ["commit:e4d281a", "path:project/src/export/user_output.py", "path:project/scripts/l1_backlog.py", "path:project/docs/operations/backlog-drain-runbook.md", "metric:355 tests passed (baseline 263)", "metric:424 gated master rows, GOLD 384, L1_ONLY 40"]
verify: "cd project; python -m pytest tests/ -q"
original: "commit:e4d281a"
reconstructed: 2026-10-06
summary: User delivery gated on L1 only with Gold as optional enrichment, five ingest and runner bugs fixed, backlog drain tooling added and lost modules recovered from bytecode; retired by ADR-0010.
---

# US-008 — L1-only export gate, L1/Gold backlog drain tooling and lost module recovery

## Contract

- The `final.csv` delivered to users MUST require only L1 DoD; Gold is optional enrichment.
- An article without Gold is still delivered with empty Gold fields and `gold_status=L1_ONLY`, and upgrades to `GOLD` on a later round.
- Gold tokens MUST NOT be spent on an article without L1, because it cannot be routed to any user.
- Purpose of the file: a full reconciliation record for later sessions (what changed, from what to what, which proof, what is still owed).
- Read it before editing `user_output.py`, `runner.py`, `catalog.py` or the batch flow.

## Acceptance Criteria

- [x] Export gate is `l1_outputs.dod_pass=1` only: INNER JOIN on L1 and LEFT JOIN on Gold, with the latest Gold row chosen by subquery `MAX(id)`.
- [x] `FINAL_COLUMNS` has 16 columns, adds `gold_status` (`GOLD` or `L1_ONLY`) after `event_type`, and drops `materiality_score` from the user deliverable.
- [x] `_checkpoint.json` records `gold_status` per article and still reads the legacy list format.
- [x] The noise filter reads no Gold field.
- [x] Gold export requires L1 by default (`--require-l1`).
- [x] Five bugs in `agent_ingest.py`, `runner.py` and `l1_ingest.py` are fixed, each with a test.
- [x] Backlog tooling exists: `l1_backlog.py`, `l1_route.py --only` and `--mini-batch`, L1 batch packets, runbook.
- [x] Full suite passes: 355 tests.

## Design Notes

### Contract changes (breaking)

- Gate before: `l1_outputs.dod_pass=1` AND `agent_outputs.dod_pass=1`, two INNER JOINs, no `ORDER BY`, so the Gold row was random on fan-out.
- Gate after: L1 only; Gold is a LEFT JOIN, and the latest row is chosen deterministically.
- `agent_outputs` is UNIQUE on `(article_id, raw_sha256)`, so a re-captured article has several DoD rows. The real DB had 50 such articles; 424 articles produced 447 raw rows.
- `FINAL_COLUMNS`: `date, matched_entities, title, summary, key_points, implication, impact_area, time_sensitivity, sentiment, event_type, gold_status, url, source_domain, article_id, agent_provider, model_used`.
- `materiality_score` stays in `agent_outputs.output_json` and in the `materiality_score` column of `_master/<date>_agent.csv`.
- Missing `agent_provider` or `model_used` becomes an empty string instead of the invented `"unknown"`.
- `MASTER_COLUMNS` is `FINAL_COLUMNS` plus `noise_signals`, only in `_master/<date>.csv`.

### Output paths (flat)

```
users/output/<user>/<YYYY-MM-DD>.csv          users/output/<user>/_checkpoint.json
users/output/_master/<YYYY-MM-DD>.csv         _master/<date>_L1.csv   _master/<date>_agent.csv
```

- There is no nested `<date>/` folder and no file named `final.csv`. User folders have no `L1.csv` or `agent.csv`.

### Checkpoint

```jsonc
// before: { "written": { "2026-08-18": ["<aid>", ...] } }
// after : { "written": { "2026-08-18": { "<aid>": "GOLD" | "L1_ONLY" } } }
```

- The old list format still loads (empty status). `ckpt.filter_upgraded()` was added. The log reads `rows=N (new=X upgraded=Y l1_only=Z)`.
- The checkpoint does not decide output content. Idempotency comes from a full rewrite, `os.replace` and `article_id` dedupe.
- Its real role is a delivery ledger: the only source for "which articles are new" and "which just received Gold".

### Noise filter without Gold

- Before: specific entity OR `materiality.score >= 0.6` OR alias in title. After: specific entity OR alias in title.
- Required because the gate is L1-only: an article without Gold always scored 0, so the materiality branch halved the effect of the looser gate.
- The constraint is recorded in `.agents/rules/entity-system-invariants.md`: "The filter MUST NOT read any Gold field."
- `_silver_noise_signals()` adds the `noise_signals` column (`alias_title`, `alias_body`, `body_len`, `code_in_symbols`, `cats`) for observation only, not gating yet.

### L1 before Gold, enforced by structure

- `Catalog.claim(require_l1=False)`, then `AgentRunner.export_tasks(require_l1=True)` by default, then `agent_export.py --require-l1` or `--no-require-l1`.
- Cadence effect: `run_daily.ps1` ran `agent_export` BEFORE `l1_ingest`, so new articles without `l1_outputs` waited for the next round.
- No article is lost (`work_items` stays `pending`). Catching up the same day needs two agent rounds.

### `materiality_score` scale is 0 to 1

- `agent-output-v1` sets `minimum:0, maximum:1`. The `3/5` scale trace was removed from `entity-system-invariants.md`, and `02-financial-domain-rules.md` forbids other scales.

### CORE and DETAIL model

- Principle: separate the STORAGE contract from the DELIVERY contract.

| Tier | Who | Fields | Role |
|---|---|---|---|
| Bronze/Silver | code | `article_id, title, url, source_domain, date, cleaned_text` | CORE, always present |
| L1 | agent | `entities[].entity_id` + `in_list`, `categories` | CORE, hard gate |
| Gold | agent | `summary.abstractive`, `summary.key_points`, `citations` at least 2 | CORE, soft gate |
| Gold | agent | `implication`, `materiality`, `sentiment`, `event_type` | DETAIL |

- `agent-output-v1` was NOT changed: a data contract change is a high-risk hard gate needing an ADR and human approval. Hiding a delivery column is cheap and reversible in one line.

### Bugs fixed

| # | File | Symptom | Cause |
|---|---|---|---|
| 1 | `scripts/agent_ingest.py` | `NameError: done_aids` on the first DoD-passing Gold output | variable never initialized (`l1_ingest.py` had it) |
| 2 | `scripts/agent_ingest.py` | raw output carrying a `dod_pass` key bypassed all DoD | branch `... if "dod_pass" not in item else item` |
| 3 | `src/agent/runner.py` | L1 to Gold chaining (rule 05 §2.5) silently dead, `l1_entities` always `[]` | read `e.get("code")`; L1 schema has only `entity_id` (0/399 entities had `code`) |
| 4 | `src/agent/runner.py` | `wp` unbound, `NameError`, whole export round broken | missing `continue` after `mark_failed` |
| 5 | `scripts/l1_ingest.py` | agent returning a whole batch in one file failed silently | JSON array not unpacked |

- Bug 1 explains 304 `work_items` stuck in `claimed`: each ingest run processed one article and then crashed.

### Backlog drain tooling

- `scripts/l1_backlog.py` (read-only) inventories T1 to T4 plus stuck `claimed`, and prints the command chain.
- `scripts/l1_route.py` gained `--only {all,gold-ready,in-articles}` and `--mini-batch N`.
- `src/agent/batch_handoff.py` gained `build_l1_batch_packet` and `split_l1_tasks_into_batches`. L1 batches hold 25 articles (titles only, 13.5 KB per batch) versus Gold 5 to 10 (with `cleaned_text`).
- `.agents/skills/l1-entity-matcher/SKILL.md` §5 gained batch mode and five traps that break DoD.
- `project/docs/operations/backlog-drain-runbook.md` is a four-step runbook.

### Backlog figures (real DB, 2026-09-07)

| Group | Articles | Meaning |
|---|---|---|
| Passed gate | 424 | GOLD 384, L1_ONLY 40 |
| T1 gold-ready | 423 | Gold done, L1 missing; running L1 delivers at once with 0 Gold tokens |
| T2 l1-only | 6,372 | neither L1 nor Gold (473 already have a waiting packet) |
| T3 gold-next | 40 | L1 present, `work_item` pending |
| T4 orphan | 467 / 261 / 417 | no row in `articles`, so never deliverable |
| stuck `claimed` | 304 (232 without Gold, present in `articles`) | `claim()` reads only `pending`; no reclaim exists |

- Loosening the gate added only 40 articles. The real bottleneck was L1, not Gold. 17 batch packets were issued for the 423 T1 articles.

### Data-loss incident (must read)

- During the session, untracked files vanished from disk several times; the cause is unknown. No delete command ran, the Recycle Bin was empty, and `git log --all` had nothing.
- Recovered from `__pycache__/*.cpython-314.pyc`:

| File | Fidelity |
|---|---|
| `src/agent/archive.py`, `manifest.py`, `batch_handoff.py` | exact bytecode match (function names, parameters, defaults, constants) |
| `src/agent/pruner.py` | match except one blank docstring line |
| `tests/test_pruner_and_batch.py`, `test_batch_manifest.py` | rebuilt from pytest-rewritten `.pyc`; behavior-equivalent, not original |
| `scripts/l1_backlog.py` | rewritten from scratch (lost after creation, before commit) |

- Lost for good (markdown has no `.pyc`): `docs/stories/US-004-newest-first-batch-processing.md`, `US-006-task-batch-manifest-and-archive.md`, `US-007-gold-task-payload-optimization.md`, `project/daily_log.txt`, `project/data/reports/daily/tnck-2026-09-07.md`.
- Comments and formatting of the four modules are NEW, not original. Logic was checked against bytecode; comment wording was not.
- `.pyc` files are not a backup. They were overwritten after recovery, so the comparison proof exists only in that run's output.
- Deliberately not committed (still in `HEAD`, recoverable with `git restore`): `okf/catalog/configurations/monocle_config.md`, `users/subscriptions/AnPT_news.csv`, `users/subscriptions/_template_news.csv`.
- `AnPT_news.csv` is the user's watchlist source (`compile.py` reads `users/subscriptions/`); without it `compile_users.py --all` has no source.

### Debt left open

1. `gated_rows()` got heavier: `_GATED_SQL` pulls `a.content_text` only to feed `noise_signals`. It was 1.1 MB, and about 11.8 MB per run after the L1 backlog drains, even with `--date today`.
2. Batch packets are never cleaned: `archive_completed_tasks` moves only `<article_id>.task.json`. Old `batch_XX.task.json` and `l1_batch_XX.task.json` remain, so agents may reprocess finished articles.
3. 304 `work_items` stuck in `claimed` since 2026-08-17, with no reclaim. 232 articles stay invisible to the Gold queue.
4. T4 leak: Bronze and Silver create work packages but do not write `articles` (678 articles already paid to agents). Trace `orchestrator` and `derive`.
5. 25 documentation drifts. The worst is `project/docs/design/14-entity-system-and-mapping.md:76-77` (noise filter with `materiality_score >= 3`).
6. Also: 11 places state nested paths (including `AGENTS.md:80`), 5 still say "two-layer gate", and `design/12-agent-infrastructure.md:44` still lists `confidence >= 0.65` as a DoD predicate.

### Status

- Depends on US-002 (partially superseded) and US-007 (files lost, see incident).
- Retired: ADR-0010 ended the two-tier L1/Gold lane, the `gold_status` delivery model and the L1 backlog tooling. Delivery now follows the Article Lane.
- Reconstructed: the `harness.db` row US-008 describes a different story ("L1 and radar operations optimization", 2026-09-15). The id was reused; this file is the 2026-09-07 story.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; .venv\Scripts\python.exe -m pytest tests/ -q` | passed, 355 (session baseline 263) |
| Integration | `.venv\Scripts\python.exe scripts/write_user_output.py --date all` | passed, 424 `_master` rows (GOLD 384, L1_ONLY 40), AnPT 146 |
| Integration | `.venv\Scripts\python.exe scripts/l1_route.py --only gold-ready --all --mini-batch 25` | passed, 423 articles in 17 batch packets, 13.5 KB per batch |
| Integration | `.venv\Scripts\python.exe scripts/l1_backlog.py` | passed, prints T1 to T4 plus stuck `claimed` |
| Platform | none; needs a real L1 agent to process packets | not run |

## Evidence

- The file cites commit `9c06234` (79 files, +3824/-1161, 355 tests passed). That hash does not resolve in the current repository; the content is reachable through commit e4d281a.
- Ten new tests: `gold_status` GOLD/L1_ONLY, `test_multiple_gold_rows_picks_latest`, `test_noise_filter_broad_entity_no_gold_dependency`, `test_l1_only_export_fallback_empty_gold`, `test_export_requires_l1_by_default`.
- Also new: `test_export_embeds_l1_entity_ids`, `test_ingest_single_output_no_nameerror`, `test_output_carrying_dod_pass_key_is_not_trusted`, `test_checkpoint_records_gold_status_and_upgrade`, `test_checkpoint_reads_legacy_list_format`.
- Harness delta: this story file was created after the fact (the earlier session had none, against `docs/HARNESS.md`).
- `docs/TEST_MATRIX.md` gained the US-008 row and noted that US-003 never had a row and US-004, US-006, US-007 lost their files. US-002 was marked partially superseded. `docs/SESSION-LATEST.md` was overwritten.
- Trace outcome: completed. Friction: untracked files vanished repeatedly; recovery used `.pyc` files matching Python 3.14.3 magic.
- Further friction: `.pyc` files were overwritten during comparison, losing the `pruner.py` proof. Too many untracked files meant git could not help, so everything was committed.
