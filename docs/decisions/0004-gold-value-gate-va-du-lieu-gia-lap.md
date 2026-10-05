# ADR 0004 — Cổng giá trị cho tầng Gold & xử lý dữ liệu do script giả lập

- **Ngày:** 2026-09-08
- **Trạng thái:** **accepted** — phần D đã duyệt theo Phương án D1 (2026-09-09)
- **Lane:** high-risk (chạm dữ liệu không đảo ngược + hợp đồng DoD)
- **Story:** US-102 · **Backlog:** #3, #4

## 1. Bối cảnh

Rà soát deliverable người dùng cuối (US-101) làm lộ ra bệnh nặng hơn nhiều so với vấn đề định
dạng. Đo trên `project/data/monocle.db` (đọc read-only, 2026-09-08):

| Chỉ số | Số liệu |
|---|---|
| `agent_outputs` | 1.274 |
| `dod_pass = 1` | **1.274 / 1.274 (100%)** |
| `key_points` copy y hệt `citations[].source_span` | **1.274 / 1.274 (100%)** |
| `implication.text` | chỉ **3 câu** distinct cho toàn bộ 1.274 bản ghi |
| trong đó 1 câu template duy nhất | **1.117 (87,7%)** |
| `impact_area = market` | **1.274 / 1.274 (100%)** |
| `sentiment = neutral` | 1.191 (93,5%) |
| `event_type = macro` | 1.143 (89,7%) |
| gắn nhãn `gemini/gemini-3.7-flash` | 1.139 |

## 2. Nguyên nhân gốc

`project/scripts/maintenance/repair_truncated_outputs.py` **giả lập trí tuệ Agent bằng
heuristic script** — vi phạm trực tiếp AGENTS.md §6.C:

- `extract_sentences()` tách câu bằng regex, lấy 3 câu đầu làm `summary.abstractive`
  (nên 58% bản ghi có tóm tắt mở đầu bằng chính tiêu đề — `cleaned_text` bắt đầu bằng tiêu đề);
- `key_points = [c["source_span"] for c in citations[:4]]` — điểm chính = đúng các đoạn đã trích
  (giải thích 100% ở bảng trên);
- gán CỨNG `implication.text` = câu template, `impact_area="market"`, `materiality.score=0.6`,
  `time_sensitivity="this_week"`, `sentiment="neutral"`, `event_type="macro"`,
  `confidence=0.85`, `extraction_quality="high"`;
- `UPDATE agent_outputs … SET agent_provider='gemini', model_used='gemini-3.7-flash'` —
  **giả provenance**, kể cả ghi đè `stub` → `gemini`, khiến bản ghi do regex sinh ra không thể
  phân biệt với bản ghi LLM thật;
- cuối script tự gọi `UserOutputWriter.write(days=30)` → đẩy thẳng ra file người dùng.

**Vì sao cổng DoD không chặn.** 4 predicate cũ (`schema_valid`, `grounded`, `quality_ok`,
`auditable`) đo *tính có căn cứ*, không đo *có phân tích*. Với output copy nguyên văn thì phép
thử `source_span ⊂ cleaned_text` trở nên **hiển nhiên đúng**; `extraction_quality` là tự khai.
Một cổng chưa từng từ chối bản ghi nào (1.274/1.274 pass) thì không phải là cổng.

## 3. Quyết định

### A. Xoá nguồn giả lập — ĐÃ LÀM
`scripts/maintenance/repair_truncated_outputs.py` bị xoá. Không sửa thành "bản nhẹ hơn": mọi
biến thể của nó đều là script viết nội dung Gold.

### B. Vá cổng DoD bằng 2 predicate mới — ĐÃ LÀM
`src/agent/dod.py::check_dod` thêm:

| Predicate | Nội dung |
|---|---|
| `value_added` | `summary.abstractive` (chuẩn hoá) **không** là chuỗi con của `cleaned_text`; không `key_points[i]` nào trùng nguyên văn một `citations[].source_span` |
| `implication_specific` | `len(implication.text) ≥ 40`; không là chuỗi con của `cleaned_text`; không khớp `thresholds.boilerplate_implications` |

Đây vẫn là **validation tất định** — nó chỉ TỪ CHỐI, không tự sinh nội dung, nên không vi phạm
§6.C. Ngưỡng và blocklist nằm trong `schemas/task-lifecycle-v1.yaml` để chỉnh mà không đổi code.

### C. Khoá bất biến chống tái phạm — ĐÃ LÀM
`tests/test_no_agent_emulation.py`:
1. chỉ `src/db/store.py` được viết SQL chạm `agent_outputs`/`l1_outputs`;
2. chỉ `runner.py`/`l1_runner.py` được gọi `insert_*_output` (tức mọi bản ghi đều bị chấm DoD);
3. `repair_truncated_outputs.py` phải ở trạng thái đã xoá.

Kèm theo: `schemas/agent-instructions-v1.md` §2b nêu rõ chỉ `citations` được copy; và
`schemas/samples/agent-output-sample.json` được sửa vì **chính nó** đang mắc lỗi
`key_points == source_span` — agent bắt chước mẫu thì học đúng lỗi đó.

### D. Dữ liệu 1.274 bản ghi đã bị ghi đè — **ĐÃ DUYỆT (Phương án D1)**
Hard gate (AGENTS.md Cấp 3): Human Operator đã duyệt Phương án D1 ngày 2026-09-09.

| Phương án | Hệ quả | Đánh giá | Trạng thái |
|---|---|---|---|
| **D1. Hạ `dod_pass=0` cho bản ghi trượt cổng mới, GIỮ `output_json`** | Bài rời deliverable, tự quay lại hàng đợi Gold; số dòng giao giảm mạnh trong ngắn hạn; không mất dữ liệu gốc | **Khuyến nghị** — trung thực, đảo ngược được (chỉ là cờ) | **CHẤP THUẬN (Đang áp dụng)** |
| D2. Giữ nguyên, chỉ siết cho bản ghi mới | Deliverable tiếp tục chứa nội dung template vô giá trị | Không giải quyết được vấn đề | Bác bỏ |
| D3. Xoá hẳn các bản ghi giả lập | Mất luôn `citations` có thật đã trích được | Phá huỷ quá mức | Bác bỏ |

## 4. Hệ quả đã biết

- Cổng mới sẽ **đánh trượt gần như 100% output theo lối cũ**. Đây là chủ đích: pipeline sẽ
  không giao hàng "đầy đủ" cho tới khi prompt agent được cập nhật theo §2b và chạy lại. Bài chỉ
  có L1 vẫn giao bình thường ở trạng thái `Sơ bộ` — cơ chế L1-only gate không đổi.
- `sentiment` / `event_type` / `impact_area` gần như hằng số là **triệu chứng cùng gốc**.
  `impact_area` và `event_type` đã bị loại khỏi deliverable ở US-101; hai cột này chỉ nên bật
  lại khi `verify_gold_quality` cho thấy phân bố thật.
- Cổng theo từng bản ghi không phát hiện được "cả tập giống nhau" → phải chạy
  `verify_gold_quality.py` định kỳ, xem `implication_distinct` như một chỉ số sức khoẻ.

## 5. Tham chiếu
- AGENTS.md §6.C — Cấm giả lập trí tuệ Agent bằng heuristic script
- `docs/FEATURE_INTAKE.md` — hard gate "thay đổi dữ liệu không đảo ngược"
- `project/docs/design/13-per-user-output-workflow.md` §8, §10
- `project/schemas/task-lifecycle-v1.yaml` §definition_of_done, §thresholds
