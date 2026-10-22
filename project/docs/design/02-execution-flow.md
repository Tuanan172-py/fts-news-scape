# Thiết kế — Luồng thực thi chi tiết (capture Bronze)

Cập nhật: 2026-10-22 · Đối tượng: dev muốn hiểu chính xác thứ tự thực thi của một chu kỳ thu thập.
Bức tranh toàn hệ: [00-end-to-end-architecture.md](00-end-to-end-architecture.md). Tham chiếu theo tên hàm, không theo số dòng.

Entry production là `python -m src.morninger` (job `capture` mỗi `morninger.capture_interval_minutes` = 10'):
`Morninger.run_capture()` gọi `Orchestrator.run_cycle()`, rồi `scripts/maintenance/backfill_deferred.py`,
rồi `scripts/capture_reconcile.py run` (tối đa mỗi 30'). `python -m src.orchestrator` vẫn chạy được độc lập.

## 1. Khởi tạo (1 lần) — `Orchestrator.__init__` (`src/orchestrator.py`)

Thứ tự dựng phụ thuộc:
`load_settings` → `setup_logging` → `ArticleStore` → `DBWriter` → `HTTPClient(rate_limit, max_retries)`
→ `DedupCache` → `Heartbeat` → `FileNotifier`.
Cuối `__init__`: `dedup.cleanup(max_age_days=30)` — xoá dấu vết seen quá 30 ngày.

## 2. Một cycle — `Orchestrator.run_cycle(names)`

```
names = names or list_domains()          # rỗng → cảnh báo, return 0
refresh_lock("scheduler") nếu đang giữ khoá
for name in names:
    cfg = load_domain_config(name)       # FileNotFoundError/ValueError → continue
    if not cfg.get("enabled", True): continue
    primary = build_scraper(cfg, http, dedup)   # KeyError → continue
    fallback = REGISTRY["_<fallback>"] nếu cfg["fallback"] hợp lệ
    heartbeat.record_start(name)
    result = run_with_fallback(primary, fallback) | run_with_retry(primary)
    for a in result.new:
        gộp classify_rule_based(title, text) vào a.categories (bỏ "uncategorized")
        writer.enqueue(a)
    heartbeat.record_result(result)
notifier.notify_articles(all_new); notifier.notify_cycle_summary(results)   # lỗi → log, bỏ qua
writer.flush()
_export_csv()       # <DATA_ROOT>/exports/articles-YYYY-MM-DD.csv nếu export.enabled
_wal_checkpoint()   # PRAGMA wal_checkpoint(TRUNCATE)
return len(all_new)
```

**Điểm mấu chốt:** capture chỉ gắn chuyên mục theo luật (`src/processor/classifier.py`). Không có
sentiment ở lớp này: `sentiment` do agent `article-processor` sinh trong Article Lane.

## 3. Bên trong một scraper — `BaseScraper.run()` (`src/core/base_scraper.py`)

Template method, **không override được**. Thứ tự cứng:

1. `errors=[]`, `started=monotonic()`. Nếu `self.disabled` → trả `ScrapeResult` rỗng ngay.
2. **fetch** — `fetch_list()` trong try; Exception → log + `errors.append("fetch_list: …")`, `raw_items=[]`.
3. **parse** — loop `parse_item(raw)`; Exception → warn + `errors.append`, continue. Chỉ giữ item truthy.
4. **ghi sổ rồi bỏ bản sao kỹ thuật** — mỗi article trước hết vào sổ phát hiện qua
   `dedup.discover(url, domain, via)`. Sau đó:
   - `dedup.is_duplicate(url, title)` → skip (hash exact).
   - cùng mã bài đã `captured` mà URL ở dạng khác, hoặc trùng khoá trong cùng chu kỳ → skip và ghi bí danh.
   - else → `new.append(a)`. Không có bước loại theo độ giống tiêu đề (rule 10).
5. **enrich** — CHỈ cho `a in new`. `enrich(a)` trong try; lỗi → warn + `errors.append`, **giữ article** (fallback summary). Sau đó `a.processed_at = now_vn_iso()` + `dedup.mark_seen(url, title, name)`.
6. Trả `ScrapeResult(scraper, fetched=len(raw_items), new, errors=list(self.errors), duration_s)`.

**Bất biến quan trọng:**
- Scraper **không ghi DB** — chỉ trả `ScrapeResult.new`.
- Article chỉ thành `captured` trong sổ phát hiện khi `store.insert_batch` ghi `articles` (cùng transaction).
- Mọi lỗi trở thành string trong `errors[]`, không bao giờ raise.

## 4. Enrich & cap chi tiết

Mỗi scraper có `max_details_per_cycle` (mặc định 30; tnck = 40, vndirect = 20; YAML `detail.max_details_per_cycle` ghi đè). Khi vượt cap:
`content_text = summary`, `metadata["detail_deferred"] = True`, không fetch nữa. Cơ chế này giữ
mỗi cycle bounded về số request chi tiết (bảo vệ rate limit + thời gian cycle).

RSS còn có tối ưu **inline content ≥500 ký tự** (`_MIN_INLINE_CONTENT` trong `src/scrapers/rss_generic.py`):
nếu feed đã nhúng nội dung đủ dài (vd VnEconomy `content:encoded`) → dùng luôn, bỏ qua fetch detail.

## 5. Hai chế độ CLI — `src/orchestrator.py::main(argv)`

- `python -m src.orchestrator` → **scheduler mode**: lấy `capture.lock` và khoá `scheduler` trong `pipeline_state`,
  `BlockingScheduler` + `IntervalTrigger(minutes=scheduler.interval_minutes)` (15), `coalesce=True`, `max_instances=1`,
  `misfire_grace_time=300`, chạy ngay lần đầu. Từ chối khởi động nếu morninger đang giữ khoá.
- `python -m src.orchestrator --once` → chạy đúng 1 cycle mọi domain bật rồi thoát (cũng lấy hai khoá trên).
- `python -m src.orchestrator --once cafef tnck` → chỉ 2 domain đó.
- `python -m src.morninger --once capture|derive|drift` → một lượt job tương ứng của morninger.

Cả hai mode đều `finally: orch.shutdown()` → nhả khoá, flush DBWriter, WAL checkpoint (gọi lặp an toàn).

## 6. Vòng đời tín hiệu dừng

SIGINT/SIGTERM → scheduler `shutdown(wait=False)` hoặc handler `--once` → `orch.shutdown()`:
`DBWriter.stop()` xả hết queue rồi join thread. Không mất bài đã enqueue.

## 7. Câu hỏi mở

- Đo 2026-09-17: một lượt job capture của morninger ≈ 7 phút (capture ~335s + backfill ≤90s) so với nhịp 10'
  (`config/settings.yaml`). Nếu vượt, `coalesce=True` gộp tick lỡ — không chồng cycle, nhưng tần suất thực giảm.
  Xem [../dev/05-known-issues.md](../dev/05-known-issues.md).
