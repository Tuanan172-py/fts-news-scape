---
id: US-036
type: story
title: Bronze written to the wrong root and Silver failure ledger keys
status: implemented
lane: normal
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: [ADR-0007, ADR-0013]
plan: []
evidence:
  - commit:bfbd5e6
  - commit:0340f64
  - commit:737d8ce
  - path:project/src/crawler/raw_store.py
  - path:project/src/db/store.py
  - path:project/src/pipeline/derive.py
  - test:project/tests/test_raw_store.py
  - test:project/tests/test_silver_failure_keys.py
  - test:project/tests/test_paths_anchored.py
  - metric:2,750 Bronze files moved from the repo-root data folder; 1,607 same-name conflicts kept aside, 2026-10-05
  - metric:1,365 silver_failures rows merged to 850 after key normalisation, 2026-10-05
  - metric:64 targeted tests passed, 2026-10-05
  - operator:approved copying raw_html instead of re-crawling, 2026-10-05
verify: "python -m pytest project/tests/test_raw_store.py project/tests/test_silver_failure_keys.py project/tests/test_paths_anchored.py -q"
original: "commit:0340f64"
reconstructed: 2026-10-06
summary: Captured articles are never reported lost because Bronze and other data products always resolve under project/data, a failed capture never overwrites a good one, and stale Silver failure rows no longer pin the watermark.
---

# US-036 — Bronze written to the wrong root and Silver failure ledger keys

## Contract

A captured article is never treated as lost. Bronze and every data product land under `project/data` whatever the process working directory is. A failed capture never overwrites a good capture, and old Silver failure rows no longer pin the derive watermark.

## Acceptance Criteria

- [x] 2,750 Bronze files in `<repo root>/data/raw_html` moved into `project/data/raw_html`; 1,607 same-name files with different content kept in `C:\data\news-scape\recovered\root_raw_html_conflicts_20261005`.
- [x] All 1,362 `raw_missing` rows in `silver_failures` have both meta and HTML files on disk.
- [x] `RawStore` anchors relative paths to `PROJECT_ROOT` and writes a relative `html_path` in the meta file.
- [x] A failed capture does not overwrite the meta and HTML of a good capture.
- [x] `silver_failures` keys are normalised to forward-slash relative paths; old rows merge on every derive cycle (1,365 rows became 850).
- [x] The rest of `<repo root>/data` is cleared by option E: 259 files moved to `C:\data\news-scape\recovered\root_data_20261005`, 4 export CSVs merged into `project/data/exports`.
- [x] Write points for `exports`, `notifications`, `staging` and `work_packages` are anchored to `PROJECT_ROOT`, with a test.
- [ ] After a morninger restart on the new code, blocking `silver_failures` rows reach 0 and the watermark moves past 2026-09-25. Not confirmed in this record.
- [ ] The full pytest suite is rerun after the `store.py`, `derive.py` and write-point changes.

## Design Notes

- Cause: from 2026-09-28 to 2026-10-02 a process ran with the repo root as cwd and wrote Bronze, `silver`, `agent_tasks`, `work_packages` and `exports` to `<repo root>/data`.
- `derive` reads through `PROJECT_ROOT`, so those articles showed as `raw_missing`.
- Old failure rows used relative keys that the new derive could not clear, so the watermark stayed at 2026-09-25 14:53.
- Fireant article 41948083 had a good capture; a later failed recapture overwrote its meta with a `failed` record without a hash.
- Still relative: `batch_handoff.py`, `l1_router.py`, `packet.py`, `runner.py` and `l1_runner.py`, all in the L1/Gold lane stopped by ADR-0010.
- `harness.db` paused this story on 2026-10-05 17:30 to keep WIP at one for US-038; last story commit ac9f22f. Code had shipped by then, so the status is implemented with open platform checks.
- The same root-cause fix appears as R-07 in the US-037 plan; this story delivered it.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | raw store, failure keys, anchored paths, watermark, backfill, concurrency, notify and morninger tests | 64 passed, 2026-10-05 |
| Integration | `python -m pytest tests --ignore=tests/test_cli_entrypoints.py` from `project/` | not run; blocked in session |
| Platform | `pipeline_radar.py status` after a derive cycle | 849 rows, 108 blocking at 15:12 on 2026-10-05; 2 true dead-letters reported on 2026-10-06 |

## Evidence

- Commit bfbd5e6 (commit labelled US-033): `RawStore._portable_path`, `_has_good_capture`, and `ArticleStore.canonical_meta_key` with `normalize_silver_failure_keys`.
- Commit 0340f64 (commit labelled US-036, mainly a closure gate): `derive.py` calls the key normalisation; `test_silver_failure_keys.py`; this story file.
- Commit 737d8ce (commit labelled US-037): anchored write points in `csv_export.py`, `silver_manifest.py`, `staging.py`, `work_package.py`, `file_notify.py`, `orchestrator.py`, and `test_paths_anchored.py`.
- DB backup before the merge: `C:\data\news-scape\monocle.db.bak-20261005-pre-bronze-merge`.
- Unique content folded in from the removed duplicate file of the same story: write-point anchoring, option E cleanup, 1,365 to 850 rows, 64 tests and the 15:12 radar reading.
- Commits ac9f22f, 1ae81be and b7f1a37 carry this story's label but change Article Lane packing; they are recorded in US-037.
