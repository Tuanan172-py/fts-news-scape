# Phase 04 — Tests (mirror test_vietstock pattern)

## Context Links
- Template: `tests/test_vietstock.py`
- Mock: `tests/_fakes.py::FakeHTTP` (get_bytes=feed, get_response=detail, get=robots)
- Fixtures from phase-01: `vneconomy_feed.xml`, `vneconomy_detail_page.html`
- Depends: phase-01 (fixtures), phase-03 (scraper)

## Overview
- **Date:** 2026-08-17 | **Priority:** High | **Impl status:** Not started | **Review status:** Not reviewed
- **Description:** Create `tests/test_vneconomy.py` mirroring test_vietstock: registration, capture happy-path (byte-exact bronze), ticker tagging, detail-failure keeps summary.

## Key Insights
- `FakeHTTP(feed_bytes=..., detail_html=...)`: `get_bytes`→feed, `get_response`→FakeResponse(detail). `detail_html=None` → `get_response` returns None (fetch fail path).
- `env` fixture: `monkeypatch.chdir(tmp_path)` isolates RawStore under tmp; builds `ArticleStore`+`DedupCache` as `dedup` arg.
- Byte-exact assertion: `Path(a.metadata["capture"]["html_path"]).read_text(utf-8) == detail_html`.
- No robots_txt passed → RobotsGate `allowed` likely permissive/no-fetch in test; mirror vietstock which passes none. If robots blocks in test, pass `robots_txt="User-agent: *\nAllow: /"` or set `compliance.respect_robots: false` in `_config`. Match whatever test_vietstock does (it passes none and works).

## Requirements
**Functional tests**
1. `test_registered` — `"vneconomy" in REGISTRY` and maps to `VnEconomyScraper`.
2. `test_capture_happy_path` — run() yields new articles; ≥1 `capture_status=="ok"`; `source_domain=="vneconomy.vn"`; `published_at.endswith("+07:00")`; `metadata["language"]=="vi"`; bronze artifact byte-exact; `content_html` non-empty.
3. `test_tickers_tagged` — an entry whose title/summary contains a watchlist symbol → symbol in `a.symbols` (ensure fixture has one; phase-01 requirement).
4. `test_detail_failure_keeps_summary` — `detail_html=None` → `capture_status=="failed"`, `content_text==summary`, error logged.

**Non-functional**
- Offline (no network). Fast.

## Architecture
`FakeHTTP` → `VnEconomyScraper(_config(), http, env)` → `.run()` → assert `ScrapeResult`.

## Related Code Files
- CREATE `tests/test_vneconomy.py`
- USE `tests/fixtures/vneconomy_feed.xml`, `tests/fixtures/vneconomy_detail_page.html`, `tests/_fakes.py`

## Implementation Steps
1. Copy `test_vietstock.py` → `test_vneconomy.py`.
2. Swap imports: `from src.scrapers.vneconomy import VnEconomyScraper`.
3. Fixtures: `vneconomy_feed.xml` (bytes), `vneconomy_detail_page.html` (text utf-8).
4. `_config()`: name `vneconomy`, feeds = vneconomy chung-khoan, `detail.content_selector` = phase-01 value, `watchlist` = symbols present in fixture, `capture`/`compliance` optional (mixin defaults). Mirror vietstock `_config`.
5. Rewrite assertions to vneconomy domain + selector; adjust image-manifest assertion (vietstock checks lazy-resolved "Down-8" — vneconomy has direct `src` on premedia; assert `metadata["capture"]["images"]` non-empty OR drop image assertion if manifest differs — verify RawStore image manifest behavior for direct-src).
6. Ensure a fixture entry carries a watchlist ticker for test 3.
7. Run: `pytest tests/test_vneconomy.py -q`.
8. Full suite: `pytest -q` (no regressions).

## Todo List
- [ ] test_vneconomy.py from vietstock template
- [ ] fixtures in place (phase-01)
- [ ] _config for vneconomy
- [ ] test_registered
- [ ] test_capture_happy_path (byte-exact bronze)
- [ ] test_tickers_tagged
- [ ] test_detail_failure_keeps_summary
- [ ] adjust/verify image-manifest assertion for direct-src
- [ ] pytest tests/test_vneconomy.py green
- [ ] full pytest green

## Success Criteria
- `pytest tests/test_vneconomy.py` all pass.
- Full `pytest` no new failures.
- Bronze byte-exact assertion passes (proves raw persisted unmutated).

## Risk Assessment
- **R1:** Image-manifest assertion copied blindly fails (vneconomy no lazy-load) → assert manifest non-empty or remove; verify RawStore behavior on direct `src`.
- **R2:** Fixture lacks watchlist ticker → test 3 fails; enforce in phase-01.
- **R3:** RobotsGate fetches robots in test → pass `robots_txt` allow-all or `respect_robots:false` in `_config`. Confirm against how vietstock test passes.
- **R4:** Detail fixture selector mismatch → `content_html` empty → density fallback yields something; assert `len>0` not specific class.

## Security Considerations
- Tests offline; no live fetch. Validates robots/failure paths behave (defensive, never-raise contract).

## Next Steps
- Feeds phase-05 (live e2e).
