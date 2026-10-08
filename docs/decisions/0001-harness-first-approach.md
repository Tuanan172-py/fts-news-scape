---
id: ADR-0001
type: adr
title: Harness-first approach for agentic collaboration
status: accepted
lane: high-risk
created: 2026-08-24
updated: 2026-10-06
lang: en
authors: [operator, agy]
approvers: ["operator (date unrecorded)"]
story: []
evidence:
  - commit:bb13847
  - commit:3a0c527
  - path:plans/20260817-1536-harness-h1-newsscape/plan.md
  - path:other/harness/HARNESS_BUILD_FROM_SCRATCH.md
  - path:docs/HARNESS.md
  - path:docs/FEATURE_INTAKE.md
  - path:docs/HARNESS_MATURITY.md
  - path:docs/HARNESS_BACKLOG.md
original: "commit:3a0c527"
reconstructed: 2026-10-06
summary: Build the operating harness (intake gate, bounded context, mechanical proof, durable records) around the product before extending product features; every request passes risk classification first.
summary_vi: Xây khung vận hành (harness) quanh sản phẩm trước khi mở rộng tính năng; mọi yêu cầu đi qua cổng phân loại rủi ro, giới hạn ngữ cảnh, kiểm thử cơ học và ghi bằng chứng bền vững.
---

# ADR-0001 — Harness-first approach for agentic collaboration

## Context

- `news-scape` scrapes and processes financial news with several subagents and automated tasks.
- Letting agents change source code directly, without a control boundary (harness), leads to code drift, loss of observability, missing proof tests and lost context between sessions.
- The harness was first instantiated at maturity H1 on 2026-08-18: pure Markdown policy files, templates and a hand-maintained proof table, with no database and no CLI (reconstructed from commit bb13847 and `plans/20260817-1536-harness-h1-newsscape/plan.md`).
- The H1 plan recorded three friction items: status not queryable across stories, WIP=1 without enforcement, and `SESSION-LATEST.md` as hand-edited live state (reconstructed from `docs/HARNESS_BACKLOG.md` at commit bb13847).
- The reference guide `other/harness/HARNESS_BUILD_FROM_SCRATCH.md` lists "harness-first or code-first" as the first design question and cites its own reference decision for harness-first (reconstructed from the guide at commit bb13847).

The H1 dogfood run blocked story US-001 at the hard gate for a public data contract, which showed the gate working as intended (reconstructed from `docs/SESSION-LATEST.md` at commit bb13847). This ADR, written on 2026-08-24 together with the H2 durable layer, records the approach the project had already adopted.

## Decision

- D1. The project MUST apply the Harness-First approach: build the operating framework and working discipline (the harness) around the product before extending product features.
- D2. Every request MUST pass a risk classification gate (Intake Gate).
- D3. Every request MUST respect a bounded reading scope (Bounded Context).
- D4. Every change MUST be backed by mechanical proof (Proof-Driven).
- D5. Evidence MUST be recorded durably (Durable Layer); the storage choice is ADR-0002.

## Alternatives

| Option | Why rejected |
|---|---|
| Status quo: agents edit product code directly with no harness | Produces code drift, lost observability, missing proof and lost context between sessions, as stated in the original Context. |
| Code-first: grow product features, add process later | The reference guide frames this as the first design choice and recommends harness-first (reconstructed from `other/harness/HARNESS_BUILD_FROM_SCRATCH.md`, commit bb13847). |
| Stay at H1 with Markdown-only records | Kept for one week; the three H1 friction items made state unqueryable, which triggered the climb to H2 in ADR-0002 (reconstructed from commit bb13847). |

## Consequences

- Gain: stability; every change carries clear acceptance evidence.
- Gain: agents do not break the database structure or a data contract without review.
- Cost: each working session needs extra steps to open an intake and record a trace.
- Original outcome note (2026-08-24): the H1 to H5 foundation was set up, and the authors reported that lost traces and work-state drift were eliminated. No measurement backs that claim.

### Current status (2026-10-06)

- D1: in force. ADR-0021 amends how harness knowledge is written, not the harness-first direction.
- D2, D3, D4: in force through `AGENTS.md` and `docs/FEATURE_INTAKE.md`.
- D5: in force, amended by ADR-0021.D1. Markdown files with frontmatter are now the source of truth; `harness.db` story and decision tables are derived.

## Rollback

- Rollback means removing the intake, story, proof and trace steps from `AGENTS.md` and `docs/HARNESS.md`. Agents would then patch product code directly.
- No technical rollback is recorded. Only the operator may order it, through a new ADR.

## Follow-up

- [x] Climb from H1 to H2 with a durable layer: ADR-0002 (commit 3a0c527).
- [x] Normalize this ADR under the knowledge contract: ADR-0021.D6.
- [ ] Reconcile the maturity claim: `docs/HARNESS_MATURITY.md` says "H5 Ready" while `docs/HARNESS.md` still says H1 (ADR-0021 follow-up G6).
