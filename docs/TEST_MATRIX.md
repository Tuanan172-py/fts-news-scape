# TEST_MATRIX.md — Evidence vocabulary + live proof table (news-scape, H1)

Golden rule: **"No proof = not implemented."** A claim without a mechanical result is a plan, not a fact.
At H1 this table is hand-maintained (a known friction — moves to a DB query at H2).

## Status enum

| Status | Meaning |
|--------|---------|
| `planned` | Story exists, not started. |
| `in_progress` | Being worked (WIP=1 — only one at a time). |
| `implemented` | Reached ONLY via a real validation command that ran + is recorded. Never hand-flipped. |
| `changed` | Previously implemented, since modified (needs re-proof). |
| `retired` | Removed / superseded. |

## Proof tiers

| Tier | For news-scape means |
|------|----------------------|
| **Unit** | Pure-function tests (parsers, dedup hash, sentiment rules) — `pytest tests/`. |
| **Integration** | Scraper → parse → dedup → store against captured fixtures. |
| **E2E** | A full cycle (`scripts/run_once.py <domain>`) or `verify_quality.py`. |
| **Platform** | Runtime/ops (scheduler, WAL, graceful shutdown, health check). |

A tier is `1` (passed, evidence recorded), `0` (not passed/not run), or `—` (N/A for this story).

## Live proof table

| Story | Parent/Epic | Status | Unit | Integ | E2E | Platform | Evidence |
|-------|-------------|--------|:----:|:-----:|:---:|:--------:|----------|
| [US-001](stories/US-001-gold-agent-output-contract.md) | Phase 3 — Gold / agent-extract | `in_progress` | 0 | — | — | — | validation cmd defined, NOT yet run (see story) |

> Rule reminder: US-001 stays `in_progress` until its validation command actually runs and its output is recorded here. Do not mark `implemented` prematurely.
