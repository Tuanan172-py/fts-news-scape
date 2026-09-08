---
type: Reference
title: Agent Contracts & DoD
description: 5 hợp đồng JSON Schema ở ranh giới producer↔agent, các predicate Definition-of-Done và guardrail I/O.
resource: project/schemas/
tags: [contract, schema, dod, agent, governance]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: dod
    resource: project/src/agent/dod.py
    title: check_dod + verify_preconditions
  - id: validator
    resource: project/src/handoff/contract_validator.py
    title: contract_validator
  - id: lifecycle
    resource: project/schemas/task-lifecycle-v1.yaml
    title: Task lifecycle + thresholds
  - id: agent-io
    resource: project/docs/design/09-agent-io-contract.md
    title: Agent I/O contract
  - id: governance
    resource: project/docs/design/10-agent-orchestration-governance.md
    title: Agent orchestration governance
sources_last_checked: 2026-09-07
---

Ranh giới producer ↔ agent được định nghĩa **hoàn toàn bằng hợp đồng**, không bằng code chung.
Nhờ vậy agent có thể là bất kỳ provider nào; repo không chứa lời gọi LLM.[^agent-io]

# 5 hợp đồng trong `project/schemas/`

| File | Vai trò | Ai tạo |
|---|---|---|
| `silver-v1.schema.json` | clean base sau chuẩn hoá | producer |
| `work-package-v1.schema.json` | INPUT giao agent (trỏ raw, không inline) | producer |
| `agent-output-v1.schema.json` | OUTPUT Lớp 2 (tóm tắt/hàm ý/materiality/citations) | agent |
| `l1-entity-output-v1.schema.json` | OUTPUT Lớp 1 (thực thể trong tiêu đề) | agent |
| `task-lifecycle-v1.yaml` | vòng đời task + **ngưỡng DoD** | spec |

Kèm 2 file hướng dẫn viết prompt: `agent-instructions-v1.md`, `l1-entity-instructions-v1.md`, và
`schemas/samples/` để đối chiếu. `CHANGELOG.md` ghi lịch sử bump.

`contract_validator.validate(instance, schema_name)` là điểm kiểm duy nhất — dùng lại cho cả
hard-gate Silver/package lẫn predicate `schema_valid` của DoD.[^validator]

# Preconditions — trước khi giao việc

```
verify_preconditions(work_package, check_integrity=True)
  ① change_state ∉ {SELECTOR_BROKEN, TEMPLATE_DRIFT}
  ② file raw_html_path tồn tại
  ③ sha256(file) == raw_sha256        ← chống inject / lệch bản
```

Không đạt ⇒ `work_items.status = held`, agent không bao giờ thấy việc đó.[^dod]

# Definition-of-Done — Lớp 2 (`agent-output-v1`)

| # | Predicate | Điều kiện |
|---|---|---|
| 1 | `schema_valid` | khớp `agent-output-v1` |
| 2 | `grounded` | ≥ `min_citations` (**2**) citations; mỗi `source_span` là chuỗi con nguyên văn của `cleaned_text`, dài ≥ **20** ký tự |
| 3 | `quality_ok` | `extraction_quality ∈ {high, medium}` |
| 4 | `auditable` | `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp` |

Ngưỡng đọc từ `task-lifecycle-v1.yaml`; thiếu file/PyYAML ⇒ fallback hằng số khớp spec.[^lifecycle]

`_MIN_SPAN_LEN = 20` tồn tại để chặn "groundedness giả": span quá ngắn (`"."`, `"VN"`) là chuỗi
con của gần như mọi bài.

**`confidence` KHÔNG phải gate** (bỏ 2026-08-18 ở cả 2 lớp): agent tự khai, calibration kém. Vẫn
lưu cột để audit, nhưng không xuất ra CSV người dùng.

# Definition-of-Done — Lớp 1 (`l1-entity-output-v1`)

schema hợp lệ + bằng chứng bề mặt ⊂ **tiêu đề** + checklist packet đầy đủ.

# Trường bắt buộc trong output Lớp 2

`output_schema_version`, `article_id`, `summary` (`abstractive` + `key_points`), `implication`
(`text` + `impact_area`), `materiality` (`score` 0.1–1.0 + `time_sensitivity`), `citations` (≥2),
`processing_metadata`. Tuỳ chọn: `sentiment.polarity`, `event_type`.

# Task packet — cấu trúc self-describing

```
packet_version, work_item_id, article_id, raw_sha256
input:            payload đã prune (+ l1_entities nếu có)
output_contract:  schema_name, schema_path, required[], thinking_order[]
constraints:      min_citations, min_citation_len, citations_must_be_substring_of,
                  extraction_quality_in, processing_metadata_required, preconditions[]
instructions_ref: schemas/agent-instructions-v1.md
```

Agent không cần biết nội bộ codebase — mọi thứ cần thiết nằm trong packet.

# Guardrail I/O

Subagent chỉ **đọc** `data/agent_tasks/` và chỉ **ghi** `data/agent_outputs/`,
`data/agent_outputs_l1/` (quy định ở `.agents/rules/`). Mọi nội dung agent chỉ vào hệ thống qua
đường ingest có validate + DoD; fail ⇒ `dod_reasons` quay lại agent để tự sửa (self-healing).[^governance]

# Ép schema theo provider

OpenAI `response_format json_schema` · Anthropic tool `input_schema` · Gemini `responseSchema` ·
local/MCP → validate cùng schema. Runtime không quy định provider.[^agent-io]

# Liên quan

- [Agent Handoff](../pipelines/agent_handoff.md) · [agent_outputs](../tables/agent_outputs.md) ·
  [l1_outputs](../tables/l1_outputs.md) · [Silver & Work Packages](../datasets/silver_work_packages.md)

[^dod]: [dod.py](project/src/agent/dod.py)
[^validator]: [contract_validator.py](project/src/handoff/contract_validator.py)
[^lifecycle]: [task-lifecycle-v1.yaml](project/schemas/task-lifecycle-v1.yaml)
[^agent-io]: [Agent I/O contract](project/docs/design/09-agent-io-contract.md)
[^governance]: [Agent orchestration governance](project/docs/design/10-agent-orchestration-governance.md)
