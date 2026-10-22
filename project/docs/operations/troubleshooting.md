# Operations — Xử lý sự cố

Cập nhật: 2026-10-22 · Triệu chứng → nguyên nhân → cách xử. Lớp capture (scrape) và DB.
Sự cố của đợt Article Lane, breaker, mandate: [ops-daemon.md §4](ops-daemon.md). Sự cố xuất bản: [publisher.md §4](publisher.md).

## 1. Nhiều scheduler chạy song song

**Triệu chứng:** số bài tăng bất thường ở mọi domain, số liệu heartbeat nhảy, lưu lượng ngoài gấp đôi.
**Nguyên nhân:** ≥2 tiến trình `python -m src.morninger` / `python -m src.orchestrator` cùng chạy.
`--once` bị khoá `capture.lock` và khoá `scheduler` trong `pipeline_state` từ chối khi đã có tiến trình cào.
**Kiểm tra (Windows):**
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -like '*src.orchestrator*' -or $_.CommandLine -like '*src.morninger*' } |
  Select-Object ProcessId, CommandLine
```
**Xử:** giữ 1, tắt phần còn lại: `Stop-Process -Id <PID>`. Khi `ops_daemon` đang chạy, giữ bản `morninger`
do daemon sinh. Dữ liệu không hỏng (WAL + INSERT OR IGNORE), chỉ cần dừng lãng phí.
Xem [../dev/05-known-issues.md](../dev/05-known-issues.md) §1.1.

## 2. FireAnt không lấy được tin

**Triệu chứng:** log `[fireant] auth failed (HTTP 401)` hoặc `no token … disabled`.
**Nguyên nhân & xử:**
- Chưa có token / còn `PASTE_*` → điền `config/secrets.yaml` `fireant_token`.
- Token hết hạn (401/403) → scraper self-disable 1 lần/cycle. Lấy token mới: [../skills/fireant.md](../skills/fireant.md).
- Dán token kèm `"Bearer "` → **không sao**, code tự cắt (`src/scrapers/fireant.py`).

## 3. Feed RSS lỗi encoding / mojibake

**Triệu chứng:** tiếng Việt hiển thị `Ã¡`, `Ä‘`… hoặc feed parse rỗng.
**Nguyên nhân:** encoding lạ (utf-16 mislabel, BOM, brotli).
**Xử:** `_decode_feed` xử đa số. Nếu vẫn lỗi: kiểm tra HTTP client **không** khai `Accept-Encoding`
(tránh brotli rác), và bytes thô lấy qua `get_bytes`. Thêm fixture thật vào `tests/fixtures/` +
mở rộng `_decode_feed` nếu gặp pattern mới.

## 4. Domain trả 0 bài liên tục

**Triệu chứng:** health báo STALE/FAILED cho 1 domain.
**Kiểm tra:** `python -m src.monitor.health`, hoặc đọc-only `SELECT * FROM scraper_heartbeat WHERE scraper_name='<name>';`
**Nguyên nhân thường gặp:**
- Feed dormant (0 `<item>`) → xem xét `enabled: false`.
- Redirect 302 (vnexpress chung-khoan) → đổi feed URL.
- Endpoint đổi (Stockbiz đã chết) → cập nhật/loại nguồn.
- TLS chain lỗi (hnx) → đảm bảo `truststore` cài được.

## 5. SQLITE_BUSY / DB khoá

**Triệu chứng:** lỗi database is locked.
**Nguyên nhân:** DB Browser (hoặc tiến trình khác) đang ghi song song với morninger/orchestrator.
**Xử:** đóng công cụ ghi ngoài, hoặc mở read-only. Ghi bảng `articles` chỉ nên qua DBWriter.
WAL + `busy_timeout=30000` chịu được reader song song, không chịu 2 writer.

## 6. Cycle chậm / bỏ tick

**Triệu chứng:** nhịp capture thực tế dài hơn `morninger.capture_interval_minutes` (10 phút).
**Nguyên nhân:** tổng thời gian scrape (đặc biệt cafef/fireant × 30 mã) + phần bù `backfill_deferred`
vượt interval; `coalesce=True` gộp tick lỡ.
**Xử:** giảm watchlist, giảm `pages_per_cycle`/cap detail, hoặc tăng `morninger.capture_interval_minutes`
(orchestrator chạy riêng dùng `scheduler.interval_minutes`).

## 7. Nhật ký nhanh

| Nơi | Nội dung |
|---|---|
| `C:\data\news-scape\logs\monocle.log` | log tổng (loguru), lỗi fetch/parse/enrich |
| `C:\data\news-scape\ops_logs\capture.log` | đầu ra `morninger` do `ops_daemon` sinh |
| `C:\data\news-scape\notifications\*.log` | tin đã bắn (1 dòng/bài; xem [../design/05-notification-coverage.md](../design/05-notification-coverage.md)) |
| `C:\data\news-scape\exports\articles-*.csv` | bài hôm nay dạng CSV (auto cuối mỗi cycle, mở Excel) |
| `scraper_heartbeat` | trạng thái mỗi scraper |
| `scraper_metrics` | fetched/new/errors/duration mỗi cycle |
