---
name: dod-gatekeeper
description: Chuyên viên kiểm định chất lượng độc lập, kiểm tra schema v2-lean, rà soát citations nguyên văn exact substring, chống lặp key_points và tự động cải tiến System Prompt (Human-in-the-loop).
---

# DoD Quality Gatekeeper Agent Skill

> **Mục tiêu cốt lõi:** Tuyệt đối không để dữ liệu hallucination hoặc dữ liệu vi phạm chuẩn chạm vào Database và Deliverable Excel. Thực thi nguyên tắc *"No proof = Not done"*.

---

## 1. Định Hướng & Bất Biến Kiểm Định (Quality Invariants)

1. **Rào Cản Schema Hợp Lệ (Schema Valid — Hard Gate)**:
   - **Tầng Gold (`agent-output-v2-lean`)**: Bắt buộc chuẩn phẳng 7 trường cốt lõi (`article_id`, `summary`, `key_points`, `implication`, `sentiment`, `time_sensitivity`, `citations`). Không chấp nhận các trường thừa cũ (`affected_parties`, `impact_area`, `materiality.score`).
   - **Tầng L1 (`l1-entity-output-v1`)**: Bắt buộc đủ `article_id`, `recognized`, `entities`, `categories`, `citations`, `processing_metadata`.
2. **Ràng Buộc Căn Cứ Thực Tế (Grounded Citations)**:
   - Tối thiểu 2 trích dẫn citations / bài.
   - Mỗi `source_span` BẮT BUỘC là **chuỗi con nguyên văn (exact substring)** lấy trực tiếp từ `cleaned_text`.
   - Độ dài mỗi đoạn trích dẫn phải đạt **$\ge 20$ ký tự**. Tuyệt đối không chấp nhận câu trích dẫn bị cắt xén làm thay đổi ngữ cảnh.
3. **Rào Cản Giá Trị Mới & Chống Trùng Lặp (Value-Added Invariant)**:
   - `summary`: Phải là tóm tắt trừu tượng (abstractive), không được copy nguyên văn bài báo.
   - `key_points`: Phải là các gạch đầu dòng diễn giải bằng lời văn phân tích tài chính riêng của Agent, **TUYỆT ĐỐI KHÔNG copy nguyên văn chuỗi citations**.
   - `implication`: Phải là phân tích hàm ý thị trường riêng (>= 40 ký tự), không được dùng câu mẫu sáo rỗng.

---

## 2. Quy Trình Vận Hành & Tự Động Lưu Trữ (Gatekeeper Workflow)

```
[Nhận Kết Quả Từ Subagents] (data/agent_outputs/*.output.json)
       │
       ▼
[Bước 1: Chạy Kiểm Tra Định Lượng Cơ Học] (dod.py / agent_ingest.py)
  ├── Soát Schema: Cú pháp JSON, cấu trúc trường, kiểu dữ liệu
  ├── Soát Grounding: Exact substring matching trên cleaned_text (span in cleaned_text)
  ├── Soát Value-Added: Kiểm tra _norm(kp) in citations_spans
  └── Phân loại: Bài PASS vs Bài FAIL
       │
       ├─► Nếu PASS 100%:
       │     1. Ghi nhận dữ liệu vào bảng agent_outputs / l1_outputs trong SQLite
       │     2. Tự động di dời task packets sang data/agent_tasks/archive/<YYYYMMDD>/
       │     3. Xóa tệp task packet gốc để giải phóng hàng đợi
       │
       └─► Nếu CÓ BÀI FAIL:
             1. Ghi nhận lý do fail chi tiết (ví dụ: 'citation not grounded', 'copy citations')
             2. Kích hoạt VÒNG LẶP TỰ HỌC (Learning Loop)
```

---

## 3. Vòng Lặp Tự Học & Cải Tiến Liên Tục (Continuous Learning Loop)

Khi Gatekeeper phát hiện lỗi của Subagent, Agent không chỉ từ chối bài viết mà còn thực hiện hành động sửa đổi tri thức hệ thống:

```
[Phát hiện vi phạm] 
       │  (Ví dụ: Subagent cắt bớt từ đầu câu trong trích dẫn)
       ▼
[1. Sửa nhanh bản ghi cục bộ] (Fix exact substring để nạp DB ngay)
       │
       ▼
[2. Tự động cập nhật System Prompt trong Skill]
       │  (Cập nhật news-scape-agent-operations với lưu ý nhấn mạnh)
       ▼
[3. Ghi vết vào SESSION-LATEST.md]
       │  (Lưu bài học để các phiên tiếp theo không bị lặp lại)
```

---

## 4. Bộ Công Cụ Cơ Học Thực Thi (Execution Tooling)

```powershell
# 1. Kiểm định và Ingest kết quả L1:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py data/agent_outputs_l1

# 2. Kiểm định và Ingest kết quả Gold v2-lean:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/agent_ingest.py data/agent_outputs
```
