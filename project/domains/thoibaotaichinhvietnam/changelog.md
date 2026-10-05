# TBTC Domain Changelog

Ghi lại mọi thay đổi upstream của thoibaotaichinhvietnam.vn ảnh hưởng đến scraper.

---

## 2026-09-07 — Onboard nguồn mới (phase-02)

Kế hoạch: `plans/20260907-0834-market-sources-expansion/phase-02-tbtc-new-source.md`

**Thêm mới**
- `config/domains/thoibaotaichinhvietnam.yaml` — `method: rss_capture`, chạy trên
  `RssCaptureScraper` của phase-01.
- `domains/thoibaotaichinhvietnam/{schema.yaml,README.md,changelog.md}`.
- `tests/test_thoibaotaichinhvietnam.py` — 7 case + 2 fixture thật.
- Tên config = `thoibaotaichinhvietnam` (khớp host stem) để né bẫy `.vn`-suffix
  ở `scripts/domain_check.py:152`.

**🔴 PHÁT HIỆN LỚN — RSS theo chuyên mục của TBTC là ẢO**

Kế hoạch ban đầu định cấu hình **9 feed chuyên mục** theo mẫu
`https://thoibaotaichinhvietnam.vn/{category}/rss_feed/`. Mẫu này trả HTTP 200 với
25 item nên trông có vẻ đúng. Verify sâu 2026-09-07 cho thấy **server BỎ QUA path
chuyên mục**:

| Kiểm chứng | Kết quả |
|---|---|
| 12 chuyên mục, so `<pubDate>` mới nhất/cũ nhất | **giống hệt nhau** (19:51:09 / 08:56:27) |
| `chung-khoan` vs `thue-hai-quan` vs `bat-dong-san` vs root — 3 title đầu | **giống hệt nhau** |
| channel `<link>` của cả 4 | đều là `.../trang-chu` |

→ Cấu hình 9 feed sẽ **fetch trùng 9 lần** cùng một nội dung và gắn **nhãn chuyên mục SAI**
(mỗi bài bị dán tên feed mà nó không thuộc về).

**Quyết định:** chỉ dùng **1 feed** `/rss_feed/`. Lấy chuyên mục THẬT từ
`<meta property="article:section">` trên trang detail.

**Hệ quả code:** thêm tuỳ chọn generic `detail.category_meta` vào `RssCaptureScraper`
(phase-01), ~20 dòng, config-driven, tắt mặc định. Đây là **sai lệch có chủ ý** so với
tiêu chí "zero new Python" (S2) của phase-02 — lý do: nếu không có nó, `categories`
của mọi bài TBTC sẽ là "TBTC Tin mới", tức mất hoàn toàn tín hiệu chuyên mục.
Kế hoạch đã dự liệu đúng dạng thay đổi này ("that is a phase-01 change, not a fork here").

**Verified live 2026-09-07**
- Feed `/rss_feed/`: 200, **25 item**, CÓ `content:encoded` full body.
- Volume: 25 item trải ~11 giờ → **~50 bài/ngày**. `max_details_per_cycle: 40` dư sức.
- `{category}.rss` → 404. `/rss_feed/{category}` và `/{category}/rss_feed/` → 200 (nhưng trùng).
- Detail: body `div.article-detail-main`, `article:published_time` = `2026-09-07T19:51:09+07:00`
  (ISO + offset chuẩn), `article:section` = "Chính sách tài chính",
  `category_url` meta trỏ về URL chuyên mục.
- robots: `Allow: /` + Disallow `/tag/ /article/ *.pdf *.xls ...`. Bài chi tiết ở ROOT
  `/<slug>-<id>.html` → không bị chặn. **Không fetch attachment PDF/XLS.**
- Nội dung khớp mục tiêu: bài đầu feed hôm nay là "Infographics 8 tháng giải ngân vốn
  đầu tư công cả nước đạt 509.557,5 tỷ đồng" → đúng beat đầu tư công.

**Vai trò:** nguồn **proxy KTXH/đầu tư công chính** trong lúc NSO (`nso.gov.vn`) bị chặn
network (xem phase-05).
