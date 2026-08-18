# GLOSSARY — Harness vocabulary (news-scape)

One word = one meaning across the whole harness. Every other harness doc borrows terms from here.
Keep short; grow only when a new concept actually appears.

## Harness core terms

| Term | Meaning |
|------|---------|
| **Agent** | The human+AI worker executing a request under the harness (this repo's operating model). |
| **Harness** | The repo-level operating model that turns intent → safe, proof-backed change. NOT product code. "App is what users touch; the harness is what agents touch." |
| **Policy** | Markdown docs describing *how to work* (this dir). Stable, human-readable. |
| **Durable** | *(H2+, not built yet)* a database recording *what happened* (intake/story/trace). At H1 this is hand-written markdown. |
| **OKF** | Operational Knowledge Files — the existing product knowledge base to read for context: `project/docs/skills/*`, `project/docs/{design,dev,domains}/`, and repo `okf/`. See [AGENTS.md](../AGENTS.md). |
| **Request class** | The authority gate: **read-only** (answer/explain/diagnose/plan — no repo change) vs **change** (build/fix/apply — may mutate). Decided by desired outcome, not keywords. |
| **Feature Intake** | The step that classifies a change request into a **Risk Lane** before any work. See [FEATURE_INTAKE.md](FEATURE_INTAKE.md). |
| **Risk Lane** | `tiny` / `normal` / `high-risk` — the effort+scrutiny tier for a change. Set by counting risk flags. |
| **Hard gate** | A risk flag that forces `high-risk` + a human decision (e.g. DB migration, secrets). |
| **Story Packet** | A unit of work (`US-XXX`) with contract, acceptance, proof. Template: [templates/story.md](templates/story.md); instances in [stories/](stories/). |
| **Parent / Epic** | Free-text grouping of a story into a product Phase (e.g. "Phase 3 — Gold / agent-extract"). No epic folders at H1 — reuse `project/docs/charter.md` phases. |
| **Proof / Evidence** | A mechanical result (test/verify command output) that backs a claim. "No proof = not implemented." Tiers: Unit/Integration/E2E/Platform. See [TEST_MATRIX.md](TEST_MATRIX.md). |
| **Trace** | The evidence left behind after a session: what was done, files read/changed, outcome, friction. At H1 = inline notes in the story + [SESSION-LATEST.md](SESSION-LATEST.md). |
| **Handoff** | Step 9 of the change loop: overwrite [SESSION-LATEST.md](SESSION-LATEST.md) so the next session knows "where am I, what next". |
| **Friction** | A specific pain / missing capability hit while working. Recorded in [HARNESS_BACKLOG.md](HARNESS_BACKLOG.md). The harness grows from friction. |
| **WIP=1** | Work-In-Progress limit: at most **one** story `in_progress` at a time. An interrupt parks the current story (`blocked`/`deferred`) before starting another. |
| **Decision record (ADR)** | A durable record of an architectural/behavioral choice. Template: [templates/decision.md](templates/decision.md); instances in [decisions/](decisions/). |
| **Maturity (H0–H5)** | Harness evolution: H1 = pure markdown (here now) → H2 = SQLite+CLI → … → H5 = self-improve. See `harness/HARNESS_BUILD_FROM_SCRATCH.md`. |

## News-scape product terms (context for intake/architecture)

| Term | Meaning |
|------|---------|
| **Bronze** | Raw captured HTML, WORM (write-once, byte-exact). `content_sha256` = immutable proof. |
| **Silver** | Clean, re-derivable base derived purely from Bronze (`project/data/silver/*`). Reparse ≠ re-scrape. |
| **Gold** | Agent output layer — **deferred** by design. The active frontier is the agent-handoff contract (Vòng 3). |
| **Dedup** | 2-tier duplicate detection: SHA-256(url+title) + fuzzy. Table `seen_articles`. |
| **Source domain** | One news source (cafef.vn, vietstock.vn, …), config-driven via `project/config/domains/*.yaml`. |
| **Sentiment lexicon** | Rule-based VN sentiment word list under `project/data`; EN articles = neutral by design. |
| **Handoff contract** | The producer↔agent JSON boundary (`project/docs/design/08`, `09`). |
