# Phase 03 — Checkpoint / Resume theo article_id

## Context links
- Parent: [plan.md](plan.md) · Depends: Phase 02.
- Reuse idempotency DB: `l1_outputs`/`agent_outputs` dod_pass cached (l1_runner/runner đã trả cached).

## Overview
- **Date:** 2026-08-18 · **Priority:** P1 · **Impl status:** ⬜ · **Review:** ⬜
- Cho phép chạy lại/tiếp tục mà không xử lý lại phần đã xong, không nhân đôi output.

## Key Insights
- Đã có 2 lớp idempotency: (a) DB — cùng article_id/(article_id,raw_sha256) đạt DoD → trả cached, không double-mark; (b) writer cần lớp riêng cho FILE output.
- Checkpoint đơn giản nhất = tập `article_id` đã ghi vào `final.csv` per user. Resume = bỏ qua id đã có.

## Requirements
1. Không nhân đôi dòng trong final.csv khi chạy lại.
2. Ngắt giữa chừng → chạy lại chỉ ghi phần còn thiếu.
3. Trạng thái per user (và per date).

## Architecture
### Checkpoint file `users/output/<name>/_checkpoint.json`
```json
{ "written": { "2026-08-18": ["<article_id>", ...] },
  "last_run_at": "<vn_iso>", "last_date": "2026-08-18" }
```
- Trước khi ghi 1 user/date: load set `written[date]`; lọc bỏ article_id đã có → chỉ append phần mới.
- Ghi final.csv theo chế độ APPEND (giữ header nếu file mới) HOẶC rewrite toàn bộ tập (đơn giản, an toàn hơn: gom rows đã-written ∪ mới rồi rewrite atomic). Chọn **rewrite atomic** để tránh header lặp/ file hỏng.
- Cập nhật checkpoint SAU khi `os.replace` thành công (crash-safe: nếu chết trước replace → lần sau ghi lại, không mất).
### Guard tầng xử lý (tránh gọi lại agent thừa)
- `run_user_workflow` (P4) chỉ enqueue/agent-export article CHƯA có agent_outputs.dod_pass=1 (store đã hỗ trợ cached) → checkpoint L3 theo article_id đạt đúng yêu cầu người dùng.
- Optional: bảng `pipeline_state` ghi `user_output_last_date` cho toàn cục.

## Related code files
- NEW `project/src/export/checkpoint.py` (`load_checkpoint`, `mark_written`, `filter_new`)
- MODIFY `project/src/export/user_output.py` (dùng checkpoint trong `write`)

## Implementation Steps
1. `checkpoint.py`: load/save json atomic; `filter_new(user, date, ids)`; `mark_written(user, date, ids)`.
2. Tích hợp vào `UserOutputWriter.write`: lọc new → union rows → rewrite atomic → mark.
3. Đảm bảo thứ tự: write file trước, mark checkpoint sau.

## Todo list
- [ ] checkpoint.py (load/save/filter/mark, atomic)
- [ ] Tích hợp writer (rewrite atomic + mark sau replace)
- [ ] Guard agent-export chỉ article thiếu agent_outputs.dod_pass

## Success Criteria
- Chạy writer 2 lần liên tiếp → final.csv KHÔNG đổi (0 dòng thêm).
- Xóa 1 article khỏi checkpoint → lần sau nó được ghi lại đúng 1 lần.
- Ngắt giữa batch → rerun hoàn tất phần còn thiếu, không trùng.

## Risk Assessment
- Checkpoint & final.csv lệch nhau (một cái ghi, cái kia chưa) → mitigate bằng thứ tự replace-rồi-mark + rewrite toàn tập.
- Nhiều tiến trình ghi cùng user → ngoài phạm vi (chạy tuần tự per user); ghi chú không chạy song song cùng user.

## Security Considerations
- Không lưu nội dung nhạy cảm trong checkpoint (chỉ article_id + timestamp).

## Next steps → Phase 04 nối toàn bộ.

## Unresolved
- Có cần checkpoint toàn cục ở `pipeline_state` (đa máy) không, hay file-per-user là đủ? Đề xuất: file-per-user đủ giai đoạn này.
