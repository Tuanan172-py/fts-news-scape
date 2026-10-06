---
id: ADR-0007
type: adr
title: Silver watermark integrity and the silver_failures table
status: accepted
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh (commit author)]
approvers: [operator 2026-09-17]
story: [US-016]
related: [ADR-0013]
evidence:
  - commit:0f1a65c
  - path:plans/20260917-1420-pipeline-integrity-remediation/phase-01-silver-watermark-integrity.md
  - path:project/src/pipeline/derive.py
  - path:project/src/db/store.py
  - path:project/scripts/pipeline_radar.py
  - test:project/tests/test_silver_watermark_integrity.py
  - metric:7203 articles captured versus 424 past the delivery gate, end-to-end review 2026-09-17
  - metric:7402 Bronze files times 3 reads per cycle on OneDrive, 2026-09-17
original: "commit:0f1a65c"
reconstructed: 2026-10-06
summary: The Silver derive watermark becomes a low-water mark that never passes an unresolved failure; failures go to a new silver_failures table with a 5-attempt dead-letter threshold, and the radar must show dead-letters.
summary_vi: Watermark Silver chuyển sang low-water mark không vượt qua bài lỗi chưa giải quyết, sổ lỗi silver_failures với ngưỡng dead-letter 5 lần, và radar phải hiện số dead-letter.
---

# ADR-0007 — Silver watermark integrity and the silver_failures table

## Context

- The end-to-end review of 2026-09-17 found silent data loss in the Silver layer.
- In `src/pipeline/derive.py`, `_should_process` selected a file only when `fetch_ts > watermark` (lines 51 to 57).
- The new watermark was `max(ok_ts)`, the maximum over successful files only (line 130).
- Failed files (`continue` at lines 115 to 117, `raw_missing`, `raw_read_error`) did not contribute to `ok_ts`.
- Example: file A with `fetch_ts` 10:00 fails and file B at 11:00 succeeds. The watermark jumps to 11:00 and A never satisfies `> watermark` again.
- There was no warning, no attempt counter and no dead-letter, only one log line.
- A second leak: an article with `silver_ok=False` but `pkg_ok=True` still returned `res["ok"]=True` (`run.py:122`). The watermark advanced and the article was never derived again.
- Architectural impact: the Bronze "no article left behind" work (US-011, US-012, US-015) was voided one layer later. Bronze kept the article, Silver dropped it, and it never reached L1, Gold or a user.
- Related measurement: 7,203 articles captured, 424 articles past the delivery gate.

```python
def _should_process(fetch_ts, watermark):     # lines 51-57
    return fetch_ts > watermark

watermark_new = max(ok_ts) if ok_ts else watermark    # line 130, max over successes ONLY
```

## Decision

- D1. The watermark uses low-water-mark semantics. If unresolved failures remain, `watermark_new` is the minimum `fetch_ts` of failures not yet dead-lettered. If none remain, it is `max(ok_ts)`. The watermark MUST NOT pass an unresolved failure.

```
watermark_new = min(fetch_ts of failures NOT yet dead-lettered)   if failures remain
              = max(ok_ts)                                         if clean
```

- D2. New table `silver_failures` in `monocle.db` (schema change, Hard Gate). The reverse risk of D1 is head-of-line blocking, where one permanently broken file stalls Silver. A durable failure ledger with a give-up threshold is therefore mandatory.

| Column | Type | Meaning |
|---|---|---|
| `meta_path` | TEXT PK | Path of the `.meta.json`, relative to `PROJECT_ROOT` |
| `url_title_hash` | TEXT | Link to `articles` when it can be resolved |
| `fetch_ts` | TEXT | Timestamp used to hold the watermark |
| `attempts` | INTEGER | Attempts so far, incremented each derive cycle |
| `last_error` | TEXT | Latest error message |
| `last_at` | TEXT | ISO timestamp, `+07:00` |
| `dead_letter` | INTEGER | 0 or 1; at 1 the row stops holding the watermark |

- D2a. The dead-letter threshold is 5 attempts, aligned with `deferred_max_attempts` of the backfill.
- D2b. A file that succeeds MUST be deleted from the table so no residue accumulates.
- D3. Dead-letters MUST be visible. `pipeline_radar.py` MUST show "Bronze articles stuck or dead-lettered in Silver: N" with a `HIGH` recommendation when N is above 0. A silent dead-letter recreates the very bug being fixed, so this is a mandatory acceptance condition, not an option.

## Alternatives

| Option | Why rejected |
|---|---|
| JSON blob in `pipeline_state`: no schema change, lane `normal`, immediate | The operator chose a separate table so failures can be queried and reported. A JSON blob is hard to filter by domain or time, hard to join with `articles`, and grows inside one cell. |
| Keep `max(ok_ts)` and add an "always retry" list | Still a failure ledger in a different place; it does not recover files the watermark already passed in earlier runs. |
| Drop the watermark and rescan everything each cycle | 7,402 files times 3 reads per cycle on OneDrive; this was already the current performance bottleneck. |

## Consequences

Gains:

- No silent path for losing articles between Bronze and Silver remains. Every drop has a queryable record and shows on the radar.

Risks to manage:

- Head-of-line blocking if the threshold is too high or the ledger breaks, which stalls Silver. Mitigation: log at ERROR level when the watermark is held for more than 2 consecutive cycles.
- Backlog on the first run, which may pull back many previously skipped articles. A dry run on a copy of the database MUST come first to size the volume.
- Migration: the table is created with `CREATE TABLE IF NOT EXISTS` in `ArticleStore`. Old tables are untouched and no data is lost. A backup of `monocle.db` is still mandatory before the first run.

Acceptance tiers defined by the original ADR:

| Tier | Condition |
|---|---|
| Unit | A failed file older than a successful file is selected again next cycle (fails on the old code) |
| Unit | After 5 attempts `dead_letter=1` and the watermark may advance |
| Unit | A successful file is deleted from `silver_failures` |
| Integration | Broken and good Bronze files interleaved over several runs; no article disappears |
| Platform | Real morninger run, 2 consecutive derive cycles, radar shows the dead-letter count |

The story reaches `implemented` only with the Platform tier (rule 06 §4.4).

### Current status (2026-10-06)

- D1 in force. `derive.py` records failures through `store.record_silver_failure` and holds the watermark on blocking rows.
- D2 and D2a in force. `DEFAULT_MAX_ATTEMPTS = 5` in `derive.py` cites this ADR.
- D3 in force. `pipeline_radar.py` reads `silver_failures` and counts blocking and dead-letter rows.
- ADR-0013 builds on this ADR: a URL may end only as `captured`, `alias`, `gone` or `dead_letter` with a reason.

## Rollback

- The original ADR names no rollback procedure. Reverting the `derive.py`, `run.py` and `store.py` changes of commit 0f1a65c restores `max(ok_ts)` and with it the silent loss (reconstructed from the commit file list).
- The `silver_failures` table is additive; leaving it in place does not affect old tables. The mandated pre-run backup of `monocle.db` is the data restore point.
- Under the high-risk lane (`AGENTS.md` §0) a rollback needs operator approval.

## Follow-up

- [x] Low-water mark, `silver_failures` and radar line shipped with tests in commit 0f1a65c (US-016).
- [ ] Platform tier: two consecutive real derive cycles with the dead-letter count on the radar. Its status was not verified during normalization; check `harness_cli.py query matrix` for US-016.
