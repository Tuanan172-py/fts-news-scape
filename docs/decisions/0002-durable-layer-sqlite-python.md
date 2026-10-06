---
id: ADR-0002
type: adr
title: Durable layer using SQLite and a Python CLI
status: accepted
lane: high-risk
created: 2026-08-24
updated: 2026-10-06
lang: en
authors: [operator, agy]
approvers: ["operator (date unrecorded)"]
story: []
related: [ADR-0001]
evidence:
  - commit:bb13847
  - commit:3a0c527
  - commit:e765737
  - commit:0f1a65c
  - commit:1561636
  - path:scripts/harness_cli.py
  - path:scripts/schema/001-init.sql
  - path:tests/test_harness_cli.py
  - path:other/harness/HARNESS_BUILD_FROM_SCRATCH.md
original: "commit:3a0c527"
reconstructed: 2026-10-06
summary: Harness state (story, intake, decision, backlog, trace, intervention, tool) lives in a WAL-mode SQLite file harness.db, isolated from monocle.db, and is operated through the Python CLI scripts/harness_cli.py.
summary_vi: Trạng thái harness lưu trong SQLite harness.db (chế độ WAL, tách khỏi monocle.db) và thao tác qua CLI Python scripts/harness_cli.py, không cần toolchain Rust/Go.
---

# ADR-0002 — Durable layer using SQLite and a Python CLI

## Context

- At maturity H1 the harness kept state in hand-edited Markdown files, such as `SESSION-LATEST.md` and the Markdown table in `TEST_MATRIX.md`.
- That caused friction: state was hard to query automatically, it drifted, and trace scoring and entropy audit could not be automated.
- The H1 backlog recorded the same pain on 2026-08-18. Item 1, "Status not queryable across stories", was named the primary climb-to-H2 signal (reconstructed from `docs/HARNESS_BACKLOG.md` at commit bb13847).
- The H1 plan set four climb signals: status not queryable, a stale hand table, a trail lost between sessions, and backlog needing predicted-versus-actual (reconstructed from `plans/20260817-1536-harness-h1-newsscape/plan.md`).
- The reference guide leaves the engine open. Its reference framework used a Rust prebuilt binary with SQLite. It requires a queryable store, safe concurrent writes and no toolchain install for the consumer (reconstructed from `other/harness/HARNESS_BUILD_FROM_SCRATCH.md`, commit bb13847).

## Decision

- D1. The harness MUST keep a durable layer in a SQLite file, `harness.db`, in WAL mode. It MUST be fully isolated from `monocle.db`.
- D2. `harness.db` stores the state of Story, Intake, Decision, Backlog, Trace, Intervention and Tool.
- D3. Agents and humans MUST interact with the durable layer through one Python CLI, `scripts/harness_cli.py`. It needs no external binary toolchain (Rust or Go) and runs in the existing Windows and Python environment.

## Alternatives

| Option | Why rejected |
|---|---|
| Status quo: H1 Markdown files (`SESSION-LATEST.md`, `TEST_MATRIX.md` table) | Not queryable, drift-prone, and blocks automated trace scoring and audit (original Context; backlog item 1 at commit bb13847). |
| Rust prebuilt binary with SQLite, as in the reference framework | Would require a Rust or Go toolchain that the project does not use; the decision names this explicitly (reconstructed from `other/harness/HARNESS_BUILD_FROM_SCRATCH.md`). |
| Store harness state inside `monocle.db` | The decision requires full isolation from `monocle.db`. No further rationale was recorded. |

## Consequences

- Gain: Story, Trace and Audit are managed automatically and are machine-readable as JSON or tables.
- Gain: the CLI checks evidence before a story moves to `implemented` (`story complete` proof gate, commit 3a0c527).
- Cost: agents run CLI commands instead of editing Markdown by hand.
- Commit 3a0c527 added `scripts/harness_cli.py` (722 lines), `scripts/schema/001-init.sql` (125 lines) and `tests/test_harness_cli.py` with five tests.
- Later migrations extended the schema: `002-agent-metrics.sql` (commit e765737), `003-intake-types.sql` (commit 0f1a65c) and `004-git-tracking.sql` (commit 1561636, US-030).
- Original outcome note (2026-08-24): the move from H1 to H2-H5 succeeded, with automated state queries and audit. No measurement was recorded.

### Current status (2026-10-06)

- D1: in force. `harness.db` stays a WAL-mode SQLite file, separate from the product database.
- D2: amended by ADR-0021.D1. The `story` and `decision` tables are now derived from Markdown files by `harness_cli.py doc sync`. `trace`, `intake` and `agent_metrics` stay runtime data.
- D3: in force; `scripts/harness_cli.py` remains the single harness interface.

## Rollback

- Return to H1 by keeping state only in Markdown files and ignoring `harness.db`.
- The schema files in `scripts/schema/` and `scripts/harness_cli.py` can be removed with `git revert` of the introducing commits. Only the operator may order it.

## Follow-up

- [x] Add schema migrations as needs appear (002, 003, 004).
- [x] Derive `story` and `decision` rows from files: ADR-0021.D1.
- [ ] Record why `harness.db` must stay separate from `monocle.db`; the original gave no reason.
