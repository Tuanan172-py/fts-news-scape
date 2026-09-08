---
type: SQLite Table
title: agent_outputs
description: Kết quả Lớp 2 (Gold — tóm tắt/hàm ý/materiality) do agent ngoài nộp, đã qua cổng DoD.
resource: "project/data/monocle.db (table: agent_outputs)"
tags: [agent, gold, dod, output]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: runner
    resource: project/src/agent/runner.py
    title: AgentRunner — export_tasks / ingest_output
  - id: dod
    resource: project/src/agent/dod.py
    title: Definition-of-Done predicates
  - id: agent-io
    resource: project/docs/design/09-agent-io-contract.md
    title: Agent I/O contract
sources_last_checked: 2026-09-07
---

`agent_outputs` lưu **1 output chuẩn / bản raw** của Lớp 2 nghiệp vụ (Gold — Financial Analyst):
tóm tắt, hàm ý thị trường, điểm materiality, sentiment, citations. Producer **không có LLM**;
hàng ở đây do agent NGOÀI nộp file JSON rồi `scripts/agent_ingest.py` validate + chấm DoD trước
khi ghi.[^runner]

Idempotency key `UNIQUE(article_id, raw_sha256)` ⇒ ingest lại cùng bài + cùng bản raw trả
*cached*, không double-mark [work_items](work_items.md).

# Definition-of-Done (`dod_pass = 1`)

Tất cả 4 predicate phải đạt, kiểm tra thuần bằng code, không gọi LLM:[^dod]

1. **schema_valid** — khớp `agent-output-v1.schema.json`.
2. **grounded** — ≥ 2 `citations`, mỗi `source_span` là **chuỗi con nguyên văn** của
   `input.cleaned_text` và dài ≥ 20 ký tự.
3. **quality_ok** — `extraction_quality ∈ {high, medium}`.
4. **auditable** — `processing_metadata` đủ `agent_provider`, `model_used`, `timestamp`.

> `confidence` **không còn là gate** (bỏ 2026-08-18): agent tự khai, calibration kém. Cột vẫn
> được lưu để audit nhưng không dùng để quyết định pass/fail.

Fail ⇒ `dod_pass=0` + `dod_reasons` (JSON list) → work_item `failed`, và vòng self-healing gửi
lý do lại cho agent sửa.

# Schema

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `article_id` | TEXT NOT NULL | = `articles.url_title_hash` |
| `raw_sha256` | TEXT NOT NULL | Bản raw Bronze mà output này bám vào |
| `work_item_id` | INTEGER | Trỏ [work_items](work_items.md).`id` |
| `output_json` | TEXT NOT NULL | Toàn bộ `agent-output-v1` nguyên bản agent nộp |
| `agent_provider` | TEXT | Rút từ `processing_metadata` (audit) |
| `model_used` | TEXT | Model đã dùng |
| `confidence` | REAL | Agent tự khai — **không** phải gate |
| `dod_pass` | INTEGER DEFAULT 0 | 1 = qua DoD |
| `dod_reasons` | TEXT | JSON list lý do fail (rỗng nếu pass) |
| `created_at` | TEXT | Thời điểm ingest |

**Constraints:** `UNIQUE(article_id, raw_sha256)` ·
**Index:** `idx_agent_outputs_dod` trên `(dod_pass, created_at)`

# Common Query Patterns

### Tỷ lệ pass DoD 7 ngày

```sql
SELECT date(created_at) AS d,
       SUM(dod_pass) AS passed,
       COUNT(*)      AS total,
       ROUND(SUM(dod_pass) * 100.0 / COUNT(*), 1) AS pass_pct
FROM agent_outputs
WHERE created_at >= datetime('now', '-7 days', 'localtime')
GROUP BY d ORDER BY d DESC;
```

### Lý do fail phổ biến

```sql
SELECT dod_reasons, COUNT(*) AS n
FROM agent_outputs
WHERE dod_pass = 0
GROUP BY dod_reasons ORDER BY n DESC LIMIT 20;
```

# Joins

- [articles](articles.md) qua `article_id = url_title_hash`
- [l1_outputs](l1_outputs.md) qua `article_id` — hai lớp cùng gate cho deliverable
- [work_items](work_items.md) qua `work_item_id`

# Pipeline liên quan

- [Agent Handoff](../pipelines/agent_handoff.md) · [User Output](../pipelines/user_output.md)

# Metrics

- [DoD Pass Rate](../metrics/dod_pass_rate.md) · [Sentiment Distribution](../metrics/sentiment_distribution.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^runner]: [AgentRunner](project/src/agent/runner.py)
[^dod]: [DoD predicates](project/src/agent/dod.py)
[^agent-io]: [Agent I/O contract](project/docs/design/09-agent-io-contract.md)
