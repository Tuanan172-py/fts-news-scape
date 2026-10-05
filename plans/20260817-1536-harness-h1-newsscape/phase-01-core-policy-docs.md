# Phase 01 — Core Policy Docs

## Context Links
- Parent plan: [plan.md](plan.md)
- v2 evaluation: [reports/01-v2-evaluation.md](reports/01-v2-evaluation.md)
- Research: [research/researcher-01-report.md](research/researcher-01-report.md), [research/researcher-02-report.md](research/researcher-02-report.md)
- Scout: [scout/scout-01-report.md](scout/scout-01-report.md)
- Source guides: `harness/HARNESS_BUILD_FROM_SCRATCH.md` (Part 3 file order), `harness/HARNESS_RUNBOOK.md` (8-step loop, lanes, Done)
- Product refs (do NOT duplicate): `project/docs/ARCHITECTURE.md`, `project/docs/charter.md`

## Overview
- **Date:** 2026-08-17
- **Description:** Write the 6 core policy docs at repo ROOT in strict semantic order: GLOSSARY → AGENTS → HARNESS → FEATURE_INTAKE → ARCHITECTURE(pointer) → TEST_MATRIX. Plus `CLAUDE.md` importing `@AGENTS.md`.
- **Priority:** P0 (foundation; every later file borrows vocab/rules from here).
- **Implementation status:** Planned
- **Review status:** Pending

## Key Insights
- Write order is NOT arbitrary — vocabulary first, then entrypoint, then rules (HARNESS_BUILD Part 3).
- AGENTS.md = small STABLE shim (authority gate), points elsewhere; do NOT cram detail.
- CC does not auto-load AGENTS.md → repo `CLAUDE.md` must add `@AGENTS.md` import.
- `docs/ARCHITECTURE.md` must be a THIN pointer to existing `project/docs/*` — duplication is the trap.
- OKF already exists (`project/docs/skills/*`, repo `okf/`) → declare, do not fork.
- News-scape risk flags map to concrete surfaces: dedup/DB schema, scraper config, sentiment lexicon, external API tokens (FireAnt), Bronze/Silver/Gold data contracts.

## Requirements
**Functional**
- 6 policy files + CLAUDE.md exist at correct repo-root paths.
- AGENTS.md states read-only vs change gate + names `project/docs/skills/*` as OKF.
- FEATURE_INTAKE.md risk checklist tailored to news-scape; lane rule (0–1→tiny/normal, 2–3→normal, 4+→high-risk, hard-gate→high-risk).
- ARCHITECTURE.md is a pointer/boundary doc referencing `project/docs/ARCHITECTURE.md` + `charter.md`, no re-statement of TDRs.
- TEST_MATRIX.md defines status enum + 4 proof tiers + "no proof = not done".

**Non-functional**
- English; keep technical terms (intake/lane/trace/proof) as-is.
- Concise (each file 1–2 pages). Windows/PowerShell examples where commands appear.

## Architecture
Layer = **Policy (markdown, "how to work")**. No durable/DB layer at H1. Files sit at repo root so an agent starting anywhere in the repo hits the gate first:
```
<repo root>/
  AGENTS.md          entrypoint + authority gate (shim)
  CLAUDE.md          imports @AGENTS.md (+ repo-scope note)
  docs/
    GLOSSARY.md  HARNESS.md  FEATURE_INTAKE.md  ARCHITECTURE.md  TEST_MATRIX.md
```

## Related Code Files (create — repo ROOT)
1. `docs/GLOSSARY.md` — vocab: Agent, Harness, Product Contract, Story Packet, Feature Intake, Trace, Durable Layer, Risk Lane (tiny/normal/high-risk), OKF. + news-scape terms: Bronze/Silver/Gold layer, dedup, sentiment lexicon, source domain.
2. `AGENTS.md` — build/run cmds (point to `project/`); `## Harness` section: golden rule (read-only → only read; change → intake first); name `project/docs/skills/*` + repo `okf/` as OKF; WIP=1 one-liner; link to `docs/HARNESS.md`.
3. `docs/HARNESS.md` — lifecycle intent→intake→story→product delta→proof→harness delta; Request-Class Loops (read-only vs 8-step change loop, markdown-adapted: no bootstrap/CLI, steps become manual); WIP=1 rule; Done Definition; reserve **step 9 = write SESSION-LATEST handoff** (wired in Phase 03).
4. `docs/FEATURE_INTAKE.md` — input types (new spec, spec slice, change, new initiative, maintenance, harness improvement); news-scape risk checklist (see Impl Steps); lane rule; per-lane requirements; WIP=1 intake refusal (park 2nd In-Progress → backlog).
5. `docs/ARCHITECTURE.md` — THIN pointer: "Product architecture lives in `project/docs/ARCHITECTURE.md` (TDR-001..006) + `project/docs/charter.md` (goals/phases). This file only states the harness↔product boundary + Discovery-Before-Shape + Dependency Rule reminder." No TDR copy.
6. `docs/TEST_MATRIX.md` — status enum (planned/in_progress/implemented/changed/retired) + proof tiers (Unit/Integration/E2E/Platform) + "no proof = not done"; hand table seeded empty.
7. `CLAUDE.md` — single line `@AGENTS.md` + note: repo-scoped, extends global `~/.claude/CLAUDE.md`, does not override it.

## Implementation Steps
1. Create `docs/` at repo root (if absent) — quote path (spaces).
2. Write `docs/GLOSSARY.md` FIRST (all later files reference it).
3. Write `AGENTS.md` — keep small; authority gate + OKF declaration + WIP=1 pointer.
4. Write `docs/HARNESS.md` — lifecycle + loops + Done; leave step-9 handoff placeholder.
5. Write `docs/FEATURE_INTAKE.md`. Map news-scape **risk flags** (mark each applicable):
   - touches dedup logic or DB schema (SQLite monocle.db / Bronze-Silver-Gold);
   - changes scraper config (`project/config/domains/*.yaml`, settings.yaml);
   - edits sentiment lexicon/classification rules;
   - touches external API tokens/secrets (FireAnt, etc.);
   - changes a public data contract (Bronze/Silver/Gold schema, handoff/agent-io contract);
   - schema migration / irreversible data change (**hard gate → high-risk**).
6. Write `docs/ARCHITECTURE.md` as pointer ONLY (verify it references, not restates, `project/docs/*`).
7. Write `docs/TEST_MATRIX.md` (vocab + empty table).
8. Write `CLAUDE.md` with `@AGENTS.md` + repo-scope note; confirm no conflict with global CLAUDE.md.

## Todo List
- [ ] Create repo-root `docs/`
- [ ] docs/GLOSSARY.md
- [ ] AGENTS.md (gate + OKF + WIP=1)
- [ ] docs/HARNESS.md (loops + Done + step-9 placeholder)
- [ ] docs/FEATURE_INTAKE.md (news-scape risk flags + lanes)
- [ ] docs/ARCHITECTURE.md (thin pointer)
- [ ] docs/TEST_MATRIX.md (enum + tiers)
- [ ] CLAUDE.md (@AGENTS.md import)

## Success Criteria
- 7 files exist at listed repo-root paths.
- AGENTS.md unambiguously answers "may I change the repo?" + names OKF source.
- FEATURE_INTAKE risk flags are news-scape-specific (not generic).
- ARCHITECTURE.md contains zero duplicated TDR content; only references + boundary.
- CLAUDE.md `@AGENTS.md` import present; global instructions untouched.

## Risk Assessment
- **Duplication drift** (ARCHITECTURE): mitigate — pointer only, review for copied TDRs.
- **CLAUDE.md conflict** with `~/.claude/CLAUDE.md`: mitigate — additive only (import + scope note).
- **Over-detailed AGENTS.md**: mitigate — keep as shim, push detail to HARNESS.md.

## Security Considerations
- FEATURE_INTAKE must flag external API tokens (FireAnt) + secrets (`config/settings.yaml`) as risk → high-risk lane, human gate.
- Do NOT write any secret values into harness docs; reference config paths only.

## Next Steps
- Depends on: nothing (foundation).
- Enables: Phase 02 (templates reference GLOSSARY vocab + story fields).
