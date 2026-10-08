---
id: US-028
type: story
title: Antigravity CLI runner and headless trigger for Article Lane
status: implemented
lane: high-risk
created: 2026-09-25
updated: 2026-10-06
lang: en
authors: [unknown]
adr: [ADR-0011]
plan: []
evidence: [commit:dd1e709, commit:a068c59, path:project/src/agent/agy_runner.py, path:project/scripts/article_tick.py, test:project/tests/test_agy_runner.py, test:project/tests/test_article_tick.py]
verify: "pytest project/tests/test_agy_runner.py project/tests/test_article_tick.py"
reconstructed: 2026-10-06
summary: The Article Lane can run waves through the Antigravity CLI as a single-turn, zero-tool sandboxed runner, selected with article_run --runner agy and triggered headlessly by article_tick.
---

# US-028 — Antigravity CLI runner and headless trigger for Article Lane

## Contract

- `AgyRunner` MUST call the Antigravity CLI single-turn, with zero tools, under a sandbox profile (reconstructed from the harness.db row and ADR-0011).
- `article_run --runner agy` MUST select this runner for a wave.
- `article_tick` MUST provide a hybrid headless trigger, so a wave starts without an interactive DSH session.

## Acceptance Criteria

- [x] `AgyRunner` runs single-turn, zero-tool, with a sandbox profile.
- [x] `article_run` accepts `--runner agy`.
- [x] `article_tick` provides the hybrid trigger.
- [x] Unit tests pass 100%.

## Design Notes

- Decision in ADR-0011; the harness.db `product_contract` cites only that ADR.
- Commit dd1e709 adds `agy_runner.py` (631 lines), `article_tick.py` (425 lines), their tests and ADR-0011.
- Commit a068c59 makes `--analyze` delegate to `cmd_prepare` when the wave manifest is missing.
- ADR-0017 later placed every provider, agy included, under one output contract with agy as the reference.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/test_agy_runner.py project/tests/test_article_tick.py` | pass (harness.db `unit_proof=1`) |
| Integration | none recorded | harness.db `integration_proof=0` |
| Platform | `article_tick --status` | verified; AST check passed |

## Evidence

- Commit dd1e709 (2026-09-25), "architechture headless agy"; commit a068c59 (2026-09-25) runner fix. Neither message names US-028.
- harness.db story row US-028; no trace row.
