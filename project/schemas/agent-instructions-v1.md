# Agent Instructions v1 — bản chỉ dẫn chuẩn (người dùng viết prompt từ đây)

Cập nhật: 2026-08-17 · Trạng thái: SPEC/GUIDELINE (không kèm LLM). Đây là **ràng buộc +
định hướng** để BẠN tự soạn prompt cho agent bất kỳ provider. Runtime chỉ validate output,
không quy định cách bạn prompt. Liên kết: [09](../docs/design/09-agent-io-contract.md),
[10](../docs/design/10-agent-orchestration-governance.md), [12](../docs/design/12-agent-infrastructure.md).

## 1. Đầu vào bạn nhận (task-packet)
`data/agent_tasks/<article_id>.task.json` gồm:
- `input` = work-package-v1 (có `cleaned_text`, `raw_html_path`, `raw_sha256`, `change_state`).
- `output_contract` = schema OUTPUT phải emit + thứ tự tư duy.
- `constraints` = ngưỡng DoD để tự canh trước khi nộp.

## 2. Việc agent phải làm (thứ tự tư duy bắt buộc)
1. **tóm tắt** (`summary.abstractive` + `key_points`) — trung thực với bài, không bịa.
2. **hàm ý** (`implication.text` + `affected_parties` + `impact_area`) — "so-what" cho thị trường.
3. **mức độ quan trọng** (`materiality.score 0..1` + `time_sensitivity`).
4. (tuỳ chọn) sentiment / event_type / entities+ticker.
5. Gắn **citations** ≥2, mỗi `source_span` **PHẢI là chuỗi con của `input.cleaned_text`**.
6. Điền `processing_metadata` (agent_provider, model_used, timestamp) + `extraction_quality`.

## 3. Ràng buộc CỨNG (nếu vi phạm → ingest đánh trượt, không mark_done)
| Ràng buộc | Ngưỡng |
|-----------|--------|
| `confidence` ≥ | 0.65 |
| số `citations` ≥ | 2 |
| mỗi `citations[].source_span` ⊂ `cleaned_text` | bắt buộc |
| `extraction_quality` ∈ | {high, medium} |
| `processing_metadata` có | agent_provider, model_used, timestamp |
| output PASS | `agent-output-v1.schema.json` |

## 4. Preconditions (agent tự kiểm trước khi xử lý)
- Verify `sha256(raw_html_path) == raw_sha256` (chống inject). Lệch → dừng.
- `change_state ∈ {SELECTOR_BROKEN, TEMPLATE_DRIFT}` → **không xử lý** (đã held phía producer).
- Idempotent: cùng (article_id, raw_sha256) chỉ cần 1 output đạt.

## 5. Định dạng output
- JSON đúng `agent-output-v1` (ASCII keys). Số kẹp đúng range; enum đóng.
- Ép schema tuỳ provider: OpenAI `response_format json_schema` · Anthropic tool `input_schema` ·
  Gemini `responseSchema` · local/MCP → validate cùng schema. (doc 09 §3)

## 6. Quy trình khép kín
```
scripts/agent_export.py  → data/agent_tasks/*.task.json
   → [AGENT của bạn: prompt dựa trên file này] → agent-output-v1 (*.json)
      → scripts/agent_ingest.py  → validate + DoD → mark_done / mark_failed
```
Mẫu output hợp lệ tham chiếu: `schemas/samples/agent-output-sample.json`.
