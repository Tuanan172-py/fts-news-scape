# Verification Report — Live Endpoint Checks (2026-07-24)

Pre-implementation verification per user decisions on plan unresolved questions.

## Decisions Recorded

| # | Question | Decision |
|---|----------|----------|
| 1 | FireAnt bearer token | **Manual update accepted** Phase 1. Token in `config/secrets.yaml` (gitignored). 401 → self-disable + ERROR log |
| 2 | 4th RSS source | **VnEconomy approved** (NDH dropped, dormant) |
| 3 | Vietstock endpoints | **Verified — internal API NOT reachable via HTTP client** → switch to RSS (pre-approved fallback) |
| 4 | Dev rules | Follow global `~/.claude/workflows/development-rules.md` |

## Live Verification Results

### Vietstock — internal API DEAD END, RSS CONFIRMED
- Probed `/data/`, `/News/`, `/StartPage/`, `/Article/`, `/Home/`, `/TinTucSuKien/` + `TopPageArticle|NewsMoinhat` with browser UA, Referer, XHR header, cookies, `__RequestVerificationToken` → all soft-404 (homepage HTML ~320KB). Endpoint paths hidden in JS bundles not exposed in static HTML. Thamkhao research (Feb 2026, 38 endpoints) lacks full URLs; `results/` files absent from repo.
- **RSS verified working:** `https://vietstock.vn/rss` index → 60 feeds, valid RSS 2.0, `pubDate` with `+0700`, description has summary + img tag.
- Key feeds: `/0/tin-moi.rss`, `/144/chung-khoan.rss` (redirect note: 830 = co-phieu), `/733/doanh-nghiep.rss`, `/737/doanh-nghiep/hoat-dong-kinh-doanh.rss`, `/738/doanh-nghiep/co-tuc.rss`, `/764/doanh-nghiep/tang-von-m-a.rss`, `/761/kinh-te/vi-mo.rss`, `/5307/kinh-te.rss`, `/736/the-gioi.rss`, `/579/nhan-dinh-phan-tich.rss`, `/785/chung-khoan/thi-truong-trai-phieu.rss`
- **DECISION: Vietstock method = RSS** (moves to Phase 5 generic RSS collector; Phase 3 scope reduces to TNCK + FireAnt)

### CafeF — API CONFIRMED, param corrected
- `GET https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx?symbol=hpg&Newstype=0&PageIndex=1&PageSize=3&Type=1` → HTTP 200 JSON `{"Data":[{Symbol,Title,SubTitle,NewsType,...}]}`
- **`Type=1` REQUIRED** — `Type=2` returns `{"Success":false,"Message":"loại tin khoán trống"}` (resolves plan Q4)
- Headers needed: UA + `Referer: https://cafef.vn/`

### TNCK — API CONFIRMED, 2 caveats
- `GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-4-1.html` → HTTP 200, **gzip-compressed** (requests handles automatically; curl needs `--compressed`)
- Response: `data.contents[]` with `content_id, title, sub_title, description, date (epoch sec), update_time, avatar_url, ...` — field is **`date`** not `date_unix` as thamkhao docs said
- ⚠️ **`phrase=HPG` filter appears IGNORED** (returned PLX article first) — validate phrase behavior during implementation; fallback = no-phrase zone pass + client-side ticker tagging

### VnEconomy — RSS CONFIRMED (new 4th RSS source)
- Index `https://vneconomy.vn/rss.html` → feeds: `tin-moi.rss, chung-khoan.rss, tai-chinh.rss, thi-truong.rss, dau-tu.rss, kinh-te-the-gioi.rss, dia-oc.rss, ...`
- Feed format: RSS 2.0 + `content:encoded` namespace (richer than plain description)

### FireAnt — auth requirement CONFIRMED
- `GET https://restv2.fireant.vn/posts?symbol=HPG&type=1&offset=0&limit=5` without token → HTTP 401 `{"message":"Authorization has been denied for this request."}`
- Endpoint alive; bearer token flow as documented in thamkhao

## Impact on Plan
- Phase 3: drop VietstockScraper (API) → scope = TnckScraper + FireAntScraper only. CafeF config must use `Type=1`.
- Phase 5: add Vietstock feeds (start: tin-moi, chung-khoan, doanh-nghiep, vi-mo) + VnEconomy feeds → RSS domains: vietstock, vnexpress, baodautu, vneconomy.
- Domain count unchanged ≥5: cafef(API) + tnck(API) + fireant(API) + vietstock(RSS) + vnexpress(RSS) + baodautu(RSS) + vneconomy(RSS) = 7.

## Unresolved
- TNCK `phrase` param behavior (filter vs ignore) — test with fixtures during Phase 3.
- FireAnt list-response field names — need real token to capture fixture; use thamkhao `FIREANT_OUTPUT_JSON.md` until then.
