---
id: US-032
type: story
title: Ops M1 presentation standards glossary and doc lint
status: implemented
lane: normal
created: 2026-10-01
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: [ADR-0014]
plan: []
evidence:
  - commit:dd492ed
  - commit:579163c
  - commit:0340f64
  - path:project/scripts/doc_lint.py
  - path:project/src/ops/present.py
  - path:docs/GLOSSARY.md
  - path:docs/templates/plan.md
  - path:docs/templates/proposal.md
  - path:docs/templates/runbook.md
  - path:project/docs/operations/ops-daemon-reference.md
  - test:project/tests/test_ops_present.py
  - test:project/tests/test_doc_lint.py
  - metric:M1 S-01 to S-06, 704 tests passed, doc_lint 0 violations, 2026-10-01 (harness.db)
verify: "python -m pytest project/tests/test_ops_present.py project/tests/test_doc_lint.py -q"
reconstructed: 2026-10-06
summary: Every operator-facing product (documents, ADRs, runbooks, Telegram messages, control room) follows one presentation standard and one glossary, checked by a zero-token doc lint inside pytest.
---

# US-032 — Ops M1 presentation standards glossary and doc lint

## Contract

Every product the operator reads, including documents, ADRs, runbooks, Telegram messages and the control room, follows one presentation standard and one glossary. A zero-token lint checks the documents, and pytest runs that lint.

## Acceptance Criteria

- [x] `docs/GLOSSARY.md` covers the ops and Article Lane vocabulary in Vietnamese.
- [x] Three new templates exist for plan, proposal and runbook documents.
- [x] `src/ops/present.py` is the shared formatter for Telegram, console and control room text.
- [x] `project/scripts/doc_lint.py` runs inside pytest and reports 0 violations at closure.
- [x] High-priority drift items among S1 to S23 are fixed (reconstructed from the harness.db acceptance text; no per-item record was found).
- [x] The daemon is restarted on the new code and the control room is checked in Edge.

## Design Notes

- Milestone M1 of the ops work covers steps S-01 to S-06; `harness.db` names S-01 to S-05 in the title and S-01 to S-06 in the evidence. No document defining each step was found.
- Parent epic in `harness.db`: "Autonomous Ops".
- The lint is deterministic and costs zero tokens, in line with ADR-0014 supervision tooling.
- `doc_lint.py` later became the legacy checker; files with typed frontmatter are checked by `scripts/knowledge.py` under ADR-0021.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `verify` command in frontmatter | part of 704 tests passed (harness.db, 2026-10-01) |
| Integration | `python project/scripts/doc_lint.py` | 0 violations at closure |
| Platform | control room screenshot in Edge after daemon restart | taken, 2026-10-01 |

## Evidence

- Commit dd492ed: stored as the story commit in `harness.db`. Its content is the FPA toolkit strategy plan, supervision changes and the split of the ops-daemon runbook into a reference page.
- Commit 579163c (commit labelled US-031): `doc_lint.py`, `present.py`, `test_ops_present.py`, the glossary rewrite and the three templates.
- Commit 0340f64 (commit labelled US-036): `project/tests/test_doc_lint.py` as present in this repository history.
