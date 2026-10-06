---
id: FACT-unified-output-contract
type: fact
title: Unified Article Lane output contract
status: active
created: 2026-10-05
updated: 2026-10-06
verified: 2026-10-05
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0017]
story: [US-034]
evidence:
  - "path: project/schemas/article-compact-v2.schema.json"
  - "path: project/src/agent/article_contract.py"
  - "path: .agents/rules/11-hop-dong-dau-ra-thong-nhat.md"
  - "commit: a7e9db8"
  - "operator: 2026-10-05 c holds 2 to 4 indexes, batch 50, agy is the gold-set baseline, claude not in the lane"
summary: The compact record schema article-compact-v2 is the only output contract, validated only by parse_and_validate; agy is the gold-set baseline and claude is not in the lane.
---

# FACT-unified-output-contract — Unified Article Lane output contract

## Fact

- ADR-0017 was accepted on 2026-10-05 with story US-034.
- The compact record `{i,e,s,k,im,sn,ts,c}` is defined in `project/schemas/article-compact-v2.schema.json` and read through `src/agent/article_contract.py`.
- Every runner uses `parse_and_validate`; a separate validator is forbidden. Rule 11 is the invariant.
- Operator choices: `c` holds 2 to 4 indexes, the standard batch is 50, and agy is the provider that sets the gold-set baseline.
- The provisional threshold is the agy score minus 5 points. `claude` is not yet in the lane.

## Why

- An audit found provider differences hidden by three validators of different strictness.
- The expander also defaulted `sn=neutral` and `ts=this_week` and filled `c` itself.
- Character-identical output across models is impossible. Only the output shape is deterministic; semantics must be measured on the gold set.

## How to Apply

- To change the contract: edit the schema first, regenerate the prefix, sync `persona` in `agent.cordis.yml`, then restart the DSH host (rule 09).
- Open items sit in `docs/OPEN-ITEMS.md` item CON-1: DSH restart after a prefix change, gold-set labels and ledger source tagging by meta.
