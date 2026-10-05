# Phase 03 — Adopt-Now v2 Additions + First Dogfood Run

## Context Links
- Parent plan: [plan.md](plan.md)
- Prev phases: [phase-01-core-policy-docs.md](phase-01-core-policy-docs.md), [phase-02-templates-scaffolding.md](phase-02-templates-scaffolding.md)
- v2 evaluation: [reports/01-v2-evaluation.md](reports/01-v2-evaluation.md) (#2 SESSION-LATEST KEEP, #3 WIP=1 KEEP, #5 OKF declare)
- Source guide: `harness/HARNESS_RUNBOOK.md` (8-step loop §2, Done §12), research/researcher-01-report.md (§1 handoff, §4 WIP)
- Candidate dogfood work: existing pending Gold-layer / agent-extract task (commit `7adc68a` "prepare gold layer for agent extract")

## Overview
- **Date:** 2026-08-17
- **Description:** Wire the 2 adopt-now v2 additions (SESSION-LATEST handoff + WIP=1 rule), declare OKF, then run ONE real small piece of work end-to-end (intake → story → proof → trace → handoff) to validate the harness and seed the friction backlog.
- **Priority:** P0 (validates the whole H1 build; H1 not "done" without a real run).
- **Implementation status:** Planned
- **Review status:** Pending

## Key Insights
- SESSION-LATEST.md = single-pointer handoff; accepted live-state debt because tiny + fully overwritten (v2 #2). → migrates to DB `next_action` at H2.
- WIP=1 is a written honor-system rule at H1 (no CI/git-hook). Belongs in HARNESS.md + FEATURE_INTAKE.md.
- OKF = existing `project/docs/skills/*` + `project/docs/{design,dev,domains}/` + repo `okf/`. Just declared, not forked.
- Dogfood MUST be real (source guide Stage B): a real story exposes real friction → first genuine backlog entry.
- The 8-step loop is markdown-adapted: no bootstrap/CLI; intake/proof/story/trace become hand-written markdown; add step 9 = handoff.

## Requirements
**Functional**
- `docs/SESSION-LATEST.md` created + populated: Current story, Status, Blocker, Next Action, Files changed, Last commit.
- SESSION-LATEST protocol wired as **step 9** of the change loop in `docs/HARNESS.md` (write/overwrite at end of every session).
- WIP=1 rule text present in `docs/HARNESS.md` + `docs/FEATURE_INTAKE.md` (finalized here if placeholdered in Phase 01).
- OKF source explicitly declared in `AGENTS.md` + `docs/HARNESS.md`.
- 1 real story file in `docs/stories/US-001-*.md` completed through intake→story→proof→trace→handoff.
- ≥1 real `docs/HARNESS_BACKLOG.md` entry from the run.
- `docs/TEST_MATRIX.md` updated with the story's proof row.

**Non-functional**
- Keep SESSION-LATEST tiny (single screen). Overwrite, do not append (no dashboard growth).

## Architecture
Adds the handoff pointer + closes the operational loop:
```
intent → intake(FEATURE_INTAKE) → story(templates/story → docs/stories/US-001)
       → product delta(the real work) → proof(TEST_MATRIX row + validation-report)
       → trace(inline in story / notes) → step 9: SESSION-LATEST handoff
       → friction → HARNESS_BACKLOG entry
```
SESSION-LATEST is the only mutable-state markdown file (accepted debt). Everything else is immutable-ish policy/records.

## Related Code Files
**Create (repo ROOT)**
1. `docs/SESSION-LATEST.md` — 6 fields, populated from the dogfood run.
2. `docs/stories/US-001-<slug>.md` — real story (e.g. a small slice of Gold-layer / agent-extract).

**Modify (repo ROOT)**
3. `docs/HARNESS.md` — finalize step 9 (SESSION-LATEST protocol) + WIP=1 rule + OKF declaration.
4. `docs/FEATURE_INTAKE.md` — finalize WIP=1 intake refusal (2nd In-Progress → backlog).
5. `AGENTS.md` — finalize OKF declaration line.
6. `docs/TEST_MATRIX.md` — add US-001 proof row.
7. `docs/HARNESS_BACKLOG.md` — replace example row with ≥1 real friction entry.

## Implementation Steps
1. Create `docs/SESSION-LATEST.md` skeleton (6 fields).
2. Finalize step 9 in `docs/HARNESS.md`: "At end of session, overwrite SESSION-LATEST.md."
3. Finalize WIP=1 rule text in HARNESS.md + FEATURE_INTAKE.md.
4. Finalize OKF declaration in AGENTS.md + HARNESS.md (point to `project/docs/skills/*`, `project/docs/{design,dev,domains}/`, repo `okf/`).
5. **Dogfood run** — pick 1 small real slice (proposed: a slice of Gold-layer / agent-extract):
   a. Intake it via FEATURE_INTAKE (state Lane / Reason / Docs / Story / Validation).
   b. Instantiate `docs/stories/US-001-*.md` from template; set `Parent / Epic: Phase 3`.
   c. Do the smallest real work slice; run a validation command; fill validation table + evidence.
   d. Update `docs/TEST_MATRIX.md` with the proof row (only via completed proof, not hand-flip to implemented).
   e. Write the trace (inline notes: actions, files read/changed, outcome).
   f. Step 9: populate SESSION-LATEST.md.
   g. Record ≥1 real friction line in HARNESS_BACKLOG.md.
6. Self-inspect with the 11-responsibility checklist (task-spec/context/memory/verification covered?).

## Todo List
- [ ] docs/SESSION-LATEST.md skeleton
- [ ] HARNESS.md step 9 (handoff protocol) finalized
- [ ] WIP=1 rule finalized (HARNESS.md + FEATURE_INTAKE.md)
- [ ] OKF declared (AGENTS.md + HARNESS.md)
- [ ] Dogfood: intake → US-001 story → proof → TEST_MATRIX row → trace → handoff
- [ ] ≥1 real HARNESS_BACKLOG entry
- [ ] 11-responsibility self-inspection

## Success Criteria
- SESSION-LATEST.md populated with all 6 fields.
- WIP=1 rule + OKF declaration present in the named files.
- US-001 story completed end-to-end with a real proof row in TEST_MATRIX.
- ≥1 genuine (not placeholder) backlog entry.
- H1 Done-definition (plan.md) fully satisfied → 20–40% compliance target met.

## Risk Assessment
- **Dogfood chosen too big**: mitigate — pick the SMALLEST real slice (a single-file change with a runnable check).
- **SESSION-LATEST grows into a dashboard**: mitigate — enforce overwrite-only, single-screen.
- **Hand-flip proof to implemented**: mitigate — TEST_MATRIX row only set after a real validation command ran ("no proof = not done").
- **WIP=1 ignored** (no CI gate): mitigate — honor system + note as H2 git-hook candidate in backlog.

## Security Considerations
- If dogfood touches FireAnt tokens / `config/settings.yaml` → intake flags it high-risk → human gate before proceeding.
- SESSION-LATEST "Files changed" must not leak secret values; list paths + commit hash only.

## Next Steps
- Depends on: Phase 01 + Phase 02.
- After H1: operate a few more real stories, collect friction. Climb to H2 ONLY when markdown hurts (see plan.md climb signal). Do NOT build H2 in this plan.
