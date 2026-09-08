# OKF Changelog

## 2026-09-08 (Mo rong nguon tin + bao cao dinh ky NSO)

Dong bo OKF voi dot mo rong nguon (`7bb46ba`, `75b8b6c`) va hop nhat 2 may (`e4d281a`).

- **New**: `tables/periodic_reports.md` — bang thu 11, dedup theo `(report_type, period)` chu KHONG theo URL
- **New**: `datasets/bronze_periodic_reports.md` — kho WORM thu hai `data/raw_reports/**` (HTML + `.xlsx`), va **vi sao** phai tach root khoi `data/raw_html/`
- **New**: `pipelines/periodic_reports.md` — nhanh xu ly thu tu, NGOAI cycle 15'; NSO khong phai domain thu 25
- **Update**: `index.md` — 7/24 → **8/24 domain enabled** (them fireant); them bao cao dinh ky vao ban do thu muc
- **Update**: `tables/index.md`, `datasets/index.md` — 10 → **11 bang**
- **Update**: `pipelines/index.md` — them muc "Ngoai chu ky"
- **Update**: `configurations/domain_sources.md` — 7 → **8 enabled**, 17 → 16 tat
- **Update**: `references/codebase.md` — `src/pipeline/` 8 → 9 file; them bang 3 API nen tang moi: `resolve_source_domain()`, `RawStore.save_binary()`, `backfill_deferred.py` (thay `enrich_deferred.py` da xoa vi mu Bronze)
- **Update**: `MAPPING.md` — anh xa driver NSO va `resolve_source_domain`
- **Total**: 28 → 31 concepts

## 2026-09-07 (Full refresh — đồng bộ với kiến trúc 3 vòng)

Toàn bộ KB được rà lại theo code hiện hành (13 file `stale`, 3 `no-source`). **22 → 41 concept.**

**Mới (19):**
- `datasets/bronze_raw_html.md` — Bronze WORM, meta 14 khoá
- `datasets/silver_work_packages.md` — silver-v1, work-package-v1, task packet, pruner/batch
- `datasets/user_deliverables.md` — CSV per-user + `_master`
- `tables/article_versions.md`, `work_items.md`, `agent_outputs.md`, `l1_tasks.md`,
  `l1_outputs.md`, `pipeline_state.md` — 6 bảng chưa từng có trong KB
- `pipelines/morninger.md`, `silver_derive.md`, `agent_handoff.md`, `user_output.md`
- `configurations/entity_registry.md`, `user_subscriptions.md`
- `references/agent_contracts.md`
- `playbooks/daily_agent_run.md`
- `metrics/dod_pass_rate.md`, `silver_backlog.md`

**Sửa sai so với code (quan trọng):**
- `articles`: cột là `metadata_json` (không phải `metadata`); index thật là
  `idx_articles_published` / `idx_articles_source`
- `seen_articles`: PK là `hash` (không phải `hash_id`), `seen_at` là REAL epoch
- `scraper_metrics`: **không có** cột `id`
- `scraper_heartbeat`: `status ∈ {running, ok, failed}` — không có `error`
- `web_monocle_db`: 5 → **10 bảng**; **không tồn tại** bảng `schema_version`
- `settings.md`: viết lại theo YAML thật (khối `morninger`; bỏ các khoá không tồn tại)
- `notifications.md`: cấu trúc thật là danh sách `rules` (4 rule, khớp-đầu-tiên-thắng), output là
  `data/notifications/YYYY-MM-DD.log` — không có `tiers`/`prefix`/file `.txt`
- `secrets.md`: khoá là `fireant_token` cấp gốc
- `domain_sources` / `source_strategy`: 23 → **24 config, 7 enabled**; giải thích quy tắc
  Bronze-first
- `scraper_health`: bỏ truy vấn uptime sai (heartbeat chỉ 1 hàng/scraper), thay bằng
  `scraper_metrics`
- `sentiment_distribution`: nguồn tính chuyển sang `agent_outputs`

**Đánh dấu deprecated:** `pipelines/sentiment_pipeline.md` — engine rule-based đã gỡ khỏi
workflow (chỉ `classify_rule_based` còn chạy).

**Cấu trúc:** `configurations/monocle_config.md` → `secrets.md` (khớp link ở index, sửa link
gãy). Mọi `index.md` viết lại. `MAPPING.md` mở rộng cho Vòng 2/3 và lớp người dùng.

**Provenance:** `sources[]` của metrics trỏ về **file code có thật** thay vì file `.md` khác →
`okf_check` hết cảnh báo `no-source`.

## 2026-08-04 (Fix Session)
- **Fix**: Sửa toàn bộ frontmatter — `generated` từ string → object `{ by, at }`, `status: active` → `status: stable`, `sources[].url` → `sources[].resource`
- **Fix**: Thêm footnote definitions cho tất cả concept, sửa footnote label khớp với `sources[].id`
- **Update**: Cập nhật `articles.md` — thêm 3 columns còn thiếu (id, url_title_hash), indexes, 2 query patterns mới
- **Update**: Cập nhật `seen_articles.md` — thêm 2 columns (title_norm, source_domain), mô tả 2-layer dedup
- **Update**: Cập nhật `web_monocle_db.md` — thêm 3 bảng mới (scraper_heartbeat, scraper_metrics, schema_version)
- **Update**: Viết lại `ingestion_scheduler.md` — đổi tên thành orchestrator, thêm execution flow, CLI usage, graceful shutdown
- **Update**: Viết lại `runbook.md` — thêm health check queries, troubleshooting table
- **Update**: Viết lại `deployment.md` — thêm system requirements, monitoring commands
- **Update**: Viết lại `codebase.md` — đầy đủ 9 subpackages, 28 files, dependency injection diagram
- **Update**: Viết lại `source_strategy.md` — bảng đầy đủ 23 domain với trạng thái active/disabled
- **Update**: Viết lại `monocle_config.md` → `secrets.md` — thêm cấu trúc YAML, setup steps
- **New**: `tables/scraper_heartbeat.md` — Bảng theo dõi trạng thái scraper
- **New**: `tables/scraper_metrics.md` — Bảng metrics mỗi chu kỳ
- **New**: `pipelines/db_writer.md` — Single-writer thread pattern
- **New**: `pipelines/sentiment_pipeline.md` — Pipeline phân tích cảm xúc tiếng Việt
- **New**: `metrics/articles_per_day.md` — Metric số lượng bài báo/ngày
- **New**: `metrics/dedup_rate.md` — Metric tỷ lệ khử trùng lặp
- **New**: `metrics/sentiment_distribution.md` — Metric phân phối cảm xúc
- **New**: `metrics/scraper_health.md` — Metric sức khỏe scraper
- **New**: `configurations/settings.md` — Cấu hình toàn cục settings.yaml
- **New**: `configurations/watchlist.md` — Danh sách 30 mã blue-chip
- **New**: `configurations/domain_sources.md` — Danh sách đầy đủ 23 domain config
- **New**: `configurations/notifications.md` — Cấu hình thông báo
- **New**: `references/architecture.md` — Kiến trúc tổng thể hệ thống
- **Update**: Tất cả index.md — làm mới để phản ánh đầy đủ concepts
- **Total**: 9→28 concepts, 8→8 index files

## 2026-08-03 (Pha 1 — Discovery)
- Khởi tạo cấu trúc OKF v0.2 ban đầu qua pha Discovery, Generation, và Enrichment dựa trên codebase của dự án Web Monocle (news-scape). Khai phá các thực thể dữ liệu chính: bảng `articles`, bảng `seen_articles` và pipeline Ingestion Scheduler.

## 2026-08-03 (Pha 2 — Enrichment Tự động)
- Bổ sung các Playbook Triển khai (`deployment`), tham chiếu Cấu trúc mã nguồn (`codebase`) và Chiến lược tiếp cận nguồn (`source_strategy`). Bổ sung thông tin chi tiết về các nguồn API Môi giới (FireAnt, CafeF, TNCK).
