---
type: Metric
title: DoD Pass Rate
description: Tỷ lệ bản ghi mô hình qua cổng Definition-of-Done — thước đo chất lượng của Article Lane theo runner/model.
tags: [metric, agent, dod, quality]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: dod
    resource: project/src/agent/contract/dod.py
    title: check_dod — 6 tiêu chí
  - id: runner
    resource: project/src/agent/ingest/runner.py
    title: ingest_output
  - id: db-store
    resource: project/src/db/store.py
    title: DDL agent_outputs / l1_outputs
sources_last_checked: 2026-10-22
---

# Definition

`DoD Pass Rate = COUNT(dod_pass = 1) / COUNT(*)` trên
[agent_outputs](../tables/agent_outputs.md) (nội dung) và [l1_outputs](../tables/l1_outputs.md)
(nhận diện; loại hàng `l1_source = 'code_first'`).

Đây là **thước đo chất lượng mô hình**, không phải sức khoẻ hạ tầng: pass thấp nghĩa là persona
hoặc model chưa đáp ứng hợp đồng, không phải pipeline hỏng. Chấm provider so với tập vàng và
mốc agy: `scripts/provider_conformance.py` (ADR 0017).

# Computation

### Theo ngày, bản nội dung

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
| Pass rate bản nội dung | > 85% | < 70% |
| Pass rate bản nhận diện | > 95% | < 85% |
| Tỷ lệ trượt do citation | < 10% | > 25% ⇒ sửa persona/chắt lọc |

# Diễn giải lý do trượt

| Lý do | Ý nghĩa |
|---|---|
| `citation[i] not grounded in cleaned_text` | agent bịa hoặc diễn giải lại thay vì trích nguyên văn |
| `citation[i] source_span too short (<20 chars)` | trích quá ngắn ⇒ groundedness giả |
| `citations N < 2` | thiếu số lượng trích dẫn tối thiểu |
| `summary.abstractive là trích nguyên văn …` / `key_points[i] copy nguyên văn …` | không thêm giá trị (`value_added`) |
| `implication.text < 40 ký tự` / `… boilerplate` | hàm ý sơ sài hoặc câu mẫu (`implication_specific`) |
| `extraction_quality=... not in ('high','medium')` | chỉ schema v1 — payload nghèo, có thể do selector hỏng ở Bronze |
| `schema_invalid: …` | bản ghi sai cấu trúc |
| `processing_metadata.X missing` | chỉ schema v1 — thiếu trường audit |

Trượt vì `extraction_quality` lặp lại ở **cùng một domain** ⇒ vấn đề nằm ở
[Source config](../configurations/domain_sources.md), không phải ở agent.

# Liên quan

- [Agent Ingest & cổng DoD](../pipelines/agent_handoff.md) · [Agent Contracts & DoD](../references/agent_contracts.md)
- [Silver Backlog](silver_backlog.md)
