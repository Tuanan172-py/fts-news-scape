---
id: ADR-0027
type: adr
title: "Module boundaries: logic in src, thin CLIs at stable paths"
status: accepted
lane: high-risk
created: 2026-10-22
updated: 2026-10-22
lang: en
authors: [claude-opus-5-5]
approvers: [operator 2026-10-22]
story: [US-049]
supersedes: []
amends: []
related: [ADR-0010, ADR-0024, ADR-0026]
evidence:
  - path:docs/proposals/20261022-codebase-modularization.md
  - "operator:2026-10-22 approved option B, the deletion lists of proposal F4 groups 2 and 3, and pushing the branch"
summary: "Business logic lives in project/src in four layers; project/scripts holds thin CLIs whose paths never change; an ast test enforces no scripts-to-scripts, no src-to-scripts, no new sys.path hacks and no sqlite3.connect outside src/db."
summary_vi: "Logic nghiệp vụ nằm trong project/src theo bốn tầng; project/scripts chỉ còn CLI mỏng giữ nguyên đường dẫn; test ast chặn import script-script, src-script, sys.path mới và sqlite3.connect ngoài src/db."
---

# ADR-0027 — Module boundaries: logic in src, thin CLIs at stable paths

## Context

- PRP-20261022-codebase-modularization measured the layout at `ec4e7fe`: about 4,000 LOC of lane logic in `project/scripts/`, 7 scripts-to-scripts imports, 2 src-to-scripts imports, 30 `PROJECT_ROOT` definitions and 66 unreachable files.
- CLI paths under `project/scripts/` are referenced by `.agents/pipeline.yaml`, Task Scheduler, `src/ops/wave_flow.py`, conductor programs and 236 documents, so moving them is a breaking change for a system that runs 24/7.
- The daemon runs from the canonical tree and reloads scripts from disk, so every restructuring commit reaches production on merge. The structure must improve in small, revertible steps with mechanical checks.

## Decision

- **ADR-0027.D1 (Layers):** L0 `src/core`, L1 `src/db`, L2 domain packages (`crawler`, `scrapers`, `processor`, `pipeline`, `agent`, `article_lane`, `export`, `lakehouse`, `ops`, `monitor`, `handoff`, `telemetry`, `users`, `analytics`, `notifier`), L3 `project/scripts/`. A layer imports only layers below it; L2 packages import each other without cycles.
- **ADR-0027.D2 (Stable CLI paths):** Existing `project/scripts/*.py` paths stay. A script parses arguments and calls functions in `src`; it holds no reusable logic.
- **ADR-0027.D3 (Forbidden edges):** No `scripts → scripts` import and no `src → scripts` import.
- **ADR-0027.D4 (Plumbing):** The project root, data root and DB path are computed only in `src/core/paths.py`. New code adds no `sys.path.insert` outside thin CLI bootstraps and calls `sqlite3.connect` only inside `src/db` and `src/core/paths.py`.
- **ADR-0027.D5 (Enforcement):** `project/tests/repo/test_architecture.py` checks D3 and D4 with `ast`. Its allowlist records the remaining violations and may only shrink.
- **ADR-0027.D6 (Dead code):** Code unreachable from the live entry points is deleted, not archived in the tree; git history keeps it.

## Alternatives

| Option | Why rejected |
|---|---|
| Hygiene only (proposal option A) | Leaves the inverted layering in place. |
| Installable package with new entry points (option C) | Breaks every CLI path at once on a production system with no staging environment. |

## Consequences

- Readers find lane logic under `src/article_lane/` and CLIs stay where runbooks, presets and Task Scheduler say they are.
- New violations fail `pytest` at once instead of accumulating silently.
- Thin CLI files remain as a small duplication cost, and each move updates the tests that import the old location.

## Rollback

- Revert the story commits; the architecture test and allowlist go with them. Only the operator may order the rollback.

## Follow-up

- [ ] Stories S1-S5 of PRP-20261022-codebase-modularization.
- [ ] Rule `.agents/rules/12-module-boundaries.md` citing this ADR.
