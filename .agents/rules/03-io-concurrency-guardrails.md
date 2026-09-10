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

## 5. Bất biến Xuất Dữ liệu & Chống Xung đột Đồng bộ OneDrive (Bulk Export & OneDrive Anti-Fork Invariants)

Nhằm loại bỏ hoàn toàn tình trạng OneDrive tự động tạo các cặp file song song mang tên máy trạm (`<name>-<HOSTNAME>.<ext>`, ví dụ: `2019-01-28-FPA-AnPT.xlsx`):

1. **Byte-level Equality Pre-replacement Check (Tầng Staging)**:
   - Trước khi thực hiện `os.replace` trên bất kỳ file nào nằm trong vùng đồng bộ OneDrive, tầng Staging (`safe_atomic_write` trong `src.core.staging`) BẮT BUỘC phải so sánh kích thước file (`st_size`) và mã băm `SHA-256` của file tạm với file đích hiện có.
   - Nếu nội dung nhị phân giống hệt: HỦY file `.tmp` và trả về thành công mà không chạm vào file đích, triệt tiêu sự kiện File System Watcher kích hoạt sync thừa.

2. **Smart Idempotency Skip Guard (Tầng Giao hàng Deliverable)**:
   - Mọi hàm ghi deliverable cho người dùng (`user_output.py`, periodic reports) BẮT BUỘC phải kiểm tra checkpoint:
     ```python
     if not force and file_path.exists() and not new and not upgraded:
         counts[user] = counts.get(user, 0) + len(finals)
         continue
     ```
   - Nghiêm cấm chạy vòng lặp ghi đè hàng loạt hàng trăm file nhị phân (`.xlsx`) trong thời gian ngắn mà không có cơ chế bỏ qua hoặc cờ `--force`.

3. **Quy chuẩn Lệnh Shell Bảo trì (PowerShell vs Python Script)**:
   - **CẤM tuyệt đối** đưa các one-liner PowerShell phức tạp có chứa biến `$_`, dấu ống dẫn `|`, hoặc khối mã `{ ... }` bên trong chuỗi nháy kép `"..."` cho người dùng hoặc gọi qua `run_command`, vì shell sẽ nội suy `$_` thành rỗng gây lỗi `The term '.Name' is not recognized`.
   - **BẮT BUỘC dùng Script Python**: Mọi thao tác quét file, kiểm tra xung đột, lọc thư mục hoặc dọn dẹp bảo trì phải được đóng gói thành file Python độc lập (ví dụ: `scripts/maintenance/<script>.py`) có cấu hình `sys.stdout.reconfigure(encoding="utf-8")`.

4. **Bất biến Thúc đẩy File Conflict Mới hơn (Promote-Before-Delete Invariant)**:
   - Trong môi trường OneDrive/SharePoint, khi xảy ra xung đột đồng bộ, OneDrive thường giữ nguyên tên file gốc cho bản trên đám mây (thường là bản cũ), và đổi tên bản sửa đổi MỚI NHẤT của người dùng cục bộ thành `<file>-<HOSTNAME>.<ext>`.
   - **CẤM tuyệt đối xóa mù quáng bản `<HOSTNAME>`**: Khi xử lý xung đột, BẮT BUỘC phải so sánh thời gian sửa đổi (`st_mtime`) và mã băm SHA-256.
   - Nếu bản `<HOSTNAME>` mới hơn: BẮT BUỘC **PROMOTE** (sao chép ghi đè bản `<HOSTNAME>` thành file chính thức, sau đó mới xóa file có hậu tố) để không làm mất các chỉnh sửa của người dùng.
   - **Dọn dẹp & Hợp nhất Tự động**: Sử dụng công cụ chuẩn `project/scripts/maintenance/clean_onedrive_conflicts.py` (đã tích hợp sẵn logic so sánh SHA256 và tự động Promote khi conflict mới hơn).


