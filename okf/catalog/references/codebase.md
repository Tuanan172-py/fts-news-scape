---
type: Reference
title: Cấu trúc Mã nguồn (Codebase Guide)
description: Bản đồ 143 file Python trong project/src sau ADR-0027 — 17 package, CLI mỏng, vai trò từng gói và điểm vào.
resource: project/src/
tags: [codebase, reference, development, architecture]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: codebase-guide
    resource: project/docs/dev/01-codebase-guide.md
    title: Codebase Guide
  - id: orchestrator
    resource: project/src/orchestrator.py
    title: Orchestrator (Vòng 1)
  - id: morninger
    resource: project/src/morninger.py
    title: Morninger (entrypoint prod)
  - id: registry
    resource: project/src/scrapers/__init__.py
    title: Scraper REGISTRY
  - id: adr-0027
    resource: docs/decisions/0027-module-boundaries-thin-clis.md
    title: Ranh giới module, CLI mỏng
sources_last_checked: 2026-10-22
---

`project/src/` gồm **17 package + 2 module gốc (`orchestrator.py`, `morninger.py`), 143 file
`.py`** (kể cả `__init__.py`). Ranh giới module theo ADR-0027: logic nằm trong `src/`,
`project/scripts/*.py` chỉ là **CLI mỏng** giữ nguyên đường dẫn (lệnh `python scripts/<tên>.py`
không đổi); mọi kết nối SQLite ngoài nội bộ `src/db` đi qua `src/db/connect.py`.[^adr-0027]

Nguyên tắc: thêm domain mới không cần sửa core; thêm tầng mới không cần sửa scraper.

# Điểm vào

| Lệnh | Module | Việc |
|---|---|---|
| `python -m src.morninger` | `morninger.py` | capture + re-derive + drift + reclaim |
| `python -m src.orchestrator` | `orchestrator.py` | chỉ Vòng 1 (standalone) |
| `python -m src.monitor.health` | `monitor/health.py` | health check |
| `scripts/ops_daemon.py run` | `ops/runtime/daemon.py` | control plane không người trực (ADR-0012) |
| `scripts/article_run.py` | `ops/wave/article_run.py` | một đợt Article Lane |
| `scripts/pipeline_radar.py` | `ops/console/radar.py` | radar chỉ đọc |
| `scripts/publish.py` | `export/publisher.py` (`publish_day`) | publish lên SharePoint sandbox (ADR-0026.D1) |

# CLI mỏng → module

| Script | Module |
|---|---|
| `article_pack.py` · `article_expand.py` · `token_ledger.py` · `article_tick.py` · `handoff.py` | `src/article_lane/{pack,expand,ledger,tick,handoff}.py` |
| `article_run.py` | `src/ops/wave/article_run.py` |
| `pipeline_radar.py` | `src/ops/console/radar.py` |
| `build_entities.py` | `src/agent/catalog/catalog_build.py` |

# `src/core/` — nền tảng (18 file)

| File | Vai trò |
|---|---|
| `paths.py` | **mọi** đường dẫn dữ liệu từ `data_root()` (`MONOCLE_DATA_DIR`, mặc định `C:\data\news-scape`); `PROJECT_ROOT`, `REPO_ROOT`, `harness_db_path()` |
| `config.py` | loader `settings.yaml`, `domains/*.yaml`, `watchlist.yaml`, `secrets.yaml`; `resolve_db_path`, `resolve_source_domain` |
| `ops_config.py` | cấu hình, đường dẫn, secrets của tầng vận hành |
| `pipeline_spec.py` | đọc khối `ops_spec` của `.agents/pipeline.yaml` |
| `redact.py` | che secrets trước khi ghi log/sự kiện/prompt |
| `base_scraper.py` | `BaseScraper` template method: `fetch_list` → `parse_item` → dedup → `enrich` |
| `models.py` | `Article`, `ScrapeResult`, `sha256_hash()`, `now_vn_iso()`, `VN_TZ` |
| `proclock.py` | `capture.lock` (file lock một tiến trình) + advisory lock scheduler (stale 2400s) |
| `user_manifest.py` | công tắc bật/tắt người dùng từ `<DATA_ROOT>/subscriptions/manifest.yaml` |
| `logging.py` · `retry.py` · `staging.py` · `stdio.py` · `tickers.py` · `urlnorm.py` · `htmltitle.py` · `pagination.py` | log, retry/fallback, ghi nguyên tử, UTF-8 console, gắn mã CK, chuẩn hoá URL, tiêu đề, phân trang theo watermark |

# `src/crawler/` (4) · `src/scrapers/` (11) · `src/processor/` (2)

`http_client.py` (rate limit per-domain, UA rotation, truststore) · `raw_store.py` (**Bronze
WORM**, atomic tmp→replace) · `robots.py` · `backoff.py`.

Scraper: `rss_capture.py` (RSS + Bronze — cách thêm nguồn 0 dòng code), `rss_generic.py` (RSS
thuần, không Bronze), `capture_mixin.py`, `cafef.py`, `tnck.py`, `baodautu.py`, `vietstock.py`,
`vneconomy.py`, `fireant.py`, `vndirect.py`. Đăng ký bằng `@register("<name>")` vào
`REGISTRY`.[^registry]

`processor/`: `extractor.py` (trafilatura) · `classifier.py` (`classify_rule_based`). Engine
sentiment rule-based đã xoá.

# `src/db/` — lưu trữ (7 file)

`store.py` (`ArticleStore`: DDL `_SCHEMA`, pragmas WAL, state + advisory lock) · `connect.py`
(`open_ro`, `open_rw`) · `writer.py` (`DBWriter` single-writer) · `dedup.py` · `registry.py` (sổ
phát hiện URL, ADR 0013) · `snapshot.py` (bản chụp không chặn ghi) · `preflight.py` (đường dẫn
DB + thử ghi trước khi tiêu token).

# `src/pipeline/` — Vòng 2 (12 file)

`silver_builder.py` · `change_detect.py` · `run.py` · `derive.py` (tăng dần theo watermark) ·
`drift.py` · `refresh.py` · `backfill.py` · `reconcile.py` (đối chiếu sitemap, độ phủ) ·
`story_cluster.py` · `cluster_job.py` · `inherit.py` (cụm câu chuyện, ADR 0016).

# `src/handoff/` (4) — work-package + hàng đợi

`work_package.py` · `contract_validator.py` (JSON Schema) · `catalog.py` (`Catalog` —
enqueue/claim/mark, exactly-once).

# `src/agent/` — hợp đồng, catalog thực thể, runner (24 file)

| Gói | File | Vai trò |
|---|---|---|
| `runners/` | `agy_runner`, `opencode_runner`, `openrouter_runner` | gọi runtime LLM cho từng lô (ADR-0026.D3) |
| `contract/` | `article_contract`, `dod`, `l1_router`, `conformance` | hợp đồng đầu ra, cổng DoD, chấm provider (ADR 0017) |
| `ingest/` | `runner`, `l1_runner`, `batch_handoff` | nạp bản ghi qua cổng DoD |
| `catalog/` | `entities`, `intent_resolve`, `l1_classifier`, `catalog_build` | `EntityRegistry`, ánh xạ tên → `entity_id`, khớp tất định, dựng catalog |
| `packet/` | `distill`, `pruner`, `prefix`, `silver_source` | chắt lọc đoạn, tiền tố tĩnh, đọc Silver |

# `src/article_lane/` (6) · `src/telemetry/` (3)

`pack.py` · `expand.py` · `ledger.py` (`token_ledger` ở `harness.db`) · `tick.py` · `handoff.py`.
`telemetry/`: `dsh_usage.py` (số đo token thật của DSH) · `trace.py` (span của đợt vào `ops_spans`).

# `src/ops/` — vận hành tự chủ (28 file)

| Gói | Nội dung |
|---|---|
| `wave/` | `wave_flow`, `dbos_flow`, `article_run`, `manual`, `lanes`, `procrun`, `metrics` |
| `runtime/` | `daemon`, `sensor`, `probes`, `breakers`, `mandate`, `order`, `supervisor`, `sentinel`, `notify` |
| `console/` | `control_room` (+ `web/control_room.html`), `commands`, `present`, `reports`, `supervision`, `radar`, `improve` |
| `store.py` | sự kiện, cảnh báo, breaker, đợt, lệnh trong `ops.db` |

# `src/export/` (8) · `src/lakehouse/` (5) · `src/analytics/` (2) · `src/users/` (2)

`user_output.py` (gate, route, noise filter) · `xlsx_delivery.py` (file giao `.xlsx`) ·
`radar_sheet.py` · `checkpoint.py` · `csv_export.py` · `silver_manifest.py` · `publisher.py`
(`publish_day`, ADR 0023/0026). `lakehouse/`: thư viện dropzone + consolidator DuckDB
(`lakehouse_cli.py` chỉ verify + dropzone). `analytics/signals.py` dựng `signal_daily`,
`entity_links`, `source_profile`. `users/compile.py` biên dịch danh mục người dùng.

# `src/monitor/` (3) · `src/notifier/` (2)

`health.py` · `heartbeat.py` · `notifier/file_notify.py`.

# Dependency injection (orchestrator)

```
Orchestrator.__init__():
  store     = ArticleStore(settings.database.path)
  writer    = DBWriter(store)
  http      = HTTPClient(settings.http)
  dedup     = DedupCache(store)
  heartbeat = Heartbeat(store)
  notifier  = FileNotifier(out_dir=...)

build_scraper(cfg, http, dedup)   # scraper dùng chung HTTPClient + DedupCache
```

# Liên quan

- [Kiến trúc Hệ thống](architecture.md) · [Agent Contracts](agent_contracts.md)
- [Domain Sources](../configurations/domain_sources.md)

[^codebase-guide]: [Codebase Guide](project/docs/dev/01-codebase-guide.md)
[^orchestrator]: [Orchestrator](project/src/orchestrator.py)
[^morninger]: [Morninger](project/src/morninger.py)
[^registry]: [Scraper registry](project/src/scrapers/__init__.py)
[^adr-0027]: [ADR-0027](docs/decisions/0027-module-boundaries-thin-clis.md)
