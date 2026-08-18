# Operations — Triển khai & vận hành

Cập nhật: 2026-07-26 · Môi trường tham chiếu: Windows 11, Python 3.14, venv `.venv`.

## 1. Cài đặt

```powershell
# Tạo venv + cài phụ thuộc
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Phụ thuộc chính: `feedparser`, `requests`, `urllib3`, `truststore`, `trafilatura`,
`beautifulsoup4`+`lxml`, `rapidfuzz`, `pyvi`, `APScheduler`, `loguru`, `pyyaml`.

## 2. Cấu hình bắt buộc trước khi chạy

1. **secrets.yaml** (cho FireAnt): copy template rồi điền token.
   ```powershell
   Copy-Item config/secrets.yaml.example config/secrets.yaml
   ```
   Sửa `fireant_token: "<token>"`. File này **gitignored** — không commit. Lấy token:
   [../skills/fireant.md](../skills/fireant.md). (Dán kèm hay không kèm "Bearer " đều được — code tự cắt.)
2. Kiểm tra `config/settings.yaml` (interval 15 phút, rate 3s) và `config/watchlist.yaml` (30 mã).

## 3. Chạy

```powershell
# Pipeline ban ngày liên tục (production) — capture + re-derive Silver + drift trong 1 scheduler
.venv\Scripts\python.exe -m src.morninger

# Scheduler chỉ capture (15 phút) — nếu không cần downstream tự động
.venv\Scripts\python.exe -m src.orchestrator

# 1 cycle mọi domain rồi thoát (test/cron ngoài)
.venv\Scripts\python.exe -m src.orchestrator --once

# 1 cycle vài domain
.venv\Scripts\python.exe -m src.orchestrator --once cafef fireant tnck
```

⚠️ **Chỉ chạy MỘT scheduler.** Hai tiến trình scheduler → gấp đôi lưu lượng, nguy cơ chặn IP
(xem [troubleshooting.md](troubleshooting.md)).

## 4. Theo dõi sức khoẻ

```powershell
# Trạng thái scraper + exit code (0 = OK, 1 = có vấn đề)
.venv\Scripts\python.exe -m src.monitor.health
```
Ngưỡng: `consecutive_failures ≥ 3` → CRITICAL; `status=failed` → FAILED; last_run > 30 phút →
STALE. Dữ liệu từ bảng `scraper_heartbeat` + `scraper_metrics`.

Log: `logs/monocle.log` (loguru, rotate 50MB, giữ 14 ngày).
Thông báo tin: `data/notifications/YYYY-MM-DD.log` (giờ VN) + stdout. **1 dòng/bài**, format
tối giản `<emoji> <title> (chi tiết (<url>))` (emoji sentiment 🟢🔴🟡; giờ/tag/symbols/nguồn
tra trong DB). Chỉ ghi tin khớp rule trong `config/notifications.yaml` — thiết kế
**phủ toàn thị trường** (sources + has_symbol + keyword, ~98% coverage, chỉ loại lá cải cafebiz).
Chi tiết: [../design/05-notification-coverage.md](../design/05-notification-coverage.md).
Grep được: `grep HPG`, `grep 🔴`.

## 5. Xem dữ liệu

- **CSV (Excel-friendly):** `python scripts/export_csv.py` → `data/exports/articles-YYYYMMDD.csv`
  (utf-8-sig, mở Excel không lỗi font). Lọc: `--today`, `--days 3`, `--domain cafef fireant`,
  `--with-symbols`, `--limit N`, `--out <path>`. Bỏ cột HTML/text thô, giữ cột review
  (fetched_at, published_at, nguồn, mã, categories, sentiment, score, title, summary, url).
- **SQLite CLI:** `sqlite3 data/monocle.db` rồi chạy SQL (mẫu ở [../dev/02-data-model-and-db.md](../dev/02-data-model-and-db.md) §6).
- **DB Browser for SQLite:** mở `data/monocle.db`. ⚠️ Mở **read-only** hoặc đóng orchestrator trước
  khi ghi, tránh tranh WAL. Sau khi orchestrator ghi, file `-wal`/`-shm` xuất hiện là bình thường.

## 6. Chạy nền / như dịch vụ

- **Đơn giản (dev):** chạy trong terminal/`Start-Process`, dừng bằng Ctrl+C (SIGINT → graceful
  shutdown, flush DBWriter).
- **Bền hơn:** Task Scheduler (Windows) hoặc NSSM để chạy `-m src.morninger` (pipeline đầy đủ)
  hoặc `-m src.orchestrator` như service; đảm bảo **chỉ 1 instance** (không đặt cả scheduler mode
  lẫn cron `--once`).
- **Cron ngoài:** nếu muốn điều phối bằng cron/Task Scheduler thay APScheduler → dùng `--once`
  mỗi lần chạy, KHÔNG chạy scheduler mode song song.

## 7. Backup

- DB 1 file → backup = copy `data/monocle.db` (nên `PRAGMA wal_checkpoint` hoặc đóng orchestrator
  trước để gộp WAL). Orchestrator tự `wal_checkpoint(TRUNCATE)` cuối mỗi cycle.
- Lexicon `data/lexicon/*.tsv` + `config/` nằm trong git (trừ secrets).

## 8. Câu hỏi mở

- Chưa có script prune/rotation cho DB (đang ~550MB). Xem [../dev/05-known-issues.md](../dev/05-known-issues.md) §1.2.
