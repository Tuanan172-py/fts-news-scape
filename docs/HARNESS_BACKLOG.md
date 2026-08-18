# HARNESS_BACKLOG.md — Friction reservoir (news-scape, H1)

The harness grows from friction. When something is hard / repeats / is ambiguous / lacks a rule → add a row here (don't silently change the process). Moves to a DB `backlog` table at H2.

**Risk** = a lane (`tiny` / `normal` / `high-risk`), not `low`.

| # | Title | Discovered while | Current pain | Suggested improvement | Risk | Status |
|---|-------|------------------|--------------|-----------------------|------|--------|
| 1 | Status not queryable across stories | Building TEST_MATRIX by hand | Proof/status live in a hand-edited markdown table + scattered story files; no single query for "what's in_progress / unproven". Stale-prone. | H2: SQLite `story`/`trace` + `harness-cli query matrix`. Primary climb-to-H2 signal. | normal | open |
| 2 | WIP=1 has no enforcement | Writing the WIP=1 rule | Honor-system only; nothing stops two `in_progress` stories or a stray branch. | H2 candidate: git pre-commit hook checking a single `in_progress` marker. | tiny | open |
| 3 | SESSION-LATEST is live-state in markdown | Wiring step-9 handoff | A hand-edited state file drifts if not overwritten every session; accepted small debt at H1. | H2: fold into durable `trace.next_action`; keep the file as a generated view. | tiny | open |

<!-- On close: add "Outcome:" with the actual measured result. -->
