# Thiết kế — Luồng thực thi chi tiết

Cập nhật: 2026-07-26 · Đối tượng: dev muốn hiểu chính xác thứ tự thực thi.
Mọi tham chiếu dạng `file:line` theo mã hiện tại.

## 1. Khởi tạo (1 lần) — `Orchestrator.__init__` (`orchestrator.py:48-65`)

Thứ tự dựng phụ thuộc:
`load_settings` → `setup_logging` → `ArticleStore` → `DBWriter` → `HTTPClient(rate_limit, max_retries)`
→ `DedupCache` → `Heartbeat` → `FileNotifier` → `SentimentEngine`.
Cuối `__init__`: `dedup.cleanup(max_age_days=30)` (`orchestrator.py:63`) — xoá dấu vết seen quá 30 ngày.

## 2. Một cycle — `run_cycle(names)` (`orchestrator.py:69-121`)

```
names = names or list_domains()          # rỗng → cảnh báo, return 0        :69-72
cycle_start = time.monotonic()                                              :73-74
for name in names:                                                          :77
    cfg = load_domain_config(name)       # FileNotFoundError/ValueError → continue :79-81
    if not cfg.get("enabled", True): continue                              :83-84
    primary = build_scraper(cfg, http, dedup)   # KeyError → continue      :87-89
    fallback = build_scraper(_<fb>) nếu cfg["fallback"] hợp lệ             :92-95
    heartbeat.record_start(name)                                           :97
    result = run_with_fallback(primary, fallback) | run_with_retry(primary) :98-99
    for a in result.new:                                                   :100
        cats = classify_rule_based(a.title, a.content_text)                :101
        merge cats (bỏ "uncategorized", dedupe) vào a.categories           :102-103
        if a.metadata.get("language","vi") == "vi":                        :104
            a.sentiment, a.sentiment_score = sentiment.analyze(title, text) :105-106
        else:                                                              :107
            a.sentiment, a.sentiment_score = "neutral", 0.0                :108-109
        writer.enqueue(a)                                                  :110
    heartbeat.record_result(result)                                        :111
notifier.notify_articles(all_new)                                          :115
notifier.notify_cycle_summary(results)                                     :116-117
_wal_checkpoint()   # PRAGMA wal_checkpoint(TRUNCATE)                       :118
return len(all_new)                                                        :119-121
```

**Điểm mấu chốt:** `classify` + `sentiment` chạy **trong orchestrator**, sau khi scraper
trả `result.new`, TRƯỚC khi enqueue. Scraper không hề biết sentiment.

## 3. Bên trong một scraper — `BaseScraper.run()` (`base_scraper.py:33-83`)

Template method, **không override được**. Thứ tự cứng:

1. `errors=[]`, `started=monotonic()`. Nếu `self.disabled` → trả `ScrapeResult` rỗng ngay (`:36-38`).
2. **fetch** — `fetch_list()` trong try; Exception → log + `errors.append("fetch_list: …")`, `raw_items=[]` (`:40-45`).
3. **parse** — loop `parse_item(raw)`; Exception → warn + `errors.append`, continue. Chỉ giữ item truthy (`:48-56`).
4. **dedup** (`:58-67`) — `fuzzy = cfg.get("fuzzy_dedup", True)`. Mỗi article:
   - `dedup.is_duplicate(url, title)` → skip (hash exact).
   - fuzzy và `dedup.is_similar_title(title, name)` → **`mark_seen` ngay** rồi skip (khỏi so lại cycle sau).
   - else → `new.append(a)`.
5. **enrich** — CHỈ cho `a in new` (`:69-77`). `enrich(a)` trong try; lỗi → warn + `errors.append`, **giữ article** (fallback summary). Sau đó `a.processed_at = now_vn_iso()` + `dedup.mark_seen(url, title, name)`.
6. Trả `ScrapeResult(scraper, fetched=len(raw_items), new, errors=list(self.errors), duration_s)` (`:82-83`).

**Bất biến quan trọng:**
- Scraper **không ghi DB** — chỉ trả `ScrapeResult.new`.
- Article "sạch" chỉ được `mark_seen` **sau enrich** (`:77`); article bị fuzzy-loại thì `mark_seen` ngay (`:65`).
- Mọi lỗi trở thành string trong `errors[]`, không bao giờ raise.

## 4. Enrich & cap chi tiết

Mỗi scraper có `max_details_per_cycle` (RSS/cafef/tnck/fireant = 30, vndirect = 20). Khi vượt cap:
`content_text = summary`, `metadata["detail_deferred"] = True`, không fetch nữa. Cơ chế này giữ
mỗi cycle bounded về số request chi tiết (bảo vệ rate limit + thời gian cycle).

RSS còn có tối ưu **inline content ≥500 ký tự** (`_MIN_INLINE_CONTENT`, `rss_generic.py:25,88-95`):
nếu feed đã nhúng nội dung đủ dài (vd VnEconomy `content:encoded`) → dùng luôn, bỏ qua fetch detail.

## 5. Hai chế độ CLI — `main(argv)` (`orchestrator.py:171-192`)

```
once  = "--once" in argv                                    :172
names = [a for a in argv if not a.startswith("--")] or None :173
```

- `python -m src.orchestrator` → **scheduler mode**: `BlockingScheduler` + `IntervalTrigger(minutes=15)`,
  `coalesce=True`, `max_instances=1`, `misfire_grace_time=300`, `next_run_time=now` (chạy ngay lần đầu).
  Đảm bảo "1 cycle xong mới chạy cycle tiếp".
- `python -m src.orchestrator --once` → chạy đúng 1 cycle mọi domain rồi thoát.
- `python -m src.orchestrator --once cafef tnck` → chỉ 2 domain đó.

Cả 2 mode đều `finally: orch.shutdown()` → flush DBWriter (graceful).

## 6. Vòng đời tín hiệu dừng

SIGINT/SIGTERM → scheduler `shutdown(wait=False)` hoặc `--once` handler → `orch.shutdown()`:
`DBWriter.stop(timeout=30)` xả hết queue rồi join thread (`writer.py:70-76`). Không mất bài đã enqueue.

## 7. Câu hỏi mở

- Tổng thời gian 1 cycle khi bật đủ 22 domain (đặc biệt cafef/fireant chạy theo 30 mã watchlist,
  ~90s mỗi nguồn) chưa được đo chính thức so với interval 15 phút. Nếu vượt, `coalesce=True` sẽ
  gộp tick lỡ — không chồng cycle, nhưng tần suất thực giảm. Xem [../dev/05-known-issues.md](../dev/05-known-issues.md).
