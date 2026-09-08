# Domains — Nguồn HTML listing (không có RSS, không có API)

Cập nhật: 2026-09-07 · 1 nguồn: **baodautu**.

## Vì sao có nhóm này (ngoại lệ TDR-001)

TDR-001 xếp **RSS > API > HTML**, và HTML gần như không dùng. Nhóm này là ngoại lệ **có chủ ý**,
chỉ mở khi thoả **cả ba**:

1. Nguồn **không có RSS dùng được** *và* **không có API** — đã verify live, không phải phỏng đoán.
2. Nội dung đủ giá trị để chịu chi phí bảo trì HTML scraping.
3. robots.txt cho phép.

Cái giá phải trả: **không có hợp đồng upstream nào**. Feed RSS đổi thì thường vẫn parse được;
template HTML đổi thì vỡ ngay và âm thầm. Vì vậy nhóm này bắt buộc:

- **Mọi selector nằm trong YAML**, không hard-code trong Python → template đổi = sửa config.
- `domains/<name>/schema.yaml` ghi lại **toàn bộ** selector — đó là baseline drift duy nhất.
- Listing trả 0 item → **ghi error rõ ràng** (`"listing 0 items (template drift?)"`), không im lặng.
- Ngưỡng cảnh báo chặt hơn nhóm RSS.

## baodautu — `baodautu.yaml` ✅ enabled 2026-09-07 (`method: baodautu`)

Cơ quan của Bộ Tài chính. Nguồn số 1 về **giải ngân đầu tư công, FDI, quy hoạch hạ tầng**.

### RSS hỏng vĩnh viễn — không phải dormant

Re-verify 2026-09-07, **8/8 URL**: 200, ~1.2 KB, **0 `<item>`**. Mọi feed trả **cùng** channel:

```xml
<title>Trang chủ</title>
<link>https://baodautu.vn//.rss</link>   <!-- double-slash, không có category -->
```

Generator phía server hỏng. `rssMain.html` trả HTML homepage 34 KB. **Đừng probe lại.**
(Chẩn đoán 2026-07-24 "dormant, có thể bật lại" là sai và đã tồn tại 14 tháng.)

### URL

| | |
|---|---|
| Trang 1 | `https://baodautu.vn/{slug}-d{id}/` — **CÓ** `/` cuối |
| Trang N>1 | `https://baodautu.vn/{slug}-d{id}/p{N}` — **KHÔNG** có `/` cuối |
| `…/p2/` | **404** ⚠️ |

6 chuyên mục: d2 Toàn cảnh đầu tư ★ · d1 Thời sự Đầu tư ★ · d6 Đầu tư tài chính ★ ·
d3 Kinh doanh ★ · d5 `ngan-hang--bao-hiem` (⚠️ **hai** dấu gạch) · d41 Đầu tư và Pháp luật.
Loại d80 "Quảng bá" (PR).

### Ba cái bẫy phải biết

**1. `div.thumbblock` khớp 0 node.** Class `thumbblock` nằm trên thẻ **`<a>` ảnh**, không phải
`<div>` (dù chuỗi xuất hiện 35 lần trong HTML). Item thật là thẻ **`<article>`**.
Trong mỗi `<article>`, link ảnh (**không có text**) đứng **trước** link tiêu đề → `select_one()`
vớ phải link ảnh rồi bỏ qua ⇒ **mất sạch bài**. Phải duyệt hết anchor và lọc theo
text + `link_pattern` (`-d\d+\.html`).

**2. `.content` là chuỗi template JavaScript.** Source có
`<div class="content">'+content+'</div>'` của widget bình luận. Selector `.content` bắt nhầm node
này. **Chỉ dùng `#content_detail_news`.** Có test regression.

**3. Không có metadata ngày.** Trang detail **không có** `<h1>`, `<time>`,
`article:published_time`, JSON-LD. Ngày là **text thuần** `dd/MM/yyyy HH:mm` trong
`span.post-time` (nằm **ngoài** `#content_detail_news`). Listing **không có ngày** →
`published_at` chỉ điền được ở `enrich()`.
Parse fail → `published_at = ""` **+** ghi `missing: ["published_at"]`. **Không bịa timestamp.**

### robots.txt

`User-agent: * / Allow: /` — không `Disallow`, không `Crawl-delay`. Vẫn giữ
`respect_robots: true` + `rate_limit: 3.0`. **Không** bật `proxy_rotation`: HTML scraping đã lộ
hơn RSS, bật proxy là vượt từ *tương thích* sang *né tránh* — cần maintainer duyệt.

### Sitemap backstop (chưa dùng)

`sitemaps/news-{YYYY}-{M}.xml` — 348 `<url>` cho 1-7/9 ≈ **50 bài/ngày**. Nhưng `<loc>` bị đệm
khoảng trắng, `<lastmod>` **chỉ có ngày**, **không có category**. Chỉ mở sub-phase 04b nếu
date-parse < 98% hoặc miss rate > 5%. (Hiện date-parse = **100%**.)

Chi tiết đầy đủ: [`domains/baodautu/README.md`](../../domains/baodautu/README.md) ·
[`domains/baodautu/schema.yaml`](../../domains/baodautu/schema.yaml)

## Thêm nguồn HTML listing mới

Xem [`../dev/03-adding-a-source.md`](../dev/03-adding-a-source.md) §1 (nhánh 3) và dùng
`src/scrapers/baodautu.py` làm mẫu. Bắt buộc:

- [ ] Chứng minh **không** có RSS *và* **không** có API (ghi lại URL đã probe + kết quả).
- [ ] Fetch thật 1 trang listing + 1 trang detail, **đếm số item parse được** trước khi viết code.
- [ ] Kiểm tra selector bằng BeautifulSoup thật — đừng tin DevTools (`div.X` vs `a.X`!).
- [ ] Mọi selector vào YAML; `schema.yaml` ghi đủ + watch points.
- [ ] Test: 0-item → error rõ ràng; selector bẫy → regression test; ngày thiếu → không bịa.
