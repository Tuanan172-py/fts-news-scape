# Dev — Thêm một nguồn tin mới

Cập nhật: 2026-07-26 · Đối tượng: dev muốn bổ sung domain.

## 1. Quyết định phương thức

Theo TDR-001 (RSS > API > HTML):
1. Nguồn **có RSS** đủ sâu → dùng `RSSScraper`, **chỉ cần 1 file YAML, 0 code**. → Mục 2.
2. Nguồn **chỉ có API JSON** (theo mã CK, cần auth, schema riêng) → viết scraper module. → Mục 3.

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
- [ ] Cập nhật [../domains/](../domains/) tương ứng + bảng ma trận.
