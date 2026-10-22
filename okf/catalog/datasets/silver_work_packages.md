---
type: File Dataset
title: Silver & Work Packages
description: Các artifact dưới Bronze — silver-v1, work-package-v1 (re-derivable), packet và bản ghi của Article Lane trên đĩa.
resource: "<DATA_ROOT>/silver/"
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
  - id: pack
    resource: project/src/article_lane/pack.py
    title: Packet cả lô của Article Lane
  - id: distill
    resource: project/src/agent/packet/distill.py
    title: Chắt lọc đoạn tất định
  - id: storage-design
    resource: project/docs/design/07-storage-layers-and-change-detection.md
    title: Storage layers & change detection
sources_last_checked: 2026-10-22
---

Silver và work-package là **hàm thuần của [Bronze](bronze_raw_html.md)**: xoá đi rồi re-derive sẽ
ra kết quả giống hệt (không dùng `now()` trong nội dung — `built_at` lấy từ `fetch_ts` của
Bronze).[^silver-builder] Packet và bản ghi của Article Lane là artifact của từng đợt.

# Bố cục thư mục (dưới `<DATA_ROOT>`)

| Đường dẫn | Nội dung | Hợp đồng |
|---|---|---|
| `silver/**` | bản clean base 1 bài | `silver-v1` |
| `work_packages/<domain>/<YYYYMMDD>/<article_id>.json` | INPUT đã chuẩn hoá cho một bài | `work-package-v1` |
| `agent_tasks/article/<batch>.task.json` + `<batch>.map.json` | packet cả lô của Article Lane + bảng chỉ số → `article_id` | packet `{d, n, a[]}` |
| `agent_tasks/article/wave_<W>.json`, `wave_<W>.conductor.ts` | mô tả đợt, chương trình điều phối | — |
| `agent_outputs_article/<batch>.*` | bản ghi gọn mô hình trả + meta | `article-compact-v2` |
| `agent_outputs_l1/<batch>.output.json` | bản nhận diện đã bung | `l1-entity-output-v1` |
| `agent_outputs/<batch>.output.json` | bản nội dung đã bung | `agent-output-v2-lean` |

JSON Schema nằm ở `project/schemas/`.

# Silver (`silver-v1`)

Trường chính do `SilverBuilder.build()` sinh:[^silver-builder]
`silver_schema_version`, `article_id`, `source_url`, `domain`, `content_sha256`, `cleaned_text`,
`extraction_quality` (`high|medium|low|empty`), `structure` (headings/paragraphs/tables/links),
`images`, `language`, `built_at`, `built_from_raw_path`.

Silver có **hard-gate**: không PASS `silver-v1` ⇒ bài bị `held`, không đi tiếp.

# Work package (`work-package-v1`)

Gói INPUT tự mô tả, **trỏ** Bronze chứ không inline bytes (`raw_html_path` + `raw_sha256`) để
cổng ingest kiểm toàn vẹn.[^work-package] Kèm `change_state`, `capture_status` và khối
`provenance` (`fetch_ts`, `render_method`, `scraper_version`, `silver_schema_version`). Khi
Article Lane nạp một bài chưa có work-package, `AgentRunner` tự dựng một gói tối thiểu từ Silver.

# Packet Article Lane

`pack.py` đọc `cleaned_text` từ Silver, **chắt lọc** đoạn tất định (`src/agent/packet/distill.py`,
giữ nguyên văn từng đoạn để trích dẫn còn grounded), rồi đóng cả lô vào một packet: chỉ số cục bộ
thay `article_id`, mỗi đoạn một dòng.[^pack] Luật, bảng tra nhóm và ví dụ nằm trong prefix tĩnh
(`src/agent/packet/prefix.py`), không lặp trong packet. Chi tiết:
[Article Lane](../pipelines/article_lane.md).

# Bất biến

1. Package **trỏ** raw, không nhúng bytes.
2. Mọi package phải PASS `contract_validator` mới được `pending`; else `held`.
3. Ingest kiểm `sha256(raw_html_path) == raw_sha256` (preconditions) trước khi chấm DoD.
4. Packet là **ephemeral** — sinh lại được từ Silver bất cứ lúc nào.

# Quan hệ

- Sinh bởi [Silver Derive](../pipelines/silver_derive.md); tiêu thụ bởi [Article Lane](../pipelines/article_lane.md)
- Trạng thái hàng đợi ở [work_items](../tables/work_items.md)

[^silver-builder]: [SilverBuilder](project/src/pipeline/silver_builder.py)
[^work-package]: [WorkPackageBuilder](project/src/handoff/work_package.py)
[^pack]: [pack.py](project/src/article_lane/pack.py)
[^storage-design]: [Storage layers & change detection](project/docs/design/07-storage-layers-and-change-detection.md)
