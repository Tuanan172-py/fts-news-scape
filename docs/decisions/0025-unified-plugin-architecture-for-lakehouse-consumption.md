---
id: ADR-0025
type: adr
title: Unified Plugin Architecture for Lakehouse Consumption on AGY and Gemini
status: accepted
lane: normal
created: 2026-10-20
updated: 2026-10-20
lang: en
authors: [operator, antigravity]
approvers: [operator 2026-10-20]
story: [US-038]
related: [ADR-0020, ADR-0023]
evidence:
  - path:project/src/lakehouse/
  - path:project/src/export/publisher.py
  - path:project/tests/lakehouse/test_lakehouse_perf.py
  - commit:23f760e
  - metric:DuckDB vectorized scan 2905 articles in 0.42s
summary: Establishes the Unified Plugin packaging architecture (fpts-market-intel) for local Lakehouse data consumption across Antigravity (AGY) and Gemini CLI/IDE ecosystems, replacing fragmented standalone skills with a single-bundle distribution, zero-config path auto-discovery, and shared DuckDB vectorized tooling.
summary_vi: Thiết lập kiến trúc đóng gói Unified Plugin (fpts-market-intel) phục vụ khai phá dữ liệu Lakehouse cục bộ trên hệ sinh thái Antigravity (AGY) và Gemini CLI/IDE, thay thế mô hình skill rời rạc bằng một gói phân phối duy nhất, cơ chế tự động tìm đường dẫn shortcut không cần cấu hình và công cụ DuckDB dùng chung.
---

# ADR-0025 — Unified Plugin Architecture for Lakehouse Consumption on AGY and Gemini

## Context

- ADR-0023 established the backend CQRS Partitioned Lakehouse Data Plane on SharePoint (`FRA_DataIngestion - news-data`) with canonical 22-column One Big Table (OBT) Parquet storage, cryptographic manifest indexing (`_manifest/latest.json`), and automated dropzone purging.
- Over 2,900 articles have been compacted into columnar Parquet files (`parquet/articles/year=YYYY/month=MM/part-YYYYMMDD.parquet`), enabling zero-token vectorized query execution in under 0.5s via DuckDB.
- Multiple departmental analysts (e.g., users `AnPT`, `PhoHG`, `ThanhTD`, `UyenNNT`, `VyPTT`) access this Data Plane locally via Microsoft OneDrive Shortcuts on their corporate workstations.
- Distributing individual, loose skills (`skills/<name>/SKILL.md`) to end-user workstations creates significant operational liabilities:
  1. Redundant Code Duplication: Every individual skill duplicates DuckDB connection logic and OneDrive path resolution scripts.
  2. Configuration Friction: Analysts are not software engineers and must not configure local paths, database drivers, or environment variables manually.
  3. Version Skew: Updating the Parquet schema or DuckDB client requires updating multiple disjoint directories, causing fragmented tool states across workstations.
  4. Degraded UI Discoverability: Standalone skills lack centralized toggle switches and pre-built prompt accelerators (`suggestedPrompts`) in the Antigravity IDE and Gemini user interfaces.

## Decision

- **ADR-0025.D1 (Unified Plugin as Single Unit of Delivery):** All client-side analytical capabilities for querying and screening News-Scape Lakehouse data MUST be packaged as a single unified plugin (`fpts-market-intel`). Target location is `~/.gemini/config/plugins/fpts-market-intel/`. Distributing loose, unbundled skills in client environments is strictly prohibited.
- **ADR-0025.D2 (Progressive Disclosure and Reusable Tooling Layout):** The plugin bundle MUST adhere to the standard plugin layout. It includes `plugin.json` for metadata and `suggestedPrompts`. It includes `rules/AGENTS.md` for financial domain invariants and citation groundings. It provides shared tooling in `tools/lakehouse_client.py` for DuckDB execution. It provides focused workflows in `skills/`.
- **ADR-0025.D3 (Zero-Config Path Auto-Discovery Protocol):** Client queries MUST NOT require manual path configuration. The shared client module MUST resolve the local SharePoint shortcut automatically via a 3-tier hierarchy:
  1. Environment variable `$env:NEWS_DATA_ROOT`.
  2. Standard shortcut locations (`%USERPROFILE%\OneDrive - fpts.com.vn\Shortcuts\FRA_DataIngestion - news-data` or `%USERPROFILE%\OneDrive - fpts.com.vn\FRA_DataIngestion - news-data`).
  3. Dynamic filesystem discovery scanning local OneDrive roots for `_manifest/latest.json`.
- **ADR-0025.D4 (Vectorized Zero-Token Embedded DuckDB Engine):** Client queries MUST execute directly against canonical Parquet partitions using local in-memory DuckDB. Analytical queries MUST use columnar predicate pushdown and list filtering (`list_contains(symbols, '...')`). Database engine installation and execution MUST NOT require dedicated server processes or external network calls.
- **ADR-0025.D5 (Files On-Demand Offline Pinning Enforcement):** The plugin onboarding workflow MUST verify offline availability of Parquet partitions (checking for Windows `attrib +P -U` status) to eliminate network hydration delays and timeout deadlocks during interactive user EDA sessions.
- **ADR-0025.D6 (Cross-Platform Compatibility across AGY and Gemini):** The plugin structure MUST strictly follow the Google Antigravity and Gemini plugin manifest specification (`plugin.json`). This ensures full compatibility across CLI (`agy`) and graphical IDE or Web interfaces.

## Alternatives

| Option | Why rejected |
|---|---|
| Standalone Loose Skills (`~/.gemini/config/skills/`) | Duplicates DuckDB client scripts across multiple directories; no centralized UI toggle; high risk of version mismatch across client machines. |
| Centralized Database Server (Postgres / MySQL) | Introduces external infrastructure dependencies, connection pooling overhead, network latency, credential management, and VPN requirements for remote users. |
| Shared Network Excel Workbooks | Concurrent multi-user access causes file locks (`PermissionError`) and OneDrive synchronization conflict forks (`*-DESKTOP-*`). |

## Consequences

- Direct 1-click deployment for departmental analysts: dropping a single directory into `plugins/` enables all market intelligence skills instantly.
- Unified maintenance: schema updates and DuckDB optimizations are made in a single codebase location (`tools/lakehouse_client.py`).
- Zero LLM token consumption during data querying: DuckDB executes local vectorized scans in under 0.5s.
- Interactive user onboarding via native `suggestedPrompts` in AGY and Gemini IDE.
- Accepted trade-off: Client machines require Python with `duckdb` installed in their local environment.

## Rollback

To roll back this architecture, remove the directory `~/.gemini/config/plugins/fpts-market-intel/` and revert to reading static Excel deliverables from `users/output/<user>/`.

## Follow-up

- [ ] Implement `install-plugin.ps1` for 1-click installation on analyst workstations.
- [ ] Implement `tools/lakehouse_client.py` with the 3-tier path auto-discovery protocol.
- [ ] Author the initial 2 bundled skills: `news-ticker-screener` and `news-daily-brief`.
