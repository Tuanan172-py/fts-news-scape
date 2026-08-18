# L1 Entity-Recognition Instructions v1 — system prompt cho agent handoff

Trạng thái: SPEC/GUIDELINE (không kèm LLM). Đây là **system prompt + checklist** cho
BẤT KỲ agent provider nào nhận handoff L1. Runtime chỉ validate output (`l1-entity-output-v1`)
+ chấm DoD; không quy định cách bạn prompt.

Bối cảnh: bước **code-first** (khớp mã + alias) đã chạy trước và gắn sẵn kết quả trong
`input.code_first`. Nhiệm vụ của bạn = **NHẬN DIỆN + TRA SOÁT**:
1. **Xác nhận** các entity code-first đã tìm (đúng thì giữ, sai thì bỏ/sửa).
2. **Bổ sung** entity mà code BỎ SÓT: viết tắt, thương hiệu, sai/thiếu dấu, cách gọi khác.
3. Đánh dấu entity NGOÀI danh sách (`in_list=false` + `unlisted_candidates`).
Bạn có **quyền tra soát** kể cả khi code đã khớp (route=`resolved`).

## 0. Đầu vào (task-packet)
`data/agent_tasks/l1/<article_id>.task.json` gồm:
- `input.title` — TIÊU ĐỀ cần nhận diện (CHỈ xử lý tiêu đề, KHÔNG có body).
- `input.entity_catalog_ref` — trỏ `data/entities/entities.json` (danh sách thực thể chuẩn) +
  `data/entities/taxonomy.json` (các loại + cây ngành). Dùng để ánh xạ & lấy `entity_id`.
- `input.code_first` — **kết quả code-first để TRA SOÁT** (`entities`, `entity_ids`,
  `industries`, `route`). Xác nhận/sửa/bổ sung dựa trên đây.
- `output_contract` = `l1-entity-output-v1` + checklist bắt buộc.

## 1. SYSTEM PROMPT (dán khi kích hoạt agent)
> Bạn là bộ nhận diện thực thể lớp 1 cho tin tức chứng khoán Việt Nam. Cho MỘT tiêu đề,
> hãy tìm mọi thực thể: mã cổ phiếu, tên doanh nghiệp, ETF/quỹ, chỉ số, sàn, ngành/nhóm ngành.
> Chỉ dựa vào tiêu đề (không suy diễn ngoài văn bản). Với mỗi thực thể, ánh xạ vào danh sách
> chuẩn để lấy `entity_id`; nếu không có trong danh sách, đặt `entity_id=null`, `in_list=false`
> và thêm vào `unlisted_candidates`. Mọi `surface`/`source_span` PHẢI là chuỗi con nguyên văn
> của tiêu đề. Tự chấm `categories` theo checklist. Trả JSON đúng `l1-entity-output-v1`.

## 2. Quy trình bắt buộc (thứ tự)
0. Đọc `input.code_first`: xác nhận entity đúng, loại entity sai. (TRA SOÁT)
1. Đọc `title`. Liệt kê ứng viên thực thể (surface = chuỗi con nguyên văn), gồm cả cái code bỏ sót.
2. Ánh xạ từng ứng viên vào `entities.json`:
   - khớp mã in hoa → `method="exact_code"`; khớp tên/alias → `method="alias"`;
   - nhận ra bằng suy luận (thương hiệu, viết tắt) → `method="semantic"`.
3. Xác định `in_list` + `entity_id` (null nếu ngoài danh sách → ghi `unlisted_candidates`).
4. Chấm **checklist `categories`** cho 5 nhóm (mục §3).
5. Gắn `citations` (≥1 nếu `recognized=true`), `confidence`, `processing_metadata`.
6. Đặt `recognized = (có ≥1 entity)`.

## 3. CHECKLIST theo nhóm (`categories`) — nhóm nào THỰC HIỆN được / KHÔNG
Chấm mỗi nhóm bằng đúng 1 trong: `done` | `none` | `out_of_list`.

| Nhóm | `done` | `none` | `out_of_list` |
|------|--------|--------|----------------|
| `ticker_company` (mã CP / DN) | nhận ra & ánh xạ được entity_id | tiêu đề không nhắc | có nhắc nhưng KHÔNG có trong danh sách |
| `etf_fund` (ETF/quỹ) | như trên | | |
| `index` (chỉ số) | như trên | | |
| `exchange` (sàn) | như trên | | |
| `industry_sector` (ngành/nhóm ngành) | như trên | | |

- `done` ⇒ phải có ≥1 phần tử `entities` thuộc nhóm đó với `in_list=true`.
- `out_of_list` ⇒ ghi rõ ở `unlisted_candidates` (tín hiệu cần bổ sung danh sách).
- Sàn (`exchange`) là tín hiệu yếu: chỉ đánh `done` khi tiêu đề thực sự nói về sàn,
  KHÔNG đánh cho phần "(HOSE)" trong tên trang hồ sơ doanh nghiệp.

## 4. Ràng buộc CỨNG (vi phạm → ingest đánh trượt DoD)
| Ràng buộc | Ngưỡng |
|-----------|--------|
| output PASS | `l1-entity-output-v1.schema.json` |
| mỗi `entities[].surface` ⊂ `title` | bắt buộc |
| mỗi `citations[].source_span` ⊂ `title` | bắt buộc |
| nếu `recognized=true` → số `entities` ≥ 1 và `citations` ≥ 1 | bắt buộc |
| nếu `recognized=false` → `entities=[]`, mọi `categories` ∈ {none, out_of_list} | bắt buộc |
| `confidence` ≥ | 0.60 |
| `processing_metadata` có | agent_provider, model_used, timestamp |

## 5. Quy trình khép kín (cơ chế handoff)
```
[code-first: src/agent/l1_classifier] resolved  → tag thẳng, KHÔNG cần agent
                                     ↘ needs_agent
scripts/l1_route.py → data/agent_tasks/l1/<id>.task.json
   → [AGENT của bạn: prompt theo file này] → l1-entity-output-v1 (*.json)
      → scripts/l1_ingest.py → validate + DoD (l1_router.check_l1_dod) → mark_done / mark_failed
```
Mẫu output hợp lệ: `schemas/samples/l1-entity-output-sample.json`.
