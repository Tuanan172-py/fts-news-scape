# Domain Skill: TNCK / ĐTCK (tinnhanhchungkhoan.vn)

Verified live: 2026-07-24.

| Thành phần | Chi tiết |
|-----------|---------|
| **Domain** | tinnhanhchungkhoan.vn (Đầu tư Chứng khoán) |
| **Method** | REST API (internal, zone-based) |
| **Endpoint** | `GET https://api.tinnhanhchungkhoan.vn/api/morenews-zone-{zone}-{page}.html` |
| **Zones** | 4 = Thông tin doanh nghiệp (mặc định). Khác: xem `thamkhao/present/docs_tnck/Khám phá parameter.md` |
| **Headers** | UA browser + `Referer: https://www.tinnhanhchungkhoan.vn/` + `Accept: application/json` |
| **Response** | gzip (requests tự decompress). `data.contents[]` — 40 items/page |
| **Fields** | `content_id`, `title`, `description`, `date` (epoch giây, string), `update_time`, `url` (relative), `zone` (dict: `name`), `avatar_url` |
| **Date** | epoch seconds → `datetime.fromtimestamp(int(date), tz=Asia/Ho_Chi_Minh)` |
| **⚠️ Pitfall chính** | **`phrase` param BỊ IGNORE** (verified: `phrase=HPG` trả zone content y hệt) — KHÔNG dùng để filter ticker. Ticker tagging client-side qua `core/tickers.py` |
| **Content** | Detail page fetch (`url` join base) → trafilatura raw HTML + text |

## Sample call

```bash
curl --compressed -H "User-Agent: Mozilla/5.0 ..." \
  -H "Referer: https://www.tinnhanhchungkhoan.vn/" -H "Accept: application/json" \
  "https://api.tinnhanhchungkhoan.vn/api/morenews-zone-4-1.html"
```

## Behavior notes

- 2 pages/cycle mặc định (80 items) — dedup skip bài cũ nên chỉ bài mới bị fetch detail.
- Detail cap 30/cycle; vượt → `metadata.detail_deferred=true`, giữ description.
- Lưu ý field names KHÁC docs thamkhao cũ (không có `full_url`/`related_tickers`/`date_unix`).
