# TRACE_SPEC.md — Trace Structure and Execution Evidence (H2)

This document standardises the agent execution trace for **observability**: reconciliation, benchmarking and self-improvement (H3–H5).

---

## 1. Three trace tiers (per prompt)

Every prompt or session **MUST** record one trace row in `harness.db` at the tier of its lane:

| Trace tier | Lane | Required fields | Purpose |
|:---|:---:|:---|:---|
| **Tier 1: Minimal** | `tiny` | `task_summary`, `outcome`, `files_read` or `files_changed` | Quick record of Q&A, architecture lookups, diagnostics or 1-2 line patches. |
| **Tier 2: Standard** | `normal` | `task_summary`, `story_id`, `actions_taken`, `files_read`, `files_changed`, `outcome`, `friction` | New features, module refactors, context measurement and test evidence. |
| **Tier 3: Detailed** | `high-risk` | All Standard fields + `intake_id`, `score_context`, `score_trace`, `error_msg`, `intervention` | Strict audit of architecture safety (hard gate, ADR, schema). |


---

## 2. Trace fields (`trace` table)

```json
{
  "story_id": "US-002",
  "intake_id": 1,
  "task_summary": "Optimize the per-user output column layout",
  "actions_taken": [
    "Read user_output.py",
    "Reorder FINAL_COLUMNS",
    "Update the test case in test_user_output.py",
    "Run pytest 13/13 passed"
  ],
  "files_read": [
    "project/src/export/user_output.py",
    "project/tests/export/test_user_output.py"
  ],
  "files_changed": [
    "project/src/export/user_output.py",
    "project/tests/export/test_user_output.py",
    "docs/stories/US-002-optimize-user-output-format.md"
  ],
  "outcome": "completed",
  "score_context": 1.0,
  "score_trace": 1.0,
  "friction": "None",
  "created_at": "2026-08-24T14:00:00+07:00"
}
```

---

## 3. Trace scoring (`calculate_score_trace`, `calculate_score_context` in `scripts/harness_cli.py`)

1. **`score_trace` (0.0 to 1.0):**
   * $+0.25$ when `task_summary` has at least 10 characters.
   * $+0.25$ when `actions_taken` lists at least one step.
   * $+0.25$ when `files_read` or `files_changed` is present.
   * $+0.25$ when `outcome` is one of `completed`, `blocked`, `failed`, `partial`.
2. **`score_context` (0.0 to 1.0):**
   * $1.0$ when the number of files read is within the lane budget (Tiny $\le 5$, Normal $\le 15$, High-risk $\le 30$).
   * Minus $0.05$ per file over budget (floor $0.2$).
   * **`files_read` lists only files that enter the orchestrating agent's context directly.** Files an
     Explore subagent reads are not listed (see `CONTEXT_RULES.md` §1): they do not occupy the
     orchestrator's context window, and delegation is encouraged.

---

## 4. Recording a trace with the CLI

```powershell
python scripts/harness_cli.py trace `
  --story "US-002" `
  --summary "Optimize user output column format" `
  --outcome "completed" `
  --actions '["Update FINAL_COLUMNS", "Run pytest"]' `
  --files-read '["project/src/export/user_output.py"]' `
  --files-changed '["project/src/export/user_output.py"]'
```

`session close` records the trace itself as part of atomic closure (AGENTS.md §12).
