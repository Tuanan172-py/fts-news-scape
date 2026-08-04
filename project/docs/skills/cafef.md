# Domain Skill: CafeF (cafef.vn)

Verified live: 2026-07-24.

| Thành phần | Chi tiết |
|-----------|---------|
| **Domain** | cafef.vn |
| **Method** | REST API (internal, reverse-engineered) |
| **Endpoint** | `GET https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx` |
| **Headers** | `User-Agent` (browser) + `Referer: https://cafef.vn/` — thiếu → rỗng/403 |
| **Params** | `symbol` (lowercase), `Newstype=0`, `PageIndex`, `PageSize` (max 200, dùng 100), **`Type=1` bắt buộc** — `Type=2` → `{"Success":false,"Message":"loại tin khoán trống"}` |
| **Response** | `{"Data": [...], "Success": ...}` — fields: `Title`, `SubTitle`, `NewsType`, `Image`, `DeployDate`, `LinkDetail` (`Symbol`/`NewsId` thường null) |
| **Date format** | `/Date(1784543714000)/` — ms epoch (đôi khi kèm `+0700`) → `parse_cafef_date()` |
| **Detail URL** | `LinkDetail` relative (`/du-lieu/...chn?utm_source=du-lieu`) → join `https://cafef.vn` |
| **Content** | `div#mainContent` trên trang detail — lưu nguyên bản vào `content_html`; trafilatura → `content_text` |
| **Pitfalls** | List pages load JS động → không parse HTML tĩnh được. Rate ≥3s. Selector miss → fallback full-page + WARN |

## Sample call

```bash
curl --compressed -H "User-Agent: Mozilla/5.0 ..." -H "Referer: https://cafef.vn/" \
  "https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx?symbol=fpt&Newstype=0&PageIndex=1&PageSize=5&Type=1"
```

## Behavior notes

- Watchlist-driven: 1 request / symbol / cycle. 30 symbols × 3s ≈ 90s list phase.
- Detail fetch cap `max_details_per_cycle: 30`; vượt cap → article giữ summary, `metadata.detail_deferred=true`.
- 1 symbol fail không dừng cycle (lỗi gom vào `ScrapeResult.errors`).
