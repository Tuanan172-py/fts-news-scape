# Report 01 — Plan audit (pre-implementation), 2026-09-07

Audited: `plan.md` + all 5 phase files, against the real codebase and live sites.
Verdict: **plan is sound, 2 defects found (1 blocking), 3 blocking unknowns closed.**

---

## A. Verified correct — no action

| Plan claim | Evidence |
|---|---|
| `build_scraper` = `REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")` | `src/orchestrator.py:52-57` ✓ → `_rss_capture` registration works, zero orchestrator change |
| `RSSScraper.enrich()` never calls `RawStore` | `rss_generic.py:195-217` — `self.http.get()` → `extract_content()` ✓ **Plan's core premise holds** |
| Only 3 domains enabled, and exactly those 3 capture Bronze | `grep ^enabled: config/domains/*.yaml` → cafef/vietstock/vneconomy; `RawStore` refs → cafef.py, vietstock.py, vneconomy.py; `ls data/raw_html/` → 3 dirs ✓ |
| `_clean_title` / `_decode_feed` / `_parse_entry_date` / `_inline_content` exist as used | `rss_generic.py:33,40,88,97` ✓ |
| `Article(...)` constructor fields | `src/core/models.py` ✓ all fields match |
| `.vn`-suffix hack locations | `scripts/domain_check.py:152`, `src/monitor/domain_reporter.py:126,170` ✓ exact |
| `FakeHTTP(list_json, detail_html, detail_status, robots_txt, feed_bytes, detail_headers)` | `tests/_fakes.py:26-62` ✓ |
| `diagnose_sources.py <name>` takes positional names | `scripts/diagnose_sources.py:146` ✓ |
| `domains/<name>/schema.yaml` carries top-level `domain:` | `domains/cafef/schema.yaml` → `domain: cafef.vn` ✓ → phase-03's `resolve_source_domain` is viable |

---

## B. Defects

### A1 — Phase-01: `RssCaptureScraper` duplicates ~50 lines of `RSSScraper` [design]

Plan's `fetch_list()` is **byte-identical** to `RSSScraper.fetch_list()` (`rss_generic.py:130-158`);
`parse_item()` is `:160-193` minus filters and `link_rewrites`. That contradicts the phase's own
stated DRY requirement.

**Fix — change the base class:**
```python
class RssCaptureScraper(CaptureMixin, RSSScraper):   # was: (CaptureMixin, BaseScraper)
```
Override **only** `__init__` (call `super()`, add `content_selector`/`base_url`, `_init_capture()`)
and `enrich()`. Delete the copied `fetch_list` and `parse_item`.

MRO is safe: `RssCaptureScraper → CaptureMixin → RSSScraper → BaseScraper`; `CaptureMixin` defines
no `__init__`, so `super().__init__(config, http, dedup)` lands on `RSSScraper.__init__`.

**Bonus — closes 2 open questions for free:** the subclass inherits `filter.any` / `filter.none`
and `link_rewrites`. That resolves plan open-question #12 and phase-02 §Unresolved Q2 ("if a TBTC
category is noisy we'd have to port filtering into phase-01") with **zero** extra work.

### A2 — Phase-01: "ship without `content_selector`" would silently hold every article [BLOCKING]

Plan Step 1 says: if the body container can't be pinned down, ship without `content_selector`
(class default `"article"`) and let `_density_extract` cover it.

**That is wrong.** `CaptureMixin._capture_and_extract` does:
```python
if not self._looks_complete(html, selector):
    cap["capture_status"] = "partial"
    cap.setdefault("missing", []).append("incomplete_render")
```
and `_looks_complete` returns `False` when the selector matches nothing. Per design-07 `classify()`,
`partial`/`incomplete_render` ⇒ **`SELECTOR_BROKEN` ⇒ `manual_review` ⇒ the agent holds the package.**
`_density_extract` only repairs `content_html`; it does **not** repair `capture_status`.

Confirmed live: **vietnambiz has no `<article>` tag at all.** So the fallback path would have
marked 100% of vietnambiz captures broken and failed the phase's own S10.

**Fix:** the selector is mandatory, not best-effort. Resolved below.

---

## C. Blocking unknowns closed by live probe

### A3 — vietnambiz (phase-01 §Unresolved Q1 + Q2) — RESOLVED
- **robots.txt:** `User-agent: *` / `Allow: /` — permissive, no `Disallow`, no `Crawl-delay`. Phase proceeds.
- **body: `div.vnbcbc-body`** (`div.vnbcbc-body.vceditor-content[data-role=content]`) — verified
  wrapping the article `<p>` run. Outer `div.post-body-content[data-role=body]` also holds title/author, so it is too wide.
- title `h1.vnbcb-title` · date `span.vnbcbat-data[data-role=publishdate]` (`19:41 | 07/09/2026`)
- **NEW TRAP:** `<meta property="article:published_time" content="2026-09-07T19:41:00">` has **no
  timezone offset**. Harmless today because `_parse_entry_date` reads RSS `pubDate` first — but
  record it so nobody "improves" the date by switching to the meta tag.
- Feed still declares `encoding="utf-16"` while serving utf-8 — quirk confirmed live, `_decode_feed` still needed.

### A4 — baodautu date container (phase-04 §Unresolved Q1, blocking for S7) — RESOLVED
Byte offsets in the live article: date at **16656**, `main.main_content` at 11594,
`#content_detail_news` at **18739** → the date sits **outside** the body, inside main.

Container: **`span.post-time`**, text `" - 07/09/2026 10:38"`.

**Fix:** `date_scope_selector: "span.post-time"` (exact) instead of `main.main_content` (wide).
This eliminates phase-04 Risk row 2 ("regex matches a date inside the article body") outright,
rather than merely narrowing it.

**Bonus:** author is `a.author.cl_green` (`Phong Bình`) — the plan never captured `author` for
baodautu. Cheap addition, `Article.author` already exists.

---

## D. Test-writing trap (no plan change, record only)

### A5 — `FakeHTTP.get_json()` ignores the URL
`tests/_fakes.py:39-40` returns the same `list_json` for **every** call. Phase-03's TNCK scraper
loops 9 zones × 1 page ⇒ the fake replays one zone 9×, yielding 9× duplicate items from a single
`fetch_list()`. Any test asserting item counts must configure a **single zone**, or assert on the
post-dedup set. Same caveat applies to phase-04, which is why that phase already plans to add a
`listing_html` attribute to `_fakes.py`.

---

## E. Applied changes

| File | Change |
|---|---|
| `phase-01-…md` | base class → `(CaptureMixin, RSSScraper)`; drop copied `fetch_list`/`parse_item`; `content_selector: "div.vnbcbc-body"`; robots + no-tz-meta traps into `pitfalls`; Q1/Q2 marked RESOLVED; filter support noted as inherited |
| `phase-02-…md` | §Unresolved Q2 marked RESOLVED (filtering inherited via A1) |
| `phase-03-…md` | A5 caveat added to Step 5 |
| `phase-04-…md` | `date_scope_selector: "span.post-time"`; `author_selector: "a.author"`; Q1 marked RESOLVED; Risk row 2 downgraded |
| `plan.md` | open-question #12 closed |

## Owner decisions recorded (2026-09-07)

1. vietnambiz selectors verified live before shipping — **done**, see A3.
2. `.vn`-hack fix → **in phase-03**.
3. `domains/<name>/schema.yaml` **mandatory** — agreed.
4. ~20 disabled domains — **intentional**; Bronze needs full raw HTML, so each source requires
   per-site research, not RSS breadth. Do not mass re-enable.
5. NSO — **TBTC/baodautu accepted as KTXH proxies** for now.
6. TNCK zone 8 excluded from v1, 7-day review — agreed.

## Unresolved (carried)

- Phase-02 Q1 TBTC volume/day · Q3 category set · Q4 overlap accounting
- Phase-03 Q1 zone 8 (7-day review) · Q2 zones 14/16 unmapped · Q4 ad stripping in Silver
- Phase-04 Q2 listing newest-first · Q3 sitemap backstop (gated) · Q5 category set · Q6 `html-scrapers.md` naming
- Phase-05 G1 NSO connectivity from deployment host
- scout-01: `sample_articles.py` GROUPS + `validate_capture.py` list — treated as optional/cosmetic
