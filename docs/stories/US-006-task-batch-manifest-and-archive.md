# US-006: Task Batch Manifest & Archive Lifecycle Management

## 1. Bối cảnh & Mục tiêu (Problem & Goal)
- Khi xuất task packet cho Subagents theo lô (batch 20, 50, 100 tin), các file .task.json được ghi chung vào thư mục phẳng data/agent_tasks/.
- Người dùng và Subagents không thể phân biệt được bài nào thuộc lô nào, không có file chỉ mục tóm tắt (manifest) và các task cũ không được lưu trữ dọn dẹp sau khi ingest.
- **Mục tiêu**:
  1. Tự động sinh atch_manifest.json trong data/agent_tasks/ (và data/agent_tasks/l1/).
  2. In bảng tóm tắt danh sách tin trên terminal ngay khi chạy export.
  3. Tự động chuyển các task đã đạt chuẩn DoD sang data/agent_tasks/archive/<date>/ sau khi ingest, giữ bể việc active pool luôn sạch sẽ.

## 2. Tiêu chí Chấp nhận (Acceptance Criteria)
- [x] Xuất hiện file data/agent_tasks/batch_manifest.json chứa atch_id, created_at, atch_size, order, và mảng rticles chứa danh sách chi tiết các bài trong lô.
- [x] Lệnh export in ra màn hình bảng tóm tắt trực quan (STT, Thời gian, Nguồn tin, Tiêu đề).
- [x] Khi Ingest hoàn thành (dod_pass=1), các file .task.json tương ứng được di chuyển an toàn vào data/agent_tasks/archive/<date>/.
- [x] Unit test kiểm chứng toàn bộ quy trình sinh manifest, in bảng và lưu trữ archive đạt 100% pass.
