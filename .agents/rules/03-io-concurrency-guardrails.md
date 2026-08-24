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

## 3. Cách ly Môi trường OneDrive
- Đối với môi trường có client OneDrive sync đang chạy:
  - Cho phép override đường dẫn runtime data ra ngoài OneDrive bằng biến môi trường `MONOCLE_DATA_DIR` hoặc `MONOCLE_DB_PATH`.
