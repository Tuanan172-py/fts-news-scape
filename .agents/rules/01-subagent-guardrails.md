---
trigger: always_on
---
# 01 — Subagent Guardrails & Authority Boundary

Ranh giới quyền hạn bất biến cho MỌI Subagent trong hệ thống News-Scape trên nền tảng Antigravity 2.0:

## 1. Quyền I/O duy nhất (Strict I/O Boundary)
- **Subagent L1**: CHỈ đọc `data/agent_tasks/l1/*.task.json` và CHỈ ghi kết quả vào `data/agent_outputs_l1/<article_id>.json`.
- **Subagent Gold**: CHỈ đọc `data/agent_tasks/*.task.json` (bỏ qua thư mục con `l1/`) và CHỈ ghi kết quả vào `data/agent_outputs/<article_id>.json`.
- Không được phép ghi đè hay tạo file ngoài 2 thư mục đích trên.

## 2. Các hành động CẤM TUYỆT ĐỐI (Strict Prohibitions)
- **KHÔNG** sửa đổi database SQLite (`data/monocle.db`).
- **KHÔNG** chỉnh sửa mã nguồn hệ thống (`src/**`).
- **KHÔNG** chỉnh sửa hoặc xóa các file task packets đầu vào (`data/agent_tasks/**`).
- **KHÔNG** tự ý chạy các script ingest (`l1_ingest.py`, `agent_ingest.py`, `run_user_workflow.py`). Đây là thẩm quyền của Master Orchestrator.

## 3. Ràng buộc Grounding & Bằng chứng (Grounded Citations)
- **Chuỗi con nguyên văn**: Mọi `source_span` trong mảng `citations[]` BẮT BUỘC phải là chuỗi con nguyên văn (exact substring) lấy từ `cleaned_text` (Gold) hoặc `title` (L1).
- **Độ dài tối thiểu**: Mỗi `source_span` của Gold Extraction phải có độ dài **$\ge 20$ ký tự**.
- **Không suy diễn ngoài văn bản**: Tuyệt đối không bịa đặt số liệu, mã cổ phiếu hoặc sự kiện không xuất hiện trong bài viết.

## 4. Ràng buộc Schema Enum & Danh tính Người dùng (Enums & User Identity)
- **Event Type Enum (Gold)**: `event_type` trong Gold Output chỉ được phép là 1 trong các giá trị: `['earnings', 'acquisition', 'regulatory', 'lawsuit', 'partnership', 'financial_move', 'macro', 'other']`. Tuyệt đối không dùng các giá trị ngoài schema (như `operations`).
- **Entity Method Enum (L1)**: `method` trong L1 Output chỉ được phép là 1 trong: `['exact_code', 'alias', 'semantic']`.
- **Zero Hallucination User Manifest**: Khi phân tích hoặc báo cáo phân phối tin, chỉ được phép tham chiếu các người dùng thực tế được định nghĩa trong `config/entities/users/` và `users/input/manifest.yaml` (hiện tại: `AnPT`). Tuyệt đối không bịa đặt người dùng hư cấu.

