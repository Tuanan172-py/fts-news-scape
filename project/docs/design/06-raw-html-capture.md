# Design 06 — RAW HTML Capture (Vietstock + CafeF)

Cập nhật: 2026-08-13 · Trạng thái: **ĐÃ TRIỂN KHAI + validate LIVE** · Đối tượng: dev/vận hành.

Tài liệu chuyên sâu về cơ chế thu thập **toàn bộ raw HTML nguyên bản** của từng bài
đăng CafeF/Vietstock, phục vụ pipeline xử lý (NLP/sentiment) phía sau. Đọc kèm:
[03-source-strategy](03-source-strategy.md), [dev/03-adding-a-source](../dev/03-adding-a-source.md),
kế hoạch gốc `plans/20260813-0736-raw-html-capture-vietstock-cafef/`.

---

## 1. Mục tiêu & phạm vi

Lấy và **lưu lại byte-exact** mã nguồn HTML của trang chi tiết bài viết TRƯỚC mọi bước
xử lý. Không dừng ở metadata (title/url/thời gian) — phải bảo toàn: heading các cấp,
sapo, đoạn văn, list, bảng, chú thích; **mọi `<img>`** (kể cả lazy-load) + URL/alt/
caption; video/iframe/embed; link nội bộ & ngoài; tác giả/thời gian/chuyên mục.
**Không** làm sạch/chuẩn hoá/bóc text/đổi định dạng ở giai đoạn này.

Hai nguồn đã xác minh **server-rendered** (body có sẵn trong HTTP GET, không cần JS) →
client `requests` hiện có đủ dùng; headless browser chỉ là fallback tuỳ chọn (§9).

### 1.1 Tiêu chí nghiệm thu (AC) → nơi đáp ứng

| AC | Yêu cầu | Đáp ứng bởi | Bằng chứng validate |
|----|---------|-------------|---------------------|
| AC1 | Xác định đúng URL nguồn | `capture.source_url`, layout thư mục | audit: url in ra đúng |
| AC2 | Full raw HTML, không preview | `RawStore.save` ghi `response.content` | sha256 match=True (112KB/388KB) |
| AC3 | Giữ trọn text/tag/ảnh/bảng/link | ghi nguyên bytes, không parse-lại | file byte-exact |
| AC4 | Nội dung động/lazy nếu thuộc bài | server-rendered + `_looks_complete` | images 11/41 có trong artifact |
| AC5 | Ảnh giữ định danh + URL | `images[]` manifest (read-only) | 11/41 URL CDN thật |
| AC6 | Raw lưu + kiểm tra độc lập | `.html` + `.meta.json` trên đĩa | mở file offline OK |
| AC7 | Không tóm tắt/loại tag/clean | ghi raw TRƯỚC mọi parse; artifact bất biến | order-spy test + sha256 |
| AC8 | Ghi rõ phần thiếu/nguyên nhân | `capture_status/missing/error` | test failed/partial branch |
| AC9 | Tôn trọng rate limit/robots/ToS | `RobotsGate` + rate limit + `SourceBackoff` | cafef 9.1s/2 bài (rate-limited) |

---

## 2. Kiến trúc tổng thể

Tận dụng pipeline template-method sẵn có (`BaseScraper.run()`:
`fetch_list → parse_item → dedup → enrich → mark_seen`). Điểm chèn = hook **`enrich()`**.

```
                 ┌─────────────────── enrich(article) ───────────────────┐
 RSS/API list →  │ 1. RobotsGate.allowed(url)?  ──no──► skipped_robots     │
 (fetch_list)    │ 2. crawl_delay → RateLimiter.wait                       │
                 │ 3. SourceBackoff.before_fetch (pause nếu đang 429/503)  │
                 │ 4. resp = HTTPClient.get_response(url)  (status+headers)│
                 │ 5. SourceBackoff.observe(status) [+ rotate_proxy nếu on]│
                 │ 6. ★ RawStore.save(resp) ── ghi .html byte-exact ─────► data/raw_html/…
                 │        + .meta.json (status, headers, sha, images[], …) │
                 │        → article.metadata["capture"]                     │
                 │ 7. content_html = select_one(selector)  (vùng con)      │
                 │       └ miss → _density_extract (D5, CHỈ content_html)   │
                 │ 8. _looks_complete? no → capture_status=partial (D1)    │
                 │ 9. content_text = extract_text(content_html)  (SAU raw) │
                 └────────────────────────────────────────────────────────┘
```

**Bất biến cốt lõi:** bước 6 (ghi raw) luôn xảy ra **trước** bước 7-9 (parse/clean).
File `.html` là bytes nguyên của `response.content`, **không bao giờ** bị sửa. Mọi thứ
khác (`images[]`, `content_html`, density) đọc từ bản sao — artifact bất biến.

### 2.1 Thành phần mới/sửa

| File | Vai trò | Loại |
|------|---------|------|
| `src/crawler/raw_store.py` | Ghi raw `.html` + `.meta.json`; quét `images[]` read-only | mới |
| `src/scrapers/capture_mixin.py` | Luồng `_capture_and_extract` + `_looks_complete` + `_density_extract` dùng chung | mới |
| `src/crawler/robots.py` | `RobotsGate` — robots.txt cache 24h, fail-open | mới |
| `src/crawler/backoff.py` | `SourceBackoff` — pause 2→4→8→16s trên 429/503 | mới |
| `src/scrapers/vietstock.py` | Scraper chuyên dụng (RSS list + capture) | mới |
| `src/scrapers/cafef.py` | `enrich()` chuyển sang RawStore-first | sửa |
| `src/crawler/http_client.py` | `get_response` (đã có) + `rotate_proxy`/`set_proxy_pool` | sửa |
| `config/domains/{cafef,vietstock}.yaml` | block `capture` + `compliance` | sửa |

---

## 3. RawStore — lưu trữ artifact

`RawStore(base_dir="data/raw_html").save(domain, url, hash, response, *, fetched_at, …) -> capture: dict`

- **Layout:** `data/raw_html/<domain>/<yyyymmdd>/<url_title_hash>.html` + `.meta.json`.
  `hash` = SHA-256(url+title) sẵn có trên `Article` → ổn định, chống trùng, dedup tự nhiên
  khi 1 bài bị quét lại (ghi đè atomic).
- **Byte-exact:** ghi `response.content` (bytes) qua `_write_atomic` (ghi `.tmp` → `os.replace`).
  KHÔNG decode/normalize. `content_sha256` = SHA-256 của chính bytes đó (dùng verify).
- **Header subset (Q5):** chỉ giữ `content-type, content-length, last-modified, etag,
  server, date`. **Loại** `Set-Cookie`/`Authorization` → không rò rỉ PII/secret.
- **`images[]` (D2, read-only):** quét mọi `<img>` bằng BeautifulSoup (trên bản sao),
  ghi `{outer_tag, resolved_url, alt, title, caption}`. `resolved_url` = giá trị đầu tiên
  có trong `src, data-src, data-original, original-src, document-path, data-lazy`, else URL
  đầu trong `srcset`; `urljoin` về tuyệt đối. `<figure>/<figcaption>` ghép caption.
  **Việc swap `data-src→src` KHÔNG làm ở đây** — đó là việc parser downstream; artifact
  giữ nguyên `data-src`.

### 3.1 Schema `.meta.json`

```json
{
  "source_url": "https://cafef.vn/....chn?utm_source=du-lieu",
  "url_title_hash": "26b0ebed…6616",
  "fetch_ts": "2026-08-13T15:33:xx+07:00",
  "render_method": "requests",
  "html_path": "data/raw_html/cafef.vn/20260813/<hash>.html",
  "http_status": 200,
  "content_sha256": "…",
  "content_length_bytes": 112196,
  "encoding": "utf-8",
  "response_headers": {"content-type": "...", "server": "...", "date": "..."},
  "images": [{"outer_tag": "<img …>", "resolved_url": "https://cafefcdn.com/…png",
              "alt": "...", "title": "...", "caption": "..."}],
  "capture_status": "ok",          // ok | partial | failed | skipped_robots
  "missing": [],                    // vd ["main_content_node","incomplete_render"]
  "error": null                     // hoặc {type,http_status,message,protection_mechanism}
}
```

`Article.metadata["capture"]` = chính dict này (không kèm body) → lưu vào cột
`metadata_json` của bảng `articles`. **Không đổi schema DB** (con trỏ nằm trong JSON sẵn có).

### 3.2 Các trạng thái & nhánh lỗi (AC8)

| Tình huống | capture_status | Ghi chú |
|------------|----------------|---------|
| 200 + body > 0 | `ok` | ghi `.html` + `images[]` |
| 200 nhưng thiếu (caller báo `missing`) | `partial` | vẫn ghi `.html` |
| `_looks_complete=False` (D1) | `partial` + `incomplete_render` | ứng viên Playwright (§9) |
| selector miss | thêm `missing:["main_content_node"]` | density fallback cho content_html |
| 4xx/5xx | `failed` + `error{http_error, status}` | body một phần vẫn ghi để soi |
| response None (fetch fail) | `failed` + `error{fetch_failed}` | ghi meta, không có `.html` |
| robots Disallow | `skipped_robots` | không fetch |

---

## 4. CaptureMixin — luồng dùng chung (DRY)

`_capture_and_extract(article, domain, referer, selector) -> html | None` gói toàn bộ
bước 1-8 ở §2 để CafeF & Vietstock dùng chung, tránh lặp code. Không raise — lỗi →
`self.errors` + `content_text=summary`.

- **`_looks_complete(html, selector)` (D1):** true iff `len(bytes) ≥ min_body_bytes`
  (mặc định 2048) **và** selector có node non-empty **và** không có marker render lỗi
  (`vui lòng bật javascript`, `checking your browser`, `captcha`…). Đây là **content-based
  gate**, KHÔNG cố định theo domain — ~90% trang qua, ~5-10% (Infographic/E-Magazine) rớt.
- **`_density_extract(html)` (D5):** khi selector miss, thử `readability-lxml` rồi `goose3`
  (lazy-import; thiếu lib → None → fallback full page). Chỉ ảnh hưởng `content_html`
  (tiện ích downstream); **raw artifact không bao giờ đổi**. Vì raw đã lưu trước, parser
  hỏng có thể sửa & **chạy lại offline** trên artifact đã lưu, không cần hit lại site.

---

## 5. Compliance & chống chặn (AC9)

### 5.1 RobotsGate (`src/crawler/robots.py`)
`urllib.robotparser` (stdlib). Cache `RobotFileParser` per-domain TTL 24h + lock (thread-safe
với APScheduler). Gọi trước `get_response`; Disallow → `skipped_robots`. **Fail-open**:
robots.txt lỗi/timeout → cho phép + WARN (không để robots outage chặn pipeline). Đọc robots
qua `HTTPClient.get` (đi chung rate limit). Đặt trong scraper-base, **opt-in** theo config
`compliance.respect_robots` (mặc định true) → không đụng 20+ domain RSS khác (Q3).

### 5.2 Rate limit + adaptive backoff (D4)
- **Hard limit (sẵn có):** `RateLimiter` per-domain 3.0s + urllib3 `Retry`
  (`backoff_factor=1.5`, `status_forcelist=[429,500,502,503,504]`) — retry trong 1 request.
- **`SourceBackoff` (mới):** pause **cấp-source giữa các lần enrich**. 429/503 → exponential
  `2→4→8→16s` (cap 16), reset khi 2xx. Bổ sung, không thay hard limit.
- **Proxy rotation (tuỳ chọn):** `compliance.proxy_rotation` mặc định **off**. Bật + có
  `proxies[]` → khi 429/503 gọi `HTTPClient.rotate_proxy()` (xoay `session.proxies`).
  Pool rỗng → no-op. (Hook cho residential proxy nếu quét tần suất lớn.)

---

## 6. Cấu hình

```yaml
# config/domains/cafef.yaml (tương tự vietstock.yaml)
capture:
  raw_dir: "data/raw_html"     # RawStore base
  min_body_bytes: 2048         # ngưỡng _looks_complete
compliance:
  respect_robots: true         # RobotsGate gate
  proxy_rotation: false         # off mặc định
  proxies: []
detail:
  content_selector: "div#mainContent"          # cafef
  # "div.article-content, div.single_post_content, article"  # vietstock
  max_details_per_cycle: 30
```

- **Vietstock** đổi `method: rss → vietstock` (dùng `VietstockScraper` chuyên dụng thay
  generic RSS). Đăng ký ở `src/scrapers/__init__.py`.
- **Retention (Q2):** `data/raw_html/` giữ toàn bộ, `.gitignore` (không commit). Rà soát
  rotation nếu đĩa phình (~110-390 KB/bài).

---

## 7. Kết quả validate LIVE (2026-08-13)

`python scripts/validate_capture.py` (HTTPClient thật, site thật, temp DB):

| | CafeF | Vietstock |
|---|-------|-----------|
| fetched / new / captured | 20 / 20 / 2 | 110 / 110 / 2 |
| capture_status | `{ok: 2}` | `{ok: 2}` |
| raw file | 112,196 B | 387,929 B |
| **sha256 == bytes** | ✅ True | ✅ True |
| http_status | 200 | 200 |
| images[] | 11 (cafefcdn.com…) | 41 (image.vietstock.vn…) |
| headers subset | content-type, server, date | +content-length |
| missing / errors | [] / 0 | [] / 0 |
| duration (rate-limited) | 9.1s | 18.7s |

`captured=2` vì `max_details_per_cycle=2` trong audit; 18/108 bài còn lại `detail_deferred`
(Q1: capture trong cap; backfill quét phần hoãn — xem `scripts/enrich_deferred.py`).

---

## 8. Kiểm thử

Chạy (venv có deps): `pytest -q tests/test_raw_store.py tests/test_cafef_capture.py
tests/test_vietstock.py tests/test_robots.py tests/test_backoff.py tests/test_looks_complete.py`

- `test_raw_store.py` — byte-exact, sha256, `images[]` (lazy `data-src`/`srcset`/figcaption,
  **artifact không mutate**), header subset, nhánh None/4xx.
- `test_cafef_capture.py` — artifact ok; **order-spy** (raw save TRƯỚC `extract_text` → AC7); 404→failed.
- `test_vietstock.py` — RSS list, ISO+07:00, tickers, language, byte-exact, `images[]`, failure.
- `test_robots.py` — allow/deny, crawl-delay, fail-open, cache 1 lần.
- `test_backoff.py` — 2→4→8→16 + reset.
- `test_looks_complete.py` — D1 true/false + `_density_extract` graceful khi thiếu lib.
- Fakes dùng chung: `tests/_fakes.py` (`FakeResponse`/`FakeHTTP.get_response`).
  Capture tests chdir tmp trong fixture `env` (cô lập raw writes), **không** chdir toàn cục
  (tránh vỡ notifier/sentiment load config theo path tương đối).

---

## 9. Playwright fallback [HOÃN / tuỳ chọn]

Chưa build (YAGNI): cả 2 nguồn ~90% server-rendered. Kích hoạt CHỈ khi `_looks_complete`
(D1) rớt (`capture_status=partial/incomplete_render`) + config bật. Khi build cần
**hardening (D6):** `playwright-stealth`/`undetected-playwright` (xoá `navigator.webdriver`),
residential rotating proxy, **`async_playwright`** (tránh memory leak của sync+threads).
Lưu DOM render qua cùng `RawStore` với `render_method="playwright"`. Chi tiết:
`plans/…/phase-05-playwright-fallback-optional.md`.

---

## 10. Hạn chế & câu hỏi mở

- **Cap vs full (Q1):** v1 chỉ raw-capture trong `max_details_per_cycle`; phần hoãn cần
  backfill sweep — chưa có job tự động chuyên cho capture (tái dùng `enrich_deferred.py`).
- **`_density_extract`** phụ thuộc `readability-lxml` (đã thêm vào requirements) — thiếu lib
  thì fallback full-page cho `content_html` (raw vẫn nguyên).
- **UTF-8 stdout (Windows):** in tiếng Việt qua stdout redirect cp1252 gây `UnicodeEncodeError`
  → chạy script cần `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` (orchestrator đã có `_force_utf8_stdio`).
- **Marker `_EMPTY_MARKERS`** là heuristic — mở rộng khi gặp trang chặn thực tế.
- **Ảnh** mới lưu URL trong `images[]`; **tải file ảnh** là bước downstream (chưa làm).
