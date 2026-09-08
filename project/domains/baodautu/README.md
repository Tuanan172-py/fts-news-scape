# Domain Mastery — Báo Đầu Tư (baodautu.vn)

Cơ quan của **Bộ Tài chính** (trước là Bộ Kế hoạch & Đầu tư). Nguồn **số 1** về
giải ngân đầu tư công, dự án FDI, quy hoạch hạ tầng, chính sách vĩ mô.

**Nguồn HTML-listing đầu tiên của repo** — ngoại lệ có chủ ý của TDR-001.

---

## 1. Tổng quan

| Thuộc tính | Giá trị |
|-----------|--------|
| **Domain** | baodautu.vn |
| **Phương thức** | **HTML listing** (list) + full raw HTML capture (detail) |
| **Scraper class** | `BaodautuScraper` (`src/scrapers/baodautu.py`), registry key `baodautu` |
| **Chuyên mục** | 6 (d2, d1, d6, d3, d5, d41) |
| **Volume** | ~50 bài/ngày (sitemap: 348 url cho 7 ngày) |
| **Bronze** | `data/raw_html/baodautu.vn/<yyyymmdd>/` |
| **Trạng thái** | enabled 2026-09-07 (disabled 2026-07-24 vì RSS hỏng) |

## 2. 🔴 RSS hỏng vĩnh viễn — đừng chờ, đừng probe lại

Comment cũ "bật lại khi feed có items" tồn tại **14 tháng** và không bao giờ khả thi.

Re-verify 2026-09-07, **8/8 URL**: 200, ~1.2 KB, **0 `<item>`**. Nguyên nhân gốc —
**mọi** feed trả **cùng một channel rỗng**:

```xml
<title>Trang chủ</title>
<link>https://baodautu.vn//.rss</link>   <!-- double-slash, KHÔNG có category -->
```

Generator RSS phía server hỏng. `rssMain.html` trả HTML homepage 34 KB, không phải feed.
Đây **không phải** "dormant" (hết bài tạm thời) — chẩn đoán 2026-07-24 đã sai.

Nếu ngày nào upstream sửa, cân nhắc quay lại `rss_capture` (rẻ và bền hơn) —
watch point `bdt-w6`, kiểm tra ~6 tháng/lần.

## 3. ⚠️ Bẫy cấu trúc listing (dễ sai nhất)

**Class `thumbblock` nằm trên thẻ `<a>` ẢNH, không phải `<div>`.**
`select("div.thumbblock")` trả **0 node** — dù chuỗi "thumbblock" xuất hiện 35 lần trong HTML.
Kế hoạch ban đầu ghi `div.thumbblock` và đã sai vì lý do này.

Cấu trúc thật:

```
<article class="d-flex">              ← ITEM (29 thẻ/trang, 28 có link bài)
  <a class="thumbblock thumb275x155" href="…-dNNN.html">   ← link ẢNH, KHÔNG có text
     <img …>
  </a>
  <a class="fs22 fbold" href="…-dNNN.html">Tiêu đề bài</a>  ← link TIÊU ĐỀ
  <div class="sapo_thumb_news">Sapo…</div>
  <span class="cl_green">Toàn cảnh đầu tư</span>
</article>
```

Link ảnh đứng **TRƯỚC** link tiêu đề ⇒ `select_one("a")` vớ phải link ảnh (không có text)
rồi bị bỏ qua ⇒ **mất sạch bài**.

→ Scraper duyệt **hết** anchor trong block, lấy cái **đầu tiên vừa có text vừa khớp**
`link_pattern` = `-d\d+\.html`.

## 4. ⚠️ Bẫy pagination

| Trang | URL | Ghi chú |
|---|---|---|
| 1 | `https://baodautu.vn/{slug}-d{id}/` | **CÓ** dấu `/` cuối |
| N>1 | `https://baodautu.vn/{slug}-d{id}/p{N}` | **KHÔNG** có `/` cuối |
| — | `…/p2/` | **404** |

Anchor trên trang là relative (`<a href="p2" class="pagation_item">` — upstream viết thiếu
chữ "in" trong "pagination", đừng sửa). Test `test_page_url_trailing_slash` canh chừng.

## 5. ⚠️ Bẫy body selector — `.content` là chuỗi JS

Trong source có:

```html
<div class="content">'+content+'</div>' +
```

Đó là **chuỗi template JavaScript** của widget bình luận, không phải thân bài.
Selector `.content` sẽ bắt nhầm node này.

→ **Chỉ dùng `#content_detail_news`.**
Test regression `test_content_selector_avoids_js_template` khẳng định `'+content+'`
không bao giờ lọt vào `content_html`/`content_text`.

## 6. ⚠️ Ngày đăng — không có metadata nào

Trang detail **KHÔNG có**: `<h1>`, `<time>`, `article:published_time`, JSON-LD.

Ngày là **text thuần** `dd/MM/yyyy HH:mm` trong `span.post-time`:

```html
<span class="post-time"> - 07/09/2026 10:38</span>
```

`span.post-time` nằm **NGOÀI** `#content_detail_news` (offset 16656 vs 18739) →
`date_scope_selector: "span.post-time"` là chính xác, không dính ngày trong thân bài.

**Listing không có ngày** → `published_at` chỉ điền được ở `enrich()`. Hệ quả: không thể
xếp/lọc theo độ mới trước khi fetch; dựa vào thứ tự listing + dedup.

**Không bịa timestamp:** parse fail → `published_at = ""` **và** ghi
`missing: ["published_at"]` vào `.meta.json`.

## 7. Selector map

| Thành phần | Selector |
|---|---|
| Item listing | `article` |
| Link | `a[href]` + `link_pattern` `-d\d+\.html`, lấy cái đầu có text |
| Sapo listing | `div.sapo_thumb_news, div.desc_list_news_home` |
| **Body detail** | **`#content_detail_news`** (⚠️ KHÔNG dùng `.content`) |
| Title detail | `div.title-detail` (đối chiếu; **không có `<h1>`**) |
| Sapo detail | `div.sapo_detail` |
| Tác giả | `a.author` (`a.author.cl_green`) |
| Ngày | `span.post-time` |
| Tags | `div.tag_detail > .tag_detail_item` |

## 8. robots.txt

```
User-agent: *
Allow: /
Sitemap: https://baodautu.vn/sitemap.xml
```

Hoàn toàn permissive — không `Disallow`, không `Crawl-delay`. Vẫn giữ
`respect_robots: true` và `rate_limit: 3.0`. **Không** bật `proxy_rotation`:
HTML scraping đã lộ hơn RSS, bật proxy là vượt từ *tương thích* sang *né tránh*.

## 9. Sitemap backstop (chưa dùng)

`sitemaps/news-{YYYY}-{M}.xml` — 102 KB, **348 `<url>`** cho 1-7/9 → **~50 bài/ngày**.

Hạn chế: `<loc>` bị đệm khoảng trắng (cần `.strip()`), `<lastmod>` **chỉ có ngày**,
**không có category** → không nhắm được beat đầu tư công.

Chỉ mở **sub-phase 04b** nếu tỉ lệ parse ngày < 98% hoặc miss rate > 5%. Đừng build sẵn (YAGNI).

## 10. Bảo trì

- **Rủi ro thường trực:** nguồn này KHÔNG có hợp đồng upstream. `schema.yaml` là baseline
  drift duy nhất. Mọi selector nằm trong YAML → template đổi thì sửa config, không sửa code.
- Listing trả 0 item → scraper ghi error `"listing 0 items (template drift?)"` **rõ ràng**,
  không im lặng.
- `python scripts/verify_quality.py baodautu.vn` · `python scripts/domain_check.py --report baodautu`
- Sửa selector → `python scripts/rederive_from_bronze.py baodautu.vn` (không cần re-scrape).
