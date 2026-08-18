# Scout 01 — OKF Deep-Integration File Map

## 1. OKF KB content (Web Monocle — SOURCE OF TRUTH, preserve)
- `okf/datasets/`: index.md, web_monocle_db.md
- `okf/tables/`: index.md, articles.md, seen_articles.md, scraper_heartbeat.md, scraper_metrics.md
- `okf/pipelines/`: index.md, ingestion_scheduler.md, db_writer.md, sentiment_pipeline.md
- `okf/metrics/`: index.md, articles_per_day.md, dedup_rate.md, sentiment_distribution.md, scraper_health.md
- `okf/playbooks/`: index.md, runbook.md, deployment.md
- `okf/references/`: index.md, architecture.md, codebase.md
- `okf/configurations/`: index.md, monocle_config.md, source_strategy.md, settings.md, watchlist.md, notifications.md, domain_sources.md
- Root: `okf/index.md` (KB root), `okf/log.md` (changelog)
Total ~30 KB md files.

## 2. OKF python lib (`okf/okf/src/reference_agent/**`) — REUSE candidates
- Core: agent.py, __main__.py, cli.py, runner.py
- bundle/: document.py (KB doc parser), index.py, paths.py, synthesizer.py  ← **document.py = frontmatter/markdown parse, key reuse**
- sources/: base.py, bigquery.py (GCP — ignore), 
- tools/: bundle_tools.py, context.py, source_tools.py, web_tools.py
- viewer/: generator.py + static viz.js/viz.css + templates/viz.html  ← **graph viz reuse (Cytoscape)**
- web/: fetcher.py
- prompts/: reference_instruction.md, web_ingestion_instruction.md
NOTE: agent is hardcoded GCP/Gemini → not runnable as-is; harvest parsers/viewer only.

## 3. Config loaders (project)
- `project/src/core/config.py` — YAML loader (domains/settings/secrets/watchlist), yaml.safe_load + deep-merge
- `project/config/domains.yaml` (master registry), settings.yaml, notifications.yaml, watchlist.yaml, secrets.yaml(gitignored)
- `project/config/domains/*.yaml` — 23 domain files
- Per-domain API schema: `project/domains/{vietstock,cafef}/schema.yaml`

## 4. DB layer (`project/src/db/`)
- store.py (CREATE TABLE DDL = schema source of truth), writer.py (single-writer), dedup.py

## 5. Harness (independent track)
- `harness/HARNESS_RUNBOOK.md` + _VI, `HARNESS_BUILD_FROM_SCRATCH.md` + _VI
- `plans/20260817-1536-harness-h1-newsscape/`: plan.md, phase-01/02/03, research/*, scout/*, reports/01-v2-evaluation.md
- H2 climb artifacts (CLI/SQLite/CONTEXT_RULES/TRACE_SPEC) described in BUILD_FROM_SCRATCH Stage C

## 6. Root docs — status
- `README.md` (minimal VN). **NOT PRESENT at root**: AGENTS.md, CLAUDE.md, CONTEXT_RULES.md, SESSION-LATEST.md, HARNESS_BACKLOG.md (all H1 to-be-created).
- Google upstream boilerplate (IGNORE): okf/README.md, okf/SPEC.md(root), okf/CODE_OF_CONDUCT.md, CONTRIBUTING.md, LICENSE.md

## 7. project/docs/** (existing product docs — OKF sources[] targets)
- design/ (00 e2e-architecture … 12 bronze-to-silver-rules; ARCHITECTURE.md)
- dev/ (01 codebase-guide, 02 data-model-and-db, 03 adding-a-source, 04 testing, 05 known-issues, 06 raw-html)
- domains/ (vn-rss, intl-rss, api-scrapers, exchange-layer0)
- skills/ (cafef, fireant, tnck, rss-sources)  ← harness declared these = OKF too
- operations/ (deployment, troubleshooting), runbook.md
- others/decisions.md ← **existing decision-record convention (ADR-lite)**
- charter.md, charter-executive-summary.md
- reference/meta-schema.annotated.jsonc

## Flags
- `project/docs/others/decisions.md` = existing decision log → OKF `sources:` can point here.
- `project/docs/skills/*` already declared as OKF by harness H1 → reconcile w/ okf/ root KB (two homes for "OKF").
