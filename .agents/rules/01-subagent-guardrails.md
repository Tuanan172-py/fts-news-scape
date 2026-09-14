---
trigger: always_on
---
# 01 — Subagent Guardrails & Authority Boundary

Ranh giới quyền hạn bất biến cho MỌI Subagent trong hệ thống News-Scape trên nền tảng Antigravity 2.0:

## 1. Quyền I/O duy nhất (Strict I/O Boundary)
- **Subagent L1**: CHỈ đọc `data/agent_tasks/l1/*.task.json` và CHỈ ghi kết quả vào `data/agent_outputs_l1/<article_id>.json` hoặc `data/agent_outputs_l1/l1_batch_XX.output.json`.
- **Subagent Gold**: CHỈ đọc `data/agent_tasks/*.task.json` (bỏ qua thư mục con `l1/`) và CHỈ ghi kết quả vào `data/agent_outputs/<article_id>.json` hoặc `data/agent_outputs/batch_XX.output.json`.
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

## 5. Nguyên tắc 2-I/O Tinh Gọn (Strict 2-I/O Boundary & Anti-Token Burn)
- **Quy tắc 1 đọc — 1 ghi**: Subagent khi nhận nhiệm vụ xử lý lô gom BẮT BUỘC chỉ gọi tối đa **1 lần** `view_file` để nạp toàn bộ task packet đầu vào và **1 lần** `write_to_file` để lưu mảng JSON đầu ra.
- **CẤM TUYỆT ĐỐI Discovery Tool Loops**: Không được phép gọi các công cụ tìm kiếm (`grep_search`, `find_by_name`, `list_dir`) để quét qua các file từ điển ngoài (`entities.json` 1.5 MB, catalog, codebase). Mọi tri thức phân loại ngữ nghĩa đã được tích hợp sẵn trong prompt và Ontology Skill.

## 6. Ràng buộc Entity Type & Registry ID (L1 Schema Invariant)
- **12 Entity Types chuẩn**: Thuộc tính `type` trong mọi thực thể L1 BẮT BUỘC phải thuộc 1 trong 12 giá trị Enum: `['TICKER', 'ETF', 'SECURITY_OTHER', 'INDEX', 'EXCHANGE', 'INDUSTRY_GICS1', 'INDUSTRY_GICS2', 'INDUSTRY_GICS3', 'MACRO_GEO', 'MACRO_THEME', 'ASSET_CLASS', 'INSTITUTION', 'UNKNOWN']`. Tuyệt đối KHÔNG sử dụng tên loại chung chung như `INDUSTRY`.
- **Quy tắc Entity Catalog In-List**:
  - Chỉ gán `in_list: true` và điền `entity_id` (kèm tiền tố chuẩn như `TICKER:`, `MACRO_THEME:`, `IND_GICS1/2/3:`) nếu thực thể tồn tại chính thức trong danh mục hệ thống.
  - Các thực thể nhận diện được ngoài danh mục (quốc gia ngoài Top 8, tổ chức/thương hiệu quốc tế hoặc chưa niêm yết): BẮT BUỘC gán `in_list: false`, `entity_id: null` và đưa chuỗi tên vào danh sách `unlisted_candidates`.
