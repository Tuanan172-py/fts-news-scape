---
type: File Dataset
title: Silver & Work Packages
description: Các artifact re-derivable dưới Bronze — silver-v1, work-package-v1, task packet và output agent trên đĩa.
resource: project/data/silver/
tags: [silver, work-package, agent-tasks, re-derivable]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: silver-builder
    resource: project/src/pipeline/silver_builder.py
    title: SilverBuilder — chuẩn hoá Bronze thành clean base
  - id: work-package
    resource: project/src/handoff/work_package.py
    title: WorkPackageBuilder + write_package
  - id: packet
    resource: project/src/agent/packet.py
    title: Task packet builder (prune + output contract)
  - id: storage-design
    resource: project/docs/design/07-storage-layers-and-change-detection.md
    title: Storage layers & change detection
sources_last_checked: 2026-09-07
---

Toàn bộ artifact dưới đây là **hàm thuần của [Bronze](bronze_raw_html.md)**: xoá đi rồi
re-derive sẽ ra kết quả giống hệt (không dùng `now()` trong nội dung — `built_at` lấy từ
`fetch_ts` của Bronze).[^silver-builder]

# Bố cục thư mục

| Đường dẫn | Nội dung | Hợp đồng |
|---|---|---|
| `data/silver/**` | bản clean base 1 bài | `silver-v1` |
| `data/work_packages/<domain>/<YYYYMMDD>/<article_id>.json` | INPUT giao agent | `work-package-v1` |
| `data/agent_tasks/<article_id>.task.json` | task packet Lớp 2 (Gold) | packet 1.0 |
| `data/agent_tasks/l1/<article_id>.task.json` | task packet Lớp 1 | packet 1.0 |
| `data/agent_outputs/*.json` | output Lớp 2 agent nộp | `agent-output-v1` |
| `data/agent_outputs_l1/*.json` | output Lớp 1 agent nộp | `l1-entity-output-v1` |

JSON Schema nằm ở `schemas/` (repo root của project): `silver-v1`, `work-package-v1`,
`agent-output-v1`, `l1-entity-output-v1`, `task-lifecycle-v1.yaml`.

# Silver (`silver-v1`)

Trường chính do `SilverBuilder.build()` sinh:[^silver-builder]
`silver_schema_version`, `article_id`, `source_url`, `domain`, `content_sha256`, `cleaned_text`,
`extraction_quality` (`high|medium|low|empty`), `structure` (headings/paragraphs/tables/links),
`images`, `language`, `built_at`, `built_from_raw_path`.

Silver có **hard-gate**: không PASS `silver-v1` ⇒ bài bị `held`, không đi tiếp.

# Work package (`work-package-v1`)

Gói INPUT tự mô tả, **trỏ** Bronze chứ không inline bytes (`raw_html_path` + `raw_sha256`) để
agent tự verify offline chống inject.[^work-package] Kèm `change_state`, `capture_status` và khối
`provenance` (`fetch_ts`, `render_method`, `scraper_version`, `silver_schema_version`).

# Task packet (packet 1.0)

Packet là thứ **thực sự** giao cho agent, gồm 4 phần:[^packet]

- `input` — payload tinh gọn: `cleaned_text` đã qua **pruner** (chỉ giữ đoạn văn nội dung
  chính, bỏ 100% teaser/menu/quảng cáo/ảnh), kèm `l1_entities` nếu Lớp 1 đã nhận diện.
- `output_contract` — tên schema + đường dẫn + trường bắt buộc + `thinking_order`.
- `constraints` — ngưỡng DoD để agent tự canh trước khi nộp (`min_citations`, `min_citation_len`
  = 20, `citations_must_be_substring_of: input.cleaned_text`, `extraction_quality_in`).
- `instructions_ref` — trỏ `schemas/agent-instructions-v1.md`.

**Quy chuẩn Payload Đoạn văn Sạch**: pruning nén payload từ ~182 KB xuống 6–8 KB (giảm ~96%
token input) trong khi giữ nguyên văn từng đoạn để citation vẫn grounded được.

Gom lô: `src/agent/batch_handoff.py` đóng 5–10 bài vào `batch_XX.task.json`, giảm ~90% số tool
call I/O của subagent; `src/agent/manifest.py` dựng manifest lô;
`src/agent/archive.py` dọn packet sau khi ingest thành công.

# Bất biến

1. Package **trỏ** raw, không nhúng bytes.
2. Mọi package phải PASS `contract_validator` mới được `pending`; else `held`.
3. Agent verify `sha256(raw_html_path) == raw_sha256` trước khi xử lý.
4. Task packet là **ephemeral** — xoá được, sinh lại từ work-package bất cứ lúc nào.

# Quan hệ

- Sinh bởi [Silver Derive](../pipelines/silver_derive.md); tiêu thụ bởi [Agent Handoff](../pipelines/agent_handoff.md)
- Trạng thái hàng đợi ở [work_items](../tables/work_items.md)

[^silver-builder]: [SilverBuilder](project/src/pipeline/silver_builder.py)
[^work-package]: [WorkPackageBuilder](project/src/handoff/work_package.py)
[^packet]: [Task packet builder](project/src/agent/packet.py)
[^storage-design]: [Storage layers & change detection](project/docs/design/07-storage-layers-and-change-detection.md)
