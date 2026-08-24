# TOOL_REGISTRY.md — Danh mục Công cụ & Bậc thang Suy giảm (H4)

Tài liệu này quản lý danh sách các công cụ thực thi trong hệ thống News-Scape, các điều kiện tiên quyết và cơ chế **Suy giảm An toàn (Degrade-Don't-Fail)** khi thiếu công cụ.

---

## 1. Danh mục Công cụ Lõi (Core Tools Manifest)

| Tool ID | Tên công cụ | Mục đích | Lệnh kiểm tra tình trạng | Fallback khi thiếu (Degrade Ladder) |
|:---|:---|:---|:---|:---|
| `python` | Python Runtime (3.10+) | Chạy core pipelines, scripts, CLI | `python --version` | **Hard Stop** (Bắt buộc phải có). |
| `pytest` | Pytest Framework | Chạy bộ kiểm thử tự động Unit/Integ | `python -m pytest --version` | Chạy thủ công qua `python -m unittest`. |
| `sqlite3` | SQLite Engine (WAL mode) | Lưu trữ monocle.db & harness.db | `python -c "import sqlite3; print(sqlite3.sqlite_version)"` | **Hard Stop** (Bắt buộc cho Durable layer). |
| `trafilatura` | Web Content Extractor | Bóc tách bài viết cào từ web | `python -c "import trafilatura"` | Fallback sang Regex / BeautifulSoup thô. |
| `rapidfuzz` | String Similarity Matcher | Khử trùng lặp tiêu đề tin tức | `python -c "import rapidfuzz"` | Fallback sang so sánh chuỗi chính xác (exact match). |

---

## 2. Nguyên tắc Suy giảm An toàn (Degrade-Don't-Fail)

1. Khi một công cụ không thiết yếu bị thiếu hoặc lỗi, hệ thống ghi log cảnh báo và hạ cấp sang phương án dự phòng (fallback), **tuyệt đối không để crash toàn bộ luồng pipeline**.
2. Mọi sự cố suy giảm công cụ phải được ghi nhận vào bảng `intervention` hoặc `backlog` để xử lý sau.
