# Design 09 — Agent I/O Contract + Output Field Taxonomy [SPEC]

Cập nhật: 2026-08-14 · Trạng thái: **SPEC-ONLY** (chưa có agent/LLM code) · Kèm: [08](08-handoff-contract-catalog.md), [10](10-agent-orchestration-governance.md).

Đặc tả để BẤT KỲ agent provider nào (OpenAI/Anthropic/Gemini/local) xử lý đồng nhất từ work-package.
Phase-04. **Không** implement agent giờ (owner: "lớp agent để sau").

## 1. INPUT = work-package-v1 (doc 08)
Agent nhận đúng JSON work-package. Tiền điều kiện: verify `raw_sha256`; nếu `change_state ∈
{SELECTOR_BROKEN, TEMPLATE_DRIFT}` → không xử lý (held). Idempotent theo (article_id, raw_sha256).

## 2. OUTPUT = agent-output-v1 (schemas/agent-output-v1.schema.json)
ASCII keys (interop) + nhãn song ngữ. **CORE bắt buộc** (quyết định owner) — provider yếu vẫn đạt;
phần còn lại optional.

| Field (key) | Nhãn | Kiểu / thang | Req |
|-------------|------|--------------|-----|
| `summary` | tóm tắt | {abstractive, key_points[], key_quotes[]} | ✅ |
| `implication` | hàm ý (so-what) | {text, affected_parties[], impact_area: market\|regulatory\|sentiment\|supply_chain\|geopolitical\|other} | ✅ |
| `materiality` | mức độ quan trọng | {score 0..1, time_sensitivity: urgent\|today\|this_week\|this_month\|archive} | ✅ |
| `confidence` | độ tự tin | 0..1 | ✅ |
| `citations` | trích dẫn (grounded) | [{claim, source_span ⊂ cleaned_text, source_offset}] | ✅ |
| `processing_metadata` | truy vết | {agent_provider, model_used, timestamp, schema_version} | ✅ |
| `sentiment` | cảm xúc | {overall -1..1, polarity} | ○ |
| `event_type` | loại sự kiện | earnings\|acquisition\|regulatory\|lawsuit\|partnership\|financial_move\|macro\|other | ○ |
| `entities` | thực thể | {companies[{name,ticker,sentiment -1..1}], people[], locations[]} | ○ |
| `extraction_quality` | chất lượng | high\|medium\|low | ○ |

**Rule:** score/enum đóng; số clamp đúng range; `citations[].source_span` phải là substring của
work-package `cleaned_text` (groundedness → kiểm ở DoD/Phase-06). Thứ tự tư duy: tóm tắt → hàm ý →
mức độ quan trọng (đúng yêu cầu).

## 3. Provider mapping (documented, not coded)
| Provider | Cơ chế ép schema |
|----------|------------------|
| OpenAI | `response_format: {type:"json_schema", json_schema: agent-output-v1}` |
| Anthropic | tool use — `input_schema = agent-output-v1` (structured output) |
| Gemini | `generationConfig.responseSchema = agent-output-v1` |
| Local / LiteLLM / MCP | MCP tool result → validate cùng schema (`contract_validator`) |

Portability = 1 JSON Schema nguồn + adapter mỏng mỗi provider (adapter = việc sau).

## 4. Validate + persist (future)
Output validate qua `contract_validator("agent-output-v1")` (đã có, dùng chung). Sample hợp lệ:
`schemas/samples/agent-output-sample.json` (validate PASS trong `validate_e2e.py`). Khi agent land:
map vào `articles.sentiment/sentiment_score` + bảng `agent_outputs` mới (NOTE, chưa implement).

## 5. Versioning
Additive/optional; bump `output_schema_version`; giữ bản cũ đọc được. `schemas/CHANGELOG.md`.

## Unresolved
- Đa ngôn ngữ (vi/en) cho materiality scale; ngưỡng hallucination; verify citation ở quy mô lớn → doc 10 DoD.
