# Hướng dẫn Chạy Scripts & Quản lý Môi trường Venv Cục bộ (User Guide)

> **Dành cho Người dùng & Vận hành viên:** Hướng dẫn các câu lệnh chuẩn để chạy pipeline, kiểm thử và xử lý dữ liệu với môi trường Python cách ly ngoài OneDrive tại `C:\venvs\news-scape`.

---

## 1. Môi trường Thực thi (Python Environment)

| Thông số | Giá trị |
| :--- | :--- |
| **Đường dẫn Venv** | `C:\venvs\news-scape` |
| **Python Binary** | `C:\venvs\news-scape\Scripts\python.exe` |
| **Database Chính** | `C:\data\news-scape\monocle.db` (biến môi trường `MONOCLE_DB_PATH`) |
| **Working Tree** | `C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape` |

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
python scripts/run_once.py
python scripts/verify_gold_quality.py --apply
pytest tests/ -v
```

### Cách 2: Gọi Trực tiếp Đường dẫn Tuyệt đối (Không cần activate)
Phù hợp khi chạy một lệnh đơn lẻ hoặc paste vào Task Scheduler:
```powershell
# Chạy từ thư mục gốc
C:\venvs\news-scape\Scripts\python project/scripts/run_once.py

# Chạy kiểm thử chất lượng Gold
C:\venvs\news-scape\Scripts\python project/scripts/verify_gold_quality.py

# Áp dụng hạ cờ vào database
C:\venvs\news-scape\Scripts\python project/scripts/verify_gold_quality.py --apply
```

### Cách 3: Tự động Kích hoạt trong VS Code / Cursor
1. Nhấn tổ hợp phím `Ctrl + Shift + P`.
2. Gõ `Python: Select Interpreter` $\rightarrow$ Nhập hoặc chọn: `C:\venvs\news-scape\Scripts\python.exe`.
3. Từ lúc này, mọi tab Terminal mở trong VS Code sẽ **tự động kích hoạt** môi trường này. Bạn chỉ cần gõ:
```powershell
python scripts/run_once.py
```

---

## 3. Các Lệnh Pipeline Thường dùng Hàng ngày

```powershell
# 1. Chạy 1 chu kỳ cào tin & đồng bộ Silver
C:\venvs\news-scape\Scripts\python project/scripts/run_once.py

# 2. Kiểm kê tồn đọng L1 & Gold
C:\venvs\news-scape\Scripts\python project/scripts/l1_backlog.py

# 3. Gom lô bài viết chuyển giao cho Subagent
C:\venvs\news-scape\Scripts\python project/scripts/l1_route.py --review missed --mini-batch 25
C:\venvs\news-scape\Scripts\python project/scripts/agent_export.py --all

# 4. Giao hàng cho người dùng (Xuất file final.csv)
C:\venvs\news-scape\Scripts\python project/scripts/compile_users.py --all
C:\venvs\news-scape\Scripts\python project/scripts/run_user_workflow.py --date today

# 5. Xuất snapshot database an toàn lên SharePoint để review
C:\venvs\news-scape\Scripts\python scripts/db_snapshot.py

# 6. Chạy bộ kiểm thử tự động
C:\venvs\news-scape\Scripts\python -m pytest project/tests/ -q
```

---

## 4. Quản lý Thư viện (Pip Packages)

Khi cần cài thêm gói thư viện mới:
```powershell
# Cài đặt gói vào venv cục bộ
C:\venvs\news-scape\Scripts\pip install <package_name>

# Cập nhật danh sách vào requirements.txt để đồng bộ cho các máy khác
C:\venvs\news-scape\Scripts\pip freeze > project/requirements.txt
```
