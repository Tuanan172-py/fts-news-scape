---
type: Python Pipeline
title: Agent Ingest & cổng DoD (nửa hoàn tất của Article Lane)
description: Nạp bản ghi mô hình vào DB qua hai cổng Definition-of-Done thuần code — l1_ingest.py (l1-entity-output-v1) và agent_ingest.py (agent-output-v2-lean / v1) — do article_run.py --finish gọi.
resource: project/src/agent/ingest/runner.py
tags: [pipeline, agent, ingest, dod, article-lane]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: runner
    resource: project/src/agent/ingest/runner.py
    title: AgentRunner.ingest_output — cổng DoD nội dung
  - id: l1-runner
    resource: project/src/agent/ingest/l1_runner.py
    title: L1Runner.ingest_output — cổng DoD nhận diện thực thể
  - id: dod
    resource: project/src/agent/contract/dod.py
    title: verify_preconditions + check_dod (6 tiêu chí)
  - id: l1-router
    resource: project/src/agent/contract/l1_router.py
    title: check_l1_dod
  - id: run
    resource: project/src/ops/wave/article_run.py
    title: Bước ingest của --finish
  - id: adr-0010
    resource: docs/decisions/0010-ngung-lane-l1-gold-article-lane-duy-nhat.md
    title: Article Lane là đường duy nhất
sources_last_checked: 2026-10-22
---

Đây là **nửa nghiệm thu** của [Article Lane](article_lane.md), không phải một đường xử lý riêng.
Đường hai lớp L1/Gold cũ (`l1_route.py`, `agent_export.py`, `run_agent_hierarchy.py`,
`run_user_workflow.py`, `run_daily.ps1`) đã khai tử và bị xoá theo ADR-0010.[^adr-0010]

Hai lệnh ingest còn lại vì chúng là cổng duy nhất để bản ghi của mô hình vào DB:

| Lệnh | Schema vào | Cổng | Bảng |
|---|---|---|---|
| `scripts/l1_ingest.py <file...>` | `l1-entity-output-v1` | `check_l1_dod` | [l1_outputs](../tables/l1_outputs.md) (+ [l1_tasks](../tables/l1_tasks.md)) |
| `scripts/agent_ingest.py <file...>` | `agent-output-v2-lean` (hoặc `agent-output-v1`) | `verify_preconditions` + `check_dod` | [agent_outputs](../tables/agent_outputs.md) (+ [work_items](../tables/work_items.md)) |

`article_run.py --wave W --finish` gọi cả hai, **chỉ** trên các tệp
`article_<W>_*.output.json` của đợt đó (trong `<DATA_ROOT>/agent_outputs_l1/` và
`<DATA_ROOT>/agent_outputs/`), sau bước bung bản ghi. Ingest lỗi ⇒ đợt dừng ngay.[^run]

# Bản ghi của Article Lane không có hàng đợi cũ

Article Lane chọn bài từ `articles` + `work_items` mà không đi qua định tuyến L1 cũ, nên:

- `L1Runner` tự ghi một hàng `l1_tasks` (`route = 'article_lane'`) khi bài chưa có, lấy tiêu đề
  từ bảng `articles` chứ không từ bản ghi mô hình — cổng vẫn đối chiếu với nguồn.[^l1-runner]
- `AgentRunner` tự đăng ký `work_items` + work-package khi thiếu, với `cleaned_text` đọc từ
  Silver.[^runner]

# Preconditions

`verify_preconditions()` chặn trước khi chấm:[^dod]
- `change_state ∈ {SELECTOR_BROKEN, TEMPLATE_DRIFT}` ⇒ không đạt.
- Toàn vẹn raw khi work-package trỏ Bronze: `sha256(raw_html_path) == raw_sha256`.

# Definition-of-Done — nội dung

Sáu tiêu chí thuần code, ngưỡng đọc từ `schemas/task-lifecycle-v1.yaml`:[^dod]

1. `schema_valid` — khớp `agent-output-v2-lean` hoặc `agent-output-v1`.
2. `grounded` — ≥ `min_citations` (2; bài một đoạn có `citation_basis = single-paragraph` chỉ
   cần 1), mỗi trích dẫn là chuỗi con nguyên văn của `cleaned_text`, dài ≥ 20 ký tự.
3. `quality_ok` — `extraction_quality ∈ {high, medium}` (chỉ schema v1).
4. `auditable` — `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp` (chỉ v1;
   v2-lean do hệ điền).
5. `value_added` — tóm tắt không chép nguyên văn bài; `key_points` không chép trích dẫn.
6. `implication_specific` — hàm ý ≥ `min_implication_len`, không chép bài, không là câu mẫu.

Đạt ⇒ `work_items.done`; trượt ⇒ `failed` + `dod_reasons`. `confidence` **không** phải cổng.

# Definition-of-Done — nhận diện thực thể

`check_l1_dod`: schema `l1-entity-output-v1` hợp lệ; mọi `surface` và `source_span` là chuỗi con
của **tiêu đề**; `recognized` nhất quán với `entities`/`citations`; nhóm `categories` đánh `done`
phải có entity `in_list` thuộc nhóm đó.[^l1-router]

Bản ghi `code_first` là tạm: bản ghi của mô hình được ghi đè lên nó, không bao giờ ngược lại
(ADR-0003).[^l1-runner]

# Idempotency

Ingest lại cùng bài đã đạt DoD trả *cached*, không ghi đôi (`UNIQUE(article_id, raw_sha256)` ở
`agent_outputs`, `UNIQUE(article_id)` ở `l1_outputs`).

# Quan hệ

- Đầu vào: bản ghi do bước expand của [Article Lane](article_lane.md) sinh
- Đầu ra: [User Output](user_output.md)
- Chỉ số: [DoD Pass Rate](../metrics/dod_pass_rate.md)

[^runner]: [AgentRunner](project/src/agent/ingest/runner.py)
[^l1-runner]: [L1Runner](project/src/agent/ingest/l1_runner.py)
[^dod]: [DoD](project/src/agent/contract/dod.py)
[^l1-router]: [check_l1_dod](project/src/agent/contract/l1_router.py)
[^run]: [article_run.py](project/src/ops/wave/article_run.py)
[^adr-0010]: [ADR-0010](docs/decisions/0010-ngung-lane-l1-gold-article-lane-duy-nhat.md)
