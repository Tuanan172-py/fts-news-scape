# Operations — Triển khai & vận hành

Cập nhật: 2026-10-22 · Môi trường tham chiếu: Windows 11, Python 3.13, venv `C:\venvs\news-scape` (ngoài OneDrive, không tạo `.venv`).

Cây mã: `C:\src\news-scraper`. Dữ liệu ghi: `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`), đường dẫn do `src/core/paths.py` quyết định. Mọi lệnh dưới đây chạy với thư mục hiện tại là `project/`.

## 1. Cài đặt

```powershell
# Tạo venv + cài phụ thuộc
python -m venv C:\venvs\news-scape
C:\venvs\news-scape\Scripts\python.exe -m pip install -r requirements.txt
```

Phụ thuộc chính: `feedparser`, `requests`, `truststore`, `trafilatura`, `readability-lxml`,
`beautifulsoup4`+`lxml`, `rapidfuzz`, `pyvi`, `APScheduler`, `dbos`, `loguru`, `pyyaml`,
`jsonschema`, `openpyxl`, `pandas`+`pyarrow`. Danh sách đầy đủ: `requirements.txt`.

## 2. Cấu hình bắt buộc trước khi chạy

1. **secrets.yaml** (cho FireAnt): copy template rồi điền token.
   ```powershell
   Copy-Item config/secrets.yaml.example config/secrets.yaml
   ```

   Sửa `fireant_token: "<token>"`. File này **gitignored** — không commit. Lấy token:
   [../skills/fireant.md](../skills/fireant.md). (Dán kèm hay không kèm "Bearer " đều được — code tự cắt.)
2. Kiểm tra `config/settings.yaml` (DB `C:/data/news-scape/monocle.db`, capture 10 phút, re-derive 30 phút, rate 3s) và `config/watchlist.yaml` (30 mã).

## 3. Chạy

Vận hành không người trông dùng `ops_daemon` (Task Scheduler `news-scape-ops`): daemon tự giữ `morninger` sống và mở đợt Article Lane. Cài đặt: [ops-daemon.md](ops-daemon.md).

Chạy tay (dev, thử nghiệm):

```powershell
# Pipeline ban ngày liên tục — capture + re-derive Silver + drift trong 1 scheduler
C:\venvs\news-scape\Scripts\python.exe -m src.morninger

# Scheduler chỉ capture (15 phút) — nếu không cần downstream tự động
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator

# 1 cycle mọi domain rồi thoát (test/cron ngoài)
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator --once

# 1 cycle vài domain
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator --once cafef fireant tnck
```

⚠️ **Chỉ chạy MỘT scheduler.** Scheduler thứ hai bị khoá tiến trình từ chối. Khi daemon đã cài,
không khởi động thêm `morninger` bằng tay (xem [troubleshooting.md](troubleshooting.md)).

## 4. Theo dõi sức khoẻ

```powershell
# Trạng thái scraper + exit code (0 = OK, 1 = có vấn đề)
C:\venvs\news-scape\Scripts\python.exe -m src.monitor.health

# Điểm chạm của pipeline và đúng một lệnh kế tiếp (đọc-only)
C:\venvs\news-scape\Scripts\python.exe scripts/pipeline_radar.py status
```

Ngưỡng: `consecutive_failures ≥ 3` → CRITICAL; `status=failed` → FAILED; last_run > 30 phút →
STALE. Dữ liệu từ bảng `scraper_heartbeat` + `scraper_metrics`.

Log: `C:\data\news-scape\logs\monocle.log` (loguru, rotate 50MB, giữ 14 ngày).
Thông báo tin: `C:\data\news-scape\notifications\YYYY-MM-DD.log` (giờ VN) + stdout. **1 dòng/bài**.
Chỉ ghi tin khớp rule trong `config/notifications.yaml` (sources + has_symbol + keyword).
Chi tiết: [../design/05-notification-coverage.md](../design/05-notification-coverage.md).

## 5. Xem dữ liệu

- **CSV (Excel-friendly):** orchestrator tự xuất bài hôm nay cuối mỗi cycle ra
  `C:\data\news-scape\exports\articles-YYYY-MM-DD.csv` (khối `export` trong `config/settings.yaml`).
- **SQLite CLI:** `sqlite3 -readonly C:\data\news-scape\monocle.db`, hoặc mở bằng **DB Browser for SQLite** ở chế độ read-only
  (mẫu SQL ở [../dev/02-data-model-and-db.md](../dev/02-data-model-and-db.md)). Không ghi khi morninger đang chạy; file `-wal`/`-shm` là bình thường.

## 6. Chạy nền / như dịch vụ

- **Chuẩn:** `powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Register -Start`
  đăng ký `news-scape-ops` và `news-scape-ops-watchdog`. Daemon sinh `morninger` và ghi đầu ra vào
  `C:\data\news-scape\ops_logs\capture.log`. Không tạo thêm task riêng cho `morninger`.
- **Dev:** chạy trong terminal, dừng bằng Ctrl+C (SIGINT → graceful shutdown, flush DBWriter).
- **Cron ngoài:** dùng `--once` mỗi lần chạy, KHÔNG chạy song song với scheduler mode.

## 7. Backup

- DB 1 file → backup = copy `C:\data\news-scape\monocle.db` khi không có tiến trình ghi (hoặc dùng
  sqlite backup API). Orchestrator tự `wal_checkpoint(TRUNCATE)` cuối mỗi cycle.
- `config/` nằm trong git (trừ `secrets.yaml`).
- Dữ liệu dùng chung xuất bản một chiều lên SharePoint sandbox: [publisher.md](publisher.md).

## 8. Câu hỏi mở

- Chưa có script prune/rotation cho DB. Xem [../dev/05-known-issues.md](../dev/05-known-issues.md) §1.2.
