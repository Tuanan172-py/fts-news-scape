# Báo Đầu Tư Domain Changelog

Ghi lại mọi thay đổi upstream của baodautu.vn ảnh hưởng đến scraper.

---

## 2026-09-07 — RSS (hỏng vĩnh viễn) → HTML listing scraper (phase-04)

Kế hoạch: `plans/20260907-0834-market-sources-expansion/phase-04-baodautu-html-listing.md`

### 🔴 RSS HỎNG Ở SERVER, KHÔNG PHẢI "DORMANT"

Comment cũ trong config ("bật lại khi feed có items") tồn tại 14 tháng và **không bao giờ
khả thi**. Re-verify 2026-09-07, 8/8 URL:

| URL | Kết quả |
|---|---|
| `/chung-khoan.rss`, `/dau-tu-tai-chinh.rss`, `/thoi-su-dau-tu.rss`, `/kinh-doanh.rss`, `/toan-canh-dau-tu.rss`, `/rss/home.rss`, `/rss/thoi-su-dau-tu.rss` | 200, ~1.2 KB, **0 `<item>`** |
| `rssMain.html` | trả **HTML homepage 34 KB**, không phải feed |

Nguyên nhân gốc: **mọi** feed trả **cùng một channel rỗng**:

```xml
<title>Trang chủ</title>
<link>https://baodautu.vn//.rss</link>   <!-- double-slash, KHÔNG có category -->
```

→ generator RSS phía server hỏng. Đã xoá hẳn block `rss:` và comment chờ-bật-lại.
**Đừng probe lại.**

### Thay bằng HTML listing scraper

Nguồn HTML-listing **đầu tiên** của repo — ngoại lệ có chủ ý của TDR-001 (RSS > API > HTML):
baodautu không có cả RSS lẫn API, nhưng là nguồn số 1 về giải ngân đầu tư công / FDI / hạ tầng.

**Thêm mới**
- `src/scrapers/baodautu.py` — `BaodautuScraper(CaptureMixin, BaseScraper)` + `_parse_detail_date`.
- `config/domains/baodautu.yaml` — viết lại hoàn toàn, 6 chuyên mục.
- `tests/test_baodautu.py` — 14 case + 2 fixture thật.
- `tests/_fakes.py` — thêm `listing_html` / `listing_match` / `listing_calls` cho FakeHTTP.
- `domains/baodautu/{schema.yaml,README.md,changelog.md}`.

### ⚠️ Bẫy cấu trúc listing — giả định ban đầu SAI

Kế hoạch ghi item selector là `div.thumbblock`. **Sai.** Class `thumbblock` nằm trên thẻ
**`<a>` ảnh**, không phải `<div>` → `BeautifulSoup.select("div.thumbblock")` trả **0 node**
(dù chuỗi "thumbblock" xuất hiện 35 lần trong HTML).

Cấu trúc thật: mỗi bài là một thẻ **`<article>`** (29 thẻ, 28 có link bài).
Trong mỗi `<article>` có **nhiều `<a>`**, và link ảnh (`a.thumbblock`, **không có text**)
đứng **TRƯỚC** link tiêu đề → `select_one()` sẽ vớ phải link ảnh rồi bị bỏ qua ⇒ **mất sạch bài**.

→ Scraper duyệt hết anchor trong block, lấy cái **đầu tiên vừa có text vừa khớp
`link_pattern` (`-d\d+\.html`)**.

### Bẫy khác (verified 2026-09-07)

| # | Bẫy | Xử lý |
|---|---|---|
| 1 | Trang 1 = `…-d<N>/` (CÓ `/`); trang >1 = `…-d<N>/p<N>` — **thêm `/` cuối → 404** | `_page_url()` + test `test_page_url_trailing_slash` |
| 2 | Body: `.content` là **chuỗi template JS** `<div class="content">'+content+'</div>'` của widget bình luận | dùng `#content_detail_news`; test regression `test_content_selector_avoids_js_template` |
| 3 | Trang **KHÔNG có `<h1>`** | title lấy từ listing; `div.title-detail` chỉ để đối chiếu |
| 4 | **KHÔNG có** `<time>` / `article:published_time` / JSON-LD | ngày = text thuần `dd/MM/yyyy HH:mm` |
| 5 | Listing **không có ngày đăng** | `published_at` điền ở `enrich()` từ trang detail |
| 6 | Ngày nằm ở `span.post-time` (**ngoài** `#content_detail_news`) | `date_scope_selector: span.post-time` — chính xác, không dính ngày trong thân bài |
| 7 | Slug d5 có **HAI** dấu gạch ngang: `ngan-hang--bao-hiem` | test `test_config_file_sane` canh |
| 8 | Paragraph mã hoá HTML entity (`&ecirc;`) | trafilatura xử lý |

**Không bịa timestamp:** ngày không parse được → `published_at = ""` **và** ghi
`missing: ["published_at"]` vào `.meta.json` để drift report nhìn thấy.
Test `test_missing_date_recorded_not_faked`.

### Chuyên mục (6)

d2 Toàn cảnh đầu tư ★ (đầu tư công/giải ngân/FDI/hạ tầng) · d1 Thời sự Đầu tư ★ ·
d6 Đầu tư tài chính ★ · d3 Kinh doanh ★ · d5 Ngân hàng & Bảo hiểm · d41 Đầu tư và Pháp luật.
**Loại d80 "Quảng bá"** (PR trả tiền).

### robots.txt

`User-agent: * / Allow: /` — không `Disallow`, không `Crawl-delay`.
Vẫn giữ `respect_robots: true` + `rate_limit: 3.0`; **không** bật `proxy_rotation`
(HTML scraping đã lộ hơn RSS; bật proxy là vượt từ tương thích sang né tránh).

### Sitemap = backstop, chưa dùng

`sitemaps/news-YYYY-M.xml` (102 KB, **348 `<url>`** cho 1-7/9 → **~50 bài/ngày**).
Nhưng `<loc>` bị đệm khoảng trắng, `<lastmod>` **chỉ có ngày**, **không có category**
→ không nhắm được beat đầu tư công. Chỉ mở sub-phase 04b nếu tỉ lệ parse ngày < 98%
hoặc miss rate > 5%.

## 2026-07-24 — Disabled (chẩn đoán sai là "dormant")

Tắt vì "feed trả XML hợp lệ nhưng 0 item — dormant giống NDH", kèm comment
"bật lại khi feed có items". Chẩn đoán này **sai**: không phải tạm thời hết bài mà là
generator hỏng (channel luôn là "Trang chủ" + `<link>` dị dạng). Sửa lại 2026-09-07.
