---
id: US-045
type: story
title: "Unify architecture state: lane docs, harness tracking, publish path, L0/L1, manifest SSOT, users/output"
status: blocked
lane: high-risk
branch: dev/us038
created: 2026-10-21
updated: 2026-10-21
lang: en
authors: [operator, claude]
adr: [ADR-0026]
plan: []
evidence:
  - path:project/docs/design/00-end-to-end-architecture.md
  - path:project/src/core/user_manifest.py
  - path:project/scripts/maintenance/migrate_users_output.py
verify: "cd project && python -m pytest tests/test_ops_core.py tests/test_user_manifest.py tests/test_migrate_users_output.py tests/test_publisher.py tests/test_entities.py tests/test_harness_cli.py -q"
summary: Brings docs, harness and code to one state - Article Lane docs, non-gating session close, one publish path, L0/L1 only, one user manifest, one users/output tree.
---

# US-045 — Unify architecture state

## Contract

After this story the architecture map, the documents and the code describe one system. The end-to-end document shows only the Article Lane. The harness records every session without blocking it. There is one production publish path, two autonomy levels, one user manifest and one Excel output tree shared by the operating machine and SharePoint.

## Acceptance Criteria

- [x] `project/docs/design/00-end-to-end-architecture.md` describes the Article Lane only; legacy design docs carry a pointer banner.
- [x] `session close` records verify, push and friction in the trace, continues after a failed verify, and grants proof only on a passing verify (`--strict` aborts).
- [x] `publish.py` to `publish_day()` is documented as the only production publish path; `lakehouse_cli.py` only verifies and receives the dropzone (ADR-0026.D1).
- [x] `order.py` has no L2/L3 mapping; `/level L2` and `/level L3` are refused; `/level L1 <n>` sets a per-wave cap.
- [x] `<DATA_ROOT>/subscriptions/manifest.yaml` is the only user switch; `config/entities/manifest.yaml` is deleted.
- [x] `paths.users_output_dir()` is `<DATA_ROOT>/users/output`; a migration script exists with a dry-run default.
- [ ] (blocked on operator) Operator runs the migration with `--apply` on the operating machine while the daemon is stopped.

## Design Notes

- Decisions: ADR-0026 (amends ADR-0012 D5). ADR-0023 supersedes ADR-0020.
- Shared loader `src/core/user_manifest.py` serves `agent/entities.py`, `users/compile.py` and `pipeline_radar.py`.
- Wave cap: `wave_flow` uses `min(cfg.wave.limit, order.max_limit)`.
- The old config manifest held no ticker data, so no `ticker_directory.yaml` was needed.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests` (full suite) | 962 passed, 1 deselected (`test_b2_sensor_does_not_count_reserved_articles`, see Evidence) |
| Integration | `migrate_users_output.py` dry-run on the live data root | 607 files, 0 conflicts |
| Platform | `pipeline_radar.py users` reads the new manifest | 5 active users |

## Evidence

- The deselected test fails on a fixed-date sensor reading and does not import any file this story changed; not re-run on the previous commit.
