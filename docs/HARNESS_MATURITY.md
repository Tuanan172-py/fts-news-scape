# HARNESS_MATURITY.md — Harness Maturity Ladder (H0 – H5)

This document sets the criteria for the maturity and self-operation capability of the harness.

---

## Maturity levels

| Level | Name | Nature | Exit criteria |
|:---|:---|:---|:---|
| **H0** | **Bare** | Prompt in $\rightarrow$ patch out. No harness, no rules. | Starting point. |
| **H1** | **Scaffolding** | Static Markdown rules, templates, risk lanes. No database. | `AGENTS.md`, `HARNESS.md`, `FEATURE_INTAKE.md`, `TEST_MATRIX.md`, `SESSION-LATEST.md` exist. |
| **H2** | **Durable** | SQLite + thin CLI recording durable state (intake, story, decision, trace, backlog). | `harness.db`, `scripts/harness_cli.py`, `CONTEXT_RULES.md`, `TRACE_SPEC.md` exist. |
| **H3** | **Active Observability** | Trace scoring, context budget compliance, friction grouped by component. | `trace` computes `score_trace` and `score_context`; `propose` groups friction by component. |
| **H4** | **Auto-Verification** | Verification runs the real command before a story completes. | `TOOL_REGISTRY.md`; `story complete --run-verify` and `session close` run the verify command. |
| **H5** | **Self-Improvement** | Automatic entropy audit and evidence-based proposals for human approval. | `HARNESS_AUDIT.md`, `IMPROVEMENT_PROTOCOL.md`, `audit` and `propose` commands. |

---

## Current state

* **Level reached:** **H5** (durable database, CLI tooling, tracing and scoring, verification gate, self-improvement protocol, knowledge contract ADR-0021). Tracking records state and does not gate work (ADR-0026.D2).
