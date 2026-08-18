# Harness Runbook (EN) — How to Execute the Process Yourself

A self-execution document for the Sen13 **Harness** process. This is the English
distillation of `docs/HARNESS.md`, `docs/FEATURE_INTAKE.md`,
`docs/CONTEXT_RULES.md`, `docs/TRACE_SPEC.md`, and `scripts/README.md`. When there
is a conflict, those original files are the source of truth; this runbook is only
a fast path.

> **App is what users touch. The harness is what agents touch.**
> The harness is NOT trading code (DP/OG/OF). It is the operational layer wrapped
> around it that turns requests into **safe + evidence-backed (proof)** work.

---

## 0. Rule number one — Classify the request BEFORE any operation

Everything starts at a single gate: the **request class**. It decides *whether you
are allowed to change the repo/DB*. The decision is based on the **desired outcome**,
not on a keyword.

```
Incoming request
  └─ Only needs: answer / explain / review / diagnose / plan / status ?
       ├─ YES  → READ-ONLY
       │         Read AGENTS.md + exactly the files needed → answer → STOP.
       │         NO bootstrap, NO init/migrate DB,
       │         NO writing intake / story / trace / backlog.
       │
       └─ NO   → CHANGE (change / build / fix / "review and apply fixes")
                 Run the 8-step mutation loop in Section 2.
```

Boundary examples:
- "Why is this test failing?" → read-only. Even if you discover a missing migration →
  you **still must not** create the migration (it is only a diagnosis).
- "Fix that migration" → change. Bootstrap + intake before fixing.
- "Review and apply the fix for me" → change (because the user asked to modify the repo).

---

## 1. Harness architecture (2 layers)

| Layer | Storage | Role |
|------|---------|---------|
| **Policy** | `docs/*.md` | Describes *how to work*. Stable, human-readable. |
| **Durable** | `harness.db` (SQLite, gitignored) via `scripts/bin/harness-cli.exe` | Records *what happened*: intake, story, decision, trace, backlog. |
| **Templates** | `docs/templates/*` | Story / decision / validation-report scaffolds. |
| **Schema** | `scripts/schema/NNN-*.sql` | DB structure, version-controlled. |

Policy = "how"; Durable = "what happened". `harness.db` is local to each machine.

---

## 2. CHANGE loop — 8 steps

```
1. Bootstrap    .\scripts\bootstrap-harness.ps1
2. Intake       Classify per docs/FEATURE_INTAKE.md (Section 3)
                → harness-cli intake ...
3. Proof status harness-cli query matrix --active --summary
                (+ --story <id> if a story is already chosen)
4. Context      Read only the files for the lane per docs/CONTEXT_RULES.md (Section 4)
5. Implement    Smallest slice + validate within the lane
6. Self-check   Product truth / validation / architecture / next-agent changed?
7. Trace        harness-cli trace ... per docs/TRACE_SPEC.md → view score
8. Friction     Fix in place OR harness-cli backlog add
```

A change request is done when:
- The change is complete **or** the blocker is clearly recorded.
- Related docs / stories / test matrix are still correct.
- The validation command has been run (if one exists).
- A **trace** has been recorded.
- A missing harness capability → a **backlog** entry was recorded (if relevant).
- The final answer clearly states *what changed* and *what was not done*.

---

## 3. Intake — pick a LANE

Humans do **not** need to rank the risk themselves. The harness does it.

### 3.1 Input type (where the work "lands")

| Type | Use when | Artifact |
|------|----------|----------|
| New spec | Turn a project spec into harness docs | Product docs, epics, decisions |
| Spec slice | Implement one chosen behavior from a spec | Story packet |
| Change request | Change/fix/tune an existing behavior | Story packet or direct patch |
| New initiative | Large product area, many stories | Initiative notes + stories |
| Maintenance | Dependency / architecture / performance / security / operations | Story, validation report, or decision |
| Harness improvement | Improve how humans + agents collaborate | Update docs or `backlog add` |

### 3.2 Risk checklist — mark EVERY applicable flag

| Flag | Applies when it touches |
|------|----------------------|
| Auth | login, logout, session, JWT, password, refresh token |
| Authorization | roles, permissions, tenant/company scope |
| Data model | schema, migration, uniqueness, deletion, retention |
| Audit/security | audit log, privacy, sensitive data, access log |
| External systems | email, payment, cloud, provider SDK, queue, webhook |
| Public contracts | API shape, response envelope, client-visible behavior |
| Cross-platform | desktop/mobile/browser, native shell, deep link |
| Existing behavior | already-implemented / already-tested behavior being changed |
| Weak proof | tests around the affected area are vague or missing |
| Multi-domain | more than one product domain changing at once |

### 3.3 Lane selection rule

```
0–1 flag          → tiny or normal (depending on code impact)
2–3 flags         → normal (stronger validation)
4+ flags          → high-risk
Any HARD GATE     → high-risk (unless the human narrows the scope)
```

**Hard gates:** Auth · Authorization · Data loss/migration · Audit/security ·
External provider behavior · Weakening/removing validation.

### 3.4 Per-lane requirements

| Lane | What you must do |
|------|----------|
| **Tiny** | Record intake row → patch directly → keep docs current → run a quick check. Skip the story packet (but do NOT skip intake). |
| **Normal** | Create/update 1 story from `templates/story.md` → link product docs → validation expectations → record proof via `story add`/`story update`. |
| **High-risk** | Use `templates/high-risk-story/` (`execplan.md`, `overview.md`, `design.md`, `validation.md`) → ask the human if the direction is unclear → record a **decision record** (`docs/decisions/NNNN-*.md` from `templates/decision.md` + `decision add`). Trace text does NOT replace a decision record. |

### 3.5 Intake output — you must be able to state this

```
Lane: normal
Reason: touches authorization + API contract + audit
Docs: permissions, account-settings, audit-log
Story: docs/stories/epics/E02-.../US-014-...md
Validation: unit, integration, E2E
```

---

## 4. Context Rules — read the right amount, know when to stop

The goal is NOT to cram in maximum context, but to bring the right information for
the current **phase + lane**.

Phases: **Intake → Planning → Implementation → Validation → Trace**. Each cell in
`docs/CONTEXT_RULES.md` is Must / Should / Skip per lane.

**Token budget:**

| Lane | Harness context budget | Reading shape |
|------|---------------------------|----------------|
| Tiny | ~2K | AGENTS.md + FEATURE_INTAKE + matrix summary + exactly the file being changed |
| Normal | ~5K | Intake docs + related product/story + architecture (if structural) + validation + trace spec at the end |
| High-risk | ~10K | Full intake + architecture + decisions + high-risk template + product/validation + trace spec + component/maturity |

**Budget rules:**
- Prefer targeted `rg` over reading whole files.
- Read the smallest section that answers the phase's question.
- Raise context when you hit a *retrieval trigger*.
- Once the lane + file + validation path are clear → **stop** reading irrelevant history.

**Retrieval triggers (auto-raise context), for example:**
- Touching schema/DB/migration → read `decisions/0004-sqlite-durable-layer.md` +
  `scripts/schema/`.
- Touching CLI/installer → read `decisions/0005-prebuilt-rust-harness-cli.md` +
  `scripts/README.md`.
- Touching auth / authorization / audit / data-loss / external provider → **treat as
  high-risk**, read `templates/high-risk-story/*` + decisions before working.
- Changing public API / user-visible behavior → read `docs/product/*` + story +
  validation before fixing.
- Changing Harness policy / hierarchy / risk rule / validation → read HARNESS +
  FEATURE_INTAKE + ARCHITECTURE + decisions; **stop if the direction is unclear**.

---

## 5. Trace — the evidence left behind

3 tiers, `harness-cli trace` scores automatically:

| Lane | Tier | Minimum content |
|------|------|--------------------|
| Tiny | **Minimal** (1) | `task_summary` (≥10 chars) + `outcome` |
| Normal | **Standard** (2) | + `intake_id`, `story_id`, `agent`, `actions_taken`, `files_read`, `files_changed`, and ≥1 of `errors`/`harness_friction` |
| High-risk | **Detailed** (3) | + `decisions_made`, `errors` (use `none` if there are none), `harness_friction` (only `none` after you have actually checked), `duration`, `token_estimate`, `notes` |

`outcome` ∈ `completed` | `blocked` | `partial` | `failed`.

**How to write good friction:** state the *specific pain* + the missing capability,
not a vague feeling.
- ✅ "New docs are not in the installer copy list; recorded an out-of-scope backlog entry."
- ❌ "docs confusing".

---

## 6. Story lifecycle & verification

- Proof flags are **numbers** `1`/`0` (do NOT use `yes`/`no`).
- `story verify <id>` runs the configured `verify_command` (does not accept proof flags).
- `story complete <id>` = the **only path** to `implemented` (runs fresh proof +
  atomic). `story update --status implemented` is **rejected**.
- `story verify-all` before any merge / maturity claim / benchmark.
- To copy proof values: use `query matrix --numeric` to get the 1/0 form.

---

## 7. Growth rule — the harness grows from friction

When an agent is confused / repeats manual steps / lacks a rule / sees a recurring
failure: **fix the harness now** or record a backlog entry. Backlog `--risk` uses a
**lane** (`tiny`/`normal`/`high-risk`), NOT `low`.

```powershell
.\scripts\bin\harness-cli.exe backlog add --title "<name>" --pain "<what was hard>" --risk tiny --predicted "<measurable impact>"
# When closing:
.\scripts\bin\harness-cli.exe backlog close --id <n> --outcome "<actual measured result>"
```

---

## 8. Decision records (high-risk)

When changing behavior / architecture / authorization / data ownership / API shape /
validation → record it in **both places**:

1. Markdown file `docs/decisions/NNNN-*.md` (from `templates/decision.md`).
2. Durable row:

```powershell
.\scripts\bin\harness-cli.exe decision add --id 0008-auth-boundary --title "Auth Boundary" --doc docs/decisions/0008-auth-boundary.md --notes "Accepted during T4 auth work."
```

Trace `--decisions` is *evidence*, it does NOT replace the decision log.

---

## 9. What an agent may / must ask about

**May do directly:** story status (except completion) + evidence, test matrix
rows, linking story→product docs, validation notes, small clarifications, intake/trace/backlog.

**Must ask the human before:** changing architectural direction · removing a validation
requirement · changing the source-of-truth hierarchy · changing the risk classification
rules · changing the feature workflow.

---

## 10. Windows commands — copy-paste

```powershell
# 0. ONLY when this is a CHANGE request
.\scripts\bootstrap-harness.ps1
.\scripts\bin\harness-cli.exe --version

# 1. Intake
.\scripts\bin\harness-cli.exe intake --type <type> --summary "<text>" --lane <tiny|normal|high-risk>

# 2. Proof status
.\scripts\bin\harness-cli.exe query matrix --active --summary
.\scripts\bin\harness-cli.exe query matrix --story <id>
.\scripts\bin\harness-cli.exe query matrix --numeric        # get proof in 1/0 form

# 3. Story (normal+)
.\scripts\bin\harness-cli.exe story add --id US-0xx --title "<text>" --lane normal --verify "<cmd>"
.\scripts\bin\harness-cli.exe story update --id US-0xx --unit 1 --integration 1 --e2e 0 --platform 0
.\scripts\bin\harness-cli.exe story verify US-0xx
.\scripts\bin\harness-cli.exe story complete US-0xx
.\scripts\bin\harness-cli.exe story verify-all              # before merging

# 4. Decision (high-risk)
.\scripts\bin\harness-cli.exe decision add --id NNNN-slug --title "<text>" --doc docs/decisions/NNNN-slug.md --notes "<...>"

# 5. Trace (final)
.\scripts\bin\harness-cli.exe trace --summary "<text>" --outcome completed `
  --intake <id> --story US-0xx --agent claude `
  --actions "a,b,c" --read "f1,f2" --changed "f3,f4" --friction "none"
.\scripts\bin\harness-cli.exe score-trace --id <n>          # re-score an old trace

# 6. Friction / backlog
.\scripts\bin\harness-cli.exe backlog add --title "<name>" --pain "<pain>" --risk tiny
.\scripts\bin\harness-cli.exe query backlog --open
.\scripts\bin\harness-cli.exe query friction

# Further reading
.\scripts\bin\harness-cli.exe help
.\scripts\bin\harness-cli.exe query help
```

Bootstrap note: `bootstrap-harness.ps1` **refuses** to create an empty DB if this is a
source checkout missing the core DB (you must restore a verified core epoch); in a
consumer install it safely self-`init`s. It **pins the CLI version** to
`scripts/harness-cli-release-tag` — a version mismatch = bootstrap failure. It also
auto-`migrate`s an old DB and refuses a schema outside the supported range.

---

## 11. Read-only inspection (no bootstrap needed)

Allowed to run to answer a question **without** changing state (for read-only requests):

```powershell
.\scripts\bin\harness-cli.exe query matrix --active --summary
.\scripts\bin\harness-cli.exe query stories --json
.\scripts\bin\harness-cli.exe query backlog
.\scripts\bin\harness-cli.exe query traces
.\scripts\bin\harness-cli.exe query stats
.\scripts\bin\harness-cli.exe query sql "<a single read-only SELECT>"
```

`query sql` accepts only 1 read-only statement; the CLI enforces read-only at the
connection layer.

---

## 12. Definition of "Done"

**Read-only done:** the answer has repo evidence, clearly separates fact vs inference,
and the repo + harness state are **unchanged**.

**Change done:** all the conditions in Section 2 are met (change/blocker, docs/story/matrix
current, validation run if applicable, **trace recorded**, friction filed to backlog if
needed, final answer clearly states what changed / what was not done).

---

## Appendix — Applied example (Sen13 scenario)

**Request:** "Fix OF to filter keyspace events by configured timeframe."

```
1. Class     → CHANGE (fix).
2. Bootstrap → .\scripts\bootstrap-harness.ps1
3. Intake    → type=Change request.
   Risk flags: Existing behavior (OF is running), Weak proof (no OF tests).
   → 2 flags, no hard gate → LANE = normal.
   intake --type change-request --summary "OF filter keyspace by TF" --lane normal
4. Matrix    → query matrix --active --summary  (find the related story)
5. Story     → story add --id US-0xx ... --verify "python -m compileall -q core"
6. Context   → read core/channel_listener.py + adjacent; skip irrelevant history.
7. Implement → change the smallest slice, run compileall.
8. Trace     → Standard tier: actions/read/changed/friction.
9. Friction  → if OF tests are missing: backlog add --pain "OF lacks tests around the listener".
```

---

_Source of truth when this runbook is out of date: `docs/HARNESS.md`, `docs/FEATURE_INTAKE.md`,
`docs/CONTEXT_RULES.md`, `docs/TRACE_SPEC.md`, `scripts/README.md`._
