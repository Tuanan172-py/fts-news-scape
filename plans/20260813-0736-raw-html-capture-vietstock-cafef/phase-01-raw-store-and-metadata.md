# Phase 01 — Raw Artifact Store + Capture Metadata Schema

## Context links
- research/researcher-02-capture-architecture.md (§3 storage layout, §4 failure schema, §6 lazy preserve)
- scout/scout-01-codebase.md (models.py, store.py, HTTPClient.get_response gaps)
- Code: `project/src/core/models.py`, `project/src/db/store.py`, `project/src/crawler/http_client.py`

## Overview
- **Date:** 2026-08-13 · **Priority:** P0 (foundation; 02/03 depend on it)
- **Description:** Build ONE shared on-disk raw-artifact writer + define capture-metadata shape carried
  in `Article.metadata["capture"]`. No cleaning here. Foundation reused by both scrapers.
- **Implementation status:** PLANNED · **Review status:** NOT REVIEWED

## Key Insights
- Both sources server-rendered ⇒ plain `requests` body IS the full raw HTML (no headless needed).
- `HTTPClient.get_response()` already returns `requests.Response` (status + headers) — use it, not `get()`.
- `Article.metadata` is a free-form JSON dict persisted to `metadata_json` — zero schema churn.
- Raw HTML must be saved BEFORE any parse/clean → AC7 (no normalization) satisfied by ordering.
- `images[]` manifest uses BeautifulSoup READ-ONLY (find `<img>`/`<figure>`, read attrs) AFTER the
  `.html` bytes are already written — this is inspection, NOT cleaning/normalization. AC7 unaffected:
  no `trafilatura`, no tag removal, no attribute rewrite, no re-serialization of the artifact.
- `url_title_hash` (SHA-256) already on `Article` → reuse as artifact filename (stable, collision-safe).

## Requirements
**Functional**
- Write raw HTML byte-exact to `data/raw_html/<domain>/<yyyymmdd>/<hash>.html`.
- Write sidecar `<hash>.meta.json` with: source_url, http_status, response headers (subset),
  fetch_ts (ISO+07:00), content_sha256, content_length_bytes, encoding, render_method (`"requests"`),
  capture_status (`ok|partial|failed`), missing[] (list of absent parts), error (nullable object),
  **`images[]` read-only manifest (D2)**.
- Build `images[]` by scanning the byte-exact raw HTML with BeautifulSoup (READ-ONLY — never mutate
  the `.html`). One entry per `<img>`: `{outer_tag, resolved_url, alt, title, caption}`.
  `resolved_url` = first present of `src, data-src, data-original, original-src, document-path,
  data-lazy`, else first URL in `srcset` (split on comma, take first token before whitespace).
  `caption` = nearest enclosing `<figure>`'s `<figcaption>` text if present, else null. This
  RECONCILES lazy-load (`data-src`) with the no-mutation rule; the `data-src→src` SWAP is a DOWNSTREAM
  parser concern, NOT this phase.
- Return a `capture` dict for `Article.metadata["capture"]` mirroring meta.json (minus body).
- On failure (no body / HTTP 4xx-5xx): still write `.meta.json` with `capture_status=failed`,
  error{type,http_status,message,protection_mechanism}, and if partial body exists write `.html` too.
**Non-functional**
- No network, no cleaning, no tag-stripping. Idempotent (same hash overwrites atomically).
- No raise — errors surface via return value; caller appends to `self.errors`.

## Architecture
New module `src/crawler/raw_store.py`:
```
RawStore(base_dir="data/raw_html")
  .save(domain, url, url_title_hash, response|None, *, fetched_at, missing=None,
        protection=None) -> dict   # the "capture" metadata dict
```
Flow (called from scraper.enrich, FIRST step):
```
resp = http.get_response(url, referer=...)          # status + headers + .text/.content
cap  = raw_store.save(domain, url, hash, resp, fetched_at=now_vn_iso())
article.metadata["capture"] = cap
# THEN existing parse/clean continues (content_html/content_text) unchanged
```
`render_method` fixed `"requests"` in v1 (phase-05 may add `"playwright"`).

### meta.json shape (target)
```json
{
  "source_url": "https://cafef.vn/....chn",
  "url_title_hash": "abc123...",
  "fetch_ts": "2026-08-13T07:36:00+07:00",
  "http_status": 200,
  "response_headers": {"content-type":"text/html; charset=utf-8","content-length":"245678",
                       "last-modified":"...","etag":"...","server":"...","date":"..."},
  "content_sha256": "def456...",
  "content_length_bytes": 245678,
  "encoding": "utf-8",
  "render_method": "requests",
  "capture_status": "ok",
  "missing": [],
  "error": null,
  "images": [
    {"outer_tag": "<img class=\"lazy\" data-src=\"https://.../a.jpg\" alt=\"...\">",
     "resolved_url": "https://.../a.jpg", "alt": "...", "title": null,
     "caption": "Ảnh minh họa"}
  ]
}
```
`images[]` (D2) = READ-ONLY scan of the byte-exact raw HTML; the `.html` file is never touched.
`resolved_url` precedence: `src → data-src → data-original → original-src → document-path →
data-lazy → srcset(first)`. `caption` from enclosing `<figure>/<figcaption>`.
Failure example: `capture_status:"failed"`, `error:{type:"http_error",http_status:403,
message:"Forbidden",protection_mechanism:"bot_challenge"}`, `missing:["article_body"]`, `images:[]`.

## Storage decision (disk vs SQLite BLOB) — justification
- **Disk chosen.** Artifacts are 200–500 KB each; BLOBs bloat WAL DB, slow backups, break offline
  grep/inspection (AC6). Disk files are directly openable, git-ignorable, and decouple raw bytes from
  the queryable metadata row. DB keeps only the pointer (`metadata.capture.*`).

## Related code files
- **Create:** `project/src/crawler/raw_store.py` (RawStore).
- **Create:** `project/data/raw_html/.gitignore` (ignore `*` keep dir) — or add to root `.gitignore`.
- **Modify:** `project/src/core/models.py` — NO field change; document `metadata["capture"]` convention
  in the `Article` docstring only.
- **No change:** `store.py` (metadata_json already persists the capture dict). `http_client.py` unchanged
  (reuse `get_response`).

## Implementation Steps
1. Create `raw_store.py`. `RawStore.__init__(base_dir)`; compute `dir = base/domain/yyyymmdd`,
   `mkdir -p`. `yyyymmdd` derived from `fetched_at` (VN date).
2. `_write_atomic(path, data: bytes)`: write to `path.tmp` then `os.replace` (atomic on same fs).
3. In `save()`: if `response is None` → failed branch (no body). Else read `response.content` (bytes,
   byte-exact, NO decode/normalize). Compute sha256 of bytes. Detect encoding from
   `response.encoding`/apparent. Write `<hash>.html` (bytes).
4. Build meta dict (subset headers only — drop Set-Cookie/Authorization). Set capture_status:
   `ok` if 200 + body>0; `partial` if body>0 but caller passed `missing`; `failed` otherwise.
5. Build `images[]` (D2): `_scan_images(html_bytes) -> list[dict]`. Parse READ-ONLY with BeautifulSoup;
   for each `<img>` record `outer_tag`, `resolved_url` (precedence: src→data-src→data-original→
   original-src→document-path→data-lazy→srcset first token), `alt`, `title`, and `caption` from the
   nearest enclosing `<figure>`'s `<figcaption>`. Empty list on failed/no-body. Never mutate/rewrite.
6. Write `<hash>.meta.json` (UTF-8, `ensure_ascii=False`, indent=2) atomically.
7. Return the meta dict WITHOUT body for `Article.metadata["capture"]`.
8. Add `.gitignore` under `data/raw_html/`.
9. Update `Article` docstring: document `metadata["capture"]` keys (incl. `images`).

## Todo list
- [ ] `raw_store.py` with `save()` + atomic writers
- [ ] sha256 over raw bytes; header subset whitelist
- [ ] ok/partial/failed status logic + error object
- [ ] `_scan_images()` read-only manifest (resolved_url precedence + figcaption pairing)
- [ ] failed-branch still writes meta.json (`images:[]`)
- [ ] `data/raw_html/.gitignore`
- [ ] docstring note in models.py

## Success Criteria
- Given a 200 response, `save()` writes byte-identical `.html` (sha256 matches `response.content`) +
  valid `.meta.json`; returns capture dict → **AC2, AC6**.
- Given `response=None` (fetch fail), writes `.meta.json` with `capture_status=failed` + error, no raise
  → **AC8**.
- No `trafilatura`/normalization/tag-strip in `raw_store.py`; `.html` bytes written before any parse
  and never re-serialized (grep clean of trafilatura) → **AC7**. (Read-only BeautifulSoup used ONLY to
  BUILD `images[]` from the already-written bytes — no mutation of the artifact.)
- `images[]` resolves a lazy-load `data-src` to `resolved_url` while `.html` stays byte-exact → **AC5**.
- Path pattern exactly `data/raw_html/<domain>/<yyyymmdd>/<hash>.{html,meta.json}` → **AC1**.

## Risk Assessment
- **Disk growth** → mitigate: gitignore + note retention as unresolved Q2; small per-file size.
- **Encoding mislabel** (VN utf-8/utf-16): store raw BYTES + record `encoding`; never re-encode → safe.
- **Windows path length / atomic replace across drives** (OneDrive path): keep base under project dir,
  same volume → `os.replace` atomic.

## Security Considerations
- Strip sensitive headers (Set-Cookie, Authorization) from meta.json → no secret/PII leakage.
- No secret logging (convention §4). Raw artifacts may contain third-party content — internal use only.

## Next steps
- phase-02 (CafeF) and phase-03 (Vietstock) wire `RawStore` into `enrich()`.
