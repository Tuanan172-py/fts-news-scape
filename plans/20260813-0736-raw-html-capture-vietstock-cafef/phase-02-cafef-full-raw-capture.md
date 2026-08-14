# Phase 02 — CafeF Full-Raw Capture

## Context links
- research/researcher-01-source-structure.md (CafeF ADDENDUM: server-rendered, metadata in HTML, `#mainContent`)
- scout/scout-01-codebase.md (CafeF gaps a–e)
- Code: `project/src/scrapers/cafef.py`, `project/config/domains/cafef.yaml`, phase-01 `RawStore`

## Overview
- **Date:** 2026-08-13 · **Priority:** P0 · **Depends:** phase-01
- **Description:** Extend `CafeFScraper.enrich()` to save the FULL raw page artifact FIRST (via RawStore),
  keep `#mainContent` only as a captured sub-region reference in `content_html`. Record capture metadata.
  No change to list/API path. Cleaning (trafilatura) stays but runs AFTER raw save, unchanged.
- **Implementation status:** PLANNED · **Review status:** NOT REVIEWED

## Key Insights
- CafeF detail confirmed server-rendered: full body + author `Khánh Hân` + publish `04-08-2026 08:03 AM`
  + category `Doanh nghiệp` + captioned image all present in plain GET.
- Current `enrich()` uses `http.get()` (text only) and stores ONLY `#mainContent` → loses `<head>` meta,
  status, headers, lazy attrs, full-page structure. Fix: switch to `get_response()` + RawStore.
- URL carries `?utm_source=du-lieu`; canonicalize for hash/URL identity but capture the fetched URL as-is.

## Requirements
**Functional**
- Fetch detail via `http.get_response()` (status + headers + bytes).
- FIRST: `RawStore.save(...)` full page → `Article.metadata["capture"]`. Full raw page persisted, not `#mainContent`.
- THEN: parse `#mainContent` into `content_html` (sub-region reference); `extract_text` → `content_text`
  (downstream cleaning, unchanged, AFTER raw save).
- Preserve image/lazy/link/table/caption bytes intact IN the artifact (RawStore writes raw bytes).
  Image identifying info + URL surfaced via RawStore `images[]` manifest (D2, phase-01) — no HTML mutation.
- **Content-based validity check (D1)**: after RawStore save, run `_looks_complete(html,
  self.content_selector)` — true iff body bytes ≥ threshold (config `min_body_bytes`, default ~2 KB)
  AND `#mainContent` present & non-empty AND no known empty-render/error marker. If it returns FALSE →
  set `capture_status="partial"`/`missing:["incomplete_render"]` (candidate for phase-05 Playwright).
  Do NOT statically flag CafeF as JS-needed; ~90% pages pass, only Infographic/E-Magazine may fail.
- **Text-density fallback for content_html (D5)**: if `#mainContent` selector returns empty/missing,
  derive `content_html` sub-region via a text-density extractor (`readability-lxml`/`goose3`). This
  changes ONLY the parsed `content_html` field — the raw `.html` artifact (saved first) is untouched.
- On fetch failure / non-200: RawStore failed-branch + `self.errors.append`, keep summary fallback.
**Non-functional**
- No raise. Honor `max_details_per_cycle` (raw-capture only within cap — see Q1). Rate limit via `http`.

## Architecture
`enrich()` new order:
```
if self._details_fetched >= self.max_details:
    article.content_text = article.summary
    article.metadata["detail_deferred"] = True
    return                                        # (unchanged deferral; no raw capture — see Q1)
resp = self.http.get_response(article.url, referer=f"{self.BASE_URL}/", timeout=...)
cap  = self.raw_store.save("cafef.vn", article.url, article.url_title_hash, resp,
                           fetched_at=article.fetched_at)
article.metadata["capture"] = cap
if resp is None or not resp.ok:
    article.content_text = article.summary
    self.errors.append(f"detail fetch failed: {article.url}")   # cap already recorded failure
    return
self._details_fetched += 1
html = resp.text
node = BeautifulSoup(html, "lxml").select_one(self.content_selector)
if node is not None and node.get_text(strip=True):
    article.content_html = str(node)                       # sub-region ref (primary)
else:
    # D5 parser resilience — text-density fallback; raw .html already saved byte-exact, untouched
    article.content_html = self._density_extract(html) or html
    article.metadata.setdefault("capture", {}).setdefault("missing", []).append("main_content_node")
# D1 content-based validity check (drives optional phase-05 escalation; NEVER mutates raw artifact)
if not self._looks_complete(html, self.content_selector):
    cap["capture_status"] = "partial"
    cap.setdefault("missing", []).append("incomplete_render")
article.content_text = extract_text(article.content_html) or article.summary
```
`_looks_complete(html, selector) -> bool`: `len(html.encode()) >= min_body_bytes` AND selector node
present & non-empty AND no known error/empty-render marker. `_density_extract(html) -> str|None`:
lazy-import `readability`/`goose3`, return main-content HTML sub-region (parser field only).
`RawStore` injected in `__init__` (construct from config `raw_dir` default `data/raw_html`, or shared
singleton passed by orchestrator — prefer construct-in-scraper to avoid orchestrator changes; KISS).

## Related code files
- **Modify:** `project/src/scrapers/cafef.py` — import + init `RawStore`; rewrite `enrich()` per above.
- **Modify:** `project/config/domains/cafef.yaml` — optional
  `capture: {raw_dir: data/raw_html, min_body_bytes: 2048}` block.
- **Optional dep (D5):** `readability-lxml` or `goose3` (lazy-imported; only used on selector miss).
- **Depends:** `project/src/crawler/raw_store.py` (phase-01).

## Implementation Steps
1. Import `RawStore`; in `__init__` set `self.raw_store = RawStore(config.get("capture",{}).get("raw_dir","data/raw_html"))`.
2. Replace `http.get()` with `http.get_response()` in `enrich()`.
3. Call `raw_store.save(...)` as FIRST action after fetch; assign `metadata["capture"]`.
4. Guard `resp is None or not resp.ok` → summary fallback + error; keep going (no raise).
5. Keep `#mainContent` extraction into `content_html` as sub-region; on empty/miss → `_density_extract`
   fallback (D5), record `missing`. Raw artifact never touched.
6. Add `_looks_complete(html, selector)` (D1); mark `capture_status="partial"` + `incomplete_render`
   when it fails (feeds optional phase-05). Add `min_body_bytes` to yaml (default ~2048).
7. Keep `extract_text` AFTER raw save (downstream cleaning untouched).
8. Preserve deferral path; leave note re: Q1 (raw-capture within cap only in v1).

## Todo list
- [ ] init RawStore in CafeFScraper
- [ ] switch to get_response()
- [ ] raw save first + metadata["capture"] (incl. images[] from RawStore)
- [ ] non-200/None failure branch records + falls back
- [ ] #mainContent sub-region ref; empty/miss → `_density_extract` fallback (D5) + missing[]
- [ ] `_looks_complete` validity check (D1) → partial/incomplete_render
- [ ] extract_text remains after raw save
- [ ] yaml capture block (raw_dir, min_body_bytes) (optional)

## Success Criteria
- After enrich on a 200 detail, artifact `.html` exists byte-equal to response; `metadata["capture"].
  capture_status=="ok"` → **AC2, AC4 (server-rendered), AC5 (img bytes in artifact), AC6**.
- `content_html` still holds `#mainContent`; full page in artifact (not replaced) → **AC3**.
- No trafilatura runs before `raw_store.save` (order asserted in test) → **AC7**.
- Detail 404/None → `capture_status=="failed"`, error recorded, `content_text==summary`, no raise → **AC8**.

## Risk Assessment
- **`get_response` returns non-None but 500**: `.ok` guard handles; RawStore records status.
- **Behavior change to existing cafef tests** (they assert `content_html` has mainContent): still true;
  add new assertions in phase-06. FakeHTTP must gain `get_response` (phase-06).
- **utm_source in URL** inflates dedup? URL identity unchanged from today (already used as-is) — no regression.

## Security Considerations
- Same header-subset rule (no Set-Cookie) inherited from RawStore.
- Referer kept to `cafef.vn/` (existing) — no new headers.

## Next steps
- phase-03 mirrors this for Vietstock (dedicated scraper). phase-06 adds tests + FakeHTTP.get_response.
