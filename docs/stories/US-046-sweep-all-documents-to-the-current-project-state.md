---
id: US-046
type: story
title: Sweep all documents to the current project state
status: in_progress
lane: normal
branch: dev/us038
created: 2026-10-21
updated: 2026-10-21
lang: en
authors: [operator, claude]
adr: [ADR-0026]
plan: []
evidence:
  - path:docs/decisions/0026-canonical-publish-path-runner-order-l0-l1-levels.md
  - path:docs/knowledge/facts/llm-runtimes-are-interchangeable.md
  - path:docs/OPEN-ITEMS.md
verify: "cd project && python -m pytest tests/test_ops_core.py tests/test_publisher.py tests/test_opencode_runner.py -q"
summary: Every current document (ADRs, facts, glossary, open items, design, AGENTS.md) states the same runner order, levels, publish path, manifest and output tree as the code.
---

# US-046 — Sweep all documents to the current project state

## Contract

After this story no current document contradicts the code or ADR-0026. Superseded ADRs, level names, runner lists, manifest paths and output paths are stated once and the same way everywhere. Historical records (plans, proposals, run notes, closed stories) stay as written because they describe the past.

## Acceptance Criteria

- [x] Runner order (agy, `opencode run`, OpenRouter; Claude never a replacement) matches in AGENTS.md, FACT-llm-runtimes-are-interchangeable, design 00 and ADR-0026.
- [x] Levels L0/L1 only: ADR-0012 amendment note, GLOSSARY entries and `order.py` agree.
- [x] ADR-0020 is cited only as superseded by ADR-0023 (`publisher.py` messages, archive fact).
- [x] OPEN-ITEMS reflects `--runner opencode` as code present, not yet accepted by a real wave.
- [x] `doc lint` reports 0 findings and `doc index` is regenerated after the sweep.
- [ ] Operator decides whether `opencode` joins `PROVIDERS` of the daemon (`src/ops/order.py`).

## Design Notes

- Scope is current documents only. Files under `plans/`, `docs/proposals/`, `docs/runs/` and closed stories are history and are not rewritten.
- `opencode_runner.py`, `run_backlog_opencode.*` and the `article_run.py --runner opencode` change were added by another session; this story documents them and does not alter them.
- Accepted ADR bodies are frozen (ADR-0021.D6); ADR-0012 gets an amendment note under its existing amendment history.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | see `verify` | pending |
| Integration | `harness_cli doc lint` | pending |

## Evidence

- Stale-term grep over current docs for `users_output`, `entities/manifest.yaml`, `L2/L3`, `ADR-0020` found only the items fixed here and historical files.

