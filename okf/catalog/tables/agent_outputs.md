---
type: SQLite Table
title: agent_outputs
description: Bản ghi nội dung (agent-output-v2-lean, đọc cả v1) — tóm tắt, luận điểm, hàm ý, sentiment, trích dẫn — do Article Lane nạp sau cổng DoD.
resource: "<DATA_ROOT>/monocle.db (table: agent_outputs)"
tags: [agent, gold, dod, output]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: runner
    resource: project/src/agent/ingest/runner.py
    title: AgentRunner.ingest_output
  - id: dod
    resource: project/src/agent/contract/dod.py
    title: Definition-of-Done — 6 tiêu chí
sources_last_checked: 2026-10-22
---

`agent_outputs` lưu **1 bản ghi nội dung / bản raw**: tóm tắt, luận điểm, hàm ý thị trường,
sentiment, time_sensitivity, trích dẫn. Bản ghi do bước expand của
[Article Lane](../pipelines/article_lane.md) bung ra theo `agent-output-v2-lean`, rồi
`scripts/agent_ingest.py` validate + chấm DoD trước khi ghi.[^runner] Các trường `materiality`,
`event_type`, `impact_area` đã bỏ.

Idempotency key `UNIQUE(article_id, raw_sha256)` ⇒ ingest lại cùng bài + cùng bản raw trả
*cached*, không double-mark [work_items](work_items.md).

# Definition-of-Done (`dod_pass = 1`)

Mọi tiêu chí phải đạt, kiểm tra thuần bằng code:[^dod]

1. **schema_valid** — khớp `agent-output-v2-lean` (hoặc `agent-output-v1`).
2. **grounded** — ≥ 2 trích dẫn (1 nếu bài một đoạn), mỗi trích dẫn là **chuỗi con nguyên văn**
   của `cleaned_text` và dài ≥ 20 ký tự.
3. **quality_ok** — `extraction_quality ∈ {high, medium}` (chỉ v1).
4. **auditable** — `processing_metadata` đủ trường (chỉ v1; v2-lean do hệ điền).
5. **value_added** — tóm tắt/luận điểm không chép nguyên văn.
6. **implication_specific** — hàm ý ≥ 40 ký tự, không chép bài, không là câu mẫu.

> `confidence` **không còn là gate** (bỏ 2026-08-18): agent tự khai, calibration kém. Cột vẫn
> được lưu để audit nhưng không dùng để quyết định pass/fail.

Fail ⇒ `dod_pass=0` + `dod_reasons` (JSON list) → work_item `failed`.

# Schema

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `article_id` | TEXT NOT NULL | = `articles.url_title_hash` |
| `raw_sha256` | TEXT NOT NULL | Bản raw Bronze mà output này bám vào |
| `work_item_id` | INTEGER | Trỏ [work_items](work_items.md).`id` |
| `output_json` | TEXT NOT NULL | Toàn bộ bản ghi (`agent-output-v2-lean` hoặc v1) |
| `agent_provider` | TEXT | Rút từ `processing_metadata` (audit) |
| `model_used` | TEXT | Model đã dùng |
| `confidence` | REAL | Agent tự khai — **không** phải gate |
| `dod_pass` | INTEGER DEFAULT 0 | 1 = qua DoD |
| `dod_reasons` | TEXT | JSON list lý do fail (rỗng nếu pass) |
| `created_at` | TEXT | Thời điểm ingest |

**Constraints:** `UNIQUE(article_id, raw_sha256)` ·
**Index:** `idx_agent_outputs_dod` `(dod_pass, created_at)` · `idx_agent_outputs_article_dod` `(article_id, dod_pass)`

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
- [l1_outputs](l1_outputs.md) qua `article_id` — bản nhận diện là gate bắt buộc, bản nội dung tuỳ chọn
- [work_items](work_items.md) qua `work_item_id`

# Pipeline liên quan

- [Agent Ingest & cổng DoD](../pipelines/agent_handoff.md) · [User Output](../pipelines/user_output.md)

# Metrics

- [DoD Pass Rate](../metrics/dod_pass_rate.md) · [Sentiment Distribution](../metrics/sentiment_distribution.md)

[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^runner]: [AgentRunner](project/src/agent/ingest/runner.py)
[^dod]: [DoD predicates](project/src/agent/contract/dod.py)
