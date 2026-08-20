# Vận hành — Hướng dẫn PROMPT & nghiệm thu lớp AGENT

Cập nhật: 2026-08-19 · Đối tượng: người điều khiển agent (provider bất kỳ) xử lý 2 handoff:
**L1 nhận diện entity** và **bóc tách** (summary/implication/materiality…).

Nguyên tắc: **agent-agnostic** — runtime chỉ *phát packet* + *nạp & chấm DoD*, KHÔNG nhúng LLM.
Bạn tự soạn prompt từ: **file chỉ dẫn** (system) + **task-packet** (input) + **schema output**.
Tham chiếu: [09-agent-io-contract](../design/09-agent-io-contract.md),
[13-per-user-output-workflow §14](../design/13-per-user-output-workflow.md).

---

## 1. Agent cần ĐỌC gì để hiểu context

| Lớp | Chỉ dẫn (SYSTEM) | Packet (INPUT) | Schema output (ép JSON) | Tra cứu |
|-----|------------------|----------------|-------------------------|---------|
| **L1** | `schemas/l1-entity-instructions-v1.md` | `data/agent_tasks/l1/<id>.task.json` → `input.title`, `input.code_first` | `schemas/l1-entity-output-v1.schema.json` | `data/entities/entities.json` + `taxonomy.json` (lấy `entity_id`) |
| **Bóc tách** | `schemas/agent-instructions-v1.md` | `data/agent_tasks/<id>.task.json` → `input.cleaned_text` (+ `raw_sha256`, `change_state`) | `schemas/agent-output-v1.schema.json` | — |

Mẫu output hợp lệ để đối chiếu: `schemas/samples/l1-entity-output-sample.json`,
`schemas/samples/agent-output-sample.json`. **Đọc mẫu trước khi soạn prompt.**

---

## 2. Prompt mồi (paste vào LLM)

Cấu trúc chung cho MỌI provider:
```
[SYSTEM]  = nội dung file *-instructions-v1.md (nguyên văn hoặc rút gọn §system prompt)
[USER]    = "Đây là task-packet. Trả về DUY NHẤT một JSON hợp lệ theo schema <tên>.
             Không giải thích, không markdown."  +  <dán JSON packet>
[SCHEMA]  = ép cứng bằng cơ chế của provider (xem §2.3)
```

### 2.1 L1 — system prompt mồi (rút gọn, đủ dùng)
> Bạn là bộ nhận diện thực thể lớp 1 cho tin chứng khoán VN. Cho MỘT tiêu đề, tìm mọi thực thể:
> mã CP, tên DN, ETF/quỹ, chỉ số, sàn, ngành. **Chỉ dựa vào tiêu đề** (không suy diễn ngoài văn bản).
> `input.code_first` là kết quả code-first để bạn **xác nhận / sửa / bổ sung**. Ánh xạ mỗi thực thể
> vào danh sách chuẩn để lấy `entity_id`; ngoài danh sách → `entity_id=null`, `in_list=false`,
> thêm `unlisted_candidates`. **Mọi `surface` và `citations[].source_span` PHẢI là chuỗi con nguyên văn
> của tiêu đề.** Tự chấm `categories` cho 5 nhóm. Trả JSON đúng `l1-entity-output-v1`.

### 2.2 Bóc tách — system prompt mồi (rút gọn)
> Bạn bóc tách tin chứng khoán VN từ `input.cleaned_text`. Thứ tự: (1) `summary.abstractive` +
> `key_points` — trung thực, không bịa; (2) `implication.text` + `impact_area` — "so-what" cho thị trường;
> (3) `materiality.score` (0..1) + `time_sensitivity`; (4) tuỳ chọn `sentiment`, `event_type`.
> **Gắn ≥2 `citations`, mỗi `source_span` PHẢI là chuỗi con của `cleaned_text` và dài ≥20 ký tự.**
> Đặt `extraction_quality ∈ {high, medium}`. Điền `processing_metadata` (provider/model/timestamp).
> Trả JSON đúng `agent-output-v1`.

### 2.3 Ép schema theo provider (bắt buộc để qua DoD)
- **Anthropic**: tool `input_schema` = nội dung file schema → buộc model gọi tool.
- **OpenAI**: `response_format={"type":"json_schema","json_schema":{…}}`.
- **Gemini**: `responseSchema` + `responseMimeType="application/json"`.
- **local/MCP**: tự validate lại bằng `schemas/<name>.schema.json` trước khi ghi file.

Output ghi thành `<article_id>.json` vào thư mục ingest (`data/agent_outputs_l1/` hoặc `data/agent_outputs/`).

### 2.4 KHOÁ VAI TRÒ — agent làm ĐÚNG phần của agent (dán vào SYSTEM)
Agent **đọc packet của mình và TỰ GHI file output** `<article_id>.json` vào thư mục ingest đúng lớp.
**Định nghĩa HOÀN THÀNH = file output đã được ghi ra** (không phải "đã trả JSON trong chat"). Ngoài việc
đọc packet + ghi output, agent KHÔNG lấn sang phần script cục bộ.
> RÀNG BUỘC CỨNG: Bạn đọc packet, sinh JSON đúng schema, rồi **TỰ GHI** ra `<article_id>.json` trong
> thư mục output đúng lớp (`data/agent_outputs_l1/` cho L1, `data/agent_outputs/` cho bóc tách). Chỉ
> khi file đã ghi mới coi là xong bài đó. **KHÔNG** chạy `*_ingest.py`/bất kỳ script nào khác, **KHÔNG**
> truy vấn/sửa DB (`data/monocle.db`), **KHÔNG** sửa packet đầu vào, **KHÔNG** ghi ra thư mục khác,
> **KHÔNG** đề xuất "bước tiếp theo". Nội dung file = DUY NHẤT một JSON hợp lệ (không markdown, không
> giải thích). Không bịa dữ liệu ngoài `input`; thiếu bằng chứng → `recognized=false` (L1) hoặc để
> trường tuỳ chọn trống hợp lệ. Giữ nguyên `article_id` từ packet (làm tên file).

Ranh giới trách nhiệm (agent làm cột giữa; CẤM lấn cột phải):

| Việc | AGENT | Script cục bộ của bạn |
|------|-------|------------------------|
| Đọc packet từ đĩa (`data/agent_tasks*/`) | ✅ | — |
| Sinh JSON đúng schema/DoD | ✅ | — |
| **Ghi `<id>.json` vào `data/agent_outputs*/`** | ✅ | — |
| `l1_ingest.py` / `agent_ingest.py` (validate + DoD → `dod_pass`) | — | ✅ |
| Truy vấn/sửa DB, orchestrate, cron, ghi final.csv | — | ✅ |

Nghiệm thu **KHÔNG do agent tự tuyên bố**: agent chỉ ghi file; `*_ingest.py` mới chấm DoD và đặt
`dod_pass`. "Xong bài" = file ghi ra **và** `dod_pass=1` sau ingest.

Ba cách cấp khả năng ghi file cho agent:
- **(A) Agent có tool file** (Claude Code, Cursor, MCP filesystem…) — agent tự đọc/ghi trực tiếp.
  Dùng phiếu giao việc [agent-runner-prompt.md](agent-runner-prompt.md). **Khuyến nghị.**
- **(B) Adapter cục bộ** `scripts/agent_run.py` (chạy trên máy bạn, gọi API) — "agent" là 1 lời gọi
  API trong hàm; hàm ghi file hộ. Xem [13 §14.4](../design/13-per-user-output-workflow.md).
- **(C) Copy-paste** (chỉ khi agent KHÔNG có tool file): bạn là dây chuyền vận chuyển — dán packet,
  lưu JSON trả về thành file. Kết quả cuối vẫn là file `<id>.json` trong thư mục output.

---

## 3. Thứ tự công việc agent phải làm

**L1**: đọc `code_first` → liệt kê ứng viên (surface = chuỗi con của title) → ánh xạ `entities.json`
lấy `entity_id` (`in_list`) → chấm `categories` (done/none/out_of_list) → gắn `citations` → đặt
`recognized = (có ≥1 entity)`.

**Bóc tách**: (tuỳ chọn) kiểm tra precondition `sha256(raw_html_path)==raw_sha256` & `change_state` không
thuộc {SELECTOR_BROKEN, TEMPLATE_DRIFT} → tóm tắt → hàm ý → materiality → (sentiment/event) → ≥2 citation
grounded → `extraction_quality` + `processing_metadata`.

---

## 4. Tiêu chí NGHIỆM THU (DoD) — self-check TRƯỚC khi nộp

Runtime chấm đúng các điều dưới (nguồn: `src/agent/l1_router.py::check_l1_dod`,
`src/agent/dod.py::check_dod`). **`confidence` KHÔNG còn là gate.** Đạt hết mới `dod_pass=1`.

### 4.1 L1 (`l1-entity-output-v1`)
- [ ] Hợp `l1-entity-output-v1.schema.json`.
- [ ] Mỗi `entities[].surface` là **chuỗi con của title**.
- [ ] Mỗi `citations[].source_span` là **chuỗi con của title**.
- [ ] `recognized=true` ⇒ `entities ≥ 1` **và** `citations ≥ 1`.
- [ ] `recognized=false` ⇒ `entities = []` **và** không `categories` nào = `done`.
- [ ] `categories.<nhóm>='done'` ⇒ có ≥1 entity `in_list=true` **thuộc đúng nhóm đó**.
- [ ] `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp`.

### 4.2 Bóc tách (`agent-output-v1`)
- [ ] Hợp `agent-output-v1.schema.json`.
- [ ] **≥ 2 citations**; mỗi `source_span` **⊂ `cleaned_text`** và **≥ 20 ký tự**.
- [ ] `extraction_quality ∈ {high, medium}`.
- [ ] `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp`.
- [ ] (precondition) `raw_sha256` khớp & `change_state` không bị held.

---

## 5. Vòng lặp "cam đoan tới khi hoàn thành"

Cơ chế khép kín, idempotent — agent lặp tới khi `dod_pass=1`:

```
soạn output → ghi <id>.json → l1_ingest.py / agent_ingest.py
   ├─ DoD PASS → mark done  →  l1_outputs/agent_outputs.dod_pass=1   (replay = cached, không làm lại)
   └─ DoD FAIL → mark failed + LƯU `dod_reasons`  →  đọc reasons, SỬA đúng điểm, nộp lại
```

- **Xem lý do trượt** để sửa trúng:
  ```powershell
  .\.venv\Scripts\python.exe -c "import sqlite3;[print(dict(r)) for r in sqlite3.connect('data/monocle.db').execute(\"select article_id,dod_pass,dod_reasons from l1_outputs where dod_pass=0 limit 20\")]"
  ```
  (đổi `l1_outputs`→`agent_outputs` cho lớp bóc tách.)
- **Idempotent**: bài đã `dod_pass=1` → nạp lại trả cached, KHÔNG xử lý lại → an toàn chạy trùng.
- **"Hoàn thành" của cả lô** = `db_status.py` mục 8–9 cho thấy `dod_pass=1` phủ hết article cần thiết;
  khi đó `write_user_output.py` mới ghi được `final.csv`.

---

## 6. Lỗi hay gặp → cách sửa (từ `dod_reasons`)

| reason | Nguyên nhân | Sửa |
|--------|-------------|-----|
| `surface không phải chuỗi con của title` | copy sai/paraphrase | dán **nguyên văn** đoạn trong title |
| `source_span too short (<20 chars)` | trích quá ngắn | chọn câu/cụm ≥20 ký tự |
| `citation not grounded in cleaned_text` | bịa/diễn giải | span phải **có thật** trong `cleaned_text` |
| `citations N < 2` | thiếu trích dẫn | thêm cho đủ ≥2 |
| `extraction_quality=… not in (high, medium)` | để `low`/thiếu | đặt `high`/`medium` |
| `processing_metadata.* missing` | quên metadata | điền provider/model/timestamp |
| `recognized=false nhưng có category='done'` | mâu thuẫn | đồng bộ `recognized`/`categories`/`entities` |

---

## 7. Không có LLM? Dùng stub để nghiệm thu luồng
`scripts/agent_stub.py` sinh output hợp lệ theo quy tắc (KHÔNG phân tích thật) — dùng kiểm thử end-to-end.
Khi cắm LLM, thay bằng adapter đọc packet → gọi model (ép schema §2.3) → ghi `<id>.json`. Xem
[13-per-user-output-workflow §14.4](../design/13-per-user-output-workflow.md).

---

## 8. Câu hỏi mở
- Chưa có adapter LLM sẵn (`scripts/agent_run.py`) — hiện là stub hoặc agent thủ công.
- `check_l1_dod` map nhóm ngành theo `INDUSTRY_GICS*`; entity thực tế dùng type `IND_GICS*` →
  nên chỉ đánh `categories.industry_sector='done'` khi chắc có entity in_list nhóm ngành (tránh lệch coherence).
