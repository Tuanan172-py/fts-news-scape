---
type: Reference
title: Cấu trúc Mã nguồn (Codebase Guide)
description: Bản đồ 74 module Python trong project/src — 12 package, vai trò từng file và điểm vào.
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
sources_last_checked: 2026-09-07
---

`project/src/` gồm **12 package, 74 file `.py`** (kể cả `__init__.py` và 2 module gốc `orchestrator.py`, `morninger.py`). Nguyên tắc: thêm domain mới không cần sửa
core; thêm tầng mới không cần sửa scraper.

# Điểm vào

| Lệnh | Module | Việc |
|---|---|---|
| `python -m src.morninger` | `morninger.py` | **PROD** — 3 job: capture 15′, re-derive 30′, drift sáng |
| `python -m src.orchestrator` | `orchestrator.py` | chỉ Vòng 1 (standalone/fallback) |
| `python -m src.monitor.health` | `monitor/health.py` | health check |

# `src/core/` — nền tảng (10 file)

| File | Vai trò |
|---|---|
| `base_scraper.py` | `BaseScraper` template method: `fetch_list` → `parse_item` → dedup → `enrich` |
| `config.py` | loader `settings.yaml`, `domains/*.yaml`, `watchlist.yaml`, `secrets.yaml` |
| `models.py` | `Article`, `ScrapeResult`, `sha256_hash()`, `now_vn_iso()`, `VN_TZ` |
| `logging.py` | Loguru — 1 sink file xoay vòng + stderr |
| `retry.py` | `run_with_retry` / `run_with_fallback` (primary fail → fallback) |
| `staging.py` | Safe I/O — chống Windows file lock, `safe_atomic_write`, `safe_json_dump` |
| `proclock.py` | advisory lock scheduler (`host:pid`, stale 2400s) |
| `stdio.py` | ép stdout/stderr UTF-8 trên Windows |
| `tickers.py` | gắn mã CK 3 ký tự in hoa theo watchlist |

# `src/crawler/` — tầng HTTP & Bronze (4 file)

`http_client.py` (session dùng chung, rate limit per-domain, UA rotation, truststore) ·
`raw_store.py` (**Bronze WORM**, atomic tmp→replace, meta 14 khoá) · `robots.py` (RobotsGate
trước khi fetch chi tiết) · `backoff.py` (`SourceBackoff` cool-down cấp source).

# `src/scrapers/` — 11 file (9 scraper + mixin + registry)

| File | Domain | Phương thức |
|---|---|---|
| `rss_capture.py` | generic | RSS list + Bronze capture ⇒ **cách thêm nguồn 0 dòng code** |
| `rss_generic.py` | generic | RSS thuần, **không** Bronze ⇒ các domain dùng nó đang tắt |
| `capture_mixin.py` | — | logic capture dùng chung (DRY) |
| `cafef.py` | cafef.vn | JSON API nội bộ theo watchlist |
| `tnck.py` | tinnhanhchungkhoan.vn | zone JSON API, 9 zone |
| `baodautu.py` | baodautu.vn | HTML listing (RSS hỏng vĩnh viễn) |
| `vietstock.py`, `vneconomy.py` | tương ứng | RSS + capture |
| `fireant.py`, `vndirect.py` | tương ứng | REST API (đang tắt) |

Đăng ký bằng decorator `@register("<name>")` vào `REGISTRY`; import ở cuối
`scrapers/__init__.py` để trigger.[^registry]

# `src/db/` — lưu trữ (4 file)

`store.py` (`ArticleStore`: DDL 10 bảng, pragmas WAL, state + advisory lock) ·
`writer.py` (`DBWriter` single-writer) · `dedup.py` (`DedupCache` 2 lớp) ·
`snapshot.py` (bản chụp point-in-time không chặn ghi).

# `src/pipeline/` — Vòng 2 (9 file)

`silver_builder.py` · `change_detect.py` · `run.py` (`process_meta` — 1 artifact qua cả chuỗi) ·
`derive.py` (tăng dần theo watermark) · `drift.py` · `refresh.py` (re-fetch kích hoạt
change-detect) · `user_workflow.py` (orchestrator lớp người dùng) ·
`periodic_reports.py` (**ngoài** vòng 2 — driver báo cáo định kỳ NSO, xem
[pipeline](../pipelines/periodic_reports.md)).

`silver_builder.py` có nhánh JSON generic: Content-Type là JSON ⇒ `_html_from_json()` rút HTML
từ các trường `content` / `originalContent` / `body_html`… nên Bronze JSON (fireant) ra Silver được.

# API nền tảng thêm 2026-09-07

| Hàm | File | Vì sao tồn tại |
|---|---|---|
| `resolve_source_domain(name)` | `src/core/config.py` | Nguồn sự thật cho host của domain: dotted → `domains/<name>/schema.yaml` khoá `domain:` → netloc `base_url` → legacy `<name>.vn`. Sửa bẫy cũ `tnck` → `tnck.vn` (không khớp gì trong DB ⇒ báo cáo 0 bài) |
| `RawStore.save_binary(...)` | `src/crawler/raw_store.py` | Lưu file nhị phân (`.xlsx`/`.docx`/`.pdf`) WORM; meta ghi `.binmeta.json` để `derive` không quét trúng |
| `scripts/maintenance/backfill_deferred.py` | scripts | Thay `enrich_deferred.py` (đã xoá — nó fetch lại từ mạng, **mù Bronze**). Đọc Bronze đã có, kể cả Bronze JSON; `--dates-only` vá `published_at` thiếu |

# `src/handoff/` — ranh giới producer↔agent (4 file)

`work_package.py` (`WorkPackageBuilder` + `write_package`) · `contract_validator.py` (validate
instance vs JSON Schema) · `catalog.py` (`Catalog` — enqueue/claim/mark, exactly-once).

# `src/agent/` — Vòng 3, **không LLM** (12 file)

| File | Vai trò |
|---|---|
| `runner.py` | `AgentRunner` — export task Lớp 2, ingest + DoD |
| `l1_runner.py` | `L1Runner` — mirror cho Lớp 1 |
| `l1_router.py` | quy trình 2 tầng code-first → handoff, `check_l1_dod` |
| `l1_classifier.py` | bước code-first deterministic (khớp mã + alias trong tiêu đề) |
| `packet.py` | dựng task packet self-describing (input + output_contract + constraints) |
| `pruner.py` | lọc đoạn văn sạch — giảm ~96% payload, giữ nguyên văn cho citation |
| `batch_handoff.py` | gom 5–10 bài vào `batch_XX.task.json` |
| `manifest.py` | manifest lô + hiển thị tiến độ trên terminal |
| `archive.py` | dọn/lưu trữ packet sau khi ingest thành công |
| `dod.py` | `verify_preconditions` + `check_dod` (4 predicate) |
| `entities.py` | `EntityRegistry` — detect / subscribers_for / resolve_subscription |

# `src/export/` (5 file) · `src/users/` (2 file)

`csv_export.py` (utf-8-sig) · `silver_manifest.py` · `user_output.py` (`UserOutputWriter` — gate,
route, noise filter, ghi CSV) · `checkpoint.py` (resume theo `article_id`) ·
`users/compile.py` (input người dùng → yaml + manifest).

# `src/monitor/` (6 file) · `src/notifier/` (2) · `src/processor/` (4)

`daily_reporter.py` (analytics toàn hệ) · `domain_reporter.py` (báo cáo Markdown theo domain) ·
`domain_validator.py` (validate field theo schema domain) · `health.py` · `heartbeat.py` ·
`file_notify.py` · `extractor.py` (trafilatura) · `classifier.py` (**đang chạy**) ·
`sentiment.py`, `segment.py` (⚠️ **LEGACY / cold backup**, đã gỡ khỏi workflow).

# Dependency injection

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

⚠️ `SentimentEngine` **không còn** được inject vào orchestrator.

# Liên quan

- [Kiến trúc Hệ thống](architecture.md) · [Agent Contracts](agent_contracts.md)
- [Domain Sources](../configurations/domain_sources.md)

[^codebase-guide]: [Codebase Guide](project/docs/dev/01-codebase-guide.md)
[^orchestrator]: [Orchestrator](project/src/orchestrator.py)
[^morninger]: [Morninger](project/src/morninger.py)
[^registry]: [Scraper registry](project/src/scrapers/__init__.py)
