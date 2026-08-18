# Harness H1 for News-Scape: Research Report
**Date:** 2026-08-17 | **Status:** Deep read complete

---

## A. What H1 Requires (~10 markdown files)

Per HARNESS_BUILD_FROM_SCRATCH_VI.md, H1 is **pure markdown, no database**:

| File | Purpose | Mandatory? |
|------|---------|-----------|
| `GLOSSARY.md` | Vocab (Agent, Harness, Story, Trace, Risk Lane) | ✓ Write first |
| `AGENTS.md` | Entrypoint + request-class gate (read-only vs change) | ✓ Entry shim |
| `HARNESS.md` | Lifecycle: intent → intake → story → product delta → proof → harness delta | ✓ Constitution |
| `FEATURE_INTAKE.md` | Input types (new spec, spec slice, change, new initiative, maintenance, harness improvement); risk checklist; lane rules (0-1 flag→tiny/normal; 2-3→normal; 4+→high-risk; hard gate→high-risk) | ✓ Risk gate |
| `ARCHITECTURE.md` | Discovery-before-shape; dependency rules; product boundaries (NOT harness) | ✓ Product law |
| `TEST_MATRIX.md` | Status enum (planned/in_progress/implemented/changed/retired); proof tiers (Unit/Integration/E2E/Platform); "no proof=not done" | ✓ Evidence vocab |
| `templates/story.md` | Story packet khuôn: Title (US-XXX), Status, Lane, Contract, Acceptance, Design, Validation (unit/int/e2e/platform), Harness Delta, Evidence | ✓ Core template |
| `templates/decision.md` | ADR: Context, Decision, Alternatives, Consequences, Follow-Up; status enum (Proposed/Accepted/Superseded/Rejected) | ✓ Core template |
| `templates/validation-report.md` | Scope, Commands Run, Results table, Evidence, Gaps | ✓ Core template |
| `HARNESS_BACKLOG.md` | Friction bồn: Title, Discovered While, Current Pain, Suggested Improvement, Risk (lane), Status | ✓ Friction capture |

**H1→H5 ladder:** H1 (markdown only) → H2 (SQLite durable + CONTEXT_RULES, TRACE_SPEC) → H3 (scoring, friction by component) → H4 (tool registry, verify gates) → H5 (self-improve: audit entropy + propose).

---

## B. What Harness ALREADY Covers (v2 claims)

### (a) **"New initiative" input type** — FOUND ✓
Line 90 in charter.md: `New initiative | Vùng sản phẩm lớn, nhiều story | Initiative notes + stories`.
**RUNBOOK confirms** (line 90, RUNBOOK_VI): `New initiative` is explicitly listed input type.

### (b) **story_dependency / story_hierarchy tables** — FOUND (at H2+) ✓
HARNESS_BUILD_FROM_SCRATCH_VI.md line 297–298:
> `story_dependency`, `story_hierarchy` — SAU `story` (self-join many-to-many).

Confirmed in section 4.4: schema tables **8. `story_dependency`, `story_hierarchy` — SAU `story`**.
These are **H2+ durable layer**, not H1 markdown. Not yet implemented in news-scape (H1 only).

### (c) **Trace outcome states + friction/next-action** — FOUND ✓
HARNESS_RUNBOOK_VI.md line 187:
> `outcome` ∈ `completed` | `blocked` | `partial` | `failed`.

Friction guidance (lines 189–192):
> Friction viết sao cho tốt: nêu *cái đau cụ thể* + năng lực còn thiếu.
> ✅ "New docs chưa nằm trong installer copy list; ghi backlog out-of-scope."

**Trace tier 3 (Detailed, for high-risk)** includes `decisions_made`, `errors`, `harness_friction`, `duration`, `token_estimate`, `notes` (line 185).
**outcome=blocked + friction → next-action implicit** (ghi backlog or harness backlog entry).

---

## D. Reusable Project Assets as OKF (Existing Knowledge Base)

### Inventory: `project/docs/skills/*` (Domain knowledge)
- `cafef.md` — CafeF scraper rules, selectors, data model
- `fireant.md` — FireAnt API docs, integration patterns
- `rss-sources.md` — RSS feed URLs, validation, health checks
- `tnck.md` — TNCK data source mappings

### Inventory: `project/docs/` subfolders
| Folder | Content | Status |
|--------|---------|--------|
| `design/` | 00-end-to-end (bronze→silver→agent), 01-system-overview, 02-execution-flow, 03-source-strategy, 04-sentiment, 05-notification, 06-raw-html-capture, 07-storage, 08-handoff-contract, 09-agent-io, 10-governance, 11-e2e-standardization, 12-agent-infra, 12-bronze-to-silver | Phase 1 MVP + roadmap to Phase 3 |
| `dev/` | 01-codebase-guide, 02-data-model-db, 03-adding-source, 04-testing, 05-known-issues, 06-raw-html-capture | Implementation how-tos |
| `domains/` | api-scrapers, exchange-layer0, intl-rss, vn-rss | Source taxonomy |
| `operations/` | troubleshooting, deployment | Runbook-like ops guides |
| `reference/` | README, rss-reference | Static reference data |
| `others/` | 260726-project-approach, decisions, phase1-report, system-prompt | Approach docs, ADRs |

**Argument:** These ARE the existing knowledge base (OKF). No separate `knowledge/` folder needed; fold into future H2 `CONTEXT_RULES.md` retrieval triggers and `HARNESS_COMPONENTS.md` per-domain sections.

---

## E. Project Doc Conventions (charter + ARCHITECTURE framing)

### charter.md structure:
- **Sections 3.1–3.2:** Goals (P0 core, P1+ mở rộng). G-1 to G-4 = MVP scope.
- **Section 4.2:** Data flow 3 phases: Phase 1 MVP (RSS→Dedup→Extract→Classify→SQLite→Telegram), Phase 2 (+ ClickHouse sync, LLM), Phase 3 (HTML scraper, API reverse, daily digest).
- **Section 5:** Constraints (C-01 to C-09 tech, O-01 to O-05 ops, D-01 to D-06 dev, T-01 to T-03 time).
- **Section 6:** WBS (Phase 1 MVP checklist, Phase 2, Phase 3).

### ARCHITECTURE.md framing:
- TDR-001 to TDR-006 (RSS primary, trafilatura, dedup 2-tier, SQLite WAL single-writer, standalone, sync not async).
- No explicit Epic/parent-child concept, but **Phase concept exists** (Phase 1/2/3 aligned to charter goals G1–G4 core, G5–G13 future).
- Informal hierarchy: goal → phase → story (implied).

### Project plan naming (`project/plans/`):
- Dated plan directory: `plans/20260817-1536-harness-h1-newsscape/` (YYYYMMDD-HHMM-initiative).
- Likely subdirs: `research/`, `decisions/`, `stories/` (per H1 template).

---

## F. Mapping: v2 Concept → Existing Mechanism

| v2 Concept | Existing Harness/Project Mechanism | Status |
|-----------|----------------------------------|--------|
| Epic / Phase hierarchy | charter.md Phase 1/2/3 + ARCHITECTURE.md phases. Implicit parent-child (Phase 1 goals→stories). | Informal but present; H2 `story_hierarchy` formalizes. |
| Initiative (large work package) | Input type "New initiative" (FEATURE_INTAKE.md line 90); yields initiative notes + stories. | Covered ✓ |
| Risk lane classification | FEATURE_INTAKE.md risk checklist + lane rules (0-1→tiny/normal, 2-3→normal, 4+→high-risk). | Covered ✓ |
| Story with proof tiers | TEST_MATRIX.md enum (planned/in_progress/implemented/changed/retired) + Unit/Integration/E2E/Platform tiers. | Covered ✓ |
| Trace with outcome + friction | TRACE_SPEC.md 3 tiers. Outcome ∈ {completed, blocked, partial, failed}. Friction + next-action → backlog/decision. | Covered ✓ |
| Dependency graph (story→story) | H2 table `story_dependency`, `story_hierarchy` (not yet implemented in H1). | H2+ feature |
| Change detection / delta tracking | charter.md section 4 data flow; ARCHITECTURE.md TDR-004 (SQLite WAL single-writer). Explicit in design/07-storage-layers. | Covered ✓ (DB layer) |
| Handoff contract (to agent) | design/08-handoff-contract-catalog.md + 09-agent-io-contract.md. Explicit input/output envelope. | Covered ✓ (domain-specific) |
| Self-improve / proposal loop | H5 concept (HARNESS_BUILD_FROM_SCRATCH_VI.md line 98–99). Not yet in v0. Tracked as friction→backlog first. | Roadmap (H5 future) |

---

## Unresolved Questions

1. **Which harness files already exist in news-scape repo?** (GLOSSARY, AGENTS, HARNESS, etc. — assumed missing, need audit.)
2. **Does charter.md map directly to FEATURE_INTAKE.md risk checklist?** (Constraints C-01/C-06 suggest hard gates, but explicit risk-flag mappings unclear.)
3. **Are `project/plans/` directories expected to have harness trace/story/decision files, or only ad-hoc analysis?** (Unclear if planned stories → docs/stories/ or plans/ subdir.)
4. **When moving from Phase 1 (standalone MVP) to Phase 2 (ClickHouse sync, LLM), does that trigger H1→H2 migration or new H1 per phase?** (Clarify phase=feature, not H-level.)
5. **Friction backlog items (O-03, O-04, D-02 implied) — should these populate HARNESS_BACKLOG.md or kept separate in project/docs/others/?**
