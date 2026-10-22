# Thiết kế — Tổng quan hệ thống

Cập nhật: 2026-07-26 · Đối tượng: kiến trúc sư, tech lead, người mới cần bức tranh lớn.

## 1. Web Monocle là gì

Hệ thu thập tin tức thị trường chứng khoán Việt Nam, chạy standalone, poll định kỳ
23 nguồn (báo VN, sàn HOSE/HNX, API môi giới, báo tài chính quốc tế), chuẩn hoá về
một schema chung, chấm sentiment tiếng Việt bằng luật, khử trùng lặp cross-domain,
lưu vào **một** file SQLite và bắn thông báo ra file/stdout.

Không có service ngoài, không message queue, không DB server, không LLM. Toàn bộ là
một tiến trình Python + APScheduler + SQLite (WAL).

## 2. Triết lý thiết kế

| Nguyên tắc | Biểu hiện trong code |
|---|---|
| **Config-driven** | Thêm nguồn RSS = 1 file YAML, 0 dòng code. 18/23 domain dùng chung `RSSScraper`. |
| **Graceful degradation** | Lỗi fetch/parse/enrich gom vào `errors[]`, không bao giờ raise ra pipeline (`base_scraper.py:40-77`). 1 nguồn chết không kéo cả cycle. |
| **Không vứt dữ liệu** | `Article` giữ CẢ `content_html` (raw) lẫn `content_text` (sạch). Bóc tách sai vẫn còn HTML gốc để xử lại. |
| **Single-writer** | Mọi ghi bảng `articles` qua 1 thread `DBWriter` → tránh `SQLITE_BUSY`, không cần điều phối multi-writer. |
| **Deterministic, không LLM** | Sentiment + classify bằng lexicon/regex → rẻ, nhanh, tái lập được, không phụ thuộc API ngoài. |
| **YAGNI/KISS** | Sync `requests`, không async/Scrapy. 5-22 domain × 3s rate limit × 15 phút → tuần tự là đủ (TDR-006). |

## 3. Sơ đồ khối

```
        ┌──────────────────────────────────────────────┐
        │  ORCHESTRATOR (APScheduler, 15 phút/cycle)   │
        │  coalesce=True, max_instances=1 → singleton  │
        └───────────────────────┬──────────────────────┘
                                │  run_cycle(names)
             ┌──────────────────┼──────────────────┐
             ▼                  ▼                  ▼
      ┌────────────┐    ┌────────────┐    ┌────────────┐    Mỗi scraper =
      │ RSSScraper │    │ API scraper│    │ API scraper│    BaseScraper subclass
      │ (_rss, ×18)│    │ cafef/tnck │    │ vndirect/  │    → trả ScrapeResult
      │            │    │            │    │ fireant    │
      └─────┬──────┘    └─────┬──────┘    └─────┬──────┘
            └─────────────────┼─────────────────┘
                              ▼  BaseScraper.run(): fetch → parse → DEDUP → enrich
                    ┌──────────────────┐
                    │ POST-PROCESS     │  (trong orchestrator, KHÔNG trong scraper)
                    │  classify (regex)│
                    │  sentiment (VN)  │  EN → neutral/0.0 cứng
                    └────────┬─────────┘
                             ▼  writer.enqueue(article)
                    ┌──────────────────┐
                    │ DBWriter thread  │  queue, batch ≤50, INSERT OR IGNORE
                    │  → SQLite (WAL)  │  data/monocle.db
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │ NOTIFY + MONITOR │  file log + stdout · heartbeat/metrics
                    └──────────────────┘
```

## 4. Ba lớp scraper, một khuôn

Mọi scraper kế thừa `BaseScraper` và cài 2 hook bắt buộc `fetch_list()` + `parse_item()`,
tuỳ chọn `enrich()`. Khác biệt chỉ nằm ở cách lấy dữ liệu:

- **RSS** (`_rss`) — feed XML, dùng chung 1 class cho 18 domain. Khác biệt = YAML.
- **REST API** (`cafef`, `tnck`, `vndirect`, `fireant`) — mỗi nguồn 1 module vì response
  schema + quirk riêng (xem [domains/api-scrapers.md](../domains/api-scrapers.md)).
- **Official exchange** (`hose`, `hnx`) — vẫn qua `RSSScraper` nhưng là Layer 0 (công bố
  chính thống), cấu hình summary-only vì trang chi tiết là SPA.

Đăng ký bằng decorator `@register("name")` (`scrapers/__init__.py`). Orchestrator không
biết tên scraper cụ thể — nó `build_scraper(cfg)` từ field `method` trong YAML.

## 5. Vòng dữ liệu một bài báo

1. Scraper `fetch_list()` → list dict thô.
2. `parse_item()` → `Article` (url, title, summary, symbols, published_at, `metadata.language`).
3. **Dedup** 2 lớp: hash SHA-256(url+title) exact + fuzzy title cross-domain (rapidfuzz ≥90, 48h).
4. `enrich()` → tải chi tiết, điền `content_html`/`content_text` (có cap `max_details_per_cycle`).
5. Orchestrator: `classify` (regex) + `sentiment` (lexicon VN; EN ép neutral).
6. `writer.enqueue()` → DBWriter batch `INSERT OR IGNORE` vào SQLite.
7. Notifier khớp rule → ghi `data/notifications/YYYY-MM-DD.log` + stdout.

Chi tiết từng bước: [02-execution-flow.md](02-execution-flow.md).

## 6. Ranh giới hệ thống

| Trong phạm vi | Ngoài phạm vi (hiện tại) |
|---|---|
| Thu thập, chuẩn hoá, lưu, thông báo file | Bot Telegram/Discord, web UI |
| Sentiment tiếng Việt rule-based | Sentiment LLM, tiếng Anh có nghĩa |
| SQLite 1 file | Postgres/ClickHouse, sharding |
| Sync tuần tự | Async/Scrapy, phân tán |

Các quyết định nền: [../decisions.md](../decisions.md) (TDR-001…006).
