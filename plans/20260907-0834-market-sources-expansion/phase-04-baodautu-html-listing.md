# Phase 04 — Báo Đầu Tư: RSS → bespoke HTML listing scraper

## Context links

- Parent plan: [plan.md](plan.md)
- Depends on: nothing (independent of 01/02/03; may run in parallel with phase-03).
  Soft dependency: phase-03's `resolve_source_domain` is **not** needed here (`baodautu` → `baodautu.vn` already resolves).
- Research: [researcher-03 §2](research/researcher-03-live-verification-report.md) (RSS root-caused dead; pagination, selectors, sitemap all curl-verified) · [scout-01](scout/scout-01-touchpoints-report.md)
- Repo docs: `project/docs/design/03-source-strategy.md` (TDR-001 method priority) · `project/docs/design/06-raw-html-capture.md` · `project/docs/dev/03-adding-a-source.md`

## Overview

| | |
|---|---|
| Date | 2026-09-07 |
| Description | baodautu.vn's RSS is **permanently broken at the server** — every category feed serves the same empty "Trang chủ" channel with a malformed `<link>`. The 14-month-old "re-enable when the feed has items" comment is dead and gets closed out. Replace it with a bespoke HTML listing scraper: category pages `…-d<N>/p<page>`, detail body `#content_detail_news`, and a bespoke `dd/MM/yyyy HH:mm` date parse. Hardest phase in the plan. |
| Priority | **P0** — one of the two headline asks; #1 source for giải ngân đầu tư công / FDI / hạ tầng |
| Implementation status | 🔲 Not started |
| Review status | 🔲 Not reviewed |

## Key insights

- **RSS is dead at the source, not dormant.** All 8 probed feed URLs → HTTP 200, ~1.2 KB, **0 `<item>`**,
  and every one of them returns the *same* channel:
  `<title>Trang chủ</title><link>https://baodautu.vn//.rss</link>` — a malformed double-slash,
  category-less link. `rssMain.html` returns the 34 KB HTML homepage, not a feed. This is a broken
  server-side generator. **Do not re-probe, do not wait for it.** Delete the RSS block and the
  "bật lại khi feed có items" comment from the YAML.
- **This is the repo's first true HTML-listing source.** TDR-001 says RSS > API > HTML; baodautu
  has neither of the first two, and the content is too valuable to drop. Document the exception.
- **Pagination resolved and trap-laden:** page 1 = `https://baodautu.vn/<slug>-d<N>/` (**with**
  trailing slash); page N>1 = `https://baodautu.vn/<slug>-d<N>/p<N>` (**no** trailing slash —
  `…/p2/` returns **404**). Anchors on the page are relative (`<a href="p2" class="pagation_item">`).
- **Listing markup verified:** item `div.thumbblock.thumb275x155`, title link `a.title_thumb_square.fbold`,
  sapo `div.sapo_thumb_news`, category label `span.cl_green`. d2 page 1 = 48,558 B, **31 unique
  article links**; p2 = 49,658 B, 34 links.
- **No publish datetime on the listing** — date is detail-only. So freshness cannot be used to
  prioritise before fetching; rely on listing order (newest first, assumed) + `seen_articles` dedup.
- **Detail is bespoke everywhere:**
  - body **`#content_detail_news`** — the only correct selector.
  - title `div.title-detail` — the page has **no `<h1>` at all**.
  - sapo `div.sapo_detail`; tags `div.tag_detail > .tag_detail_item`; wrapper `main.main_content.main_detail`.
  - published = plain text `07/09/2026 10:38`. **No `<time>`, no `article:published_time`, no JSON-LD.**
  - **Trap:** a JS comment-widget template string `<div class="content">'+content+'</div>'` exists in
    the page source. A naive `.content` selector grabs the wrong node. `#content_detail_news` only.
  - Body paragraphs `<p class="p1" style="text-align: justify;">`, HTML-entity encoded (`&ecirc;`).
- **robots.txt fully permissive:** `User-agent: * / Allow: /`, no `Disallow`, no `Crawl-delay`.
  Repo default `rate_limit: 3.0` still applies — be a good citizen, not a maximaliser.
- **Sitemap is a backstop, not the primary route.** `sitemaps/news-2026-9.xml` = 102 KB, **348 `<url>`**
  for Sep 1–7 → **~50 articles/day**. But `<loc>` is whitespace-padded (needs `.strip()`),
  `<lastmod>` is **date-only**, and there is **no category and no time-of-day** — so it cannot
  target the đầu tư công beat and gives poor freshness ordering. **Deferred to sub-phase 04b**,
  gated on an observed miss rate; 6 categories × 31 links/cycle at a 15-min cadence already
  dwarfs 50 articles/day.

## Requirements

**Functional**
1. Ingest 6 investment-relevant categories via HTML listing; Bronze artifact per detail page.
2. `published_at` parsed from the detail page as ISO `+07:00`; when absent, record it as
   `missing` rather than fabricating a timestamp.
3. Title comes from the listing anchor (detail has no `<h1>`); `div.title-detail` is the cross-check.
4. Never select `.content` — `#content_detail_news` only.

**Non-functional**
- All selectors, category ids and URL forms come from the YAML, not from Python literals — a
  template change must be a config edit.
- KISS: `pages_per_cycle: 1`. Listing-only in v1; no sitemap fetch.
- Bronze non-negotiables per [plan.md](plan.md#global-non-negotiables-every-phase).

## Architecture

```
config/domains/baodautu.yaml (method: baodautu)
   → REGISTRY["baodautu"]
BaodautuScraper(CaptureMixin, BaseScraper)
  fetch_list()
     for cat in listing.categories:                # slug + id + name
       for page in 1..pages_per_cycle:
         url = f"{base}/{slug}-d{id}/"   if page == 1
               f"{base}/{slug}-d{id}/p{page}"  otherwise   # ⚠ NO trailing slash
         html = http.get(url, referer=f"{base}/")
         soup.select("div.thumbblock") → {link, title, sapo, _cat_name, _listing_url}
         (fetch fail / 0 items → self.errors.append, continue — category isolation)
  parse_item()
     Article(url=urljoin(base, href), title=…, source_domain="baodautu.vn",
             summary=sapo, published_at="",       # ← detail-only, filled in enrich()
             categories=[_cat_name], metadata={language, listing_url})
  enrich()
     html = _capture_and_extract(article, "baodautu.vn", f"{base}/", "#content_detail_news")
            ★ RawStore.save FIRST → data/raw_html/baodautu.vn/<yyyymmdd>/
     article.published_at = _parse_detail_date(html)     # AFTER capture, never before
     if not published_at: metadata["capture"]["missing"].append("published_at")
     article.content_text = extract_text(article.content_html) or article.summary
```

`_parse_detail_date(html)` — module-level, pure, unit-testable:
```python
_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})\b")

def _parse_detail_date(html: str, scope_selector: str) -> str:
    """`dd/MM/yyyy HH:mm` plain text → ISO +07:00. baodautu KHÔNG có <time> /
    article:published_time / JSON-LD (verified 2026-09-07). Rỗng khi không khớp —
    KHÔNG bịa timestamp."""
    # 1. thu hẹp về scope (main.main_content) để tránh khớp ngày trong bài/comment
    # 2. lấy match ĐẦU TIÊN
    # 3. datetime(...).replace(tzinfo=VN_TZ).isoformat(timespec="seconds")
```

## Related code files

**Create**
| Path | Note |
|---|---|
| `project/src/scrapers/baodautu.py` | `BaodautuScraper`, `@register("baodautu")`, `_parse_detail_date` |
| `project/tests/test_baodautu.py` | `FakeHTTP`-driven, zero network |
| `project/tests/fixtures/baodautu_listing_d2.html` | real `…/toan-canh-dau-tu-d2/` page (~48.5 KB) |
| `project/tests/fixtures/baodautu_detail_page.html` | real article page (~61.6 KB) — **must retain the `<div class="content">'+content+'</div>'` JS template string** so the trap is regression-tested |
| `project/domains/baodautu/schema.yaml` | contract; `domain: baodautu.vn`, `method: html_listing` |
| `project/domains/baodautu/README.md`, `changelog.md` | monitor-doc convention |

**Modify**
| Path | Change |
|---|---|
| `project/src/scrapers/__init__.py` | add `baodautu` to the trailing import tuple |
| `project/config/domains/baodautu.yaml` | **full rewrite** — delete `rss:` block + the dead re-enable comment; `enabled: true`, `method: baodautu`, `listing:` + `detail:` + `capture:` + `compliance:` |
| `project/docs/domains/README.md` | baodautu row: Loại `VN HTML`, Method `HTML listing + capture`, Enabled ✅, quirk text; line 3 counts; line 34 stats |
| `project/docs/domains/vn-rss.md` | **remove** the baodautu section (it is no longer an RSS source); line 3 count; add a one-line pointer to the new doc |
| `project/docs/domains/html-scrapers.md` | **NEW FILE** — the repo's first HTML-listing source doc; link it from `docs/domains/README.md:38-41` |
| `project/docs/skills/rss-sources.md` | remove/rewrite the baodautu feed row + the "blank lines before `<?xml`" encoding-quirk row (both now moot) |
| `project/docs/design/03-source-strategy.md` | §1 TDR-001: document the HTML-scraping exception and why baodautu earns it |
| `project/README.md` | source counts + the "baodautu (disabled — dormant)" phrase (`:117`) |
| `project/docs/dev/03-adding-a-source.md` | §1 decision tree: add "no RSS **and** no API → HTML listing scraper" branch |

**No change:** `src/orchestrator.py`, `src/core/config.py`, `src/pipeline/*`, `src/crawler/*`.

## Implementation steps

### Step 1 — Re-verify the four fragile facts (they are template-dependent)
```bash
B=https://baodautu.vn
curl -sIL -A "Mozilla/5.0" "$B/toan-canh-dau-tu-d2/"     | head -1   # expect 200
curl -sIL -A "Mozilla/5.0" "$B/toan-canh-dau-tu-d2/p2"   | head -1   # expect 200
curl -sIL -A "Mozilla/5.0" "$B/toan-canh-dau-tu-d2/p2/"  | head -1   # expect 404 (trailing-slash trap)
curl -sL  -A "Mozilla/5.0" "$B/toan-canh-dau-tu-d2/" | grep -c 'thumbblock'
curl -sL  -A "Mozilla/5.0" "$B/robots.txt"
```
Then fetch one article and confirm `#content_detail_news`, `div.title-detail`, and the
`dd/MM/yyyy HH:mm` text, **and** where in the DOM that date string sits (researcher-03 verified
the format but not its container). That container choice is the whole of `date_scope_selector`.

### Step 2 — `src/scrapers/baodautu.py`
Module docstring must record: RSS permanently broken (root cause), the `p<N>` trailing-slash trap,
the `.content` JS-template trap, and that dates are detail-only. Skeleton:

```python
"""
Báo Đầu Tư scraper — HTML listing cho list, capture full raw HTML cho detail.

RSS VĨNH VIỄN HỎNG (verified 2026-09-07): mọi feed trả CÙNG channel rỗng
"Trang chủ" + <link> lỗi https://baodautu.vn//.rss → generator server hỏng,
KHÔNG phải dormant. Không probe lại.

List: category page `<slug>-d<N>/` (trang 1) và `<slug>-d<N>/p<page>` (trang >1;
⚠ THÊM dấu / ở cuối → 404). Item = div.thumbblock, link = a.title_thumb_square.
KHÔNG có ngày đăng trên listing → published_at điền ở enrich() từ trang detail.

Detail: body = #content_detail_news (⚠ KHÔNG dùng .content — trong source có
chuỗi template JS `<div class="content">'+content+'</div>'` của widget bình luận).
Trang KHÔNG có <h1>; title lấy từ listing, đối chiếu div.title-detail.
Ngày = text thuần `dd/MM/yyyy HH:mm`, không <time>/article:published_time/JSON-LD.
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.core.base_scraper import BaseScraper
from src.core.config import load_watchlist
from src.core.models import VN_TZ, Article
from src.core.tickers import tag_tickers
from src.processor.extractor import extract_text
from src.scrapers import register
from src.scrapers.capture_mixin import CaptureMixin

BASE_URL = "https://baodautu.vn"
SOURCE_DOMAIN = "baodautu.vn"
_DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})\b")


def _parse_detail_date(html: str, scope_selector: str) -> str:
    """`dd/MM/yyyy HH:mm` → ISO +07:00. Rỗng nếu không khớp — KHÔNG bịa."""
    try:
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(scope_selector) or soup
        m = _DATE_RE.search(node.get_text(" ", strip=True))
    except Exception:
        return ""
    if not m:
        return ""
    d, mo, y, hh, mm = (int(g) for g in m.groups())
    try:
        return datetime(y, mo, d, hh, mm, tzinfo=VN_TZ).isoformat(timespec="seconds")
    except ValueError:
        return ""


@register("baodautu")
class BaodautuScraper(CaptureMixin, BaseScraper):
    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        listing = config.get("listing", {})
        self.categories = listing.get("categories", [])
        self.pages_per_cycle = listing.get("pages_per_cycle", 1)
        self.item_selector = listing.get("item_selector", "div.thumbblock")
        self.link_selector = listing.get("link_selector", "a.title_thumb_square")
        self.sapo_selector = listing.get("sapo_selector", "div.sapo_thumb_news")
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector", "#content_detail_news")
        self.date_scope = detail.get("date_scope_selector", "main.main_content")
        self.max_details = detail.get("max_details_per_cycle", 30)
        self.base_url = config.get("base_url", BASE_URL)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()

    def _page_url(self, slug: str, cid: int, page: int) -> str:
        """Trang 1 = `…-d<N>/` (CÓ /). Trang >1 = `…-d<N>/p<page>` (KHÔNG có / cuối → 404)."""
        return (f"{self.base_url}/{slug}-d{cid}/" if page == 1
                else f"{self.base_url}/{slug}-d{cid}/p{page}")

    def fetch_list(self) -> list[dict]:
        self._details_fetched = 0
        items: list[dict] = []
        for cat in self.categories:
            for page in range(1, self.pages_per_cycle + 1):
                url = self._page_url(cat["slug"], cat["id"], page)
                html = self.http.get(url, referer=f"{self.base_url}/",
                                     timeout=self.config.get("timeout", 30))
                if html is None:
                    self.errors.append(f"listing fetch failed: {url}")
                    continue                       # category isolation
                found = self._parse_listing(html, cat, url)
                if not found:
                    self.errors.append(f"listing 0 items (template drift?): {url}")
                items.extend(found)
        return items

    def _parse_listing(self, html, cat, listing_url) -> list[dict]:
        # BeautifulSoup(html, "lxml").select(self.item_selector) → per block:
        #   a = block.select_one(self.link_selector); href/title
        #   sapo = block.select_one(self.sapo_selector)
        #   dict(link=..., title=..., sapo=..., _cat_name=cat["name"],
        #        _listing_url=listing_url)
        # mọi lỗi → self.errors.append, trả [] — KHÔNG raise
        ...

    def parse_item(self, raw: dict) -> Article | None:
        url, title = raw.get("link", ""), (raw.get("title") or "").strip()
        if not url or not title:
            return None
        summary = (raw.get("sapo") or "").strip()
        return Article(
            url=urljoin(self.base_url, url),
            title=title,
            source_domain=SOURCE_DOMAIN,
            summary=summary,
            published_at="",                       # detail-only — điền ở enrich()
            symbols=tag_tickers(f"{title} {summary}", self.watchlist),
            categories=[raw["_cat_name"]],
            metadata={"language": self.language, "listing_url": raw["_listing_url"]},
        )

    def enrich(self, article: Article) -> None:
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, SOURCE_DOMAIN,
                                         f"{self.base_url}/", self.content_selector)
        if html is None:
            return                                 # mixin đã set summary + errors
        self._details_fetched += 1
        article.published_at = _parse_detail_date(html, self.date_scope)
        if not article.published_at:
            article.metadata["capture"].setdefault("missing", []).append("published_at")
        article.content_text = extract_text(article.content_html) or article.summary
```

### Step 3 — `config/domains/baodautu.yaml` (full rewrite)
```yaml
name: baodautu
enabled: true            # RE-ENABLED 2026-09-07 — chuyển RSS → HTML listing
method: baodautu         # dedicated scraper: HTML listing + full raw HTML capture (was: rss)
rate_limit: 3.0
timeout: 30
language: vi
base_url: "https://baodautu.vn"
listing:
  # URL: trang 1 = "{base}/{slug}-d{id}/"  (CÓ / cuối)
  #      trang N = "{base}/{slug}-d{id}/p{N}"  (⚠ KHÔNG có / cuối → 404)
  categories:
    - {slug: "toan-canh-dau-tu",    id: 2,  name: "Toàn cảnh đầu tư"}      # đầu tư công/giải ngân/FDI/hạ tầng ★
    - {slug: "thoi-su-dau-tu",      id: 1,  name: "Thời sự Đầu tư"}        # chính sách vĩ mô ★
    - {slug: "dau-tu-tai-chinh",    id: 6,  name: "Đầu tư tài chính"}      # chứng khoán/tài chính ★
    - {slug: "kinh-doanh",          id: 3,  name: "Kinh doanh"}            # doanh nghiệp ★
    - {slug: "ngan-hang--bao-hiem", id: 5,  name: "Ngân hàng & Bảo hiểm"}  # ⚠ hai dấu gạch
    - {slug: "dau-tu-va-phap-luat", id: 41, name: "Đầu tư và Pháp luật"}
    # TRÁNH: d80 "Quảng bá" (PR). Chưa dùng: d54 d4 d77 d52 d10 d8 d53 d55 d27 d9 d78 d76 d36.
  pages_per_cycle: 1        # ~31 link/trang × 6 chuyên mục, nhịp 15' — thừa cho ~50 bài/ngày
  item_selector: "div.thumbblock"
  link_selector: "a.title_thumb_square"
  sapo_selector: "div.sapo_thumb_news"
detail:
  extract_full: true
  content_selector: "#content_detail_news"   # ⚠ TUYỆT ĐỐI không dùng .content (template JS)
  title_selector: "div.title-detail"         # đối chiếu; trang KHÔNG có <h1>
  date_scope_selector: "main.main_content"   # thu hẹp vùng tìm `dd/MM/yyyy HH:mm`
  max_details_per_cycle: 30
capture:
  raw_dir: "data/raw_html"
  min_body_bytes: 2048
compliance:
  respect_robots: true      # robots: Allow: / , không Disallow, không Crawl-delay
  proxy_rotation: false
  proxies: []
pitfalls: "RSS VĨNH VIỄN HỎNG (verified 2026-09-07): mọi feed trả CÙNG channel rỗng 'Trang chủ' + <link> lỗi 'https://baodautu.vn//.rss' → generator server hỏng, KHÔNG phải dormant; rssMain.html trả HTML homepage. Pagination `…-d<N>/p<page>` — THÊM / cuối là 404. Listing KHÔNG có ngày đăng → published_at chỉ có ở detail. Detail: KHÔNG có <h1>, KHÔNG có <time>/article:published_time/JSON-LD; ngày là text thuần dd/MM/yyyy HH:mm. Body = #content_detail_news; selector .content sẽ dính chuỗi template JS của widget bình luận. Paragraph mã hoá HTML entity (&ecirc;). Sitemap sitemaps/news-YYYY-M.xml (~348 url/tuần, ~50 bài/ngày) chỉ là backstop — không có category, lastmod chỉ có ngày."
```

### Step 4 — Register in `src/scrapers/__init__.py`

### Step 5 — Fixtures + `tests/test_baodautu.py`
`FakeHTTP` needs the listing via `get()` and the detail via `get_response()`. `FakeHTTP.get()`
currently returns `detail_html` for any non-robots URL — for this scraper the listing also goes
through `get()`. **Either** extend `tests/_fakes.py` with a `listing_html` attribute returned when
the URL contains `-d`, **or** subclass `FakeHTTP` locally in the test. Prefer extending `_fakes.py`
(DRY, and phase-05 or future HTML sources will want it) — it is additive and breaks no caller.

Cases:
- `test_registered` — `REGISTRY["baodautu"] is BaodautuScraper`
- `test_page_url_trailing_slash` — `_page_url(...,1)` ends with `/`; `_page_url(...,2)` ends with `p2` and **not** `/`
- `test_listing_parsed` — fixture yields ≥ 25 items with non-empty link+title
- `test_capture_happy_path` — `capture_status == "ok"`; `source_domain == "baodautu.vn"`;
  byte-exact `Path(cap["html_path"]).read_text(encoding="utf-8") == detail_html`
- `test_content_selector_avoids_js_template` — `content_html` contains real article text and
  **not** the literal `'+content+'` (this is the trap regression test)
- `test_date_parsed_from_detail` — `published_at == "2026-09-07T10:38:00+07:00"` and ends with `+07:00`
- `test_missing_date_recorded_not_faked` — detail fixture with the date stripped →
  `published_at == ""` and `"published_at" in cap["missing"]`; **no fabricated timestamp**
- `test_detail_failure_keeps_summary` — `detail_html=None`, `backoff=None` → `capture_status == "failed"`
- `test_listing_failure_isolated` — one category returns `None` → error appended, other categories still parse
- `test_max_details_cap` — cap 1 → `detail_calls == 1`, overflow flagged `detail_deferred`

### Step 6 — `domains/baodautu/{schema.yaml,README.md,changelog.md}`
`schema.yaml` is the drift baseline for a source with **no** upstream contract — record every
selector (`div.thumbblock`, `a.title_thumb_square`, `div.sapo_thumb_news`, `#content_detail_news`,
`div.title-detail`, `main.main_content`) and the two URL forms, with `last_verified: 2026-09-07`.

### Step 7 — Docs (see the Modify table). Create `docs/domains/html-scrapers.md`.

### Step 8 — Live smoke
```bash
cd project
python scripts/diagnose_sources.py baodautu
python -m src.orchestrator --once baodautu
python scripts/run_once.py baodautu
python scripts/verify_quality.py baodautu.vn
python scripts/report_drift.py
```

### Step 9 — Measure date-extraction success (gates sub-phase 04b)
```bash
python - <<'PY'
import json, pathlib
metas = list(pathlib.Path("data/raw_html/baodautu.vn").rglob("*.meta.json"))
miss = [m for m in metas if "published_at" in json.loads(m.read_text("utf-8")).get("missing", [])]
print(f"{len(metas)-len(miss)}/{len(metas)} dates parsed")
PY
```
**Gate:** ≥98% → ship as-is, 04b stays closed. <98% → open **sub-phase 04b (sitemap backstop)**:
fetch `sitemaps/news-{YYYY}-{M}.xml` once per day, `.strip()` each `<loc>`, and use `<lastmod>`
(date-only, `T00:00:00+07:00`) to fill gaps with `metadata["published_at_precision"] = "day"`.
Do **not** build 04b speculatively.

### Step 10 — Coverage cross-check (one-off, informational)
Compare one day of captured URLs against `sitemaps/news-2026-9.xml` `<loc>` entries. If the
listing route misses >5% of that day's articles, 04b also gains a discovery role. Record the number.

## Todo list

- [ ] 1. Re-verify pagination / listing selectors / detail date container live
- [ ] 2. Write `src/scrapers/baodautu.py` (+ `_parse_detail_date`)
- [ ] 3. Register in `src/scrapers/__init__.py`
- [ ] 4. Full rewrite of `config/domains/baodautu.yaml` (delete `rss:` + dead comment)
- [ ] 5. Extend `tests/_fakes.py` with `listing_html`; capture both fixtures
- [ ] 6. `tests/test_baodautu.py` (10 cases); `pytest -q` green
- [ ] 7. `domains/baodautu/{schema.yaml,README.md,changelog.md}`
- [ ] 8. Docs incl. **new** `docs/domains/html-scrapers.md`; remove baodautu from `vn-rss.md` + `skills/rss-sources.md`
- [ ] 9. Live smoke incl. `verify_quality.py baodautu.vn`
- [ ] 10. Date-parse rate measurement → 04b gate decision
- [ ] 11. Sitemap coverage cross-check; record miss rate

## Success criteria

| # | Check | Command / evidence |
|---|---|---|
| S1 | Tests green | `pytest -q` |
| S2 | Parse health | `python scripts/diagnose_sources.py baodautu` → 6 categories, ≥120 items, 0 errors |
| S3 | Cycle clean | `python -m src.orchestrator --once baodautu` → `new>0`, `errors=0` |
| S4 | **Bronze artifact** | `data/raw_html/baodautu.vn/<yyyymmdd>/<hash>.html`; `sha256sum` == `.meta.json` `content_sha256`; `capture_status: "ok"`; `http_status: 200` |
| S5 | Bronze WORM | second cycle leaves an already-captured `.html` byte-identical |
| S6 | **Silver derive** | `python scripts/run_once.py baodautu` → `data/silver/baodautu.vn/<yyyymmdd>/<hash>.json`, non-empty `cleaned_text`, `built_from_raw_path` → S4 |
| S7 | **Date extraction** | Step 9 script → **≥98%** parsed; every `published_at` ends `+07:00`; zero fabricated timestamps |
| S8 | Quality gate | `python scripts/verify_quality.py baodautu.vn` → ≥95% title+body+date |
| S9 | Trap regression | `test_content_selector_avoids_js_template` green; no Silver `cleaned_text` contains `'+content+'` |
| S10 | Selector health | `missing: ["main_content_node"]` in <2% of `.meta.json` |
| S11 | No drift | `python scripts/report_drift.py` → no new `SELECTOR_BROKEN`/`TEMPLATE_DRIFT` for baodautu |
| S12 | Dead comment closed | `grep -c "bật lại khi feed" config/domains/baodautu.yaml` → 0; `rss:` block gone |
| S13 | Docs consistent | baodautu no longer appears in `docs/domains/vn-rss.md` or `docs/skills/rss-sources.md` as an RSS source |

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **HTML template change breaks 6 selectors at once** — no upstream contract to lean on | **High** (this is the standing cost of HTML scraping) | **High** | All selectors in YAML (config edit, not code); `_parse_listing` returning 0 items appends an explicit "template drift?" error; `domains/baodautu/schema.yaml` is the diff baseline; `report_drift.py` in the daily runbook |
| Date regex matches a date *inside* the article body | Med | Med — wrong `published_at` | `date_scope_selector` narrows to `main.main_content`; take the FIRST match; Step 1 must confirm the actual container; S7 measures |
| Naive `.content` selector reintroduced by a later edit | Med | **High** — silently captures a JS template string | Dedicated regression test S9 + the trap is documented in the module docstring, the YAML `pitfalls`, and `schema.yaml` |
| Trailing slash added to `p<N>` "for consistency" → every page 404 | Med | High | `test_page_url_trailing_slash` + comments at the URL builder and in the YAML |
| Listing order is not actually newest-first (assumed, unverified) | Med | Med — freshness skew | Dedup makes ordering non-fatal (nothing is lost, only delayed); Step 10 cross-check quantifies; 04b fixes properly if needed |
| Missing dates fail the `verify_quality` gate | Med | Med | S7 gate at 98%; if unmet, 04b provides day-precision fallback with an explicit precision flag — never a silent fake |
| 6 listing fetches + 30 details ≈ 108 s/cycle | Low | Low | Inside the 15-min interval |
| Category ids `d<N>` change on a site restructure | Low | High | Ids live in YAML; `diagnose_sources.py` fails loudly with a 404 per category |

## Security considerations

- robots.txt is fully permissive (`Allow: /`, no `Disallow`, no `Crawl-delay`) — **verified**.
  Keep `respect_robots: true` regardless: permissive today is not permissive forever, and
  `RobotsGate` re-reads with a 24 h cache.
- Keep `rate_limit: 3.0` even though no `Crawl-delay` is declared. Permissive robots is not an
  invitation to hammer; `SourceBackoff` still guards 429/503.
- HTML listing scraping is more visible to the origin than RSS. Browser UA + `Referer` are set for
  compatibility; **do not** enable `proxy_rotation` — that crosses from compatibility into evasion
  and needs a maintainer decision.
- `RawStore._filter_headers` whitelist keeps `Set-Cookie` out of `.meta.json`.
- Parsed HTML is untrusted third-party markup: it reaches BeautifulSoup and `extract_text()` only —
  never `eval`, never a template renderer, never a shell.
- Bronze `.html` is copyrighted third-party content held as local WORM for internal analysis; not
  redistributed.

## Next steps

→ [phase-05-nso-gated-deferred.md](phase-05-nso-gated-deferred.md).
Conditional: **sub-phase 04b (sitemap backstop)** — opens only if S7 < 98% or Step 10 shows >5% miss.

## Unresolved questions

1. **Where exactly does the `dd/MM/yyyy HH:mm` string live in the DOM?** researcher-03 verified the
   format and that it is detail-only, but not its container. `date_scope_selector: "main.main_content"`
   is a defensible default; Step 1 must confirm and tighten it. **Blocking for S7.**
2. **Is the listing genuinely newest-first?** (researcher-03 §Unresolved #2, partly open.) Assumed,
   not verified. Affects freshness only, not completeness.
3. **Sitemap backstop — build it or not?** Deferred behind the Step 9/10 gates. Do not build 04b
   speculatively (YAGNI).
4. **Should `pages_per_cycle` be 2?** ~50 articles/day vs 6 × 31 links/cycle at 15-min cadence says
   no. Revisit only if the Step 10 cross-check shows misses.
5. **Category set** — 6 chosen. d36 "Thông tin doanh nghiệp" and d77 "Kinh tế số" are plausible
   additions; d80 "Quảng bá" is PR and permanently excluded. Owner call after a week.
6. **`docs/domains/html-scrapers.md`** — new doc file; confirm the naming/location fits the
   maintainer's docs taxonomy before creating it.
