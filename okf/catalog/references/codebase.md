---
type: Reference
title: Cấu trúc Mã nguồn (Codebase Guide)
description: Hướng dẫn cấu trúc mã nguồn cốt lõi của Web Monocle — kiến trúc module hóa 9 subpackages.
resource: project/docs/dev/01-codebase-guide.md
tags: [codebase, reference, development, architecture]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: codebase-guide
    resource: project/docs/dev/01-codebase-guide.md
    title: Codebase Guide
    author: human:anpt
  - id: source-tree
    resource: project/src/
    title: Source tree
sources_last_checked: 2026-08-04
---

Mã nguồn của hệ thống Web Monocle được tổ chức theo kiến trúc module hóa để phục vụ việc mở rộng (thêm domain) mà không phải sửa đổi phần core. Entry point chính của hệ thống là `src/orchestrator.py`.[^codebase-guide]

## Kiến trúc các Module (`src/`) — 28 files, 9 subpackages

### `src/core/` — Lớp nền tảng dùng chung (7 files)

| File | Vai trò |
|---|---|
| `base_scraper.py` | Abstract Base Class `BaseScraper` — Template Method: `fetch_list()` → `parse_item()` → dedup → `enrich()` |
| `config.py` | Loader cho settings.yaml, domains/*.yaml, secrets.yaml, watchlist.yaml |
| `models.py` | Data Classes: `Article` (16 fields), `ScrapeResult`, `sha256_hash()`, `now_vn_iso()` |
| `logging.py` | Thiết lập Loguru: lưu 14 ngày, rotate 50MB, format có màu |
| `retry.py` | Retry decorator với exponential backoff |
| `tickers.py` | Xử lý mã chứng khoán — tách, chuẩn hóa, lookup từ watchlist |
| `__init__.py` | Package init |

### `src/crawler/` — HTTP Client (1 file)

| File | Vai trò |
|---|---|
| `http_client.py` | `HTTPClient` với `requests.Session`, `RateLimiter` per-domain (3s), 5 User-Agent xoay vòng, Retry strategy (3 lần, backoff 1.5x), `truststore` cho Windows cert |

### `src/scrapers/` — Domain Scrapers (5 files)

| File | Vai trò | Method |
|---|---|---|
| `rss_generic.py` | `RSSScraper` — dùng chung cho 18 domain RSS | RSS |
| `cafef.py` | Custom scraper cho cafef.vn | API (reverse-engineer) |
| `fireant.py` | Custom scraper cho fireant.vn (cần Bearer token) | API |
| `tnck.py` | Custom scraper cho tinnhanhchungkhoan.vn | API |
| `vndirect.py` | Aggregator scraper cho vndirect.com.vn | API |
| `__init__.py` | Registry pattern: `@register("cafef")` decorator + `REGISTRY` dict |

### `src/processor/` — NLP & Phân tích (4 files)

| File | Vai trò |
|---|---|
| `classifier.py` | Rule-based keyword classification (finance/tech/trading/cmt) |
| `sentiment.py` | Sentiment engine tiếng Việt: pyvi segment → n-gram lexicon match → negation flip → score |
| `extractor.py` | Trích xuất nội dung sạch từ HTML qua Trafilatura |
| `segment.py` | Tokenize tiếng Việt bằng Pyvi |

### `src/db/` — Database Layer (3 files)

| File | Vai trò |
|---|---|
| `store.py` | `ArticleStore` — SQLite schema v2 (5 tables), WAL mode, insert_batch, export |
| `writer.py` | `DBWriter` — Single-writer background thread, queue.Queue, batch insert |
| `dedup.py` | `DedupCache` — 2-layer dedup: exact hash + fuzzy title match (rapidfuzz) |

### `src/monitor/` — Giám sát (5 files)

| File | Vai trò |
|---|---|
| `health.py` | Health check endpoint |
| `heartbeat.py` | Ghi trạng thái scraper vào `scraper_heartbeat` |
| `domain_reporter.py` | Báo cáo metrics theo domain |
| `domain_validator.py` | Kiểm tra domain config hợp lệ |
| `__init__.py` | Package init |

### `src/notifier/` — Thông báo (2 files)

| File | Vai trò |
|---|---|
| `file_notify.py` | File-based notification — ghi file .txt khi có bài mới khớp watchlist |
| `__init__.py` | Package init |

### `src/export/` — Xuất dữ liệu (2 files)

| File | Vai trò |
|---|---|
| `csv_export.py` | Xuất articles ra CSV |
| `__init__.py` | Package init |

### `src/orchestrator.py` — Entry Point

Điều phối toàn bộ pipeline. Xem chi tiết tại [Web Monocle Orchestrator](../pipelines/ingestion_scheduler.md).

## Dependency Injection

Orchestrator khởi tạo tất cả services và inject qua constructor:
```
Orchestrator
├── ArticleStore (DB)
├── DBWriter (single-writer thread)
├── HTTPClient (shared session)
├── DedupCache (in-memory hash set)
├── Heartbeat (monitoring)
├── FileNotifier (alerts)
└── SentimentEngine (NLP)
```

Mỗi scraper nhận `HTTPClient` và `DedupCache` qua constructor, không tự tạo instance riêng.

[^codebase-guide]: [Codebase Guide](project/docs/dev/01-codebase-guide.md)
[^source-tree]: [Source tree](project/src/)
