---
type: Python Pipeline
title: Capture Orchestrator (Vòng 1)
description: Điều phối scraper theo chu kỳ — fetch list, dedup, capture Bronze byte-exact, classify, enqueue DBWriter.
resource: project/src/orchestrator.py
tags: [pipeline, ingestion, capture, bronze, apscheduler]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: orchestrator
    resource: project/src/orchestrator.py
    title: Orchestrator.run_cycle
  - id: base-scraper
    resource: project/src/core/base_scraper.py
    title: BaseScraper template method
  - id: capture-mixin
    resource: project/src/scrapers/capture_mixin.py
    title: CaptureMixin
  - id: execution-flow
    resource: project/docs/design/02-execution-flow.md
    title: Execution Flow
sources_last_checked: 2026-10-22
---

`src/orchestrator.py` là **Vòng 1 — Capture** trong kiến trúc 3 vòng: lấy tin mới và ghi bản raw
byte-exact xuống [Bronze](../datasets/bronze_raw_html.md). Đây là *hot path* online, cố ý tách
khỏi phần chuẩn hoá offline.[^execution-flow]

> Ở môi trường prod, orchestrator **không chạy trực tiếp** mà được [Morninger](morninger.md) gọi
> như job `capture`. Chạy `python -m src.orchestrator` là chế độ standalone/fallback.

# Execution flow — 1 cycle

```
run_cycle(names)
  ├─ refresh advisory lock "scheduler"        (pipeline_state)
  └─ for each domain enabled:
       load_domain_config → build_scraper (REGISTRY factory)
       heartbeat.record_start
       run_with_retry / run_with_fallback
          └─ BaseScraper.run(): fetch_list → parse_item → dedup → enrich()
                enrich(): robots gate → backoff → fetch detail
                          → RawStore.save (.html + .meta.json)  ← BRONZE, trước mọi xử lý
                          → extract (trafilatura)
       classify_rule_based(title, text) → gắn categories
       writer.enqueue(article)
       heartbeat.record_result
  ├─ notifier.notify_articles + notify_cycle_summary   (lỗi ở đây không làm hỏng cycle)
  ├─ writer.flush()                                    (commit trước khi export)
  ├─ _export_csv()   → <DATA_ROOT>/exports/articles-YYYY-MM-DD.csv (ghi đè mỗi cycle)
  └─ _wal_checkpoint()  → PRAGMA wal_checkpoint(TRUNCATE)
```

Cycle không tính sentiment: chỉ có `classify_rule_based` gắn `categories`. Sentiment của
deliverable do mô hình sinh trong [Article Lane](article_lane.md) và nằm ở
[agent_outputs](../tables/agent_outputs.md); engine rule-based cũ đã xoá.

# CLI

```powershell
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator             # scheduler liên tục
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator --once      # 1 cycle rồi thoát
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator --once cafef tnck
C:\venvs\news-scape\Scripts\python.exe scripts\run_once.py [domain...]  # tương đương --once
```

# Bất biến & ràng buộc

| Ràng buộc | Giá trị | Nguồn |
|---|---|---|
| Chu kỳ | standalone: `scheduler.interval_minutes` (15′); dưới morninger: `morninger.capture_interval_minutes` (10′); `coalesce=True`, `max_instances=1`, misfire 300s | [settings.yaml](../configurations/settings.md) |
| Rate limit | ≥3 giây / domain | `http.rate_limit` |
| Timeout | 30 giây | `http.timeout` |
| Retry | 3 lần + fallback method | `src/core/retry.py` |
| Đơn tiến trình | file lock `capture.lock` cạnh DB (cả `--once` lẫn scheduler) + advisory lock `lock:scheduler`, stale 40′ | `src/core/proclock.py`, [pipeline_state](../tables/pipeline_state.md) |

**Graceful degradation** — 1 domain lỗi không làm hỏng domain khác; lỗi notify/export không làm
hỏng cycle. **Graceful shutdown** — SIGINT/SIGTERM ⇒ flush [DBWriter](db_writer.md), WAL
checkpoint, nhả lock.

**Bronze-first**: chỉ domain có capture raw HTML mới được `enabled` — `method: rss` generic
không lưu Bronze nên bị tắt có chủ đích.[^capture-mixin] Xem
[Source Strategy](../configurations/source_strategy.md).

# Quan hệ

- Ghi [Bronze raw store](../datasets/bronze_raw_html.md), [articles](../tables/articles.md),
  [seen_articles](../tables/seen_articles.md), [scraper_heartbeat](../tables/scraper_heartbeat.md),
  [scraper_metrics](../tables/scraper_metrics.md)
- Được điều phối bởi [Morninger](morninger.md); tiếp nối bởi [Silver Derive](silver_derive.md)

[^orchestrator]: [Orchestrator](project/src/orchestrator.py)
[^base-scraper]: [BaseScraper](project/src/core/base_scraper.py)
[^capture-mixin]: [CaptureMixin](project/src/scrapers/capture_mixin.py)
[^execution-flow]: [Execution Flow](project/docs/design/02-execution-flow.md)
