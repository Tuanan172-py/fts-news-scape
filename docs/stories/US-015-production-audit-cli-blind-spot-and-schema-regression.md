---
id: US-015
type: story
title: "Production audit: CLI and subprocess blind spot, schema enum regression, cycle budget"
status: implemented
lane: high-risk
created: 2026-09-17
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: [ADR-0010]
related: [US-011, US-012]
evidence: ["commit:0f1a65c", "path:project/schemas/work-package-v1.schema.json", "test:project/tests/test_cli_entrypoints.py", "metric:413 tests passed (from 403, plus 10 CLI subprocess tests)", "metric:backfill fetched=14 failed=1 deleted_at_source=1 budget_stopped=1"]
verify: "cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q"
original: "commit:0f1a65c"
summary: Every automation CLI entry point is tested through subprocess, the work-package schema accepts deleted_at_source, backfill has a time budget and capture has measured headroom.
---

# US-015 — Production audit: CLI and subprocess blind spot, schema enum regression, cycle budget

## Contract

- The system MUST run with a measured safety margin.
- Every CLI entry point on the automation path MUST be tested for real through subprocess.
- A new `capture_status` value MUST NOT block articles at Silver.
- The capture interval MUST keep headroom over the measured cycle duration.

## Acceptance Criteria

- [x] `work-package-v1.schema.json` accepts `deleted_at_source`.
- [x] `backfill_deferred.py` has `--budget-seconds`, stops cleanly between two articles and still prints its report.
- [x] `morninger` passes `encoding="utf-8"` to both subprocess calls and guards against `stdout=None`.
- [x] `capture_interval_minutes: 10`, about 40% headroom over a job round of about 7 minutes.
- [x] `deferred_backfill_limit` falls from 200 to 60; the subprocess timeout is budget plus 60s.
- [x] `tests/test_cli_entrypoints.py` has 10 tests covering 9 automation scripts.
- [x] The radar shows both today's count and the cumulative total for articles deleted at source.

## Design Notes

### Five live bugs found by running for real

| # | Bug | Origin | Why 403 green tests missed it |
|---|---|---|---|
| 3 | `__doc__.split("\n")[1]` raises `IndexError` on the first line (one-line docstring) | pre-existing | tests import `main()` via `importlib`, never through `__main__` |
| 4 | `UnicodeEncodeError` when printing Vietnamese with stdout as a pipe | pre-existing | tests do not run through subprocess |
| 5 | `capture_interval_minutes: 5` is shorter than the measured cycle of 335s | US-011 | no test measures cycle duration |
| 6 | auto-drain `--limit 200` hits the 180s timeout every cycle | US-011 | tests use fake HTTP with no real rate-limit cost |
| 7 | `subprocess.run(text=True)` without `encoding` gives `stdout=None`, then `AttributeError` | US-011 | no test crosses the subprocess boundary |
| 8 | `deleted_at_source` violates the enum of `work-package-v1.schema.json`, so articles are `held` at Silver | US-011 | no test validates a work package with the new value |

- Bug 3 did the most damage. Auto-drain, the main feature of US-011, crashed on the first line of every call.
- The crash was swallowed into `logger.warning`, so the feature was reported "done" without ever running once.

### Lesson: the US-011 lane was wrong

- In US-011 the agent judged a new `capture_status` value "additive, backward-compatible, not a public data contract change". It chose lane `normal` and no ADR.
- In fact `project/schemas/work-package-v1.schema.json:23` validates that enum, and every flagged article was blocked at the Silver gate.
- Per `FEATURE_INTAKE.md` §2 this is a data-contract flag, a hard gate, lane `high-risk`. Adding an enum value is a contract change when a consumer validates it.

### Root cause: a systemic blind spot

- 52 scripts have a `__main__` block, and 0 tests used `subprocess`. Bugs 3, 4 and 7 sat entirely in that blind spot.
- `project/tests/test_cli_entrypoints.py` closes it: it runs `--help` of 9 automation scripts through subprocess with `capture_output=True`, reproducing the pipe and encoding conditions of `morninger`.
- The test caught bug 7 within its first few minutes.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q` | passed, 413 (from 403) |
| Integration | same command; CLI tests run the real scripts through subprocess | passed, 10/10 |
| E2E | `backfill_deferred.py --fetch --mode all --budget-seconds 45` | passed, `fetched=14 failed=1 deleted_at_source=1 budget_stopped=1`, exit 0 |
| Platform | restart `python -m src.morninger` | passed, log `capture/10min (+backfill_deferred nối tiếp), derive/30min, l1_route/15min, drift/6:0` |

- The platform tier was paid for the first time; it was the missing proof of US-011.

## Evidence

- Auto-drain ran in full for the first time (11:10:59):

```
[backfill] hết ngân sách 45s — dừng sạch, phần còn lại để chu kỳ sau
backfill [all]: candidates=60 fetched=14 failed=1 deleted_at_source=1 budget_stopped=1
```

- The radar confirmed the flag reached the DB: "0 bài đăng hôm nay / 1 tổng tích lũy" (0 published today, 1 cumulative).
- This also shows a metric filtered by `published_at` under-reports, because deletions are usually detected after the publish date.
- `morninger` restarted at 11:16:34 with the schedule above (from the `harness.db` row).
- Harness delta: backlog #8. `harness_cli.py intake` declares 9 `--type` values in argparse, but the DB CHECK constraint accepts only 6.
- So `qa_inquiry`, `diagnostic` and `exploration` (all valid per `FEATURE_INTAKE.md` §1) always failed. Found while recording intake for this story.
- Trace #49: `score_trace = 1.0`, `score_context = 1.0`. Outcome: completed.
- The `l1_route/15min` job in the platform log was later removed by ADR-0010; the rest of the story stays in force.
