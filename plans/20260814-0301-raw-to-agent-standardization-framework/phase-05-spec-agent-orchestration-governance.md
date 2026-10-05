# Phase 05 — [SPEC-ONLY] Agent Orchestration & Governance Framework

> **SPEC-ONLY. NO agent code, NO LLM calls, NO framework install now.** Deliverable = governance doc + diagrams
> + machine-readable state/DoD definitions (JSON/YAML). Provider-agnostic. Implementation deferred.

## Context links
- Research: `research/researcher-02-agent-framework.md` §3 (orchestration, subagent roles, loops), §4 (execution
  governance, task lifecycle, definition-of-done, idempotency, HITL), §5 (quality gates, LLM-as-judge, metrics).
- Phase 3: work-package INPUT + catalog watermark. Phase 4: OUTPUT schema.

## Overview
- **Date:** 2026-08-14 · **Priority:** MEDIUM (design; the "agent layer to come").
- **Description:** Specify the agent execution framework so any provider can implement it: main-agent
  (router/dispatcher) → subagents (extractor, analyst, verifier/critic, aggregator); pipeline-by-default;
  loop conditions; task lifecycle states; definition-of-done touchpoint; guardrails/preconditions;
  provider-agnostic (no vendor lock). Written spec + state machine only.
- **Implementation status:** SPEC ONLY · **Review status:** NOT REVIEWED.
- **Type:** SPEC/DESIGN.

## Key Insights
- 2026 winning pattern (researcher-02 §3): deterministic backbone (flow) + agent invoked intentionally at steps;
  control returns to flow — NOT autonomous loops. Encode as state machine, not free-running agent.
- Definition-of-done is a concrete checkpoint (schema-valid AND confidence≥threshold AND ≥N citations AND
  status→COMPLETE) — this is the "điểm chạm báo hiệu công việc ĐÃ THỰC SỰ hoàn thành".
- Idempotency via (article_id, raw_sha256) already provided by Phase 3 catalog → agent reuse cached result.
- Provider-agnostic: define roles/contracts/states independent of LangGraph/CrewAI/MCP; those are impl choices.

## Requirements (deliverables — docs/config only)
- D1: `docs/design/10-agent-orchestration-governance.md` — main/sub roles, flow, loops, lifecycle, DoD, guardrails, HITL.
- D2: `schemas/task-lifecycle-v1.yaml` (or json) — machine-readable state set + allowed transitions + DoD predicate.
- D3: Mermaid diagrams for pipeline + state machine (embedded in doc 10).

## Orchestration spec (encode in doc + diagrams)
**Roles / order (main → sub):**
1. **Router (main)** — claim work_item(s) from catalog; classify article type; dispatch. Always first.
2. **Extractor (sub)** — read work-package INPUT; fill canonical OUTPUT schema (summary/entities/event/sentiment).
3. **Analyst (sub)** — enrich implication(hàm ý) + materiality(mức độ quan trọng). LOOP: refine 1–2x if confidence<0.7.
4. **Verifier/Critic (sub)** — schema validation (hard) + groundedness/citation check (LLM-as-judge, optional).
5. **Aggregator (sub)** — dedupe cross-source duplicates, merge related; finalize; mark_done in catalog.

**Pipeline-by-default:**
```
catalog.claim -> Router -> Extractor -> Analyst -(loop?)-> Verifier -(fail?)-> back to Extractor/Analyst
             -> Aggregator -> OUTPUT (agent-output-v1) -> contract_validator -> mark_done
```

**Loop conditions (explicit, bounded):**
- Map-reduce: batch N articles → parallel extractors → aggregator merge.
- Iterative refine: `materiality.confidence < threshold` → Analyst re-run with more context (MAX 2 iters).
- Adversarial verify: Critic asks "is implication overreaching?" → reconcile; MAX 1 round.
- ALL loops bounded (max-iters) — no unbounded autonomy (guardrail).

**Task lifecycle states (task-lifecycle-v1):**
`STARTED → EXTRACTION_PENDING → VERIFICATION_PENDING → (COMPLETE | FAILED_RECOVERABLE | FAILED_PERMANENT)`.
Transitions defined; FAILED_RECOVERABLE → retry (bounded); maps to catalog status pending/claimed/done/failed/held.

**Definition-of-Done touchpoint (COMPLETE iff ALL):**
1. OUTPUT passes `contract_validator` (agent-output-v1) — hard.
2. `confidence ≥ threshold` (config, default 0.65).
3. `len(citations) ≥ N` (config, default 2), each grounded (source_span ⊂ cleaned_text).
4. `extraction_quality ∈ {high, medium}`.
5. `processing_metadata` (provider, model, timestamp) logged.
→ Only then `catalog.mark_done`. Else `mark_failed`/`held` (never silently "done").

**Guardrails / preconditions:**
- Precondition: work-package `change_state ∉ {SELECTOR_BROKEN, TEMPLATE_DRIFT}` (else held, skip agent).
- Precondition: `raw_sha256` re-verified against Bronze before processing (integrity).
- Idempotency: cache by (article_id, raw_sha256); replay returns cached OUTPUT.
- Bounded loops; timeout per task; no tool/network beyond declared adapters.
- HITL gates (researcher-02 §4): confidence>0.8 auto; 0.5–0.8 flag review; verifier concern → human.

## Related code files
- CREATE `project/docs/design/10-agent-orchestration-governance.md` (spec + mermaid).
- CREATE `project/schemas/task-lifecycle-v1.yaml` (states + transitions + DoD predicate, machine-readable).
- NO source code. NO framework dependency added.

## Implementation Steps (authoring only)
1. Write doc 10: role table (main/sub), pipeline diagram, loop table (trigger, max-iters), lifecycle state machine,
   DoD checklist, guardrails/preconditions, HITL thresholds, provider-agnostic note (roles ≠ vendor).
2. Author `task-lifecycle-v1.yaml`: enumerate states, allowed transitions, DoD boolean predicate referencing
   agent-output-v1 fields + thresholds.
3. Embed Mermaid: (a) pipeline sequence, (b) lifecycle state machine.
4. Cross-link Phase 3 catalog status ↔ lifecycle states (mapping table) and Phase 4 OUTPUT schema fields ↔ DoD.

## Todo list
- [ ] docs/design/10-agent-orchestration-governance.md (roles, flow, loops, lifecycle, DoD, guardrails, HITL).
- [ ] schemas/task-lifecycle-v1.yaml (states, transitions, DoD predicate).
- [ ] Mermaid pipeline + state-machine diagrams embedded.
- [ ] Catalog-status ↔ lifecycle-state mapping table; OUTPUT-fields ↔ DoD mapping.

## Success Criteria
- A dev on ANY provider can build the agent from doc 10 + schemas alone (roles, order, loops, DoD unambiguous).
- DoD predicate is machine-checkable (references agent-output-v1 + thresholds) — testable later without ambiguity.
- Lifecycle states map cleanly to Phase 3 catalog statuses (no orphan states).
- No vendor lock: no LangGraph/CrewAI/OpenAI-specific requirement in the contract (only in "possible impl" note).

## Risk Assessment
- R1 Over-engineering multi-agent (YAGNI) → spec allows single-agent MVP (Router+Extractor+Verifier); Analyst/Aggregator optional.
- R2 DoD too strict (≥2 citations) blocks valid short articles → thresholds configurable; document tuning.
- R3 Spec drift from real impl later → keep doc 10 authoritative; impl must reference it; validator enforces OUTPUT.
- R4 Unbounded loops if impl ignores caps → make max-iters part of the contract, not optional.

## Security Considerations
- Guardrails: precondition integrity check (raw_sha256), bounded loops/timeouts, no network beyond adapters
  → limits prompt-injection blast radius from untrusted article HTML.
- HITL gates for high-materiality/low-confidence (finance high-stakes) documented.
- Audit trail mandated in DoD (provider/model/timestamp/confidence) for reproducibility (EU AI Act / NIST — researcher-02 §5).

## Next steps
- Phase 6: E2E governance doc stitches producer↔agent contract; wires OUTPUT validator gate; migration/versioning.
