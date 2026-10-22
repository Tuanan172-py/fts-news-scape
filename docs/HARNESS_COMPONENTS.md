# HARNESS_COMPONENTS.md — Eleven Runtime Responsibilities of the Harness (H2)

This document names the **eleven core responsibilities** the harness guarantees across the human-agent interaction lifecycle.

---

## The eleven runtime responsibilities

| # | Responsibility | Role | Implementation in News-Scape |
|:---|:---|:---|:---|
| **1** | **Task Specification** | Machine-readable work with an explicit risk class. | `FEATURE_INTAKE.md` + `intake`, `story` tables; story files from `doc new`. |
| **2** | **Context Boundary** | Bounds the documents and code loaded into context. | `CONTEXT_RULES.md` + per-lane budgets; `docs/INDEX.md` as the entry point. |
| **3** | **Tool Access** | Which tools an agent may call and how they degrade. | `TOOL_REGISTRY.md`. |
| **4** | **Memory & State** | Durable record of what happened across sessions. | `harness.db` (`story`, `trace`, `backlog`) and `docs/knowledge/facts/FACT-*.md`. |
| **5** | **Task State** | Status and order of work, no double claim. | `status` in story frontmatter, WIP=1 per worktree (ADR-0022), checked by `doc lint`. |
| **6** | **Observability** | Measures behaviour, files read and changed. | `trace` table with `score_trace` and `score_context`; `query matrix`. |
| **7** | **Failure Attribution** | Captures errors and friction for root-cause analysis. | `intervention` and `backlog` tables (friction reservoir). |
| **8** | **Verification Gate** | Proof before a story counts as done ("No proof = not done"). | `unit/integ/e2e/platform_proof` columns + `story complete --run-verify`, `session close`. |
| **9** | **Permissions Gate** | Read-only versus mutation, hard gates. | `AGENTS.md` §0 + `FEATURE_INTAKE.md` hard gates. |
| **10**| **Entropy Audit** | Detects drift of process and documents. | `python scripts/harness_cli.py audit` (`HARNESS_AUDIT.md`). |
| **11**| **Intervention & Propose** | Proposes process improvements from accumulated friction. | `python scripts/harness_cli.py propose` (`IMPROVEMENT_PROTOCOL.md`). |

---

## Self-check lens

When adding a process or tool, the agent checks:
* Does the change break the **Context Boundary**?
* Does it come with a mechanical **Verification Gate**?
* Is the new state written to **durable storage**?
