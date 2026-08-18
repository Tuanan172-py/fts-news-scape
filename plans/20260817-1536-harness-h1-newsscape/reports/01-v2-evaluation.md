# Report 01 — v2 Proposal Evaluation & Critique

**Date:** 2026-08-17 | **Scope:** verdict on the 5 v2-proposal additions for news-scape H1
**Inputs:** research/researcher-01-report.md, research/researcher-02-report.md, scout/scout-01-report.md, harness/HARNESS_BUILD_FROM_SCRATCH.md, harness/HARNESS_RUNBOOK.md

---

## Verdict summary

| # | v2 addition | Verdict | Core-philosophy reason |
|---|-------------|---------|------------------------|
| 1 | Initiative→Epic→Story hierarchy + `docs/initiatives/` + `docs/epics/` folders | **DEFER-to-H2 (folders: DROP)** | Grows-from-friction. No backlog >10 items yet. Harness already has intake type "New initiative" + H2 tables `story_dependency`/`story_hierarchy`. |
| 2 | Session Handoff `SESSION-LATEST.md` | **KEEP-NOW** | Genuine gap (cross-session agent memory). Cheap, proven single-pointer pattern. Small accepted debt at H1. |
| 3 | Interrupt / WIP=1 discipline | **KEEP-NOW (as written rule, no new file)** | Kanban WIP=1 is sound; parallel stories confuse agent memory. Zero-cost = a rule in HARNESS.md + FEATURE_INTAKE.md. |
| 4 | Project Health dashboard `PROJECT_HEALTH.md` | **DEFER-to-H2** | Live-state-in-markdown anti-pattern → drifts/stales. Belongs to a DB query (`harness-cli health`) at H2. |
| 5 | OKF knowledge base `knowledge/` folder | **MODIFY → DROP the new folder** | Project ALREADY has OKF = `project/docs/skills/*` + design/dev/domains/. Declare them, do not fork a parallel tree. |

---

## Detail per addition

### 1. Initiative→Epic→Story hierarchy + new folders — DEFER (folders DROP)
- Violates friction-first (researcher-01 §2): Epic/Initiative ceremony premature for a tiny team; "walking skeleton > ceremony"; add hierarchy when backlog exceeds 10 items.
- Redundant with existing mechanisms (researcher-02 §B, §F): intake input-type **"New initiative"** already exists (charter.md line 90; RUNBOOK line 90); H2 tables `story_dependency`/`story_hierarchy` formalize hierarchy later.
- **H1 representation of Epic (informal):** reuse the project's existing **Phase 1/2/3** concept from `project/docs/charter.md` §4.2 as the Epic surrogate + a free-text `Parent / Epic` field in the story template. **No parallel folders.**

### 2. Session Handoff (SESSION-LATEST.md) — KEEP-NOW
- Genuine gap: single-machine, single-agent, multi-session work loses "where was I" between sessions (researcher-01 §1, §5).
- Single-pointer file, fields: **Current story, Status, Blocker, Next Action, Files changed, Last commit.**
- **Nuance (declare as debt):** this IS technically live-state-in-markdown. Accepted at H1 because it is tiny + fully overwritten each session (not an accumulating dashboard like #4). Migrates into DB `trace.next_action` / trace tier at H2.
- Location decision (resolves researcher-01 open Q): **repo ROOT `docs/SESSION-LATEST.md`** per user landing-zone decision.

### 3. Interrupt / WIP=1 — KEEP-NOW as written rule
- Sound (researcher-01 §4, Atlassian WIP limits). "Never 2 stories In Progress."
- Cost-appropriate: a paragraph in `docs/HARNESS.md` (lifecycle) + a line in `docs/FEATURE_INTAKE.md` (intake refuses a 2nd In-Progress story → park in backlog). **No new file, no CI gate at H1** (honor system).

### 4. Project Health dashboard — DEFER-to-H2
- Classic live-state-in-markdown anti-pattern (researcher-01 §3; HARNESS_BUILD pitfalls table). Hand-maintained status drifts → loss of trust → ignored.
- At H1 the minimum is already covered: **SESSION-LATEST.md** (now-state) + **HARNESS_BACKLOG.md** (friction) + **TEST_MATRIX.md** (proof vocab, hand table). A real health view = DB query at H2.

### 5. OKF knowledge base — MODIFY → DROP new folder
- Project already owns the knowledge base (researcher-02 §D): `project/docs/skills/*` (cafef.md, fireant.md, rss-sources.md, tnck.md) + `design/`, `dev/`, `domains/` subfolders. There is ALSO a repo-root `okf/` framework folder (playbooks, references, toolbox) — a second existing asset.
- **Action:** DECLARE these as the priority OKF context source inside `AGENTS.md` + `docs/HARNESS.md`. Do NOT create a parallel `knowledge/` tree. Folds into H2 `CONTEXT_RULES.md` retrieval triggers later.

---

## 3-tier model verdict (Strategic / Tactical / Operational)
Good mental model, but at H1 instantiate only:
- **Operational tier** — story + proof + trace + handoff (the 8-step loop, markdown-adapted). ← fully built.
- **Minimal Tactical tier** — story template + HARNESS_BACKLOG.md. ← built.
- **Strategic tier** — stays as the EXISTING `project/docs/charter.md` (goals G-1..G-13) + Phase 1/2/3. ← NOT re-created; referenced.

---

## Open questions
1. Should `docs/stories/` / `docs/decisions/` hold the harness stories, or should real work stay under `project/plans/*`? (Plan assumes harness stories → repo-root `docs/stories/`; product implementation plans stay under `project/plans/`.)
2. WIP=1 enforcement without a CI gate — honor-system only at H1; git-hook branch check is an H2 candidate (researcher-01 open Q).
