# Dev — Data model & tầng SQLite

Cập nhật: 2026-07-26 · Nguồn: `src/db/store.py`, `writer.py`, `dedup.py`, `core/models.py`.

## 1. `Article` (dataclass, `models.py:28-96`)

| Field | Kiểu | Ghi chú |
|---|---|---|
| url | str | bắt buộc, UNIQUE ở DB |
| title | str | bắt buộc |
| source_domain | str | bắt buộc |
| summary | str | tóm tắt (fallback content khi enrich lỗi) |
| content_html | str | **HTML gốc** — không vứt |
| content_text | str | text sạch (trafilatura) |
| published_at | str | ISO 8601 giờ VN |
| author | str | |
| symbols | list[str] | mã CK (join `,` khi lưu) |
| categories | list[str] | nhãn + tên feed |
| sentiment | str | positive/negative/neutral |
| sentiment_score | float\|None | |
| fetched_at | str | mặc định `now_vn_iso()` lúc tạo |
| processed_at | str | đặt sau enrich (`base_scraper.py:76`) |
| metadata | dict | có `language` (gate sentiment), `feed_name`, `detail_deferred`… → `metadata_json` |

- `url_title_hash` (property) = `sha256_hash(url, title)` = `sha256(f"{url}{title}")` hex (`models.py:18-20,52-54`).
- `to_row()`/`from_row()` map ↔ cột SQLite; metadata `json.dumps(ensure_ascii=False)`.
- `ScrapeResult(scraper, fetched, new, errors, duration_s)`; `.ok = not errors`.

## 2. Schema SQLite (`store.py:28-74`)

Không có bảng version; "v2" chỉ là chú thích. Dùng `CREATE TABLE IF NOT EXISTS` idempotent
(`init_schema()` → `executescript`). Migration thật duy nhất = dedup JSON→SQLite (mục 5).

### `articles`
Cột (theo `_COLUMNS`, `store.py:17-21`): url, url_title_hash, title, summary, content_html,
content_text, published_at, author, source_domain, symbols, categories, sentiment,
sentiment_score, fetched_at, processed_at, metadata_json. Cộng `id INTEGER PK AUTOINCREMENT`.
- **UNIQUE**: `url`, `url_title_hash`.
- Index: `idx_articles_published(published_at)`, `idx_articles_source(source_domain, fetched_at)`.
- Ghi bằng `INSERT OR IGNORE` → trùng url/hash bị bỏ im lặng.

### `seen_articles` (dedup)
`hash TEXT PRIMARY KEY, title_norm TEXT, source_domain TEXT, seen_at REAL(epoch)`.
Index `idx_seen_source(source_domain, seen_at)`.

### `scraper_heartbeat`
`scraper_name TEXT PK, last_run_ts TEXT, status TEXT(running|ok|failed), error_msg TEXT,
consecutive_failures INT, cycle_count INT`.

### `scraper_metrics` (append-only, không PK)
`ts, scraper_name, articles_fetched, articles_new, errors, duration_ms`. Index
`idx_metrics_scraper(scraper_name, ts)`.

### PRAGMA (mọi connection, `store.py:91-95`)
`journal_mode=WAL`, `busy_timeout=5000`, `synchronous=NORMAL`, `row_factory=Row`,
`connect(timeout=5.0, check_same_thread=False)`.

## 3. DBWriter — single-writer (`writer.py`)

- 1 thread daemon `db-writer`, connection **riêng của thread**.
- Scraper/orchestrator chỉ `enqueue()`; không ai khác ghi bảng `articles`.
- Batch: gom tối đa `batch_size=50`, chờ item đầu blocking `flush_interval=2.0s`.
- `insert_batch` (`store.py:123-148`): `BEGIN IMMEDIATE` → `executemany(INSERT OR IGNORE)` →
  commit; trả delta `total_changes` (số row thật mới). `sqlite3.Error` → rollback trả 0;
  `BaseException` → rollback rồi re-raise (không treo transaction).
- Shutdown `stop(timeout=30)`: set `_stop`, tự xả hết queue rồi join → **flush graceful**, idempotent.

**Vì sao single-writer:** SQLite chỉ cho 1 writer tại một thời điểm; gom mọi ghi vào 1 thread
tránh `SQLITE_BUSY` và đơn giản hơn multi-writer coordination (TDR-004). WAL cho phép reader
(health CLI, DB Browser) đọc song song.

## 4. Dedup (`dedup.py`)

- **Lớp 1 (đang chạy):** `is_duplicate(url,title)` tra hash trong `seen_articles`. `mark_seen`
  ghi `INSERT OR IGNORE` (hash, `normalize_title`, source, `time.time()`). `normalize_title`
  = lowercase + gộp whitespace, **giữ dấu tiếng Việt**.
- **Lớp 2 (fuzzy):** `is_similar_title(title, source, hours=48, threshold=90)` dùng
  `rapidfuzz.token_set_ratio` so với tiêu đề **domain khác** trong 48h. Gọi trong
  `BaseScraper.run()` khi `cfg.fuzzy_dedup` (mặc định True).
- `cleanup(max_age_days=30)` xoá seen cũ (gọi lúc khởi tạo orchestrator).

## 5. Migration JSON→SQLite (`dedup.py:37-53`)

Nếu còn `data/dedup_cache.json` (schema cũ): đọc `{hash: ts}` → `INSERT OR IGNORE` với
`title_norm=''`, `source='legacy'`, rồi **xoá file**. Lỗi → warn, bỏ qua. Chạy 1 lần, idempotent.

## 6. Truy vấn nhanh (SQLite CLI / DB Browser)

```sql
-- 20 bài mới nhất
SELECT fetched_at, sentiment, source_domain, title FROM articles
ORDER BY id DESC LIMIT 20;

-- Đếm theo nguồn + sentiment
SELECT source_domain, sentiment, COUNT(*) FROM articles
GROUP BY source_domain, sentiment ORDER BY source_domain;

-- Tin về 1 mã
SELECT published_at, title FROM articles WHERE symbols LIKE '%HPG%'
ORDER BY published_at DESC;

-- Sức khoẻ scraper
SELECT scraper_name, status, last_run_ts, consecutive_failures FROM scraper_heartbeat;
```
⚠️ Mở DB Browser ở chế độ read-only hoặc đóng orchestrator trước khi ghi, tránh tranh WAL.

## 7. Câu hỏi mở

- Chưa có retention/rotation cho bảng `articles` và `scraper_metrics` (append-only) → DB phình
  theo thời gian (hiện `monocle.db` ~550MB). Xem [05-known-issues.md](05-known-issues.md).
