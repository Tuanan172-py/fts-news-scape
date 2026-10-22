# HARNESS.md — The human ↔ agent collaboration model (news-scape, H5)

The "constitution" doc. Stable, rarely edited. Vocabulary: [GLOSSARY.md](GLOSSARY.md).
Maturity **H5**: durable layer (`harness.db`, `scripts/harness_cli.py`), scoring, auto-verification and self-improvement (see HARNESS_MATURITY.md). The loop below is tracked by the CLI; it records state and does not gate work (ADR-0026.D2).

## 1. Two layers

| Layer | Storage | Role |
|-------|---------|------|
| **Policy** | `docs/*.md` (this dir), `docs/knowledge/README.md`, `.agents/rules/*.md` | *How to work*. Stable. |
| **Durable** | `harness.db` (SQLite), written by `scripts/harness_cli.py` | *What happened*: intake, story, decision, trace, backlog, metric rows. Story and ADR files stay the source; `doc sync` derives their rows. |

A single request produces up to two outputs: a **product delta** (code/config/docs in `project/`) and a **harness delta** (a backlog/decision/doc that makes next time easier).

## 2. Request-class loops and per-prompt lifecycle

Every prompt goes through three core steps: **Classify (3 tiers) → Execute & Proof → Harness Closure**.

```
1. Classify   Put the request into one of three tiers: Tiny / Normal / High-Risk. Record the intake with harness_cli intake.
2. Context    Read documents per the docs/CONTEXT_RULES.md matrix (token budget per lane).
3. Execute    - Tiny: answer or patch directly.
              - Normal: WIP=1, create docs/stories/US-NNN-<slug>.md with harness_cli doc new, code and run unit/integration tests.
              - High-Risk: stop at the hard gate, write an ADR in docs/decisions/, ask the user for approval.
4. Proof      Run the mechanical test command and check the result.
5. Trace      Record a trace (Minimal / Standard / Detailed) in harness.db with harness_cli trace.
6. Closure    Print the Harness Closure Table (mandatory).
```

## 3. WIP = 1 per worktree (interrupt discipline)

At most **one** story `in_progress` per git worktree, declared by its `branch` (ADR-0022). Other worktrees run in parallel with equal authority. On interruption inside a worktree:
1. Do NOT abandon the current story silently.
2. Set it `blocked` or `deferred` with a one-line reason (and `Depends On:` if applicable).
3. Create or park the new story, finish it, then resume the old one (read its notes first).

## 4. Step 6 — Mandatory Harness Closure Protocol

At the end of **every answer or execution session** the agent prints the closure table. `harness_cli.py session close` prints it with these rows:

```markdown
### Harness Closure Protocol

| File / Component | Updated? | Reason & Evidence |
|:---|:---:|:---|
| `harness.db` *(Trace & Intake)* | **Yes** | Trace #ID (Lane: `tiny/normal/high-risk`, Outcome: completed). |
| `docs/stories/US-NNN-<slug>.md` | **Yes / No** | Created / updated / not needed (Tiny task). |
| `docs/TEST_MATRIX.md` | **Yes / No** | X tests passed / no new test. |
| `docs/decisions/NNNN-*.md` | **Yes / No** | ADR written for an architecture change / no hard gate touched. |
| `docs/SESSION-LATEST.md` | **Yes / No** | Handoff state updated / unchanged. |
| `docs/HARNESS_BACKLOG.md` | **Yes / No** | Friction recorded / no friction. |
| `Git Codebase Status` | **Clean / Dirty** | Commit and branch, `clean_for_closure`. |
```

## 5. Proof Rule

Status enum + proof tiers live in [TEST_MATRIX.md](TEST_MATRIX.md). A story reaches `implemented` ONLY after a real validation command ran and is recorded in `harness.db`. Never hand-flip a proof row.

## 6. Decisions (High-Risk)

When changing architecture / a public data contract / a hard-gate area → record an ADR with `python scripts/harness_cli.py doc new --type adr --title "..."`; files live in [decisions/](decisions/). A trace note does NOT replace an ADR. Accepted ADR bodies are frozen (K-R8).

## 7. Definition of Done

**Done criteria:**
1. The task meets the request and has clear empirical evidence.
2. A durable trace is recorded in `harness.db` (`score_trace` $\ge 0.75$, `score_context` $\ge 0.8$).
3. The **Harness Closure Protocol** table is printed in full at the end of the response.

## 8. Growth rule

The harness grows from friction. Add durable tooling only when a recorded friction shows that a document or table hurts: (a) status cannot be queried across stories; (b) a hand table goes stale; (c) the trail is lost between sessions; (d) backlog needs predicted-vs-actual. Record the friction first (`harness_cli.py backlog add`), then propose the change (`harness_cli.py propose`).

## 9. What an agent may / must ask

**May do directly:** story status/notes, TEST_MATRIX rows, linking story→OKF docs, intake, backlog, small clarifications.
**Must ask the human first:** changing architecture direction · removing a validation requirement · changing the risk rules · touching a hard-gate area (secrets, DB migration, external API tokens).
