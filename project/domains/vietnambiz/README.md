# Domain Mastery — VietnamBiz (vietnambiz.vn)

Tài liệu toàn diện về nguồn VietnamBiz: cấu trúc dữ liệu, data flow, field mapping, pitfalls,
và quy trình bảo trì. Nguồn ĐẦU TIÊN chạy trên `method: rss_capture` (RSS + Bronze capture).

---

## 1. Tổng quan

| Thuộc tính | Giá trị |
|-----------|--------|
| **Domain** | vietnambiz.vn |
| **Phương thức** | RSS 2.0 (6 feeds) + full raw HTML capture |
| **Auth** | Public, không cần auth |
| **Scraper class** | `RssCaptureScraper` (`src/scrapers/rss_capture.py`), registry key `_rss_capture` |
| **Schema contract** | `domains/vietnambiz/schema.yaml` |
| **Config** | `config/domains/vietnambiz.yaml` |
| **Bronze** | `data/raw_html/vietnambiz.vn/<yyyymmdd>/<hash>.{html,meta.json}` |
| **Silver** | `data/silver/vietnambiz.vn/<yyyymmdd>/<hash>.json` |
| **Trạng thái** | enabled 2026-09-07 (trước đó disabled từ 2026-08-03) |

## 2. Cơ chế lấy dữ liệu

```
config/domains/vietnambiz.yaml → 6 feed URLs:
  ├── /chung-khoan.rss    "VietnamBiz Chứng khoán"
  ├── /tai-chinh.rss      "VietnamBiz Tài chính"
  ├── /vi-mo.rss          "VietnamBiz Vĩ mô"
  ├── /doanh-nghiep.rss   "VietnamBiz Doanh nghiệp"   (mới 2026-09-07)
  ├── /nha-dat.rss        "VietnamBiz Nhà đất"        (mới 2026-09-07)
  └── /hang-hoa.rss       "VietnamBiz Hàng hóa"       (mới 2026-09-07)
    ↓ (per feed, tuần tự, rate_limit 3s)
GET feed → raw bytes → _decode_feed() → feedparser.parse()      [kế thừa RSSScraper]
    ↓ parse_item()                                              [kế thừa RSSScraper]
Article(source_domain=vietnambiz.vn, published_at ISO +07:00, language=vi)
    ↓ enrich()                                                  [OVERRIDE — Bronze]
  1. RobotsGate.allowed(url)?
  2. crawl-delay → RateLimiter
  3. SourceBackoff.before_fetch
  4. HTTPClient.get_response(url)
  5. ★ RawStore.save(resp)  ← byte-exact, TRƯỚC mọi parse (design 06 AC7)
  6. content_html = select_one("div.vnbcbc-body")
  7. content_text = extract_text(content_html)
```

- **6 feeds** × 30 items = ~180 raw items/cycle
- **Detail cap**: 30 bài/cycle → phần dư `metadata.detail_deferred = true`
- **Per-feed isolation**: 1 feed chết → `self.errors`, feed khác vẫn chạy
- Chi phí 1 cycle ≈ 6×3s + 30×3s ≈ 108 s (nhịp scheduler 15 phút)

## 3. Vì sao `rss_capture` chứ không phải `rss`

`RSSScraper` (generic `method: rss`) **không bao giờ gọi `RawStore`** — nó chỉ
`http.get()` + `extract_content()`. Nghĩa là **không có Bronze artifact**. Đây chính là lý do
~20 domain bị disable 2026-08-03: mở rộng nguồn giờ phải Bronze-first, không phải RSS-breadth.

`RssCaptureScraper` **kế thừa** `RSSScraper` và chỉ override `__init__` + `enrich()`:
`fetch_list`, `parse_item`, `filter.any/none`, `link_rewrites` dùng lại nguyên vẹn (0 dòng lặp).

## 4. Pitfalls (verified live 2026-09-07)

| # | Pitfall | Xử lý |
|---|---------|-------|
| 1 | XML declaration khai `encoding="utf-16"` nhưng serve **utf-8** | `_decode_feed()` strip encoding attr khỏi 200 byte đầu |
| 2 | `pubDate` = `Mon, 07 Sep 2026 19:41:53 **GMT+7**` (phi chuẩn RFC-2822) | `_parse_raw_date()` normalize `GMT+7` → `+0700` |
| 3 | **Trang detail KHÔNG có thẻ `<article>`** | `content_selector` là **BẮT BUỘC**. Default `"article"` sẽ làm **mọi** bài thành `partial` → `SELECTOR_BROKEN` → agent **HOLD**. Có test regression: `test_default_article_selector_would_break` |
| 4 | `div.post-body-content` bọc cả title/author/date | Dùng `div.vnbcbc-body` (hẹp, đúng body) |
| 5 | `meta article:published_time` = `2026-09-07T19:41:00` — **THIẾU timezone** | Lấy ngày từ `pubDate` của RSS. **ĐỪNG** chuyển sang meta tag |
| 6 | URL bài kết thúc **`.htm`** (không phải `.html`) | Không xử lý gì, nhưng đừng hard-code `.html` |
| 7 | `quoc-te.rss` chết (0 item / 356 bytes) | Đã loại khỏi config |
| 8 | Feed **không có** `content:encoded` | Bắt buộc fetch detail (đúng ý đồ Bronze) |

## 5. Selector map (detail page)

| Thành phần | Selector |
|---|---|
| **Body (dùng)** | `div.vnbcbc-body` (`.vnbcbc-body.vceditor-content[data-role=content]`) |
| Wrapper (quá rộng) | `div.post-body-content[data-role=body]` |
| Title | `h1.vnbcb-title` |
| Ngày (tham chiếu) | `span.vnbcbat-data[data-role=publishdate]` → `19:41 \| 07/09/2026` |
| Ảnh CDN | `cdn.vietnambiz.vn` — `src` trực tiếp, **không** lazy-load |

## 6. robots.txt

```
User-agent: *
Allow: /
```
Không `Disallow`, không `Crawl-delay`. Vẫn giữ `respect_robots: true` và `rate_limit: 3.0` —
permissive hôm nay không có nghĩa là permissive mãi mãi (`RobotsGate` cache 24 h).

## 7. Bảo trì

- Watch point số 1: **`div.vnbcbc-body`**. Đổi class → `capture_status: partial` hàng loạt.
  Theo dõi bằng `scripts/report_drift.py` và tỉ lệ `missing[incomplete_render]`.
- Kiểm tra: `python scripts/verify_quality.py vietnambiz.vn` (dùng **host**, không phải `vietnambiz`).
- Field health: `python scripts/domain_check.py report vietnambiz`.
- Sửa selector → **không cần re-scrape**: `python scripts/rederive_from_bronze.py vietnambiz.vn`.

## 8. Liên quan

- `docs/design/06-raw-html-capture.md` — cơ chế capture
- `docs/design/07-storage-layers-and-change-detection.md` — Bronze/Silver + drift
- `docs/dev/03-adding-a-source.md` §2b — quy trình thêm nguồn `rss_capture`
- `plans/20260907-0834-market-sources-expansion/phase-01-rss-capture-framework-vietnambiz.md`
