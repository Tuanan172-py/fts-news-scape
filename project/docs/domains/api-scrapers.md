# Domains — API scrapers (cafef, fireant, tnck, vndirect)

Cập nhật: 2026-07-26 · 4 nguồn JSON có code riêng. Verify: cafef/tnck/fireant 2026-07-24,
vndirect 2026-07-25.

## Bảng so sánh

| | cafef | tnck | vndirect | fireant |
|---|---|---|---|---|
| Endpoint | cafef.vn/du-lieu/Ajax/PageNew/News.ashx | api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html | api-finfo.vndirect.com.vn/v4/news | restv2.fireant.vn/posts → /post/{id} |
| Auth | không | không | không | **Bearer token** |
| Bước | 2 (list→detail) | 2 (list→detail) | 1 (inline) | 2 (list→detail) |
| Driven by | watchlist symbols | zone × page | 1 call/trang | watchlist symbols |
| Cap detail | 30 | 40 | 20 | 30 |
| Self-disable | – | – | – | ✅ 401/403 |

---

## cafef — `config/domains/cafef.yaml` (`src/scrapers/cafef.py`)

- **List:** `GET News.ashx` params `Newstype=0, PageIndex=1, PageSize=20, Type=1` + `symbol`
  (lowercase) inject theo từng mã watchlist. Cần `Referer: https://cafef.vn/` + browser UA.
- **Detail:** BeautifulSoup lxml, `content_selector: div#mainContent`; miss → dùng full page + warn.
- **Quirk:**
  - **`Type=1` BẮT BUỘC** — `Type=2` trả `{"Success":false,"Message":"loại tin khoán trống"}` (rỗng).
  - Date `/Date(1784543714000)/` (ms epoch, đôi khi `+0700`) → `parse_cafef_date`: lấy ms, **bỏ tz
    offset**, dựng theo `VN_TZ`.
  - `LinkDetail` relative + utm → join `https://cafef.vn`. `Symbol`/`NewsId` thường null.
  - Chi phí: 30 mã × 3s ≈ 90s pha list mỗi cycle.

## fireant — `fireant.yaml` ✅ enabled 2026-09-07 (`method: fireant`, API + Bronze **JSON**)

- **Endpoint:** `GET https://restv2.fireant.vn/posts?symbol={S}&type=1&offset=0&limit=20`
  → detail `GET /posts/{id}` (**SỐ NHIỀU**; `/post/{id}` số ít → 404).
- **Auth:** Bearer token từ `config/secrets.yaml` → `fireant_token`. Thiếu/hết hạn →
  scraper **self-disable** trong cycle + ERROR log. **Không ghi Bronze** cho response 401/403.
- **⚠️ Bronze là JSON, không phải HTML.** `fireant.vn/dashboard/content/{id}` là Next.js SPA,
  body bài không có trong HTTP GET → capture **response API** (byte-exact).
  KHÔNG dùng `_capture_and_extract` (chạy CSS selector → báo `partial` oan).
  `SilverBuilder` thấy `Content-Type: application/json` thì bóc trường HTML trước khi trích.
- **Field là camelCase:** `postID`, `postSource`, `postSourceUrl`. Bản cũ đọc `post_source`
  snake_case nên `source_name` LUÔN rỗng — **sửa 2026-09-07**.
- **Permalink** đúng: `/dashboard/content/{id}`. `/bai-viet/{id}` → **404** — sửa 2026-09-07.
- List trả `content` **rỗng** → bắt buộc gọi detail (`content` ~3.7k HTML).
- `date` đã ISO `+07:00`. `taggedSymbols` **gắn sẵn mã CK** → không cần `tag_tickers`.
- Volume: 30 mã × 20 = 600 item/cycle (verified: fetched=600, 493 new, 0 lỗi).
- **⚠️ TUÂN THỦ:** robots của fireant.vn chặn ClaudeBot/GPTBot/CCBot/Google-Extended và khai
  `Content-Signal: ai-train=no, use=reference`. Ta đi qua API đã xác thực bằng token người
  dùng (restv2 không có robots) → chịu **ToS tài khoản**. **Tuyệt đối không dùng để train model.**
  Chi tiết + việc cần owner xác nhận: [`domains/fireant/README.md`](../../domains/fireant/README.md).

## tnck — `tnck.yaml` ✅ enabled 2026-09-07 (`method: tnck`, API + Bronze capture)

**Không có RSS** (verified 2026-09-07: `/rss.html` = 13 bytes; `/rss/*.rss` = 302). API zone là
route **duy nhất** — đừng probe lại.

- **Endpoint:** `GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html`
- **Zones (9):** `[1, 4, 6, 11, 21, 26, 29, 33, 39]` = Chứng khoán · Thông tin doanh nghiệp ·
  Tiền tệ · Trái phiếu · **Pháp luật** · **M&A** · **Đại hội cổ đông** · **Pháp đình** · Vĩ mô.
  `pages_per_cycle: 1` (40 item/zone; nhịp 15' thì page 2 gần như 100% trùng).
  ⚠️ **Zone 8 "Điều tra" bị loại** — nội dung lệch hình sự/tiêu dùng, không phải điều tra DN.
  Bảng zone đầy đủ 1..45: `domains/tnck/schema.yaml`.
- **Headers:** browser UA + `Referer: https://www.tinnhanhchungkhoan.vn/` + `Accept: application/json`.
  Response gzip, `data.contents[]`.
- **`date` = epoch GIÂY, JSON NUMBER** (tài liệu cũ ghi "string" — **SAI**, sửa 2026-09-07).
- **`phrase` param bị server IGNORE** → tag ticker client-side.
- **`source_domain` = NON-WWW** `tinnhanhchungkhoan.vn`; `article.url` giữ host `www.`
  (đổi URL = đổi `url_title_hash` = đổi định danh bài).
  → `verify_quality.py tinnhanhchungkhoan.vn` (HOST), `domain_check.py --report tnck` (tên config).
- **robots:** www Disallow `/api/`, nhưng `api.tinnhanhchungkhoan.vn` là **host khác**
  (robots riêng, rỗng). Bài `/<slug>-post<NNN>.html` được phép. Không khai Crawl-delay.
- **Detail:** server-rendered, body `div.article__body.cms-body`.
  ⚠️ Quảng cáo `div[id^=adsWeb_]` nằm **bên trong** body → strip ở Silver, không đụng Bronze.
- Chi tiết: [`domains/tnck/README.md`](../../domains/tnck/README.md).

## vndirect — `config/domains/vndirect.yaml` (`src/scrapers/vndirect.py`)

- **Endpoint:** `api-finfo.vndirect.com.vn/v4/news?size=60&sort=newsDate:desc`. `news_groups` rỗng =
  tất cả; có thì thành `q=newsGroup:...`.
- **Quirk:**
  - Public JSON, **không auth** (web dstock thì Cloudflare 403, API thì không).
  - **AGGREGATOR:** `newsSource` = báo gốc, `newsUrl` = link gốc → tin trùng nguồn khác chỉ khử ở
    **fuzzy dedup cross-domain**.
  - **1-step:** full content nhúng sẵn trong list (`newsContent`). `enrich`: nếu `content_text ≥ 200`
    ký tự → dùng luôn; else fetch bài gốc qua trafilatura (cap 20; đếm cả attempt fail).
  - published = `{date}T{time}+07:00`; symbols từ `tagCodes` split comma upper.

## Ghi chú chung

- Chỉ **fireant** có `disabled`/self-disable. cafef/tnck/vndirect không — lỗi chỉ vào `errors[]`.
- cafef/fireant **quét theo watchlist** → chi phí tỉ lệ số mã. Muốn giảm tải: bớt watchlist.
- Mọi date chuẩn hoá về `Asia/Ho_Chi_Minh` bất kể định dạng nguồn.
