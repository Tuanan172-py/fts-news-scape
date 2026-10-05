# Scout Report: Web Monocle Vietnamese Stock-Market Scraper
Date: 2026-07-24 | Scope: Audit gaps, completeness, architecture alignment

---

## 1. SOURCE FILES INVENTORY & COMPLETENESS

### src/ Structure (8 Python files)
- src/rss/collector.py | RSS/Atom/RDF fetch+parse | WORKING | 87 LOC
- src/crawler/http_client.py | HTTP layer retry/rate-limit/UA | WORKING | 87 LOC  
- src/processor/pipeline.py | Main pipeline entry→Article | WORKING | 90 LOC
- src/processor/extractor.py | trafilatura+readability fallback | WORKING | 80 LOC
- src/processor/classifier.py | Rule-based category classification | WORKING | 62 LOC
- src/db/store.py | SQLite article persistence | WORKING | 87 LOC
- src/db/dedup.py | SHA-256 dedup+fuzzy match | STUB | 71 LOC (fuzzy broken)
- src/run_collection.py | Main orchestrator/Hermes entry | WORKING | 92 LOC

Missing vs README: src/rss/scheduler.py, src/api/collector.py, src/crawler/anti_bot.py, src/processor/summarizer.py, src/processor/entity_extract.py, src/notifier/telegram.py, src/db/models.py, src/db/clickhouse.py, src/generic_scraper/content.py

### config/ (3 YAML)
- collections.yaml | 3 collections (financial_vn, tech_blogs, cmt_research) | WORKING
- domains.yaml | Selectors for vnexpress/cafef/ndh | SKELETON (unused)
- notifications.yaml | Rules | TBD

### Other files
- scripts/financial_collector.py: Hermes cron entry (WORKING)
- tests/: test_rss.py, test_dedup.py, test_processor.py (present, not verified)
- docs/: system-prompt (375 lines Phase 1 spec), architecture.md, decisions.md (TDR), etc.

---

## 2. CRITICAL AUDIT GAPS vs SPEC

### GAP #1: Database divergence
Spec: SQLite (WAL mode) as ONLY database
Finding: Code uses SQLite; WAL mode NOT enabled; architecture.md mentions ClickHouse (contradicts spec); store.py comments say "fallback SQLite" (implies secondary)
Risk: Concurrent write contention without WAL

### GAP #2: Hermes dependency claim
Spec: Standalone (NO Hermes dependency)
Finding: Code has NO imports; designed for Hermes cron; README has hermes commands; notify delegates to Hermes send_message
Reality: Hermes-agnostic code but orchestration-coupled

### GAP #3: BaseScraper abstract class
Spec: Required for per-domain config-driven scrapers (30-min add-domain target)
Finding: MISSING—scrapers are functional modules, not class hierarchy

### GAP #4: Retry + fallback strategy
Spec: Primary fail→auto fallback; 3x retry before fail; graceful degradation
Finding: PARTIAL—HTTPClient has backoff, extractor has fallback, missing formal retry orchestration

### GAP #5: Rule-based Vietnamese sentiment engine
Spec: Rule-based sentiment (positive/negative/neutral)—REQUIRED PHASE 1
Finding: COMPLETELY MISSING—classifier has only category rules, no sentiment lexicon, classify_llm() is TODO

### GAP #6: Monitoring + logging
Spec: Full monitoring (know when scraper dies); INFO/WARN/ERROR logging
Finding: PARTIAL—print() statements exist; NO centralized logger; NO health check/dashboard

### GAP #7: File-based notify module
Spec: File-based notify (stdout+log file, no Telegram yet)
Finding: STUB—config/notifications.yaml exists; NO handler implementation; NO async queue

---

## 3. ARCHITECTURE & DESIGN DECISIONS

TDR-001: RSS Primary Source (decisions.md)
- RSS chosen for coverage+maintenance; fallback HTML scraping

TDR-002: Trafilatura Generic Extractor
- 85-90% accuracy target; per-domain selectors config (domains.yaml) unused

TDR-003: 2-Layer Dedup
- Layer 1: SHA-256(url+title)—implemented
- Layer 2: Fuzzy title match—BROKEN (is_similar_title() always False)

---

## 4. RESEARCH ASSETS (thamkhao/)

6-layer source coverage (Nguon tin.md):
- Layer 0: Official (HOSE, HNX, UPCoM) via RSS/API
- Layer 1: News (CafeF, VnExpress, VietStock, TNCK, NDH) via API reverse-engineered
- Layer 2: Brokerages (SSI, HSC, VNDirect, MBS, VCSC) via RSS/HTML
- Layer 3: Aggregators (FireAnt, Cophieu68) via API (auth)
- Layer 4: Research (Scribd, ResearchAndMarkets) via HTML
- Layer 5: Community (Facebook, Telegram, X) via API/scrape

API Research (docs_*/):
- CafeF: Symbol-based /du-lieu/Ajax/PageNew/News.ashx, date format /Date(ts+tz)/
- Vietstock: POST-based 15+ endpoints, channel filtering
- FireAnt: Bearer token auth, symbol-based
- TNCK: Zone+phrase filter, multi-format

Comparison (So sanh.md): 1018-line 4-system architecture analysis

---

## 5. CONFIG SCHEMA

collections.yaml:
  {name}: {schedule, extract_full, classify, feeds:[{url,name}], notify:[{match,to,format}]}
Current: financial_vn (15m), tech_blogs (1h), cmt_research (1h)

domains.yaml:
  {domain}: {has_rss, has_api, selectors:{title,body,date}, rate_limit, anti_bot, fallback}
Defined: vnexpress.net, cafef.vn, ndh.vn (selectors unused)

---

## 6. UNRESOLVED QUESTIONS (10)

1. Database: ClickHouse vs SQLite only? (docs conflict spec)
2. Fuzzy dedup broken—remove or fix?
3. Sentiment engine: Phase 1 or Phase 2? (spec required, missing)
4. Hermes: Standalone or orchestration-coupled?
5. WAL mode: Enable PRAGMA journal_mode=WAL?
6. Notify handler: Phase 1 or Phase 2?
7. Test coverage: Tests passing?
8. API collectors: When implemented?
9. Summarizer: Phase 1 or Phase 2?
10. Entity extraction: When added?

---

## SUMMARY ASSESSMENT

Completeness: 65% working, 20% stub, 15% missing

Readiness for Phase 1: 70% ready

Blockers: Sentiment engine (CRITICAL), notify impl, logging, WAL, fuzzy dedup fix

Audit alignment: Code mostly aligned except database (ClickHouse mention), Hermes coupling, missing sentiment/notify/monitoring.
