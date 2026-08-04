# Domain Mastery — Vietstock (vietstock.vn)

Tài liệu toàn diện về nguồn Vietstock: cấu trúc dữ liệu, data flow, field mapping, pitfalls, và quy trình bảo trì.

---

## 1. Tổng quan

| Thuộc tính | Giá trị |
|-----------|--------|
| **Domain** | vietstock.vn |
| **Phương thức** | RSS 2.0 (4 feeds) |
| **Auth** | Public, không cần auth |
| **Scraper class** | `RSSScraper` (`src/scrapers/rss_generic.py`) |
| **Schema contract** | `domains/vietstock/schema.yaml` |
| **Config** | `config/domains/vietstock.yaml` |

## 2. Cơ chế lấy dữ liệu

Vietstock scraper dùng **multi-feed RSS** — parse tuần tự 4 RSS feeds:

```
config/domains/vietstock.yaml → 4 feed URLs:
  ├── https://vietstock.vn/0/tin-moi.rss             "Vietstock Tin mới"
  ├── https://vietstock.vn/144/chung-khoan.rss      "Vietstock Chứng khoán"
  ├── https://vietstock.vn/733/doanh-nghiep.rss     "Vietstock Doanh nghiệp"
  └── https://vietstock.vn/761/kinh-te/vi-mo.rss    "Vietstock Vĩ mô"
    ↓ (per feed, tuần tự, rate_limit 3s)
GET feed URL → raw bytes → _decode_feed() → feedparser.parse()
    ↓
RSS entries (link, title, description, author, pubDate)
    ↓ parse_item()
Article objects
    ↓
enrich: GET article.url → trafilatura extract_content() → content_text
```

- **4 feeds** × ~25 items/feed = ~100 raw items/cycle
- **Detail cap**: 30 bài enrich/cycle
- **Per-feed isolation**: nếu 1 feed chết, 3 feed còn lại vẫn chạy

## 3. Cấu trúc RSS Feed

### Raw XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Chung khoan - Vietstock RSS</title>
    <link>https://vietstock.vn/144/chung-khoan/</link>
    <description>Vietstock.vn</description>
    <item>
      <title>Khối ngoại mua ròng phiên thứ 5 liên tiếp</title>
      <link>https://vietstock.vn/2026/07/khoi-ngoai-mua-rong-phien-thu-5-lien-tiep-...</link>
      <description>&lt;img src="..." /&gt;Phiên 24/07, khối ngoại mua ròng...</description>
      <pubDate>Fri, 24 Jul 2026 14:54:34 +0700</pubDate>
      <guid>...</guid>
    </item>
  </channel>
</rss>
```

### Encoding Handling

`_decode_feed()` xử lý multi-stage:
1. UTF-16 BOM detection (`\xff\xfe` hoặc `\xfe\xff`)
2. Null bytes trong 400 byte đầu → UTF-16
3. Default: `utf-8-sig` với `errors="replace"`
4. Strip BOM, whitespace, và `encoding` attribute

### Field Mapping: RSS Entry → Article

| RSS Field | Article Field | Transform |
|-----------|---------------|-----------|
| `link` | `url` | `.strip()` |
| `title` | `title` | `_clean_title()`: strip HTML + unescape double-encoded entities |
| *urlparse* | `source_domain` | `urlparse(url).netloc.removeprefix("www.")` |
| `description` | `summary` | `extract_text()` via trafilatura (strip `<img>` tags) |
| `pubDate` | `published_at` | `_parse_entry_date()`: struct_time → UTC → VN_TZ → ISO |
| `author` | `author` | Direct |
| *tag_tickers* | `symbols` | Regex `\b[A-Z]{3}\b` ∩ watchlist |
| `_feed_name` | `categories` | `["Vietstock Chứng khoán"]` |
| *from detail* | `content_html` | Full page HTML |
| *from detail* | `content_text` | trafilatura `extract_content()` auto-detect |

### Date Parsing

Primary: `published_parsed` (feedparser struct_time, UTC-normalized)

Fallback `_parse_raw_date()`:
- `GMT+7` → `+0700`
- `+07` → `+0700` (two-digit tz, non-destructive)
- `7/25/2026 7:39:00 PM` (US format, narrow no-break space)
- No timezone → assume VN_TZ

### Title Cleaning

`_clean_title()`:
- Strip `<span>`, `<em>`, etc. HTML tags
- `html.unescape()` double-encoded entities (`&aacute;`, `&#225;`)

### Ticker Tagging

- Regex: `\b[A-Z]{3}\b` 3 uppercase letters
- Filter qua watchlist (uppercased)
- Stoplist: `GDP, CPI, PMI, FED, USD, EUR, JPY, CNY, VND, CEO, CFO, COO, HHD, ETF, IPO, ROE, ROA, EPS, HNX, OTC, GMT, UBC, TOD`

## 4. Enrich (Detail Page)

```
GET {article.url}
  ↓
trafilatura.extract_content(article.url, html=html)
  ├── result["raw_html"] → content_html (full page)
  └── result["content"]  → content_text
                          → fallback: summary
```

Không dùng CSS selector (trafilatura auto-detect main content).

**Cap**: nếu `_details_fetched >= 30` → deferred.

## 5. Các điểm dễ vỡ (Watch Points)

| ID | Điểm | Rủi ro | Hậu quả |
|----|------|--------|---------|
| W1 | RSS feed URL | 1 feed URL thay đổi | Feed đó chết, các feed khác vẫn chạy |
| W2 | pubDate format | Format thay đổi | Multiple fallback parsers, rủi ro thấp |
| W3 | description structure | Cấu trúc HTML thay đổi | extract_text vẫn hoạt động |
| W4 | title encoding | Entity encoding thay đổi | _clean_title() xử lý |
| W5 | feed encoding | Đổi encoding (UTF-16) | _decode_feed() multi-stage |
| W6 | trafilatura extraction | Không extract được | Fallback summary |

## 6. Error Handling

| Tình huống | Hành vi |
|-----------|---------|
| 1 feed URL lỗi network | Error record, tiếp tục feed tiếp theo |
| Feed XML không parse được | Error record, tiếp tục feed tiếp theo |
| Entry thiếu `link` hoặc title rỗng | `parse_item` → None, bỏ qua |
| pubDate parse fail | `published_at = ""` |
| Detail page fetch fail | `content_text = summary` |
| Detail cap (30) | Deferred |

## 7. Performance

| Metric | Giá trị |
|--------|---------|
| Feed HTTP calls/cycle | 4 (mỗi feed 1 call) |
| Detail fetches/cycle | ≤ 30 (cap) |
| Rate limit delay | 3s/request |
| Typical cycle time | ~12s (steady-state) |
| Articles/cycle (typical) | ~100 (first run) |

## 8. Quy trình bảo trì

### Khi nghi ngờ upstream thay đổi

```bash
# Kiểm tra nhanh raw response
python scripts/domain_check.py vietstock --raw-check

# Chạy validate toàn bộ
python scripts/domain_check.py vietstock --report

# Chạy diagnostic chuyên sâu
python scripts/diagnose_sources.py vietstock
```

### Khi xác nhận thay đổi

1. Cập nhật `domains/vietstock/schema.yaml` (feed URLs, fields mới)
2. Cập nhật `domains/vietstock/changelog.md` (ghi ngày + mô tả)
3. Sửa `src/scrapers/rss_generic.py` nếu parse logic thay đổi
4. Cập nhật fixture trong `tests/fixtures/` và `domains/vietstock/fixtures/`
5. Chạy `python scripts/domain_check.py vietstock` để verify
6. Chạy `python -m pytest tests/test_rss_scraper.py -v` để verify regression

## 9. Mở rộng trong tương lai

- RSS index tại `https://vietstock.vn/rss` liệt kê 60 feeds — có thể mở rộng thêm feeds khác
- Internal API (TopPageArticle...) cần browser session — có thể dùng làm fallback nếu cần

## 10. Liên kết

- Schema contract: `domains/vietstock/schema.yaml`
- Changelog: `domains/vietstock/changelog.md`
- Scraper code: `src/scrapers/rss_generic.py`
- Config: `config/domains/vietstock.yaml`
- Tests: `tests/test_rss_scraper.py`
- Fixture: `tests/fixtures/vietstock_feed.xml`
