---
type: Metric
title: DoD Pass Rate
description: Tỷ lệ output agent qua cổng Definition-of-Done ngay lần nộp đầu — thước đo chất lượng lớp Gold.
tags: [metric, agent, dod, quality]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: dod
    resource: project/src/agent/dod.py
    title: check_dod — 4 predicate
  - id: runner
    resource: project/src/agent/runner.py
    title: ingest_output
  - id: db-store
    resource: project/src/db/store.py
    title: DDL agent_outputs / l1_outputs
sources_last_checked: 2026-09-07
---

# Definition

`DoD Pass Rate = COUNT(dod_pass = 1) / COUNT(*)` trên
[agent_outputs](../tables/agent_outputs.md) (Lớp 2) và [l1_outputs](../tables/l1_outputs.md)
(Lớp 1).

Đây là **thước đo chất lượng agent**, không phải sức khoẻ hạ tầng: pass thấp nghĩa là prompt
hoặc model chưa đáp ứng hợp đồng, không phải pipeline hỏng.

# Computation

### Theo ngày, Lớp 2

```sql
SELECT date(created_at) AS d,
       COUNT(*)        AS total,
       SUM(dod_pass)   AS passed,
       ROUND(SUM(dod_pass) * 100.0 / COUNT(*), 1) AS pass_pct
FROM agent_outputs
WHERE created_at >= datetime('now', '-7 days', 'localtime')
GROUP BY d ORDER BY d DESC;
```

### Theo model / provider

```sql
SELECT agent_provider, model_used,
       COUNT(*) AS total,
       ROUND(SUM(dod_pass) * 100.0 / COUNT(*), 1) AS pass_pct
FROM agent_outputs
WHERE created_at >= datetime('now', '-7 days', 'localtime')
GROUP BY agent_provider, model_used
ORDER BY total DESC;
```

### Lý do trượt phổ biến

```sql
SELECT dod_reasons, COUNT(*) AS n
FROM agent_outputs
WHERE dod_pass = 0
GROUP BY dod_reasons ORDER BY n DESC LIMIT 20;
```

# Target

| Chỉ số | Target | Cảnh báo |
|---|---|---|
| Pass rate Lớp 2 (lần nộp đầu) | > 85% | < 70% |
| Pass rate Lớp 1 | > 95% | < 85% |
| Tỷ lệ trượt do citation | < 10% | > 25% ⇒ sửa prompt/pruner |

# Diễn giải lý do trượt

| Lý do | Ý nghĩa |
|---|---|
| `citation[i] not grounded in cleaned_text` | agent bịa hoặc diễn giải lại thay vì trích nguyên văn |
| `citation[i] source_span too short (<20 chars)` | trích quá ngắn ⇒ groundedness giả |
| `citations N < 2` | thiếu số lượng trích dẫn tối thiểu |
| `extraction_quality=... not in ('high','medium')` | payload nghèo — có thể do selector hỏng ở Bronze |
| `schema_invalid: …` | output sai cấu trúc ⇒ ép JSON Schema ở phía provider |
| `processing_metadata.X missing` | thiếu trường audit |

Trượt vì `extraction_quality` lặp lại ở **cùng một domain** ⇒ vấn đề nằm ở
[Source config](../configurations/domain_sources.md), không phải ở agent.

# Liên quan

- [Agent Handoff](../pipelines/agent_handoff.md) · [Agent Contracts & DoD](../references/agent_contracts.md)
- [Silver Backlog](silver_backlog.md)
