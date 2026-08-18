# Building a Custom Harness From Scratch — Step-by-Step Design & Execution Guide (EN)

> Purpose of this document: a guide to **building a brand-new harness by hand** for a
> fresh agent/project — WITHOUT pulling in the old harness repo wholesale — borrowing
> only the **foundational direction** (philosophy, model, ordering) from a reference
> harness framework.
>
> This document is a distillation produced after deeply studying the 3 layers of the
> reference harness framework: **policy docs**, **durable layer (SQLite + CLI)**, and
> **contract + decisions**. Read alongside `docs/HARNESS_RUNBOOK.md` (day-to-day
> operation).

---

## Part 0 — How to read this document

The document has 7 parts, moving from **mindset → roadmap → file-writing order → data
design → execution checklist → pitfalls → decisions to record**.

If you only have 5 minutes: read **Part 1** (philosophy), **Part 2** (the H1→H5 roadmap),
and **Part 5** (the checklist). Parts 3–4 are the detail for actually getting hands-on.

The principle that governs the entire guide:

> **The harness grows from friction; it is not built top-down in advance.**
> Start with the smallest thing that runs (H1, pure markdown, NO database), and add a
> new layer only when a real piece of work exposes a gap. Don't build H5 when you don't
> have a single trace yet.

---

## Part 1 — Foundational mindset: what a harness is, and what it is for

### 1.1 Definition

> **App is what users touch. The harness is what agents touch.**

The harness = a **repo-level operating system** that turns *human intent* into *safe,
evidence-backed product change*. It is NOT product code. It is the discipline layer
wrapped around: classify the work, choose the context, record what happened, prove it,
and improve itself.

A single request can produce 2 kinds of output:
- **Product delta** — code, tests, API, schema, product docs.
- **Harness delta** — docs/template/backlog/decision that make next time easier.

### 1.2 Six design principles (the backbone of every decision)

| # | Principle | Meaning when building |
|---|------------|------------------|
| 1 | **Separate Policy ↔ Durable** | Markdown holds *how to work* (rules, vocab, templates). The database holds *what happened* (intake, story, trace). Don't stuff live state into markdown. |
| 2 | **Grows from friction** | Don't design everything up front. Hit pain → record it → recurs often → then upgrade. |
| 3 | **Proof-driven** | "No evidence = not implemented." Every claim must have mechanical proof (test/verify command). |
| 4 | **Request-class authority gate** | Classify the request FIRST: read-only cannot change state; only change/build/fix may mutate. High-risk must stop and ask the human. |
| 5 | **Bounded context** | Read only the context the phase + lane needs. Don't cram in the maximum. There is a token budget. |
| 6 | **Verifiable maturity** | A level is only "reached" when it can be verified in a file/DB/benchmark. No self-congratulation. |

An important sub-point: **degrade-don't-fail** — a missing optional capability is *a
reported event*, not a blocking failure. The core harness still runs smoothly on a
blank machine.

### 1.3 Goals & expectations

**Goals** of a good harness:
1. A new agent, ignorant of the project, reads `AGENTS.md` and knows *what to do first*.
2. There is never a repo change without a risk classification.
3. There is never a "done" claim without evidence.
4. Every run leaves a trace behind for next time.
5. When pain recurs, the harness proposes fixes to itself (the mature stage).

**Realistic expectations:** your v0 will be **rough** and **pure markdown**. That is
CORRECT. 20–40% compliance at H1 is a valid starting target. The database comes later.

---

## Part 2 — Maturity roadmap H0 → H5 (the route map)

This is the evolution model. **Each level is climbed only when the level below is truly
operational.** Each level *activates* new responsibilities.

```
H0  Bare        : prompt in → patch out. No harness. (starting point)
      │  + write static policy
      ▼
H1  Scaffolding : static rules, templates, risk lane, source-of-truth.
      │           PURE MARKDOWN, NO DATABASE.  ← your v0 stops here first
      │  + add durable layer
      ▼
H2  Durable     : SQLite + CLI recording intake/story/decision/backlog/trace.
      │           + component taxonomy, trace spec, context rules.
      │  + measurement
      ▼
H3  Active Obs. : score traces, friction grouped by component,
      │           backlog predicted-vs-actual.
      │  + automate verify
      ▼
H4  Auto-Verify : stories have verify_command, verify gate before close.
      │  + self-improve
      ▼
H5  Self-Improve: entropy audit + propose (rule-based, evidence-backed) +
                  measure outcome, human approves every high-risk one.
```

**One-sentence reading:** *static policy (H1) → record what happened (H2) → measure it
(H3) → gate on evidence (H4) → let the harness propose its own fixes, human approves (H5).*

**Required-file table by level:**

| Level | Newly appearing files/infrastructure |
|-----|---------------------------|
| **H1** | `AGENTS.md`, `docs/HARNESS.md`, `docs/FEATURE_INTAKE.md`, `docs/ARCHITECTURE.md`, `docs/TEST_MATRIX.md`, `docs/GLOSSARY.md`, `docs/templates/{story,decision,validation-report}.md` |
| **H2** | CLI + `scripts/schema/001-init.sql`, `docs/HARNESS_COMPONENTS.md`, `docs/HARNESS_MATURITY.md`, `docs/TRACE_SPEC.md`, `docs/CONTEXT_RULES.md` |
| **H3** | trace scoring (`score-trace`/`score-context`), friction-by-component, backlog outcome loop |
| **H4** | `docs/TOOL_REGISTRY.md`, story `verify_command`, verify gate at trace time |
| **H5** | `docs/HARNESS_AUDIT.md`, `docs/IMPROVEMENT_PROTOCOL.md`, `propose`, intervention |

> **Key recommendation:** Build **the whole of H1 first**, operate a few real pieces of
> work, then decide whether you need H2 (the database) at all. Many small projects live
> perfectly well at pure-markdown H1.

---

## Part 3 — File-WRITING order (detailed, with logic/goal/expectations)

This is the "which file to write first, which later" part. The order is NOT arbitrary —
it follows semantic dependency: *vocabulary first → entrypoint → classification rules →
context rules → templates → (only then) durable*.

### H1 LAYER — Pure markdown (do 100% before thinking about a database)

#### File 1 — `docs/GLOSSARY.md`  *(write FIRST)*
- **Logic:** Every later file borrows vocabulary from here. Without a glossary, the later
  docs will define terms in overlapping, contradictory ways.
- **Minimum content:** definitions of *Agent, Harness, Product Contract, Story
  Packet, Feature Intake, Trace, Durable Layer, Risk Lane (tiny/normal/high-risk)*.
- **Goal:** one word = one single meaning across the whole project.
- **Expectation:** short (1–2 pages), grows as concepts are added.

#### File 2 — `AGENTS.md`  *(entrypoint — the single gate)*
- **Logic:** This is the file the agent reads FIRST each session. It must **pick a request
  class before doing anything**. Keep it SMALL and STABLE (a shim), pointing to the
  detailed docs.
- **Minimum content:** project build/run commands; a **## Harness** section with the
  golden rule: *read-only → only read, no mutate; change → intake first*.
- **Goal:** an unfamiliar agent reads it and immediately knows "am I allowed to change the
  repo or not".
- **Expectation:** this is the authority contract. Don't cram detail in; point elsewhere.
- **CC note:** Claude Code does not auto-load `AGENTS.md`. If using CC, add an
  `@AGENTS.md` line in `CLAUDE.md` to import it.

#### File 3 — `docs/HARNESS.md`  *(the human ↔ agent collaboration model)*
- **Logic:** Explains the end-to-end lifecycle: intent → intake → story → work loop
  → product delta → proof → harness delta. Defines the **Request-Class Loops**
  (read-only vs the 8-step change) and the **Done Definition**.
- **Goal:** the shared thinking framework; where everyone looks up "what is the standard
  process".
- **Expectation:** this is the "constitution" doc. Stable, rarely edited.

#### File 4 — `docs/FEATURE_INTAKE.md`  *(the risk-classification machine)*
- **Logic:** The classification gate. Defines **input types**, the **risk checklist**,
  the **lane selection rule** (0–1 flag→tiny/normal; 2–3→normal; 4+→high-risk; hard gate→
  high-risk), and the **per-lane requirements**.
- **Goal:** humans do NOT have to rank risk themselves — the harness does it,
  deterministically.
- **Expectation:** at the end of intake, the agent can state: `Lane / Reason / Docs / Story /
  Validation`.

#### File 5 — `docs/ARCHITECTURE.md`  *(the boundary rules of the PRODUCT)*
- **Logic:** This is the ONLY doc about *the product being built*, not about the harness.
  Uses **Discovery-Before-Shape** (discover surfaces/stack/domains/validation
  ladder before shaping) and the **Dependency Rule** (inner layers do not depend on
  outer layers).
- **Goal:** the agent knows "where new code goes, what it is allowed to depend on".
- **Expectation:** on a new project, most of it is discovery questions with no answers yet —
  that is acceptable. Fill in gradually as real code appears.

#### File 6 — `docs/TEST_MATRIX.md`  *(the evidence vocabulary)*
- **Logic:** Defines the status enum **planned / in_progress / implemented /
  changed / retired** and the 4 proof layers **Unit / Integration / E2E / Platform**,
  along with the golden rule *"no evidence = not implemented"*.
- **Goal:** a shared language for talking about progress + evidence.
- **Expectation:** at H1 this is a hand-written markdown table; at H2 it moves into the DB
  (`query matrix`) and this file only keeps the *vocabulary*.

#### Files 7–9 — Templates  *(reusable scaffolds)*
Write the 3 core scaffolds (skip the advanced ones at first):
- `docs/templates/story.md` — **the most important**. Sections: Title (US-XXX),
  Status, Lane, Product Contract, Acceptance Criteria, Design Notes, a
  Validation table (Unit/Integration/E2E/Platform), Harness Delta, Evidence.
- `docs/templates/decision.md` — ADR: Context, Decision, Alternatives,
  Consequences (Positive/Tradeoffs), Follow-Up. Status matches the enum
  Proposed/Accepted/Superseded/Rejected.
- `docs/templates/validation-report.md` — Scope, Commands Run, a Results table
  (default "not run"), Evidence, Gaps.

**Advanced scaffolds — for later (only when you need the high-risk lane):**
`docs/templates/spec-intake.md` (onboard a large spec) and the directory
`docs/templates/high-risk-story/{overview,design,execplan,validation}.md`.

#### File 10 — `docs/HARNESS_BACKLOG.md`  *(the friction reservoir)*
- **Logic:** Where you record "missing harness capability" while working, when you don't
  want to change the process right away. Fields: Title, Discovered While, Current Pain,
  Suggested Improvement, Risk (lane), Status.
- **Goal:** realize the "grows from friction" principle from day one.
- **Expectation:** at H2+ it moves into the DB (`backlog` table); this file only keeps the template.

> **H1 wrap-up:** After these 10 files you have a WORKING harness, without a single line of
> code. Operate a few real pieces of work. Record friction. Only climb to H2 when the
> markdown tables start to hurt (hard to query, error-prone, loss of observability).

---

### H2 LAYER — Add the Durable Layer (only when markdown already hurts)

Before writing code, write the 4 docs that define the durable layer:

#### File 11 — `docs/CONTEXT_RULES.md`  *(read the right amount, know when to stop)*
- **Logic:** The **phase × lane** matrix (Intake/Planning/Implementation/Validation/
  Trace) with each cell Must/Should/Skip, + the **token budget** (tiny ~2K, normal ~5K,
  high-risk ~10K), + the **retrieval triggers**.
- **Goal:** stop the agent from cramming in context recklessly; make context selection measurable.

#### File 12 — `docs/TRACE_SPEC.md`  *(the standard for evidence left behind)*
- **Logic:** 3 tiers **Minimal(1)/Standard(2)/Detailed(3)** mapped by lane; defines
  each trace field (`task_summary`, `outcome`, `actions_taken`,
  `files_read/changed`, `harness_friction`...).
- **Goal:** traces that are useful for review + benchmark + later self-improvement.

#### Files 13–14 — `docs/HARNESS_COMPONENTS.md` + `docs/HARNESS_MATURITY.md`
- **Logic:** Components = the **11 runtime responsibilities** (task spec, context, tool
  access, memory, task state, observability, failure attribution, verification,
  permissions, entropy audit, intervention). Maturity = the definitions of H0–H5.
- **Goal:** use them as a *design lens* ("does my v0 already cover task-spec /
  context / memory / verification?") and a *maturity yardstick*.
- **Expectation:** use the 11-responsibility checklist even at H1 to self-inspect the design.

#### THEN comes the CODE — CLI + Schema (see Part 4 for table order)
- `scripts/schema/001-init.sql` + a thin CLI to operate the DB.
- The big decision: **language/engine**. The reference framework chose a **Rust prebuilt
  binary + SQLite** (see decisions 0004, 0005). You may choose otherwise (Python +
  SQLite, Go + embedded...) AS LONG AS you keep: queryable, safe concurrent writes,
  distribution that doesn't force the consumer to install a toolchain.

---

### H3–H5 LAYER — Advanced (add when you have enough data to measure)

- **H3:** `score-trace`, `score-context`, group friction by component, backlog
  predicted-vs-actual.
- **H4:** `docs/TOOL_REGISTRY.md` (outbound manifest + inbound registry + degrade
  ladder), story `verify_command`, verify gate at trace time.
- **H5:** `docs/HARNESS_AUDIT.md` (6 weighted drift checks → entropy score),
  `docs/IMPROVEMENT_PROTOCOL.md` (friction+intervention+audit → propose → human
  approves with 1 key → outcome loop), the `intervention` table.

> `HARNESS_AUDIT.md` and `IMPROVEMENT_PROTOCOL.md` are **the most advanced** — the machine
> fixing itself, meaningless before you have accumulated records. Don't write them early.

---

## Part 4 — Designing the DURABLE LAYER: data model & table order

Only read this part once you have decided to climb to H2. This is "which table to write
first" at the DB layer.

### 4.1 The five core tables (migration 001 — enough to OPERATE)

| Table | Role | Key columns |
|------|---------|-----------|
| `schema_version` | Ledger of applied migrations | `version PK`, `applied_at` |
| `intake` | Classify incoming work | `input_type`(CHECK enum), `summary`, `risk_lane`, `risk_flags`(JSON), `story_id`(soft) |
| `story` | Work packet + proof (THE HEART) | `id TEXT PK` (US-XXX), `status`(enum), `unit/integration/e2e/platform_proof`(INTEGER 0/1), `evidence` |
| `decision` | Durable ADR | `id TEXT PK`, `status`(enum), `doc_path`, `predicted_impact`, `actual_outcome` |
| `trace` | Observability per run | `task_summary`, `intake_id`→intake, `story_id`→story, `actions/files_*`(JSON), `outcome`(enum) |

`backlog` is also in 001 but it is the self-improvement loop — useful early, not required
to *operate*.

### 4.2 Relationship diagram (core)

```
   intake ──intake_id──▶ trace ◀──story_id── story
     │(story_id soft)      │                   ▲
     │                     ▼                    │(FK from several advanced tables)
     └····▶ story    intervention (FK→trace)   │
                                                │
   decision (independent)  backlog (independent at v0)
```
Remember: `trace` is the first table with a **real FK** (into `intake` + `story`).
`intake.story_id` and `intervention.story_id` are **soft links** (TEXT, no FK).

### 4.3 Table build order (by dependency — HARD RULE)

1. `schema_version` **first of all** + enable `PRAGMA journal_mode=WAL`,
   `foreign_keys=ON`.
2. `story` — is the **FK target of the most tables**. Nothing that references story may
   come before it.
3. `intake` — is referenced by `trace.intake_id`; build before trace.
4. `decision`, `backlog` — independent, no FK into them at v0.
5. `trace` — AFTER `intake` + `story` (real FK into both).
6. `intervention` — AFTER `trace` (FK into `trace.id`).
7. `tool`, `changeset_applied` — independent infrastructure, fine anytime.
8. `story_dependency`, `story_hierarchy` — AFTER `story` (self-join many-to-many).
9. **(advanced)** The UNIQUE index on `uid` must exist **BEFORE** any table referencing
   `backlog(uid)` — SQLite FKs require a unique parent index.

> One-line rule: **`story` before anything referencing it; `intake`+`story` before
> `trace`; `trace` before `intervention`.**

### 4.4 Advanced tables (add gradually as you mature)
`tool` (+ scan columns) → tool awareness · `intervention` → oversight ·
`changeset_applied` (+ sha) → idempotent content-pack distribution ·
`story_dependency`/`story_hierarchy` → work graph · the cluster `uid` +
`proposal_evidence_link` + `backlog_outcome_observation` + `audit_evidence_
episode` + `legacy_evidence_snapshot` + `story_backlog_link` → the closed-loop
learning system (only worth doing once you run many traces and want to *prove*
improvements work).

### 4.5 CLI: the minimal command surface
Group by concern: `init/migrate` · `intake` · `story add/update/verify/
complete` · `decision add` · `backlog add/close` · `trace`/`score-trace` ·
`query matrix/stories/traces/...`. Read-only is separate from mutate.

### 4.6 Process contract (if there is an external orchestrator)
If you want an external agent/tool to drive the CLI: apply the **discovery-before-
mutation** framing — the first command `query contract` returns `protocol_version`, the
schema range, `database_state`, `capabilities`; the consumer *verifies rather than
inferring from semver*. Each command prints **exactly 1 JSON**; branch on **exit code +
`error.code`**, not on the message. A mutation timeout = *undefined result* → re-query
state, don't assume rollback. This is the foundational idea; the specific format may differ.

---

## Part 5 — Execution checklist for a BRAND-NEW agent (follow in order)

### Stage A — Build H1 (one session, pure markdown)
```
[ ] A1. Create the directory tree:  docs/  docs/templates/  docs/stories/  docs/decisions/
[ ] A2. Write docs/GLOSSARY.md            (core vocabulary)
[ ] A3. Write AGENTS.md                    (entrypoint + ## Harness authority gate)
[ ] A4. Write docs/HARNESS.md              (lifecycle + read-only vs change loop + Done)
[ ] A5. Write docs/FEATURE_INTAKE.md       (input types + risk checklist + lane rule)
[ ] A6. Write docs/ARCHITECTURE.md         (Discovery-Before-Shape + Dependency Rule)
[ ] A7. Write docs/TEST_MATRIX.md          (status enum + proof layers + "no proof=not done")
[ ] A8. Write the 3 templates: story/decision/validation-report
[ ] A9. Write docs/HARNESS_BACKLOG.md      (friction reservoir)
[ ] A10. (CC) Add @AGENTS.md to CLAUDE.md
[ ] A11. SELF-INSPECT with the 11-responsibility checklist (Components):
         have you covered task-spec / context / memory / verification?
```

### Stage B — Operate for real & collect friction (a few days–weeks)
```
[ ] B1. Run 3–5 real pieces of work through the proper intake→story→proof process.
[ ] B2. Every time it hurts/repeats/is ambiguous → record 1 line in HARNESS_BACKLOG.md.
[ ] B3. End-of-week review: does the markdown hurt yet? (hard to query / error-prone / lost trail)
        → NOT yet hurting: stay at H1.  ALREADY hurting: go to C.
```

### Stage C — Climb to H2 (only when B3 says "already hurting")
```
[ ] C1. Write CONTEXT_RULES.md + TRACE_SPEC.md
[ ] C2. Write HARNESS_COMPONENTS.md + HARNESS_MATURITY.md
[ ] C3. Decide the CLI engine/language + record 1 decision record (why)
[ ] C4. Write schema 001 (5 core tables) in the order of Part 4.3
[ ] C5. Build a thin CLI: init/migrate/intake/story/trace/query
[ ] C6. Move the TEST_MATRIX markdown table → query matrix; docs keep only vocab
[ ] C7. Record the "SQLite/Durable layer" + "prebuilt binary" decisions if applicable
```

### Stage D — Climb H3→H5 (when you have enough traces to measure)
```
[ ] D1. score-trace/score-context; group friction by component            (H3)
[ ] D2. TOOL_REGISTRY.md; story verify_command; verify gate at trace time  (H4)
[ ] D3. HARNESS_AUDIT.md (entropy) + IMPROVEMENT_PROTOCOL.md (propose)      (H5)
```

---

## Part 6 — Pitfalls & anti-patterns (learned from the reference design)

| Anti-pattern | Why it's wrong | Do this instead |
|--------------|-----------|----------|
| Building the database on day 1 | H2 is meaningless before real work exposes the need | H1 markdown first, DB when it hurts |
| Stuffing live state into markdown | Hand tables are error-prone, not queryable, lose observability | State → durable layer; markdown keeps *rules* |
| Treating trace text = decision record | A trace is *evidence*, not *proof* of a durable record | High-risk: REQUIRE both the `decisions/NNNN.md` file + a durable row |
| `story update --status implemented` | Skips fresh proof | Only `story complete` (runs proof + atomic) reaches implemented |
| Writing IMPROVEMENT_PROTOCOL/AUDIT early | Machine self-fixing with no data = empty | Wait until enough traces/records accumulate |
| Reading every doc each session | Breaks bounded-context, wastes tokens | Read by phase×lane, with a budget |
| Auto-applying proposals | The harness rewrites policy uncontrolled = scope creep | `propose` is advisory only, human approves with 1 key |
| Inferring compatibility from semver | A high version ≠ having the capability you need | `query contract`: verify protocol+schema+capabilities |
| Bootstrapping/mutating when only asked to answer | Violates the authority gate | Read-only → only read, absolutely do not touch the DB |

---

## Part 7 — The DECISIONS to record when building (decision records)

When building your own harness, the following choices should have a `docs/decisions/NNNN-*.md`:

1. **Harness-first or code-first?** (reference: decision 0001 chose
   harness-first — build the operating model before code).
2. **Is the spec a seed or a living plan?** (0002/0003: treat the spec as *historical
   input*, after which everything re-enters through intake; keep the harness stack-neutral,
   reusable).
3. **Durable layer: which engine?** (0004 chose SQLite because you need queryable +
   observability as the precondition for self-improvement; rejected all-markdown, JSON
   files, a DB server for v0).
4. **How to distribute the CLI?** (0005 chose a prebuilt binary + checksum so the consumer
   doesn't have to install a toolchain; the binary IS the distribution contract).
5. **The durable-record vs trace-evidence boundary** (0006: a decision must be a durable
   row + a markdown file; a trace does not count).
6. **The self-improvement rule** (0007: `propose` is advisory, rule-based, evidence-backed,
   human-approved; no auto-apply, no free-running LLM).

**What is FOUNDATIONAL (must copy the idea)** vs **what is DETAIL (replaceable)**:

- *Foundational:* separate policy↔durable · structured trace + friction · authority
  gate · proof-driven · durable-record≠evidence · self-improve with a human gatekeeper ·
  discovery-before-mutation · CAS + server-side derived field.
- *Replaceable:* SQLite (could be Postgres/KV/event-log) · Rust prebuilt (could be
  Python/Go/container) · the specific timeout/cap numbers · the changeset JSONL format · the
  command syntax/names · the specific layered architecture.

---

## Appendix — Target directory tree (full H2, for reference)

```
<repo>/
  AGENTS.md                         # entrypoint + authority gate (small shim, stable)
  CLAUDE.md                         # (if CC) import @AGENTS.md
  harness.db                        # durable state (gitignored)  ← only from H2
  docs/
    README.md                       # docs map
    GLOSSARY.md                     # core vocabulary
    HARNESS.md                      # collaboration model + request-class loops
    FEATURE_INTAKE.md               # risk classification → lane
    ARCHITECTURE.md                 # PRODUCT boundary rules
    TEST_MATRIX.md                  # evidence vocab (live state in DB from H2)
    CONTEXT_RULES.md                # read right/enough/stop          (H2)
    TRACE_SPEC.md                   # trace standard             (H2)
    HARNESS_COMPONENTS.md           # 11 responsibilities            (H2)
    HARNESS_MATURITY.md             # the H0–H5 ladder               (H2)
    TOOL_REGISTRY.md                # manifest + degrade ladder (H4)
    HARNESS_AUDIT.md                # entropy score             (H5)
    IMPROVEMENT_PROTOCOL.md         # propose → outcome loop    (H5)
    HARNESS_BACKLOG.md              # friction reservoir (template)
    templates/
      story.md  decision.md  validation-report.md
      spec-intake.md                # (when onboarding a large spec)
      high-risk-story/{overview,design,execplan,validation}.md   # (high-risk lane)
    stories/                        # real work packets
    decisions/                      # ADR: NNNN-*.md
  scripts/
    schema/001-init.sql …           # migrations                 (H2)
    bin/<cli>                        # durable-layer CLI          (H2)
    bootstrap-*.{sh,ps1}            # build local runtime          (H2)
```

---

_Research sources: the reference harness framework — `docs/HARNESS.md`,
`FEATURE_INTAKE.md`, `CONTEXT_RULES.md`, `TRACE_SPEC.md`, `GLOSSARY.md`,
`ARCHITECTURE.md`, `HARNESS_COMPONENTS.md`, `HARNESS_MATURITY.md`,
`HARNESS_AUDIT.md`, `IMPROVEMENT_PROTOCOL.md`, `TOOL_REGISTRY.md`,
`TEST_MATRIX.md`, `contracts/harness-orchestration-v1.md`, `scripts/schema/*.sql`
(001–013), `docs/templates/*`, `docs/decisions/0001–0007`. Day-to-day operation:
`docs/HARNESS_RUNBOOK.md`._
