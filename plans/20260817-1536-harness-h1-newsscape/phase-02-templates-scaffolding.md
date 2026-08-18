# Phase 02 — Templates + Friction Reservoir + Scaffolding

## Context Links
- Parent plan: [plan.md](plan.md)
- Prev phase: [phase-01-core-policy-docs.md](phase-01-core-policy-docs.md)
- v2 evaluation: [reports/01-v2-evaluation.md](reports/01-v2-evaluation.md) (Epic → `Parent/Epic` free-text field, no folders)
- Source guide: `harness/HARNESS_BUILD_FROM_SCRATCH.md` (Files 7–10)

## Overview
- **Date:** 2026-08-17
- **Description:** Create the 3 core templates, the friction reservoir (HARNESS_BACKLOG.md), and empty story/decision dirs. Story template carries a free-text `Parent / Epic` field (Epic surrogate = charter Phase 1/2/3). NO initiatives/epics folders.
- **Priority:** P0 (needed before the dogfood run in Phase 03).
- **Implementation status:** Planned
- **Review status:** Pending

## Key Insights
- Templates are reusable scaffolds; story.md is the most important.
- Epic hierarchy stays informal at H1 → one `Parent / Epic` free-text line in story template, no parallel folders (v2 verdict #1).
- HARNESS_BACKLOG.md realizes "grows-from-friction" from day one; at H2 it moves into a DB `backlog` table.
- Empty `stories/` and `decisions/` dirs = landing zones for the dogfood run (Phase 03) + future ADRs.

## Requirements
**Functional**
- `docs/templates/{story,decision,validation-report}.md` exist.
- story.md sections: Title (US-XXX), Status, Lane, `Parent / Epic` (free text), Product Contract, Acceptance Criteria, Design Notes, Validation table (Unit/Integration/E2E/Platform), Harness Delta, Evidence.
- decision.md = ADR: Context, Decision, Alternatives, Consequences (Positive/Tradeoffs), Follow-Up; status enum Proposed/Accepted/Superseded/Rejected.
- validation-report.md: Scope, Commands Run, Results table (default "not run"), Evidence, Gaps.
- HARNESS_BACKLOG.md: fields Title, Discovered While, Current Pain, Suggested Improvement, Risk (lane), Status.
- `docs/stories/` and `docs/decisions/` exist (empty; `.gitkeep`).

**Non-functional**
- English; keep intake/lane/trace/proof terms.
- Templates must be fill-in-the-blank, junior-dev usable.

## Architecture
Still pure Policy layer. Adds reusable scaffolds + friction reservoir:
```
<repo root>/docs/
  HARNESS_BACKLOG.md
  templates/  story.md  decision.md  validation-report.md
  stories/    .gitkeep      (real US-XXX packets land here)
  decisions/  .gitkeep      (ADR NNNN-*.md land here)
```
No SQLite. Status/live-state fields in templates are per-story static text, not a shared dashboard.

## Related Code Files (create — repo ROOT)
1. `docs/templates/story.md` — with `Parent / Epic:` free-text field (e.g. "Phase 3 — Gold layer / agent extract").
2. `docs/templates/decision.md` — ADR structure + status enum.
3. `docs/templates/validation-report.md` — Results table defaults "not run".
4. `docs/HARNESS_BACKLOG.md` — friction table + one worked example row (placeholder, replaced in Phase 03 by a real entry).
5. `docs/stories/.gitkeep`
6. `docs/decisions/.gitkeep`

## Implementation Steps
1. Create `docs/templates/`, `docs/stories/`, `docs/decisions/` (quote paths — spaces).
2. Write `story.md`; include the `Parent / Epic` free-text line under Title; keep Validation as a 4-row table (Unit/Integration/E2E/Platform, each: tier / command / status / evidence).
3. Write `decision.md` (ADR) + `validation-report.md`.
4. Write `HARNESS_BACKLOG.md` with header + column legend + 1 example row.
5. Add `.gitkeep` to `stories/` and `decisions/` so empty dirs commit.
6. Cross-check: template vocabulary matches `docs/GLOSSARY.md` exactly (no new undefined terms).

## Todo List
- [ ] docs/templates/story.md (+ Parent/Epic field)
- [ ] docs/templates/decision.md
- [ ] docs/templates/validation-report.md
- [ ] docs/HARNESS_BACKLOG.md
- [ ] docs/stories/.gitkeep
- [ ] docs/decisions/.gitkeep
- [ ] Vocab consistency check vs GLOSSARY

## Success Criteria
- 3 templates + backlog + 2 empty dirs exist.
- story.md has the `Parent / Epic` free-text field and a 4-tier validation table.
- NO `initiatives/` or `epics/` or `knowledge/` folders created.
- All template terms defined in GLOSSARY.

## Risk Assessment
- **Scope creep** (adding advanced templates spec-intake/high-risk-story): mitigate — those are for the high-risk lane later; skip at H1.
- **Vocab drift**: mitigate — GLOSSARY cross-check step.

## Security Considerations
- validation-report.md must not embed secrets in "Commands Run"; reference config paths, mask tokens.

## Next Steps
- Depends on: Phase 01 (GLOSSARY vocab, TEST_MATRIX enum).
- Enables: Phase 03 dogfood run writes a real story into `docs/stories/` + a real backlog entry.
