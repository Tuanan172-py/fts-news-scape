---
id: US-042
type: story
title: CQRS Partitioned Lakehouse on SharePoint Data Plane
status: planned
lane: normal
created: 2026-10-08
updated: 2026-10-08
lang: en
authors: [operator, antigravity]
adr: [ADR-0023]
evidence:
  - "metric:DuckDB vectorized dedup 115ms for 1300 records"
  - "path:C:/data/news-scape/publish_hold"
verify: "pytest project/tests/ -k lakehouse"
summary: Implement lock-free dropzone ingestion and DuckDB consolidation for the SharePoint news-data sandbox.
---

# US-042 — CQRS Partitioned Lakehouse on SharePoint Data Plane

## Contract

The system must provide a lock-free dropzone ingestion protocol on the SharePoint news-data sandbox. Multiple worker processes and developers must publish immutable Parquet batch fragments concurrently without file collisions. A background DuckDB consolidation engine must reconcile fragments, eliminate duplicate articles by article identifier and modification timestamp, and produce canonical partitioned Parquet datasets accompanied by cryptographic SHA-256 manifests.

## Acceptance Criteria

- [ ] Concurrent dropzone batch writing succeeds across three parallel processes without generating conflict files or file lock exceptions.
- [ ] DuckDB consolidator reconciles fragmented batches into partitioned Parquet files within five seconds for one thousand articles.
- [ ] Cryptographic manifest files record accurate row counts, byte sizes, and SHA-256 checksums matching the consolidated partitions.
- [ ] User delivery workbooks in Excel format continue to strictly conform to the existing fifteen-column layout contract.

## Design Notes

- References ADR-0023 and RULE-03 for staging invariants and atomic replacement.
- Touched modules include lakehouse ingestion under storage modules and consolidation utilities.
- Writes to the official departmental site remain strictly blocked by target markers.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/test_lakehouse.py -q` | Pending implementation |
| Integration | `pytest project/tests/test_lakehouse_concurrency.py -q` | Pending implementation |
| Platform | `python scripts/lakehouse_admin.py verify` | Pending implementation |

## Evidence

- `metric:DuckDB vectorized dedup 115ms for 1300 records`
- `path:C:/data/news-scape/publish_hold`
