---
name: gold-financial-analyst
description: Chuyên viên bóc tách và phân tích ngữ nghĩa sâu tin tức tài chính, chấm điểm materiality_score, phân loại sentiment và trích dẫn citations chuẩn DoD.
---
# Gold Financial Analyst Skill

> **Mục đích:** Hướng dẫn Subagent Flash thực hiện suy luận tài chính chuyên sâu từ toàn văn bài viết (`cleaned_text`).

## 1. Đầu vào & Kiểm tra Tiền điều kiện (Preconditions)

- **Đầu vào**: Các task packet trong `data/agent_tasks/*.task.json` (bỏ qua thư mục con `l1/`).
- **Precondition Check**:
  - Nếu `input.change_state` ∈ {`SELECTOR_BROKEN`, `TEMPLATE_DRIFT`} $\rightarrow$ Bỏ qua bài viết, không xử lý.
  - Đọc `input.cleaned_text` làm căn cứ trích xuất duy nhất.

## 2. Quy trình Suy luận Ngữ nghĩa Tinh Gọn (Lean Cognitive Workflow)

1. **Tóm tắt Súc tích (`summary`)**:
   - Đoạn văn tóm tắt 2–4 câu văn hoàn chỉnh, rõ ý, kết thúc bằng dấu chấm câu. Tuyệt đối không cắt chuỗi thô giữa từ.
2. **Luận điểm Trọng yếu (`key_points`)**:
   - Mảng 2–4 luận điểm quan trọng nhất của bài viết (ví dụ: `["Doanh thu Q3 tăng 25%...", "Tiến độ bàn giao vượt kế hoạch..."]`).
3. **Hàm ý Thị trường (`implication`)**:
   - Chuỗi phân tích tác động trực tiếp của tin tức đối với doanh thu, lợi nhuận, dòng tiền hoặc giá trị cổ phiếu (tối thiểu 40 ký tự).
4. **Sắc thái (`sentiment`)**:
   - Chọn 1 trong 3 nhãn: `"positive"`, `"negative"`, `"neutral"`.
5. **Độ nhạy Thời gian (`time_sensitivity`)**:
   - Chọn 1 trong: `"urgent"`, `"today"`, `"this_week"`, `"this_month"`, `"archive"`.
6. **Trích dẫn Chứng cứ Grounded (`citations`) — Cổng DoD Tinh Gọn**:
   - Tối thiểu **2 trích dẫn**.
   - Dạng mảng chuỗi trực tiếp: mỗi phần tử **BẮT BUỘC là chuỗi con NGUYÊN VĂN** của `cleaned_text` với độ dài **$\ge 20$ ký tự**.
   - *Không cần sinh `claim` hay `source_offset`*.
7. **Zero-Token Metadata**:
   - *KHÔNG CẦN SINH*: `processing_metadata`, `affected_parties`, `impact_area`, `event_type`, `materiality.score`, `extraction_quality`. Hệ thống sẽ tự động điền khi Ingest.

## 3. Quy chuẩn Output JSON Tinh Gọn (`agent-output-v2-lean`)

Ghi vào `data/agent_outputs/<article_id>.json`:

```json
{
  "article_id": "<article_id>",
  "summary": "Tập đoàn Vingroup công bố khởi công dự án...",
  "key_points": [
    "Quy mô dự án đạt 400 ha với vốn đầu tư...",
    "Dự kiến hoàn thành các hạng mục chính vào tháng 8/2027"
  ],
  "implication": "Công trình biểu tượng thể thao quy mô lớn thúc đẩy mạnh mẽ giá trị thương hiệu và mở ra dư địa khai thác thương mại dài hạn cho hệ sinh thái.",
  "sentiment": "positive",
  "time_sensitivity": "today",
  "citations": [
    "VinFast - Trống Đồng là sân vận động có mái che đóng mở tự động quy mô nhất hành tinh",
    "dự kiến hoàn thành các hạng mục chính vào tháng 8 năm 2027; sẵn sàng đăng cai"
  ]
}
```

## 4. Chế độ Gom Lô Siêu Tốc (Consolidated Batch Mode)

Khi nhận file task dạng gom lô `data/agent_tasks/batch_XX.task.json`:
1. **Một lần đọc duy nhất**: Gọi `view_file` đọc toàn bộ file `batch_XX.task.json`.
2. **Tận dụng `l1_entities`**: Mỗi task trong mảng `tasks[]` đã được L1 tiếp sức sẵn các mã cổ phiếu liên quan (`l1_entities`). Subagent tập trung ngay vào suy luận tác động doanh thu, dòng tiền, thị giá mà không cần dò lại từ đầu.
3. **Một lần ghi duy nhất**: Ghi toàn bộ kết quả của cả lô vào `data/agent_outputs/batch_XX.output.json` dưới dạng mảng JSON các object theo schema `v2-lean`:
```json
[
  {
    "article_id": "<article_id_1>",
    "summary": "...",
    "key_points": ["...", "..."],
    "implication": "...",
    "sentiment": "positive",
    "time_sensitivity": "today",
    "citations": ["trích dẫn nguyên văn 1...", "trích dẫn nguyên văn 2..."]
  },
  {
    "article_id": "<article_id_2>",
    "summary": "...",
    "key_points": ["...", "..."],
    "implication": "...",
    "sentiment": "neutral",
    "time_sensitivity": "this_week",
    "citations": ["trích dẫn nguyên văn 1...", "trích dẫn nguyên văn 2..."]
  }
]
> Tiết kiệm ~60% output tokens so với v1, giảm 90% số lần gọi công cụ I/O.

---

## 5. Bảng Tra Cứu Định Mức Token & Hạn Mức Quota (Cheatsheet)

Khi lập kế hoạch hoặc nhận diện khối lượng công việc, sử dụng bảng định mức chuẩn sau:

| Quy mô tác vụ | Số lượng bài | Kích thước Input | Input Tokens | Output Tokens | Tổng Token ước tính | Thời gian (1 Agent) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Mini-Batch (v2-lean)** | 5 bài | ~15.5 KB | ~3.800 | ~1.800 | **~5.600 tokens** | ~1.8 phút |
| **Block nhỏ (v2-lean)** | 20 bài | ~62.0 KB | ~15.200 | ~7.200 | **~22.400 tokens** | ~7 phút |
| **Wave 1 (Ưu tiên)** | 150 bài | ~465 KB | ~114.000 | ~54.000 | **~168.000 tokens** | ~55 phút |
| **Một ngày đầy đủ** | ~700 bài | ~2.1 MB | ~532.000 | ~252.000 | **~784.000 tokens** | ~4.2 giờ |

> [!TIP]
> **Quy tắc an toàn TPM**: Chạy tối đa 3–5 Subagents đồng thời. Mỗi Subagent cách nhau một khoảng nghỉ ngắn hoặc xử lý theo lô 5 bài để đảm bảo tốc độ sinh token nằm dưới ngưỡng 4.000.000 TPM của mô hình Flash.

