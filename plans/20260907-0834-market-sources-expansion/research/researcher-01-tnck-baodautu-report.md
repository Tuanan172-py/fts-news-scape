# TNCK & Báo Đầu Tư — Source Research (bronze scraping)

Budget: 5 tool calls used (1 ToolSearch + 4 WebFetch). Deep selector/robots/volume work NOT done — see Unresolved.

## 1. TNCK (tinnhanhchungkhoan.vn)

### API confirmed (fetched `https://api.tinnhanhchungkhoan.vn/api/morenews-zone-4-1.html`)
Top-level: `data{contents[], load_more}`, `error_code`, `error_message`, `server_time`.

Each item in `contents[]`:
| field | example |
|---|---|
| `content_id` | 397143 |
| `title` | "DICERA Holdings (DC4) lên kế hoạch vay nợ..." |
| `sub_title` | "" |
| `description` | summary text |
| `date` | 1788764679 (unix sec, string per task brief — actual fetch returned as number; harness should tolerate either) |
| `update_time` | unix sec |
| `avatar_url` | full image URL |
| `url` | relative path e.g. `/dicera-holdings-dc4-...-post397143.html` |
| `zone` | object: `zone_id`, `parent_id`, `name`, `url` |
| `display_type`, `attributes` | ints, purpose unclear |
| `show_title`,`show_avatar`,`show_comment`,`show_ads` | bool flags |

This confirms repo's existing config field names are right, and **zone name/id is echoed per-article in `zone.name`/`zone.zone_id`** — useful for verifying zone assignment without a separate lookup table.

### Zone-ID map
Only zone **4 = confirmed** (task brief + API `zone` field, name = "Thông tin doanh nghiệp" family).
Other zone IDs **[UNVERIFIED]** — did not have budget to probe zone 1,2,3,5... against the API. Recommend: hit `morenews-zone-{n}-1.html` for n=1..~20 and read `contents[0].zone.name` to build the map cheaply (1 request/zone, small pages).

### Site nav categories (fetched homepage, non-API URLs — NOT zone IDs, these are slug routes)
| Vietnamese name | URL |
|---|---|
| Chứng khoán | tinnhanhchungkhoan.vn/chung-khoan/ |
| Vĩ mô | /vi-mo/ |
| Thông tin doanh nghiệp | /thong-tin-doanh-nghiep/ (maps to zone 4 per task brief) |
| Địa ốc | /dia-oc/ (bất động sản) |
| Quốc tế | /quoc-te/ |
| Tài chính - Ngân hàng | /tai-chinh-ngan-hang/ |
| Thương trường | /thuong-truong/ |
| Cuộc sống | /cuoc-song/ |
| Số hóa | /so-hoa/ |
| Pháp lý kinh doanh | /phap-ly-kinh-doanh/ (pháp luật/pháp lý) |

No "đầu tư" or "thời sự" top-level nav item seen — may be sub-categories or absent. **[UNVERIFIED]** beyond what's listed.

### RSS
`tinnhanhchungkhoan.vn/rss.html` returned empty/no content via WebFetch (page likely JS-rendered or fetch got blank shell) — **could not verify RSS feeds exist or their URLs.** No `rel=alternate` RSS links found on homepage either. **[UNVERIFIED]** whether TNCK has RSS at all; the JSON API path is the confirmed-working ingestion route.

### Article detail selectors, robots.txt, rate limits, volume
**[UNVERIFIED]** — not fetched, no budget remaining. Task brief's existing partial config (browser UA + Referer + Accept:application/json, gzip response) is corroborated only insofar as the API call above succeeded via WebFetch (which doesn't reveal raw headers/encoding, so gzip/UA requirement not independently re-verified this session, just trusted from brief).

## 2. baodautu.vn

### Structure: RSS/HTML, no JSON API found
Homepage fetch found **no evidence of a JSON API** (server-rendered HTML). One RSS link in footer: `https://baodautu.vn/rssMain.html` — **not yet fetched to confirm it's a valid feed / list per-category feeds** [UNVERIFIED — need follow-up fetch].

### Category URL paths (fetched homepage nav)
| Vietnamese name | Path | Likely maps to requested category |
|---|---|---|
| Thời sự Đầu tư | /thoi-su-dau-tu-d1/ | thời sự |
| Toàn cảnh đầu tư | /toan-canh-dau-tu-d2/ | đầu tư công / giải ngân (candidate) |
| Kinh doanh | /kinh-doanh-d3/ | doanh nghiệp (candidate) |
| Đầu tư tài chính | /dau-tu-tai-chinh-d6/ | tài chính - chứng khoán (candidate) |
| Thị trường địa ốc | /thi-truong-dia-oc-d7/ | bất động sản |
| Kinh tế số | /kinh-te-so-d77/ | — |
| Đầu tư và Pháp luật | /dau-tu-va-phap-luat-d41/ | pháp lý |
| Tiêu dùng | /tieu-dung-d8/ | — |
| Phát triển bền vững | /phat-trien-ben-vung-d52/ | — |
| Khoa học và Công nghệ | /khoa-hoc-va-cong-nghe-d10/ | — |

Note: paths follow `slug-d{N}` pattern (N = category id, analogous to TNCK's `zone_id` but embedded in the URL rather than a separate API param). No explicit "FDI" or "hạ tầng - quy hoạch" top-level nav item seen — likely sub-categories under Toàn cảnh đầu tư / Kinh doanh. **[UNVERIFIED]**, need to browse into d2/d3 subnav to confirm.

### Article detail selectors, robots.txt, rate limits, Cloudflare/JS, volume
**[UNVERIFIED]** — not fetched, no budget remaining.

## Citations (fetched this session)
- https://api.tinnhanhchungkhoan.vn/api/morenews-zone-4-1.html
- https://tinnhanhchungkhoan.vn/rss.html (empty result, inconclusive)
- https://tinnhanhchungkhoan.vn/ (homepage)
- https://baodautu.vn/ (homepage)

## Unresolved questions
1. TNCK zone IDs for chứng khoán / bất động sản / tài chính-ngân hàng / đầu tư / pháp lý / thời sự — need to probe API zones 1-20+ directly (cheap: 1 tiny request each, read `zone.name`).
2. Does TNCK have working RSS at all? `/rss.html` returned blank via WebFetch — retry with raw curl/browser UA, or check `<link rel=alternate type=application/rss+xml>` in raw HTML source (WebFetch may have stripped it).
3. `baodautu.vn/rssMain.html` — not fetched; confirm it's a valid RSS/OPML index and extract per-category feed URLs.
4. baodautu.vn FDI and hạ tầng-quy hoạch category paths — likely nested under d2 (Toàn cảnh đầu tư) or d3 (Kinh doanh), unconfirmed.
5. Article detail CSS selectors (title/datetime/author/body/breadcrumb/tags) for both sites — not investigated at all this session.
6. robots.txt rules, rate limits, Cloudflare/JS-render requirement, gzip quirks, pagination stability — not investigated for either site.
7. Volume/day estimates per site/category — not investigated.
8. TNCK `date` field: task brief says "epoch seconds string" but this fetch's tool-summarized JSON showed it as a number (1788764679) — need raw byte-level check (WebFetch normalizes types; actual API may return it as string).
