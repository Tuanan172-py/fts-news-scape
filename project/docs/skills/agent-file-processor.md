# Skill: VN Stock News Packet Processor (`agent-file-processor`)

> **Mục đích:** Xử lý tự động cả 2 hàng đợi task packets (L1 Entity Recognition từ Title & Bóc tách Body từ Cleaned Text), tự động kiểm tra Definition-of-Done (DoD) và ghi file output JSON vào thư mục ingest.

---

## 1. Trigger & CWD
- **Thư mục làm việc (CWD):** `project/` (phải nhìn thấy `data/agent_tasks/`, `schemas/`, `scripts/`).
- **Nhiệm vụ:** Tự động đọc tất cả `.task.json`, sinh JSON hợp lệ theo schema, tự ghi đè `.json` vào thư mục output tương ứng.

---

## 2. Guardrails (Ràng buộc cứng)
1. **Zero-packet Guard:** Nếu đếm được 0 packet ở cả 2 hàng đợi → DỪNG, báo cáo CWD hiện tại và KHÔNG kết luận "hoàn thành".
2. **Authority Boundary:** 
   - CHỈ ghi file `.json` vào `data/agent_outputs_l1/` và `data/agent_outputs/`.
   - TUYỆT ĐỐI KHÔNG: chạy `l1_ingest.py`, `agent_ingest.py`, truy vấn/sửa DB (`data/monocle.db`), sửa packet đầu vào.
   - Không bịa dữ liệu ngoài `input`.

---

## 3. Thực thi nhanh qua Native Engine (Khuyến nghị)
Agent có thể trực tiếp thực thi Native CLI Engine để xử lý hàng loạt packet một cách chuẩn hóa, chống cắt cụt từ và tự động chấm DoD:
```powershell
python scripts/agent_process_packets.py --provider antigravity --model gemini-3.7-flash
```

---

## 4. Quy trình thực thi 2 tầng chi tiết

### Tầng 1: Hàng đợi L1 (Nhận diện thực thể từ Tiêu đề)
- **Đầu vào (Input):** `data/agent_tasks/l1/*.task.json`
- **Chỉ dẫn & Schema:** `schemas/l1-entity-instructions-v1.md` · `schemas/l1-entity-output-v1.schema.json`
- **Đầu ra (Output):** `data/agent_outputs_l1/<article_id>.json`
- **Quy tắc xử lý:**
  1. Đọc `input.title` và `input.code_first` để tra soát.
  2. Khớp mã in hoa 3 ký tự (loại trừ `CODE_STOPLIST`), alias tiếng Việt, thương hiệu doanh nghiệp, ngành GICS và chỉ số (`VNINDEX`, `VN30`...).
  3. Mọi `surface` và `citations[].source_span` **bắt buộc là chuỗi con nguyên văn của `title`**.
  4. Tự chấm checklist 5 nhóm `categories` (`ticker_company`, `etf_fund`, `index`, `exchange`, `industry_sector`) với giá trị `done` | `none` | `out_of_list`.
  5. Nếu `recognized=true` ⇒ `entities >= 1` và `citations >= 1`.
  6. Điền `processing_metadata` (`agent_provider`, `model_used`, `timestamp` ISO +07:00).

### Tầng 2: Hàng đợi Bóc tách (Phân tích Body)
- **Đầu vào (Input):** `data/agent_tasks/*.task.json` (KHÔNG đệ quy — bỏ qua thư mục con `l1/`)
- **Chỉ dẫn & Schema:** `schemas/agent-instructions-v1.md` · `schemas/agent-output-v1.schema.json`
- **Đầu ra (Output):** `data/agent_outputs/<article_id>.json`
- **Quy tắc xử lý:**
  1. Precondition: Nếu `input.change_state` ∈ {`SELECTOR_BROKEN`, `TEMPLATE_DRIFT`} → Bỏ qua bài viết.
  2. Sinh `summary.abstractive` (2-4 câu văn hoàn chỉnh, kết thúc bằng dấu chấm câu, KHÔNG cắt chuỗi thô giữa từ) và `summary.key_points` (2-5 ý hoàn chỉnh).
  3. Xác định `implication` (so-what thị trường), `impact_area`, `materiality.score` (0..1), `time_sensitivity`.
  4. **Grounding:** Tối thiểu **2 citations**, mỗi `source_span` là chuỗi con nguyên văn của `cleaned_text` và **độ dài ≥ 20 ký tự**.
  5. `extraction_quality` ∈ {`high`, `medium`}.
  6. Điền `processing_metadata` đầy đủ 3 trường.

---

## 4. Tự kiểm tra Definition-of-Done (DoD)
Trước khi coi là xong một bài, output phải thỏa mãn:
- Khớp 100% JSON Schema tương ứng.
- Toàn bộ trích dẫn (citations/surfaces) nằm trong văn bản nguồn gốc.
- Tính nhất quán giữa các cờ trạng thái (`recognized` vs `entities`/`categories`).

---

## 5. Mẫu Báo Cáo Đầu Ra Chuẩn
Sau khi xử lý xong, Agent in đúng định dạng 3 dòng:
```text
- L1: [N] packet -> [N] output đã ghi (data/agent_outputs_l1/)
- Bóc tách: [N] packet -> [N] output đã ghi (data/agent_outputs/)
- Bỏ qua: [Danh sách article_id + lý do, hoặc "Không có"]
```
