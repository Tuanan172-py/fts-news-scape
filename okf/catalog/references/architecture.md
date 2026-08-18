---
type: Reference
title: Kiến trúc Hệ thống (System Architecture)
description: Sơ đồ kiến trúc tổng thể Web Monocle — thành phần, luồng dữ liệu, và mối quan hệ giữa các module.
resource: project/docs/design/01-system-overview.md
tags: [architecture, design, overview]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
verified:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: system-overview
    resource: project/docs/design/01-system-overview.md
    title: System Overview
    author: human:anpt
  - id: execution-flow
    resource: project/docs/design/02-execution-flow.md
    title: Execution Flow
sources_last_checked: 2026-08-04
stale_after: 2026-12-31
---

# Kiến trúc Tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│                     APSCHEDULER (15 phút)                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   ORCHESTRATOR                             │   │
│  │                                                            │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │ for each enabled domain:                            │  │   │
│  │  │                                                     │  │   │
│  │  │  REGISTRY[domain] → Scraper                         │  │   │
│  │  │       │                                             │  │   │
│  │  │       ├── cafef.py     (API, 1 req/mã/chu kỳ)      │  │   │
│  │  │       ├── fireant.py   (API, Bearer token)          │  │   │
│  │  │       ├── tnck.py      (API, zone × page)           │  │   │
│  │  │       ├── vndirect.py  (API, aggregator)            │  │   │
│  │  │       └── rss_generic.py (RSS, 18 domain)           │  │   │
│  │  │                                                     │  │   │
│  │  │  Each Scraper.run():                                │  │   │
│  │  │    fetch_list() → parse_item() → dedup → enrich()   │  │   │
│  │  │         │                │           │        │      │  │   │
│  │  │         ▼                ▼           ▼        ▼      │  │   │
│  │  │   [HTTPClient]    [Trafilatura] [DedupCache] [HTTP] │  │   │
│  │  │                                                     │  │   │
│  │  │  → ScrapeResult (list[Article])                     │  │   │
│  │  └──────────────────┬──────────────────────────────────┘  │   │
│  │                     ▼                                      │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │ POST-PROCESSING (per article)                       │  │   │
│  │  │  1. Classify (rule-based → categories)              │  │   │
│  │  │  2. Sentiment (pyvi → lexicon → score)              │  │   │
│  │  └──────────────────┬──────────────────────────────────┘  │   │
│  │                     ▼                                      │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │ DBWriter.enqueue(article) → queue.Queue             │  │   │
│  │  └──────────────────┬──────────────────────────────────┘  │   │
│  └─────────────────────┼──────────────────────────────────────┘   │
│                        ▼                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   DBWRITER (daemon thread)                │   │
│  │  queue.Queue → batch 50 → ArticleStore.insert_batch()    │   │
│  │  → SQLite WAL (data/monocle.db)                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  POST-CYCLE                                              │   │
│  │  • FileNotifier → watchlist alerts                       │   │
│  │  • CSV Export → data/exports/                            │   │
│  │  • WAL Checkpoint (if DB > 100MB)                        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

# Thành phần chính

| Thành phần | Module | Vai trò |
|---|---|---|
| **Orchestrator** | `src/orchestrator.py` | Điều phối toàn bộ pipeline |
| **HTTPClient** | `src/crawler/http_client.py` | HTTP session dùng chung, rate limit, retry |
| **Scrapers** | `src/scrapers/` | RSS + API reverse-engineer cho 23 domain |
| **DedupCache** | `src/db/dedup.py` | 2-layer dedup: exact hash + fuzzy title |
| **Classifier** | `src/processor/classifier.py` | Rule-based keyword classification |
| **Sentiment Engine** | `src/processor/sentiment.py` | VN NLP sentiment scoring |
| **DBWriter** | `src/db/writer.py` | Single-writer thread |
| **ArticleStore** | `src/db/store.py` | SQLite schema v2, CRUD operations |
| **Heartbeat** | `src/monitor/heartbeat.py` | Ghi trạng thái scraper |
| **FileNotifier** | `src/notifier/file_notify.py` | File-based alert system |

# Dependency Injection

```
Orchestrator.__init__():
  self.store     = ArticleStore(settings.database.path)
  self.writer    = DBWriter(self.store)
  self.http      = HTTPClient(settings.http)
  self.dedup     = DedupCache(self.store)
  self.heartbeat = Heartbeat(self.store)
  self.notifier  = FileNotifier(settings.notifications)
  self.sentiment = SentimentEngine()

build_scraper(cfg, http=self.http, dedup=self.dedup)
  → Các scraper dùng chung HTTPClient và DedupCache
```

# Tài liệu liên quan

- [Orchestrator](../pipelines/ingestion_scheduler.md) — Chi tiết luồng execution
- [DBWriter](../pipelines/db_writer.md) — Single-writer thread
- [Sentiment Pipeline](../pipelines/sentiment_pipeline.md) — Phân tích cảm xúc
- [Codebase Guide](codebase.md) — Cấu trúc mã nguồn chi tiết

[^system-overview]: [System Overview](project/docs/design/01-system-overview.md)
[^execution-flow]: [Execution Flow](project/docs/design/02-execution-flow.md)
