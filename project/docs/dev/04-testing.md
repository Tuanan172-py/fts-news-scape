# Dev — Kiểm thử

Cập nhật: 2026-07-26 · 112 test, chạy `pytest -q`. Nguồn: `tests/`.

## 1. Nguyên tắc

- **Không mạng thật** trong unit test — dùng `FakeHTTP` bơm bytes/JSON cố định.
- **Không mock giả để pass build** — test phải phản ánh hành vi thật của code.
- **Fixture thật** cho feed khó: `tests/fixtures/*.rss` (dantri BOM, vietnambiz utf-16-mislabel)
  được capture từ nguồn sống, dùng để khoá regression encoding.
- DB test dùng `tmp_path` (SQLite tạm), không đụng `data/monocle.db`.

## 2. Bản đồ test

| File | Phủ |
|---|---|
| `test_base_scraper.py` | template run(): thứ tự fetch→parse→dedup→enrich, gom errors, disabled |
| `test_rss_scraper.py` | RSSScraper cơ bản: parse feed, symbols, categories |
| `test_rss_features.py` | `_decode_feed` (utf-16/BOM/mislabel), `_parse_raw_date`, filter any/none, language |
| `test_cafef.py` | cafef: 2-step, Type=1, `/Date(ms)/` parse, content_selector |
| `test_tnck.py` | tnck: zone/page, epoch giây, phrase-ignore, relative URL |
| `test_vndirect.py` | vndirect: 1-step inline content, aggregator, cap 20 |
| `test_fireant.py` | fireant: happy path, thiếu/placeholder token, strip "Bearer ", self-disable 401/403 |
| `test_sentiment.py` | lexicon load, n-gram longest-first, negation, ngưỡng pos/neg |
| `test_store.py` | schema, INSERT OR IGNORE dedup, to_row/from_row |
| `test_dedup.py` | hash exact, mark_seen, normalize_title giữ dấu |
| `test_fuzzy_dedup.py` | rapidfuzz token_set_ratio ≥90, cross-domain, window 48h |
| `test_tickers.py` | tag_tickers gắn mã từ watchlist |
| `test_orchestrator.py` | run_cycle: classify+sentiment áp đúng chỗ, EN→neutral |
| `test_monitor_notify.py` | heartbeat/metrics ghi đúng bảng; format notify |

## 3. Chạy

```powershell
.venv\Scripts\python.exe -m pytest -q                       # tất cả
.venv\Scripts\python.exe -m pytest tests/test_fireant.py -v # 1 file
.venv\Scripts\python.exe -m pytest -k "dedup" -q            # theo keyword
```

## 4. Mẫu FakeHTTP

```python
class FakeHTTP:
    def __init__(self, xml): self.xml = xml
    def get_bytes(self, url, **kw): return self.xml.encode("utf-8")
    def get(self, url, **kw): return "<html>…</html>"
```
API scraper dùng `FakeResp`/`FakeHTTP` trả `.json()` + `.status_code` để test self-disable
(vd FireAnt `list_status=401` → assert `scraper.disabled` và không gọi tiếp watchlist còn lại).

## 5. Thêm test khi thêm nguồn

Tối thiểu: happy path (1 item → 1 Article đúng field), thiếu field → None, lỗi HTTP → errors
không rỗng nhưng không crash, date parsing đúng giờ VN. Nếu có auth: token thiếu/hết hạn →
disabled. Nếu encoding lạ: thêm fixture thật vào `tests/fixtures/`.

## 6. Câu hỏi mở

- Chưa có fixture cố định cho hose (JSON-feed qua feedparser) → chỉ verify thủ công 2026-07-25.
  Nên thêm để khoá regression. Xem [05-known-issues.md](05-known-issues.md).
