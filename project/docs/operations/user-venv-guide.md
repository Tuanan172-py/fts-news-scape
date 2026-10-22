# Hướng dẫn Chạy Scripts & Quản lý Môi trường Venv Cục bộ (User Guide)

> **Dành cho Người dùng & Vận hành viên:** Hướng dẫn các câu lệnh chuẩn để chạy pipeline, kiểm thử và xử lý dữ liệu với môi trường Python cách ly ngoài OneDrive tại `C:\venvs\news-scape`. Không tạo `.venv` cục bộ.

---

## 1. Môi trường Thực thi (Python Environment)

| Thông số | Giá trị |
| :--- | :--- |
| **Đường dẫn Venv** | `C:\venvs\news-scape` |
| **Python Binary** | `C:\venvs\news-scape\Scripts\python.exe` |
| **Thư mục dữ liệu** | `C:\data\news-scape` (biến môi trường `MONOCLE_DATA_DIR`) |
| **Database Chính** | `C:\data\news-scape\monocle.db` (ghi đè bằng `MONOCLE_DB_PATH`) |
| **Working Tree** | `C:\src\news-scraper` |

Mọi lệnh `scripts/...` chạy với thư mục hiện tại là `project/`.

---

## 2. Ba (03) Cách Chạy Script Đơn Giản

### Cách 1: Kích hoạt Venv 1 lần / Phiên làm việc (Khuyến nghị cho Terminal)
- **Trong PowerShell (PS)**: Bắt buộc dùng đuôi `.ps1` và dấu `&`:
  ```powershell
  & "C:\venvs\news-scape\Scripts\Activate.ps1"
  ```
- **Trong Command Prompt (CMD)**:
  ```cmd
  C:\venvs\news-scape\Scripts\activate.bat
  ```
Khi thấy tiền tố `(news-scape)` xuất hiện ở đầu dòng lệnh, bạn có thể gõ ngắn gọn:
```powershell
cd project
python scripts/pipeline_radar.py status
python scripts/run_once.py
```

### Cách 2: Gọi Trực tiếp Đường dẫn Tuyệt đối (Không cần activate)
Phù hợp khi chạy một lệnh đơn lẻ:
```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --where
```

### Cách 3: Tự động Kích hoạt trong VS Code / Cursor
1. Nhấn tổ hợp phím `Ctrl + Shift + P`.
2. Gõ `Python: Select Interpreter` $\rightarrow$ Nhập hoặc chọn: `C:\venvs\news-scape\Scripts\python.exe`.
3. Từ lúc này, mọi tab Terminal mở trong VS Code sẽ **tự động kích hoạt** môi trường này.

---

## 3. Các Lệnh Pipeline Thường dùng Hàng ngày

Vận hành hằng ngày do `ops_daemon` đảm nhận ([ops-daemon.md](ops-daemon.md)). Các lệnh tay, chạy trong `project/` sau khi kích hoạt venv:

```powershell
# 1. Xem điểm chạm và đúng một lệnh kế tiếp (đọc-only, chạy đầu tiên)
python scripts/pipeline_radar.py status

# 2. Trạng thái daemon: mức, đợt, breaker
python scripts/ops_daemon.py status

# 3. Chạy 1 chu kỳ cào tin & đồng bộ Silver
python scripts/run_once.py

# 4. Đợt Article Lane tay (chỉ khi daemon không chạy đợt; xem ops-daemon-reference.md §7)
python scripts/article_run.py --wave <mã> --date <YYYY-MM-DD> --limit <n> --batch 100
python scripts/article_run.py --wave <mã> --finish

# 5. Giao hàng cho người dùng: C:\data\news-scape\users\output\<user>\<YYYY-MM-DD>.xlsx
python scripts/write_user_output.py --date today

# 6. Xuất bản ngày hôm qua lên SharePoint sandbox (xem publisher.md)
python scripts/publish.py --date yesterday --dry-run

# 7. Chạy kiểm thử của một package (đọc trước docs/knowledge/facts/tests-must-not-write-operational-db.md)
python -m pytest tests/<package>/ -q
```

---

## 4. Quản lý Thư viện (Pip Packages)

Khi cần cài thêm gói thư viện mới:
```powershell
# Cài đặt gói vào venv
C:\venvs\news-scape\Scripts\pip install <package_name>
```
Rồi thêm tay một dòng `<package_name>>=<phiên bản>` vào `project/requirements.txt` (file có chú thích theo từng dòng; không ghi đè bằng `pip freeze`).
