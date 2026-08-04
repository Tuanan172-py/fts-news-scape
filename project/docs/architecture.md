# Architecture & Technical Decisions

Cập nhật: 2026-07-24 (Phase 1 foundation refactor — SQLite-only, standalone).

## Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────┐
│                ORCHESTRATOR / SCHEDULER                      │
│  APScheduler (coalesce, max_instances=1) — Phase 6           │
│  Singleton: 1 cycle chạy xong mới chạy cycle tiếp            │
└────────────────────┬────────────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐        ┌──────────────┐
    ▼                ▼                ▼        │  MONITORING  │
┌──────────┐  ┌────────────┐  ┌──────────────┐ │  (loguru log │
│ RSS       │  │ REST API   │  │ HTML Request │ │  + heartbeat │
│ Scraper   │  │ Scraper    │  │ Scraper      │ │  Phase 4)    │
│ (generic) │  │ (per-domain)│ │ (per-domain) │ └──────────────┘
└─────┬─────┘  └──────┬─────┘  └──────┬───────┘
      │  đều là BaseScraper subclass  │
      └───────────────┼───────────────┘
                      ▼
            ┌──────────────────┐     Mỗi scraper trả ScrapeResult;
            │ PARSE + ENRICH   │     Article giữ CẢ content_html (raw)
            │  (per domain)    │     lẫn content_text (sạch)
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │   DEDUP          │  Lớp 1: SHA-256(url+title) — bảng seen_articles
            │                  │  Lớp 2: fuzzy title cross-domain (Phase 4)
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │ SENTIMENT ENGINE │  rule-based tiếng Việt (Phase 4)
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │  DBWriter thread │  single-writer queue, batch ≤50/txn
            │  → SQLite (WAL)  │  data/monocle.db — DB DUY NHẤT
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │  NOTIFY MODULE   │  file-based log + stdout (Phase 4)
            └──────────────────┘
```

## Thành phần chính (Phase 1)

| Module                         | Vai trò                                                                                                                             |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `src/core/models.py`         | `Article` (schema v2, raw HTML + text), `ScrapeResult`, `sha256_hash`                                                          |
| `src/core/base_scraper.py`   | `BaseScraper` ABC — template method `run()`: fetch → parse → dedup → enrich. Lỗi gom vào `errors`, không crash pipeline |
| `src/core/config.py`         | Config-driven:`config/domains/<name>.yaml` per domain, settings/watchlist/secrets                                                  |
| `src/core/logging.py`        | loguru:`logs/monocle.log` rotation 50MB, retention 14d                                                                             |
| `src/crawler/http_client.py` | Rate limit 3s/domain, retry 429/5xx, UA rotation, get/get_json/post_json                                                             |
| `src/db/store.py`            | SQLite WAL (`journal_mode=WAL, busy_timeout=5000, synchronous=NORMAL`), UNIQUE url + url_title_hash                                |
| `src/db/writer.py`           | DBWriter — single-writer thread, graceful shutdown (flush queue)                                                                    |
| `src/db/dedup.py`            | Bảng`seen_articles` cùng DB (migrate từ JSON cũ)                                                                               |
| `src/scrapers/`              | Registry`@register("name")` — thêm domain = 1 module + 1 yaml, không sửa core                                                  |

## Technical Decision Records

### TDR-001: RSS làm primary method

RSS > reverse API > HTML (spec §8). RSS coverage rộng, setup nhanh, ít vỡ.
API cho nguồn không có RSS đủ sâu (CafeF symbol-based, TNCK, FireAnt).

### TDR-002: trafilatura cho article extraction

newspaper3k abandoned. trafilatura v2 maintained, hỗ trợ tiếng Việt tốt.
Extractor trả cả raw HTML lẫn text — không throw away data.

### TDR-003: Dedup 2 lớp

Lớp 1: SHA-256(url+title) exact — bảng `seen_articles`.
Lớp 2: fuzzy title match cross-domain (rapidfuzz, Phase 4).

### TDR-004: SQLite-only, WAL, single-writer (2026-07-24)

Không ClickHouse/PostgreSQL ở phase này (spec §7). WAL + busy_timeout cho
concurrent reads; mọi ghi bảng articles qua 1 DBWriter thread duy nhất —
tránh SQLITE_BUSY, đơn giản hơn multi-writer coordination.

### TDR-005: Standalone, không phụ thuộc hệ thống ngoài (2026-07-24)

Toàn bộ orchestration nội bộ (APScheduler Phase 6). Notify = file/stdout,
không tích hợp bot/messaging ngoài ở phase này.

### TDR-006: Sync requests, không Scrapy/async (2026-07-24)

5-10 domains × rate limit 3s × cycle 15 phút → sequential đủ nhanh.
Async/Scrapy thêm phức tạp không cần thiết (YAGNI). Xem lại khi >20 domains.
