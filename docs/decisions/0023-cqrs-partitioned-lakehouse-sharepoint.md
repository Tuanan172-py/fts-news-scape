---
id: ADR-0023
type: adr
title: CQRS Partitioned Lakehouse on SharePoint Data Plane
status: accepted
lane: high-risk
created: 2026-10-08
updated: 2026-10-08
lang: en
authors: [operator, antigravity]
approvers: [operator 2026-10-08]
story: [US-042]
supersedes: [ADR-0020]
evidence:
  - path:project/src/lakehouse/
  - path:project/scripts/lakehouse_cli.py
  - path:project/tests/test_lakehouse_concurrency.py
  - path:project/tests/test_lakehouse_perf.py
  - commit:966ba42
  - metric:DuckDB vectorized dedup 115ms for 1300 records
summary: Establishes CQRS Partitioned Lakehouse on SharePoint news-data sandbox with lock-free dropzone, DuckDB deduplication, and strictly isolates official FRA - Data site.
summary_vi: Thiết lập kiến trúc CQRS Partitioned Lakehouse trên SharePoint sandbox news-data với dropzone phi khóa, DuckDB khử trùng lặp và cách ly tuyệt đối site chính thức FRA - Data.
---

# ADR-0023 — CQRS Partitioned Lakehouse on SharePoint Data Plane

## Context

- The previous publication design in ADR-0020 attempted to sync a monolithic 758 MB SQLite review database (`monocle_review.db`) into the corporate teamsite `FRA - Data/news/review`.
- On 2026-10-08, syncing a monolithic database into OneDrive sync folders was found to risk sync loop deadlocks, file locking exceptions during client reads, and file system watcher saturation across departmental accounts.
- In addition, multiple developers and background ingestion workers require the ability to publish processed news batches concurrently without colliding on identical file paths or generating `*-DESKTOP-*` OneDrive synchronization conflict forks.
- Direct writing of end-user Excel deliverables from multi-process workers is prone to file corruption and permission locks when analysts open target workbooks in Microsoft Excel.
- A reliable, distributed Data Plane is necessary on cloud storage to decouple concurrent data writes from centralized query reads.

## Decision

- **ADR-0023.D1 (Hard Isolation of Official Site):** System processes MUST NOT write any files to the official departmental site `https://fptscomvn.sharepoint.com/sites/FRA` (`FRA - Data`). Enforcement is implemented via `OFFICIAL_TARGET_MARKERS = frozenset({"fra - data"})` in `publisher.py`.
- **ADR-0023.D2 (Designated Sandbox Data Plane):** All remote Data Plane publication operations MUST execute exclusively within the isolated sandbox: `FRA_DataIngestion - news-data` (`sites/FRA_DataIngestion/Shared Documents/AnPT`).
- **ADR-0023.D3 (Lock-Free Dropzone Ingestion Protocol):** Multi-developer write operations MUST publish article batches as immutable, uniquely-named Parquet fragments under `dropzone/YYYY/MM/DD/part-<date>-<dev_id>-<batch_id>.parquet`. Every write MUST follow the atomic protocol: write `.partial` staging file, flush, execute `os.fsync`, and atomic `os.replace`.
- **ADR-0023.D4 (Vectorized DuckDB Lakehouse Consolidator):** A zero-token background compaction engine using DuckDB MUST consolidate dropzone fragments into canonical time-partitioned Parquet files: `parquet/articles/year=YYYY/month=MM/part-YYYYMMDD.parquet` (compressed with ZSTD). Deduplication MUST prioritize the latest `updated_at` (tie-breaking with `batch_id DESC`).
- **ADR-0023.D5 (Cryptographic Manifest & Pointer):** Every consolidation MUST record partition metadata, row counts, byte lengths, and SHA-256 hashes in `_manifest/<date>.json` and update the atomic pointer `_manifest/latest.json`. Consumers MUST verify hashes before reading.
- **ADR-0023.D6 (Decoupling Data Plane from Delivery):** The Lakehouse module MUST remain a pure Data Plane (`ingest`, `consolidate`, `verify`). User delivery Excel workbooks MUST remain strictly produced by canonical modules (`src/export/xlsx_delivery.py` and `src/export/user_output.py`) conforming to the established 15-column specification (`DELIVERY_FIELDS`).

## Alternatives

| Option | Why rejected |
|---|---|
| Monolithic SQLite database sync | Writing 758 MB database files over OneDrive sync causes extreme network lag, database locks, and sync conflict forks. |
| Direct shared Excel workbook writing | Concurrent processes locking `.xlsx` files cause PermissionError exceptions whenever analysts open files. |
| In-place single Parquet file updates | Multiple concurrent developer processes writing to the same Parquet file cause overwrite collisions and data loss. |

## Consequences

- Zero file-lock contention and zero OneDrive synchronization fork files (`*-DESKTOP-*`) across distributed developer machines.
- Near-instantaneous vectorized deduplication: DuckDB consolidates 1,300 articles in 115 milliseconds with zero LLM token consumption.
- Cryptographic tamper-proofing through automated SHA-256 byte validation.
- Clear architectural separation between storage data plane (Parquet) and user application deliverables (Excel).
- Accepted operational cost: scheduled maintenance jobs are required to purge archived dropzone files once compacted into canonical partitions.

## Rollback

To roll back this architecture, disable `lakehouse_cli.py` in automation schedules, remove `project/src/lakehouse/`, and rely exclusively on local single-node SQLite `monocle.db` storage.

## Follow-up

- [ ] Implement an automated retention pruning policy for dropzone files older than 7 days that are verified in `_manifest/latest.json`.
- [ ] Connect `write_user_output.py` to optionally query canonical Parquet partitions via DuckDB views when local SQLite is offline.
