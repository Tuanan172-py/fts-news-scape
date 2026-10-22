# ARCHITECTURE.md — Harness ↔ Product boundary (news-scape)

> This is a **pointer**, not a copy. The product architecture is authoritative in `project/`.
> This file states only where things live and the rules that keep the harness out of the product's way.

## 1. Where the real product architecture lives (do NOT duplicate here)

| Source of truth | Content |
|-----------------|---------|
| `project/docs/architecture.md` | Ingestion architecture + TDR-001..006 (RSS primary, trafilatura, 2-tier dedup, SQLite WAL single-writer, standalone, sync). |
| `project/docs/design/00-end-to-end-architecture.md` | The single high-level map: six layers L0 control, L1 capture (Bronze), L2 Silver, L3 Article Lane, L4 delivery and Lakehouse, L5 harness. |
| `project/docs/design/07`, `08`, `00` §6.2 | Storage and change detection, handoff contract, Article Lane data contracts. |
| `.agents/rules/12-module-boundaries.md` (RULE-12, ADR-0027) | Code layout: logic in `project/src/<package>/`, thin CLIs at stable paths in `project/scripts/`. |
| `project/docs/dev/01-codebase-guide.md` | Code walkthrough for developers. |

When a change touches architecture, READ these — do not restate them in the harness.

## 2. Harness ↔ product boundary

- The **harness** (this repo root: `AGENTS.md`, `docs/`, `scripts/`, `.agents/`, `harness.db`) is the operating model. It never contains product logic.
- The **product** (`project/`) is the news-ingestion pipeline. Its code/config/tests/docs stay under `project/`.
- Harness meta-work (stories about the harness) → `docs/stories/`. Plans → `plans/<YYYYMMDD>-<HHMM>-<slug>/plan.md` (K-R10).

## 3. Discovery-Before-Shape (reminder)

Before shaping new product code: discover the surface (which `project/src/*` module), the stack constraints (standalone, single SQLite, sync), the domains touched, and the validation ladder (which pytest). Only then design. Most of "the product law" is already discovered in `project/docs/*`.

## 4. Dependency Rule (reminder)

Inner layers do not depend on outer layers. For news-scape's medallion: **Silver is a pure function of Bronze**; the Article Lane consumes Silver packets, not raw scrapers (ADR-0010 retired the Gold lane). Do not create upward dependencies (e.g. a scraper writing downstream tables) — see `project/docs/design/00` §1.
