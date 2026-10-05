# Phase 05 — Tests

## Context links
- Parent: [plan.md](plan.md) · Covers P1–P4. Reuse test style trong `project/tests/`.

## Overview
- **Date:** 2026-08-18 · **Priority:** P1 · **Impl status:** ⬜ · **Review:** ⬜
- Kiểm chứng: compile đúng, gate đúng, idempotent/resume, end-to-end smoke.

## Requirements
- Không phụ thuộc mạng/agent thật (agent-agnostic). Dùng temp dir + temp sqlite. Fixtures nhỏ.

## Architecture / Test matrix
### `tests/test_compile_users.py` (P1)
- xlsx fixture (openpyxl dựng runtime) có tickers HPG/FPT + 1 mã sai `ZZZ`.
- compile → yaml chứa HPG,FPT; `_unknown.txt` chứa ZZZ; `registry.resolve_subscription(name)` ra đúng ids.
- enabled=FALSE / folder `_x` → bị bỏ.

### `tests/test_user_output.py` (P2)
- Seed store: 3 articles. A1: l1 dod_pass + agent dod_pass (chạm HPG). A2: chỉ l1 done. A3: cả 2 done nhưng entity không ai đăng ký.
- write(date) → AnPT/<date>/final.csv chỉ có A1; A2,A3 vắng. Cột đúng, matched_entities=HPG.
- flatten null-safe: agent thiếu `event_type`/`sentiment` → ô rỗng, không lỗi.

### `tests/test_checkpoint.py` (P3)
- write() 2 lần → final.csv identical, checkpoint chứa A1.
- Xóa A1 khỏi checkpoint → write lại → đúng 1 dòng A1 (không nhân đôi).

### `tests/test_user_workflow.py` (P4)
- Temp db + temp users/input (1 user) → run(mode=ingest, skip_scrape=True) với l1/agent outputs seed sẵn → final.csv sinh ra + summary rows>0 + log "done".
- User disabled → 0 output.

## Related code files
- NEW tests trên; REUSE helpers trong `tests/conftest.py` nếu có (temp store).

## Implementation Steps
1. Fixture builder: `make_store(tmp)`, `seed_article(store, id, entities, l1_pass, agent_pass)`.
2. Viết 4 file test theo matrix.
3. Chạy `pytest project/tests -k "user or compile or checkpoint"`.

## Todo list
- [ ] fixtures (temp store + seed helpers)
- [ ] test_compile_users
- [ ] test_user_output (gate + flatten)
- [ ] test_checkpoint (idempotent/resume)
- [ ] test_user_workflow (smoke)

## Success Criteria
- Tất cả test xanh; coverage các nhánh: gate đủ/thiếu layer, subscriber match/không, idempotent.

## Risk Assessment
- Seed sai schema output_json → dùng `schemas/samples/*.json` làm khuôn để fixture hợp lệ.

## Security Considerations
- N/A (test nội bộ).

## Next steps → Review với user, rồi implement theo thứ tự P1→P5.

## Unresolved
- Có yêu cầu ngưỡng coverage tối thiểu không? Đề xuất: không ép %, chỉ phủ nhánh chính.
