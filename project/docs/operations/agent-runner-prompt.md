# Hanoff cho AGENT CÓ quyền thực thi với file FILE (tự đọc packet, tự ghi output)

Cập nhật: 2026-08-20 · Đối tượng: agent có tool đọc/ghi file cục bộ (Claude Code, Cursor, MCP filesystem…).
Khác [agent-prompting-guide](agent-prompting-guide.md) (kiểu copy-paste): ở đây agent **TỰ GHI FILE** —
không còn bước con người copy output. Bổ trợ [daily-runbook-per-user §3](daily-runbook-per-user.md).

**Định nghĩa HOÀN THÀNH:** agent **phải tự ghi ra** file output JSON — chưa ghi file thì CHƯA xong.
Agent ĐƯỢC ghi **đúng một loại file** = output JSON vào thư mục ingest. VẪN CẤM: chạy `*_ingest.py`,
truy vấn/ghi DB, chạy script khác, sửa packet đầu vào, đề xuất "bước tiếp theo".

Chỗ vận hành trong chu kỳ: chạy `run_daily.ps1 -Mode emit` (phát packet) → **dán phiếu này cho agent**
→ `run_daily.ps1 -Mode ingest` (nạp + ghi <date>.xlsx). Agent thay cho khúc giữa thủ công.

---

## Bảng đường dẫn (agent PHẢI theo đúng)

| Lớp | ĐỌC packet (input) | Chỉ dẫn đầy đủ | GHI output (mỗi bài 1 file) | Schema |
|-----|--------------------|----------------|------------------------------|--------|
| **L1** | `data/agent_tasks/l1/*.task.json` | `schemas/l1-entity-instructions-v1.md` | `data/agent_outputs_l1/<article_id>.json` | `l1-entity-output-v1` |
| **Bóc tách** | `data/agent_tasks/*.task.json` (KHÔNG đệ quy — bỏ thư mục `l1/`) | `schemas/agent-instructions-v1.md` | `data/agent_outputs/<article_id>.json` | `agent-output-v1` |

- Tên file output = **đúng `article_id` trong packet** + `.json`. Ghi đè nếu đã có (idempotent).
- `<article_id>` lấy từ trường `article_id` của packet, KHÔNG tự đặt.

---

## PROMPT DÁN CHO AGENT (dùng chung cả 2 lớp)

> **NHIỆM VỤ.** Bạn là bộ xử lý tin chứng khoán VN có quyền đọc/ghi file trong thư mục dự án.
> Xử lý **cả 2 hàng đợi** dưới đây. Với MỖI packet: đọc → sinh JSON đúng schema → **tự ghi file output**
> vào đúng thư mục. Không hỏi lại, làm hết rồi báo cáo số file đã ghi.
>
> **BƯỚC 0 — XÁC ĐỊNH THƯ MỤC (bắt buộc, làm TRƯỚC).** Thư mục làm việc phải là thư mục `project/`
> (chứa `data/`, `scripts/`, `schemas/`). Kiểm tra `data/agent_tasks/l1/` có tồn tại và có `*.task.json`.
> Các đường dẫn dưới đây là **tương đối với `project/`**; packet KHÔNG nằm ở thư mục gốc repo mà ở
> `project/data/agent_tasks/`. Nếu không thấy thư mục đó → bạn đang sai cwd, chuyển vào `project/` rồi thử lại.
>
> **GUARD chống báo xong giả.** Nếu đếm được **0 packet**, TUYỆT ĐỐI KHÔNG kết luận "hoàn thành".
> Thay vào đó IN RA: thư mục hiện tại (cwd) + danh sách bạn thấy trong `data/agent_tasks/`, rồi DỪNG và
> hỏi. "Hoàn thành" chỉ đúng khi đã GHI được file output — KHÔNG phải khi "không tìm thấy việc".
>
> **HÀNG ĐỢI 1 — L1 (nhận diện thực thể từ TIÊU ĐỀ).**
> Đọc mọi `data/agent_tasks/l1/*.task.json`. Chỉ dùng `input.title` (không có body).
> Với mỗi file:
> 1. Đọc `input.code_first` (kết quả máy dò trước): xác nhận đúng, bỏ sai, bổ sung cái bị sót
>    (viết tắt, thương hiệu, thiếu/sai dấu).
> 2. Mỗi thực thể: `surface` = chuỗi con NGUYÊN VĂN của `title`. `method`= exact_code/alias/semantic.
>    Có `entity_id` trong `code_first` → dùng lại, `in_list=true`. Bổ sung mà không chắc `entity_id`
>    → `entity_id=null`, `in_list=false`, đưa `surface` vào `unlisted_candidates`.
> 3. Chấm `categories` cho 5 nhóm (ticker_company, etf_fund, index, exchange, industry_sector):
>    `done` (có ≥1 entity in_list=true đúng nhóm) | `none` (không nhắc) | `out_of_list` (nhắc nhưng ngoài DS).
> 4. `citations`: ≥1 nếu `recognized=true`, mỗi `source_span` là chuỗi con của `title`.
> 5. `recognized = (có ≥1 entity)`.
> Ghi kết quả (đúng format `schemas/l1-entity-output-v1.schema.json`) ra
> `data/agent_outputs_l1/<article_id>.json`.
>
> **HÀNG ĐỢI 2 — BÓC TÁCH (phân tích BODY).**
> Đọc mọi `data/agent_tasks/*.task.json` (KHÔNG đệ quy, bỏ qua `l1/`). Phân tích `input.cleaned_text`.
> Nếu `input.change_state` ∈ {SELECTOR_BROKEN, TEMPLATE_DRIFT} → bỏ qua bài đó (đã bị giữ ở nguồn).
> Với mỗi file, theo thứ tự:
> 1. `summary.abstractive` (2-4 câu, trung thực, không suy diễn) + `summary.key_points` (2-5 ý).
> 2. `implication.text` ("so-what" cho thị trường) + `impact_area`
>    ∈ {market, regulatory, sentiment, supply_chain, geopolitical, other}.
> 3. `materiality.score` (0..1) + `time_sensitivity` ∈ {urgent, today, this_week, this_month, archive}.
> 4. (tuỳ chọn) `sentiment`, `event_type`, `entities.companies`.
> 5. `citations` ≥ **2**; mỗi `source_span` là chuỗi con NGUYÊN VĂN của `cleaned_text` **và ≥20 ký tự**;
>    kèm `claim`. Đặt `extraction_quality` ∈ {high, medium}.
> Ghi kết quả (đúng `schemas/agent-output-v1.schema.json`) ra
> `data/agent_outputs/<article_id>.json`.
>
> **CHUNG CHO CẢ 2.** Giữ nguyên `article_id` từ packet → làm tên file. Điền `processing_metadata`
> (`agent_provider`, `model_used`, `timestamp` ISO +07:00). Nội dung file = **DUY NHẤT một JSON object**
> hợp lệ, không markdown, không chú thích, không văn bản thừa.
>
> **RÀNG BUỘC CỨNG.** Bạn CHỈ được ghi các file `.json` output nói trên. TUYỆT ĐỐI KHÔNG: chạy
> `l1_ingest.py`/`agent_ingest.py`/bất kỳ script nào, truy vấn/sửa DB (`data/monocle.db`), sửa packet
> đầu vào, ghi ra thư mục khác, hay đề xuất "bước tiếp theo". Không bịa dữ liệu ngoài `input`.
>
> **BÁO CÁO KHI XONG.** In: số packet mỗi hàng đợi, số file đã ghi mỗi thư mục, và danh sách
> `article_id` (nếu có) mà bạn bỏ qua kèm lý do (vd change_state bị giữ). KHÔNG làm gì thêm.

---

## Tự kiểm trước khi coi là XONG (DoD — trùng với cái `*_ingest.py` chấm)

**L1** (`data/agent_outputs_l1/<id>.json`):
- [ ] Hợp `l1-entity-output-v1.schema.json`; đủ khoá bắt buộc.
- [ ] Mỗi `entities[].surface` ⊂ `title`; mỗi `citations[].source_span` ⊂ `title`.
- [ ] `recognized=true` ⇒ `entities≥1` và `citations≥1`. `recognized=false` ⇒ `entities=[]` và không nhóm nào `done`.
- [ ] `categories.<nhóm>='done'` ⇒ có ≥1 entity `in_list=true` đúng nhóm.
- [ ] `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp`.

**Bóc tách** (`data/agent_outputs/<id>.json`):
- [ ] Hợp `agent-output-v1.schema.json`.
- [ ] **≥2 citations**; mỗi `source_span` ⊂ `cleaned_text` và **≥20 ký tự**.
- [ ] `extraction_quality` ∈ {high, medium}.
- [ ] `processing_metadata` đủ 3 trường.

Sau khi agent ghi xong, bạn (người vận hành) chạy nạp — agent KHÔNG tự chạy:
```powershell
.venv\Scripts\python.exe scripts\l1_ingest.py    data/agent_outputs_l1
.venv\Scripts\python.exe scripts\agent_ingest.py data/agent_outputs
.venv\Scripts\python.exe scripts\write_user_output.py --date today
# hoặc gộp: .\scripts\run_daily.ps1 -Mode ingest
```
Bài trượt DoD → `dod_pass=0`+`dod_reasons`; đọc lý do, bảo agent sửa đúng bài đó, ghi đè, nạp lại.

---

## Mẫu đối chiếu
- L1: `schemas/samples/l1-entity-output-sample.json`
- Bóc tách: `schemas/samples/agent-output-sample.json`

## Câu hỏi mở
- Nếu agent bổ sung nhiều entity mới cần `entity_id` chính xác → cấp thêm `data/entities/entities.json`
  cho agent đọc (nó có tool file), hoặc chấp nhận `in_list=false` + `unlisted_candidates` (an toàn hơn).
