# Domains — Báo VN qua RSS

Cập nhật: **2026-09-07**. `language: vi`, `extract_full: true` (trừ ghi chú), cap 30.

**Hai class khác nhau — đọc kỹ:**
- `method: rss` → `RSSScraper` — **KHÔNG lưu Bronze** (`enrich()` không gọi `RawStore`).
  Mọi nguồn nhóm này hiện **disabled** (freeze Bronze-first 2026-08-03).
- `method: rss_capture` → `RssCaptureScraper` (kế thừa `RSSScraper`) — **có Bronze byte-exact**.
  Chỉ override `__init__` + `enrich()`; `fetch_list`/`parse_item`/`filter`/`link_rewrites` dùng chung.

Enabled trong nhóm này: **vietstock**, **vneconomy** (scraper riêng, có capture) và
**vietnambiz** (`rss_capture`, mới 2026-09-07). Xem [README.md](README.md) cho ma trận đầy đủ.

## Nguồn có cấu hình đặc thù

### vietstock — `vietstock.yaml`

- **4 feeds:** `/0/tin-moi.rss`, `/144/chung-khoan.rss`, `/733/doanh-nghiep.rss`, `/761/kinh-te/vi-mo.rss`.
- **Quirk:** Internal API (TopPageArticle…) unreachable/cần browser session → **RSS là PRIMARY**.
  pubDate `+0700`. Description chứa `<img>` → strip khi bóc summary. Index 60 feed tại `vietstock.vn/rss`.

### vnexpress — `vnexpress.yaml`

- **1 feed:** `/rss/kinh-doanh.rss`.
- **Quirk:** `chung-khoan.rss` **redirect 302** → chỉ dùng kinh-doanh. Body `fck_detail` → trafilatura OK.

### vneconomy — `vneconomy.yaml`

- **3 feeds:** `/chung-khoan.rss`, `/tai-chinh.rss`, `/thi-truong.rss`.
- **Quirk:** khai namespace `content:encoded` nhưng item **rỗng** → phải fetch detail. Thêm để
  **thay NDH** (dormant, quyết định 2026-07-24).

### vietnamnet — `vietnamnet.yaml` (**có filter**)

- **2 feeds:** `/rss/chung-khoan.rss` (142 items), `/rss/kinh-doanh.rss` (**1000 items!**).
- **filter.any** (18 keyword: chứng khoán, cổ phiếu, vn-index, trái phiếu, niêm yết, lãi suất,
  ngân hàng, tỷ giá, doanh nghiệp, vàng, hose, hnx, upcom, lợi nhuận, cổ tức, vĩ mô, gdp, lạm
  phát, fed), `drop_unmatched: true`.
- **Quirk:** kinh-doanh quá rộng → filter **bắt buộc**. Nếu vẫn nhiễu sau 24h: bỏ feed kinh-doanh.

### baodautu — `baodautu.yaml` (**DISABLED**)

- **3 feeds:** `/chung-khoan.rss`, `/dau-tu-tai-chinh.rss`, `/ngan-hang--bao-hiem.rss`.
- **Quirk:** `enabled: false` — feed XML hợp lệ nhưng **0 `<item>`** (dormant, verify nhiều
  UA/client). Có **4 dòng trống trước `<?xml`** (RSSScraper đã lstrip). Bật lại khi feed hồi.

## Nguồn "cắm là chạy" (quirk encoding nhẹ, RSSScraper tự xử)

| Domain      | Feed                                  | Quirk                                                                                              |
| ----------- | ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| tuoitre     | `/rss/kinh-doanh.rss`               | XML minified 1 dòng; 50 items; date US-style`%m/%d/%Y %I:%M:%S %p`                              |
| thanhnien   | `/rss/kinh-te.rss`                  | thiếu`<?xml` declaration; 50 items                                                              |
| znews       | `/rss/kinh-doanh-tai-chinh.rss`     | 50 items                                                                                           |
| cafebiz     | `/rss/home.rss`                     | home.rss = superset (61 items); zone khác không tồn tại                                        |
| vietnamplus | `www.vietnamplus.vn/rss/kinhte.rss` | dùng bản**www.** (không en.); 50 items                                                    |
| vietnambiz  | **6 feeds** (xem §vietnambiz)       | ✅ enabled, `rss_capture`. khai `utf-16` serve **utf-8**; 30 items/feed |
| dantri      | `/rss/kinh-doanh.rss`               | **BOM utf-8** → utf-8-sig; KHÔNG có chung-khoan.rss; 100 items                            |

### vietnambiz — `vietnambiz.yaml` ✅ enabled 2026-09-07, `method: rss_capture`

Nguồn **đầu tiên** chạy `RssCaptureScraper` (RSS list + Bronze full raw HTML capture).

- **6 feeds** (verified live 2026-09-07, 30 items/feed):
  `/chung-khoan.rss`, `/tai-chinh.rss`, `/vi-mo.rss`,
  `/doanh-nghiep.rss`, `/nha-dat.rss`, `/hang-hoa.rss`.
  ⚠️ `/quoc-te.rss` **chết** (0 item / 356 bytes) — không dùng.
- **Body selector BẮT BUỘC:** `div.vnbcbc-body` (`.vnbcbc-body.vceditor-content[data-role=content]`).
  Trang **KHÔNG có thẻ `<article>`** → nếu để selector mặc định thì `_looks_complete` fail →
  `capture_status: partial` → `SELECTOR_BROKEN` → agent **hold** mọi bài. Có test regression.
  KHÔNG dùng `div.post-body-content` (bọc cả title/author/date).
- **Encoding:** XML declaration khai `utf-16` nhưng serve utf-8 → `_decode_feed` strip encoding attr.
- **Ngày:** `pubDate` = `Mon, 07 Sep 2026 19:41:53 GMT+7` (phi chuẩn) → `_parse_raw_date`
  normalize `GMT+7` → `+0700`.
  ⚠️ `meta article:published_time` **thiếu offset timezone** — đừng dùng nó thay `pubDate`.
- **URL bài** đuôi `.htm` (không phải `.html`). Ảnh trên `cdn.vietnambiz.vn`, `src` trực tiếp.
- **robots.txt:** `Allow: /`, không `Disallow`, không `Crawl-delay`.
- Chi tiết: [`domains/vietnambiz/README.md`](../../domains/vietnambiz/README.md).

### thoibaotaichinhvietnam — `thoibaotaichinhvietnam.yaml` ✅ enabled 2026-09-07, `method: rss_capture`

Cơ quan ngôn luận **Bộ Tài chính**. Nguồn proxy KTXH/đầu tư công chính (NSO đang bị chặn network).

- ⚠️ **RSS theo chuyên mục là ẢO.** `/{category}/rss_feed/` trả 200 + 25 item cho MỌI chuyên mục,
  nhưng đều là **cùng feed site-wide `trang-chu`** (verified: chung-khoan / thue-hai-quan /
  bat-dong-san / root cho ra 25 item y hệt, cùng pubDate, cùng channel `<link>`).
  → **Chỉ dùng 1 feed** `https://thoibaotaichinhvietnam.vn/rss_feed/`.
- **Chuyên mục thật** ở trang detail: `<meta property="article:section">` →
  đọc bằng `detail.category_meta`, chèn vào đầu `categories`.
- Body `div.article-detail-main` (fallback `div.article-content`).
- Ngày: `article:published_time` = ISO **+07:00 chuẩn** → health_threshold 1.0.
- Feed **có** `content:encoded` full body — vẫn fetch detail để giữ Bronze; inline chỉ là fallback.
- robots: Disallow `/tag/ /article/ *.pdf *.xls`; bài chi tiết ở ROOT nên không bị chặn.
  **Không fetch attachment PDF/XLS.**
- Volume ~50 bài/ngày. Chi tiết: [`domains/thoibaotaichinhvietnam/README.md`](../../domains/thoibaotaichinhvietnam/README.md).

### baodautu — ĐÃ CHUYỂN KHỎI NHÓM RSS

baodautu **không còn là nguồn RSS**. RSS của họ hỏng vĩnh viễn ở server (mọi feed trả cùng
channel rỗng `Trang chủ` + `<link>` dị dạng `https://baodautu.vn//.rss`, 0 item —
re-verified 2026-09-07, 8/8 URL). Từ 2026-09-07 chạy bằng **HTML listing scraper**.

→ Xem [html-scrapers.md](html-scrapers.md) và
[`domains/baodautu/README.md`](../../domains/baodautu/README.md).

## Chung cho nhóm VN RSS

- Encoding: mọi bẫy (BOM/utf-16-mislabel/blank-line/thiếu decl) do `_decode_feed` xử tập trung.
- Ngày: `_parse_raw_date` chuẩn hoá về giờ VN.
- Symbols: `tag_tickers(title+summary, watchlist)` client-side.
- categories: tên feed (vd "Vietstock Chứng khoán").
- Muốn thêm báo VN mới: chỉ tạo YAML — xem [../dev/03-adding-a-source.md](../dev/03-adding-a-source.md).
