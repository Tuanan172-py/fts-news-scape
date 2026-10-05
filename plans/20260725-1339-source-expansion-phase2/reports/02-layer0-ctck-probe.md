# Layer-0 CTCK/Exchange Probe — Feasibility (GO/NO-GO)

Date: 2026-07-25. Method: curl only, browser UA `Chrome/126`, no cookies unless noted, <10 req/target.

## Summary

| # | Target | Verdict | Method |
|---|--------|---------|--------|
| 1 | HNX | **GO** | Native RSS (4 feeds) |
| 2 | HOSE/HSX | **GO** | Native RSS via api.hsx.vn |
| 3 | SSC | **NO-GO** | Oracle ADF JS cookie-loopback wall |
| 4 | SSI | **GO (list only)** | Server-rendered HTML list; PDF behind login |
| 5 | VNDirect | **GO (partial)** | Public JSON news API; research-report feed not found in timebox |
| 6 | BSC | **GO (full)** | Server-rendered list + free PDF download, no cookies |

---

## 1. HNX — GO

- `https://www.hnx.vn/vi-vn/rss.html` = static HTML, contains 4 RSS hrefs (root-relative):
  - `/1/vi_vn/thong-tin-cong-bo-tu-so.rss` (disclosure from exchange)
  - `/2/vi_vn/thong-tin-cong-bo-tu-thanh-vien.rss` (from members)
  - `/3/vi_vn/thong-tin-cong-bo-tu-to-chuc-phat-hanh.rss` (from issuers)
  - `/4/vi_vn/su-kien-dao-tao.rss` (events/training)
- Bare URL 302s; **must follow redirect** (final: `https://www.hnx.vn/vi-vn/1/vi_vn/thong-tin-cong-bo-tu-so.rss`). Returns `application/rss+xml`, ~26KB.
- Evidence title: "Thông báo ngày giao dịch đầu tiên và ngày giao dịch cuối cùng của hạn ngạch phát thải khí nhà kính phân bổ cho giai đoạn 2025 - 2026". Item links point to `hnx.vn:7978/tin-cung-cap-rss-...` (port 7978 in link — may need rewrite to standard host).
- News listing: `https://www.hnx.vn/vi-vn/tin-tuc-su-kien.html` errors (path case-sensitive, redirects to error page), but category pages e.g. `https://www.hnx.vn/vi-vn/tin-tuc-su-kien-hnx.html` return 200, ~99KB server-rendered, dates in HTML. Pagination via POST AJAX: `/ModuleArticles/ArticlesHNX/EventNextPage`, `/NextPageTinHDSuKien`, etc. Not needed — RSS suffices.

## 2. HOSE (hsx.vn) — GO

- New site is a React SPA ("You need to enable JavaScript"); old `/Modules/CMS/...` paths dead.
- But bundle (`/static/js/main.d430e296.js`) reveals API base `https://api.hsx.vn/n/api/v1` and an RSS directory endpoint:
  - **Feed directory**: `https://api.hsx.vn/n/api/v1/News/NewsFeed` → 200, `application/rss+xml`, lists category feeds:
    - `https://api.hsx.vn/n/api/v1/News/NewsByCateFeed/11` (Quản trị công ty — currently empty)
    - `.../NewsByCateFeed/21` (Tin Tổ chức niêm yết)
    - `.../NewsByCateFeed/22` (Tin CTY CKTV)
    - (directory feed truncated in probe; more IDs likely exist — enumerate)
- Evidence titles: cat21: "FUEDCMID: Kết thúc giao dịch hoán đổi ngày 23/07/2026"; cat22: "HBS: Quyết định về việc đình chỉ một phần hoạt động giao dịch...". Titles wrapped in HTML-escaped `<span data-object-type=...>` — strip tags on ingest.
- JSON list endpoint exists in bundle (`/news/newstype/{id}/{page}?pageIndex&pageSize&startDate&endDate`) but guessed URLs 404'd — RSS is the easy path.

## 3. SSC (ssc.gov.vn) — NO-GO

- `https://ssc.gov.vn/` → redirects to `/webcenter/portal/ubck` (Oracle WebCenter/ADF). Response is 6.7KB `AdfLoopbackUtils` JS bootstrap that sets cookies via JS then reloads. Second request with cookie jar returns identical loopback page — cookie is set client-side by JS, curl cannot pass.
- No article links in raw HTML at any stage. Reason: JS cookie-challenge + ADF stateful portal. Needs headless browser (chrome-devtools/puppeteer) if wanted later.

## 4. SSI (ssi.com.vn) — GO for list, login wall for PDFs

- `https://www.ssi.com.vn/khach-hang-ca-nhan/bao-cao-nganh` → 200, 128KB server-rendered. Report entries present in raw HTML as hrefs:
  - `https://www.ssi.com.vn/analysis-center/report/download/cap-nhat-nganh-ngan-hang-khep-lai-mot-nam-nhieu-dau-an` (slug = title)
- Evidence slug-title: "cap-nhat-nganh-dien-buoc-ngoat-chu-ky-5-nam" ("Cập nhật ngành điện: bước ngoặt chu kỳ 5 năm").
- PDF download without cookies: **302 → `https://www.ssi.com.vn/analysis-center/login?redirect_to=...`** — login required for the file itself. Also rate-limit header `X-RateLimit-Limit: 30`.
- Verdict: GO for monitoring new report titles+URLs (scrape list HTML); NO-GO for PDF content without account.

## 5. VNDirect — GO partial (JSON news API), research PDFs unresolved

- `https://dstock.vndirect.com.vn/trung-tam-phan-tich` → Next.js SPA, 6.5KB shell, no content in HTML. Bundles probed (main, _app) contain no API host strings (split into other chunks).
- `https://www.vndirect.com.vn/tin-tuc-nhan-dinh/` → **403 Cloudflare "Just a moment"** challenge.
- Working public API (no cookies, no key): `https://api-finfo.vndirect.com.vn/v4/news?size=2&sort=newsDate:desc` → 200 JSON. Evidence: `"newsTitle":"Gạo sạch Aan ba lần liên tiếp đạt chứng nhận..."`, fields: newsId, newsGroup, newsType, newsTitle, newsAbstract, newsContent (full HTML). Supports `q=` filter syntax (`q=newsGroup:company_news`).
- Tried `newsGroup:analyst_report` and `newsGroup:research_report` → empty. Research-report group name unknown; dstock research center likely uses a different (possibly authed) endpoint.

## 6. BSC (bsc.com.vn) — GO full

- `https://www.bsc.com.vn/bao-cao-phan-tich` = 404; correct URLs: `https://www.bsc.com.vn/trung-tam-bao-cao-phan-tich/` (hub) and category listings e.g. `https://www.bsc.com.vn/bao-cao-vi-mo-thi-truong/` (WordPress, server-rendered).
- Category page 200, ~203KB, report detail links in raw HTML: `https://www.bsc.com.vn/bao-cao/15682-bsc-brief-24-07-vn-index-can-thoi-gian-de-on-dinh-lai-nhip-giao-dich`.
- Detail page contains direct download anchor: `https://www.bsc.com.vn/Report/ReportFile/15682` → **200 OK without cookies**, `Content-Disposition: inline; filename="BSC-Brief-2407-VN-Index-...pdf"`.
- Evidence title: "BSC Brief | 24.07: VN-Index cần thời gian để ổn định lại nhịp giao dịch". Daily Brief + Morning reports both listed. Report ID is numeric+monotonic → trivial polling. wp-json types endpoint is 401 (locked) — use HTML listing.

---

## Unresolved questions

1. VNDirect: exact `newsGroup`/endpoint for analyst research reports on api-finfo (or whether dstock research center requires auth) — needs headless XHR capture on dstock.
2. HSX: full list of `NewsByCateFeed/{id}` category IDs (directory feed showed 11/21/22; probe truncated — enumerate ids or re-fetch full directory).
3. HNX: RSS item links carry `:7978` port — verify links resolve when port stripped/rewritten to `https://www.hnx.vn`.
4. SSI: whether a free/anon PDF path exists for some report types (only one download URL tested).
5. SSC: headless-browser feasibility not tested (out of scope for curl probe).
