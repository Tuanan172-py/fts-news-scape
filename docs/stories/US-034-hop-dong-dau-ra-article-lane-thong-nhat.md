---
id: US-034
type: story
title: Unified Article Lane output contract for every provider
status: implemented
lane: high-risk
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh, claude-opus-5-5]
adr: [ADR-0017, ADR-0018]
plan: []
evidence:
  - commit:a7e9db8
  - path:project/schemas/article-compact-v2.schema.json
  - path:project/src/agent/article_contract.py
  - path:project/src/agent/conformance.py
  - path:project/scripts/provider_conformance.py
  - path:.agents/rules/11-hop-dong-dau-ra-thong-nhat.md
  - test:project/tests/test_article_contract.py
  - test:project/tests/test_conformance.py
  - metric:pytest project/tests/test_article_contract.py 17 of 17 passed, 2026-10-05 (harness.db)
  - metric:800 tests passed excluding test_cli_entrypoints, 2 failures out of scope, 2026-10-05
verify: "python -m pytest project/tests/test_article_contract.py -q"
original: "commit:a7e9db8"
reconstructed: 2026-10-06
summary: Every provider (agy, OpenRouter, opencode, DSH) returns the compact record through one schema and one validation function; deviations are rejected into repair instead of being silently corrected.
---

# US-034 — Unified Article Lane output contract for every provider

## Contract

Every provider (agy, OpenRouter, opencode, DSH) returns the compact record through the same contract and the same validation function. A deviating record is rejected and goes to `--repair`; nothing corrects it silently. ADR-0017 holds the decisions.

## Acceptance Criteria

- [x] S1: `schemas/article-compact-v2.schema.json` and `src/agent/article_contract.py` are the single source; a test blocks drift against the prefix and the expander (ADR-0017.D1).
- [x] S2: one shared `parse_and_validate`; duplicate validators and parsers in agy, OpenRouter and opencode are removed (D4).
- [x] S3: the expander no longer applies semantic defaults to `sn`, `ts`, `c`, `im` and `k` (D3).
- [x] S4: one `build_user_message`, standard parameters, mandatory meta and a standard batch of 50 (D5).
- [x] S5: prefix, registry, `AGENTS.md` and archived documents are updated; rule 11 is added (D2, D8).
- [x] S6: `--runner opencode` exists, and an unknown runner raises an error instead of falling back to agy (D6).
- [x] S7: `provider_conformance.py` and a 30-article golden set harness, with agy as the benchmark (D7).
- [x] pytest passes except `test_cli_entrypoints.py`, apart from `test_inherit` owned by the clustering work; `ast.parse` passes.
- [ ] Golden set labelled and run for each provider. Pending in `docs/OPEN-ITEMS.md` CON-1 item 2 on 2026-10-06.

## Design Notes

- One commit per step so each can be reverted with `git revert`. Flag `contract.strict` in `ops.yaml` covers the transition.
- `claude` is not a lane provider yet. Do not run the whole pytest suite without reading FACT-tests-must-not-write-operational-db.
- The original file was blocked on 2026-10-05 to yield WIP and waited for a DSH restart, the golden set and token ledger work. On 2026-10-06 CON-1 item 1 closed because DSH is no longer used.
- ADR-0018 (Silver body and one citation for one-paragraph articles) was first written in the same commit.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest project/tests/test_article_contract.py -q` | 17 of 17 passed (harness.db, 2026-10-05) |
| Integration | `python -m pytest tests --ignore=tests/test_cli_entrypoints.py` from `project/` | 800 passed; 2 failures outside scope |
| Platform | golden set through `provider_conformance.py` | pending |

## Evidence

- Commit a7e9db8: schema, `article_contract.py`, `conformance.py`, runners, expander, prefix, rule 11, ADR-0017, ADR-0018 and tests.
- Out-of-scope failures at closure (from the original file): `test_inherit` failed on the `hold_cutoff` of the clustering work; `test_article_lane_hardening::code_first` was clock-dependent.
- Harness delta: ADR-0017, rule 11, registry, `AGENTS.md`, banners on two archived documents and item CON-1 in `docs/OPEN-ITEMS.md`.
