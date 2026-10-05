# Plan — Instantiate Documentation Harness H1 for news-scape (web-monocle)

**Date:** 2026-08-17 | **Scope:** H1 ONLY (pure markdown, NO SQLite, NO CLI) | **Status:** Implemented 2026-08-18

## Overview
Instantiate the agent operating-model at maturity **H1** for news-scape. Landing zone = **git repo ROOT**
(`FRA_DataIngestion - news-scape/`). Produce ~10 markdown policy/template files + scaffolding + 1 real dogfood run.
Existing `harness/` reference docs stay as-is. The product's real architecture stays at `project/docs/ARCHITECTURE.md`
+ `project/docs/charter.md`; the harness `docs/ARCHITECTURE.md` is a THIN pointer, not a duplicate.
H2+ appears only as a "when to climb" note, never as an implementation phase.

## v2 Proposal Evaluation (full detail: reports/01-v2-evaluation.md)
| # | v2 addition | Verdict | Reason (core philosophy) |
|---|-------------|---------|--------------------------|
| 1 | Initiative→Epic→Story + `initiatives/`,`epics/` folders | **DEFER-H2 / DROP folders** | Friction-first; backlog not >10; intake "New initiative" + H2 `story_hierarchy` already cover it. Epic = existing Phase 1/2/3 + `Parent/Epic` field. |
| 2 | Session Handoff `SESSION-LATEST.md` | **KEEP-NOW** | Real gap, cheap, proven. Tiny overwritten file = accepted debt; → DB `next_action` at H2. |
| 3 | Interrupt / WIP=1 rule | **KEEP-NOW (written rule)** | Kanban WIP=1 sound; parallel stories confuse agent. Rule in HARNESS.md + FEATURE_INTAKE.md, no new file. |
| 4 | Project Health dashboard md | **DEFER-H2** | Live-state-in-markdown anti-pattern (drifts). = DB query at H2. SESSION-LATEST + BACKLOG cover minimum. |
| 5 | OKF `knowledge/` folder | **MODIFY → DROP folder** | OKF already = `project/docs/skills/*` + design/dev/domains + repo `okf/`. Declare, don't fork. |

3-tier verdict: Operational tier fully built; minimal Tactical (story+backlog) built; Strategic stays = existing charter/phases.

## Phases
| Phase | Name | Files | Status |
|-------|------|-------|--------|
| 01 | Core policy docs | [phase-01-core-policy-docs.md](phase-01-core-policy-docs.md) | ✅ Done |
| 02 | Templates + friction reservoir + scaffolding | [phase-02-templates-scaffolding.md](phase-02-templates-scaffolding.md) | ✅ Done |
| 03 | Adopt-now v2 additions + first dogfood run | [phase-03-adopt-and-dogfood.md](phase-03-adopt-and-dogfood.md) | ✅ Done (US-001 correctly blocked at hard gate) |

Write order (Phase 01): GLOSSARY → AGENTS → HARNESS → FEATURE_INTAKE → ARCHITECTURE(pointer) → TEST_MATRIX.

## Done definition (H1, target 20–40% compliance)
- All 10 harness files exist at repo root (`AGENTS.md`, `CLAUDE.md` + 8 under `docs/`) + 3 templates.
- `CLAUDE.md` imports `@AGENTS.md`; AGENTS declares read-only vs change gate + names `project/docs/skills/*` as OKF.
- `docs/ARCHITECTURE.md` is a THIN pointer to `project/docs/ARCHITECTURE.md` + `charter.md` (no duplication).
- 1 REAL small story ran end-to-end: intake → story → proof → trace → handoff (dogfood).
- ≥1 HARNESS_BACKLOG.md entry captured from the dogfood run.
- SESSION-LATEST.md populated (Current story / Status / Blocker / Next Action / Files changed / Last commit).
- WIP=1 rule written in HARNESS.md + FEATURE_INTAKE.md.

## Climb-to-H2 signal (note only — DO NOT build H2 here)
Climb when markdown starts to hurt: (a) cannot query status across many stories; (b) hand-maintained TEST_MATRIX
table is error-prone / stale; (c) trail is lost between sessions; (d) backlog needs predicted-vs-actual. Then follow
`harness/HARNESS_BUILD_FROM_SCRATCH.md` Stage C (SQLite + CLI + CONTEXT_RULES/TRACE_SPEC).

## Risks
- Drift: SESSION-LATEST + TEST_MATRIX are hand-edited live-state → accepted small debt; keep tiny, overwrite fully.
- Over-scaffolding: strictly no initiatives/epics/knowledge folders; enforce YAGNI.
- Global vs local CLAUDE.md conflict: repo `CLAUDE.md` must not fight `~/.claude/CLAUDE.md`; it only adds `@AGENTS.md` import + repo-scope note.
- OneDrive path has spaces → all commands must quote paths (Windows/PowerShell: `Get-Date -UFormat "%y%m%d"`).

## Resolved decisions (2026-08-18, user-approved)
1. **Split confirmed** — harness meta stories → repo `docs/stories/`; product impl work stays in `project/plans/*`.
2. **WIP=1 = honor-system only at H1**; git-hook enforcement deferred to H2 (not built here).
3. **Dogfood target = Gold-layer / agent-extract** slice (Phase 03).
