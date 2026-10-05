# Domain Skill: TNCK / ĐTCK (tinnhanhchungkhoan.vn)

Verified live: **2026-09-07** (cập nhật lớn — xem phase-03).

> ⚠️ **Sửa sai tài liệu:** bản trước ghi `date` là "epoch giây, **string**". Sai —
> API trả **JSON NUMBER**. `int()` nhận cả hai nên không có bug thực tế, nhưng đừng
> viết code giả định string.
>
> ⚠️ **KHÔNG CÓ RSS** (verified 2026-09-07): `/rss.html` = 200 nhưng **13 bytes**;
> `/rss/trang-chu.rss`, `/chung-khoan.rss`, `/rss/chung-khoan.rss` = **302 + 0 byte**.
> API zone là route DUY NHẤT — đừng probe lại.
>
> ⚠️ **`source_domain` = NON-WWW `tinnhanhchungkhoan.vn`**, khác tên config `tnck`.
> Dùng `resolve_source_domain()`; `verify_quality.py` nhận **HOST**, `domain_check.py` nhận **tên config**.

| Thành phần | Chi tiết |
|-----------|---------|
| **Domain** | tinnhanhchungkhoan.vn (Đầu tư Chứng khoán) |
| **Method** | REST API (internal, zone-based) |
| **Endpoint** | `GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html` |
| **Zones** | **9 zone đang bật**: `[1, 4, 6, 11, 21, 26, 29, 33, 39]`. Bảng đầy đủ 1..45 (quét live 2026-09-07): `domains/tnck/schema.yaml` → `zones.map`. ⚠️ Zone 8 "Điều tra" bị LOẠI — nội dung lệch hình sự/tiêu dùng, không phải điều tra DN |
| **Headers** | UA browser + `Referer: https://www.tinnhanhchungkhoan.vn/` + `Accept: application/json` |
| **Response** | gzip (requests tự decompress). `data.contents[]` — 40 items/page |
| **Fields** | `content_id`, `title`, `description`, `date` (epoch giây, string), `update_time`, `url` (relative), `zone` (dict: `name`), `avatar_url` |
| **Date** | epoch seconds (**NUMBER**) → `datetime.fromtimestamp(int(date), tz=VN_TZ)` |
| **⚠️ Pitfall chính** | **`phrase` param BỊ IGNORE** (verified: `phrase=HPG` trả zone content y hệt) — KHÔNG dùng để filter ticker. Ticker tagging client-side qua `core/tickers.py` |
| **Content** | Detail fetch → **RawStore.save Bronze byte-exact TRƯỚC**, rồi `content_html = div.article__body`. ⚠️ Quảng cáo `div[id^=adsWeb_]` nằm BÊN TRONG body |

## Sample call

```bash
curl --compressed -H "User-Agent: Mozilla/5.0 ..." \
  -H "Referer: https://www.tinnhanhchungkhoan.vn/" -H "Accept: application/json" \
  "https://api.tinnhanhchungkhoan.vn/api/morenews-zone-4-1.html"
```

## Behavior notes

- **1 page/cycle** (từ 2026-09-07; trước là 2). 9 zone × 40 = 360 item/cycle, phần lớn bị dedup chặn.
- Detail cap **40**/cycle; vượt → `metadata.detail_deferred=true`, giữ description.
- Lưu ý field names KHÁC docs thamkhao cũ (không có `full_url`/`related_tickers`/`date_unix`).
