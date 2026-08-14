# Dev Guide 06 — RAW HTML Capture: Quy trình phát triển end-to-end

Cập nhật: 2026-08-14 · Trạng thái: ĐÃ TRIỂN KHAI + validate LIVE
Tài liệu tự chứa: bối cảnh → phương pháp → từng bước dev → walkthrough code → luồng E2E → kiểm thử → vận hành.
Đọc kèm bản thiết kế cô đọng: [../design/06-raw-html-capture.md](../design/06-raw-html-capture.md).

> **Tóm tắt 30 giây.** Ta thêm một tầng thu thập **raw HTML byte-exact** cho CafeF + Vietstock,
> cắm vào hook `enrich()` sẵn có. Mỗi bài → 1 file `.html` nguyên bytes + 1 `.meta.json`
> (status/headers/sha256/ảnh/lỗi). Nguyên tắc bất biến: **ghi raw TRƯỚC, không bao giờ sửa**.
> Compliance (robots + backoff) và fallback (density/Playwright) bao quanh, nhưng không đụng raw.

---

## Phần A — PHƯƠNG PHÁP TIẾP CẬN (tại sao làm theo cách này)

### A.1 Nguyên tắc dẫn đường
1. **Research-first, không giả định selector.** Yêu cầu gốc nhấn mạnh "nghiên cứu cấu trúc
   HTML thực tế". Ta xác minh *thật* (WebFetch trang sống) trước khi thiết kế, thay vì đoán.
2. **Tận dụng kiến trúc sẵn có (KISS/DRY/YAGNI).** Codebase đã có pipeline template-method
   (`BaseScraper`), `HTTPClient`, DB, dedup. Ta **không** dựng hệ mới — chỉ chèn tầng capture
   vào đúng chỗ (`enrich()`), tái dùng rate-limit/retry/UA.
3. **Bất biến raw = ưu tiên số 1.** Tiêu chí nghiệm thu cấm clean/normalize. Mọi thiết kế xoay
   quanh: *lưu bytes gốc trước, mọi thứ khác đọc từ bản sao*.
4. **Fail-safe, không raise.** Theo quy ước dự án: lỗi → `self.errors`, pipeline chạy tiếp.

### A.2 Quy trình đã đi (workflow thực tế)
```
/plan:hard ──► (1) Đọc codebase (README + src) ──► (2) 2 researcher song song
   │                                                    (cấu trúc nguồn / kiến trúc capture)
   │            (3) Main agent tự verify LIVE CafeF (đóng gap researcher bỏ sót)
   │            (4) Scout report codebase ──► (5) planner tạo plan 6 phase
   ▼
User review ──► góp ý D1–D6 ──► AskUserQuestion Q1–Q5 ──► plan chốt
   ▼
/cook:auto ──► implement phase 01→06 ──► pytest ──► fix regressions ──► validate LIVE ──► docs
```
Điểm mấu chốt của phương pháp: **verify-before-assume** (bước 3 tự fetch CafeF để xác nhận
server-rendered) và **decision-gated** (D1–D6/Q1–Q5 do stakeholder chốt trước khi code).

### A.3 Phát hiện nghiên cứu định hình thiết kế
| Câu hỏi | Kết quả xác minh | Hệ quả thiết kế |
|---|---|---|
| CafeF/Vietstock render body bằng JS? | **Không** — server-rendered (fetch thật thấy đủ body) | Dùng `requests`, không cần headless → phase-05 hoãn |
| Ảnh lazy-load kiểu gì? | Vietstock `src` trực tiếp; VN news hay dùng `data-src`/`srcset` | `images[]` resolve nhiều attr, **không** rewrite raw |
| robots.txt? | Cả 2 cho phép trang bài; Vietstock chặn `/*.js,/manager` | Gate opt-in, ta chỉ fetch trang bài |
| Code có sẵn chỗ cắm? | `BaseScraper.enrich()` = nơi fetch detail | Chèn RawStore-first vào `enrich()` |

---

## Phần B — QUÁ TRÌNH PHÁT TRIỂN TỪNG BƯỚC

Thứ tự phụ thuộc: **01 → (02 ∥ 03) → 04 → 06**; 05 hoãn.

### B.1 Phase 01 — RawStore (nền móng)
**Vấn đề cần giải:** cần một nơi ghi raw HTML *byte-exact* + metadata, độc lập DB, kiểm tra
offline được, không rò rỉ secret.

**Lựa chọn & lý do:**
- *Đĩa (file) thay vì BLOB SQLite* → DB gọn, artifact grep/mở trực tiếp, git-ignore được,
  tách bytes thô khỏi hàng metadata truy vấn.
- *Sidecar `.meta.json`* → chạy lại parser mới trên artifact cũ mà không cần metadata trong DB.
- *Content-addressed theo `url_title_hash`* → trùng bài ghi đè atomic, không sinh rác.
- *Header whitelist* → chỉ 6 header vô hại; loại `Set-Cookie`/`Authorization`.

**Đầu ra:** `src/crawler/raw_store.py`. (Walkthrough chi tiết ở Phần C.1.)

### B.2 Phase 02 — CafeF (mở rộng scraper có sẵn)
**Hiện trạng cũ:** `enrich()` dùng `http.get()` (chỉ text), lưu **mỗi** node `#mainContent`,
chạy `trafilatura` ngay → mất `<head>`, mất status/headers, mất cấu trúc full-page, và
*clean ngay* (vi phạm AC7 nếu coi đây là raw).

**Thay đổi:** chuyển sang `http.get_response()` (có status+headers) → `RawStore.save()` **đầu
tiên** (lưu full page) → giữ `#mainContent` chỉ như **vùng con tham chiếu** trong `content_html`
→ `extract_text` chạy **sau**. Logic gói trong `CaptureMixin._capture_and_extract` để dùng chung.

### B.3 Phase 03 — Vietstock (scraper chuyên dụng)
**Quyết định:** Vietstock đang chạy generic RSS (không persist raw). Xây `VietstockScraper`
riêng thay vì nhồi vào RSS generic vì: (a) selector container chính xác; (b) chèn RawStore-first
sạch, không rủi ro 20+ domain RSS khác; (c) chỗ cho quirk Vietstock. **DRY**: import lại helper
RSS (`_decode_feed`, `_parse_entry_date`, `_clean_title`) thay vì copy.

### B.4 Phase 04 — Compliance (robots + backoff)
**Bổ sung, không xây lại.** `HTTPClient` đã có `RateLimiter` 3s + urllib3 Retry. Ta thêm:
`RobotsGate` (stdlib, cache 24h, fail-open) + `SourceBackoff` (pause cấp-source 2→4→8→16s trên
429/503) + hook `rotate_proxy` (tuỳ chọn, off). Đặt ở scraper-base, opt-in.

### B.5 Phase 06 — Kiểm thử + nghiệm thu
`FakeHTTP.get_response`/`FakeResponse` (offline). Mỗi AC1–AC9 ánh xạ ≥1 assert. Cô lập raw
writes bằng `monkeypatch.chdir(tmp)` trong fixture `env` (KHÔNG chdir toàn cục — bài học ở E.2).

---

## Phần C — WALKTHROUGH CODE (từng đoạn + lý do)

### C.1 `raw_store.py` — điểm mấu chốt

**(1) Ghi atomic, byte-exact.** Không decode, không chạm nội dung:
```python
@staticmethod
def _write_atomic(path, data: bytes):
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)          # atomic trên cùng volume → không có file nửa vời
```
`save()` đọc `response.content` (bytes) → `sha256` của **chính bytes đó** → ghi. `content_sha256`
cho phép verify độc lập rằng file trên đĩa == phản hồi gốc (audit LIVE: match=True).

**(2) `images[]` read-only — hoà giải AC5 với "không mutate".**
Yêu cầu: ảnh giữ URL để tải sau. Cám dỗ: swap `data-src→src`. Nhưng swap = **sửa HTML** (cấm).
Giải: quét bản sao, ghi manifest, **không đụng file**:
```python
for img in soup.find_all("img"):
    resolved = ""
    for attr in ("src","data-src","data-original","original-src","document-path","data-lazy"):
        if img.get(attr): resolved = img.get(attr).strip(); break
    if not resolved and img.get("srcset"):
        resolved = img["srcset"].split(",")[0].strip().split(" ")[0]
    if resolved: resolved = urljoin(base_url, resolved)      # về URL tuyệt đối
    # + ghép <figure>/<figcaption> lấy caption
```
Kết quả LIVE: CafeF 11 ảnh, Vietstock 41 ảnh — URL CDN thật; raw `.html` vẫn giữ `data-src`.

**(3) Ba nhánh trạng thái (AC8).** `None`→`failed{fetch_failed}`; `4xx/5xx`→`failed{http_error}`
(body một phần vẫn ghi để soi); `2xx+body`→`ok` (hoặc `partial` nếu `missing`). **Luôn** ghi
`.meta.json` kể cả khi fail → không mất dấu vết.

### C.2 `capture_mixin.py` — luồng dùng chung & thứ tự bất biến
```python
def _capture_and_extract(self, article, domain, referer, selector):
    if self.respect_robots and self.robots and not self.robots.allowed(url):
        cap["capture_status"] = "skipped_robots"; article.content_text = article.summary
        self.errors.append(...); return None                     # (1) robots gate
    if self.robots: cd = self.robots.crawl_delay(domain); ... wait(cd)   # (2) crawl-delay
    if self.backoff: self.backoff.before_fetch(domain)           # (3) backoff pause
    resp = self.http.get_response(url, referer=referer, timeout=...)
    if self.backoff: self.backoff.observe(domain, status or 503) # (5) học từ status
    cap = self.raw_store.save(domain, url, article.url_title_hash, resp, fetched_at=...)  # (6) ★RAW
    article.metadata["capture"] = cap
    if resp is None or not resp.ok:
        article.content_text = article.summary; self.errors.append(...); return None
    node = BeautifulSoup(html,"lxml").select_one(selector)
    if node and node.get_text(strip=True): article.content_html = str(node)   # (7) vùng con
    else: article.content_html = self._density_extract(html) or html          # D5 fallback
    if not self._looks_complete(html, selector): cap["capture_status"]="partial"  # D1
    return html
```
**Vì sao thứ tự này quan trọng:** bước (6) *RawStore.save* nằm **trước** (7)(8) và trước
`extract_text` (gọi ở scraper sau khi hàm này trả về). Test `test_order_raw_saved_before_extract`
dùng **spy** chốt chặn: `events[0] == "save"` và `save < extract` → bằng chứng AC7.

**`_looks_complete` (D1) — content-based, không cố định domain:**
```python
def _looks_complete(self, html, selector):
    if len(html.encode()) < self.min_body_bytes: return False   # body quá ngắn
    if any(m in html[:4000].lower() for m in _EMPTY_MARKERS): return False  # marker chặn/JS
    node = BeautifulSoup(html,"lxml").select_one(selector)
    return node is not None and bool(node.get_text(strip=True)) # container có nội dung
```
→ chỉ ~5-10% trang (Infographic/E-Magazine) rớt gate, thành ứng viên Playwright. Không "gắn cờ
domain cần JS" tĩnh.

**`_density_extract` (D5)** — lazy-import `readability-lxml`/`goose3`; thiếu lib → `None` →
fallback full page. **Chỉ** sửa `content_html`; raw đã lưu, bất biến → parser hỏng vẫn re-run offline.

### C.3 `robots.py` — gate rẻ, fail-open
Cache `RobotFileParser` per-domain 24h + lock (thread-safe với APScheduler). Đọc robots qua
`http.get` (đi chung rate limit). robots lỗi/None → **cho phép** + WARN (không để robots outage
làm nghẽn). `crawl_delay()` đọc từ cùng parser cache (không fetch lại).

### C.4 `backoff.py` — pause cấp-source
```python
_BACKOFF_STEPS = (2.0, 4.0, 8.0, 16.0)
def observe(self, domain, status):
    if status in (429,503):
        delay = _BACKOFF_STEPS[min(st["consecutive"], 3)]
        st["consecutive"] = min(st["consecutive"]+1, 4)
        st["next_allowed_ts"] = now + delay          # lần sau before_fetch sẽ ngủ phần dư
    elif 200 <= status < 300:
        st["consecutive"] = 0; st["next_allowed_ts"] = 0.0   # reset
```
Khác urllib3 Retry (trong 1 request): đây là cool-down **giữa các enrich** cho cùng domain.

### C.5 `vietstock.py` — DRY với RSS
```python
from src.scrapers.rss_generic import _clean_title, _decode_feed, _parse_entry_date  # tái dùng
@register("vietstock")
class VietstockScraper(CaptureMixin, BaseScraper):
    ...
    def enrich(self, article):
        if self._details_fetched >= self.max_details:
            article.content_text = article.summary; article.metadata["detail_deferred"]=True; return
        html = self._capture_and_extract(article, "vietstock.vn", f"{BASE_URL}/", self.content_selector)
        if html is None: return
        self._details_fetched += 1
        article.content_text = extract_text(article.content_html) or article.summary
```
MRO `(CaptureMixin, BaseScraper)`: mixin cung cấp method, BaseScraper cung cấp `run()`/`self.errors`.

### C.6 `cafef.py` — diff cốt lõi
Trước: `html = self.http.get(...)` → `BeautifulSoup(...).select_one("#mainContent")` → lưu node.
Sau: gọi `self._capture_and_extract(article, "cafef.vn", ...)` (RawStore-first) → `extract_text`
**sau**. Bỏ import `BeautifulSoup` khỏi cafef (chuyển vào mixin). `_init_capture()` trong `__init__`.

### C.7 `http_client.py` — hook proxy (tuỳ chọn)
Thêm `set_proxy_pool()` + `rotate_proxy()` (no-op khi pool rỗng). Không đổi chữ ký cũ → không
phá vỡ nơi khác. Off mặc định.

---

## Phần D — LUỒNG END-TO-END & DATA MODEL

### D.1 Sơ đồ E2E
```
orchestrator --once cafef/vietstock
  └► build_scraper(config) → REGISTRY["cafef"|"vietstock"]
       └► scraper.run():  fetch_list → parse_item → dedup → enrich(★capture) → mark_seen
            └► enrich: robots→backoff→get_response→RawStore.save→content_html→looks_complete→extract_text
  DBWriter ⇦ ScrapeResult.new  (metadata_json chứa capture{...})
  Đĩa      ⇦ data/raw_html/<domain>/<yyyymmdd>/<hash>.html + .meta.json
```

### D.2 Vòng đời một bài
1. RSS/API cho URL+title → `Article` (hash = SHA-256(url+title)).
2. `enrich` fetch detail → **raw `.html` byte-exact** + `.meta.json`.
3. `content_html` = vùng con (selector) — tiện ích cho downstream, **không** thay raw.
4. `content_text` = trafilatura(content_html) — bước clean, chạy sau raw.
5. DB lưu row + `metadata.capture` (con trỏ artifact). Raw nằm trên đĩa để pipeline sau đọc lại.

### D.3 `.meta.json` (14 keys) — xem schema đầy đủ ở design/06 §3.1.
Quan trọng: `content_sha256` (verify), `capture_status` (ok/partial/failed/skipped_robots),
`missing[]` (phần thiếu), `error{}` (type/http_status/protection_mechanism), `images[]`.

---

## Phần E — KIỂM THỬ & VALIDATION

### E.1 Ma trận test → AC
| Test | Phủ |
|---|---|
| `test_raw_store` | AC2 byte-exact, AC5 images no-mutate, AC6 offline, AC8 nhánh lỗi, header hygiene |
| `test_cafef_capture` | AC2/AC3/AC6 + **AC7 order-spy** + AC8 404 |
| `test_vietstock` | AC1/2/3/5 + RSS/ISO/tickers/language + failure |
| `test_robots` | AC9 allow/deny/crawl-delay/fail-open/cache |
| `test_backoff` | AC9 exp 2→4→8→16 + reset |
| `test_looks_complete` | D1 true/false + D5 graceful |

### E.2 Bài học regression (minh bạch)
Ban đầu đặt `monkeypatch.chdir(tmp)` **autouse toàn cục** trong `conftest` để cô lập raw writes
→ vô tình phá `test_monitor_notify`/`test_orchestrator` vì `FileNotifier`/`SentimentAnalyzer`
load config/lexicon theo **đường dẫn tương đối**. Sửa: bỏ chdir toàn cục, chỉ chdir trong fixture
`env` của các capture test. Đây là ví dụ side-effect toàn cục nguy hiểm — đã ghi lại để tránh lặp.
(2 test `test_monitor_notify` emoji còn đỏ là **tech-debt sẵn có**: code dùng `[+]`, test mong
emoji; `file_notify.py` KHÔNG nằm trong diff này.)

### E.3 Validation LIVE (`scripts/validate_capture.py`, 2026-08-13)
| | CafeF | Vietstock |
|---|---|---|
| fetched/new/captured | 20/20/2 | 110/110/2 |
| capture_status | {ok:2} | {ok:2} |
| raw bytes | 112,196 | 387,929 |
| **sha256==bytes** | ✅ | ✅ |
| images[] | 11 (cafefcdn) | 41 (image.vietstock) |
| errors | 0 | 0 |
Chứng minh toàn bộ AC trên site thật.

---

## Phần F — VẬN HÀNH

- **Chạy:** `python scripts/run_once.py cafef vietstock` (hoặc `python -m src.orchestrator --once <name>`).
- **Audit E2E:** `python scripts/validate_capture.py [cafef|vietstock] [N]` (Windows: đặt
  `PYTHONUTF8=1` để in tiếng Việt qua stdout redirect).
- **Config:** block `capture{raw_dir,min_body_bytes}` + `compliance{respect_robots,proxy_rotation,proxies}`.
- **Artifact:** `data/raw_html/` (gitignored, giữ toàn bộ — Q2). Rà soát rotation nếu đĩa phình.
- **Backfill bài hoãn:** hiện tái dùng `scripts/enrich_deferred.py` (Q1: capture trong cap).

---

## Phần G — HẠN CHẾ & HƯỚNG MỞ RỘNG

1. **Playwright (phase-05)** — hoãn có điều kiện; kích hoạt khi `_looks_complete` phát hiện trang
   thiếu thực tế. Cần stealth + async + residential proxy (D6).
2. **Backfill job riêng cho capture** — chưa tự động hoá (Q1).
3. **Tải file ảnh** — `images[]` đã lưu URL/định danh (đủ AC5); download là bước downstream.
4. **`_EMPTY_MARKERS`** heuristic — mở rộng khi gặp cơ chế chặn thực tế.
5. **Repo là thư mục OneDrive** — có drift ngoài phiên (vd `orchestrator._force_utf8_stdio`).

---

## Phần H — BẢN ĐỒ FILE
**Mới:** `src/crawler/{raw_store,robots,backoff}.py`, `src/scrapers/{capture_mixin,vietstock}.py`,
`scripts/validate_capture.py`, `tests/{_fakes,conftest,test_raw_store,test_robots,test_backoff,`
`test_looks_complete,test_cafef_capture,test_vietstock}.py`, `tests/fixtures/vietstock_detail_page.html`,
`data/raw_html/.gitignore`, 2 docs (`design/06`, `dev/06-guide`).
**Sửa:** `src/scrapers/{cafef,__init__}.py`, `src/crawler/http_client.py`, `src/core/models.py`
(docstring), `config/domains/{cafef,vietstock}.yaml`, `requirements.txt`, `tests/test_cafef.py`.
**Kế hoạch gốc:** `plans/20260813-0736-raw-html-capture-vietstock-cafef/`.
