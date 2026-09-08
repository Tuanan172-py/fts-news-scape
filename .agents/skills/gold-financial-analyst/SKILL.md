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

## 2. Quy trình Suy luận Ngữ nghĩa (Cognitive Workflow)

1. **Tóm tắt Súc tích (`summary`)**:
   - `abstractive`: Đoạn văn tóm tắt 2–4 câu văn hoàn chỉnh, rõ ý, kết thúc bằng dấu chấm câu. Tuyệt đối không cắt chuỗi thô giữa từ.
   - `key_points`: 2–4 luận điểm quan trọng nhất của bài viết.
2. **Hàm ý Thị trường (`implication`)**:
   - `text`: Phân tích tác động trực tiếp của tin tức đối với doanh thu, lợi nhuận, dòng tiền hoặc giá trị cổ phiếu.
   - `affected_parties`: Danh sách các bên bị ảnh hưởng (ví dụ: `["Vinhomes", "cổ đông VHM", "ngành bất động sản"]`).
   - `impact_area`: Chọn một trong các enum: `market`, `regulatory`, `sentiment`, `supply_chain`, `geopolitical`, `other`.
3. **Đánh giá Trọng yếu (`materiality`)**:
   - `score`: Số thực từ `0.1` đến `1.0` (tuân thủ quy tắc trong `.agents/rules/02-financial-domain-rules.md`).
   - `time_sensitivity`: `urgent`, `today`, `this_week`, `this_month`, `archive`.
4. **Sắc thái (`sentiment`)**:
   - `polarity`: `positive`, `negative`, `neutral`.
   - `overall`: Điểm số từ `-1.0` (rất tiêu cực) đến `1.0` (rất tích cực).
5. **Trích dẫn Chứng cứ Grounded (`citations`) — Cổng DoD**:
   - Tối thiểu **2 trích dẫn**.
   - Mỗi `source_span` **BẮT BUỘC là chuỗi con NGUYÊN VĂN** của `cleaned_text` với độ dài **$\ge 20$ ký tự**.
   - `source_offset`: Vị trí bắt đầu của chuỗi con trong `cleaned_text`.
6. **Phân loại Sự kiện (`event_type`) — Ràng buộc Schema Enum**:
   - `event_type` CHỈ ĐƯỢC PHÉP là 1 trong: `earnings`, `acquisition`, `regulatory`, `lawsuit`, `partnership`, `financial_move`, `macro`, `other`. Tuyệt đối không dùng các giá trị ngoài schema.

## 3. Quy chuẩn Output JSON

Ghi vào `data/agent_outputs/<article_id>.json`:

```json
{
  "output_schema_version": "1.0",
  "article_id": "<article_id>",
  "summary": {
    "abstractive": "...",
    "key_points": ["...", "..."],
    "key_quotes": []
  },
  "implication": {
    "text": "...",
    "affected_parties": ["..."],
    "impact_area": "market"
  },
  "materiality": {
    "score": 0.85,
    "time_sensitivity": "today"
  },
  "confidence": 0.9,
  "sentiment": {
    "overall": 0.8,
    "polarity": "positive"
  },
  "event_type": "earnings",
  "extraction_quality": "high",
  "citations": [
    {
      "claim": "...",
      "source_span": "...",
      "source_offset": 120
    },
    {
      "claim": "...",
      "source_span": "...",
      "source_offset": 340
    }
  ],
  "processing_metadata": {
    "agent_provider": "antigravity",
    "model_used": "flash",
    "timestamp": "<ISO_NOW_VN>",
    "schema_version": "1.0"
  }
}
```

## 4. Chế độ Gom Lô Siêu Tốc (Consolidated Batch Mode)

Khi nhận file task dạng gom lô `data/agent_tasks/batch_XX.task.json`:
1. **Một lần đọc duy nhất**: Gọi `view_file` đọc toàn bộ file `batch_XX.task.json`.
2. **Tận dụng `l1_entities`**: Mỗi task trong mảng `tasks[]` đã được L1 tiếp sức sẵn các mã cổ phiếu liên quan (`l1_entities`). Subagent tập trung ngay vào suy luận tác động doanh thu, dòng tiền, thị giá mà không cần dò lại từ đầu.
3. **Một lần ghi duy nhất**: Ghi toàn bộ kết quả của cả lô vào `data/agent_outputs/batch_XX.output.json` dưới dạng mảng JSON các object theo schema trên:
```json
[
  {
    "output_schema_version": "1.0",
    "article_id": "<article_id_1>",
    ...
  },
  {
    "output_schema_version": "1.0",
    "article_id": "<article_id_2>",
    ...
  }
]
```
> Giảm 90% số lần gọi công cụ I/O, tối ưu tốc độ và triệt tiêu context bloat.
