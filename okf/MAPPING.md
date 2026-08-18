# OKF MAPPING — module ↔ catalog file

Khi động vào code/config bên trái → **đọc để lấy context** và **cập nhật khi thay đổi ngữ nghĩa** file OKF bên phải. Đây là bản đồ track OKF độc lập (không phải harness `CONTEXT_RULES.md`). Nhà canonical DUY NHẤT của OKF = [`catalog/`](catalog/).

Nguyên tắc: OKF chỉ chứa tri thức **bền vững** (schema, thiết kế, ngữ nghĩa domain, ADR, query pattern). KHÔNG lưu live-state (giá trị metric runtime, health hiện thời) — cái đó ở DB/logs.

## DB / Storage
| Code (source of truth) | OKF file (mô tả) |
|---|---|
| `project/src/db/store.py` (CREATE TABLE DDL) | [catalog/datasets/web_monocle_db.md](catalog/datasets/web_monocle_db.md), [catalog/tables/articles.md](catalog/tables/articles.md) |
| `project/src/db/dedup.py` | [catalog/tables/seen_articles.md](catalog/tables/seen_articles.md) |
| `project/src/db/writer.py` | [catalog/pipelines/db_writer.md](catalog/pipelines/db_writer.md) |
| `project/src/monitor/**` | [catalog/tables/scraper_heartbeat.md](catalog/tables/scraper_heartbeat.md), [catalog/tables/scraper_metrics.md](catalog/tables/scraper_metrics.md) |

## Pipelines
| Code | OKF file |
|---|---|
| `project/src/orchestrator.py`, scheduler | [catalog/pipelines/ingestion_scheduler.md](catalog/pipelines/ingestion_scheduler.md) |
| `project/src/processor/**` (sentiment/classify) | [catalog/pipelines/sentiment_pipeline.md](catalog/pipelines/sentiment_pipeline.md) |
| `project/src/crawler/**`, `project/src/scrapers/**` | [catalog/configurations/source_strategy.md](catalog/configurations/source_strategy.md) |

## Config
| Code / config | OKF file |
|---|---|
| `project/config/domains/*.yaml` + `project/src/core/config.py` | [catalog/configurations/domain_sources.md](catalog/configurations/domain_sources.md) |
| `project/config/settings.yaml` | [catalog/configurations/settings.md](catalog/configurations/settings.md) |
| `project/config/watchlist.yaml` | [catalog/configurations/watchlist.md](catalog/configurations/watchlist.md) |
| `project/config/notifications.yaml` | [catalog/configurations/notifications.md](catalog/configurations/notifications.md) |
| (tổng hợp cấu hình hệ thống) | [catalog/configurations/monocle_config.md](catalog/configurations/monocle_config.md) |

## Metrics (định nghĩa, KHÔNG giá trị)
| Nguồn tính | OKF file |
|---|---|
| `articles` table | [catalog/metrics/articles_per_day.md](catalog/metrics/articles_per_day.md), [catalog/metrics/sentiment_distribution.md](catalog/metrics/sentiment_distribution.md) |
| `seen_articles` | [catalog/metrics/dedup_rate.md](catalog/metrics/dedup_rate.md) |
| `scraper_heartbeat/metrics` | [catalog/metrics/scraper_health.md](catalog/metrics/scraper_health.md) |

## Architecture / Ops
| Nguồn | OKF file |
|---|---|
| `project/docs/design/**`, `project/docs/ARCHITECTURE.md` | [catalog/references/architecture.md](catalog/references/architecture.md) |
| `project/docs/dev/01-codebase-guide.md`, `project/src/**` | [catalog/references/codebase.md](catalog/references/codebase.md) |
| `project/docs/operations/**`, `project/docs/runbook.md` | [catalog/playbooks/runbook.md](catalog/playbooks/runbook.md), [catalog/playbooks/deployment.md](catalog/playbooks/deployment.md) |

## Provenance & phân quyền
- Mỗi file catalog giữ frontmatter `sources[].resource` trỏ về code/`project/docs/**`/decision-record (`project/docs/others/decisions.md`).
- Ghi OKF: chỉ tooling `okftools` (GĐ2+) hoặc human role knowledge-manager. Agent đọc read-only.
- Upstream OKF spec đã pin: xem [`_vendor/VENDOR.md`](_vendor/VENDOR.md).
