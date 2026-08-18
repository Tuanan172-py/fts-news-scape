# HARNESS.md — The human ↔ agent collaboration model (news-scape, H1)

The "constitution" doc. Stable, rarely edited. Vocabulary: [GLOSSARY.md](GLOSSARY.md).
Maturity **H1**: pure markdown, no database, no CLI. The 8+1 loop below is done by hand.

## 1. Two layers

| Layer | Storage | Role |
|-------|---------|------|
| **Policy** | `docs/*.md` (this dir) | *How to work*. Stable. |
| **Durable** | *(H2+, not built)* SQLite | *What happened*. At H1 = story files + SESSION-LATEST + inline trace notes. |

A single request produces up to two outputs: a **product delta** (code/config/docs in `project/`) and a **harness delta** (a backlog/decision/doc that makes next time easier).

## 2. Request-class loops

### Read-only loop
Read only the files needed → answer, separating fact vs inference → STOP. No file/DB/config mutation. No intake, no story, no trace.

### Change loop (8 + 1 steps, markdown-adapted)

```
1. Classify   Confirm this is a CHANGE (else read-only). Check WIP=1 (§3).
2. Intake     Classify per docs/FEATURE_INTAKE.md → state Lane / Reason / Docs / Story / Validation.
3. Context    Read OKF (AGENTS.md §2) + the exact files for the lane. Stop when the path is clear.
4. Story      tiny → skip packet (note intake inline). normal/high-risk → create docs/stories/US-XXX.md from template.
5. Implement  Smallest real slice + a validation command within the lane.
6. Self-check Product truth? validation ran? architecture boundary respected? next agent unblocked?
7. Proof      Fill the story's validation table + docs/TEST_MATRIX.md row. "No proof = not implemented."
8. Friction   Fix in place OR add a docs/HARNESS_BACKLOG.md entry.
9. Handoff    Overwrite docs/SESSION-LATEST.md (see §4).
```

## 3. WIP = 1 (interrupt discipline)

At most **one** story `in_progress`. On interruption:
1. Do NOT abandon the current story silently.
2. Set it `blocked` or `deferred` with a one-line reason (and `Depends On:` if applicable).
3. Create/parks the new story, finish it, then resume the old one (read its notes first).

Honor-system only at H1 (no git-hook — that is an H2 candidate, tracked in the backlog).

## 4. Step 9 — Session handoff (SESSION-LATEST.md)

At the END of every change session, regardless of outcome (`completed`/`blocked`/`partial`), **overwrite** [SESSION-LATEST.md](SESSION-LATEST.md) with 6 fields: Current story · Status · Blocker · Next Action · Files changed · Last commit. Keep it a single screen. Overwrite, never append (no dashboard growth).

## 5. Proof rule

Status enum + proof tiers live in [TEST_MATRIX.md](TEST_MATRIX.md). A story reaches `implemented` ONLY after a real validation command ran and is recorded. Never hand-flip a proof row.

## 6. Decisions (high-risk)

When changing architecture / a public data contract / a hard-gate area → record an ADR: a file in [decisions/](decisions/) from [templates/decision.md](templates/decision.md). A trace note does NOT replace an ADR.

## 7. Definition of Done

**Read-only done:** answer has repo evidence, separates fact vs inference, repo unchanged.

**Change done:** change complete (or blocker clearly recorded); story + TEST_MATRIX current; a validation command ran (if one exists); SESSION-LATEST overwritten; friction filed if any; the final answer states *what changed* and *what was not done*.

## 8. Growth rule + climb-to-H2 signal

The harness grows from friction. Climb to H2 (SQLite + CLI, per `harness/HARNESS_BUILD_FROM_SCRATCH.md` Stage C) ONLY when markdown hurts: (a) can't query status across many stories; (b) the TEST_MATRIX hand table is stale/error-prone; (c) the trail is lost between sessions; (d) backlog needs predicted-vs-actual. Do not build H2 pre-emptively.

## 9. What an agent may / must ask

**May do directly:** story status/notes, TEST_MATRIX rows, linking story→OKF docs, intake, backlog, small clarifications.
**Must ask the human first:** changing architecture direction · removing a validation requirement · changing the risk rules · touching a hard-gate area (secrets, DB migration, external API tokens).
