# Scout — Codebase Map (raw→agent standardization)

Nguồn: đọc trực tiếp code trong phiên vừa triển khai tầng raw-capture. Không suy đoán.

## Đã có (producer side, vừa build — xem docs/dev/06-raw-html-capture-guide.md)
- **RawStore** `src/crawler/raw_store.py` — ghi `data/raw_html/<domain>/<yyyymmdd>/<url_title_hash>.html`
  (byte-exact) + `.meta.json` sidecar. Meta 14 keys: source_url, url_title_hash, fetch_ts,
  render_method, html_path, http_status, content_sha256, content_length_bytes, encoding,
  response_headers(subset), images[], capture_status(ok|partial|failed|skipped_robots), missing[], error.
  → Đây LÀ tầng "bronze/raw" content-addressed sẵn có. Thiếu: layer bạc/vàng, catalog index, change-log.
- **CaptureMixin** `src/scrapers/capture_mixin.py` — `_capture_and_extract` (robots→backoff→fetch→
  RawStore-first→content_html→looks_complete), `_looks_complete` (D1), `_density_extract` (D5).
- **Article model** `src/core/models.py` — dataclass; `content_html`, `content_text`, `metadata` (dict
  JSON), `url_title_hash`=SHA-256(url+title), `to_row()/from_row()`. `metadata["capture"]`=con trỏ artifact.
- **DB** `src/db/store.py` — SQLite `articles` (cột content_html/content_text/metadata_json,
  sentiment/sentiment_score đã có slot), `seen_articles`, `scraper_heartbeat`, `scraper_metrics`.
  INSERT OR IGNORE theo url/hash. Single-writer (`db/writer.py`), dedup (`db/dedup.py` SHA-256 + fuzzy).
- **Pipeline** `BaseScraper.run()` template-method; `orchestrator.py` (APScheduler, `--once`,
  `build_scraper` qua REGISTRY). `processor/` đã có extractor(trafilatura), classifier, sentiment, segment
  — nhưng chạy INLINE trong scraper (chưa tách thành tầng consumer độc lập).
- Scrapers dùng capture: `cafef.py`, `vietstock.py`. Compliance: `robots.py`, `backoff.py`.
- Export: `export/csv_export.py`. Scripts: `run_once.py`, `enrich_deferred.py`, `validate_capture.py`.

## Gap vs nhiệm vụ mới
1. **Chưa có tầng "clean base"/work-package chuẩn hoá cho agent.** content_html/content_text nằm trong
   DB + raw trên đĩa, nhưng KHÔNG có 1 gói/hợp đồng (JSON schema versioned) mà agent bất kỳ provider đọc được.
2. **Chưa có catalog/index** (manifest-of-manifests) để consumer liệt kê việc + watermark "đã xử lý".
3. **Chưa có change-detection/log** khi HTML/template đổi (chỉ có content_sha256 per-capture, chưa so sánh
   liên phiên; chưa structural fingerprint; chưa reconcile changed/unchanged/broken).
4. **Chưa tách producer↔consumer**: sentiment/classifier chạy inline; task muốn agent (ngoài phiên) nhận
   raw đã đóng gói. Cần ranh giới hợp đồng rõ (handoff contract).
5. **Chưa có spec agent framework**: I/O schema provider-agnostic, output taxonomy (tóm tắt→hàm ý→mức độ
   quan trọng…), orchestration main/sub, điều kiện loop/done, guardrails. (Task nói "lớp agent để sau" →
   phase design-only cho phần này.)

## Điểm tái dùng cho plan
- `content_sha256` + `url_title_hash` sẵn có → nền cho change-detection + idempotency key.
- `metadata_json` + `Article.metadata["capture"]` → nơi gắn con trỏ layer bạc/work-package.
- `scraper_metrics`/`heartbeat` → mẫu cho bảng change-log/processing-status.
- DB SQLite là store trung tâm → thêm bảng `article_versions`/`work_items`/`processing_status` ít xáo trộn.
- `docs/dev/03-adding-a-source.md`, `docs/design/06-raw-html-capture.md` = nguồn convention.

## Unresolved (cho planner)
- Store cho layer bạc/work-package: file JSONL trên đĩa (bên cạnh raw) vs bảng DB mới vs cả hai?
- Catalog: file index (JSONL/Parquet) vs view SQL?
- Agent runtime: chỉ ĐẶC TẢ hợp đồng (schema + docs) hay kèm reference harness Python?
