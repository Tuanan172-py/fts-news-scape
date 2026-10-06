---
id: ADR-0017
type: adr
title: Unified Article Lane output contract for every provider
status: accepted
lane: high-risk
created: 2026-10-05
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
approvers: [operator 2026-10-05]
story: [US-034]
amends: [ADR-0009, ADR-0011]
related: [ADR-0010]
evidence:
  - commit:a7e9db8
  - path:docs/stories/US-034-hop-dong-dau-ra-article-lane-thong-nhat.md
  - path:.agents/rules/11-hop-dong-dau-ra-thong-nhat.md
  - path:project/schemas/article-compact-v2.schema.json
  - path:project/src/agent/article_contract.py
  - path:project/src/agent/conformance.py
  - path:project/scripts/provider_conformance.py
  - path:project/config/ops.yaml
  - test:project/tests/test_article_contract.py
  - test:project/tests/test_conformance.py
  - metric:audit of 467 output files across agy, openrouter, opencode and DSH, 2026-10-05
  - metric:missing ids 623 (43 of 124 batches) agy, 299 (33 of 79 batches) openrouter
  - metric:2988 entity pairs unresolvable in legacy DSH waves
  - operator:parameters fixed 2026-10-05 (c 2-4, batch 50, agy benchmark, claude not in lane)
original: "commit:a7e9db8"
reconstructed: 2026-10-06
summary: One JSON Schema and one parse_and_validate function govern the compact record for agy, OpenRouter, opencode and DSH; silent semantic defaults are banned, and new providers pass a 30-article golden set benchmarked on agy.
summary_vi: Một hợp đồng đầu ra và một hàm kiểm duy nhất cho mọi provider; cấm sửa ngầm; provider mới phải qua bộ vàng 30 bài, agy là thước đo.
---

# ADR-0017 — Unified Article Lane output contract for every provider

## Context

- The Article Lane runs on several providers: agy (`gemini-3.8-flash-low`), OpenRouter, opencode (Muse Spark) and DSH (`deepseek-flash`). The same article produced different output per provider.
- An audit on 2026-10-05 covered three angles: contract and gates, prompt and runner, and measurement over 467 output files. The cause was structural, not one specific model.
- The decision touches the Data Contract of `article-processor`, the runners and the expander, so it is high-risk. The operator approved it on 2026-10-05 and opened the Hard Gate.
- It amends ADR-0009 D6, which said every model is `deepseek-flash`. It also builds on ADR-0010 and ADR-0011. The extended schemas `agent-output-v2-lean` and `l1-entity-output-v1` are unchanged.

### Evidence 1. The compact record has no source of truth

- The compact record `{i,e,s,k,im,sn,ts,c}` had no JSON Schema, pydantic model or constants module.
- It existed piecemeal in `build_article_prefix.py`, `article_expand.py`, `agy_runner.py`, `openrouter_runner.py`, `opencode_native_run.py` and `intent_resolve.py`.
- The two extended schemas existed as files but only checked expander output, which is correct by construction. They could not check the model.

### Evidence 2. Four JSON parsers and three validators with different strictness

| Path | Parsing | Validation |
|---|---|---|
| agy | `salvage_json_records`; a truncation error loses the whole batch | rejects on `c` and group; no check of enums, `im` length or `k` count |
| openrouter | most lenient, salvages each object | self-repairs: pads `im` with invented text, maps `sn` by substring, fills missing `c`, accepts synonym keys |
| opencode | no parsing | strictest: all 8 keys, `k` 2-4, `im` 40+ characters, valid enums |
| DSH | no pre-check | only `article_expand.salvage_records` |

### Evidence 3. The shared gate `article_expand.py` silently applied defaults

- An invalid `sn` became `neutral`. An invalid `ts` became `this_week`, while openrouter defaulted to `today`.
- When `c` had fewer than 2 valid indices, the first paragraphs were filled in.
- A string `k` was split into single characters, with no maximum of 4.
- Duplicate `c` values produced duplicate citations. A 1-based `c` shifted every citation without an error.
- Provider drift was therefore hidden, not measured.

### Evidence 4. Measured drift (real output, rate per record)

| Drift class | agy | openrouter | opencode | legacy DSH |
|---|---|---|---|---|
| Missing ids (PARTIAL batches) | 623 ids, 43/124 batches | 299 ids, 33/79 batches | 0 | not measurable |
| `c` below 2 valid indices (silently padded) | 5.5% | 1.3% | 1.2% | 10 records |
| `c` abnormally long | max 9 | max 16, 136 records with 9+ indices | always exactly 3 | max 12 |
| `k` above 4 | 0 | 9.3% | 0 | 1.4% |
| `k` below 2 | 1.8% | 0 | 0 | 4 records |
| Duplicate entity pairs | 1.2% | 1.0% | 0 | 55 pairs |
| Malformed TIC (`TPBank`, `Vinhomes`) | 14 | 24 | 3 | 50 |
| `ts` outside enum | 2 (`year`) | 0 | 0 | 0 |
| Empty `e` | 0.5% | 1 | 0.8% | 0 |
| Distribution skew | `sn` pos 53% | `sn` pos 36% | `ts` month 75%, `c` always 3 | different entity schema |

- JSON structure drift is the minority. The largest cost is batches with missing ids, from truncation at the OpenRouter output ceiling of 24000 tokens, and drift in list sizes.
- The legacy DSH waves (W09241605, W09241723, W365, W1, W2) used a different entity schema. 2988 pairs do not resolve under the current resolver.

### Evidence 5. Process and documents contradicted each other

- The user prompt frame differed. agy added a block "QUY TẮC BẮT BUỘC" and a `## Packet` heading. openrouter repacked the packet as `{d,n,a}`. DSH sent the packet file verbatim.
- Sampling differed: openrouter `temperature 0.1`, `max_tokens 24000`, `reasoning minimal`; DSH `reasoning off`; agy set nothing. No provider set a seed.
- The prefix contradicted itself. Its example emitted an entity absent from the text, while the rule required verbatim surfaces. Its example had a one-item `k`, while the rule said 2-4.
- The prefix banned code fences, while the expander and the opencode docs expected them.
- `registry.yaml` bound `article-processor` to skill `l1-entity-matcher` of the retired lane, with two schema names the prefix never emits. AGENTS.md said every model is `deepseek-flash`, contrary to agy, OpenRouter, opencode and the agy daemon default.
- The archived `agent-runner-prompt.md` and `agent-prompting-guide.md` taught agents to read packets themselves and write one file per article. They also required a report of written files plus `materiality` and `impact_area`.
- That is the inverse of the Article Lane contract. No `claude` run path existed in code, so Claude-style agents had only these two documents to follow.
- Provenance metadata was wrong. The expander defaulted to `dsh/deepseek-flash` when meta was missing. The token ledger tagged `--source agy` only for agy, so openrouter and opencode cost was misattributed.
- `cmd_analyze` fell back to agy for every runner other than openrouter.

### Stated limit

Sameness cannot mean character-identical output across models. Summary, `sn` and entity lists are language judgements, so two models will differ. This ADR makes three things deterministic. First, the shape and canonical form of the output. Second, every deviation is detected and enters the repair loop. Third, semantic agreement between providers is measured on a golden set.

## Decision

### Fixed parameters (2026-10-05)

| Parameter | Value |
|---|---|
| Number of `c` indices | 2 to 4 |
| Standard batch size | 50 |
| Golden-set benchmark provider | agy (`gemini-3.8-flash-low`) |
| Golden-set match threshold | Provisional: another provider reaches the agy golden-set score minus 5 percentage points on `sn`, `ts` and the TIC set. The final figure is fixed after the first agy measurement (D7). |
| `claude` | Not admitted to the lane. D6 does not add `--runner claude`. |

### D1. One source of truth for the compact record

- Create `project/schemas/article-compact-v2.schema.json` (JSON Schema) and one module `project/src/agent/article_contract.py` that reads it and exports constants: entity groups, enums and limits.
- The prefix (`build_article_prefix.py`), the validator and the expander `sn`/`ts` mapping MUST be generated from this source, never copied by hand.
- Test `test_article_contract_sync.py` blocks drift, following the pattern of `test_pipeline_spec.py`.

### D2. Closed rule for each field

| Field | Hard rule |
|---|---|
| `i` | integer, present in the packet, unique, ascending |
| `e` | array of pairs of exactly 2 items `[surface, GROUP_CODE]`; group code is one of 11 codes; no duplicates (case-insensitive); an empty array is valid |
| `s` | string, 1 to 3 sentences |
| `k` | array of strings, exactly 2 to 4 items, no item duplicating a citation |
| `im` | string of 40+ characters, not a verbatim copy |
| `sn` | exactly `pos`, `neg`, `neu` |
| `ts` | exactly `urg`, `today`, `week`, `month`, `arch` |
| `c` | array of 0-based integers, unique, ascending, within `[0, n_paragraphs)`, 2 to 4 indices (the 4 awaited operator confirmation) |
| unknown keys | rejected, not ignored |

The language of `s`, `k` and `im` is Vietnamese, and the prefix states it.

### D3. No silent repair

- Every semantic default is banned. No invalid `sn` to `neutral`, no invalid `ts` to `this_week` or `today`, no filled `c`, no padded `im`, no synonym keys, no split string `k`.
- A violating record is dropped from the batch and enters `--repair` with an error code.
- Only two kinds of mechanical normalization are allowed. Both are recorded in meta as counters.
- First, transport unwrapping: vendor envelope, code fence, text before `[`, and per-object salvage on truncation.
- Second, canonical form decided by code, not by the model: `c` sorted ascending, `e` sorted by group order then surface, `k` kept in model order.
- This normalization is mechanical and does not replace LLM judgement, so it does not violate AGENTS.md section C.

### D4. One parse and validate function

- `article_contract.parse_and_validate(text, packet)` returns valid records, errors by id and envelope counters.
- agy, openrouter, opencode, the DSH conductor (through the post-check of `article_run.py`) and the expander MUST call it.
- Delete `agy_runner.validate_records`, `openrouter_runner.validate_records`, both `salvage_json_records`, `ENTITY_GROUP_MAP` and the copies of `VALID_ENTITY_GROUPS`.
- The expander accepts only records that passed this function, so its default branches are removed.

### D5. One input frame, one parameter set

- One function `build_user_message(packet)`. No agy-specific guard and no packet repacking. Every provider receives the same bytes.
- One system prefix file, as before, with its SHA256 added to meta. The hand-pasted copy in `agent.cordis.yml` stays guarded by `--check`.
- Standard parameters: `temperature 0`, a fixed seed where supported, no `reasoning` or its lowest level. `max_tokens` equals the provider ceiling.
- That ceiling is a transport limit to avoid truncation, not a token cap under the rule "token là ghi nhận". Unsupported parameters are stated in meta.
- Each batch MUST carry meta: `provider`, `model`, sampling parameters, prefix SHA256 and contract version. Missing meta fails `--finish`.
- The expander default `dsh/deepseek-flash` is removed, and the ledger tags the source from meta.
- One standard batch size for every provider (proposed 50, following the daemon). Per-provider deviation requires a measurement and an entry in `ops.yaml`.

### D6. One lifecycle; a provider is only a transport adapter

- Every provider follows the same path: `pack`, `run`, `parse_and_validate`, `repair`, `expand`, `--finish`. In `run` the adapter only sends and receives.
- Adapter interface: `run_batch(packet_text) -> raw_text`.
- opencode and Claude-style agents go through `append_records` into the D4 function, with no validator of their own.
- Add `--runner` values `opencode` and `claude` to `article_run.py`. `cmd_analyze` MUST raise an error for an unknown runner instead of falling back to agy.

### D7. Golden-set gate for a new provider or model

- A fixed golden set of 30 articles is labelled by the operator through review screen S-13, with command `python scripts/provider_conformance.py --runner <r> --model <m>`.
- A provider or model enters the lane only when three conditions hold. Structural violations after unwrapping are zero. No ids are missing.
- The third condition is that agreement with the golden labels on `sn`, `ts` and the TIC set reaches the fixed threshold.
- The result is written as a report from `docs/templates/validation-report.md`. The command spends tokens, so it runs only for a new model, not every wave.

### D8. Clean up contradicting documents and configuration

- Fix the prefix so its examples obey the rules: entities occur in the text and `k` has 2-4 items. Code fences are banned and still unwrapped if present.
- Fix `registry.yaml` for `article-processor`: current skill, compact record as output schema, `model` per real configuration.
- Change AGENTS.md section 6.A from "every model is deepseek-flash" to the list of providers admitted by the golden set.
- Remove `agent-runner-prompt.md` and `agent-prompting-guide.md` from the agent read path with a withdrawal banner linking the new contract. Both contradict the current contract.
- New rule `.agents/rules/11-hop-dong-dau-ra-thong-nhat.md` condenses D1 to D7 into a project invariant. It is written only after this ADR is approved.

### D9. Legacy waves

The five legacy DSH waves stay unchanged in Bronze and the DB. Reports mark them `contract=legacy`, and they are not re-expanded. Nothing is deleted.

### Amendment history

The original section 7 recorded these adjustments made during implementation under US-034. They do not change the direction of the decision.

- D2, duplicate `e` and `c`: code normalizes mechanically by dropping duplicates and sorting, with a counter, instead of rejecting the record. A duplicate does not change meaning, and rejection would send the whole article to repair. The `c` count is taken after deduplication.
- D2, `s` with 1 to 3 sentences: only a warning counter `warn_summary_sentences`, no rejection. Vietnamese abbreviations such as "TP. Hồ Chí Minh" break a period-based sentence count.
- D2, `c` and short paragraphs: an index pointing to a paragraph under 20 characters is rejected. When an article has fewer than two long-enough paragraphs, the minimum index count drops to that number.
- D2, Vietnamese diacritics check: the existing agy `lost_diacritics` check is kept and moved into the shared validator.
- Section 5, flag `contract.strict`: not implemented. Rollback is by `git revert` of each commit.

## Alternatives

| Option | Why rejected |
|---|---|
| Force every provider onto one model | Not guaranteed: free tiers expire, prices differ, and the operator chose multiple providers. |
| Keep expander defaults and add a fourth validator | Adds one more copy to four copies that already drifted. |
| Use each provider's structured output | No lane provider uses it today, and support is uneven (agy CLI, opencode live session). It may be added later as an extra layer, not as a replacement for D4. |
| Use regex or heuristics to fix bad output | Violates AGENTS.md section C; silent repair is exactly what hid the drift. |
| Cap articles or tokens to reduce truncation | Contradicts the rule that tokens are recorded, not gated. |

## Consequences

Gains:

- One place to change the contract; a test blocks drift between prompt, validator and expander.
- Provider drift appears as measurements and as a repair queue, not hidden by defaults.
- A new provider has a clear, measured entry gate.
- Provenance and cost are attributed to the right source.

Costs accepted:

- The rejection rate rises at first: agy about 5.5% short `c` and 1.8% short `k`; openrouter 9.3% long `k`. These were hidden before. The existing `--repair` loop and prefix fixes at the measured drift points reduce it.
- Extra tokens are spent on repair rounds. They are recorded, not gated.
- Many files on the critical run path change, so implementation needs a window with no wave open alongside the daemon.
- The golden set depends on operator labelling effort.

### Current status (2026-10-06)

- D1 to D6 and D8 shipped in commit a7e9db8 under US-034. Standard batch 50 is set in `project/config/ops.yaml`.
- The D1 sync check lives in `test_article_contract.py` (`test_prefix_khop_hop_dong`), not in a separate `test_article_contract_sync.py`.
- The golden set is still unlabelled, so D7 cannot score providers yet (`docs/OPEN-ITEMS.md` CON-1 item 2).
- The token ledger still accepts only `dsh` and `agy` as `--source` (CON-1 item 3).
- opencode has no official `--runner` yet; its adapter already uses the shared validator (CON-1 item 4).
- The rejection rate under the new gate is not yet measured on a real wave (CON-1 item 9).
- v1 constants remain in `src/agent/packet.py`, `batch_handoff.py` and `dod.py` (CON-1 item 8).
- DSH remains a runtime option under this contract; the operator ruled on 2026-10-06 that no runtime is retired (FACT-llm-runtimes-are-interchangeable).

## Rollback

- Each step D1 to D8 is a separate change that `git revert` undoes.
- The planned `contract.strict: false` flag was not implemented, so rollback is only by revert.
- Only the operator may disable the golden-set gate.

## Follow-up

- [x] Operator approves the ADR and fixes the `c` limit, the standard batch size and the golden-set threshold (2026-10-05).
- [x] Open the story. Proposed order: D1 and D4, D3, D5, D2 and D8, D6, D7 (US-034).
- [x] Ask the operator which provider is the golden-set benchmark and whether `claude` joins the lane (agy; `claude` not admitted).
- [ ] Re-measure drift after D3 with the same audit script to compare before and after.
- [ ] Review `src/agent/packet.py`, `batch_handoff.py` and `dod.py` for v1 constants (out of scope, tracked in `docs/OPEN-ITEMS.md`).
