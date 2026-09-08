---
type: Python Pipeline
title: Agent Handoff (Vòng 3 — Gold 2 lớp)
description: Hạ tầng giao việc cho agent ngoài — export packet, ingest output, validate schema + chấm DoD. Không nhúng LLM.
resource: project/src/agent/runner.py
tags: [pipeline, agent, handoff, dod, gold]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: runner
    resource: project/src/agent/runner.py
    title: AgentRunner — Lớp 2
  - id: l1-runner
    resource: project/src/agent/l1_runner.py
    title: L1Runner — Lớp 1
  - id: dod
    resource: project/src/agent/dod.py
    title: Definition-of-Done + preconditions
  - id: packet
    resource: project/src/agent/packet.py
    title: Task packet + pruner
  - id: orchestration-design
    resource: project/docs/design/15-antigravity-multi-agent-orchestration.md
    title: Multi-agent hierarchy orchestration
sources_last_checked: 2026-09-07
---

**Vòng 3** là *hạ tầng* handoff, không phải bộ não. Codebase = **producer** (đóng gói việc,
nghiệm thu kết quả); agent ngoài = **consumer** (provider bất kỳ do người dùng điều khiển).
Ranh giới giữa hai bên là 2 JSON Schema + Definition-of-Done. **Không có lời gọi LLM nào trong
repo.**[^orchestration-design]

# Hai lớp nghiệp vụ

| Lớp | Việc | Packet vào | Output ra | Bảng |
|---|---|---|---|---|
| **L1 — Entity Recognition** | nhận diện mã CP, doanh nghiệp, ngành, chỉ số, sàn từ **tiêu đề** | `data/agent_tasks/l1/*.task.json` | `l1-entity-output-v1` | [l1_tasks](../tables/l1_tasks.md), [l1_outputs](../tables/l1_outputs.md) |
| **L2 — Content Processing (Gold)** | tóm tắt, hàm ý thị trường, materiality, sentiment, citations từ **toàn văn** | `data/agent_tasks/*.task.json` | `agent-output-v1` | [work_items](../tables/work_items.md), [agent_outputs](../tables/agent_outputs.md) |

L1 chạy **2 tầng**: code-first deterministic trước (khớp mã + alias), chỉ tiêu đề không khớp mới
cần agent. Kết quả L1 được nhúng ngược vào packet L2 (`input.l1_entities`) để agent Gold có sẵn
ngữ cảnh mã CP.[^packet]

# Chu trình 4 giai đoạn

```
1. EXPORT   scripts/l1_route.py --review missed     → packet L1
            scripts/agent_export.py                 → claim work_items → packet Gold
2. AGENT    [agent NGOÀI đọc *.task.json, nộp *.json]
              L1   → data/agent_outputs_l1/
              Gold → data/agent_outputs/
3. INGEST   scripts/l1_ingest.py <dir>     → validate + check_l1_dod → l1_outputs
            scripts/agent_ingest.py <dir>  → validate + check_dod    → agent_outputs
              PASS → work_items.done   |   FAIL → failed + dod_reasons (self-healing)
4. DELIVER  scripts/run_user_workflow.py  → users/output/<user>/<date>.csv
```

Chuỗi gộp: `scripts/run_agent_hierarchy.py`.

# Preconditions (trước khi giao)

`verify_preconditions()` chặn việc không đủ điều kiện:[^dod]
- `change_state ∈ {SELECTOR_BROKEN, TEMPLATE_DRIFT}` ⇒ **held**.
- Toàn vẹn raw: file `raw_html_path` phải tồn tại và `sha256(file) == raw_sha256` (chống inject).

# Definition-of-Done — Lớp 2

4 predicate thuần code, đọc ngưỡng từ `schemas/task-lifecycle-v1.yaml`:[^dod]

1. `schema_valid` — khớp `agent-output-v1`.
2. `grounded` — ≥ **2** citations, mỗi `source_span` là chuỗi con **nguyên văn** của
   `cleaned_text` và dài ≥ **20** ký tự.
3. `quality_ok` — `extraction_quality ∈ {high, medium}`.
4. `auditable` — `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp`.

`confidence` **không** phải gate ở cả hai lớp (bỏ 2026-08-18 — self-reported, calibration kém).

DoD Lớp 1: schema + grounding bằng chứng ⊂ tiêu đề + checklist.

# Tối ưu payload

- **Pruner** (`src/agent/pruner.py`) — chỉ giữ khối đoạn văn nội dung chính, bỏ teaser, hotline,
  thông tin toà soạn, menu, quảng cáo; **giữ nguyên văn** từng đoạn để citation vẫn grounded.
  Payload 182 KB → 6–8 KB (~96%).
- **Batch handoff** (`src/agent/batch_handoff.py`) — gom 5–10 bài vào `batch_XX.task.json`, giảm
  ~90% số tool call I/O của subagent. `manifest.py` dựng manifest lô, `archive.py` dọn packet sau
  khi ingest xong.

# Guardrail I/O

Subagent chỉ được **đọc** `data/agent_tasks/` và chỉ **ghi** `data/agent_outputs*/` — quy định ở
`.agents/rules/`. Producer không bao giờ nhận nội dung agent ngoài luồng ingest có validate.

# Quan hệ

- Đầu vào: [Silver & Work Packages](../datasets/silver_work_packages.md)
- Đầu ra: [User Output](user_output.md)

# Metrics

- [DoD Pass Rate](../metrics/dod_pass_rate.md)

[^runner]: [AgentRunner](project/src/agent/runner.py)
[^l1-runner]: [L1Runner](project/src/agent/l1_runner.py)
[^dod]: [DoD](project/src/agent/dod.py)
[^packet]: [Task packet](project/src/agent/packet.py)
[^orchestration-design]: [Multi-agent hierarchy](project/docs/design/15-antigravity-multi-agent-orchestration.md)
