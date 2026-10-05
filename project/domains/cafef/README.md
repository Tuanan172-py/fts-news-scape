# Domain Mastery — CafeF (cafef.vn)

Tài liệu toàn diện về nguồn CafeF: cấu trúc dữ liệu, data flow, field mapping, pitfalls, và quy trình bảo trì.

---

## 1. Tổng quan

| Thuộc tính | Giá trị |
|-----------|--------|
| **Domain** | cafef.vn |
| **Phương thức** | Internal JSON API |
| **Endpoint** | `https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx` |
| **Auth** | Không cần token, chỉ cần `Referer: https://cafef.vn/` |
| **Scraper class** | `CafeFScraper` (`src/scrapers/cafef.py`) |
| **Schema contract** | `domains/cafef/schema.yaml` |

## 2. Cơ chế lấy dữ liệu

CafeF scraper hoạt động theo **vòng lặp symbol** — duyệt qua từng mã cổ phiếu trong watchlist:

```
watchlist.yaml → [FPT, HPG, VNM, VIC, GAS, ...]
    ↓ (per symbol, tuần tự, rate_limit 3s)
GET https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx
    ?Newstype=0&PageIndex=1&PageSize=20&Type=1&symbol={symbol_lower}
    ↓
JSON response → parse → Article
    ↓
enrich: GET article.url → div#mainContent → trafilatura → content_text
```

- **32 tickers** × **20 items/symbol** = tối đa 640 raw items/cycle
- **Detail cap**: 30 bài enrich/cycle, bài vượt cap → deferred (summary only)
- **Không paginate**: chỉ lấy `PageIndex=1`, steady-state 15 phút đủ phủ

## 3. Cấu trúc API Response

```json
{
  "Data": [
    {
      "Symbol": null,
      "Title": "FPT: Giấy chứng nhận đăng ký doanh nghiệp...",
      "NewsId": null,
      "SubTitle": "",
      "NewsType": 0,
      "Image": "https://cafef1.mediacdn.vn/Images/Icons/News_image_default.png",
      "DeployDate": "/Date(1784543714000)/",
      "LinkDetail": "/du-lieu/FPT-2933792/fpt-giay-chung-nhan...chn?utm_source=du-lieu"
    }
  ],
  "Success": true,
  "Message": null
}
```

| Field | Kiểu | Bắt buộc | Ghi chú |
|-------|------|----------|---------|
| `Title` | string | CÓ | Tiêu đề, dùng `.strip()` |
| `SubTitle` | string | Không | Có thể rỗng "" |
| `DeployDate` | string | CÓ | `/Date(ms[+tz])/`, parse bằng `parse_cafef_date()` |
| `LinkDetail` | string | CÓ | Relative path, `urljoin("https://cafef.vn", ...)` |
| `NewsType` | int | Không | 0=default, 1=?, 2=rỗng |
| `Image` | string | Không | URL ảnh, lưu vào `metadata` |
| `Symbol` | null | Không | Luôn null (dùng symbol từ watchlist injection) |
| `NewsId` | null | Không | Luôn null |

### Date format

```
/Date(1784543714000)/          → 2026-07-20T00:01:54+07:00
/Date(1784543714000+0700)/     → 2026-07-20T00:01:54+07:00 (có thể có tz offset)
```

Regex: `r"/Date\((\d+)(?:[+-]\d{4})?\)/"` — lấy epoch ms, convert về VN_TZ.

## 4. Field Mapping: Raw API → Article

| API Field | Article Field | Transform |
|-----------|---------------|-----------|
| `Title` | `title` | `.strip()` |
| `LinkDetail` | `url` | `urljoin("https://cafef.vn", _)` |
| *hardcoded* | `source_domain` | `"cafef.vn"` |
| `SubTitle` | `summary` | `.strip()` |
| `DeployDate` | `published_at` | `parse_cafef_date()` → ISO 8601 `+07:00` |
| *injected* | `symbols` | `["FPT"]` (mã hiện tại từ vòng lặp) |
| *from detail* | `content_html` | `div#mainContent` inner HTML |
| *from detail* | `content_text` | trafilatura extract từ content_html |
| `Image` | `metadata["image"]` | URL string |
| `NewsType` | `metadata["news_type"]` | int |
| *classifier* | `categories` | Post-scrape rule-based |
| *sentiment* | `sentiment` | Post-scrape lexicon VN |

### Các field KHÔNG có từ CafeF

- `author` — không có trong API response, luôn `""`
- `categories` — không có trong API, được classifier thêm sau

## 5. Enrich (Detail Page)

```
GET {article.url}
  Headers: Referer: https://cafef.vn/
  ↓
BeautifulSoup → select_one("div#mainContent")
  ├── FOUND: content_html = str(node)
  │          content_text = extract_text(content_html)
  │                       → trafilatura(include_tables=True, no_fallback=False)
  │                       → fallback: BeautifulSoup get_text()
  └── NOT FOUND: WARNING log
                 content_html = full page HTML (fallback)
                 content_text = extract_text(full_page)

Fallback chain cho content_text:
  trafilatura(div) → trafilatura(wrapped) → BeautifulSoup.get_text() → summary
```

**Cap**: nếu `_details_fetched >= 30` → `content_text = summary`, đánh dấu `detail_deferred`.

## 6. Các điểm dễ vỡ (Watch Points)

| ID | Điểm | Rủi ro | Hậu quả |
|----|------|--------|---------|
| W1 | `DeployDate` format | Format `/Date(...)/` thay đổi | Toàn bộ `published_at` rỗng |
| W2 | `div#mainContent` | Selector bị đổi tên class/ID | Fallback full-page, chất lượng content_text giảm |
| W3 | API endpoint URL | URL thay đổi | Toàn bộ scraper không lấy được dữ liệu |
| W4 | `Type=1` requirement | Type=1 không còn hoạt động | `Success: false`, không có dữ liệu |
| W5 | `LinkDetail` format | Relative → absolute | urljoin vẫn hoạt động nhưng cần verify |

## 7. Error Handling

| Tình huống | Hành vi |
|-----------|---------|
| API trả `None` cho 1 symbol | Ghi error, tiếp tục symbol tiếp theo |
| API `Success: false` | Log warning với Message, bỏ qua symbol |
| Item thiếu `Title` hoặc `LinkDetail` | `parse_item` trả về `None`, bỏ qua |
| `DeployDate` parse fail | Warning log, `published_at = ""` |
| Detail page fetch fail | `content_text = summary`, ghi error |
| Detail cap (30) | Deferred, `content_text = summary` |
| Selector `div#mainContent` miss | Fallback full-page HTML |

## 8. Performance

| Metric | Giá trị |
|--------|---------|
| API calls/cycle | ~32 (mỗi symbol 1 call) |
| Detail fetches/cycle | ≤ 30 (cap) |
| Rate limit delay | 3s/request |
| Min cycle time | ~96s (chỉ API) |
| Typical cycle time | ~87s (steady-state, dedup skip detail) |
| Articles/cycle (typical) | 500–600 (first run) |

## 9. Quy trình bảo trì

### Khi nghi ngờ upstream thay đổi

```bash
# Kiểm tra nhanh raw response
python scripts/domain_check.py cafef --raw-check

# Chạy validate toàn bộ
python scripts/domain_check.py cafef --report

# Chạy diagnostic chuyên sâu
python scripts/diagnose_sources.py cafef
```

### Khi xác nhận thay đổi

1. Cập nhật `domains/cafef/schema.yaml` (field mới/thay đổi)
2. Cập nhật `domains/cafef/changelog.md` (ghi ngày + mô tả)
3. Sửa `src/scrapers/cafef.py` nếu parse logic thay đổi
4. Cập nhật fixture trong `tests/fixtures/` và `domains/cafef/fixtures/`
5. Chạy `python scripts/domain_check.py cafef` để verify
6. Chạy `python -m pytest tests/test_cafef.py -v` để verify regression

## 10. Liên kết

- Schema contract: `domains/cafef/schema.yaml`
- Changelog: `domains/cafef/changelog.md`
- Scraper code: `src/scrapers/cafef.py`
- Config: `config/domains/cafef.yaml`
- Tests: `tests/test_cafef.py`
- Fixtures: `tests/fixtures/cafef_list_response.json`, `tests/fixtures/cafef_detail_page.html`
