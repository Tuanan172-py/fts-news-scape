# TRACE_SPEC.md — Đặc tả Cấu trúc Trace & Bằng chứng Thực thi (H2)

Tài liệu này chuẩn hóa định dạng nhật ký thực thi (Trace) của Agent để đảm bảo tính **Observability (Quan sát được)**, phục vụ công tác đối soát, benchmark và tự cải tiến (H3–H5).

---

## 1. Ba Cấp độ Trace (Per-Prompt Trace Tiers)

Mỗi prompt / phiên tương tác của Agent BẮT BUỘC phải ghi lại một bản ghi trace vào CSDL `harness.db` theo cấp độ tương ứng:

| Cấp độ Trace | Áp dụng cho Lane | Các trường bắt buộc | Mục tiêu & Bản chất tác vụ |
|:---|:---:|:---|:---|
| **Tier 1: Minimal** | `tiny` | `task_summary`, `outcome`, `files_read` hoặc `files_changed` | Ghi nhận nhanh các phiên hỏi đáp, tra cứu kiến trúc, chẩn đoán lỗi, hoặc patch 1-2 dòng. |
| **Tier 2: Standard** | `normal` | `task_summary`, `story_id`, `actions_taken`, `files_read`, `files_changed`, `outcome`, `friction` | Đầy đủ cho các tính năng mới, refactor module, đo lường ngữ cảnh và bằng chứng kiểm thử. |
| **Tier 3: Detailed** | `high-risk` | Toàn bộ trường Standard + `intake_id`, `score_context`, `score_trace`, `error_msg`, `intervention` | Phục vụ kiểm toán an toàn kiến trúc nghiêm ngặt (Hard Gate, ADR, Schema). |


---

## 2. Định nghĩa các trường trong Trace (`trace` table)

```json
{
  "story_id": "US-002",
  "intake_id": 1,
  "task_summary": "Tối ưu hóa cấu trúc cột CSV đầu ra cho từng user",
  "actions_taken": [
    "Khảo sát mã nguồn user_output.py",
    "Chỉnh sửa thứ tự cột FINAL_COLUMNS",
    "Cập nhật test case trong test_user_output.py",
    "Chạy kiểm thử pytest 13/13 passed"
  ],
  "files_read": [
    "project/src/export/user_output.py",
    "project/tests/test_user_output.py"
  ],
  "files_changed": [
    "project/src/export/user_output.py",
    "project/tests/test_user_output.py",
    "docs/stories/US-002-optimize-user-output-format.md"
  ],
  "outcome": "completed",
  "score_context": 1.0,
  "score_trace": 1.0,
  "friction": "None",
  "created_at": "2026-08-24T14:00:00+07:00"
}
```

---

## 3. Công thức Chấm điểm Trace (`score-trace` & `score-context`)

1. **`score_trace` (0.0 đến 1.0):**
   * $+0.25$ nếu `task_summary` rõ ràng $\ge 10$ ký tự.
   * $+0.25$ nếu `actions_taken` liệt kê $\ge 1$ bước thực thi.
   * $+0.25$ nếu có thông tin `files_read` hoặc `files_changed`.
   * $+0.25$ nếu `outcome` thuộc tập chuẩn (`completed`, `blocked`, `failed`, `partial`).
2. **`score_context` (0.0 đến 1.0):**
   * Đạt $1.0$ nếu số lượng file đọc nằm trong ngân sách cho phép của Lane (Tiny $\le 5$, Normal $\le 15$, High-risk $\le 30$).
   * Giảm $0.05$ cho mỗi file đọc vượt định mức (tối thiểu $0.2$).

---

## 4. Lệnh Ghi Trace qua CLI

```powershell
python scripts/harness_cli.py trace `
  --story "US-002" `
  --summary "Optimize user output column format" `
  --outcome "completed" `
  --actions '["Update FINAL_COLUMNS", "Run pytest"]' `
  --files-read '["project/src/export/user_output.py"]' `
  --files-changed '["project/src/export/user_output.py"]'
```
