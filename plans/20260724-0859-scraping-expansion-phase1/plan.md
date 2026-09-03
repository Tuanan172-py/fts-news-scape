# Web Monocle — Scraping Expansion Phase 1 Plan

**Date:** 2026-07-24 | **Status:** Not started | **Progress:** 0%

## Mission
Turn MVP skeleton into professional Vietnamese stock-news scraping system: ≥5 domains, config-driven scrapers, rule-based VN sentiment, SQLite WAL, monitoring — standalone (no Hermes), single Windows machine, Python 3.10+.

## Phases

| # | Phase | File | Status | Progress |
|---|-------|------|--------|----------|
| 1 | Foundation refactor (BaseScraper, WAL, logging, de-Hermes) | [phase-01-foundation-refactor.md](phase-01-foundation-refactor.md) | ✅ Done | 100% |
| 2 | CafeF scraper (API) + domain skill + tests | [phase-02-cafef-scraper.md](phase-02-cafef-scraper.md) | ✅ Done — live gate 100% quality (121 bài) | 100% |
| 3 | API scrapers: TNCK, FireAnt (Vietstock → RSS, P5) | [phase-03-api-scrapers.md](phase-03-api-scrapers.md) | ✅ Done — TNCK live 100% (80 bài); FireAnt mock+401 verified, chờ token user | 100% |
| 4 | Quality layer: sentiment, fuzzy dedup, retry, monitoring, notify | [phase-04-quality-layer.md](phase-04-quality-layer.md) | ✅ Done — sentiment ≥70% gate pass | 100% |
| 5 | RSS layer: generic collector + trafilatura extraction | [phase-05-rss-layer.md](phase-05-rss-layer.md) | ✅ Done — 4 domains (vietstock, vnexpress, baodautu, vneconomy) | 100% |
| 6 | Integration & hardening: orchestrator, stability, docs | [phase-06-integration-hardening.md](phase-06-integration-hardening.md) | 🔶 Orchestrator + tests + runbook done; 24h test = user chạy watch_24h.py | 85% |

**Tests: 80 passed.** Code-review pass done (2 critical fixed: cross-thread SQLite conn cho APScheduler worker, transaction guard DBWriter). Integration cycle đầy đủ: 791 bài mới/cycle, 963 total, health CLI all-OK. baodautu disabled (feeds dormant — 0 items server-side). Progress cập nhật 2026-07-24 bởi Claude (thực thi tự động).

## Dependencies
- P1 blocks all (base abstractions, DB schema, logging, config schema).
- P2 depends on P1. First concrete BaseScraper proof — validates abstraction before P3.
- P3 depends on P2 (reuses CafeF patterns). P4 depends on P1 only → can run parallel with P3.
- P5 depends on P1 + P4 (uses retry/monitor/notify). P6 depends on all.

## Tech Stack (decided — do not relitigate)
requests + BeautifulSoup4 + requests-cache + tenacity (sync, no Scrapy/async), trafilatura, plain sqlite3 (WAL + single-writer queue), APScheduler (coalesce=True), loguru, VietSentiWordNet + underthesea + finance-term lexicon. RSS > reverse API > HTML. 15-min polling, ≥3s/domain rate limit, timeout ≤30s, dedup SHA-256(url+title), raw HTML preserved.

## Success Metrics (from spec §4.3)
- **Quantity:** ≥500 articles/day from ≥5 domains
- **Quality:** ≥95% articles have title + body + date (VN timezone correct)
- **Stability:** ≥99.5% uptime per scraper (excl. network); fallback + 3x retry; no pipeline crash
- **Professional:** add new domain in ~30 min (YAML config + module, zero orchestrator edits); full INFO/WARN/ERROR logging; heartbeat monitoring

## Key Research Assets
- Spec: `docs/system-prompt.md` | Scout: `plans/20260724-0859-scraping-expansion-phase1/scout/scout-01-report.md`
- Research: `research/researcher-01-frameworks-report.md`, `research/researcher-02-ops-sentiment-report.md`
- API docs: `thamkhao/present/docs_cafef/`, `docs_vietstock/`, `docs_fireant/`, `docs_tnck/`

## Resolved Decisions (2026-07-24 — see reports/01-verification-report.md)
1. Dev rules: follow global `~/.claude/workflows/development-rules.md`. ✅
2. FireAnt token: manual update accepted Phase 1; 401 → self-disable + ERROR. Endpoint alive (verified 401 without token). ✅
3. **Vietstock: internal API unreachable via HTTP client (verified) → method = RSS** (60 feeds verified working). Phase 3 scope = TNCK + FireAnt only; Vietstock feeds move to Phase 5. ✅
4. CafeF API verified live: **`Type=1` required** (`Type=2` → empty). ✅
5. NDH dropped → **VnEconomy approved + verified** (`https://vneconomy.vn/*.rss`, has `content:encoded`). ✅
6. TNCK API verified live (gzip; date field = `date`, not `date_unix`). ⚠️ `phrase` filter appeared ignored — validate in P3.

## Remaining Open
- VietSentiWordNet lexicon source/license — resolve in P4 (bundle in `data/lexicon/`).
- Existing tests pass status — baseline in P1.
