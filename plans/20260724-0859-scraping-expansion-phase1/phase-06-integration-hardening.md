# Phase 06 — Integration & Hardening: Orchestrator, 24h Stability, Tuning, Docs

## Context Links
- Parent plan: [plan.md](plan.md)
- Depends on: ALL phases 1-5
- Spec: `docs/system-prompt.md` §11 (orchestrator architecture), §12 (graceful shutdown), §13 Sprint 5
- Research: [research/researcher-02-ops-sentiment-report.md](research/researcher-02-ops-sentiment-report.md) §1 (APScheduler coalesce/misfire), §2 (WAL checkpoint)
- Modules integrated: `src/scrapers/*` (cafef, vietstock, tnck, fireant, rss_generic×4 configs), `src/processor/pipeline.py`, `src/db/writer.py`, `src/monitor/*`, `src/notifier/file_notify.py`

## Overview
- **Date:** 2026-07-24
- **Description:** Single orchestrator process: APScheduler 15-min cycle (coalesce=True, max_instances=1), config-driven scraper registry (scan `config/domains/*.yaml`), full pipeline per cycle, graceful shutdown, 24h end-to-end stability test, performance tuning, Phase 1 wrap-up docs.
- **Priority:** High (converts modules into the deliverable working system)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights
- Spec singleton rule: "1 cycle chạy xong mới chạy cycle tiếp" → APScheduler `max_instances=1` + `coalesce=True` + `misfire_grace_time=300` is exactly this (research-02 §1); no external cron/Task Scheduler needed — orchestrator is a long-running foreground process (start via `python -m src.orchestrator`; optional Windows auto-start = Task Scheduler "At log on" launching it, documented not scripted — KISS).
- Registry must be config-driven (spec: add domain without touching orchestrator): map `method:` field in each domain yaml → scraper class (`api` needs explicit `scraper_class` key e.g. `cafef` → `CafeFScraper`; `rss` → `RSSScraper` always). Plain dict `SCRAPER_CLASSES = {"cafef": CafeFScraper, ...}` in `src/scrapers/__init__.py` — one-line addition per new API scraper, zero orchestrator edits (registry lives with scrapers, acceptable per spec intent).
- Cycle time budget: measured in Phase 3/5 (~est. 4-8 min sequential worst case with detail fetches). If >12 min → tuning options in order: reduce `max_details_per_cycle`, reduce TNCK phrase passes, THEN consider ThreadPool of scrapers (different domains = independent rate-limit buckets; DBWriter single-writer already thread-safe) — decide from data, not upfront (YAGNI).
- Sequential-first: spec research question "async hay sequential?" answered by measurement in 24h test, documented in tuning report.
- WAL maintenance: `PRAGMA wal_checkpoint(TRUNCATE)` after each cycle end (idle moment) keeps -wal small on Windows.
- 24h test = the acceptance gate for all Phase 1 metrics (500/day, 95% quality, 99.5% uptime).

## Requirements
1. `src/orchestrator.py`: discovers enabled domain configs, builds scrapers, runs cycle: per scraper → heartbeat start → run_with_fallback (Phase 4) → pipeline (classify+sentiment+fuzzy dedup) → DBWriter enqueue → heartbeat result → notify summary.
2. APScheduler: `CronTrigger(minute="*/15")`, `coalesce=True`, `misfire_grace_time=300`, `max_instances=1`; immediate first run on start.
3. Graceful shutdown: SIGINT/SIGTERM/CTRL_C → finish current scraper item, flush DBWriter, checkpoint WAL, heartbeat "stopped", exit 0.
4. Disabled config (`enabled: false`) skipped with INFO log.
5. 24h continuous run on target Windows machine, all domains, with metrics capture.
6. Performance tuning report (cycle time, per-domain timings, sequential-vs-thread decision, batch sizes, rate-limit profile).
7. Final Phase 1 docs: architecture.md refresh, per-domain skills complete, ops runbook (start/stop/health/token-refresh/add-domain-in-30-min guide).

## Architecture
```
src/orchestrator.py             # main entry: python -m src.orchestrator [--once]
src/scrapers/__init__.py        # SCRAPER_CLASSES registry
scripts/run_once.py             # delegates to orchestrator --once (single cycle, no scheduler)
docs/runbook.md                 # ops guide
docs/phase1-report.md           # tuning numbers + acceptance evidence
```
**Cycle pseudocode:**
```python
def run_cycle():
    for cfg in load_enabled_domain_configs():           # sorted, deterministic
        heartbeat.record_start(cfg["name"])
        t0 = time.monotonic()
        try:
            result = run_with_fallback(build_scraper(cfg))   # Phase 4 retry/fallback
            for article in result.new:
                process(article)                              # classify + sentiment + fuzzy dedup
                writer.enqueue(article)
            heartbeat.record_result(cfg["name"], "success" if not result.errors else "partial",
                                    metrics=(result.fetched, len(result.new), len(result.errors), ms(t0)))
        except Exception as e:                                # PermanentError or exhausted retries
            logger.exception(...); heartbeat.record_result(cfg["name"], "failed", str(e))
    writer.flush(); store.wal_checkpoint()
    notifier.cycle_summary(...)
scheduler = BlockingScheduler()
scheduler.add_job(run_cycle, CronTrigger(minute="*/15"), coalesce=True,
                  misfire_grace_time=300, max_instances=1, next_run_time=datetime.now())
```

## Related Code Files
**Create:** `src/orchestrator.py`, `docs/runbook.md`, `docs/phase1-report.md`, `tests/test_orchestrator.py`, `scripts/watch_24h.py` (hourly snapshot: articles count, heartbeat states, cycle durations → CSV)
**Modify:** `src/scrapers/__init__.py` (SCRAPER_CLASSES registry), `scripts/run_once.py` (delegate to orchestrator --once), `src/run_collection.py` (DELETE — superseded), `README.md` (final: quick start = `python -m src.orchestrator`), `docs/architecture.md` (final diagram matching spec §11), `requirements.txt` (pin versions after 24h validation)
**Delete:** `src/run_collection.py`

## Implementation Steps
1. `SCRAPER_CLASSES` registry + `build_scraper(cfg)` factory (resolves class from `method`/`scraper_class`, injects HTTPClient/dedup/config); unit test: every yaml in `config/domains/` resolves to a class (config-drift guard).
2. Implement `run_cycle()` per pseudocode; `--once` flag runs single cycle then exits (CI/test friendly).
3. Scheduler wiring + `next_run_time=now` immediate first run; log cycle start/end + duration INFO.
4. Graceful shutdown: install signal handlers → set `stop_event`; BaseScraper checks event between items; finally-block: writer.stop(flush=True), `PRAGMA wal_checkpoint(TRUNCATE)`, heartbeat stopped. Test: CTRL+C mid-cycle → DB intact (`PRAGMA integrity_check` ok), no orphan -wal growth.
5. `tests/test_orchestrator.py`: mock scrapers — one success + one raising → cycle completes, heartbeats correct, writer flushed; `--once` exits 0.
6. Dry integration: 3 consecutive `--once` cycles all domains; fix integration bugs (dedup interplay RSS×API, symbol tagging consistency, timing).
7. **24h stability run:** start orchestrator + `scripts/watch_24h.py`; disable Windows sleep; capture: total articles, per-domain counts, quality % (verify_quality.py), cycle durations (min/avg/max), failures + recovery, memory RSS trend (leak check), -wal file size trend.
8. Analyze vs targets: ≥500 articles/day, ≥95% quality, ≥99.5% uptime (≤~1 failed cycle/96), cycle < 15 min always. Miss → tune (detail caps, pageSize, phrase rotation; escalate to ThreadPool only if sequential provably can't fit) → re-run affected window.
9. Write `docs/phase1-report.md`: metrics evidence, sequential-vs-async decision + data, known limitations (FireAnt manual token, sentiment accuracy, deferred details), Phase 2 recommendations (Playwright need?, ClickHouse?, LLM sentiment).
10. Write `docs/runbook.md`: start/stop, health check command, log locations, notify log, FireAnt token refresh procedure, "add new domain in 30 min" walkthrough (yaml template + checklist), backup (`copy data\articles.db` after checkpoint), Task Scheduler auto-start note.
11. Final sweep: README/architecture final, version pins, full `pytest` green, `grep -ri hermes|clickhouse|telegram src/ config/ docs/ README.md` → 0 relevant hits.

## Todo List
- [ ] Registry + factory + config-drift test
- [ ] run_cycle() + --once mode
- [ ] APScheduler wiring (coalesce, misfire 300, max_instances 1)
- [ ] Graceful shutdown + WAL checkpoint + integrity test
- [ ] test_orchestrator.py green
- [ ] 3× dry integration cycles clean
- [ ] 24h stability run + watch_24h.py capture
- [ ] Metrics vs targets analysis + tuning + phase1-report.md
- [ ] runbook.md (incl. 30-min add-domain guide)
- [ ] Final docs/README/pins sweep, all tests green

## Success Criteria
- 24h unattended run: ≥500 articles from ≥5 domains, ≥95% quality, ≥99.5% cycle success, zero crashes, zero DB corruption, stable memory.
- Kill/restart mid-cycle → clean recovery next cycle (coalesce prevents pile-up).
- New-domain walkthrough executed by checklist in ≤30 min (validated with vietstock_rss or dummy).
- All spec §13 Sprint 5 boxes satisfied; documentation current.

## Risk Assessment
- **Cycle overrun (>15 min):** coalesce+max_instances prevents overlap (skipped-cycle logged = uptime hit) — tuning levers ordered; ThreadPool contingency scoped (domains independent, single-writer DB safe).
- **Windows sleep/update during 24h test:** disable sleep + pause Windows Update; document in runbook.
- **Memory growth over 96 cycles** (requests-cache SQLite, feedparser, trafilatura): watch_24h tracks RSS; requests-cache TTL 900s + periodic `session.cache.delete(expired=True)` per cycle.
- **One flaky domain poisons uptime metric:** per-scraper uptime measured separately (spec: per scraper); notify surfaces chronic offender for config disable.

## Security Considerations
- Orchestrator runs as normal user, no admin; only outbound HTTP to configured domains.
- Graceful shutdown guarantees no partial txn (single-writer + BEGIN IMMEDIATE).
- Backup copy of articles.db documented; secrets never in backups instructions (separate file).
- Logs rotate (50MB×14d) — no unbounded disk growth.

## Next Steps
Phase 1 complete → Phase 2 backlog (from spec + report): CTCK Layer 2 sources, summarizer/entity extraction, LLM sentiment upgrade, Playwright for JS-rendered targets, ClickHouse evaluation, dashboard.
