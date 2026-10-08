---
id: US-002
type: story
title: Optimize user output format and clean structure
status: changed
lane: normal
created: 2026-08-24
updated: 2026-10-06
lang: en
authors: [An Pham Thanh]
adr: []
related: [US-008]
evidence: ["commit:4e1d02e", "commit:8f13c70", "path:project/src/export/user_output.py", "test:project/tests/test_user_output.py", "metric:13/13 tests passed in 3.57s", "metric:60 rows generated for AnPT"]
verify: "cd project; python -m pytest tests/test_user_output.py tests/test_user_workflow.py -v"
original: "commit:8f13c70"
summary: User CSV output put business columns first, formatted key points as bullets and kept audit files in a master folder; the column contract and paths later changed.
---

# US-002 — Optimize user output format and clean structure

## Contract

- `final.csv` puts business columns first: `date`, `matched_entities`, `title`, `summary`, `key_points`, `implication`, `impact_area`, `materiality_score`, `time_sensitivity`, `sentiment`, `event_type`.
- Technical and audit columns come last: `url`, `source_domain`, `article_id`, `agent_provider`, `model_used`.
- `key_points` is formatted with newlines and bullets (`- point 1\n- point 2`) for multi-line display in Excel and CSV cells.
- The user folder contains ONLY `final.csv` (no `L1.csv` or `agent.csv`).
- The master audit directory `users/output/_master/<YYYY-MM-DD>/` contains all three files (`L1.csv`, `agent.csv`, `final.csv`).

## Acceptance Criteria

- [x] `FINAL_COLUMNS` in `user_output.py` uses the new column order.
- [x] `_final_row()` formats `key_points` as bullet points with newlines.
- [x] `UserOutputWriter.write()` writes only `final.csv` in user folders; audit files remain in `_master/`.
- [x] Unit tests in `tests/test_user_output.py` pass and verify the new column structure and folder contents.
- [x] Design document `project/docs/design/13-per-user-output-workflow.md` is updated.

## Design Notes

- Smallest real slice: modify `src/export/user_output.py` and update assertions in `tests/test_user_output.py`.
- Intake: lane `normal`, because the story touches the output CSV format (user deliverable contract) and existing tested behavior.
- Changed (2026-09-07): the `final.csv` column contract changed. `materiality_score` was hidden (CORE/DETAIL model) and `gold_status` was added. The export gate moved from "both layers" to L1-only (US-008).
- Changed (2026-09-08): the nested path `users/output/<name>/<YYYY-MM-DD>/final.csv` was wrong against shipped code.
- The real paths are flat: `users/output/<name>/<YYYY-MM-DD>.csv` for users and `users/output/_master/<YYYY-MM-DD>.csv` plus `_L1.csv` and `_agent.csv` for audit.
- Source of truth for the later contract: `src/export/user_output.py` and `project/docs/design/13-per-user-output-workflow.md` §9 to §10.1.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `cd project; python -m pytest tests/test_user_output.py tests/test_user_workflow.py tests/test_compile_users.py tests/test_user_checkpoint.py -v` | passed, 13/13 in 3.57s |
| Integration | `cd project; python scripts/write_user_output.py --date all` | passed, 60 rows for AnPT, clean `final.csv` plus `_master` audit files |
| Platform | none | not run |

## Evidence

- Passing tests: `test_gate_and_routing`, `test_enabled_filter`, `test_flatten_null_safe`, `test_date_filter_excludes_other_day`, `test_workflow_writes_output`, `test_workflow_disabled_user`.
- Also passing: `test_roundtrip_xlsx`, `test_compile_maps_and_reports_unknown`, `test_unknown_file_cleared_when_fixed`, `test_compile_all_skips_underscore`, `test_enabled_users_manifest`, `test_idempotent_double_write`, `test_resume_adds_new_article`.
- Real data header of `users/output/AnPT/2026-08-17/final.csv`:

```
date,matched_entities,title,summary,key_points,implication,impact_area,materiality_score,time_sensitivity,sentiment,event_type,url,source_domain,article_id,agent_provider,model_used
```

- Harness delta: `TEST_MATRIX.md` row US-002 marked `implemented`; `SESSION-LATEST.md` overwritten.
- Files changed: `project/src/export/user_output.py`, `project/tests/test_user_output.py`, `project/docs/design/13-per-user-output-workflow.md`, `docs/TEST_MATRIX.md`, `docs/SESSION-LATEST.md`.
