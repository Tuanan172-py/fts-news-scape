# Dev — Hướng dẫn codebase

Cập nhật: 2026-07-26 · Đối tượng: dev mới, cần nắm cây thư mục + cách code chạy để sửa/mở rộng.

## 1. Cây thư mục

```
src/
├── orchestrator.py       # điểm vào: scheduler | --once; run_cycle; áp classify+sentiment
├── core/
│   ├── base_scraper.py   # BaseScraper ABC — template run(): fetch→parse→dedup→enrich
│   ├── config.py         # load_settings/domain_config/watchlist/secrets; list_domains
│   ├── models.py         # Article, ScrapeResult, sha256_hash, now_vn_iso, VN_TZ
│   ├── tickers.py        # tag_tickers() — gắn mã CK client-side
│   ├── retry.py          # run_with_retry / run_with_fallback
│   └── logging.py        # loguru setup (logs/monocle.log, rotate 50MB, giữ 14 ngày)
├── crawler/
│   └── http_client.py    # HTTPClient dùng chung: rate limit 3s/domain, retry, UA rotation
├── scrapers/
│   ├── __init__.py       # REGISTRY + @register + build_scraper
│   ├── rss_generic.py    # RSSScraper (_rss) — 18 domain dùng chung
│   ├── cafef.py tnck.py vndirect.py fireant.py   # API scraper riêng
├── processor/
│   ├── classifier.py     # classify_rule_based (regex 4 nhóm)
│   ├── sentiment.py      # SentimentEngine (lexicon TSV, n-gram, negation)
│   ├── segment.py        # seg() — pyvi tokenize, fallback whitespace
│   └── extractor.py      # extract_text / extract_content (trafilatura)
├── db/
│   ├── store.py          # ArticleStore — schema, PRAGMA WAL, insert_batch
│   ├── writer.py         # DBWriter — single-writer thread, batch
│   └── dedup.py          # DedupCache — seen_articles, hash + fuzzy
├── monitor/
│   ├── heartbeat.py      # ghi scraper_heartbeat + scraper_metrics
│   └── health.py         # CLI đọc trạng thái, exit code
└── notifier/
    └── file_notify.py    # FileNotifier — format + ghi data/notifications/*.log

config/domains/*.yaml     # 23 domain (1 file/nguồn)
config/{settings,watchlist,notifications}.yaml + secrets.yaml (gitignored)
data/lexicon/*.tsv        # lexicon sentiment · data/labeled/ bộ kiểm định
tests/                    # pytest, 112 test
```

## 2. Ba tầng

```
orchestrator ──build_scraper──► BaseScraper.run() ──► ScrapeResult
     │                               │  dùng: http_client, dedup, extractor
     ├─ classify_rule_based ─────────┘
     ├─ sentiment.analyze
     ├─ writer.enqueue ──► DBWriter thread ──► store.insert_batch ──► SQLite
     ├─ heartbeat.record_* ──► SQLite (ghi thẳng, không qua writer)
     └─ notifier.notify_* ──► file + stdout
```

Nguyên tắc phụ thuộc: **scraper không biết DB/sentiment/notify**. Nó chỉ nhận `http`+`dedup`,
trả `ScrapeResult`. Mọi hậu xử lý nằm ở orchestrator. Điều này giúp test scraper bằng
`FakeHTTP` mà không cần DB thật.

## 3. Registry — thêm scraper không sửa core

`scrapers/__init__.py`:

```python
REGISTRY: dict[str, type[BaseScraper]] = {}
def register(name):
    def deco(cls): REGISTRY[name] = cls; return cls
    return deco
# cuối file (tránh circular import):
from src.scrapers import cafef, fireant, rss_generic, tnck, vndirect
```

`build_scraper(cfg)` tra `REGISTRY[cfg["method"]]`. RSS domain dùng `method: rss` → key `_rss`.

## 4. HTTP client — hợp đồng dùng chung (`crawler/http_client.py`)

- **Rate limit** per-domain (bucket riêng, thread-safe), mặc định 3.0s; reserve slot trước khi
  sleep để concurrency đúng (`:46-55`).
- **Retry** urllib3: total=3, backoff 1.5 (→1.5/3/6s), status `429,500,502,503,504`, methods
  `GET/HEAD/POST`.
- **UA rotation**: random 1 trong 5 UA/request. **Không** tự khai `Accept-Encoding` (tránh brotli rác).
- **truststore**: dùng OS cert store (hnx.vn chain thiếu intermediate).
- Methods: `get`(text) · `get_bytes`(raw, cho feed) · `get_json` · `post_json` · `get_response`(raw
  Response, cho FireAnt cần đọc status 401). Lỗi request → trả `None` (không raise) trừ `get_response`.

## 5. Điểm quan trọng khi đọc code

- **Không bao giờ raise ra pipeline**: lỗi thành string trong `errors[]`. Đọc `base_scraper.py:40-77`.
- **`disabled`**: chỉ FireAnt dùng (self-disable khi 401/403). Các scraper khác không có.
- **Cap chi tiết** `max_details_per_cycle` khác nhau: RSS/cafef/tnck/fireant=30, vndirect=20.
- **now/tz**: luôn dùng `now_vn_iso()` + `VN_TZ` (`models.py:15,23`), không `datetime.now()` trần.
- **Hash dedup**: `sha256_hash(url, title)` = SHA-256 của chuỗi nối `url+title` (không separator).

## 6. Chạy nhanh

```powershell
.venv\Scripts\python.exe -m src.orchestrator --once cafef   # 1 domain, 1 cycle
.venv\Scripts\python.exe -m src.orchestrator --once         # tất cả, 1 cycle
.venv\Scripts\python.exe -m src.orchestrator                # scheduler 15 phút
.venv\Scripts\python.exe -m src.monitor.health              # trạng thái + exit code
.venv\Scripts\python.exe -m pytest -q                       # 112 test
```

Chi tiết vận hành: [../operations/deployment.md](../operations/deployment.md).
