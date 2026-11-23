---
id: US-056
type: story
title: Test safety, no test writes live operational data
status: implemented
branch: m1/us056-test-safety
lane: high-risk
created: 2026-11-23
updated: 2026-11-23
lang: en
authors: [agent]
adr: []
plan: [PLN-20261123-1510-production-upgrade-to-article-compact-v3-and-sync]
evidence:
  - "commit: 1ff2dc5 (P1a), cdc60ad, 8753312 (P1b)"
  - "test: full suite 1175 passed, 21 skipped at 8753312"
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_empirical_challenger_m2_2_wave_concurrency.py project/tests/test_empirical_challenger_m2.py project/tests/test_empirical_challenger_m2_ops_queue.py project/tests/test_empirical_challenger_m3_m5.py project/tests/test_empirical_challenger_m4_1_grounding.py project/tests/test_ops_runtime.py project/tests/test_ops_trace.py -q"
summary: The test suite no longer writes the live monocle.db or ops.db, and tests that read live data skip unless the production host flag is set.
---

# US-056 — Test safety, no test writes live operational data

## Contract

Running the test suite on any machine, including the production host, never writes to the live data directory. Tests that only read live production data run only when the operator sets `NEWS_SCAPE_PRODUCTION_HOST=1`; elsewhere they skip with a reason, so the suite passes on Linux and in fpa-toolkit.

## Acceptance Criteria

- [x] `audit_and_truncate_wal` runs only on synthetic databases in `tmp_path` (P1a).
- [x] In the five challenger files every live `sqlite3.connect` uses `mode=ro` and no `OpsStore(` runs on a live path.
- [x] A `production_host` marker skips live tests unless `NEWS_SCAPE_PRODUCTION_HOST=1` and the live DB exists.
- [x] No personal OneDrive or SharePoint path remains under `project/`.
- [x] `86b1e1a` is on the branch; the two PARKED tests pass.

## Design Notes

Plan PLN-20261123-1510, phases P1a and P1b. Rule: FACT-tests-must-not-write-operational-db. The conftest `_guarded_connect` guard covers the pytest process only; subprocess tests are fixed at the source.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `verify` command above | |
| Integration | full suite once, recorded in `docs/TEST_MATRIX.md` | |
| Platform | `grep` checks in the acceptance criteria | |

## Evidence

- P1a `1ff2dc5`: the WAL audit test runs on a synthetic DB in `tmp_path`.
- P1b `cdc60ad` (cherry-pick of `86b1e1a`), `8753312`: `production_host` marker in `conftest.py`; `audit_m4_m5_integrity.py --read-only`; `verify_ops_queue.py` and the reservation test read `ops.db` read-only; the snapshot check reads an existing snapshot only; generic paths in path-classification tests.
- Full suite 1175 passed, 21 skipped. With `NEWS_SCAPE_PRODUCTION_HOST=1` the two `m3_m5` live tests pass on the production host and the live WAL is not truncated.
- Deployed with P6 on `dev/us038` `31a5ad4` (2026-11-23 18:05).
