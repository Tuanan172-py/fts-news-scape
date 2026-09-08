# Domain Mastery — TNCK / ĐTCK (tinnhanhchungkhoan.vn)

Báo **Đầu tư Chứng khoán** — cơ quan báo chí thuộc Uỷ ban Chứng khoán Nhà nước (UBCKNN).
Mạnh về **điều tra doanh nghiệp, tranh chấp cổ đông, pháp lý chứng khoán**.

---

## 1. Tổng quan

| Thuộc tính | Giá trị |
|-----------|--------|
| **Domain** | tinnhanhchungkhoan.vn (**non-www** trong `source_domain`) |
| **Phương thức** | Zone JSON API (list) + full raw HTML capture (detail) |
| **Scraper class** | `TnckScraper` (`src/scrapers/tnck.py`), registry key `tnck` |
| **Endpoint** | `GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html` |
| **Zones** | 9: `[1, 4, 6, 11, 21, 26, 29, 33, 39]` |
| **Volume** | 9 × 40 = **360 item/cycle** (phần lớn trùng, dedup lọc) |
| **Bronze** | `data/raw_html/tinnhanhchungkhoan.vn/<yyyymmdd>/` |
| **Trạng thái** | enabled 2026-09-07 (tắt 2026-08-03) |

## 2. ⚠️ KHÔNG CÓ RSS — đừng đi tìm

Verified 2026-09-07, đừng probe lại:

| URL | Kết quả |
|---|---|
| `/rss.html` | 200 nhưng **13 bytes** (rỗng) |
| `/rss/trang-chu.rss` · `/chung-khoan.rss` · `/rss/chung-khoan.rss` | **302, 0 byte** |

API zone là route **duy nhất**. Đây cũng là rủi ro lớn nhất của nguồn này
(watch point `tnck-w2`): API nội bộ, không hợp đồng công khai, mất là mất sạch.

## 3. Zone map (quét đầy đủ 1..45, 2026-09-07)

**Đang bật (9):**

| zone | Tên | Vì sao |
|---|---|---|
| 1 | Chứng khoán | thị trường lõi |
| 4 | Thông tin doanh nghiệp | công bố thông tin DN |
| 6 | Tiền tệ | lãi suất, tỷ giá, NHNN |
| 11 | Trái phiếu | TPDN — beat rủi ro cao |
| **21** | **Pháp luật** | ★ pháp lý chứng khoán |
| **26** | **Mua bán - Sáp nhập** | ★ M&A |
| **29** | **Đại hội cổ đông** | ★ tranh chấp cổ đông |
| **33** | **Pháp đình** | ★ kiện tụng, xét xử |
| 39 | Vĩ mô | chính sách |

**⚠️ Zone 8 "Điều tra" bị loại khỏi v1** — tên rất hợp beat nhưng nội dung thực tế lệch
sang **hình sự / tiêu dùng chung**, không phải điều tra doanh nghiệp. Mẫu 2026-09-07:
*"Bộ Công an: Huấn…"*, *"Fanpage tích xanh giả mạo cơ sở lưu trú"*, *"Bến thủy nội địa không phép"*.
Tín hiệu pháp lý DN thật nằm ở **21/33/26/29**. → hoãn, quyết lại sau 7 ngày đo thực tế.

**Hoãn:** 13 Nhận định · 36 Đầu tư · 43 Thương trường.
**Loại vĩnh viễn:** 27/45/32 (PR trả tiền) · 14 (item không có object `zone`) ·
16 (thông báo báo in VIR) · 10 (Tòa soạn, 3 item) · 15/18/19/20 (rỗng) ·
các zone trùng (12↔9, 24↔3, 34↔1, 35↔7, 38↔30, 42↔2).

Bảng đầy đủ: [`schema.yaml`](schema.yaml) → `zones.map`.

## 4. Quyết định `source_domain` — NON-WWW

- `source_domain` = **`tinnhanhchungkhoan.vn`** (không www) — khớp quy ước
  `removeprefix("www.")` dùng khắp repo (`rss_generic`, `vneconomy`, `silver_builder._domain_of`).
- `article.url` **GIỮ host `www.`** mà API trả về. **Không rewrite URL** —
  `url_title_hash = SHA-256(url + title)` là định danh bài; đổi URL = đổi định danh.
- Kiểm tra trước khi chốt: DB **không có row TNCK nào** → không rủi ro đứt dedup.

**Hệ quả vận hành:**
```bash
python scripts/verify_quality.py tinnhanhchungkhoan.vn   # HOST, không phải "tnck"
python scripts/domain_check.py --report tnck              # tên config
```

## 5. Bẫy `.vn`-suffix — đã sửa trong phase này

`scripts/domain_check.py` và `src/monitor/domain_reporter.py` từng làm
`f"{dom}.vn" if "." not in dom else dom` → `tnck` → **`tnck.vn`**, không khớp gì trong DB
→ report "0 articles" và anomaly giả.

Đã thay bằng `src.core.config.resolve_source_domain(name)`:
1. tên đã có dấu chấm → trả nguyên
2. `domains/<name>/schema.yaml` → `domain:`  ← **TNCK dùng nhánh này**
3. `config/domains/<name>.yaml` → `base_url` netloc
4. fallback legacy `<name>.vn`

Đây là lý do `domains/<name>/schema.yaml` là **bắt buộc** cho mọi nguồn.

## 6. Bẫy dữ liệu

| # | Bẫy | Xử lý |
|---|---|---|
| 1 | `date` là **JSON NUMBER** (epoch giây) — docs cũ ghi "string" là SAI | `int()` nhận cả hai; có test `test_epoch_number_and_string` |
| 2 | `url` relative | `urljoin(BASE_URL, url)` |
| 3 | `phrase` param **bị server ignore** (`phrase=HPG` trả y hệt zone content) | tag ticker client-side qua `core/tickers.py` |
| 4 | `Disallow: /api/` trên robots của **www** | `api.tinnhanhchungkhoan.vn` là **host khác**, robots riêng (rỗng). Bài `/<slug>-post<NNN>.html` được phép |
| 5 | Quảng cáo `div[id^=adsWeb_]` nằm **bên trong** `div.article__body` | lọt vào Silver `cleaned_text`. Strip ở Silver nếu nhiễu — **không đụng Bronze (WORM)** |

## 7. Selector map (detail, verified 2026-09-07)

| Thành phần | Selector |
|---|---|
| **Body** | `div.article__body` (`.article__body.cms-body`) |
| Sapo | `div.article__sapo.cms-desc` |
| Meta | `div.article__meta` · Tags `div.article__tag` |
| Ngày | `<meta property="article:published_time" content="2026-09-07T17:52:56+0700">` và `<time class="time" datetime="…" data-time="…">` |

## 8. Bảo trì

- `pages_per_cycle: 1` — 40 item/zone đủ cho nhịp 15'; page 2 gần như 100% trùng.
- 360 item/cycle nghe nhiều nhưng phần lớn bị dedup chặn; chi phí thật nằm ở
  `max_details_per_cycle: 40`.
- Sửa selector → **không cần re-scrape**:
  `python scripts/rederive_from_bronze.py tinnhanhchungkhoan.vn`.
- Rà soát compliance phải kiểm tra **CẢ HAI host** (www + api) — watch point `tnck-w5`.
- **Việc cần làm:** sau 7 ngày, đếm bài theo `metadata.zone_id`, đánh giá lại zone 8/13/36/43,
  ghi quyết định vào [`changelog.md`](changelog.md).
