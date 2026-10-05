# ARCHITECTURE.md — Harness ↔ Product boundary (news-scape)

> This is a **pointer**, not a copy. The product architecture is authoritative in `project/`.
> This file states only where things live and the rules that keep the harness out of the product's way.

## 1. Where the real product architecture lives (do NOT duplicate here)

| Source of truth | Content |
|-----------------|---------|
| `project/docs/ARCHITECTURE.md` | Ingestion architecture + TDR-001..006 (RSS primary, trafilatura, 2-tier dedup, SQLite WAL single-writer, standalone, sync). |
| `project/docs/charter.md` + `charter-executive-summary.md` | Goals (G-1..), constraints (C/O/D/T), phases, WBS. |
| `project/docs/design/00-end-to-end-architecture.md` | The single high-level map: Vòng 1 Capture (Bronze) → Vòng 2 Standardize (Silver) → Vòng 3 Agent handoff. |
| `project/docs/design/07,08,09` | Storage/change-detection, handoff contract, agent-io contract. |
| `project/docs/dev/01-codebase-guide.md` | Code layout. |

When a change touches architecture, READ these — do not restate them in the harness.

## 2. Harness ↔ product boundary

- The **harness** (this repo root: `AGENTS.md`, `docs/`, `harness/`) is the operating model. It never contains product logic.
- The **product** (`project/`) is the news-ingestion pipeline. Its code/config/tests/docs stay under `project/`.
- Harness meta-work (stories about the harness) → `docs/stories/`. Product implementation work → `project/plans/*` (existing convention).

## 3. Discovery-Before-Shape (reminder)

Before shaping new product code: discover the surface (which `project/src/*` module), the stack constraints (standalone, single SQLite, sync), the domains touched, and the validation ladder (which pytest). Only then design. Most of "the product law" is already discovered in `project/docs/*`.

## 4. Dependency Rule (reminder)

Inner layers do not depend on outer layers. For news-scape's medallion: **Silver is a pure function of Bronze**; Gold (deferred) consumes the handoff contract, not raw scrapers. Do not create upward dependencies (e.g. a scraper writing downstream tables) — see `project/docs/design/00` §1.
