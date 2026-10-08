---
id: ADR-0004
type: adr
title: Value gate for the Gold tier and handling of script-emulated data
status: superseded
lane: high-risk
created: 2026-09-08
updated: 2026-10-06
lang: en
authors: [operator]
approvers: ["operator 2026-09-09"]
story: []
evidence:
  - commit:8f13c70
  - commit:3b6003b
  - commit:bb47e44
  - path:project/src/agent/dod.py
  - path:project/schemas/task-lifecycle-v1.yaml
  - path:project/tests/test_no_agent_emulation.py
  - path:project/scripts/verify_gold_quality.py
  - path:project/schemas/agent-instructions-v1.md
  - metric:monocle.db read-only 2026-09-08, 1,274 of 1,274 agent_outputs dod_pass=1, 3 distinct implication texts, 1,117 (87.7%) one template
  - operator:option D1 approved 2026-09-09, recorded in docs/OPEN-ITEMS.md item A2 at commit 3b6003b
  - commit:39c9898
  - commit:4738f66
  - commit:31d539d
  - path:C:/data/news-scape/archive/20261005-cleanup/db-backups/monocle_backup_260909_pre_a2.db
  - metric:pre-A2 backup 2026-09-09 13:24, agent_outputs 1,274 rows, all dod_pass=1, all dod_reasons empty, l1_outputs has no l1_source column
  - metric:C:/data/news-scape/monocle.db read-only 2026-10-06, 1,092 of the 1,274 original ids remain, all dod_pass=0, output_json byte-identical, dod_reasons carry value_added and implication_specific failures
  - metric:C:/data/news-scape/monocle.db read-only 2026-10-06, the other 182 original ids were replaced on 2026-09-10 by gold-financial-analyst reruns via INSERT OR REPLACE
  - metric:monocle_backup_pre_adr0007_260917.db shows the same 1,092 flagged rows and the l1_source column, so both A2 and the A3 migration ran by 2026-09-17
  - path:docs/knowledge/facts/adr-0004-d4-applied-to-operational-db.md
original: "commit:3b6003b"
reconstructed: 2026-10-06
summary: Deleted the script that faked Gold analysis, added DoD predicates value_added and implication_specific, locked anti-emulation tests, and flagged 1,274 faked records dod_pass=0 while keeping output_json (option D1). Superseded by ADR-0010.
summary_vi: Xoá script giả lập phân tích Gold, thêm hai predicate DoD value_added và implication_specific, khoá test chống giả lập, hạ dod_pass=0 cho 1.274 bản ghi giả nhưng giữ output_json (phương án D1).
---

# ADR-0004 — Value gate for the Gold tier and handling of script-emulated data

## Context

- A review of the end-user deliverable (US-101) exposed a problem far worse than formatting. US-101 and US-102 have no story file.
- Measured on `project/data/monocle.db`, read-only, 2026-09-08:

| Metric | Value |
|---|---|
| `agent_outputs` | 1,274 |
| `dod_pass = 1` | 1,274 of 1,274 (100%) |
| `key_points` identical to `citations[].source_span` | 1,274 of 1,274 (100%) |
| `implication.text` | only 3 distinct sentences across all 1,274 records |
| of which one single template sentence | 1,117 (87.7%) |
| `impact_area = market` | 1,274 of 1,274 (100%) |
| `sentiment = neutral` | 1,191 (93.5%) |
| `event_type = macro` | 1,143 (89.7%) |
| labelled `gemini/gemini-3.7-flash` | 1,139 |

### Root cause

- `project/scripts/maintenance/repair_truncated_outputs.py` emulated agent intelligence with a heuristic script, in direct breach of `AGENTS.md` §6.C.
- `extract_sentences()` split sentences by regex and took the first 3 as `summary.abstractive`. So 58% of records had a summary starting with the title itself.
- `key_points = [c["source_span"] for c in citations[:4]]` made key points equal to the cited spans, which explains the 100% above.
- It hard-coded `implication.text` to a template, plus `impact_area="market"`, `materiality.score=0.6`, `time_sensitivity="this_week"`, `sentiment="neutral"`, `event_type="macro"`, `confidence=0.85` and `extraction_quality="high"`.
- It ran `UPDATE agent_outputs … SET agent_provider='gemini', model_used='gemini-3.7-flash'`. This faked provenance, even overwriting `stub` with `gemini`, so regex records became indistinguishable from real LLM records.
- At its end the script called `UserOutputWriter.write(days=30)`, pushing straight to user files.

### Why the DoD gate did not block

- The four old predicates (`schema_valid`, `grounded`, `quality_ok`, `auditable`) measure grounding, not analysis.
- For verbatim-copied output the test `source_span ⊂ cleaned_text` is trivially true, and `extraction_quality` is self-declared.
- A gate that has never rejected a record (1,274 of 1,274 passed) is not a gate.

## Decision

- D1 (part A, done). `scripts/maintenance/repair_truncated_outputs.py` is deleted. It MUST NOT be repaired into a lighter version, because every variant of it is a script writing Gold content.
- D2 (part B, done). `src/agent/dod.py::check_dod` gains two predicates:

| Predicate | Rule |
|---|---|
| `value_added` | Normalized `summary.abstractive` is not a substring of `cleaned_text`; no `key_points[i]` equals a `citations[].source_span` verbatim |
| `implication_specific` | `len(implication.text) ≥ 40`; not a substring of `cleaned_text`; does not match `thresholds.boilerplate_implications` |

- D2 remains deterministic validation. It only rejects and never generates content, so it does not breach §6.C. Thresholds and the blocklist live in `schemas/task-lifecycle-v1.yaml`, editable without code changes.
- D3 (part C, done). `tests/test_no_agent_emulation.py` locks three invariants:
  1. Only `src/db/store.py` may write SQL touching `agent_outputs` or `l1_outputs`.
  2. Only `runner.py` and `l1_runner.py` may call `insert_*_output`, so every record is scored by DoD.
  3. `repair_truncated_outputs.py` MUST stay deleted.
- D3 also updates `schemas/agent-instructions-v1.md` §2b to state that only `citations` may be copied. `schemas/samples/agent-output-sample.json` is fixed, because the sample itself had `key_points == source_span`.
- D4 (part D, approved 2026-09-09 as option D1). For the 1,274 overwritten records, set `dod_pass=0` on records that fail the new gate and KEEP `output_json`. Hard gate per `AGENTS.md` Tier 3.

### Amendment history

- 2026-09-08 (commit 8f13c70): parts A to C executed; part D awaiting operator approval as a hard gate. It touched irreversible data and 424 rows already delivered. The tool `scripts/verify_gold_quality.py` was ready but not run (read-only by default; `--apply` writes).
- 2026-09-09 (commit 3b6003b): operator approved option D1; status set to accepted.

## Alternatives

| Option | Why rejected |
|---|---|
| D1. Set `dod_pass=0` on records failing the new gate, keep `output_json` | Chosen. Articles leave the deliverable and return to the Gold queue; reversible because it is only a flag. |
| D2. Keep the records, tighten only new records | The deliverable keeps worthless template content; does not solve the problem. |
| D3. Delete the emulated records | Also loses the real `citations` already extracted; destroys too much. |
| Repair the emulation script into a lighter version | Every variant still writes Gold content by script (original part A). |

## Consequences

- The new gate rejects almost 100% of old-style output. This is intended: no "full" delivery until the agent prompt follows §2b and reruns.
- Articles with L1 only still deliver as `Sơ bộ`; the L1-only gate mechanism is unchanged.
- Near-constant `sentiment`, `event_type` and `impact_area` share the same root cause.
- `impact_area` and `event_type` were removed from the deliverable in US-101. They should return only when `verify_gold_quality` shows a real distribution.
- A per-record gate cannot detect a whole set being identical. `verify_gold_quality.py` MUST run periodically, with `implication_distinct` as a health metric.
- `docs/OPEN-ITEMS.md` at commit 3b6003b records `verify_gold_quality.py --apply` as executed, setting `dod_pass=0` on all 1,274 records with `output_json` kept.

### Current status (2026-10-06)

- Superseded by ADR-0010 (commit bb47e44), which retired the Gold tier; the Article Lane is the only lane.
- D1 and D3: still enforced; `project/tests/test_no_agent_emulation.py` keeps its three tests.
- D2: `value_added` and `implication_specific` still run in `check_dod`, which the Article Lane ingest gate calls (ADR-0010.D3).
- D4: executed once on 2026-09-09 on the operator machine, before 3b6003b; its effect persists in today's operational DB `C:/data/news-scape/monocle.db`.
- That machine already used this DB via `MONOCLE_DB_PATH` since 2026-09-08 (commit 4738f66); commit 39c9898 only pinned the path in `settings.yaml`.
- Verified read-only on 2026-10-06: 1,092 of the 1,274 original ids remain, all `dod_pass=0`, with `output_json` byte-identical to the pre-A2 backup.
- Their `dod_reasons` hold the new D2 failures, which did not exist when those rows were written in August.
- The other 182 ids were replaced on 2026-09-10 by Gold reruns (`INSERT OR REPLACE` per article), not by D4.
- `docs/OPEN-ITEMS.md` item A3 ("nothing has run on the operational DB") was written on the dev machine about a copy (commit 31d539d) and left stale by 3b6003b; item A2 is correct. See FACT-adr-0004-d4-applied-to-operational-db.
- `project/docs/operations/pipeline-backlog.html` reports `dod_pass=1` on a separate dev copy; that copy is not the operational DB.
- The ban on `materiality`, `event_type` and `impact_area` in model output now comes from `AGENTS.md` §6A, not from this ADR.

## Rollback

- D4 is reversible because it only flips a flag and `output_json` was kept: set `dod_pass=1` again on the affected records (reconstructed from option D1).
- D1 to D3 are reverted with `git revert` of commit 8f13c70. Only the operator may order it, as a Tier 3 change.

## Follow-up

- [x] Operator decision on part D (option D1, 2026-09-09).
- [ ] Run `verify_gold_quality.py` periodically and track `implication_distinct`. Not confirmed as scheduled.
