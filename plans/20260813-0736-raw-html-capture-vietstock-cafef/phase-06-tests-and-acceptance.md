# Phase 06 — Tests + Acceptance Verification

## Context links
- project/docs/dev/03-adding-a-source.md (§5 tests with FakeHTTP, no real network)
- Code: `project/tests/test_cafef.py` (FakeHTTP pattern), phases 01–04
- research/researcher-02-capture-architecture.md (failure schema to assert)

## Overview
- **Date:** 2026-08-13 · **Priority:** P0 · **Depends:** phase-01,02,03,04
- **Description:** Unit + integration tests for RawStore, CafeF/Vietstock capture, robots gate; map every
  acceptance criterion (AC1–AC9) to an asserted test. Extend FakeHTTP with `get_response`. Real captured
  fixtures, no live network.
- **Implementation status:** PLANNED · **Review status:** NOT REVIEWED

## Key Insights
- Existing `FakeHTTP` only has `get_json`/`get`; capture uses `get_response` → must add a fake
  `requests.Response`-like (status_code/ok/headers/text/content).
- Convention: fixtures are REAL captured pages (cafef fixture already exists); add a vietstock detail fixture.
- Order matters: assert raw save happens BEFORE any extract_text (AC7) via call-order spy.

## Requirements
**Functional (tests to write)**
- `test_raw_store.py`: byte-exact html; sha256==bytes; meta.json fields; ok/partial/failed branches;
  failed writes meta w/o body; header subset excludes Set-Cookie.
- `test_raw_store.py` (D2 images manifest): given HTML with a lazy `<img data-src="...">` inside a
  `<figure>/<figcaption>`, `images[]` entry has `resolved_url == the data-src value`, correct `alt`/
  `caption`, AND the on-disk `.html` bytes still contain the ORIGINAL `data-src` (no swap/mutation) →
  proves AC5 met without touching the raw artifact. Also assert `srcset`-only img resolves to first URL.
- `test_cafef_capture.py`: enrich writes artifact; `metadata["capture"].capture_status=="ok"`; content_html
  still has `#mainContent`; 404→failed+summary; order (raw before extract) spy.
- `test_vietstock.py`: fetch_list from fixture RSS; parse_item ISO+07:00/tickers/language; enrich raw-first
  + container selector; failure fallback; register/method resolves.
- `test_robots.py`: allowed/disallowed; crawl-delay honored; robots outage fail-open.
- `test_backoff.py` (D4): simulate 429/503 → `SourceBackoff` grows delay 2→4→8→16s then resets on 2xx;
  proxy rotation invoked ONLY when config-enabled (mock `rotate_proxy`).
- `test_looks_complete.py` (D1): full page → True; short/empty-container/error-marker page → False
  (drives `capture_status="partial"`); assert density fallback populates `content_html` on selector miss
  while raw `.html` unchanged (D5).
- Acceptance matrix test/table asserting AC1–AC9 each covered.
**Non-functional**
- No network (FakeHTTP). `pytest -q` fully green incl. existing suite (no regressions).

## Architecture
Shared test helper `FakeResponse` (in a `tests/conftest.py` or per-file):
```
class FakeResponse:
    def __init__(self, text, status=200, headers=None):
        self.text=text; self.content=text.encode("utf-8")
        self.status_code=status; self.ok=200<=status<300
        self.headers=headers or {"content-type":"text/html; charset=utf-8"}
        self.encoding="utf-8"
```
Extend `FakeHTTP` with `get_response(url,**kw) -> FakeResponse|None` and `get` (robots).

## Related code files
- **Create:** `project/tests/test_raw_store.py`, `project/tests/test_vietstock.py`,
  `project/tests/test_robots.py`, `project/tests/test_cafef_capture.py`,
  `project/tests/test_backoff.py` (D4), `project/tests/test_looks_complete.py` (D1/D5).
- **Create:** `project/tests/fixtures/vietstock_detail_page.html`, `vietstock_feed.xml` (real captured).
- **Modify:** `project/tests/test_cafef.py` — extend FakeHTTP with `get_response` (or move to conftest).
- **Create (opt):** `project/tests/conftest.py` — `FakeResponse`, shared fixtures.

## Implementation Steps
1. Add `FakeResponse` + extend `FakeHTTP.get_response`/`get` (conftest).
2. Write `test_raw_store.py` (all branches + header hygiene + D2 `images[]` lazy-load/figcaption/srcset,
   asserting raw `.html` still holds original `data-src` unmutated).
3. Write `test_cafef_capture.py` incl. call-order spy (patch `extract_text` to assert artifact exists first).
4. Capture real Vietstock detail + one RSS feed as fixtures; write `test_vietstock.py`.
5. Write `test_robots.py` (allow/deny/outage) with fake robots.txt text.
6. Write `test_backoff.py` (D4 exp backoff + reset + gated proxy) and `test_looks_complete.py`
   (D1 True/False cases; D5 density fallback populates content_html, raw unchanged).
7. Add acceptance matrix (parametrized) mapping AC1–AC9 → assertions.
8. Run `pytest -q`; ensure existing cafef/rss tests still green (adjust for new FakeHTTP).

## Todo list
- [ ] conftest FakeResponse + FakeHTTP.get_response/get
- [ ] test_raw_store.py (ok/partial/failed, sha256, headers, D2 images[] lazy/figcaption/srcset)
- [ ] test_cafef_capture.py (+ order spy)
- [ ] vietstock fixtures (detail html + feed xml)
- [ ] test_vietstock.py
- [ ] test_robots.py
- [ ] test_backoff.py (D4) + test_looks_complete.py (D1/D5)
- [ ] acceptance matrix AC1–AC9
- [ ] full pytest green, no regressions

## Success Criteria
- Every AC has ≥1 passing assertion:
  AC1 path/url · AC2 byte-exact artifact · AC3 tags/img/table/link present in artifact ·
  AC4 server-rendered body captured (lazy attrs intact if any; D1 validity check flags incomplete) ·
  AC5 `<img>`+url via read-only `images[]` manifest — lazy `data-src` resolved, raw `.html` unmutated (D2) ·
  AC6 artifact opens offline (read file, parse) · AC7 no clean before raw save (order spy; images[] is
  read-only, raw bytes never re-serialized) ·
  AC8 failed/partial meta recorded · AC9 robots/crawl-delay honored.
- `pytest -q` all green (new + existing).

## Risk Assessment
- **Existing tests break** from FakeHTTP change → centralize in conftest, update imports; low risk.
- **Fixture staleness** (sites change) → fixtures are frozen captures; document capture date in file header.
- **Order-spy brittleness** → assert via artifact-exists check inside patched extract_text, not timing.

## Security Considerations
- Fixtures must not contain secrets/cookies; scrub Set-Cookie from captured headers before committing.
- Tests never hit live network (offline, deterministic).

## Next steps
- Produce acceptance report; if `_looks_complete` (D1) flags real articles incomplete (lazy/JS
  Infographic/E-Magazine) → trigger phase-05 (hardened async+stealth Playwright).
- Update `docs/dev/03-adding-a-source.md` + domain matrix with capture behavior.
