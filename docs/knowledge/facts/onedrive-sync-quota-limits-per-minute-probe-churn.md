---
id: FACT-onedrive-sync-quota-limits-per-minute-probe-churn
type: fact
title: OneDrive sync quota limits, per-minute probe churn, and CloudFiles shortcut safety
status: active
created: 2026-11-26
updated: 2026-11-26
verified: 2026-11-26
lang: en
authors: [antigravity]
adr: [ADR-0023, ADR-0024]
evidence:
  - "path:project/config/ops.yaml"
  - "path:project/src/ops/daemon.py"
  - "path:project/src/ops/probes.py"
  - "metric:1174x HTTP 400 OpenUploadSession ItemCannotFitInQuota on news-data review DBs (18.4 GB)"
  - "metric:1048 local deletions in 1090 minutes from 60s probe_publish .probe write_test"
  - "metric:301684 synced files triggered 98.0% CPU in FileScanner::DoScanWorkInternal"
summary: Syncing multi-GB SQLite review DBs exhausts SharePoint quota (ItemCannotFitInQuota), 60-second .probe writes wake OneDrive every minute, and AddToOneDrive shortcuts use CloudFiles reparse tag 0x9000601a.
---

# FACT-onedrive-sync-quota-limits-per-minute-probe-churn — OneDrive sync quota limits, per-minute probe churn, and CloudFiles shortcut safety

## Fact

- Daily 2.5-2.75 GB `review/monocle_review_YYYYMMDD.db` copies in `Shortcuts/FRA_DataIngestion - news-data` (18.4 GB rolling plus 93-day SharePoint Recycle Bin) exhausted `sites/FRA_DataIngestion` quota. This caused 1,174 HTTP 400 `OpenUploadSession` (`ItemCannotFitInQuota`) retries and 755/min `RNDataBridge` UI storms.
- Calling `probe_publish(..., write_test=True)` in `OpsDaemon.run_probes()` every 60 seconds created and deleted `_manifest/.probe` inside OneDrive 1,440 times/day. This produced 1,048 `numLcDeleteFile` events in 1,090 minutes and bloated `SafeDelete.db-wal` to 16.2 MB.
- Exceeding Microsoft's 300,000 synced-item ceiling (301,684 files across 8 scopes, 90.4% from `Desktop/backup` `.venv` archives and deprecated `FRA_DataIngestion - news-scape`) pinned `OneDrive.exe` at up to 97.4% of a CPU core. `FileScanner::DoScanWorkInternal` consumed 98.0% of OneDrive CPU time and rotated 1 MB/min of `.odl` logs.
- Verified with `fsutil reparsepoint query`: OneDrive "Add shortcut to OneDrive" folders (`scopeType = 6`, e.g., `FRA_DataIngestion - news-scape`) carry `Reparse Tag Value: 0x9000601a` (`IO_REPARSE_TAG_CLOUD_6`), not an NTFS mount-point junction (`0xA0000003`).

## Why

- Syncing monolithic SQLite databases over SharePoint violates `ADR-0023` and causes infinite retry loops once site quota fills.
- Per-minute create+delete health probes inside a OneDrive sync root trigger NTFS USN Journal storms and `DriveChangeGenerator::HandleRecycledFile` activity nonstop.
- Running `Remove-Item -Recurse` or `shutil.rmtree` on an `AddToOneDrive` shortcut folder traverses its children and deletes cloud files on SharePoint instead of unlinking the shortcut.

## How to Apply

- Keep `publish.include_review: false` in `project/config/ops.yaml`. Store local SQLite review snapshots outside OneDrive at `C:\data\news-scape\snapshots\monocle_review.db`.
- Throttle `probe_publish` write checks via `publish.write_probe_interval_minutes: 360` (at most 4 checks/day).
- Never use recursive CLI delete on a SharePoint shortcut folder. Remove shortcuts only through the official OneDrive Shell verb (`Remove shortcut`) or OneDrive Web. Use Selective Sync (`Choose folders`) for cloud-only archive folders instead of local mass delete.
