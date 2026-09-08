# Phase 01 — Generic `rss_capture` framework + vietnambiz re-enable

## Context links

- Parent plan: [plan.md](plan.md)
- Depends on: nothing. **Blocks phase-02.**
- Research: [researcher-03 §3](research/researcher-03-live-verification-report.md) (vietnambiz live feeds) · [scout-01](scout/scout-01-touchpoints-report.md) (touchpoints)
- Repo docs: `project/docs/dev/03-adding-a-source.md` · `project/docs/design/03-source-strategy.md` · `project/docs/design/06-raw-html-capture.md` · `project/docs/design/07-storage-layers-and-change-detection.md` · `project/docs/design/12-bronze-to-silver-rules.md`

## Overview

| | |
|---|---|
| Date | 2026-09-07 |
| Description | Extract the duplicated "RSS list + Bronze full capture" pattern (`vneconomy.py` ≈ `vietstock.py`) into ONE config-driven class `RssCaptureScraper` (`method: rss_capture`). Then re-enable **vietnambiz** on it with 6 live feeds (3 new), under full Bronze capture. Also truth-sync the badly stale domain matrix docs. |
| Priority | **P0** — framework asset; blocks phase-02 |
| Implementation status | 🔲 Not started |
| Review status | 🔲 Not reviewed |

## Key insights

- **`method: rss` gives NO Bronze.** `RSSScraper.enrich()` (`src/scrapers/rss_generic.py`) calls
  `self.http.get()` → `extract_content()`. `RawStore` is never touched. A "config-only"
  vietnambiz re-enable would therefore violate the plan's Bronze mandate. → Overridden: phase-01
  is cheap-but-not-free.
- **Enabled ≡ capture.** Only 3 of 23 configs are `enabled: true` today (cafef, vietstock,
  vneconomy — all `2026-08-03: focus on cafef + vietstock only`), and those 3 are exactly the
  3 dirs in `data/raw_html/`. The repo's live posture already equates "enabled" with "captures Bronze".
- **Zero orchestrator change needed.** `build_scraper()` (`src/orchestrator.py:52-57`) resolves
  `REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")`. Registering `_rss_capture`
  makes `method: rss_capture` work for any YAML with no code.
- **vietnambiz feeds verified live 2026-09-07:** 6 feeds × 30 items; `quoc-te.rss` = 0 items (dead, skip).
  utf-16-declared/utf-8-served quirk already handled by `_decode_feed`.
- **vietnambiz detail selector was NOT verified by any researcher.** Do **not** invent one.
  Ship without `content_selector` (class default `article`) → `CaptureMixin._density_extract`
  covers a miss and records `missing: ["main_content_node"]`; then verify live in Step 1 and fill it in.
- Docs are stale: `docs/domains/README.md:3` claims "23 domain (22 enabled + 1 disabled)". Reality is 3 enabled.

## Requirements

**Functional**
1. New generic scraper class usable by any RSS source needing Bronze capture, config-only.
2. vietnambiz enabled, 6 feeds, Bronze artifacts written per article, Silver derivable.
3. Feed-level isolation preserved (one dead feed → `self.errors`, other feeds continue).
4. `content:encoded` (if a feed ships it) used as **fallback** content when detail fetch fails — never as a substitute for Bronze capture.

**Non-functional**
- DRY: no third copy of the vneconomy/vietstock body. New class reuses `_clean_title`,
  `_decode_feed`, `_parse_entry_date`, `_inline_content` from `rss_generic`.
- YAGNI: do **not** refactor `vneconomy.py` / `vietstock.py` onto the new class in this phase
  (they work, they are enabled, and rewriting them risks the only 3 live producers).
  Log it as a follow-up.
- Bronze non-negotiables per [plan.md](plan.md#global-non-negotiables-every-phase).

## Architecture

```
config/domains/vietnambiz.yaml (method: rss_capture)
        │
        ▼  Orchestrator.build_scraper → REGISTRY["_rss_capture"]
RssCaptureScraper(CaptureMixin, BaseScraper)
        │ fetch_list()   : N feeds → http.get_bytes → _decode_feed → feedparser
        │ parse_item()   : Article(source_domain=netloc-minus-www, published_at=+07:00,
        │                          metadata={language, feed_name, _inline_html})
        └ enrich()       : CaptureMixin._capture_and_extract(article, article.source_domain,
                                base_url, content_selector)
                             1 robots gate → 2 crawl-delay → 3 backoff → 4 get_response
                             5 ★ RawStore.save (byte-exact, FIRST) → data/raw_html/<domain>/<yyyymmdd>/
                             6 content_html = select_one(selector) | density fallback
                             7 content_text = extract_text(content_html)  [after raw]
```

`domain` passed to `_capture_and_extract` = `article.source_domain` (generic), not a hardcoded
literal like vneconomy's `"vneconomy.vn"` — this is what makes the class reusable.

## Related code files

**Create**
| Path | Note |
|---|---|
| `project/src/scrapers/rss_capture.py` | `RssCaptureScraper`, `@register("_rss_capture")` |
| `project/tests/test_rss_capture.py` | unit tests, `FakeHTTP` |
| `project/tests/fixtures/vietnambiz_capture_feed.xml` | trimmed real feed bytes (≥2 items, keep the utf-16 declaration quirk) |
| `project/tests/fixtures/vietnambiz_detail_page.html` | one real captured article page |
| `project/domains/vietnambiz/schema.yaml` | monitoring contract; **must carry `domain: vietnambiz.vn`** (see phase-03 host-resolution fix) |
| `project/domains/vietnambiz/README.md`, `changelog.md` | mirrors `domains/cafef/`, `domains/vietstock/` |

**Modify**
| Path | Change |
|---|---|
| `project/src/scrapers/__init__.py` | add `rss_capture` to the trailing import tuple |
| `project/config/domains/vietnambiz.yaml` | `enabled: true`, `method: rss_capture`, +3 feeds, `capture`/`compliance`/`language` blocks |
| `project/docs/domains/README.md` | **truth-sync**: line 3 counts, `Enabled` column for all 23 rows, line 34 stats |
| `project/docs/domains/vn-rss.md` | vietnambiz gets its own `### vietnambiz` section (6 feeds, capture method) |
| `project/docs/skills/rss-sources.md` | vietnambiz feed-inventory row → 6 feeds; note `quoc-te.rss` dead |
| `project/docs/dev/03-adding-a-source.md` | new §2b "RSS + Bronze capture (`method: rss_capture`)"; extend §6 checklist with the touchpoints scout-01 found missing (`docs/skills/rss-sources.md`, `README.md` counts, `domains/<name>/schema.yaml`) |
| `project/docs/design/03-source-strategy.md` | §1 method table: add `rss_capture` tier between RSS and API |
| `project/README.md` | source counts (`:115-119`) |

**Read-only reference:** `src/scrapers/vneconomy.py`, `src/scrapers/capture_mixin.py`,
`src/scrapers/rss_generic.py`, `src/crawler/raw_store.py`, `tests/test_vneconomy.py`, `tests/_fakes.py`.

**No change needed** (verified by scout-01 §b3/b4): `src/orchestrator.py`, `src/core/config.py`,
`src/pipeline/*`, `scripts/rederive_from_bronze.py`, `config/watchlist.yaml`, `config/entities/*`.

## Implementation steps

### Step 1 — Verify the vietnambiz detail selector live (do this FIRST)
```bash
curl -sL -A "Mozilla/5.0" https://vietnambiz.vn/chung-khoan.rss | grep -o '<link>[^<]*</link>' | head -3
curl -sL -A "Mozilla/5.0" "<one article url from above>" -o /tmp/vnb.html
# identify the article body container; record the exact selector + the byte size
curl -sL https://vietnambiz.vn/robots.txt
```
Record the verified selector and robots rules in the YAML `pitfalls:` string. If the body
container cannot be pinned down, ship **without** `content_selector` and rely on the density
fallback — do not guess a selector into the config.

### Step 2 — `src/scrapers/rss_capture.py`
```python
"""
RssCaptureScraper — RSS list + Bronze full-capture detail (method: rss_capture).

DRY: gộp pattern trùng lặp vneconomy.py/vietstock.py thành 1 class config-driven.
Nguồn RSS mới cần Bronze capture = 1 file YAML, 0 code.
Registry key '_rss_capture' → build_scraper() map qua `method: rss_capture`.
Raw HTML luôn được RawStore.save TRƯỚC mọi parse (design 06 §2, bất biến AC7).
"""
from __future__ import annotations

import feedparser

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin
# DRY — tái dùng helper của RSSScraper, không copy-paste
from src.scrapers.rss_generic import (
    _clean_title, _decode_feed, _inline_content, _parse_entry_date,
)
from urllib.parse import urlparse


@register("_rss_capture")
class RssCaptureScraper(CaptureMixin, BaseScraper):
    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        self.feeds = config.get("rss", {}).get("feeds", [])
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector") or "article"
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.base_url = config.get("base_url", "")
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()          # RawStore + RobotsGate + SourceBackoff

    def fetch_list(self) -> list[dict]:
        self._details_fetched = 0
        items: list[dict] = []
        for feed_cfg in self.feeds:
            feed_url = feed_cfg["url"]
            feed_name = feed_cfg.get("name", feed_url)
            raw = self.http.get_bytes(feed_url, timeout=self.config.get("timeout", 30))
            if raw is None:
                self.errors.append(f"feed fetch failed: {feed_name}")
                continue                      # feed-level isolation
            feed = feedparser.parse(_decode_feed(raw))
            if feed.bozo and not feed.entries:
                self.errors.append(f"feed parse failed: {feed_name}")
                continue
            for e in feed.entries:
                items.append({
                    "link": (e.get("link") or "").strip(),
                    "title": (e.get("title") or "").strip(),
                    "summary": (e.get("summary") or "").strip(),
                    "author": (e.get("author") or "").strip(),
                    "published_parsed": e.get("published_parsed"),
                    "updated_parsed": e.get("updated_parsed"),
                    "published": e.get("published"),
                    "updated": e.get("updated"),
                    "content": e.get("content"),
                    "_feed_name": feed_name,
                })
        return items

    def parse_item(self, raw: dict) -> Article | None:
        url, title = raw["link"], _clean_title(raw["title"])
        if not url or not title:
            return None
        summary_text = extract_text(raw["summary"]) if "<" in raw["summary"] else raw["summary"]
        return Article(
            url=url,
            title=title,
            source_domain=urlparse(url).netloc.removeprefix("www."),
            summary=summary_text,
            published_at=_parse_entry_date(raw),      # ISO +07:00
            author=raw["author"],
            symbols=tag_tickers(f"{title} {summary_text}", self.watchlist),
            categories=[raw["_feed_name"]],
            metadata={"feed_name": raw["_feed_name"],
                      "language": self.language,
                      "_inline_html": _inline_content(raw)},
        )

    def enrich(self, article: Article) -> None:
        inline = article.metadata.pop("_inline_html", "")   # never persisted as Bronze
        if self._details_fetched >= self.max_details:
            article.content_text = extract_text(inline) or article.summary
            article.metadata["detail_deferred"] = True
            return
        referer = self.base_url or f"https://{article.source_domain}/"
        html = self._capture_and_extract(article, article.source_domain,
                                         referer, self.content_selector)
        if html is None:
            # capture failed/skipped — mixin already set content_text=summary + errors.
            # content:encoded is a *fallback body only*, it is NOT Bronze.
            if inline:
                article.content_html = inline
                article.content_text = extract_text(inline) or article.summary
            return
        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
```

### Step 3 — Register
`src/scrapers/__init__.py`, trailing import tuple → add `rss_capture,` (alphabetical, after `rss_generic`).

### Step 4 — `config/domains/vietnambiz.yaml`
```yaml
name: vietnambiz
enabled: true            # RE-ENABLED 2026-09-07 — 6/7 feed live 30 items (verified curl)
method: rss_capture      # RSS list + Bronze full capture (was: rss — KHÔNG lưu raw)
rate_limit: 3.0
timeout: 30
language: vi
base_url: "https://vietnambiz.vn/"
rss:
  feeds:
    - {url: "https://vietnambiz.vn/chung-khoan.rss",  name: "VietnamBiz Chứng khoán"}   # 30 items
    - {url: "https://vietnambiz.vn/tai-chinh.rss",    name: "VietnamBiz Tài chính"}     # 30 items
    - {url: "https://vietnambiz.vn/vi-mo.rss",        name: "VietnamBiz Vĩ mô"}         # 30 items
    - {url: "https://vietnambiz.vn/doanh-nghiep.rss", name: "VietnamBiz Doanh nghiệp"}  # NEW, 30 items
    - {url: "https://vietnambiz.vn/nha-dat.rss",      name: "VietnamBiz Nhà đất"}       # NEW, 30 items
    - {url: "https://vietnambiz.vn/hang-hoa.rss",     name: "VietnamBiz Hàng hóa"}      # NEW, 30 items
    # quoc-te.rss — 0 item / 356 bytes (verified 2026-09-07): DEAD, không thêm
detail:
  extract_full: true
  # content_selector: "<điền sau Step 1 — KHÔNG đoán>"; bỏ trống → default "article"
  #                   + density fallback của CaptureMixin (ghi missing[main_content_node])
  max_details_per_cycle: 30
capture:
  raw_dir: "data/raw_html"
  min_body_bytes: 2048
compliance:
  respect_robots: true
  proxy_rotation: false
  proxies: []
pitfalls: "XML declaration KHAI utf-16 nhưng serve utf-8 bytes — _decode_feed xử lý (strip encoding attr). 30 items/feed. quoc-te.rss chết (0 item, 2026-09-07). Verified live 2026-09-07."
```

### Step 5 — Tests `tests/test_rss_capture.py`
Copy the shape of `tests/test_vneconomy.py` (`env` fixture = `monkeypatch.chdir(tmp_path)` to
isolate `data/raw_html`; `FakeHTTP(feed_bytes=…, detail_html=…)`). Required cases:
- `test_registered` — `"_rss_capture" in REGISTRY`
- `test_capture_happy_path` — `capture_status == "ok"`; `source_domain == "vietnambiz.vn"`;
  `published_at.endswith("+07:00")`; `metadata["language"] == "vi"`;
  `Path(cap["html_path"]).read_text() == detail_html` (byte-exact, AC2/AC7)
- `test_detail_failure_keeps_summary` — `detail_html=None`, `scraper.backoff = None`;
  `capture_status == "failed"`, error contains `detail fetch failed`
- `test_inline_content_fallback_on_failure` — feed with `content:encoded` + `detail_html=None`
  → `content_html == inline`, capture still `failed` (inline never becomes Bronze)
- `test_max_details_cap` — cap 1, ≥2 entries → `http.detail_calls == 1`, second has `detail_deferred`
- `test_dead_feed_isolated` — one feed returns `None` → error appended, other feed still parses

### Step 6 — `domains/vietnambiz/schema.yaml` (+ README.md, changelog.md)
Mirror `domains/vietstock/schema.yaml`. **Must include** top-level `domain: vietnambiz.vn` —
this key becomes the host-resolution source of truth in phase-03.

### Step 7 — Docs truth-sync
`docs/domains/README.md`: correct line 3 to the real count (**3 enabled** before this phase),
fix the whole `Enabled` column against `grep -H "^enabled:" config/domains/*.yaml`, update line 34
stats, then add vietnambiz's new state. Do not silently propagate the stale "22 enabled" number.

### Step 8 — Live smoke
```bash
cd project
python scripts/diagnose_sources.py vietnambiz
python -m src.orchestrator --once vietnambiz
python scripts/run_once.py vietnambiz          # + Silver re-derive
```

### Step 9 — Evidence capture
Record the artifact + Silver checks (Success criteria) into `domains/vietnambiz/changelog.md`.

## Todo list

- [ ] 1. Verify vietnambiz detail selector + robots.txt live; record findings
- [ ] 2. Write `src/scrapers/rss_capture.py`
- [ ] 3. Register in `src/scrapers/__init__.py`
- [ ] 4. Rewrite `config/domains/vietnambiz.yaml`
- [ ] 5. Fixtures + `tests/test_rss_capture.py` (6 cases), `pytest -q` green
- [ ] 6. `domains/vietnambiz/{schema.yaml,README.md,changelog.md}`
- [ ] 7. Docs: `docs/domains/README.md` truth-sync + `vn-rss.md` + `skills/rss-sources.md` + `dev/03-adding-a-source.md` §2b + `design/03-source-strategy.md` + root `README.md`
- [ ] 8. Live smoke: diagnose → `--once` → `run_once.py`
- [ ] 9. Evidence into `domains/vietnambiz/changelog.md`

## Success criteria

| # | Check | Command / evidence |
|---|---|---|
| S1 | Unit tests green | `pytest -q` (full suite, not just the new file) |
| S2 | Registry wiring | `python -c "from src.scrapers import REGISTRY; print('_rss_capture' in REGISTRY)"` → `True` |
| S3 | Parse health | `python scripts/diagnose_sources.py vietnambiz` → 0 errors, sample items printed |
| S4 | Cycle runs clean | `python -m src.orchestrator --once vietnambiz` → `new>0`, `errors=0` |
| S5 | **Bronze artifact** | `data/raw_html/vietnambiz.vn/<yyyymmdd>/<hash>.html` exists; `sha256sum` of the file == `content_sha256` in the sibling `.meta.json`; `.meta.json` `capture_status == "ok"`, `http_status == 200`, `images[]` non-empty |
| S6 | Bronze WORM | re-run the cycle: existing `.html` bytes unchanged for an already-captured hash |
| S7 | **Silver derive** | `python scripts/run_once.py vietnambiz` → `data/silver/vietnambiz.vn/<yyyymmdd>/<hash>.json` with non-empty `cleaned_text` and `built_from_raw_path` pointing at S5's file |
| S8 | Quality gate | `python scripts/verify_quality.py vietnambiz.vn` → ≥95% title+body+date |
| S9 | No drift | `python scripts/report_drift.py` → no new `SELECTOR_BROKEN` for vietnambiz |
| S10 | Selector health | across S4's captures, `missing` contains `main_content_node` in <10% of `.meta.json` files |

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Unverified vietnambiz body selector → density fallback on every article | Med | Med (noisier Silver `cleaned_text`) | Step 1 verifies live before shipping; S10 measures it; `_density_extract` is a real fallback, not a failure |
| New generic class regresses nothing but is a 4th capture path to maintain | Low | Low | It is strictly less code than a 3rd + 4th copy-paste; vneconomy/vietstock untouched |
| 6 feeds × 3 s + 30 details × 3 s ≈ 108 s/cycle vs 15-min scheduler | Low | Low | Well inside the interval; `max_details_per_cycle: 30` caps the tail |
| `_inline_content` is a private helper of `rss_generic` | Low | Low | Repo already cross-imports `_clean_title`/`_decode_feed` across scraper modules — same convention |
| Docs truth-sync surfaces that ~20 domains are silently disabled | Med | Low (informational) | Report it; do NOT mass re-enable in this phase (out of scope, no Bronze capture on `method: rss`) |

## Security considerations

- `respect_robots: true`; `RobotsGate` blocks disallowed URLs before any fetch (`capture_status: skipped_robots`).
- `rate_limit: 3.0` per domain; `SourceBackoff` escalates 2→4→8→16 s on 429/503.
- `RawStore._filter_headers` whitelists 6 response headers — `Set-Cookie`/`Authorization` never persisted.
- No secrets: vietnambiz needs no auth; nothing read from `config/secrets.yaml`.
- Bronze artifacts are third-party copyrighted content stored locally as WORM — internal analysis only; do not redistribute raw `.html`.
- `content:encoded` inline HTML is untrusted markup from a remote feed; it only ever reaches `extract_text()`, never `eval`/template rendering.

## Next steps

→ [phase-02-tbtc-new-source.md](phase-02-tbtc-new-source.md), which is YAML-only **because** this
phase exists. Follow-up (not in this plan): collapse `vneconomy.py` and `vietstock.py` onto
`RssCaptureScraper` once it has run clean for a week.

## Unresolved questions

1. **vietnambiz article body selector** — not verified by any researcher. Resolved by Step 1, or
   accepted as density-fallback. Blocking for S10 only.
2. **vietnambiz robots.txt** — never fetched (researcher-02 `[UNVERIFIED]`). Step 1 must fetch it;
   if it disallows article paths, the phase stops and vietnambiz stays disabled.
3. **Is `domains/<name>/schema.yaml` mandatory?** (scout-01 §d) — this plan treats it as
   **mandatory for every source it touches**, because phase-03 makes it the host-resolution
   source of truth. Confirm with maintainer.
4. **~20 domains disabled since 2026-08-03** — is the freeze still intentional? Out of scope here,
   but the docs truth-sync will make it visible and it needs an owner decision.
