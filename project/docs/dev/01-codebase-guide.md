# Dev — Hướng dẫn codebase

Cập nhật: 2026-10-22 · Đối tượng: dev mới, cần nắm cây thư mục + cách code chạy để sửa/mở rộng.
Bức tranh toàn hệ: [../design/00-end-to-end-architecture.md](../design/00-end-to-end-architecture.md).
Ranh giới module: ADR-0027 ([`docs/decisions/0027-module-boundaries-thin-clis.md`](../../../docs/decisions/0027-module-boundaries-thin-clis.md))
và RULE-12 ([`.agents/rules/12-module-boundaries.md`](../../../.agents/rules/12-module-boundaries.md)).

## 1. Ba vùng của `project/`

| Vùng | Vai trò | Quy tắc |
|---|---|---|
| `src/<package>/` | Toàn bộ logic nghiệp vụ, chia theo tầng | `src/core` (L0) và `src/db` (L1) không import package nghiệp vụ; không vòng import giữa package (RULE-12.R1) |
| `scripts/*.py` | CLI mỏng: parse tham số rồi gọi một hàm trong `src` | Đường dẫn ổn định, không đổi tên (Task Scheduler, `.agents/pipeline.yaml`, conductor gọi tới); không `scripts → scripts`, không `src → scripts` (R2–R4); script mới phải khai trong `SCRIPT_INVENTORY` (`tests/repo/test_architecture.py`, R6) |
| `tests/<package>/` | Test soi gương `src`; kiểm tra toàn kho ở `tests/repo/` | R7 — xem [04-testing.md](04-testing.md) |

Đường gốc lấy từ `src.core.paths` (`PROJECT_ROOT`, `REPO_ROOT`, `harness_db_path()`, `data_root()` theo `MONOCLE_DATA_DIR`,
mặc định `C:\data\news-scape`). Kết nối SQLite ngoài nội bộ `src/db` đi qua `src.db.connect.open_ro` / `open_rw` (R5).

## 2. Cây `src/`

```
src/
├── orchestrator.py        # Orchestrator.run_cycle: chạy scraper các nguồn bật, gắn chuyên mục, enqueue, CSV, WAL checkpoint
├── morninger.py           # entry prod của capture: job capture 10', re-derive 30', drift 06:00, reclaim 30'
├── core/                  # L0: models, config (settings/domain/watchlist), paths, base_scraper, retry, logging,
│                          #     tickers, urlnorm, proclock, staging, stdio, user_manifest, htmltitle, pagination,
│                          #     pipeline_spec, redact, ops_config
├── db/                    # L1: store (ArticleStore), writer (DBWriter), dedup (DedupCache), registry (sổ khám phá URL),
│                          #     connect (open_ro/open_rw), preflight, snapshot
├── crawler/               # http_client, raw_store (Bronze WORM), robots, backoff
├── scrapers/              # REGISTRY + @register; rss_generic, rss_capture, capture_mixin, cafef, tnck, fireant,
│                          #     vietstock, vneconomy, baodautu, vndirect
├── processor/             # classifier (chuyên mục theo luật), extractor (trafilatura)
├── pipeline/              # Silver: silver_builder, derive, run, change_detect, drift, refresh, reconcile, backfill,
│                          #     story_cluster, cluster_job, inherit
├── handoff/               # work_package, catalog (work_items), contract_validator
├── article_lane/          # pack, expand, tick, ledger, handoff — logic của Article Lane
├── agent/
│   ├── runners/           # agy_runner, opencode_runner, openrouter_runner
│   ├── contract/          # article_contract, dod, l1_router, conformance
│   ├── ingest/            # runner (AgentRunner), l1_runner, batch_handoff — bước nạp qua DoD
│   ├── catalog/           # entities (matcher), intent_resolve, l1_classifier, catalog_build
│   └── packet/            # distill, pruner, prefix, silver_source
├── ops/
│   ├── store.py           # ops.db
│   ├── wave/              # wave_flow, dbos_flow, article_run, manual, lanes, procrun, metrics
│   ├── runtime/           # daemon, sensor, probes, breakers, mandate, order, supervisor, sentinel, notify
│   └── console/           # control_room (+ web/), commands, present, reports, supervision, radar, improve
├── export/                # user_output, xlsx_delivery, checkpoint, publisher, radar_sheet, silver_manifest, csv_export
├── lakehouse/             # storage, manifest, ingest, consolidator
├── analytics/             # signals (signal_daily, entity_links, source_profile)
├── monitor/               # heartbeat, health
├── notifier/              # file_notify
├── telemetry/             # trace, dsh_usage
└── users/                 # compile (subscription → config/entities/users/*.yaml)
```

## 3. CLI mỏng ở `scripts/` và module phía sau

| Script | Logic |
|---|---|
| `article_run.py` | `src/ops/wave/article_run.py` |
| `article_pack.py`, `article_expand.py`, `article_tick.py`, `token_ledger.py`, `handoff.py` | `src/article_lane/{pack,expand,tick,ledger,handoff}.py` |
| `l1_ingest.py`, `agent_ingest.py` | `src/agent/ingest/` (bước nạp của `article_run.py --finish`) |
| `pipeline_radar.py` | `src/ops/console/radar.py` |
| `build_entities.py` | `src/agent/catalog/catalog_build.py` |
| `ops_daemon.py`, `ops_console.py` | `src/ops/runtime/daemon.py::OpsDaemon`, `src/ops/console/reports.py` |
| `publish.py` | `src/export/publisher.py::publish_day` |
| `write_user_output.py` | `src/export/user_output.py` |
| `compile_users.py` | `src/users/compile.py` |
| `run_once.py` | `src/orchestrator.py::main(["--once", ...])` rồi `src/pipeline/derive.py::rederive_incremental` |

Danh sách đầy đủ kèm nơi gọi: `SCRIPT_INVENTORY` trong `tests/repo/test_architecture.py`.

## 4. Luồng capture (ba tầng)

```
morninger ─► orchestrator.run_cycle ─build_scraper─► BaseScraper.run() ─► ScrapeResult
     │              │                                     │  dùng: http_client, dedup, raw_store, extractor
     │              ├─ classify_rule_based ───────────────┘
     │              ├─ writer.enqueue ──► DBWriter thread ──► store.insert_batch ──► monocle.db
     │              ├─ heartbeat.record_* ──► monocle.db
     │              └─ notifier.notify_* ──► <DATA_ROOT>/notifications + stdout
     └─ backfill_deferred → capture_reconcile → (30') rederive_incremental → story_cluster/signals
```

Nguyên tắc phụ thuộc: **scraper không biết DB/notify**. Nó chỉ nhận `http` + `dedup`, ghi Bronze qua `RawStore`,
trả `ScrapeResult`. Không có sentiment ở capture: sentiment do agent `article-processor` sinh trong Article Lane.
Test scraper bằng `FakeHTTP` (`tests/_fakes.py`), không cần DB thật.

## 5. Registry — thêm scraper không sửa core

`src/scrapers/__init__.py` giữ `REGISTRY` và decorator `register(name)`; cuối file import các module scraper để kích hoạt
`@register`. `build_scraper(cfg)` (`src/orchestrator.py`) tra `REGISTRY[cfg["name"]]`, không có thì `REGISTRY["_" + cfg["method"]]`
(vd `method: rss` → `_rss`, `method: rss_capture` → `_rss_capture`).

## 6. HTTP client — hợp đồng dùng chung (`src/crawler/http_client.py`)

- **Rate limit** per-domain, mặc định `http.rate_limit` = 3.0s (`config/settings.yaml`).
- **Retry** urllib3: total=`max_retries` (3), `backoff_factor=1.5`, status `429,500,502,503,504`.
- **UA rotation**: random 1 trong 5 UA/request. **Không** tự khai `Accept-Encoding` (tránh brotli rác).
- **truststore**: dùng OS cert store (hnx.vn chain thiếu intermediate).
- Methods: `get` (text) · `get_bytes` (raw, cho feed) · `get_json` · `post_json` · `get_response` (raw Response, đọc status).

## 7. Điểm quan trọng khi đọc code

- **Không bao giờ raise ra pipeline**: lỗi scraper thành string trong `errors[]` (`BaseScraper.run`).
- **Cap chi tiết** `max_details_per_cycle`: mặc định 30, tnck 40, vndirect 20; YAML ghi đè. Vượt cap → `detail_deferred`, morninger bù.
- **now/tz**: luôn dùng `now_vn_iso()` + `VN_TZ` (`src/core/models.py`), không `datetime.now()` trần.
- **Hash**: `sha256_hash(url, title)` = SHA-256 của chuỗi nối `url+title` = `url_title_hash`, định danh bài xuyên mọi tầng.
- **Không script nào giả lập agent** (AGENTS.md §7.3); `code_first` không bao giờ tính là đã phân tích.

## 8. Chạy nhanh

Venv chuẩn `C:\venvs\news-scape` (ADR-0024), cwd = `project/`:

```powershell
C:\venvs\news-scape\Scripts\python.exe scripts\pipeline_radar.py status     # trạng thái + một lệnh tiếp theo (đọc trước tiên)
C:\venvs\news-scape\Scripts\python.exe scripts\article_run.py --where      # wave đang ở đâu (chỉ đọc)
C:\venvs\news-scape\Scripts\python.exe -m src.morninger --once capture     # một lượt capture
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator --once cafef    # 1 domain, 1 cycle
C:\venvs\news-scape\Scripts\python.exe -m src.monitor.health               # trạng thái + exit code
C:\venvs\news-scape\Scripts\python.exe -m pytest tests/ -q                 # test, xem 04-testing.md
```

Chi tiết vận hành: [../operations/deployment.md](../operations/deployment.md), [../runbook.md](../runbook.md).
