---
id: US-038
type: story
title: Codebase len Research-FPA/news-scraper va data plane SharePoint
status: in_progress
branch: dev/us038
lane: high-risk
created: 2026-10-05
updated: 2026-10-20
lang: en
authors: [operator, antigravity]
adr: [ADR-0020, ADR-0023, ADR-0024]
plan: []
evidence: []
verify: "pytest tests/test_harness_cli.py -q"
summary: Transfer codebase to Research-FPA/news-scraper and decouple SharePoint data plane.
---

# US-038 — Codebase on Research-FPA/news-scraper and SharePoint Data Plane

## Contract

Isolate the Git codebase from OneDrive/SharePoint two-way sync directories into `C:\src\news-scraper` with gitdir at `C:\gitdirs\news-scape.git` to eliminate permission lock errors. Establish `Research-FPA/news-scraper` as the single source of truth remote, route all runtime writes to `C:\data\news-scape`, and deliver user artifacts via one-way publishing to SharePoint.

## Acceptance Criteria

- [x] Codebase runs in isolation at `C:\src\news-scraper` with local gitdir.
- [x] Runtime SQLite database and raw HTML stored under `C:\data\news-scape`.
- [x] One-way publishing channel to SharePoint `FRA - Data/news` verified.
- [x] 1:1 branch mapping pushed to `Research-FPA/news-scraper` (`dev/us038`).
- [ ] Open and merge Pull Request integrating US-038 through US-043 into `fpa/main`.
- [ ] Tag formal release version `v1.0.0` on the organization repository.

## Design Notes

- Complies with ADR-0020, ADR-0023, and ADR-0024.
- Addresses hybrid workspace concurrency issues documented in Rule 03.
- Establishes dual-remote strategy (organization SSOT on `fpa`, individual sandbox on `origin`).

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest tests/test_harness_cli.py -q` | 13/13 PASS |
| Integration | `pytest project/tests/ -q` | PASS |
| Platform | `git remote -v` | fpa & origin in sync |

## Evidence

- `trace:us038_migration_and_backlog`
