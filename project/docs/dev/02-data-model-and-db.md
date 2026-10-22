# Dev — Data model & tầng SQLite

Cập nhật: 2026-10-22 · Nguồn: `src/db/store.py`, `src/db/writer.py`, `src/db/dedup.py`, `src/core/models.py`.
DB vận hành: `<DATA_ROOT>/monocle.db` (mặc định `C:\data\news-scape\monocle.db`, `paths.db_path()`; `MONOCLE_DB_PATH` ghi đè).
Tham chiếu theo tên hàm, không theo số dòng.

## 1. `Article` (dataclass, `src/core/models.py`)

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
| sentiment | str | positive/negative/neutral; capture không điền (sentiment phân tích nằm ở `agent_outputs`) |
| sentiment_score | float\|None | |
| fetched_at | str | mặc định `now_vn_iso()` lúc tạo |
| processed_at | str | đặt sau enrich (`BaseScraper.run`) |
| metadata | dict | có `language`, `feed_name`, `detail_deferred`… → `metadata_json` |

- `url_title_hash` (property) = `sha256_hash(url, title)` = `sha256(f"{url}{title}")` hex.
- `to_row()`/`from_row()` map ↔ cột SQLite; metadata `json.dumps(ensure_ascii=False)`.
- `ScrapeResult(scraper, fetched, new, errors, duration_s)`; `.ok = not errors`.

## 2. Schema SQLite (`src/db/store.py`)

Không có bảng version; "v2" chỉ là chú thích. Dùng `CREATE TABLE IF NOT EXISTS` idempotent
(`init_schema()` → `executescript`). Migration thật duy nhất = dedup JSON→SQLite (mục 5).

### `articles`
Cột (theo `_COLUMNS`): url, url_title_hash, title, summary, content_html,
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

### Bảng khác trong `monocle.db`
- Silver/handoff: `article_versions`, `work_items`, `silver_failures`, `pipeline_state` (watermark, khoá scheduler).
- Kết quả Article Lane: `l1_outputs`, `agent_outputs` (qua DoD); `l1_tasks` là bảng của lane L1 cũ, còn trong DDL.
- Sổ khám phá: `discovered_urls`, `url_aliases`, `capture_coverage`.
- Cụm tin và tín hiệu: `story_clusters`, `cluster_members`, `signal_daily`, `entity_links`, `source_profile`.
- `periodic_reports`: bảng còn trong DDL, driver đã gỡ.

Trạng thái vận hành nằm ở `ops.db` (`src/ops/store.py`: `ops_*`, `provider_breakers`), token ở `harness.db`
(`token_ledger`, `src/article_lane/ledger.py`).

### PRAGMA (mọi connection, `ArticleStore._connect`)
`journal_mode=WAL`, `busy_timeout=30000`, `synchronous=NORMAL`,
`connect(timeout=30.0, check_same_thread=False)`.

## 3. DBWriter — single-writer (`writer.py`)

- 1 thread daemon `db-writer`, connection **riêng của thread**.
- Scraper/orchestrator chỉ `enqueue()`; không ai khác ghi bảng `articles`.
- Batch: gom tối đa `batch_size=50`, chờ item đầu blocking `flush_interval=2.0s`.
- `insert_batch`: `BEGIN IMMEDIATE` → `executemany(INSERT OR IGNORE)` →
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
- **Không còn lớp lọc mờ ở tầng cào** (ADR 0013, rule 10). Lớp `is_similar_title` đã gỡ vì loại
  nhầm 202 trong 439 bài ở 3 ngày đầu tháng 10/2026. Trùng ngữ nghĩa xử lý sau Bronze bằng cụm hoá
  (`src/pipeline/story_cluster.py`, ADR 0016), không bao giờ xoá bài.
- **Sổ phát hiện:** `discovered_urls` ghi mọi URL thấy được trước mọi bước lọc. Khoá là mã bài của
  nguồn (`src/core/urlnorm.py: url_key`) nên cùng một bài đổi slug hay thêm `?utm_source` vẫn là một
  bài. Biến thể URL nằm ở `url_aliases`. `DedupCache.discover` và `store.insert_batch` cập nhật sổ.
- `cleanup(max_age_days=30)` xoá seen cũ (gọi lúc khởi tạo orchestrator).

## 5. Migration JSON→SQLite (`DedupCache._migrate_legacy_json`)

Nếu còn `<DATA_ROOT>/dedup_cache.json` (schema cũ): đọc `{hash: ts}` → `INSERT OR IGNORE` với
`title_norm=''`, `source='legacy'`, rồi **xoá file**. Lỗi → warn, bỏ qua. Chạy 1 lần, idempotent.

## 6. Truy vấn nhanh (SQLite CLI / DB Browser)

```sql
-- 20 bài mới nhất
SELECT fetched_at, source_domain, title FROM articles
ORDER BY id DESC LIMIT 20;

-- Đếm theo nguồn
SELECT source_domain, COUNT(*) FROM articles
GROUP BY source_domain ORDER BY source_domain;

-- Tin về 1 mã
SELECT published_at, title FROM articles WHERE symbols LIKE '%HPG%'
ORDER BY published_at DESC;

-- Sức khoẻ scraper
SELECT scraper_name, status, last_run_ts, consecutive_failures FROM scraper_heartbeat;
```
⚠️ Trạng thái vận hành đọc bằng `python scripts/pipeline_radar.py status` trước (AGENTS.md §9). Truy vấn tay chỉ
chạy read-only (`src.db.connect.open_ro`) hoặc trên bản snapshot (`src/db/snapshot.py`); không mở DB vận hành để ghi.

## 7. Câu hỏi mở

- Chưa có retention/rotation cho bảng `articles` và `scraper_metrics` (append-only) → DB phình
  theo thời gian (`monocle.db` ~550MB khi đo 2026-07-26). Xem [05-known-issues.md](05-known-issues.md).
