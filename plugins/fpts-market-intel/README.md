# FPTS Market Intel — Unified Lakehouse Plugin

Plugin khai phá dữ liệu tin tức tài chính và phân tích tâm lý thị trường dành cho chuyên viên phân tích FPTS trên nền tảng **Antigravity (AGY)** và **Gemini IDE**.

---

## 1. Tính Năng Nổi Bật

- **Zero-Token Local Execution**: Quét trực tiếp hồ dữ liệu Parquet (OBT 22 cột) trên máy trạm thông qua DuckDB nhúng, tốc độ dưới 0.5s, không tốn token LLM cho tầng trích xuất.
- **Zero-Config Auto-Discovery**: Tự động nhận diện shortcut thư mục SharePoint OneDrive (`FRA_DataIngestion - news-data`) trên mọi máy trạm Windows.
- **Bộ 4 Kỹ Năng Tích Hợp**:
  1. `news-ticker-screener`: Soi tin tức chuyên sâu theo từng mã cổ phiếu (tiêu đề, tóm tắt, luận điểm, hàm ý dòng tiền, sắc thái).
  2. `news-daily-brief`: Tổng hợp bản tin sáng (Morning Brief) theo Watchlist cá nhân hoặc VN30.
  3. `news-sector-pulse`: Đo lường xung lực & ma trận tâm lý 11 nhóm ngành GICS và tin tức vĩ mô.
  4. `news-lakehouse-explorer`: Kiểm toán độ tươi dữ liệu (`_manifest/latest.json`) và chạy các câu lệnh SQL DuckDB tùy biến.

---

## 2. Hướng Dẫn Kích Hoạt & Sử Dụng

### A. Kích hoạt trong Antigravity (AGY) hoặc Gemini IDE
Khi mở AGY / Gemini IDE, plugin xuất hiện trong tab **Plugins** với tên **`fpts-market-intel`**. 
Chuyên viên có thể gạt công tắc **Bật (Enable)** hoặc bấm trực tiếp các câu prompt gợi ý có sẵn:
- *"Soi tin tức mã HPG trong 3 ngày gần nhất"*
- *"Tổng hợp Morning Brief cho danh mục hôm nay"*
- *"Quét nhịp đập và sắc thái ngành Ngân hàng tuần qua"*
- *"Kiểm tra độ tươi dữ liệu Lakehouse hôm nay"*

### B. Kiểm tra Đường dẫn Dữ liệu (Shortcut OneDrive)
Plugin đọc dữ liệu từ shortcut SharePoint đã đồng bộ về máy:
- **SharePoint Site**: `https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion`
- **Thư mục cục bộ chuẩn**: `%USERPROFILE%\OneDrive - fpts.com.vn\Shortcuts\FRA_DataIngestion - news-data`
*(Nếu lưu tại vị trí khác, có thể thiết lập biến môi trường `NEWS_DATA_ROOT` trỏ tới thư mục trên).*

---

## 3. Kiến Trúc & Cấu Trúc Thư Mục

```text
fpts-market-intel/
├── plugin.json                      # Manifest đăng ký plugin & suggestedPrompts
├── README.md                        # Hướng dẫn sử dụng
├── rules/
│   └── AGENTS.md                    # Guardrails miền tài chính & chống ảo giác
├── skills/
│   ├── news-ticker-screener/        # Kỹ năng soi mã cổ phiếu
│   ├── news-daily-brief/            # Kỹ năng lập Morning Brief
│   ├── news-sector-pulse/           # Kỹ năng phân tích ngành & vĩ mô
│   └── news-lakehouse-explorer/     # Kỹ năng kiểm toán & chạy SQL
└── tools/
    └── lakehouse_client.py          # Động cơ DuckDB nhúng & Auto-Discovery
```
