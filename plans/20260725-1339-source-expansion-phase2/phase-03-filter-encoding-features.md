# Phase 3 (Sprint C): Filter + Encoding + Language Features

## Context links

- Plan overview: [plan.md](plan.md)
- Verification report (source of truth): [reports/01-live-verification-report.md](reports/01-live-verification-report.md)
- RSSScraper hiện tại: `src/scrapers/rss_generic.py` | HTTP client: `src/crawler/http_client.py`
- Orchestrator (sentiment call site): `src/orchestrator.py` dòng 100-106
- RSS skill doc: `docs/skills/rss-sources.md`

## Overview

- **Date:** 2026-07-25
- **Description:** 3 tính năng nhỏ trong RSSScraper/pipeline để mở khóa các nguồn Phase 1/2:
  (1) per-domain keyword filter, (2) encoding hardening (BOM + utf-16), (3) `language`
  metadata + sentiment skip cho non-vi. Kèm cycle-time guard (đo, không code mới).
- **Priority:** HIGH — chạy TRƯỚC (hoặc song song phần "nguồn sạch" của Phase 1/2).
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights

- VietnamBiz feed là **utf-16**; Dân trí + Fed có **BOM** trước `<?xml` — `xml.lstrip()`
  hiện tại (rss_generic.py:71) chỉ xử lý whitespace, KHÔNG xử lý BOM/utf-16.
- `HTTPClient.get()` trả `resp.text` — requests decode theo header charset; nếu server
  không khai charset đúng → mojibake trước khi tới feedparser. Cần đường bytes.
- VietnamNet kinh-doanh.rss có **1000 items** — không filter sẽ ngập DB tin ngoài scope.
- Sentiment engine (pyvi + lexicon VN) chạy trên EN text → score rác. Skip sạch hơn.
- BaseScraper.run() là template method KHÔNG override — filter đặt trong
  `parse_item()` return None (item bị bỏ trước dedup) → zero thay đổi core. KISS.

## Requirements

1. YAML mới (optional, backward-compatible — domain cũ không đổi):
   ```yaml
   language: vi              # default "vi"; "en" cho nguồn quốc tế
   filter:
     any: ["chứng khoán", "cổ phiếu", "vn-index"]   # case-insensitive substring
     drop_unmatched: true    # default true khi có filter
   ```
2. Filter match trên `title + " " + summary` (lowercase); không có `filter` → giữ tất cả.
3. Feed fetch qua bytes + decode helper: utf-16 BOM (FF FE / FE FF), utf-16 no-BOM
   (heuristic null bytes), utf-8-sig (strip BOM), fallback utf-8 errors=replace.
   Giữ hành vi lstrip cũ (baodautu blank lines) — không regression.
4. `Article.metadata["language"]` set từ config; orchestrator skip sentiment nếu != "vi"
   → gán `("neutral", 0.0)` trực tiếp.
5. Log số item bị filter mỗi feed (INFO) để tune keyword.

## Architecture

```
HTTPClient.get_bytes() ──→ RSSScraper.fetch_list()
                              └─ _decode_feed(raw: bytes) -> str   # BOM/utf-16/lstrip
                              └─ feedparser.parse(text)
RSSScraper.parse_item()
   └─ build Article (metadata: language, feed_name, _inline_html)
   └─ _passes_filter(title, summary) → False ⇒ return None (skip, log-count)
Orchestrator.run_cycle()
   └─ if metadata.language == "vi": sentiment.analyze() else ("neutral", 0.0)
```

## Related code files

**Modify:**
- `src/crawler/http_client.py` — thêm `get_bytes()` (giống `get()` nhưng trả `resp.content`).
- `src/scrapers/rss_generic.py` — `_decode_feed()`, filter trong `parse_item`, `language`.
- `src/orchestrator.py` — sentiment skip theo language (3 dòng).
- `docs/skills/rss-sources.md` — document schema mới (filter, language, encoding notes).

**Create:**
- `tests/test_rss_features.py` — decode + filter + language tests.
- `tests/fixtures/vietnambiz_utf16.rss` (bytes), `tests/fixtures/dantri_bom.rss` — capture live.

**Delete:** none.

## Implementation Steps

1. **`HTTPClient.get_bytes()`** (`src/crawler/http_client.py`): copy body của `get()`,
   đổi `return resp.text` → `return resp.content`, type `bytes | None`. Không đụng `get()`.
2. **`_decode_feed()`** (`src/scrapers/rss_generic.py`, module-level, dễ test):
   ```python
   def _decode_feed(raw: bytes) -> str:
       """BOM/utf-16 hardening — vietnambiz utf-16, dantri/fed BOM, baodautu blank lines."""
       if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
           text = raw.decode("utf-16")           # BOM utf-16
       elif b"\x00" in raw[:400]:
           text = raw.decode("utf-16", errors="replace")  # utf-16 no BOM
       else:
           text = raw.decode("utf-8-sig", errors="replace")  # strip BOM utf-8 nếu có
       return text.lstrip("﻿ \t\r\n")       # giữ fix baodautu + BOM sót
   ```
3. **fetch_list**: `xml = self.http.get(...)` → `raw = self.http.get_bytes(...)`;
   `feedparser.parse(xml.lstrip())` → `feedparser.parse(_decode_feed(raw))`.
4. **Filter** trong `RSSScraper.__init__`: đọc `config.get("filter")` →
   `self.filter_terms = [t.lower() for t in filter_cfg.get("any", [])]`,
   `self.drop_unmatched = filter_cfg.get("drop_unmatched", True)`.
   Trong `parse_item`, sau khi có `summary_text`, trước khi build Article:
   ```python
   if self.filter_terms and self.drop_unmatched:
       haystack = f"{title} {summary_text}".lower()
       if not any(t in haystack for t in self.filter_terms):
           self._filtered += 1
           return None
   ```
   Reset `self._filtered = 0` trong `fetch_list`; log tổng filtered cuối `fetch_list`
   không được (chạy sau) → log trong `parse_item` không hợp — đơn giản: log DEBUG mỗi
   skip + để `ScrapeResult` phản ánh (fetched vs new chênh lệch là đủ quan sát).
5. **Language**: `__init__`: `self.language = config.get("language", "vi")`;
   `parse_item` metadata thêm `"language": self.language`.
6. **Orchestrator** (`run_cycle`, thay dòng 104-105):
   ```python
   if a.metadata.get("language", "vi") == "vi":
       a.sentiment, a.sentiment_score = self.sentiment.analyze(a.title, a.content_text)
   else:
       a.sentiment, a.sentiment_score = "neutral", 0.0
   ```
7. **Capture fixtures live**: `python - <<'PY'` script curl vietnambiz chung-khoan.rss
   (save raw bytes), dantri kinh-doanh.rss → `tests/fixtures/`. Verify utf-16/BOM thật.
8. **Tests** (`tests/test_rss_features.py`):
   - `_decode_feed`: utf-16 BOM fixture → parse ra title tiếng Việt đúng dấu; utf-8 BOM
     fixture → không còn `﻿`; blank-lines-before-xml case (regression baodautu);
     plain utf-8 unchanged.
   - Filter: config có `filter.any` → item không match bị drop, match giữ; không có
     `filter` → giữ tất cả; `drop_unmatched: false` → giữ tất cả.
   - Language: config `language: en` → metadata đúng; default vi.
   - Orchestrator-level: article metadata language=en → sentiment neutral 0.0 (unit test
     logic trực tiếp, không cần full orchestrator).
9. **Cycle-time guard** (đo, làm ở cuối Phase 1+2 rollout): sau mỗi batch enable domain,
   chạy `python scripts/run_once.py` và đọc "Cycle done ... in Ns" log; nếu steady-state
   tiến gần 12 phút → giảm `max_details_per_cycle` nguồn EN (10 → 5) hoặc set
   `extract_full: false` (xem Phase 2). Không viết code mới.
10. Chạy full test suite: `python -m pytest tests/ -v` — 80 cũ + mới pass.
11. Update `docs/skills/rss-sources.md`: schema `filter`/`language`, bảng encoding pitfall.

## Todo list

- [ ] `get_bytes()` trong HTTPClient
- [ ] `_decode_feed()` + fetch_list dùng bytes
- [ ] Keyword filter trong parse_item
- [ ] `language` config → metadata
- [ ] Orchestrator sentiment skip non-vi
- [ ] Capture fixtures live (vietnambiz utf-16, dantri BOM)
- [ ] tests/test_rss_features.py (≥8 cases)
- [ ] Full suite pass
- [ ] Update docs/skills/rss-sources.md

## Success Criteria

- vietnambiz utf-16 fixture parse ra tiếng Việt đúng dấu (không mojibake).
- dantri/fed BOM fixture parse OK; baodautu blank-lines regression test vẫn pass.
- Filter drop đúng theo `any` list; domain không có filter hành vi y hệt cũ.
- EN article: sentiment "neutral"/0.0, không gọi pyvi segment.
- 0 thay đổi hành vi cho 6 domain Phase 1 (chạy `run_once.py` so sánh).

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Null-byte heuristic false positive trên feed utf-8 có binary rác | Thấp | Chỉ check 400 bytes đầu (XML declaration region); test 6 feed cũ |
| Filter keyword quá hẹp → miss tin quan trọng | Trung bình | Bắt đầu list rộng, quan sát fetched-vs-new log, tune sau 24h |
| get_bytes làm chậm (không) — cùng 1 request | — | — |

## Security Considerations

- `_decode_feed` errors="replace" — không crash trên bytes độc hại; feedparser đã sanitize.
- Không thêm surface mới: filter/language là config đọc từ repo, không user input.

## Next steps

Phase 1 (VN RSS — vietnambiz/dantri/vietnamnet-kinh-doanh unblock) + Phase 2 (Intl RSS).
