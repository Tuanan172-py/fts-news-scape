# Phase 04 — robots.txt Compliance + Rate-Limit Hardening

## Context links
- research/researcher-02-capture-architecture.md (§5 robots via urllib.robotparser, crawl-delay, ethics)
- research/researcher-01-source-structure.md (Vietstock disallow `/*.js,/*.css,/manager,/export,/cache`; CafeF open)
- Code: `project/src/crawler/http_client.py` (RateLimiter per-domain), scrapers from phase-02/03

## Overview
- **Date:** 2026-08-13 · **Priority:** P1 · **Depends:** phase-02, phase-03
- **Description:** Add a lightweight, cached robots.txt gate (`urllib.robotparser`) checked before each
  detail fetch; honor `Crawl-delay` by feeding it into the existing per-domain `RateLimiter`. Harden
  rate-limit defaults for these two domains. **Rate-limit strategy (D4) = hard limit + adaptive
  backoff + optional proxy rotation** — see below. robots gate is stdlib (no new dep); backoff/pause
  reuse existing client machinery.
- **Implementation status:** PLANNED · **Review status:** NOT REVIEWED

## Key Insights
- Existing `RateLimiter` already serializes per-domain with default 3.0s — good baseline; just needs
  crawl-delay awareness.
- **Existing partial rate-limit support (D4)** — EXTEND, don't rebuild: `HTTPClient` urllib3 `Retry`
  already has `backoff_factor=1.5` + `status_forcelist=[429,500,502,503,504]` (retries within a request),
  and per-domain `RateLimiter` default 3.0s (~hard ceiling ≈ 3 req/s per IP). What's MISSING: a
  SOURCE-LEVEL pause on repeated 429/503 (pause that source, exponential backoff 2→4→8→16s) and an
  optional proxy-rotation hook. Add these; keep the hard limit as-is.
- Proxy rotation = OPTIONAL, config-gated, OFF by default (KISS/YAGNI). Only rotates on backoff.
- Article pages allowed on both; Vietstock disallows asset/`/manager` paths we never fetch → gate is
  cheap insurance + future-proofing + documents ethical intent (legal defensibility).
- `urllib.robotparser` is stdlib, zero-dependency; cache per-domain 24h to avoid refetch.

## Requirements
**Functional**
- `RobotsGate.allowed(url, user_agent="*") -> bool`; fetch+cache `robots.txt` per domain (24h TTL).
- `RobotsGate.crawl_delay(domain) -> float|None`; if set, scraper passes it to `RateLimiter.wait(delay=)`.
- Scrapers call gate before `get_response()` in `enrich()`; if disallowed → skip fetch, record
  `capture_status="skipped_robots"` in `metadata["capture"]`, `self.errors.append("robots disallow: url")`.
- robots.txt fetch failure → FAIL-OPEN (allow) but log WARN (do not block pipeline on robots outage).
- **Adaptive backoff (D4)**: on HTTP 429 or 503 for a source, PAUSE that source and back off
  exponentially 2s→4s→8s→16s (cap 16s, reset on next success). Distinct from urllib3 in-request Retry —
  this is a per-SOURCE cool-down across enrich calls. Implement as a small `SourceBackoff` helper (per-
  domain state: consecutive_throttles, next_allowed_ts) consulted before `get_response` and updated
  from the response status.
- **Optional proxy rotation (D4)**: config-gated (`compliance.proxy_rotation: false` default). When ON
  AND a backoff fires, rotate to next proxy from a configured pool before retry (hook in `HTTPClient`
  session proxies). OFF by default → zero behavior change.
**Non-functional**
- No new pip dependency for robots/backoff (stdlib + existing client). Proxy pool is config-only.
- No raise. Cache/backoff state thread-safe (lock like RateLimiter).

## Architecture
New `src/crawler/robots.py`:
```
class RobotsGate:
    def __init__(self, http, ttl=86400): ...
    def allowed(self, url, ua="*") -> bool          # RobotFileParser per domain, cached
    def crawl_delay(self, domain, ua="*") -> float|None
```
- Fetch robots via `http.get()` (goes through rate limiter) OR direct `RobotFileParser.read()`
  (simpler; but bypasses UA rotation). **Recommend** feed text from `http.get(f"https://{domain}/robots.txt")`
  into `rp.parse(text.splitlines())` → keeps one HTTP path, respects our client.
- Injected into each scraper (construct in `__init__`, shared not required). Gate used only in `enrich`.
- Crawl-delay: `delay = max(config.rate_limit, gate.crawl_delay(domain) or 0)`; pass to
  `http.get_response` path via RateLimiter (add optional `delay` plumb OR pre-`rate_limiter.wait`).
  KISS: since `get_response` doesn't take delay, call `self.http.rate_limiter.wait(url, delay)` is
  internal — instead set effective per-domain delay once at startup (config), and only ADD explicit
  `wait(url, crawl_delay)` before fetch when crawl_delay > config default.

Adaptive backoff + proxy hook (D4) — new `src/crawler/backoff.py`:
```
class SourceBackoff:                       # per-domain cool-down, thread-safe
    def before_fetch(self, domain) -> None # if now < next_allowed_ts: sleep the remainder
    def observe(self, domain, status)      # 429/503 → consecutive++, next_allowed = now + min(2**n,16)
                                           # 2xx → reset consecutive=0
```
Wire in each scraper `enrich`, around `get_response`:
```
self.backoff.before_fetch(domain)
resp = self.http.get_response(url, ...)
self.backoff.observe(domain, resp.status_code if resp else 503)
if resp and resp.status_code in (429, 503) and self.cfg_proxy_rotation:
    self.http.rotate_proxy()               # optional hook, off by default
```
`HTTPClient.rotate_proxy()` = optional thin method setting `session.proxies` from a config pool;
no-op when pool empty. Hard limit (`RateLimiter` 3.0s) stays unchanged underneath.

## Related code files
- **Create:** `project/src/crawler/robots.py` (RobotsGate).
- **Create:** `project/src/crawler/backoff.py` (`SourceBackoff` — D4 adaptive pause).
- **Modify:** `project/src/scrapers/cafef.py`, `project/src/scrapers/vietstock.py` — init gate + backoff,
  check before fetch, honor crawl-delay, record `skipped_robots`, observe status, optional proxy rotate.
- **Modify (optional):** `project/config/domains/{cafef,vietstock}.yaml` — `compliance: {respect_robots:
  true, proxy_rotation: false, proxies: []}`.
- **Modify (D4, optional hook):** `project/src/crawler/http_client.py` — add thin `rotate_proxy()`
  setting `session.proxies` from pool (no-op when empty). `RateLimiter` API otherwise unchanged
  (`wait(url, delay)` already exists; hard limit kept).

## Implementation Steps
1. Create `robots.py`: per-domain `RobotFileParser` cache dict + timestamp + lock; `allowed`, `crawl_delay`.
2. Fetch robots text via `http.get`; on None/exception → fail-open + WARN + cache negative-TTL short.
3. In each scraper `__init__`: `self.robots = RobotsGate(http)` (guard by config `respect_robots`, default true).
4. In `enrich` before fetch: `if respect_robots and not self.robots.allowed(url): record skipped_robots; return`.
5. Compute effective crawl-delay; if > default, `self.http.rate_limiter.wait(url, delay)` before `get_response`.
6. Create `backoff.py` `SourceBackoff` (D4): per-domain state + lock; `before_fetch` sleeps residual
   cool-down; `observe(domain,status)` sets exp backoff 2→4→8→16s on 429/503, resets on 2xx.
7. Wire `SourceBackoff` into both scrapers around `get_response`; on 429/503 + `proxy_rotation` on →
   `self.http.rotate_proxy()`. Add optional `rotate_proxy()` to `HTTPClient` (no-op when pool empty).
8. Add `compliance` yaml block (respect_robots default on; proxy_rotation default off; proxies []).

## Todo list
- [ ] robots.py gate with 24h cache + lock
- [ ] fail-open on robots fetch error (WARN)
- [ ] scrapers check allowed() before fetch
- [ ] skipped_robots recorded in capture metadata
- [ ] crawl-delay honored via RateLimiter
- [ ] `SourceBackoff` adaptive pause 2→4→8→16s on 429/503 (D4)
- [ ] optional `HTTPClient.rotate_proxy()` hook (off by default)
- [ ] yaml compliance block (respect_robots on / proxy_rotation off / proxies[])

## Success Criteria
- Disallowed URL → no detail fetch, `capture_status=="skipped_robots"`, error logged → **AC9**.
- Crawl-delay in robots (if any) increases inter-request delay ≥ specified → **AC9**.
- robots outage → pipeline continues (fail-open), WARN logged → resilience.
- On simulated 429/503, source pauses and inter-request delay grows 2→4→8→16s then resets on 2xx
  (D4) → **AC9** resilience. Proxy rotation only fires when config-enabled (default off, no change).
- No new dependency in requirements (stdlib `urllib.robotparser`; backoff is stdlib) → KISS.

## Risk Assessment
- **Over-blocking** from mis-parsed robots → fail-open default + config toggle mitigates.
- **Extra latency** from robots fetch → cached 24h; negligible.
- **Thread-safety** with APScheduler worker → lock around cache.

## Security Considerations
- Compliance is the security/legal control here: robots + crawl-delay + rate limit + no redistribution
  documents good-faith intent (ToS/legal defensibility per research §5).
- Do not fetch disallowed asset paths; only article detail pages.

## Next steps
- phase-06 tests robots gate (allow/deny/outage) with FakeHTTP.
