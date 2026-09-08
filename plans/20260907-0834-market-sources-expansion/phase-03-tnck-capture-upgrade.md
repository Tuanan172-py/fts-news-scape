# Phase 03 — TNCK: Bronze capture upgrade + zone expansion

## Context links

- Parent plan: [plan.md](plan.md)
- Depends on: nothing (independent of phases 01/02; may run in parallel with phase-04)
- Research: [researcher-03 §1](research/researcher-03-live-verification-report.md) (full zone map, robots, detail selectors — all curl-verified) · [researcher-01 §1](research/researcher-01-tnck-baodautu-report.md) (API JSON field list) · [scout-01](scout/scout-01-touchpoints-report.md)
- Repo docs: `project/docs/design/06-raw-html-capture.md` · `project/docs/domains/api-scrapers.md` · `project/docs/dev/03-adding-a-source.md`

## Overview

| | |
|---|---|
| Date | 2026-09-07 |
| Description | `src/scrapers/tnck.py` works but does **not** use `CaptureMixin` → it writes zero Bronze artifacts today. Upgrade it to the canonical `vneconomy.py` capture pattern, expand from 1 zone to 9 (corporate-investigation / shareholder-dispute / securities-law beats), lock the `source_domain` normalization decision, and fix the `.vn`-suffix host-resolution hack that would otherwise make TNCK invisible to the monitoring tooling. |
| Priority | **P0** — one of the two headline asks |
| Implementation status | 🔲 Not started |
| Review status | 🔲 Not reviewed |

## Key insights

- **TNCK has no RSS.** `/rss.html` → 200 / **13 bytes**; `/rss/trang-chu.rss`, `/chung-khoan.rss`,
  `/rss/chung-khoan.rss` → **302, 0 bytes**. The JSON zone API is the only route. Do not re-probe.
- **Existing scraper is Bronze-blind.** `TnckScraper.enrich()` calls `self.http.get()` then
  `extract_content()` — no `RawStore`, no robots gate, no backoff, no `.meta.json`. It also never
  sets `metadata["language"]`. All three are plan-level non-negotiables.
- **Full zone map is known** (researcher-03 §1.2, 40 items/page). Recommended set was
  `[1, 4, 8, 11, 21, 26, 29, 33, 39, 6]`, with the explicit caveat that **zone 8 "Điều tra" skews
  to general crime/consumer**, not corporate. → Ship 9 zones **without 8**; gate 8 (and 13/36/43)
  behind a measured week. This resolves researcher-03 open question #3 by evidence, not opinion.
- **`Disallow: /api/` is on `www.tinnhanhchungkhoan.vn` only.** `api.tinnhanhchungkhoan.vn` is a
  separate host with its own robots.txt (200, empty). Article details `/<slug>-post<NNN>.html`
  are allowed. `RobotsGate` passes. No `Crawl-delay` → repo default 3.0 s stands.
- **Detail selectors verified:** body `div.article__body.cms-body` → selector `div.article__body`;
  sapo `div.article__sapo.cms-desc`; `<meta property="article:published_time" content="…+0700">`
  and `<time class="time" datetime="…+0700" data-time="…">`. Server-rendered, no JS.
  Ads sit in `div[id^=adsWeb_]` **inside** the body — strip downstream (Silver), never in Bronze.
- **`date` is a JSON number, not a string** (repo docs and the YAML `pitfalls` say "string" —
  wrong). `int()` tolerates both; fix the docs.
- **`source_domain` decision — DECIDED: non-www `tinnhanhchungkhoan.vn`.** Rationale:
  (a) it matches the repo-wide convention `urlparse(url).netloc.removeprefix("www.")` used by
  `rss_generic`/`vneconomy`/`silver_builder._domain_of`; (b) it is what today's `tnck.py`
  hardcodes; (c) **there is no dedup continuity risk** — live DB check on 2026-09-07 shows
  `articles.source_domain` ∈ {cafef.vn, vietstock.vn, vneconomy.vn} and `seen_articles.source_domain`
  ∈ {cafef, vietstock, vneconomy}: **zero pre-existing TNCK rows**. Article `url` keeps the `www.`
  host the API returns (do not rewrite URLs — that would change `url_title_hash` identity).
  Consequence: Bronze partition `data/raw_html/tinnhanhchungkhoan.vn/`, and
  `scripts/verify_quality.py tinnhanhchungkhoan.vn`.
- **`.vn`-suffix hack bites here.** `scripts/domain_check.py:152` and
  `src/monitor/domain_reporter.py:126,170` do `f"{dom}.vn" if "." not in dom else dom` → config
  name `tnck` resolves to `tnck.vn`, which matches nothing. TNCK is the first source in this plan
  where name ≠ host stem, so this phase fixes it.

## Requirements

**Functional**
1. Every fetched TNCK detail page produces a byte-exact Bronze artifact + `.meta.json`.
2. Zones expand 1 → 9; per-item `zone.name` continues to populate `Article.categories`.
3. `metadata["language"] = "vi"`; `published_at` ISO `+07:00` (already correct, keep).
4. `scripts/domain_check.py report tnck` and `src/monitor/domain_reporter` resolve the real host.

**Non-functional**
- DRY: reuse `CaptureMixin` verbatim; reuse `src.core.models.VN_TZ` instead of a second
  `ZoneInfo("Asia/Ho_Chi_Minh")` constant in the module.
- KISS: `pages_per_cycle: 1` (40 items/zone) — at a 15-min cadence, page 2 is ~100% duplicates and
  costs 9 extra requests/cycle for nothing.
- Backward compatible: host-resolution fix keeps the legacy `<name>.vn` fallback so no existing
  caller breaks.
- Bronze non-negotiables per [plan.md](plan.md#global-non-negotiables-every-phase).

## Architecture

```
config/domains/tnck.yaml (method: tnck)
   → REGISTRY["tnck"]  (per-name wins over per-method in build_scraper)
TnckScraper(CaptureMixin, BaseScraper)          # ← CaptureMixin is NEW
   fetch_list()  : 9 zones × 1 page → api.tinnhanhchungkhoan.vn/api/morenews-zone-{z}-{p}.html
                   http.get_json(referer=www..., headers={Referer, Accept})
   parse_item()  : urljoin(www BASE, item.url); source_domain="tinnhanhchungkhoan.vn"
                   published_at = fromtimestamp(int(date), VN_TZ).isoformat()  → +07:00
                   categories=[zone.name]; metadata={language, content_id, avatar_url, zone_id}
   enrich()      : _capture_and_extract(article, "tinnhanhchungkhoan.vn",
                                        "https://www.tinnhanhchungkhoan.vn/",
                                        "div.article__body")
                   ★ RawStore.save FIRST → data/raw_html/tinnhanhchungkhoan.vn/<yyyymmdd>/
```

**Host resolution fix (new, small, DRY):** add one helper in `src/core/config.py`

```python
def resolve_source_domain(name: str) -> str:
    """Config name → source_domain host.

    Ưu tiên `domain:` trong domains/<name>/schema.yaml (contract thật);
    fallback legacy `<name>.vn` (giữ tương thích ngược cho caller cũ).
    Sửa bẫy: name 'tnck' ≠ host 'tinnhanhchungkhoan.vn'.
    """
```
…then call it from `scripts/domain_check.py:152` and `src/monitor/domain_reporter.py:126,170`,
replacing the inline `f"{dom}.vn" if "." not in dom else dom` expression in all three places.
This is why `domains/<name>/schema.yaml` is treated as mandatory throughout this plan.

## Related code files

**Modify**
| Path | Change |
|---|---|
| `project/src/scrapers/tnck.py` | `class TnckScraper(CaptureMixin, BaseScraper)`; `self._init_capture()`; rewrite `enrich()`; add `language`/`content_selector`/`zone_id` handling; use `src.core.models.VN_TZ` |
| `project/config/domains/tnck.yaml` | `enabled: true`, `method: tnck`, 9 zones, `pages_per_cycle: 1`, `detail.content_selector`, `capture` + `compliance` + `language` blocks, corrected `pitfalls` |
| `project/src/core/config.py` | add `resolve_source_domain(name)` |
| `project/scripts/domain_check.py` | line ~152 → `resolve_source_domain(dom)` |
| `project/src/monitor/domain_reporter.py` | lines ~126, ~170 → `resolve_source_domain(...)` |
| `project/tests/test_tnck.py` | rewrite for capture (create if absent) |
| `project/docs/domains/api-scrapers.md` | tnck section: zones 1→9, capture flow, `date` is a **number**, `Disallow: /api/` scoping, `pages_per_cycle: 1` |
| `project/docs/domains/README.md` | tnck row: Method → `REST + capture`, Enabled ✅, quirk text |
| `project/docs/design/03-source-strategy.md` | §2 Nhóm B: tnck now zone × 1 page + Bronze capture |
| `project/README.md` | API source description line (`:115`) |

**Create**
| Path | Note |
|---|---|
| `project/tests/fixtures/tnck_zone_list.json` | real `morenews-zone-1-1.html` response, trimmed to 2–3 `contents[]` |
| `project/tests/fixtures/tnck_detail_page.html` | real article page (verified ~106 KB; trim only if the test stays byte-exact against the trimmed file) |
| `project/domains/tnck/schema.yaml` | **`domain: tinnhanhchungkhoan.vn`** — this is what makes the host fix work |
| `project/domains/tnck/README.md`, `changelog.md` | monitor-doc convention |

**No change:** `src/scrapers/__init__.py` (`tnck` already imported), `src/orchestrator.py`,
`src/pipeline/*`, `src/crawler/*`.

## Implementation steps

### Step 1 — Rewrite `src/scrapers/tnck.py`
Docstring update (correct the "string" claim; record no-RSS + robots scoping). Key deltas only:

```python
from src.core.models import VN_TZ, Article        # DRY: bỏ ZoneInfo cục bộ
from src.scrapers.capture_mixin import CaptureMixin

@register("tnck")
class TnckScraper(CaptureMixin, BaseScraper):
    BASE_URL = "https://www.tinnhanhchungkhoan.vn"
    SOURCE_DOMAIN = "tinnhanhchungkhoan.vn"       # non-www — QUYẾT ĐỊNH, xem Key insights
    API_TEMPLATE = "https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html"

    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        api = config.get("api", {})
        self.template = api.get("url_template", self.API_TEMPLATE)
        self.zones = api.get("zones", [4])
        self.pages_per_cycle = api.get("pages_per_cycle", 1)
        self.headers = api.get("headers", {"Referer": f"{self.BASE_URL}/"})
        detail = config.get("detail", {})
        self.content_selector = detail.get("content_selector", "div.article__body")
        self.max_details = detail.get("max_details_per_cycle", 40)
        self.watchlist = config.get("watchlist") or load_watchlist()
        self.language = config.get("language", "vi")
        self._details_fetched = 0
        self._init_capture()                       # RawStore + RobotsGate + SourceBackoff

    # fetch_list() — KHÔNG đổi (zone × page loop, lỗi → self.errors, không raise)

    def parse_item(self, raw: dict) -> Article | None:
        ...
        zone = raw.get("zone") or {}
        return Article(
            url=urljoin(self.BASE_URL, rel_url),           # giữ host www của API
            title=title,
            source_domain=self.SOURCE_DOMAIN,              # non-www
            summary=summary,
            published_at=published,                        # epoch → VN_TZ → +07:00
            symbols=tag_tickers(f"{title} {summary}", self.watchlist),
            categories=[zone.get("name")] if zone.get("name") else [],
            metadata={"content_id": raw.get("content_id", ""),
                      "avatar_url": raw.get("avatar_url", ""),
                      "zone_id": zone.get("zone_id", ""),
                      "language": self.language},          # BẮT BUỘC (thiếu ở bản cũ)
        )

    def enrich(self, article: Article) -> None:
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary
            article.metadata["detail_deferred"] = True
            return
        html = self._capture_and_extract(article, self.SOURCE_DOMAIN,
                                         f"{self.BASE_URL}/", self.content_selector)
        if html is None:
            return          # mixin đã set content_text=summary + ghi self.errors
        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
```
`date` parse: keep `int(raw_date)` inside the existing `try/except (ValueError, OSError)`; it
already tolerates both `int` and `str`. Add `TypeError` to the except tuple for null safety.

### Step 2 — `config/domains/tnck.yaml`
```yaml
name: tnck
enabled: true            # RE-ENABLED 2026-09-07 (was: focus cafef+vietstock 2026-08-03)
method: tnck             # dedicated scraper: zone API list + full raw HTML capture (was: api)
rate_limit: 3.0
timeout: 30
language: vi
api:
  url_template: "https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html"
  # Zone map verified 2026-09-07 (researcher-03 §1.2). Bộ 9 zone cho beat:
  # điều tra doanh nghiệp / tranh chấp cổ đông / pháp lý chứng khoán.
  zones: [1, 4, 6, 11, 21, 26, 29, 33, 39]
  #        │  │  │  │   │   │   │   │   └─ 39 Vĩ mô
  #        │  │  │  │   │   │   │   └───── 33 Pháp đình
  #        │  │  │  │   │   │   └───────── 29 Đại hội cổ đông
  #        │  │  │  │   │   └───────────── 26 Mua bán - Sáp nhập (M&A)
  #        │  │  │  │   └───────────────── 21 Pháp luật
  #        │  │  │  └───────────────────── 11 Trái phiếu
  #        │  │  └──────────────────────── 6  Tiền tệ
  #        │  └─────────────────────────── 4  Thông tin doanh nghiệp
  #        └────────────────────────────── 1  Chứng khoán
  # HOÃN (đo 1 tuần rồi quyết): 8 Điều tra (lệch tin hình sự/tiêu dùng),
  #                             13 Nhận định, 36 Đầu tư, 43 Thương trường.
  # TRÁNH: 27/45 "DN tự giới thiệu" (PR).
  pages_per_cycle: 1      # 40 items/page — đủ cho nhịp 15'; page 2 ~100% trùng
  headers:
    Referer: "https://www.tinnhanhchungkhoan.vn/"
detail:
  extract_full: true
  content_selector: "div.article__body"    # div.article__body.cms-body (verified 2026-09-07)
  max_details_per_cycle: 40
capture:
  raw_dir: "data/raw_html"
  min_body_bytes: 2048
compliance:
  respect_robots: true
  proxy_rotation: false
  proxies: []
pitfalls: "KHÔNG CÓ RSS (/rss.html = 13 bytes; /rss/*.rss = 302) — API là route duy nhất, đừng probe lại. Response gzip. `date` = epoch giây, JSON NUMBER (không phải string — sửa 2026-09-07); `url` relative → urljoin host www. `phrase` param BỊ IGNORE — tag ticker client-side. robots www: Disallow /api/ nhưng api.tinnhanhchungkhoan.vn là HOST KHÁC (robots riêng, rỗng); bài /<slug>-post<NNN>.html được phép. source_domain chuẩn hoá NON-WWW = tinnhanhchungkhoan.vn (Bronze partition + verify_quality dùng host này). Quảng cáo nằm trong div[id^=adsWeb_] BÊN TRONG body — strip ở Silver, KHÔNG đụng Bronze. Verified live 2026-09-07."
```

### Step 3 — `resolve_source_domain()` + 3 call sites
Add to `src/core/config.py`; wire into `scripts/domain_check.py:152` and
`src/monitor/domain_reporter.py:126,170`. Keep the `<name>.vn` fallback.

### Step 4 — `domains/tnck/schema.yaml` (+ README, changelog)
Mirror `domains/cafef/schema.yaml`. `domain: tinnhanhchungkhoan.vn`, `method: api+capture`,
`endpoint:` the zone template, `last_verified: 2026-09-07`. `raw_response.fields` from
researcher-01's field table (`content_id`, `title`, `sub_title`, `description`, `date` **integer**,
`update_time`, `avatar_url`, `url`, `zone{zone_id,parent_id,name,url}`). `output_fields` health
thresholds: `url`/`title`/`source_domain` 1.0, `published_at` 0.98.

### Step 5 — `tests/test_tnck.py`
Fixtures: `tnck_zone_list.json` + `tnck_detail_page.html`. `FakeHTTP(list_json=…, detail_html=…)`.
Cases:
- `test_registered` — `REGISTRY["tnck"] is TnckScraper`
- `test_capture_happy_path` — `capture_status == "ok"`;
  `source_domain == "tinnhanhchungkhoan.vn"`; `article.url.startswith("https://www.tinnhanhchungkhoan.vn/")`;
  `published_at.endswith("+07:00")`; `metadata["language"] == "vi"`;
  byte-exact `Path(cap["html_path"]).read_text(encoding="utf-8") == detail_html`
- `test_epoch_number_and_string` — `date` as `1788494299` **and** `"1788494299"` → same `published_at`
- `test_zone_name_becomes_category` — `categories == [zone["name"]]`, `metadata["zone_id"]` set
- `test_content_selector_hits` — `missing` lacks `main_content_node` on the fixture
- `test_detail_failure_keeps_summary` — `detail_html=None`, `backoff=None` → `capture_status == "failed"`,
  `content_text == summary`, error contains `detail fetch failed`
- `test_bad_date_does_not_raise` — `date: "not-a-number"` → `published_at == ""`, no exception
- `test_max_details_cap` — cap 1 → `http.detail_calls == 1`
- `test_resolve_source_domain` — `resolve_source_domain("tnck") == "tinnhanhchungkhoan.vn"`;
  `resolve_source_domain("baodautu") == "baodautu.vn"` (fallback path still works)

### Step 6 — Live smoke
```bash
cd project
python scripts/diagnose_sources.py tnck
python -m src.orchestrator --once tnck
python scripts/run_once.py tnck
python scripts/verify_quality.py tinnhanhchungkhoan.vn      # note: HOST, not "tnck"
python scripts/domain_check.py report tnck                  # proves Step 3 fix
python scripts/report_drift.py
```

### Step 7 — Zone-8 decision data
After 7 days, count articles per `metadata["zone_id"]` and eyeball zone-21/26/29/33 signal.
Then decide on zones 8 / 13 / 36 / 43. Record the call in `domains/tnck/changelog.md`.

## Todo list

- [ ] 1. Rewrite `src/scrapers/tnck.py` onto `CaptureMixin`
- [ ] 2. Rewrite `config/domains/tnck.yaml` (9 zones, capture/compliance, corrected pitfalls)
- [ ] 3. `resolve_source_domain()` in `src/core/config.py` + 3 call sites
- [ ] 4. `domains/tnck/{schema.yaml,README.md,changelog.md}`
- [ ] 5. Fixtures: `tnck_zone_list.json`, `tnck_detail_page.html`
- [ ] 6. `tests/test_tnck.py` (9 cases); `pytest -q` green
- [ ] 7. Docs: `api-scrapers.md`, `domains/README.md`, `design/03-source-strategy.md`, root `README.md`
- [ ] 8. Live smoke incl. `verify_quality.py tinnhanhchungkhoan.vn` + `domain_check.py report tnck`
- [ ] 9. Bronze/Silver artifact evidence into `domains/tnck/changelog.md`
- [ ] 10. Schedule the 7-day zone-8/13/36/43 review

## Success criteria

| # | Check | Command / evidence |
|---|---|---|
| S1 | Tests green | `pytest -q` |
| S2 | Parse health | `python scripts/diagnose_sources.py tnck` → 9 zones fetched, 0 errors |
| S3 | Cycle clean | `python -m src.orchestrator --once tnck` → `new>0`, `errors=0` |
| S4 | **Bronze artifact** | `data/raw_html/tinnhanhchungkhoan.vn/<yyyymmdd>/<hash>.html` exists; `sha256sum` == `.meta.json` `content_sha256`; `capture_status: "ok"`; `http_status: 200`; `images[]` non-empty |
| S5 | Bronze WORM | second cycle leaves an already-captured `.html`'s bytes identical |
| S6 | Partition path | Bronze dir is `tinnhanhchungkhoan.vn/` — **not** `www.tinnhanhchungkhoan.vn/`, not `tnck/` |
| S7 | **Silver derive** | `python scripts/run_once.py tnck` → `data/silver/tinnhanhchungkhoan.vn/<yyyymmdd>/<hash>.json`, non-empty `cleaned_text`, `built_from_raw_path` → S4 |
| S8 | Quality gate | `python scripts/verify_quality.py tinnhanhchungkhoan.vn` → ≥95% |
| S9 | Host-resolution fix | `python scripts/domain_check.py report tnck` returns real field-health (non-zero article count), not "0 articles" |
| S10 | Zone coverage | distinct `metadata["zone_id"]` in one cycle == 9 |
| S11 | No drift | `python scripts/report_drift.py` → no new `SELECTOR_BROKEN` for tnck |
| S12 | No regression | phase-01/02 domains and cafef/vietstock/vneconomy unaffected: `pytest -q` + one full `run_once.py` |

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `resolve_source_domain` touches shared monitoring code used by cafef/vietstock | Med | **High** | Legacy `<name>.vn` fallback preserved; `test_resolve_source_domain` covers both branches; S12 regression run |
| 9 zones × 40 items = 360 list items/cycle, mostly duplicates → dedup churn | High | Low | `DedupCache` is designed for exactly this; `pages_per_cycle: 1` halves the cost; detail cap 40 bounds the expensive half |
| Zone 8 excluded → miss real corporate investigations | Med | Med | 21/33/26/29 carry the corporate-legal signal per researcher-03; Step 7 reviews with data in 7 days |
| `div.article__body` changes (site redesign) | Low | High | `min_body_bytes` + `_looks_complete` → `capture_status: partial`; `report_drift.py` surfaces it; `domains/tnck/schema.yaml` is the diff baseline |
| Ads inside `div.article__body` pollute `cleaned_text` | High | Med | Known & accepted at Bronze (WORM). Strip `div[id^=adsWeb_]` in Silver/extractor if noise proves material — separate change, not this phase |
| API host blocks a heavier crawl pattern | Low | High | `rate_limit: 3.0`, `SourceBackoff` 2→4→8→16 s on 429/503, browser UA + `Referer` already in config |
| `method: api` → `method: tnck` confuses readers | Low | Trivial | `REGISTRY["tnck"]` wins by name either way; comment in the YAML mirrors the vneconomy precedent |

## Security considerations

- `respect_robots: true`. Note carefully: `Disallow: /api/` applies to `www.tinnhanhchungkhoan.vn`,
  **not** to the separate host `api.tinnhanhchungkhoan.vn` (own robots.txt, empty). List calls
  are compliant; detail URLs `/<slug>-post<NNN>.html` are explicitly allowed. Re-verify robots.txt
  on both hosts at implementation time — this is the one place where a misread means a ToS breach.
- No auth, no token, nothing from `config/secrets.yaml`.
- `RawStore._filter_headers` whitelist keeps `Set-Cookie` out of `.meta.json`.
- `rate_limit: 3.0` + `SourceBackoff`; browser UA + `Referer` are for compatibility, not evasion —
  do not add proxy rotation (`proxy_rotation: false`) unless a maintainer signs off.
- TNCK is UBCKNN-affiliated; investigative content may name individuals. Bronze is WORM local
  storage for internal analysis; do not redistribute raw `.html` or republish article text.

## Next steps

→ [phase-04-baodautu-html-listing.md](phase-04-baodautu-html-listing.md) (independent; may run in parallel).
Also unblocks: any future non-`.vn`-stem source, thanks to `resolve_source_domain`.

## Unresolved questions

1. **Zone 8 "Điều tra"** (researcher-03 §Unresolved #3) — include or rely on 21/33/26/29?
   Deferred to a 7-day measured review (Step 7). Owner decision required at that point.
2. **Zones 14 and 16** (researcher-03 §Unresolved #7) — returned 40 items with no/odd `name`,
   unmapped. Probe `contents[0].zone` once during Step 1 and record; excluded from v1 either way.
3. **`resolve_source_domain` scope** (scout-01 §d) — is fixing the `.vn` hack in-scope for this
   work, or should it be a separate PR? This plan says in-scope and minimal, because TNCK is
   otherwise invisible to `domain_check`/`domain_reporter`. Confirm with maintainer.
4. **Ad stripping** — `div[id^=adsWeb_]` inside `div.article__body` will land in Silver
   `cleaned_text`. Is that acceptable, or does `src/processor/extractor.py` need a domain-aware
   strip list? (Would be the first domain-specific rule in a deliberately generic module —
   weigh against design-12 I1/I2.)
5. **`scripts/sample_articles.py` GROUPS + `scripts/validate_capture.py` sources list** (scout-01 §d) —
   required for PR acceptance, or dev-convenience? Treated as optional/cosmetic here.
