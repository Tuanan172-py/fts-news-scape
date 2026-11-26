---
id: US-060
type: story
title: Eliminate OneDrive sync churn from review DB uploads and per-minute publish probe
status: implemented
branch: dev/us038
lane: normal
created: 2026-11-26
updated: 2026-11-26
lang: en
authors: [antigravity]
adr: [ADR-0023, ADR-0024, ADR-0026]
plan: []
evidence:
  - path:project/config/ops.yaml
  - path:project/src/ops/daemon.py
  - path:project/src/ops/probes.py
  - path:project/tests/test_publisher.py
  - path:project/tests/test_ops_runtime.py
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_publisher.py project/tests/test_ops_runtime.py -q"
summary: Stop nightly 2.75 GB review DB uploads to SharePoint, throttle per-minute OneDrive .probe file churn, and detect workstation-named OneDrive conflicts.
---

# US-060 — Eliminate OneDrive sync churn from review DB uploads and per-minute publish probe

## Contract

The daemon (`ops_daemon`) must honor `publish.include_review` from `project/config/ops.yaml`. Production sets it to `false` so nightly publishes write Parquet OBT, Bronze archives, user Excel deliverables, and manifests without syncing multi-GB `review/monocle_review_*.db` files over SharePoint. The health probe loop must throttle `_manifest/.probe` write checks via `publish.write_probe_interval_minutes` (default 360 minutes). When `write_test=False`, `probe_publish` still verifies target directory existence and detects OneDrive conflict forks matching both `-DESKTOP-` and the current workstation hostname.

## Acceptance Criteria

- [x] `project/config/ops.yaml` sets `publish.include_review: false` and `publish.write_probe_interval_minutes: 360`.
- [x] `OpsDaemon.publish_tick()` forwards `publish.include_review` to `publish_day()`.
- [x] `OpsDaemon.run_probes()` calls `probe_publish(..., write_test=True)` at most once per `write_probe_interval_minutes` and `write_test=False` on intervening beats.
- [x] `probe_publish()` verifies `target.is_dir()` when `write_test=False` and detects conflict forks matching `-{hostname}` in addition to `-DESKTOP-`.
- [x] Unit tests, docstring/phrase linters, and real CLI subprocess probes pass; live `ops_daemon` is restarted cleanly.

## Design Notes

- Aligns runtime behavior with `ADR-0023` (rejecting monolithic SQLite sync over OneDrive) and `ADR-0026.D1` (keeping `publish_day` as the sole production publish path).
- Preserves `publish_day(..., include_review: bool = True)` default for direct callers and existing tests; local snapshots stay at `C:\data\news-scape\snapshots\monocle_review.db`.
- Forensic evidence (2026-11-26): 7 stuck `monocle_review_*.db` files (18.4 GB) triggered 1,174 HTTP 400 `OpenUploadSession` (`ItemCannotFitInQuota`) errors, while 60-second `.probe` churn caused 1,048 local deletions in 1,090 minutes.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/test_publisher.py project/tests/test_ops_runtime.py -v` | 47/47 passed |
| Integration | `pytest` (publisher + ops_runtime + research_production + ops_council_fixes + ops_supervision + cli_entrypoints) | 128/128 passed |
| Lint | `ast_docstring_linter.py` (100% coverage) + `scan_code_phrases.py` (0 errors) on `project/src/ops` | PASS |
| Platform | `publish.py --date yesterday --dry-run --skip-review` (ok, 14 files), `ops_daemon.py once`, live `ops_daemon` restarted | PASS |

## Evidence

- Code: `project/config/ops.yaml`, `project/src/ops/daemon.py`, `project/src/ops/probes.py`
- Tests: `project/tests/test_publisher.py`, `project/tests/test_ops_runtime.py`
- Fact: `FACT-onedrive-sync-quota-limits-per-minute-probe-churn`
