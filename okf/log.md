# OKF Changelog

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
