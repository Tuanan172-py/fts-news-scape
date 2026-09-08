# Dev — Thêm một nguồn tin mới

Cập nhật: 2026-07-26 · Đối tượng: dev muốn bổ sung domain.

## 1. Quyết định phương thức

Theo TDR-001 (RSS > API > HTML):
1. Nguồn **có RSS** đủ sâu → **1 file YAML, 0 code**:
   - Cần **Bronze raw HTML capture** (mặc định cho mọi nguồn mới) → `method: rss_capture`. → **Mục 2b**.
   - Chỉ cần summary/metadata, KHÔNG cần Bronze → `method: rss`. → Mục 2.
     ⚠️ Hầu như không còn dùng: `RSSScraper.enrich()` **không gọi `RawStore`** nên không có
     Bronze artifact, và pipeline Silver/change-detection không có gì để dựng.
2. Nguồn **chỉ có API JSON** (theo mã CK, cần auth, schema riêng) → viết scraper module. → Mục 3.
3. Nguồn **không có cả RSS lẫn API** → HTML listing scraper (ngoại lệ TDR-001, phải ghi lý do).
   Mẫu: `src/scrapers/baodautu.py`.

Trước khi thêm: **verify feed/endpoint sống thật** (curl/trình duyệt), đếm số item, kiểm tra
encoding + định dạng ngày. Ghi lại quirk vào YAML dạng comment.

## 2. Thêm nguồn RSS (không code)

Tạo `config/domains/<name>.yaml`:

```yaml
name: <name>              # bắt buộc, khớp tên file
method: rss               # → RSSScraper
enabled: true
rate_limit: 3.0
timeout: 30
language: vi              # vi | en (en → sentiment ép neutral)

rss:
  feeds:
    - url: "https://example.com/rss/chung-khoan.rss"
      name: "Example Chứng khoán"     # → categories

detail:
  extract_full: true       # false = chỉ summary (paywall/SPA)
  max_details_per_cycle: 30

# (tuỳ chọn) lọc feed rộng:
filter:
  any: ["chứng khoán", "cổ phiếu", "vn-index"]   # allow-list
  drop_unmatched: true
  # none: ["mortgage", "credit card"]            # block-list

# (tuỳ chọn) sửa URL lỗi (vd HNX port nội bộ):
# link_rewrites:
#   - ["...:7978", ""]
#   - ["^http://", "https://"]
```

Xong. Chạy thử: `python -m src.orchestrator --once <name>`. `RSSScraper` tự lo encoding/date.

## 2b. Thêm nguồn RSS + Bronze capture (`method: rss_capture`) — KHUYẾN NGHỊ

Dùng `RssCaptureScraper` (`src/scrapers/rss_capture.py`) — kế thừa `RSSScraper`, chỉ override
`__init__` + `enrich()`. `fetch_list`, `parse_item`, `filter.any/none`, `link_rewrites` dùng lại
nguyên vẹn. **0 dòng Python cho nguồn mới.**

```yaml
name: <name>
enabled: true
method: rss_capture          # ← RSS list + Bronze full raw HTML capture
rate_limit: 3.0
timeout: 30
language: vi
base_url: "https://example.com/"     # dùng làm Referer khi fetch detail
rss:
  feeds:
    - {url: "https://example.com/chung-khoan.rss", name: "Example Chứng khoán"}
detail:
  extract_full: true
  content_selector: "div.article-body"   # ⚠️ BẮT BUỘC — xem cảnh báo bên dưới
  max_details_per_cycle: 30
capture:
  raw_dir: "data/raw_html"
  min_body_bytes: 2048
compliance:
  respect_robots: true
  proxy_rotation: false
  proxies: []
pitfalls: "…ghi quirk đã verify live…"
```

### ⚠️ `content_selector` là BẮT BUỘC, không phải tuỳ chọn

Nếu selector không khớp node nào, `CaptureMixin._looks_complete()` trả `False` →
`capture_status: "partial"` + `missing: ["incomplete_render"]` → `change_detect.classify()` cho ra
**`SELECTOR_BROKEN`** → `recommendation: manual_review` → **agent HOLD toàn bộ bài của nguồn đó**.

`_density_extract` (readability/goose3) chỉ vá `content_html`, **KHÔNG** vá `capture_status`.
Nên "để trống rồi dựa vào density fallback" là sai.

→ **Luôn fetch thật 1 bài và xác minh selector trước khi ship.** Nhiều trang VN không có thẻ
`<article>` (vd vietnambiz) nên default `"article"` sẽ hỏng 100% số bài.

### `content:encoded` KHÔNG phải Bronze

Khác `RSSScraper` (bỏ qua fetch detail khi feed có `content:encoded` ≥ 500 ký tự),
`RssCaptureScraper` **luôn** fetch trang detail để lưu raw byte-exact. Inline HTML chỉ được dùng
làm body **dự phòng** khi capture thất bại. Đừng "tối ưu" bằng cách bỏ fetch.

### Checklist riêng cho `rss_capture`

- [ ] Fetch thật 1 bài, xác minh `content_selector` khớp (không chỉ đoán từ DevTools).
- [ ] Fetch `robots.txt`, ghi vào `pitfalls` + `domains/<name>/schema.yaml`.
- [ ] Kiểm tra trang có `<article>` không — nếu không, selector càng bắt buộc.
- [ ] Xác minh format `pubDate` và **timezone** (nhiều nguồn thiếu offset ở meta tag).
- [ ] Test: capture_status `ok`, byte-exact `read_text() == fixture`, selector không sinh
      `missing[main_content_node]`, cap `max_details`, feed chết bị cô lập.

Mẫu đầy đủ: `config/domains/vietnambiz.yaml` + `tests/test_rss_capture.py` +
`domains/vietnambiz/`.

## 3. Thêm scraper API (có code)

### 3.1 Viết module `src/scrapers/<name>.py`
```python
from src.core.base_scraper import BaseScraper
from src.core.models import Article
from src.scrapers import register

@register("<name>")
class MyScraper(BaseScraper):
    def __init__(self, config, http, dedup):
        super().__init__(config, http, dedup)
        # đọc config: endpoint, params, token từ config["_secrets"], cap...

    def fetch_list(self) -> list[dict]:
        # http.get_json / get_response; gom lỗi vào self.errors, KHÔNG raise
        ...

    def parse_item(self, raw: dict) -> Article | None:
        # thiếu field cốt lõi → return None
        return Article(url=..., title=..., source_domain="...",
                       symbols=[...], published_at=<ISO+07:00>,
                       metadata={"language": "vi"})

    def enrich(self, article: Article) -> None:      # tuỳ chọn
        # tôn trọng self.max_details; lỗi → content_text = summary
        ...
```

### 3.2 Đăng ký
Thêm module vào dòng import cuối `src/scrapers/__init__.py`.

### 3.3 YAML `config/domains/<name>.yaml`
```yaml
name: <name>
method: <name>        # khớp @register
enabled: true
api:
  list_url: "..."
  params: {...}
auth:                 # nếu cần token
  type: bearer
  secret_key: <name>_token     # đọc từ config/secrets.yaml
detail:
  max_details_per_cycle: 30
```

## 4. Quy ước bắt buộc

- **Không raise** — mọi lỗi `self.errors.append(str)`, để pipeline chạy tiếp.
- **Tôn trọng rate limit** — luôn qua `self.http`, không tự `requests`.
- **Ngày ISO +07:00** — parse về giờ VN (`VN_TZ`).
- **`metadata["language"]`** — set `vi`/`en` để gate sentiment đúng.
- **Cap `max_details`** trong `enrich` — tránh cycle vô hạn.
- **Secret** đọc từ `config["_secrets"]`/`load_secrets()`, **không hard-code**, không log giá trị.
- **Self-disable** nếu auth hỏng (theo mẫu FireAnt 401/403) để không hammer API.

## 5. Viết test

Mỗi scraper cần test với `FakeHTTP` (không gọi mạng thật). Xem mẫu `tests/test_fireant.py`,
`tests/test_cafef.py`. Bắt buộc phủ: happy path, thiếu field, lỗi HTTP, self-disable (nếu có),
date parsing. **Không dùng mock giả để pass build** — test phải phản ánh hành vi thật.
Chi tiết: [04-testing.md](04-testing.md).

## 6. Checklist PR

- [ ] Feed/endpoint verify sống, ghi quirk vào YAML comment.
- [ ] `--once <name>` chạy sạch, có bài vào DB.
- [ ] Ngày đúng giờ VN, symbols gắn đúng, language đúng.
- [ ] Test mới xanh, `pytest -q` toàn bộ xanh.
- [ ] **Bronze artifact**: `data/raw_html/<host>/<yyyymmdd>/<hash>.html` tồn tại,
      `sha256sum` khớp `content_sha256` trong `.meta.json`, `capture_status: "ok"`.
- [ ] **Silver derive**: `scripts/run_once.py <name>` → `data/silver/<host>/…json`,
      `cleaned_text` không rỗng.
- [ ] **`domains/<name>/schema.yaml`** (BẮT BUỘC) — phải có key `domain: <host>` ở top level;
      đây là nguồn sự thật để tooling monitor resolve host. Kèm `README.md` + `changelog.md`.
- [ ] Cập nhật docs — **đầy đủ, không chỉ 1 file**:
      [../domains/README.md](../domains/README.md) (bảng ma trận **+ cột Enabled + số đếm**),
      [../domains/vn-rss.md](../domains/vn-rss.md) hoặc `api-scrapers.md` / `html-scrapers.md`,
      [../skills/rss-sources.md](../skills/rss-sources.md),
      `README.md` gốc (số đếm nguồn).
- [ ] `scripts/verify_quality.py <host>` ≥95% — lưu ý dùng **host** (`vietnambiz.vn`),
      không phải tên config (`vietnambiz`).
- [ ] `scripts/report_drift.py` không sinh `SELECTOR_BROKEN` mới.
