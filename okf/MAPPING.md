# OKF MAPPING — module ↔ catalog file

Khi động vào code/config bên trái → **đọc để lấy context** và **cập nhật khi thay đổi ngữ nghĩa**
file OKF bên phải. Đây là bản đồ track OKF độc lập (không phải harness `CONTEXT_RULES.md`). Nhà
canonical DUY NHẤT của OKF = [`catalog/`](catalog/). Trang có chủ đề đã khai tử nằm ở `archive/`
và không còn ánh xạ.

Nguyên tắc: OKF chỉ chứa tri thức **bền vững** (schema, thiết kế, ngữ nghĩa domain, hợp đồng,
query pattern). KHÔNG lưu live-state (giá trị metric runtime, sức khỏe hiện thời) — cái đó ở
DB/logs/radar.

Theo ADR-0027, `project/scripts/*.py` chỉ là CLI mỏng; nguồn đúng là module trong `project/src/`.

## Điều phối & entrypoint
| Code (source of truth) | OKF file |
|---|---|
| `project/src/morninger.py`, `project/src/ops/runtime/supervisor.py` | [catalog/pipelines/morninger.md](catalog/pipelines/morninger.md) |
| `project/src/orchestrator.py` | [catalog/pipelines/ingestion_scheduler.md](catalog/pipelines/ingestion_scheduler.md) |
| `project/src/core/proclock.py`, `store.try_acquire_lock` | [catalog/tables/pipeline_state.md](catalog/tables/pipeline_state.md), [catalog/pipelines/morninger.md](catalog/pipelines/morninger.md) |
| `project/src/ops/runtime/daemon.py`, `project/scripts/ops_install.ps1` | [catalog/playbooks/deployment.md](catalog/playbooks/deployment.md), [catalog/playbooks/runbook.md](catalog/playbooks/runbook.md) |

## Bronze / capture
| Code | OKF file |
|---|---|
| `project/src/crawler/raw_store.py`, `robots.py`, `backoff.py` | [catalog/datasets/bronze_raw_html.md](catalog/datasets/bronze_raw_html.md) |
| `project/src/scrapers/**`, `core/base_scraper.py` | [catalog/configurations/source_strategy.md](catalog/configurations/source_strategy.md), [catalog/references/codebase.md](catalog/references/codebase.md) |
| `project/src/core/config.py` (`resolve_source_domain`, `resolve_db_path`) | [catalog/configurations/domain_sources.md](catalog/configurations/domain_sources.md), [catalog/datasets/web_monocle_db.md](catalog/datasets/web_monocle_db.md) |
| `project/src/db/dedup.py`, `project/src/db/registry.py` | [catalog/tables/seen_articles.md](catalog/tables/seen_articles.md), [catalog/metrics/dedup_rate.md](catalog/metrics/dedup_rate.md) |
| `project/src/db/writer.py` | [catalog/pipelines/db_writer.md](catalog/pipelines/db_writer.md) |
| `project/src/monitor/heartbeat.py`, `health.py` | [catalog/tables/scraper_heartbeat.md](catalog/tables/scraper_heartbeat.md), [catalog/tables/scraper_metrics.md](catalog/tables/scraper_metrics.md), [catalog/metrics/scraper_health.md](catalog/metrics/scraper_health.md) |

## DB — DDL tập trung ở `store._SCHEMA`
| Code | OKF file |
|---|---|
| `project/src/db/store.py` (CREATE TABLE, `_MIGRATIONS`), `project/src/db/connect.py` | [catalog/datasets/web_monocle_db.md](catalog/datasets/web_monocle_db.md) + **mọi** file trong [catalog/tables/](catalog/tables/index.md) |
| `project/src/core/paths.py` | [catalog/datasets/web_monocle_db.md](catalog/datasets/web_monocle_db.md), [catalog/datasets/index.md](catalog/datasets/index.md) |

> Đổi 1 dòng DDL trong `store._SCHEMA` ⇒ kiểm lại bảng tương ứng trong `catalog/tables/` **và**
> danh sách 20 bảng ở `web_monocle_db.md`.

## Silver / change-detection
| Code | OKF file |
|---|---|
| `project/src/pipeline/{silver_builder,change_detect,run,derive,drift,refresh}.py` | [catalog/pipelines/silver_derive.md](catalog/pipelines/silver_derive.md), [catalog/tables/article_versions.md](catalog/tables/article_versions.md) |
| `project/src/handoff/{work_package,contract_validator}.py` | [catalog/datasets/silver_work_packages.md](catalog/datasets/silver_work_packages.md) |
| `project/src/handoff/catalog.py` | [catalog/tables/work_items.md](catalog/tables/work_items.md), [catalog/metrics/silver_backlog.md](catalog/metrics/silver_backlog.md) |

## Article Lane (Vòng 3 — đường duy nhất)
| Code (source of truth) | OKF file |
|---|---|
| `project/src/ops/wave/article_run.py`, `project/src/article_lane/{pack,expand,tick,handoff}.py` | [catalog/pipelines/article_lane.md](catalog/pipelines/article_lane.md), [catalog/datasets/silver_work_packages.md](catalog/datasets/silver_work_packages.md) |
| `project/scripts/build_article_prefix.py`, `project/src/agent/packet/prefix.py` | [catalog/pipelines/article_lane.md](catalog/pipelines/article_lane.md), [catalog/metrics/cache_hit_floor.md](catalog/metrics/cache_hit_floor.md) |
| `project/src/agent/packet/{distill,pruner,silver_source}.py`, `project/src/agent/catalog/intent_resolve.py` | [catalog/pipelines/article_lane.md](catalog/pipelines/article_lane.md), [catalog/configurations/entity_registry.md](catalog/configurations/entity_registry.md) |
| `project/src/agent/runners/{agy,opencode,openrouter}_runner.py` | [catalog/pipelines/article_lane.md](catalog/pipelines/article_lane.md) |
| `project/src/agent/ingest/{runner,l1_runner,batch_handoff}.py` | [catalog/pipelines/agent_handoff.md](catalog/pipelines/agent_handoff.md), [catalog/tables/l1_outputs.md](catalog/tables/l1_outputs.md), [catalog/tables/agent_outputs.md](catalog/tables/agent_outputs.md), [catalog/tables/l1_tasks.md](catalog/tables/l1_tasks.md) |
| `project/src/agent/contract/{dod,l1_router,article_contract,conformance}.py`, `project/schemas/**` | [catalog/references/agent_contracts.md](catalog/references/agent_contracts.md), [catalog/metrics/dod_pass_rate.md](catalog/metrics/dod_pass_rate.md) |
| `project/src/agent/catalog/{entities,l1_classifier,catalog_build}.py`, `project/config/entities/**` | [catalog/configurations/entity_registry.md](catalog/configurations/entity_registry.md) |
| `.agents/dsh/presets/news-scape-conductor/**` (persona của row `tool-subagent-article`) | [catalog/pipelines/article_lane.md](catalog/pipelines/article_lane.md) |

> Sinh lại prefix ⇒ **phải dán lại persona vào preset** rồi chạy `build_article_prefix.py
> --check`. Persona lệch tệp prefix là lỗi duy nhất không có triệu chứng nào ngoài hoá đơn.

## Đo chi phí và bộ nhớ đệm
| Code / config | OKF file |
|---|---|
| `project/config/token_pricing.yaml` | [catalog/configurations/token_pricing.md](catalog/configurations/token_pricing.md) |
| `project/src/telemetry/dsh_usage.py` | [catalog/references/token_economy.md](catalog/references/token_economy.md), [catalog/tables/token_ledger.md](catalog/tables/token_ledger.md) |
| `project/src/article_lane/ledger.py` | [catalog/tables/token_ledger.md](catalog/tables/token_ledger.md), [catalog/metrics/cache_hit_floor.md](catalog/metrics/cache_hit_floor.md) |
| `project/scripts/estimate_wave.py`, `project/src/ops/console/radar.py` | [catalog/references/token_economy.md](catalog/references/token_economy.md), [catalog/metrics/cache_hit_floor.md](catalog/metrics/cache_hit_floor.md), [catalog/playbooks/runbook.md](catalog/playbooks/runbook.md) |

## Lớp người dùng
| Code / config | OKF file |
|---|---|
| `project/src/users/compile.py`, `project/src/core/user_manifest.py`, `<DATA_ROOT>/subscriptions/**` (seed `users/subscriptions/`) | [catalog/configurations/user_subscriptions.md](catalog/configurations/user_subscriptions.md) |
| `project/src/export/{user_output,xlsx_delivery,checkpoint}.py` | [catalog/pipelines/user_output.md](catalog/pipelines/user_output.md), [catalog/datasets/user_deliverables.md](catalog/datasets/user_deliverables.md) |
| `project/src/agent/contract/article_contract.py` (`analyzed_l1_sql`) | [catalog/pipelines/user_output.md](catalog/pipelines/user_output.md), [catalog/tables/l1_outputs.md](catalog/tables/l1_outputs.md) |

## Config hệ thống
| Code / config | OKF file |
|---|---|
| `project/config/settings.yaml` + `src/core/config.py` | [catalog/configurations/settings.md](catalog/configurations/settings.md) |
| `project/config/secrets.yaml(.example)` | [catalog/configurations/secrets.md](catalog/configurations/secrets.md) |
| `project/config/watchlist.yaml` + `src/core/tickers.py` | [catalog/configurations/watchlist.md](catalog/configurations/watchlist.md) |
| `project/config/notifications.yaml` + `src/notifier/file_notify.py` | [catalog/configurations/notifications.md](catalog/configurations/notifications.md) |
| `project/config/domains/*.yaml` | [catalog/configurations/domain_sources.md](catalog/configurations/domain_sources.md) |

## Kiến trúc / vận hành
| Nguồn | OKF file |
|---|---|
| `project/docs/design/00,02` | [catalog/references/architecture.md](catalog/references/architecture.md) |
| `project/docs/dev/01-codebase-guide.md`, `project/src/**` | [catalog/references/codebase.md](catalog/references/codebase.md) |
| `project/docs/operations/{deployment,troubleshooting,ops-daemon}.md` | [catalog/playbooks/runbook.md](catalog/playbooks/runbook.md), [catalog/playbooks/deployment.md](catalog/playbooks/deployment.md) |

## Provenance & phân quyền
- Mỗi file catalog giữ frontmatter `sources[].resource` trỏ về **file có thật** trong repo
  (code hoặc `project/docs/**`). `okf_check` bỏ qua `resource` top-level và mọi path là thư mục.
- Ghi OKF: tooling `okf/tools/` hoặc human/agent đóng vai knowledge-manager. Agent khác đọc
  read-only.
- Upstream OKF spec đã pin: xem [`_vendor/VENDOR.md`](_vendor/VENDOR.md).
