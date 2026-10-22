---
type: Reference
title: Agent Contracts & DoD
description: Hợp đồng JSON Schema ở ranh giới producer↔mô hình (article-compact-v2, l1-entity-output-v1, agent-output-v2-lean), sáu predicate Definition-of-Done và guardrail.
resource: project/schemas/
tags: [contract, schema, dod, agent, governance]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: dod
    resource: project/src/agent/contract/dod.py
    title: check_dod + verify_preconditions
  - id: l1-router
    resource: project/src/agent/contract/l1_router.py
    title: check_l1_dod
  - id: article-contract
    resource: project/src/agent/contract/article_contract.py
    title: Hợp đồng bản ghi gọn dùng chung mọi provider
  - id: validator
    resource: project/src/handoff/contract_validator.py
    title: contract_validator
  - id: lifecycle
    resource: project/schemas/task-lifecycle-v1.yaml
    title: Task lifecycle + thresholds
sources_last_checked: 2026-10-22
---

Ranh giới producer ↔ mô hình được định nghĩa **bằng hợp đồng**, không bằng code chung. Mô hình
có thể chạy trên runner bất kỳ (DSH, agy, opencode, OpenRouter); code chỉ đóng gói, bung bản
ghi và nghiệm thu, không quyết định thực thể hay tóm tắt.

# Hợp đồng trong `project/schemas/`

| File | Vai trò | Ai tạo |
|---|---|---|
| `silver-v1.schema.json` | clean base sau chuẩn hoá | producer |
| `work-package-v1.schema.json` | INPUT đã chuẩn hoá cho một bài (trỏ raw, không inline) | producer |
| `article-compact-v2.schema.json` | bản ghi **gọn** mô hình trả cho cả lô trong Article Lane | mô hình |
| `l1-entity-output-v1.schema.json` | bản ghi nhận diện thực thể (bung từ bản gọn) | expand |
| `agent-output-v2-lean.schema.json` | bản ghi nội dung hiện hành (bung từ bản gọn) | expand |
| `agent-output-v1.schema.json` | bản ghi nội dung cũ, DoD vẫn đọc được | — |
| `task-lifecycle-v1.yaml` | vòng đời task + **ngưỡng DoD** | spec |

Kèm `agent-instructions-v1.md`, `l1-entity-instructions-v1.md`, `samples/`; `CHANGELOG.md` ghi
lịch sử bump. `contract_validator.validate(instance, schema_name)` là điểm kiểm schema duy
nhất.[^validator] Hằng số và hàm mở bao của bản ghi gọn dùng chung mọi provider nằm ở
`src/agent/contract/article_contract.py`.[^article-contract]

# Preconditions

```
verify_preconditions(work_package, check_integrity=True)
  ① change_state ∉ {SELECTOR_BROKEN, TEMPLATE_DRIFT}
  ② file raw_html_path tồn tại
  ③ sha256(file) == raw_sha256        ← chống inject / lệch bản
```

Không đạt ⇒ bản ghi nội dung bị loại, `work_items.status = failed`.[^dod]

# Definition-of-Done — nội dung

| # | Predicate | Điều kiện |
|---|---|---|
| 1 | `schema_valid` | khớp `agent-output-v2-lean` hoặc `agent-output-v1` |
| 2 | `grounded` | ≥ `min_citations` (**2**; bài một đoạn có `citation_basis = single-paragraph` cần 1); mỗi trích dẫn là chuỗi con nguyên văn của `cleaned_text`, dài ≥ **20** ký tự |
| 3 | `quality_ok` | `extraction_quality ∈ {high, medium}` — chỉ v1 |
| 4 | `auditable` | `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp` — chỉ v1 |
| 5 | `value_added` | tóm tắt không chép nguyên văn bài; `key_points` không chép trích dẫn |
| 6 | `implication_specific` | hàm ý ≥ `min_implication_len` (40), không chép bài, không là câu mẫu |

Ngưỡng đọc từ `task-lifecycle-v1.yaml`; thiếu file ⇒ fallback hằng số.[^lifecycle]
`_MIN_SPAN_LEN = 20` chặn "groundedness giả": span quá ngắn là chuỗi con của gần như mọi bài.

**`confidence` KHÔNG phải gate** (bỏ 2026-08-18): mô hình tự khai, calibration kém.

# Definition-of-Done — nhận diện thực thể

Schema `l1-entity-output-v1` hợp lệ + mọi `surface`/`source_span` ⊂ **tiêu đề** + `recognized`
nhất quán + nhóm `categories` đánh `done` phải có entity `in_list` thuộc nhóm.[^l1-router]

# Trường bắt buộc của `agent-output-v2-lean`

`article_id`, `summary`, `key_points`, `implication`, `sentiment`, `time_sensitivity`,
`citations`. Các trường `materiality`, `event_type`, `impact_area` đã bỏ ở mọi tầng; chúng chỉ
còn trong schema v1 cũ.

# Guardrail

Mô hình **không** đọc tệp, ghi tệp, tra catalog hay tự chấm DoD (bất biến của
[Article Lane](../pipelines/article_lane.md)). Mọi bản ghi chỉ vào DB qua `l1_ingest.py` /
`agent_ingest.py` có validate + DoD.

# Liên quan

- [Agent Ingest & cổng DoD](../pipelines/agent_handoff.md) · [agent_outputs](../tables/agent_outputs.md) ·
  [l1_outputs](../tables/l1_outputs.md) · [Silver & Work Packages](../datasets/silver_work_packages.md)

[^dod]: [dod.py](project/src/agent/contract/dod.py)
[^l1-router]: [l1_router.py](project/src/agent/contract/l1_router.py)
[^article-contract]: [article_contract.py](project/src/agent/contract/article_contract.py)
[^validator]: [contract_validator.py](project/src/handoff/contract_validator.py)
[^lifecycle]: [task-lifecycle-v1.yaml](project/schemas/task-lifecycle-v1.yaml)
