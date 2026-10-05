# Web Monocle — System Prompt cho Development Agent

## 1. Tổng quan dự án

**Tên:** Web Monocle
**Mục đích:** Hệ thống thu thập tin tức phục vụ phòng phân tích công ty chứng khoán — hỗ trợ ra quyết định giao dịch.

**Trạng thái phiên bản hiện tại:** MVP code skeleton (Phase 1 cơ bản). Cần research, phát triển mở rộng chuyên sâu.

**Thư mục làm việc:** `C:\Users\An Thanh Pham\Documents\web-monocle\` (trên Windows) — đây là bộ công cụ/dự án riêng, **không còn kết nối với Hermes bot nữa**.

---

## 2. Phạm vi tin tức (Scope)

### Types of news
Tất cả tin tức thuộc các lĩnh vực:
- **Cổ phiếu** — doanh nghiệp niêm yết, tin mã cổ phiếu cụ thể
- **Doanh nghiệp** — KQKD, governance, M&A, phát hành
- **Nhà nước** — chính sách, nghị định, thông tư, luật
- **Quốc tế** — kinh tế toàn cầu, Fed, giá hàng hoá
- **Vĩ mô** — GDP, CPI, lạm phát, lãi suất
- **Chính trị** — địa chính trị, bầu cử, quan hệ quốc tế

→ Tất cả trong phạm vi **hỗ trợ phân tích đầu tư chứng khoán**, dùng cho tổng thể **phòng phân tích công ty chứng khoán**.

### Đối tượng
Tập trung vào **cổ phiếu và thị trường** — bao gồm tất cả thông tin về cổ phiếu, thị trường để hỗ trợ giao dịch.

---

## 3. Mục tiêu cốt lõi của Phase hiện tại

**Mở rộng số lượng tin tức (scale coverage) — không chỉ depth trên 1 domain.**

Mục tiêu là xây dựng **hệ thống scraping chuyên nghiệp** với các chỉ số:
- **Ổn định:** Scraper không chết khi domain thay đổi layout nhỏ. Graceful degradation: fallback method khi primary fail. Tự động retry + alert.
- **Chất lượng:** Content sạch, đúng, đầy đủ. Dedup chính xác. HTML raw được bảo toàn. Date parse đúng format.
- **Số lượng:** Nhiều nguồn tin (domains), không chỉ 1-2. Tin tức về nhiều mã cổ phiếu, nhiều lĩnh vực, nhiều loại sự kiện.
- **Cấp độ chuyên nghiệp:** Có monitoring (ai đó biết khi scraper chết), có logging đầy đủ, có cấu trúc mở rộng được, có test.

---

## 4. Yêu cầu: Research & Phát triển nguồn tin đa dạng

### 4.1 Mở rộng nguồn (Domain → Skills thực thi)

**Mỗi domain mới = 1 skill scraper riêng**, được research kỹ lưỡng trước khi implement.

| Layer | Loại nguồn | Ví dụ | Phương thức khai thác |
|-------|-----------|-------|---------------------|
| **Layer 0** | Chính thống | HOSE, HNX, UPCoM, SSC, CBTT | RSS/API (nếu có) |
| **Layer 1** | Báo chí chuyên ngành | CafeF, VnExpress Kinh doanh, NDH, Vietstock, TNCK, Đầu tư, ĐTCK | **API reverse (ưu tiên)** > RSS > HTML |
| **Layer 2** | CTCK | SSI Research, HSC, VNDirect, MBS, VCSC | RSS (nếu có) > HTML |
| **Layer 3** | Tổng hợp | FireAnt, Cophieu68, StockCharts, TradingView | API (cần auth) > RSS |
| **Layer 4** | Nghiên cứu | Scribd, ResearchAndMarkets, báo cáo CTCK | HTML (thường cần login) |
| **Layer 5** | Cộng đồng | Facebook Groups, Telegram channels, X/Twitter | API chính thống > scrape |

**Tham khảo:** file `thamkhao/present/Nguồn tin.md` — phân tích chi tiết 6 layers này.

### 4.2 Quy trình Research 1 domain mới

1. **Xác định nguồn** — URL, loại nội dung, tần suất cập nhật
2. **Kiểm tra RSS** — có RSS feed không? URL feed là gì?
3. **Reverse API** — dùng DevTools (F12) → Network → Fetch/XHR → tìm endpoint JSON
4. **Phân tích API response** — cấu trúc JSON, auth cần không, rate limit?
5. **Fallback HTML** — nếu không có API/RSS → phân tích selectors (CSS/XPath)
6. **Xác định pitfalls** — date format đặc biệt? anti-bot? encoding?
7. **Viết skill scraper** — config YAML + module code
8. **Viết test** — happy path + edge cases

### 4.3 Yêu cầu kỹ thuật: Ổn định, Chất lượng, Số lượng

| Tiêu chí | Yêu cầu | Measure |
|----------|---------|---------|
| **Ổn định** | Primary method fail → fallback method tự động. Retry 3 lần trước khi bỏ cuộc. Graceful degradation — không crash pipeline | ≥ 99.5% uptime per scraper (trừ lỗi network) |
| **Chất lượng** | Content sạch (không nav, không ads, không JS). HTML raw bảo toàn. Text extract chính xác. Date parse đúng timezone VN | ≥ 95% articles có đủ title + body + date |
| **Số lượng** | Nhiều domain, mỗi domain nhiều articles/cycle. Coverage đa ticker, đa ngành | Mục tiêu: ≥ 500 articles/ngày từ ≥ 5 domains |
| **Chuyên nghiệp** | Logging đầy đủ (INFO, WARN, ERROR). Monitoring: biết ngay khi scraper fail. Cấu trúc modular để thêm domain mới trong 30 phút | Mỗi scraper có module riêng, không hardcode domain logic vào orchestrator |

---

## 5. Research Workflow & Framework phù hợp

### 5.1 Yêu cầu: research các framework/workflow hiện có

Cần research và đánh giá:

| Framework | Cân nhắc cho dự án? | Lý do |
|-----------|-------------------|-------|
| **Scrapy** | Cần research | Framework crawl mạnh, async, middleware, pipeline. Nhưng learning curve, có thể overkill cho single-machine |
| **BeautifulSoup + requests** | Đang dùng | Đơn giản, dễ maintain. Phù hợp phase này. Nhưng không async, crawl chậm khi nhiều domain |
| **Playwright** | Cần research | Cho JS-rendered content. Cần không? Bao nhiêu % domain cần? |
| **Selenium** | Cần research | Nặng hơn Playwright, nhưng support rộng. Cân nhắc trade-off |
| **Feedparser** | Đang dùng | Tốt cho RSS. Không cần thay |
| **Newspaper3k / NewsPlease** | Cần research | Framework extract article chuyên biệt. So với trafilatura (đang dùng) cái nào tốt hơn cho tiếng Việt? |
| **Apache Airflow / Prefect** | Cần research | Orchestration workflow. Cần không ở phase này? Hay chỉ cần cron đơn giản? |
| **APScheduler** | Cần research | Python scheduler nhẹ, thay thế được cron. Linh hoạt hơn |
| **pandas / Polars** | Cần research | Xử lý dữ liệu articles sau khi collect. Polars nhanh hơn pandas |

### 5.2 Research questions cần trả lời

1. **Async scraping có cần thiết?** — Với 5-10 domains, mỗi domain rate-limit 3s, tổng thời gian 1 cycle có thể > 60s. Cần async (aiohttp) không?
2. **Framework nào giúp add domain mới nhanh nhất?** — Mục tiêu: domain mới chỉ cần config YAML + 1 class kế thừa base scraper
3. **Cần caching layer không?** — Cache HTTP response để tránh request lại nếu cycle fail giữa chừng
4. **Xử lý concurrent writes vào SQLite?** — SQLite WAL mode có đủ cho 3-5 scraper chạy song song?
5. **Monitoring / Health check?** — Cần dashboard đơn giản để biết scraper nào đang chết? Hay chỉ cần log file?

### 5.3 Deliverable của research phase

Sau khi research, cần có:
1. **Bảng so sánh framework** — ưu/nhược điểm, phù hợp với use case
2. **Recommendation** — framework nào dùng cho phase này, framework nào để dành phase sau
3. **POC** — 1 domain mẫu implement với framework được chọn, so sánh với code skeleton hiện tại

---

## 6. Tần suất (Frequency)

- **Không cần stream real-time**
- Polling với tần suất hiện tại: **15 phút / lần** là OK
- Không yêu cầu push/WebSocket ở thời điểm này

---

## 7. Lưu trữ (Storage)

| Item | Chi tiết |
|------|---------|
| **Database** | **SQLite** (không ClickHouse ở phase này) |
| **Lý do** | Version hiện tại chỉ cần getting-start. SQLite đủ cho single-machine, không cần infrastructure phức tạp |
| **Lưu ý** | ClickHouse sẽ được xem xét ở phase sau nếu cần query analytics |

---

## 8. Phương thức thu thập (Methods) — Priority order

| Phương thức | Mô tả | Khi nào dùng |
|------------|-------|-------------|
| **RSS** | Feed chuẩn RSS 2.0/Atom | Ưu tiên số 1. Coverage rộng, setup nhanh |
| **REST API** | API internal reverse-engineered | Khi RSS không có hoặc không đủ. Đã research sẵn cho CafeF, FireAnt, Vietstock, TNCK |
| **HTML request** | HTTP request lấy HTML + parse | Khi không có API. Dùng BeautifulSoup/lxml |

**Tài nguyên tham khảo:** Thư mục `thamkhao/present/` chứa research chi tiết về:
- CafeF API: `docs_cafef/CafeF.md` — endpoint `https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx`
- FireAnt API: `docs_fireant/` — Bearer Token + endpoint `https://restv2.fireant.vn/posts`
- Vietstock API: `docs_vietstock/` — POST-based, channel-based, 15+ endpoints
- TNCK API: `docs_tnck/` — Zone-based + Phrase filter
- So sánh chi tiết: `Tổng hợp/So sánh.md` — phân tích 4 hệ thống

---

## 9. Xử lý dữ liệu (Processing Pipeline)

### Định dạng xử lý

```
HTML thô (raw, giữ tag) → Bóc tách nội dung → Lưu raw + text → Sentiment (rule-based)
```

### Cụ thể từng bước

| Step | Mô tả | Output |
|------|-------|--------|
| **1. Collect** | Fetch từ RSS/API/HTML | Raw content |
| **2. Parse** | Trích xuất title, body, date, author, metadata | Structured fields |
| **3. Store raw** | Lưu HTML nguyên bản (giữ tag, table, formatting) | `content_html` field |
| **4. Extract text** | Text thuần không tag | `content_text` field |
| **5. Dedup** | SHA-256 URL + title → tránh trùng | Skip nếu đã có |
| **6. Sentiment (TBD)** | **Rule-based** — phân loại sentiment tin tức tiếng Việt (positive/negative/neutral) | `sentiment` field |
| **7. Lưu** | SQLite | Article record |

### Sentiment — Yêu cầu đặc biệt

- **Chưa cần** LLM/NLP model phức tạp
- **Chỉ cần rule-based** — từ điển sentiment tiếng Việt (positive words, negative words, financial terms)
- Phase này ưu tiên làm tốt nhất có thể với rule engine, sau này mới nâng cấp lên LLM

---

## 10. Workflow per domain (Quan trọng)

**Nguyên tắc cốt lõi:** 1 domain = 1 bộ Skills & Rules riêng

### Cấu trúc domain

```
Mỗi domain có:
- Scraper skill: cách lấy dữ liệu (selectors, API endpoints, rate limit, headers)
- Processing rules: cách parse, extract, classify cho domain đó
- Domain-specific pitfalls: anti-bot, date format, encoding đặc thù
```

### Ví dụ — CafeF

| Thành phần | Chi tiết |
|-----------|---------|
| **Domain** | cafef.vn |
| **Method** | REST API (`/du-lieu/Ajax/PageNew/News.ashx`) |
| **Headers** | User-Agent + Referer |
| **Params** | symbol (lowercase), NewsType=0, pageIndex, pageSize (max 200) |
| **Date format** | `/Date(timestamp+timezone)/` — cần parse riêng |
| **Content** | HTML từ `div#mainContent` — lưu nguyên bản |
| **Pitfalls** | API trả dữ liệu động (JS load), không parse HTML tĩnh được |

### Mục tiêu
Verify và xác định chính xác nhiều domain, mỗi domain có skill fit phù hợp. Khi đã có skill cho 1 domain → có thể follow-up, xử lý đến cùng domain đó một cách tự động.

---

## 11. Kiến trúc tổng thể (Không Hermes dependency)

```
┌─────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR / SCHEDULER                 │
│  (cron / APScheduler) — điều phối tất cả collectors         │
│  Singleton: 1 cycle chạy xong mới chạy cycle tiếp           │
└────────────────────┬────────────────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐        ┌──────────────┐
    ▼                ▼                ▼        │  MONITORING  │
┌──────────┐  ┌────────────┐  ┌──────────────┐ │  (logs,      │
│ RSS       │  │ REST API   │  │ HTML Request │ │   health     │
│ Collector │  │ Collector  │  │ Collector    │ │   checks)    │
│ (generic) │  │ (per-domain)│  │ (per-domain) │ └──────────────┘
└─────┬─────┘  └──────┬─────┘  └──────┬───────┘
      │               │               │
      └───────────────┼───────────────┘
                      ▼
            ┌──────────────────┐
            │ PARSER / EXTRACT │
            │  (per domain)    │
            │  - title, body   │
            │  - date, author  │
            │  - content_html  │
            │  - content_text  │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │   DEDUP + CLASS  │
            │  (SHA-256 URL)   │
            │  (rule-based)    │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │  SENTIMENT ENGINE │
            │ (rule-based VN)   │
            │ pos/neg/neutral   │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │    SQLite DB      │
            │ (articles store)  │
            │ WAL mode cho      │
            │ concurrent writes │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │  NOTIFY MODULE   │
            │ (file-based log) │
            │ stdout + log file│
            └──────────────────┘
```

### Lưu ý kiến trúc
- **Không phụ thuộc Hermes** — đây là dự án standalone
- **Module notify hiện tại chỉ cần log ra file/stdout** — chưa cần kết nối trực tiếp Telegram
- **Hub có thể gọi LLM ở phase sau** — nhưng hiện tại ưu tiên rule-based sentiment cho tiếng Việt
- **Thiết kế để mở rộng:** thêm domain mới = thêm 1 file scraper + 1 config entry. Không sửa orchestrator

---

## 12. Ràng buộc (Constraints)

### Kỹ thuật
- Python 3.10+, single-machine (Windows + WSL)
- SQLite là DB duy nhất (không ClickHouse, không PostgreSQL, không Elasticsearch)
- Rate limiting bắt buộc (≥ 3s delay giữa requests đến cùng domain)
- Timeout ≤ 30s cho mọi external request
- Graceful shutdown — không corrupt DB khi bị kill
- WAL mode cho SQLite để hỗ trợ concurrent writes an toàn

### Dữ liệu
- Lưu HTML nguyên bản (raw) trước khi xử lý — không throw away data
- Dedup bắt buộc (SHA-256 URL + title)
- Sentiment: rule-based, từ điển tiếng Việt, chưa cần LLM

### Phát triển
- **Config-driven:** thêm domain = thêm config YAML + module code mới, không sửa core
- **Test trước khi deploy:** happy path + 1 edge case per module
- **Documentation song song:** mỗi feature xong → cập nhật docs
- **Incremental delivery:** mỗi phase là 1 working system
- **1 domain mới / sprint:** mỗi sprint research + implement 1 domain hoàn chỉnh

---

## 13. Plan phát triển chi tiết

### Sprint 1: Nền tảng + CafeF
- [ ] Refactor code skeleton: base classes cho scraper, parser, store
- [ ] Implement scraper CafeF (API có sẵn)
- [ ] Implement domain skill cho CafeF
- [ ] Test 100 articles từ CafeF, verify quality

### Sprint 2: Mở rộng nguồn
- [ ] Research framework recommendation (Scrapy vs requests vs aiohttp vs ...)
- [ ] Implement scraper Vietstock (POST API)
- [ ] Implement scraper TNCK (Zone-based API)
- [ ] Implement scraper FireAnt (Bearer Token)
- [ ] Per-domain skills cho từng nguồn

### Sprint 3: Chất lượng xử lý
- [ ] Rule-based sentiment tiếng Việt (từ điển positive/negative)
- [ ] Dedup hoàn chỉnh (URL hash + title fuzzy match)
- [ ] Monitoring / health check module
- [ ] Error handling & retry strategy hoàn chỉnh

### Sprint 4: RSS Layer 0-1
- [ ] RSS collector cho VnExpress Kinh doanh, NDH, Đầu tư, ĐTCK
- [ ] Generic RSS → article extractor (trafilatura)
- [ ] VnExpress selector refinement (nếu RSS summary không đủ)

### Sprint 5: Hoàn thiện Phase 1
- [ ] Integrate tất cả collectors vào orchestrator
- [ ] End-to-end test: 24h chạy liên tục
- [ ] Performance tuning: async hay sequential? Batch size? Rate limit profiling
- [ ] Documentation tổng kết Phase 1

---

## 14. Tài liệu tham khảo có sẵn

Trong thư mục `thamkhao/present/` (không xoá, đây là research assets):

| File | Nội dung |
|------|---------|
| `Bối cảnh hiện tại.md` | Hiện trạng module tin tức cũ (Vietstock-only) |
| `Nguồn tin.md` | 6 layers nguồn tin: chính thống → báo chí → CTCK → tổng hợp → nghiên cứu → cộng đồng |
| `Phương pháp xử lý.md` | HTML parsing, API reverse engineering, workflow |
| `Tầm nhìn mục tiêu.md` | Short-term (mở rộng nguồn) → Medium-term (phân loại + sentiment) → Long-term (dashboard) |
| `Kết luận.md` | Đạt được / chưa đạt được |
| `docs_cafef/CafeF.md` | CafeF API endpoint chi tiết |
| `docs_cafef/OUTPUT_STRUCTURE.md` | CafeF output schema 100% raw |
| `docs_vietstock/` | Vietstock API research (15+ endpoints) |
| `docs_fireant/` | FireAnt API (Bearer Token) |
| `docs_tnck/` | TNCK API (Zone-based) |
| `Tổng hợp/So sánh.md` | So sánh chi tiết 4 hệ thống (1018 lines) |

---

## 15. Priority task list

- [ ] Research: so sánh Scrapy vs requests-asyncio vs aiohttp cho use case
- [ ] Research: Newspaper3k vs trafilatura cho tiếng Việt
- [ ] Research: APScheduler vs Windows Task Scheduler vs WSL cron
- [ ] Research: SQLite WAL mode concurrency handling
- [ ] Implement: BaseScraper abstract class (template method pattern)
- [ ] Implement: CafeF scraper (API-first)
- [ ] Implement: CafeF domain skill
- [ ] Implement: Vietstock scraper (POST API)
- [ ] Implement: TNCK scraper (Zone-based API)
- [ ] Implement: FireAnt scraper (Bearer Token)
- [ ] Implement: Rule-based sentiment engine cho tiếng Việt
- [ ] Implement: Logging & monitoring module
- [ ] Implement: Notify module (file-based)
- [ ] Implement: RSS collector cho VnExpress, NDH, Đầu tư
- [ ] Implement: Generic article extractor (trafilatura + fallback)
- [ ] Implement: End-to-end orchestrator với scheduling
- [ ] Test: 24h stability test with all domains
- [ ] Doc: Sprint 1-5 documentation
