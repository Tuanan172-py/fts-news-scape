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

## fireant — `config/domains/fireant.yaml` (`src/scrapers/fireant.py`)

- **List:** `GET restv2.fireant.vn/posts?symbol={S}&type=1&offset=0&limit=20` (theo watchlist).
  **Detail:** `GET restv2.fireant.vn/post/{post_id}` (field `content` = full HTML). Web URL bài =
  `fireant.vn/bai-viet/{post_id}`.
- **Auth:** `type: bearer`, `secret_key: fireant_token` trong `config/secrets.yaml` (gitignored).
- **Quirk / bẫy đã xử:**
  - **Strip "Bearer " prefix:** nếu token dán kèm `"Bearer "` → cắt để không thành `Bearer Bearer …`
    (`fireant.py:40-41`). Token `PASTE_*` hoặc rỗng → `disabled` ngay từ constructor (WARN, không crash).
  - **Self-disable 401/403:** `get_response` đọc status; 401/403 → `_auth_failed` set `disabled`,
    ERROR log 1 lần, **break** khỏi loop watchlist (không hammer). Áp cho cả list và detail.
  - List trả `content` RỖNG → bắt buộc gọi detail. `date` đã ISO `+07:00`. symbols từ `taggedSymbols[].symbol`.
  - Token có thể hết hạn → cập nhật thủ công secrets.yaml. Hướng dẫn lấy token: [../skills/fireant.md](../skills/fireant.md).

## tnck — `config/domains/tnck.yaml` (`src/scrapers/tnck.py`)

- **Endpoint:** `.../morenews-zone-{zone}-{page}.html`; config `zones: [4]` (Thông tin doanh nghiệp),
  `pages_per_cycle: 2` (~40 item/page → 80), cap detail 40. `Referer: www.tinnhanhchungkhoan.vn/`.
- **Quirk:**
  - **`phrase` param bị server IGNORE** (verify: `phrase=HPG` trả zone content y hệt) → **không dùng**
    để filter mã; tag ticker **client-side** qua `core/tickers.py`.
  - Response **gzip** (requests auto-decompress). Data path `data["data"]["contents"]`.
  - `date` = epoch **giây** (string) → `fromtimestamp(int, VN_TZ)`. `url` relative → `urljoin(BASE)`.
  - Field names KHÁC docs cũ (không có `full_url`/`related_tickers`).

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
