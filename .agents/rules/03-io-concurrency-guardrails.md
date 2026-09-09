---
trigger: always_on
---
# 03 — I/O Concurrency, Staging & Windows File Lock Guardrails

Quy tắc bất biến cho mọi thao tác I/O (File & Database) trong hệ thống News-Scape trên môi trường Windows / OneDrive:

## 1. Nguyên tắc Ghi File An toàn (Safe Atomic Write)
- **CẤM ghi đè in-place trực tiếp**: Tuyệt đối không dùng `open(target_path, 'w')` trực tiếp trên các file dùng chung (CSV export, JSON task packets, checkpoint).
- **BẮT BUỘC dùng Staging**:
  - Mọi thao tác ghi file CSV phải đi qua `safe_atomic_write` từ `src.core.staging`.
  - Mọi thao tác ghi file JSON/packet phải đi qua `safe_json_dump` từ `src.core.staging`.
- **Windows File Lock Fallback**: Khi gặp `PermissionError` (do User đang mở file trong Excel/DB Browser), hệ thống phải tự động fallback sang file snapshot version (`stem_HHMMSS.ext`) và ghi warning log, không bao giờ để crash luồng thực thi chính.

## 2. Nguyên tắc Truy cập Database SQLite (.db)
- **Single-Writer Pattern**: Mọi thao tác ghi dữ liệu hàng loạt vào `data/monocle.db` bắt buộc phải đi qua `DBWriter` (queue thread) trong transaction `BEGIN IMMEDIATE`.
- **Read-Only Connections cho Reader**:
  - Mọi truy vấn đọc (query, export, check trạng thái, metrics) BẮT BUỘC dùng `ArticleStore._connect_ro()` hoặc URI `file:<path>?mode=ro`.
  - Giữ `PRAGMA busy_timeout = 30000` (30s) trên mọi connection để chống timeout lock giả.
- **Tách biệt Môi trường Phân tích của User**:
  - Khi User hoặc công cụ BI (DB Browser for SQLite, DBeaver) cần đọc/soi database, BẮT BUỘC sử dụng snapshot `data/monocle_review.db` (tạo qua `src/db/snapshot.py` / `scripts/db_snapshot.py`) để không mở transaction treo trên file DB chính.

## 3. Cách ly Môi trường OneDrive & SharePoint (Hybrid Workspace Invariants)

Đối với các dự án có thư mục làm việc (working tree) nằm trong vùng đồng bộ hai chiều của OneDrive / SharePoint:

- **Bất biến 1 — Tách biệt Git Database (`--separate-git-dir`)**:
  - TUYỆT ĐỐI KHÔNG để thư mục `.git` thực tế trong vùng đồng bộ OneDrive/SharePoint.
  - BẮT BUỘC khởi tạo hoặc di dời Git database ra ổ đĩa cục bộ (ví dụ: `C:\gitdirs\<repo>.git`).
  - Trong thư mục SharePoint, `.git` CHỈ ĐƯỢC PHÉP là 1 file text trỏ đường dẫn (`gitdir: <local_gitdir_path>`).

- **Bất biến 2 — Cách ly Virtual Environment (`.venv`)**:
  - TUYỆT ĐỐI KHÔNG tạo hoặc lưu trữ `.venv` bên trong thư mục đồng bộ SharePoint/OneDrive.
  - BẮT BUỘC đặt virtual environment tại thư mục chuyên dụng trên máy cục bộ (ví dụ: `C:\venvs\<project_name>`).
  - File `.gitignore` của dự án BẮT BUỘC phải chứa `.venv/`, `.pytest_cache/`, `__pycache__/`.

- **Bất biến 3 — Tách biệt Database Runtime (`.db`, `.db-wal`, `.db-shm`)**:
  - Không cho phép các tiến trình ghi dồn dập vào file SQLite nằm trên OneDrive đang bật sync.
  - BẮT BUỘC cấu hình biến môi trường (ví dụ: `MONOCLE_DB_PATH`) trỏ file DB chính ra ổ cục bộ (`C:\data\<project>\...`).
  - Chia sẻ dữ liệu cho User/BI trên SharePoint chỉ thông qua file snapshot tĩnh (ví dụ: `monocle_review.db`) hoặc file xuất bản (`final.csv`, reports).

- **Bất biến 4 — Ghim trạng thái tệp (Files On-Demand Pinning)**:
  - BẮT BUỘC bật chế độ *"Always keep on this device"* (`attrib -U +P /s /d "<repo>\*"`) để tránh việc OneDrive tự động dehydrate giải phóng dung lượng làm mất file mã nguồn khi biên dịch/thực thi.

## 4. Quy chuẩn Thực thi Script (Execution Guidelines cho Agents & Users)

Nhằm đảm bảo sự nhất quán và không gọi nhầm môi trường Python của hệ thống hay venv cũ:

- **Nguyên tắc cho Agents (Khi chạy tool `run_command`)**:
  - TUYỆT ĐỐI KHÔNG dùng tiền tố `.venv\Scripts\...` (đã bị xóa khỏi OneDrive).
  - BẮT BUỘC sử dụng đường dẫn tuyệt đối: `& "C:\venvs\news-scape\Scripts\python.exe" <script_path>` hoặc kích hoạt venv trước khi chạy.
  - Khi chạy các script pipeline trong `project/scripts/`:
    - Nếu `Cwd` là thư mục gốc: gọi `& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/<script>.py`.
    - Nếu `Cwd` là `project`: gọi `& "C:\venvs\news-scape\Scripts\python.exe" scripts/<script>.py`.
  - Khi chạy pytest: `& "C:\venvs\news-scape\Scripts\python.exe" -m pytest project/tests/ -v`.

- **Hướng dẫn cho Users (Khi thao tác bằng tay trong Terminal)**:
  - **Lựa chọn 1 (Kích hoạt 1 lần)**: Gõ `C:\venvs\news-scape\Scripts\activate` khi mở terminal. Sau đó mọi lệnh `python ...` hoặc `pytest ...` sẽ tự động chạy trong môi trường venv chuẩn.
  - **Lựa chọn 2 (Gọi trực tiếp)**: Gõ `C:\venvs\news-scape\Scripts\python <script_path> <arguments>`.
  - **Lựa chọn 3 (Auto-activate trong IDE)**: Trong VS Code / Cursor, nhấn `Ctrl + Shift + P` $\rightarrow$ `Python: Select Interpreter` $\rightarrow$ chọn `C:\venvs\news-scape\Scripts\python.exe`. Mọi terminal mở mới trong IDE sẽ tự động kích hoạt venv.


