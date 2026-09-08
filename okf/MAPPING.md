# OKF MAPPING — module ↔ catalog file

Khi động vào code/config bên trái → **đọc để lấy context** và **cập nhật khi thay đổi ngữ nghĩa**
file OKF bên phải. Đây là bản đồ track OKF độc lập (không phải harness `CONTEXT_RULES.md`). Nhà
canonical DUY NHẤT của OKF = [`catalog/`](catalog/).

Nguyên tắc: OKF chỉ chứa tri thức **bền vững** (schema, thiết kế, ngữ nghĩa domain, hợp đồng,
query pattern). KHÔNG lưu live-state (giá trị metric runtime, sức khỏe hiện thời) — cái đó ở
DB/logs.

## Điều phối & entrypoint
| Code (source of truth) | OKF file |
|---|---|
| `project/src/morninger.py` | [catalog/pipelines/morninger.md](catalog/pipelines/morninger.md) |
| `project/src/orchestrator.py` | [catalog/pipelines/ingestion_scheduler.md](catalog/pipelines/ingestion_scheduler.md) |
| `project/src/core/proclock.py`, `store.try_acquire_lock` | [catalog/tables/pipeline_state.md](catalog/tables/pipeline_state.md) |

## Bronze / capture
| Code | OKF file |
|---|---|
| `project/src/crawler/raw_store.py`, `robots.py`, `backoff.py` | [catalog/datasets/bronze_raw_html.md](catalog/datasets/bronze_raw_html.md) |
| `project/src/scrapers/**`, `core/base_scraper.py` | [catalog/configurations/source_strategy.md](catalog/configurations/source_strategy.md), [catalog/references/codebase.md](catalog/references/codebase.md) |
| `project/src/pipeline/periodic_reports.py`, `scripts/fetch_periodic_reports.py` | [catalog/pipelines/periodic_reports.md](catalog/pipelines/periodic_reports.md), [catalog/tables/periodic_reports.md](catalog/tables/periodic_reports.md), [catalog/datasets/bronze_periodic_reports.md](catalog/datasets/bronze_periodic_reports.md) |
| `project/src/core/config.py` (`resolve_source_domain`) | [catalog/configurations/domain_sources.md](catalog/configurations/domain_sources.md), [catalog/references/codebase.md](catalog/references/codebase.md) |
| `project/src/db/dedup.py` | [catalog/tables/seen_articles.md](catalog/tables/seen_articles.md), [catalog/metrics/dedup_rate.md](catalog/metrics/dedup_rate.md) |
| `project/src/db/writer.py` | [catalog/pipelines/db_writer.md](catalog/pipelines/db_writer.md) |
| `project/src/monitor/heartbeat.py`, `health.py` | [catalog/tables/scraper_heartbeat.md](catalog/tables/scraper_heartbeat.md), [catalog/tables/scraper_metrics.md](catalog/tables/scraper_metrics.md), [catalog/metrics/scraper_health.md](catalog/metrics/scraper_health.md) |

## DB — DDL tập trung ở `store._SCHEMA`
| Code | OKF file |
|---|---|
| `project/src/db/store.py` (CREATE TABLE) | [catalog/datasets/web_monocle_db.md](catalog/datasets/web_monocle_db.md) + **mọi** file trong [catalog/tables/](catalog/tables/index.md) |

> Đổi 1 dòng DDL trong `store._SCHEMA` ⇒ kiểm lại bảng tương ứng trong `catalog/tables/` **và**
> danh sách bảng ở `web_monocle_db.md`.

## Silver / change-detection
| Code | OKF file |
|---|---|
| `project/src/pipeline/{silver_builder,change_detect,run,derive,drift,refresh}.py` | [catalog/pipelines/silver_derive.md](catalog/pipelines/silver_derive.md), [catalog/tables/article_versions.md](catalog/tables/article_versions.md) |
| `project/src/handoff/{work_package,contract_validator}.py` | [catalog/datasets/silver_work_packages.md](catalog/datasets/silver_work_packages.md) |
| `project/src/handoff/catalog.py` | [catalog/tables/work_items.md](catalog/tables/work_items.md), [catalog/metrics/silver_backlog.md](catalog/metrics/silver_backlog.md) |

## Agent handoff (Vòng 3)
| Code | OKF file |
|---|---|
| `project/src/agent/{runner,l1_runner,l1_router,l1_classifier}.py` | [catalog/pipelines/agent_handoff.md](catalog/pipelines/agent_handoff.md), [catalog/tables/l1_tasks.md](catalog/tables/l1_tasks.md), [catalog/tables/l1_outputs.md](catalog/tables/l1_outputs.md), [catalog/tables/agent_outputs.md](catalog/tables/agent_outputs.md) |
| `project/src/agent/{dod,packet,pruner,batch_handoff,manifest,archive}.py`, `project/schemas/**` | [catalog/references/agent_contracts.md](catalog/references/agent_contracts.md), [catalog/datasets/silver_work_packages.md](catalog/datasets/silver_work_packages.md), [catalog/metrics/dod_pass_rate.md](catalog/metrics/dod_pass_rate.md) |
| `project/src/agent/entities.py`, `project/config/entities/**`, `project/data/entities/**` | [catalog/configurations/entity_registry.md](catalog/configurations/entity_registry.md) |

## Lớp người dùng
| Code / config | OKF file |
|---|---|
| `project/src/users/compile.py`, `config/entities/manifest.yaml`, `users/subscriptions/**` | [catalog/configurations/user_subscriptions.md](catalog/configurations/user_subscriptions.md) |
| `project/src/export/{user_output,checkpoint}.py`, `src/pipeline/user_workflow.py` | [catalog/pipelines/user_output.md](catalog/pipelines/user_output.md), [catalog/datasets/user_deliverables.md](catalog/datasets/user_deliverables.md) |

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
| `project/docs/design/00,01,02,11` | [catalog/references/architecture.md](catalog/references/architecture.md) |
| `project/docs/dev/01-codebase-guide.md`, `project/src/**` | [catalog/references/codebase.md](catalog/references/codebase.md) |
| `project/docs/operations/{deployment,troubleshooting,db-health-queries}.md` | [catalog/playbooks/runbook.md](catalog/playbooks/runbook.md), [catalog/playbooks/deployment.md](catalog/playbooks/deployment.md) |
| `project/scripts/run_daily.ps1`, `docs/operations/daily-runbook-per-user.md` | [catalog/playbooks/daily_agent_run.md](catalog/playbooks/daily_agent_run.md) |

## Legacy (đừng mở rộng)
| Code | OKF file |
|---|---|
| `project/src/processor/{sentiment,segment}.py` — cold backup | [catalog/pipelines/sentiment_pipeline.md](catalog/pipelines/sentiment_pipeline.md) (`status: deprecated`) |

## Provenance & phân quyền
- Mỗi file catalog giữ frontmatter `sources[].resource` trỏ về **file có thật** trong repo
  (code hoặc `project/docs/**`). `okf_check` bỏ qua `resource` top-level và mọi path là thư mục.
- Ghi OKF: tooling `okf/tools/` hoặc human/agent đóng vai knowledge-manager. Agent khác đọc
  read-only.
- Upstream OKF spec đã pin: xem [`_vendor/VENDOR.md`](_vendor/VENDOR.md).
