# US-041 — Test xanh, sổ cái token theo provider, phân tích độ phủ thu thập

- **Status:** implemented
- **Lane:** normal
- **Parent / Epic:** Gỡ chặn sau migration (US-038)
- **Intake date:** 2026-10-08
- **Depends On:** US-038 (nhánh `dev/us038`)

## Product Contract
Bộ test toàn phần chạy xanh không phụ thuộc ngày chạy. Sổ cái token ghi đúng chi phí cho từng provider kể cả khi một đợt dùng nhiều provider. Người vận hành biết vì sao thu thập thiếu và cần làm gì khi mở lại vận hành.

## Acceptance Criteria
- [x] `test_inherit` không còn phụ thuộc ngày: `cluster_job.refresh` nhận `today`, test truyền ngày cố định (audit US-038 P1-10)
- [x] Sổ cái tính từng tệp meta theo `agent_provider` của nó; đợt pha agy và openrouter ghi hai dòng
- [x] Token đọc từ cache (`cache_read_tokens`, `prompt_tokens_details.cached_tokens`) vào `hit_tokens`, không cộng vào `miss_tokens`
- [x] opencode-native được nhận; meta không có số token thì dòng ghi `usage=không ghi`
- [x] Chạy lại `--finish` thay mọi dòng runner cũ của đợt, kể cả khi đổi provider
- [x] `--finish` truyền `--source auto` khi không biết runner
- [x] Phân tích độ phủ thu thập và lệnh xả tồn đọng ghi vào OPEN-ITEMS CAP-1
- [ ] Adapter opencode ghi `usage` thật vào meta (ngoài phạm vi)

## Design Notes
- E1 (lô vá trùng) đã được sửa trước story này bằng tập `claimed` trong `cmd_repair`; story chỉ đóng mục.
- Không nâng giới hạn cào bù trong chu kỳ morninger: chu kỳ đã chiếm khoảng 7 trên 10 phút. Tồn đọng do dừng vận hành được xả một lần bằng lệnh tay ở bước mở lại.
- Làm trên worktree riêng `C:\src\news-scape-us041`, nhánh `fix/us041-unblock-tests-ledger` tách từ `dev/us038`, không đụng worktree migration.

## Validation
| Tier | Command | Status | Evidence |
|---|---|---|---|
| Unit | `python -m pytest tests/test_inherit.py tests/test_ledger_openrouter.py -q` | pass | 2026-10-08 |
| Full | `python -m pytest tests/ -q` | pass | 892 passed, 0 failed (mốc trước: 888 passed, 1 failed) |
