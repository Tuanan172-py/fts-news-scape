---
id: ADR-0003
type: adr
title: Deterministic code-first L1 results are written to l1_outputs and delivered
status: superseded
lane: high-risk
created: 2026-09-08
updated: 2026-10-06
lang: en
authors: [operator, agent]
approvers: ["operator 2026-09-09"]
story: []
related: [ADR-0001]
evidence:
  - commit:8f13c70
  - commit:3b6003b
  - commit:bb47e44
  - path:project/src/export/user_output.py
  - path:project/src/db/store.py
  - path:project/scripts/article_pack.py
  - path:project/config/entities/aliases/_context_guards.yaml
  - metric:monocle.db copy 2026-09-07, 7,219 articles, 1,787 l1_tasks, 424 gated articles, 146 matching AnPT
  - metric:alias guards on 1,787 real titles removed 270 false matches and added 37 correct ones; TICKER:IVS 164 to 0
  - operator:approved 2026-09-09, recorded in docs/OPEN-ITEMS.md item A1 at commit 3b6003b
original: "commit:3b6003b"
reconstructed: 2026-10-06
summary: Allowed catalog-lookup (code-first) L1 entity matches into l1_outputs, tagged l1_source='code_first', so deliveries no longer waited on an unrun LLM step; agent output may overwrite them. Superseded by ADR-0010.
summary_vi: Cho phép ghi kết quả tra danh mục tất định (code-first) vào l1_outputs với l1_source='code_first' để mở lại đường giao hàng; output của Agent được ghi đè; đã bị ADR-0010 thay thế.
---

# ADR-0003 — Deterministic code-first L1 results are written to l1_outputs and delivered

## Context

- The user delivery gate (`src/export/user_output.py:35-50`) required `articles ⨝ l1_outputs (dod_pass=1)`.
- `l1_outputs` had exactly one writer, `L1Runner.ingest_output()`, which ran only after an LLM subagent submitted output.
- The deterministic tier `l1_classifier` (0 token) already resolved entities into `l1_tasks.code_first_json`. No path carried that data to the delivery gate.
- Articles with `route='resolved'`, the ones where code-first had found a subscribed ticker, stayed `status='pending'` forever.
- No automated LLM runner existed in the repository. `requirements.txt` had no SDK, and `scripts/agent_stub.py`, called by `run_daily.ps1`, did not exist.
- The queues only grew: 1,102 pending `l1_tasks` plus 3,477 pending `work_items`. The gate depended on a manual step nobody ran, so in practice it was closed.

Measurements on `data/monocle.db`, 2026-09-07:

| Metric | Value |
|---|---|
| `articles` | 7,219 |
| `l1_tasks` | 1,787, of which `resolved` with a TICKER: 562 |
| TICKER hits in `code_first_json` | 710 (216 distinct `entity_id`) |
| `l1_outputs` | 685, stopped since 2026-08-25, with 0 TICKER entities |
| Articles passing the delivery gate | 424, of which 146 match the AnPT watchlist |
| If `code_first` were read | 1,320, of which 743 match AnPT (5.1 times more) |

## Decision

- D1. Records produced by deterministic catalog lookup MAY be written to `l1_outputs`. They MUST be marked by a new column `l1_source ∈ {'agent','code_first'}`.
- D2. Allowed under `AGENTS.md` §6C: mapping a string to an `entity_id` by lookup in the standard catalog `data/entities/entities.json` (2,152 entities issued by the organization). This is a verifiable, 100% reproducible lookup with no inference.
- D3. Still forbidden for scripts, and 100% owned by the LLM subagent: summary, `implication`, `materiality_score`, `sentiment`, `event_type`, semantic `citations`, and entities absent from the catalog (`unlisted_candidates`).
- D4. Articles with `route='needs_agent'` (code-first matched nothing; 541 articles) MUST still go through the agent. This ADR does not shrink the agent's scope; it stops discarding what lookup already found.
- D5. The `code_first` record is provisional. When the agent processes the same `article_id`, its output MAY overwrite it (`l1_source='agent'`). The reverse MUST NOT happen.

### Amendment history

- 2026-09-08 (commit 8f13c70): written as proposed, awaiting operator approval as a Tier 3 high-risk change to a data contract and DB schema.
- 2026-09-09 (commit 3b6003b): status changed to accepted after operator approval.

## Alternatives

| Option | Why rejected |
|---|---|
| Status quo: deliver only agent-written `l1_outputs` | The gate depended on a manual LLM step that was not operated; 424 articles passed versus 1,320 with code-first (original Context). |
| Run the LLM L1 subagent on every pending task | No automated runner existed in the repository; `agent_stub.py` was missing (reconstructed from the original Context). |
| Open the gate without fixing alias false positives | `TICKER:IVS` alone would have sent 164 wrong articles to users (original Consequences). |

## Consequences

Gains, as projected in the original:

- Reopens delivery: about 1,320 eligible articles instead of 424; AnPT from 146 to about 700.
- Daily output no longer depends on a manual step nobody runs.
- Token saving: 1,246 of 1,787 articles (70%) need no LLM call for L1.
- `l1_source` lets the quality of the two sources be measured separately.

Costs and risks accepted:

- Deterministic matching ran on titles only, so entities that appear only in the body are missed. This is no regression, because the L1 agent also received titles only.
- Alias false positives were the main risk and were handled before the gate opened.
- Residual ambiguity was recorded but not blocking: `IND_GICS3:NUOC` ("trong nước", "nước ngoài") and `MACRO_GEO:MY` ("thẩm mỹ"). It needs the agent or edited alias data.

Preconditions completed before this ADR (commit 8f13c70):

- `GENERIC_ALIAS_STOPLIST` blocks place-name and generic-suffix aliases generated from legal names.
- A context guard for 3-letter tickers: "TP.HCM" is no longer `TICKER:HCM`.
- A diacritic-folding guard for short one-word aliases: "quý 3" is no longer `IND_GICS*:QUY`.
- L1 DoD checks that each `entity_id` exists in the catalog.
- On 1,787 real titles: 270 false matches removed, 37 correct matches added; `TICKER:IVS` from 164 to 0.

### Current status (2026-10-06)

- Superseded by ADR-0010 (commit bb47e44). The L1/Gold two-tier lane that produced `code_first` records was retired.
- D1: the `l1_source` column remains in `project/src/db/store.py`. Per ADR-0010.D4, `code_first` rows never count as analysed and are excluded from the Article Lane selector (`project/scripts/article_pack.py`).
- D2 and D3: the boundary lives on in `AGENTS.md` §6C and in ADR-0010; catalog matching is used only to cross-check model output.
- D4 and D5: dead with the retired lane.

## Rollback

- Restore the old gate with one SQL condition: add `AND l1.l1_source = 'agent'` to `_GATED_SQL`.
- No reverse schema change is needed and no data is lost.

## Follow-up

- [ ] Original follow-up, never filled: after one week of operation, record delivered articles, the correct-match rate from a 20-row manual check, and how often the agent overwrote `code_first`. Obsolete since ADR-0010.
