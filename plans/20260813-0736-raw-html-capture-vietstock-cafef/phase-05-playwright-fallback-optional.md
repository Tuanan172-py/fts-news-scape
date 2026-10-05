# Phase 05 — Playwright Fallback for JS/Lazy Edge Cases [DEFERRED / OPTIONAL]

## Context links
- research/researcher-02-capture-architecture.md (§1 HTTP-vs-headless, §2 Playwright render/scroll/network, §6 lazy)
- research/researcher-01-source-structure.md (both sources server-rendered → headless NOT needed today)
- Code: phase-01 `RawStore`, phase-02/03 scrapers

## Overview
- **Date:** 2026-08-13 · **Priority:** P3 (DEFERRED) · **Depends:** phase-01,02,03,06
- **Description:** OPTIONAL headless fallback invoked ONLY when the HTTP `_looks_complete` validity
  check (D1, phase-02/03) fails — empty/short body, container missing, lazy images not materialized,
  JS-injected embeds. Writes the rendered DOM through the SAME `RawStore` with
  `render_method="playwright"`. **Do NOT build unless phase-06 acceptance surfaces real edge cases.**
  YAGNI. When built, must be ANTI-BOT HARDENED (D6): stealth + async.
- **Implementation status:** DEFERRED · **Review status:** NOT REVIEWED

## Key Insights
- Both Vietstock + CafeF ~90% server-rendered → HTTP suffices; headless is 5x slower, 200–500 MB/instance.
- **Trigger is CONTENT-BASED (D1), not static/per-domain**: fires only when `_looks_complete` (phase-02/03)
  returned False → `capture_status=="partial"` + `missing:["incomplete_render"]`, or body under threshold.
  Cache per-domain decision to avoid repeat browser overhead. Only ~5–10% pages (Infographic/E-Magazine).
- **Anti-bot hardening required (D6)**: default headless Playwright is detected by Cloudflare/WAF (esp.
  Vietstock during volatile markets). Use `playwright-stealth` or `undetected-playwright` (strip
  `navigator.webdriver`, spoof fingerprints/UA/viewport); support residential ROTATING proxy for
  high-frequency runs.
- **Async at scale (D6)**: prefer `asyncio` + `async_playwright` over `sync_playwright` +
  ThreadPoolExecutor — sync+threads risks browser-context memory leaks / process crashes under load.
  Sync acceptable only for a small-scale quick start / spike.
- Preserve lazy attrs: do NOT rewrite data-src/srcset; scroll to trigger loads, then `page.content()`.

## Requirements (only if built)
**Functional**
- `HeadlessCapturer.render(url) -> (html:str, meta:dict)`: goto `wait_until="networkidle"`, scroll to
  bottom N times to trigger lazy images, capture `page.content()` + list of network responses (urls/status).
- **Stealth (D6)**: apply `playwright-stealth`/`undetected-playwright` — strip `navigator.webdriver`,
  spoof fingerprint/UA/viewport. Optional residential ROTATING proxy per launch (reuse phase-04 proxy pool).
- Fallback path in `enrich`: fires when D1 `_looks_complete` False (`capture_status=="partial"`/
  `incomplete_render`) AND `config.capture.headless_fallback` true → render, RawStore.save with
  `render_method="playwright"`, `lazy_load_scrolls=N`.
- Cache per-domain render decision (avoid browser when HTTP proven sufficient).
**Non-functional**
- Guarded by config flag default FALSE.
- **Async preferred (D6)**: `async_playwright` for scale; `sync_playwright`+single-worker acceptable
  only for small-scale quick start. No raise.

## Architecture
New `src/crawler/headless.py` (lazy import playwright inside method so base install unaffected):
```
class HeadlessCapturer:
    # D6: stealth applied; async preferred at scale
    async def render(self, url, scrolls=3) -> dict:   # {html, network:[{url,status}], scrolls, render_ms}
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(proxy=self._proxy())   # optional residential rotate
            ctx = await browser.new_context(user_agent=..., viewport=...)
            page = await ctx.new_page()
            await stealth_async(page)                                 # strip navigator.webdriver etc.
            ...  # goto networkidle → scroll N → page.content()
    # sync_playwright variant kept ONLY for small-scale quick start (single worker)
```
`enrich` (both scrapers), AFTER http RawStore save — trigger keyed on D1 validity result:
```
cap = article.metadata["capture"]
if headless_enabled and cap["capture_status"] in ("partial","incomplete"):   # set by _looks_complete (D1)
    r = run_render(url)   # await/async-bridge or sync per config scale
    cap2 = raw_store.save(domain, url, hash+"-rendered", None_response_wrapper(r), render_method="playwright")
    article.metadata["capture_rendered"] = cap2
```
(RawStore needs a small overload to accept raw html string + explicit render_method — extend in this phase.)

## Related code files
- **Create:** `project/src/crawler/headless.py` (async Playwright wrapper + stealth, lazy import).
- **Modify:** `project/src/crawler/raw_store.py` — accept `(html_str, render_method, extra_meta)` overload.
- **Modify:** `cafef.py`, `vietstock.py` — optional fallback branch (config-gated, keyed on D1 result).
- **Modify:** `requirements` / docs — OPTIONAL extras: `playwright` + `playwright-stealth`/
  `undetected-playwright`; `playwright install chromium`. Reuse phase-04 proxy pool for residential rotate.

## Implementation Steps (only if triggered)
1. Add optional deps (playwright + stealth) + install note; lazy import inside `headless.py`.
2. Implement async `render()`: launch (optional proxy) → stealth (strip webdriver, spoof fingerprint) →
   networkidle → scroll loop → `page.content()` + response capture. Keep sync variant only for spike.
3. Extend RawStore for string+render_method input.
4. Add config-gated fallback branch keyed on D1 `_looks_complete` result (`capture_status=="partial"`/
   `incomplete_render`); cache per-domain decision.
5. Tests: mock capturer (no real browser in CI); assert fallback fires ONLY when D1 flagged incomplete.

## Todo list
- [ ] (DEFERRED) headless.py async wrapper + stealth (D6), lazy import
- [ ] (DEFERRED) optional residential rotating proxy (reuse phase-04 pool)
- [ ] (DEFERRED) RawStore string overload + render_method
- [ ] (DEFERRED) config-gated fallback keyed on D1 `_looks_complete` result
- [ ] (DEFERRED) per-domain decision cache
- [ ] (DEFERRED) mocked tests (fallback fires only on D1-incomplete)

## Success Criteria
- Only built if phase-06 finds real JS/lazy gaps. When enabled: incomplete HTTP capture is followed by a
  `render_method="playwright"` artifact preserving lazy attrs → **AC4** for edge cases.
- Default install/runtime unaffected (flag off, no playwright import) → KISS/YAGNI preserved.

## Risk Assessment
- **Scope creep / infra weight**: mitigated by DEFERRED status + config flag default off + evidence gate.
- **CI flakiness / browser binaries**: mock in tests; never launch real browser in CI.
- **Anti-bot (Cloudflare/WAF)**: default headless is detected (esp. Vietstock in volatile markets) →
  mitigate with stealth (`playwright-stealth`/`undetected-playwright`) + residential rotating proxy (D6).
- **Sync+threads instability at scale**: memory leaks / context crashes → prefer `async_playwright` (D6);
  sync only for small-scale spike.

## Security Considerations
- Headless executes remote JS → run sandboxed, no credentials, internal use only.
- Same header/secret hygiene; do not persist cookies.

## Next steps
- Revisit ONLY after phase-06 acceptance report. Otherwise leave deferred.
