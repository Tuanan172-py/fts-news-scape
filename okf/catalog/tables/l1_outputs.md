---
type: SQLite Table
title: l1_outputs
description: Bản ghi nhận diện thực thể (l1-entity-output-v1) đã qua DoD, do Article Lane nạp — nguồn định tuyến tin tới người dùng.
resource: "<DATA_ROOT>/monocle.db (table: l1_outputs)"
tags: [agent, l1, entity-recognition, dod, routing]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: l1-runner
    resource: project/src/agent/ingest/l1_runner.py
    title: L1Runner.ingest_output
  - id: l1-router
    resource: project/src/agent/contract/l1_router.py
    title: check_l1_dod
  - id: user-output
    resource: project/src/export/user_output.py
    title: Định tuyến theo entities[in_list]
sources_last_checked: 2026-10-22
---

`l1_outputs` giữ **1 hàng / article** (UNIQUE `article_id`) — bản ghi `l1-entity-output-v1` do
bước expand của [Article Lane](../pipelines/article_lane.md) bung ra và `l1_ingest.py` nạp sau
khi qua validate schema + DoD.[^l1-runner]

Đây là **bảng định tuyến**: trường `entities[].entity_id` (những entity có `in_list`) trong
`output_json` quyết định bài này thuộc về người dùng nào, qua `EntityRegistry.subscribers_for()`
trong [User Output](../pipelines/user_output.md).[^user-output]

# Definition-of-Done (`dod_pass = 1`)

`check_l1_dod(output, title)` — thuần code, không LLM:[^l1-router]

1. **schema_valid** — khớp `l1-entity-output-v1.schema.json`.
2. **grounding** — bằng chứng bề mặt (surface / citation) phải nằm trong **tiêu đề** của
   [l1_tasks](l1_tasks.md), không được bịa.
3. **nhất quán** — `recognized` khớp `entities`/`citations`; nhóm `categories` đánh `done` phải
   có entity `in_list` thuộc nhóm.

> `confidence` **không** phải gate — vẫn lưu để audit.

Pass ⇒ `l1_tasks.status = done`. Fail ⇒ `failed` + `dod_reasons`.

# Schema

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `article_id` | TEXT NOT NULL **UNIQUE** | = `articles.url_title_hash` |
| `output_json` | TEXT NOT NULL | Toàn bộ `l1-entity-output-v1` nguyên bản |
| `recognized` | INTEGER | 1 nếu agent nhận ra ≥1 thực thể |
| `agent_provider` | TEXT | Rút từ `processing_metadata` |
| `model_used` | TEXT | Model đã dùng |
| `confidence` | REAL | Agent tự khai — không phải gate |
| `dod_pass` | INTEGER DEFAULT 0 | 1 = qua DoD |
| `dod_reasons` | TEXT | JSON list lý do fail |
| `created_at` | TEXT | Thời điểm ingest |
| `l1_source` | TEXT NOT NULL DEFAULT `'agent'` | `agent` (mô hình) hoặc `code_first` (tra danh mục tất định); bản `agent` ghi đè `code_first`, không bao giờ ngược lại (ADR-0003) |

**Index:** `idx_l1_outputs_dod` `(dod_pass, created_at)` · `idx_l1_outputs_article_dod` `(article_id, dod_pass)` · `idx_l1_outputs_source` `(l1_source, dod_pass)`. Cột `l1_source` được thêm cho DB cũ qua `ArticleStore._MIGRATIONS`.

# Common Query Patterns

### Tỷ lệ nhận diện được thực thể

```sql
SELECT date(created_at) AS d,
       SUM(recognized) AS recognized,
       COUNT(*)        AS total
FROM l1_outputs
WHERE dod_pass = 1 AND created_at >= datetime('now', '-7 days', 'localtime')
GROUP BY d ORDER BY d DESC;
```

### Bài đủ điều kiện vào deliverable người dùng

```sql
SELECT a.url_title_hash, a.title
FROM articles a
JOIN l1_outputs l1 ON l1.article_id = a.url_title_hash AND l1.dod_pass = 1
                  AND l1.l1_source <> 'code_first'
LEFT JOIN agent_outputs ag ON ag.article_id = a.url_title_hash AND ag.dod_pass = 1
WHERE date(COALESCE(a.published_at, a.fetched_at)) = date('now', 'localtime');
```

Gate trong code: bản nhận diện **đã được mô hình phân tích** là bắt buộc (`analyzed_l1_sql`:
`dod_pass = 1` và không phải `code_first`, ADR-0010 D4); bản nội dung (`agent_outputs`) là LEFT
JOIN — thiếu thì dòng ra với `Gold Status = Preliminary`.[^user-output]

# Joins

- [l1_tasks](l1_tasks.md), [articles](articles.md), [agent_outputs](agent_outputs.md) qua `article_id`

# Pipeline liên quan

- [Agent Ingest & cổng DoD](../pipelines/agent_handoff.md) · [User Output](../pipelines/user_output.md)

# Metrics

- [DoD Pass Rate](../metrics/dod_pass_rate.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^l1-runner]: [L1Runner](project/src/agent/ingest/l1_runner.py)
[^l1-router]: [check_l1_dod](project/src/agent/contract/l1_router.py)
[^user-output]: [UserOutputWriter](project/src/export/user_output.py)
