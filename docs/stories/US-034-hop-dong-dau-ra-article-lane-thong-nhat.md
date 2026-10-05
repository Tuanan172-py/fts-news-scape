# US-034 — Hợp đồng đầu ra Article Lane thống nhất cho mọi provider

- **Status:** blocked (2026-10-05, nhường WIP cho US-035; chờ restart DSH, bộ vàng, sổ cái token)
- **Lane:** high-risk (ADR 0017 accepted 2026-10-05)
- **Parent / Epic:** Article Lane, chất lượng đầu ra đa provider
- **Intake date:** 2026-10-05
- **Depends On:** none

## Product Contract
Mọi provider (agy, openrouter, opencode, DSH) trả record gọn qua cùng một hợp đồng và cùng một hàm kiểm. Sai lệch bị từ chối và vào `--repair`, không bị sửa ngầm. Chi tiết: `docs/decisions/0017-hop-dong-dau-ra-article-lane-thong-nhat-moi-provider.md`.

## Acceptance Criteria
- [x] S1: `schemas/article-compact-v2.schema.json` và `src/agent/article_contract.py` là nguồn duy nhất; test chặn lệch với prefix và expander (D1)
- [x] S2: `parse_and_validate` dùng chung; xoá validator và bộ phân tích trùng ở agy, openrouter, opencode (D4)
- [x] S3: expander không còn mặc định ngữ nghĩa cho `sn`, `ts`, `c`, `im`, `k` (D3)
- [x] S4: một `build_user_message`, tham số chuẩn, meta bắt buộc, lô chuẩn 50 (D5)
- [x] S5: prefix, registry, AGENTS.md, tài liệu lưu trữ được sửa; rule 11 (D2, D8)
- [x] S6: `--runner opencode`, runner lạ báo lỗi thay vì rơi về agy (D6)
- [x] S7: `provider_conformance.py` và bộ vàng 30 bài, agy làm thước đo (D7)
- [x] pytest (trừ `test_cli_entrypoints.py`) đạt, trừ `test_inherit` của US-033; `ast.parse` đạt

## Design Notes
Mỗi bước một commit để `git revert` được. Cờ `contract.strict` trong `ops.yaml` cho chuyển tiếp. Không chạy pytest toàn bộ trước khi đọc memory `pytest-ghi-db-that-va-bronze-mo-coi`. `claude` chưa vào lane.

## Validation
| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; python -m pytest tests/test_article_contract.py tests/test_openrouter_runner.py tests/test_conformance.py tests/test_agy_runner.py` | passed | 800 test đạt trên toàn bộ trừ test_cli_entrypoints; 2 lỗi nằm ngoài phạm vi (xem Trace) |

## Harness Delta
ADR 0017; rule 11; registry và AGENTS.md; banner cho hai tài liệu lưu trữ; mục CON-1 trong OPEN-ITEMS.

## Trace (inline, H1)
- **Actions:** intake, audit ba hướng, ADR 0017, S1 đến S7
- **Files changed:** schemas/article-compact-v2.schema.json, src/agent/{article_contract,conformance,agy_runner,openrouter_runner}.py, scripts/{article_expand,article_run,article_pack,build_article_prefix,opencode_native_run,provider_conformance}.py, data/prefix, .agents/dsh preset persona, registry, AGENTS.md, rule 11, tests
- **Outcome:** partial (chờ restart DSH, bộ vàng, mở rộng sổ cái)
- **Friction:** `test_inherit` lỗi do hold_cutoff của US-033; `test_article_lane_hardening::code_first` chập chờn theo đồng hồ; test_cli_entrypoints vẫn ghi DB thật.
- **Điều chỉnh so với ADR:** xem ADR 0017 mục 7.
