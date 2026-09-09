# US-002 — Optimize user output format and clean structure

> **SUPERSEDED một phần (2026-09-07):** hợp đồng cột `final.csv` đã đổi — `materiality_score` tạm ẩn
> (mô hình CORE/DETAIL), thêm `gold_status`. Gate export nới từ "đủ 2 lớp" xuống **L1-only**.
> Nguồn đúng hiện tại: `project/docs/design/13-per-user-output-workflow.md` §9–§10.1.
>
> **ĐÍNH CHÍNH ĐƯỜNG DẪN (2026-09-08):** mọi tiêu chí bên dưới ghi
> `users/output/<name>/<YYYY-MM-DD>/final.csv` là SAI so với code đã ship. Đường dẫn thật là
> **phẳng**: `users/output/<name>/<YYYY-MM-DD>.csv` (user) và `users/output/_master/<YYYY-MM-DD>.csv`
> `+ _L1.csv` `+ _agent.csv` (audit). Nguồn sự thật: `src/export/user_output.py`. Giữ nguyên phần
> thân story làm bản ghi lịch sử — không viết lại.

- **Status:** implemented
- **Lane:** normal
- **Parent / Epic:** Per-User Output Workflow
- **Intake date:** 2026-08-24
- **Depends On:** none

## Intake (step 2 output)
```
Lane: normal
Reason: touches output CSV format (user deliverable contract) + existing tested behavior.
Docs: project/docs/design/13-per-user-output-workflow.md
Story: docs/stories/US-002-optimize-user-output-format.md
Validation: cd project; & "C:\Users\anpt\AppData\Local\anaconda3\python.exe" -m pytest tests/test_user_output.py tests/test_user_workflow.py -v
```

## Product Contract
- `final.csv` in `users/output/<name>/<YYYY-MM-DD>/` puts business/human-readable columns first (`date`, `matched_entities`, `title`, `summary`, `key_points`, `implication`, `impact_area`, `materiality_score`, `time_sensitivity`, `sentiment`, `event_type`) and technical/audit columns (`url`, `source_domain`, `article_id`, `agent_provider`, `model_used`) at the end.
- `key_points` is formatted with clean newlines and bullet points (`- point 1\n- point 2`) for clean multi-line display in Excel/CSV cells.
- Individual user folder `users/output/<name>/<YYYY-MM-DD>/` contains ONLY `final.csv` (no `L1.csv` or `agent.csv` in user folders).
- Master audit directory `users/output/_master/<YYYY-MM-DD>/` contains all 3 files (`L1.csv`, `agent.csv`, `final.csv`).

## Acceptance Criteria
- [x] `FINAL_COLUMNS` in `user_output.py` updated to new column order.
- [x] `_final_row()` formats `key_points` as bullet points with newlines.
- [x] `UserOutputWriter.write()` only outputs `final.csv` in user folders; audit files remain in `_master/`.
- [x] Unit tests in `tests/test_user_output.py` pass and verify new column structure and folder contents.
- [x] Design document `project/docs/design/13-per-user-output-workflow.md` updated.

## Design Notes
Smallest real slice: Modify `src/export/user_output.py` and update assertions in `tests/test_user_output.py`.

## Validation
| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; python -m pytest tests/test_user_output.py tests/test_user_workflow.py tests/test_compile_users.py tests/test_user_checkpoint.py -v` | passed | 13/13 passed in 3.57s |
| Integration | `cd project; python scripts/write_user_output.py --date all` | passed | Generated 60 rows for AnPT, clean final.csv + _master audit files |
| E2E | — | — | |
| Platform | — | — | |

> "No proof = not implemented." Set a tier to passed only after the command ran and output is recorded.

## Harness Delta
- Updated `TEST_MATRIX.md` with US-002 row marked `implemented`.
- Overwrote `SESSION-LATEST.md` with US-002 completion.

## Evidence
- Pytest output:
```
tests/test_user_output.py::test_gate_and_routing PASSED                  [  7%]
tests/test_user_output.py::test_enabled_filter PASSED                    [ 15%]
tests/test_user_output.py::test_flatten_null_safe PASSED                 [ 23%]
tests/test_user_output.py::test_date_filter_excludes_other_day PASSED    [ 30%]
tests/test_user_workflow.py::test_workflow_writes_output PASSED          [ 38%]
tests/test_user_workflow.py::test_workflow_disabled_user PASSED          [ 46%]
tests/test_compile_users.py::test_roundtrip_xlsx PASSED                  [ 53%]
tests/test_compile_users.py::test_compile_maps_and_reports_unknown PASSED [ 61%]
tests/test_compile_users.py::test_unknown_file_cleared_when_fixed PASSED [ 69%]
tests/test_compile_users.py::test_compile_all_skips_underscore PASSED    [ 76%]
tests/test_compile_users.py::test_enabled_users_manifest PASSED          [ 84%]
tests/test_user_checkpoint.py::test_idempotent_double_write PASSED       [ 92%]
tests/test_user_checkpoint.py::test_resume_adds_new_article PASSED       [100%]
13 passed in 3.57s
```
- Real data sample `users/output/AnPT/2026-08-17/final.csv`:
```
date,matched_entities,title,summary,key_points,implication,impact_area,materiality_score,time_sensitivity,sentiment,event_type,url,source_domain,article_id,agent_provider,model_used
```

## Trace (inline, H1)
- **Actions:** `/grill-me` design alignment -> implementation plan -> updated `user_output.py`, `test_user_output.py`, `13-per-user-output-workflow.md` -> ran pytest + integration write -> verified file layout.
- **Files read:** project/src/export/user_output.py, project/tests/test_user_output.py, project/docs/design/13-per-user-output-workflow.md.
- **Files changed:** project/src/export/user_output.py, project/tests/test_user_output.py, project/docs/design/13-per-user-output-workflow.md, docs/stories/US-002-optimize-user-output-format.md, docs/TEST_MATRIX.md, docs/SESSION-LATEST.md.
- **Outcome:** completed
- **Friction:** none
