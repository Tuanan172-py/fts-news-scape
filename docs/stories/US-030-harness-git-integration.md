# US-030 — Tích hợp quy trình Git toàn diện vào khung quản trị Harness

**Trạng thái:** `in_progress`  
**Cấp độ rủi ro (Lane):** `normal`  
**Parent Epic:** `Harness Core Governance`  
**Intake ID:** 28  

---

## 1. Bối cảnh & Vấn đề

- **Vết đứt gãy giữa Git và Harness**: Trước US-030, `harness_cli.py` quản lý `intake`, `story`, `decision`, `trace` trong SQLite `harness.db`, nhưng hoàn toàn không có tương tác cơ học với Git.
- **Hệ quả tiêu cực**:
  - Nhiều story đạt trạng thái `implemented` nhưng không có commit tương ứng trên Git (ví dụ US-028).
  - Tệp rác và tệp thử nghiệm nhanh (`test1.py`, `check_key.py`, worktree rác `.kilo`) nằm tự do ở trạng thái untracked, dễ bị stage nhầm.
  - Bảng `Harness Closure Protocol` thiếu dòng báo cáo bắt buộc về trạng thái Git.

---

## 2. Tiêu chí Chấp thuận (Acceptance Criteria)

1. **Hygiene & Dọn dẹp**:
   - Gỡ bỏ và dọn dẹp worktree rác `.kilo/worktrees/pushy-cheddar`.
   - Cập nhật `.gitignore` để tự động loại trừ `scratch/`, `openrouter/*_key.py`, `**/test_scratch*.py`.
2. **Schema Migration (004-git-tracking.sql)**:
   - Bổ sung cột `git_commit TEXT` và `git_branch TEXT` vào bảng `story`.
   - Bổ sung cột `git_commit TEXT` và `git_branch TEXT` vào bảng `trace`.
3. **Harness CLI Mechanical Git Integration**:
   - `harness_cli.py` tự động phát hiện nhánh hiện tại và commit hash mới nhất.
   - Khi ghi nhận trace (`cmd_trace`), tự động lưu `git_commit` và `git_branch`.
   - Lệnh `story complete`: Hỗ trợ cờ `--commit` để tự động tạo commit chuẩn `type(scope): title (US-XXX)` khi vượt qua verification gate, đồng thời lưu hash vào story.
   - Thêm nhóm lệnh `harness_cli.py git` (`checkpoint`, `verify`, `status`).
4. **Cập nhật Bất biến Quản trị (Rules & Skills)**:
   - Cập nhật `.agents/rules/04-harness-durable-invariants.md`: Thêm ràng buộc Git vào bảng Harness Closure Protocol (dòng thứ 7).
   - Cập nhật `.agents/skills/git-codebase-governance/SKILL.md`: Chuẩn hóa quy trình Commit / Push / PR gắn liền với Harness Story.
5. **Kiểm thử (Proof)**:
   - Thêm unit test kiểm tra chức năng Git trong `tests/test_harness_cli.py`.
   - Toàn bộ test suite pass 100%.
