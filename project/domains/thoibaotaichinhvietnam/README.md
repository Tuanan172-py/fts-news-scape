# Domain Mastery — Thời báo Tài chính Việt Nam (thoibaotaichinhvietnam.vn)

Cơ quan ngôn luận của **Bộ Tài chính**. Nguồn mạnh nhất (đã xác minh) về
**giải ngân đầu tư công**, chính sách tài chính, thuế - hải quan.

---

## 1. Tổng quan

| Thuộc tính | Giá trị |
|-----------|--------|
| **Domain** | thoibaotaichinhvietnam.vn |
| **Phương thức** | RSS (1 feed site-wide) + full raw HTML capture |
| **Scraper class** | `RssCaptureScraper` — **0 dòng code riêng**, chỉ 1 file YAML |
| **Config name** | `thoibaotaichinhvietnam` (khớp host stem — né bẫy `.vn`-suffix) |
| **Schema contract** | `domains/thoibaotaichinhvietnam/schema.yaml` |
| **Bronze** | `data/raw_html/thoibaotaichinhvietnam.vn/<yyyymmdd>/` |
| **Volume** | ~50 bài/ngày (25 item/feed trải ~11 giờ) |
| **Trạng thái** | enabled 2026-09-07 (nguồn mới) |

## 2. ⚠️ Cạm bẫy số 1 — RSS chuyên mục là ẢO

`https://thoibaotaichinhvietnam.vn/{category}/rss_feed/` trả **HTTP 200 với 25 item**
cho mọi chuyên mục — nhưng đó là **cùng một feed site-wide**. Server bỏ qua path.

```
chung-khoan / thue-hai-quan / bat-dong-san / root
  → cùng 25 item, cùng pubDate, channel <link> = .../trang-chu
```

**Đừng cấu hình nhiều feed chuyên mục.** Hậu quả: fetch trùng N lần + gắn nhãn chuyên mục sai.

**Chuyên mục thật** nằm ở trang detail:
```html
<meta property="article:section" content="Chính sách tài chính">
<meta name="category_url" content="https://thoibaotaichinhvietnam.vn/chinh-sach-tai-chinh">
```
Đọc qua `detail.category_meta: "article:section"` → chèn vào đầu `Article.categories`.

## 3. Selector map (detail page, verified 2026-09-07)

| Thành phần | Selector |
|---|---|
| **Body** | `div.article-detail-main` (fallback `div.article-content`) |
| Sapo | `div.article-detail-desc` |
| Tác giả | `div.article-detail-author` |
| Nguồn | `div.article-detail-source` |
| Tags | `div.article-tags` |
| Breadcrumb | `div.bx-breadcrumb` |
| **Ngày** | `<meta property="article:published_time" content="2026-09-07T19:51:09+07:00">` — ISO + offset chuẩn |
| **Chuyên mục** | `<meta property="article:section">` |

## 4. content:encoded — có, nhưng KHÔNG được dùng thay Bronze

Feed ship full body trong `content:encoded`. Cám dỗ là bỏ fetch detail cho nhanh.
**Không được.** Inline HTML không phải Bronze byte-exact. `RssCaptureScraper` luôn fetch
trang detail và chỉ dùng inline làm **body dự phòng khi capture fail**.
Test `test_inline_not_used_when_capture_ok` canh chừng điều này.

## 5. robots.txt

```
Allow: /
Disallow: /ajax/ /sp/ /services/ /utilities/ /apiservice@/ /apicenter@/ /widgets@/
          /member.api/ /preview_article/ /stats/ /slie/ /article/ /login/
          /administrator/ /act/ /adsfw/ /tag/ *.pdf *.xls *.xlsx *.doc *.docx
```

- Bài chi tiết ở **ROOT** `/<slug>-<id>.html` → `/article/` **không** chặn chúng.
- **TUYỆT ĐỐI không fetch attachment PDF/XLS** — bị Disallow tường minh.
- Nguồn cơ quan nhà nước: giữ `rate_limit: 3.0`, **không** bật `proxy_rotation`.
  Bị chặn ở đây tổn hại uy tín nặng hơn là mất vài bài.

## 6. Vai trò trong hệ thống

NSO (`nso.gov.vn`) **KHÔNG còn bị chặn** — chẩn đoán TCP reset ban đầu ở phase-05 chỉ là
chập chờn; G1 chạy lại 2026-09-07 đạt **12/12 PASS**, đã build driver riêng
(`src/pipeline/periodic_reports.py`, design 16). TBTC vẫn giữ vai trò **proxy bổ sung** cho số
liệu KTXH / giải ngân đầu tư công — đăng lại báo cáo trong vài giờ, transport ổn định, ngày sạch.

## 7. Bảo trì

- `python scripts/verify_quality.py thoibaotaichinhvietnam.vn` (dùng **host**).
- `python scripts/domain_check.py --report thoibaotaichinhvietnam`.
- Nếu feed nhiễu (có cả xã hội/đời sống): bật `filter.any`/`filter.none` **ngay trong YAML**
  — kế thừa từ `RSSScraper`, 0 dòng code.
- Kiểm tra định kỳ watch point `tbtc-w3`: nếu upstream sửa feed chuyên mục cho đúng thì
  có thể quay lại nhiều feed và bỏ `category_meta`.
