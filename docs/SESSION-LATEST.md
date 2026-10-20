# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-10-20 11:05 (GMT+7)  
**Nhánh:** dev/us038 | **Nhiệm vụ:** Hoàn Tất Chuẩn Hóa Lakehouse & Di Chuyển Sang Sandbox Mới (FRA_DataIngestion)

---

## 1. Kết Quả Di Chuyển & Chuẩn Hóa Hồ Dữ Liệu (SharePoint Sandbox Migration)

Toàn bộ hạ tầng Lakehouse phục vụ khai phá dữ liệu (EDA) và phân phối tin tức đã được di chuyển thành công sang SharePoint Sandbox mới dành riêng cho dữ liệu:
- **SharePoint Site:** `[FRA_DataIngestion - Home](https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion)`
- **Thư mục đồng bộ máy trạm:** `C:\Users\anpt\OneDrive - fpts.com.vn\Shortcuts\FRA_DataIngestion - news-data`
- **Chốt chặn an toàn (Target Guard):** Ngăn chặn tuyệt đối việc ghi nhầm vào site chính thức `FRA - Data` (`is_official_target()` ném `PermissionError`).

### 1.1. Chuẩn Hóa Schema Parquet — Một Bảng Hợp Nhất (OBT 22 Cột)
- **Kiểu dữ liệu `symbols`**: Đã đổi từ `pa.string()` sang `pa.list_(pa.string())` trong [`project/src/lakehouse/ingest.py`](file:///c:/src/news-scraper/project/src/lakehouse/ingest.py).
- **Hỗ trợ truy vấn DuckDB**: Chuyên viên phân tích và các Skills có thể trực tiếp lọc mã cổ phiếu bằng `list_contains(symbols, 'HPG')` hoặc giải nén mảng bằng `unnest(symbols)` mà không gặp lỗi `Type VARCHAR can't be cast to VARCHAR[]`.
- **Hợp nhất bảng thô**: Loại bỏ các bảng phân mảnh cũ (`parquet/analysis`, `parquet/mentions`) trong [`project/src/export/publisher.py`](file:///c:/src/news-scraper/project/src/export/publisher.py), tập trung vào Một Bảng Hợp Nhất duy nhất `parquet/articles/` (OBT) đầy đủ 22 trường nghiệp vụ (nội dung, tóm tắt, luận điểm, hàm ý, sắc thái, độ nhạy thời gian, intent).

### 1.2. Cơ Chế Auto-Purge Dropzone & Ghim Tệp Ngoại Tuyến
- **Dọn dẹp tự động (Auto-Purge)**: Tham số `auto_purge=True` trong [`project/src/lakehouse/consolidator.py`](file:///c:/src/news-scraper/project/src/lakehouse/consolidator.py) tự động xóa sạch các tệp phân mảnh tạm thời trong `dropzone/YYYY/MM/DD/` ngay sau khi DuckDB hoàn tất nén và ghi đè phân vùng canonical. Người dùng và Skills hoàn toàn không thấy rác dropzone.
- **Ghim tệp ngoại tuyến (Files On-Demand Pinning)**: Đã chạy `attrib -U +P` cho toàn bộ thư mục đích, đảm bảo tệp luôn có sẵn trên đĩa cục bộ, triệt tiêu độ trễ tải mạng khi truy vấn DuckDB.

---

## 2. Kết Quả Backfill & Kiểm Chứng Toàn Vẹn Thực Địa

Đã xuất bản thành công dữ liệu 4 ngày liên tiếp sang Sandbox mới:

| Ngày dữ liệu | Phân vùng Parquet (OBT 22 cột) | Số bài viết | Dung lượng Parquet | File Manifest | Review DB | Deliverable Excel |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2026-10-16** | `part-20261016.parquet` | 890 bài | 531 KB | `2026-10-16.json` | `monocle_review_20261016.db` | Có (5 users) |
| **2026-10-17** | `part-20261017.parquet` | 274 bài | 172 KB | `2026-10-17.json` | `monocle_review_20261017.db` | Có (5 users) |
| **2026-10-18** | `part-20261018.parquet` | 304 bài | 184 KB | `2026-10-18.json` | `monocle_review_20261018.db` | Có (5 users) |
| **2026-10-19** | `part-20261019.parquet` | 1.437 bài | 694 KB | `2026-10-19.json` | `monocle_review_20261019.db` | Có (5 users) |
| **TỔNG CỘNG** | **4 phân vùng** | **2.905 bài** | **~1.58 MB** | **5 manifests** | **4 snapshots (7d max)** | **14.015 dòng** |

- **Kiểm chứng tính toàn vẹn (Verification Gate)**:
  `lakehouse_cli.py verify` trả về PASS 100% đối chiếu SHA-256 từng tệp phân vùng với con trỏ nguyên tử `_manifest/latest.json`.
- **Đo lường hiệu năng DuckDB (EDA Benchmark)**:
  Truy vấn quét toàn bộ 2.905 bài viết nén ZSTD chỉ mất **0.42 giây** trên máy trạm cục bộ.

---

## 3. Cấu Trúc Thư Mục Chuẩn 5 Tầng Trên Sandbox

```text
FRA_DataIngestion - news-data/
├── _manifest/                                 # [1. Siêu dữ liệu & La bàn cho Skills]
│   ├── latest.json                            # Con trỏ nguyên tử cập nhật ngày mới nhất
│   ├── 2026-10-16.json
│   ├── 2026-10-17.json
│   ├── 2026-10-18.json
│   └── 2026-10-19.json
│
├── parquet/                                   # [2. Hồ dữ liệu chính thức cho Skills / DuckDB]
│   └── articles/
│       └── year=2026/
│           └── month=10/                      # Phân vùng chuẩn OBT 22 cột (list<string> symbols)
│               ├── part-20261016.parquet
│               ├── part-20261017.parquet
│               ├── part-20261018.parquet
│               └── part-20261019.parquet
│
├── users/                                     # [3. Thành phẩm Excel xem trực tiếp]
│   └── output/
│       ├── AnPT/                              # File .xlsx lọc theo watchlist cá nhân
│       ├── PhoHG/
│       ├── ThanhTD/
│       ├── UyenNNT/
│       └── VyPTT/
│
├── review/                                    # [4. Tra cứu nhanh SQLite chỉ đọc (giữ 7 ngày)]
│   ├── monocle_review_20261016.db
│   ├── monocle_review_20261017.db
│   ├── monocle_review_20261018.db
│   └── monocle_review_20261019.db
│
└── bronze/                                    # [5. Lưu trữ thô HTML + meta (dự phòng đối soát)]
    └── 2026/10/
        ├── 16/
        └── 19/
```

---

## 4. Chốt Quyết Định Kiến Trúc Đóng Gói Client (/learn & ADR-0025)

Đã chốt quyết định kiến trúc và phê chuẩn [ADR-0025](file:///c:/src/news-scraper/docs/decisions/0025-unified-plugin-architecture-for-lakehouse-consumption.md) cùng [FACT-LAKEHOUSE-PLUGIN-LAYOUT](file:///c:/src/news-scraper/docs/knowledge/facts/lakehouse-client-plugin-layout.md):
- **Unified Plugin (`fpts-market-intel`)**: Đóng gói toàn bộ kỹ năng khai phá dữ liệu vào một plugin duy nhất tại `~/.gemini/config/plugins/fpts-market-intel/` dùng chung cho cả `agy` và `gemini`. Cấm phân phối các skills rời rạc nhằm triệt tiêu nguy cơ lệch phiên bản (anti-version-skew).
- **Zero-Config Auto-Discovery**: Tự động dò tìm đường dẫn shortcut OneDrive trên máy chuyên viên theo 3 cấp (biến môi trường $\rightarrow$ shortcut chuẩn $\rightarrow$ quét filesystem).
- **Vectorized Zero-Token Tooling**: Tái sử dụng module `tools/lakehouse_client.py` chạy DuckDB nhúng, quét trực tiếp OBT 22 cột Parquet mà không tốn token LLM.
- **Trải nghiệm 1-Click**: Cung cấp sẵn các `suggestedPrompts` trên UI chat để chuyên viên phân tích bấm là chạy ngay.

---

## 5. Triển Khai Hoàn Tất FPTS Market Intel Unified Plugin

Đã hiện thực hóa toàn bộ gói plugin [`plugins/fpts-market-intel/`](file:///c:/src/news-scraper/plugins/fpts-market-intel/) và trình cài đặt tự động:
1. **Manifest & Rules**:
   - [`plugin.json`](file:///c:/src/news-scraper/plugins/fpts-market-intel/plugin.json): Khai báo 4 câu `suggestedPrompts` mẫu trên UI.
   - [`rules/AGENTS.md`](file:///c:/src/news-scraper/plugins/fpts-market-intel/rules/AGENTS.md): Ranh giới kiểm soát miền tài chính, chống ảo giác và chuẩn hóa sắc thái.
2. **Động cơ DuckDB Nhúng (`tools/lakehouse_client.py`)**:
   - Tự động nhận diện shortcut OneDrive trên mọi máy trạm qua cơ chế 3 cấp.
   - Thực thi truy vấn Parquet tốc độ cao (0 token LLM), hỗ trợ `list_contains(symbols, ?)`, chuẩn hóa sắc thái cả mã ngắn (`pos`, `neg`, `neu`) và mã đầy đủ (`positive`, `negative`, `neutral`).
3. **Bộ 4 Kỹ Năng Nghiệp Vụ (`skills/`)**:
   - [`news-ticker-screener`](file:///c:/src/news-scraper/plugins/fpts-market-intel/skills/news-ticker-screener/SKILL.md): Soi tin chi tiết theo mã CP.
   - [`news-daily-brief`](file:///c:/src/news-scraper/plugins/fpts-market-intel/skills/news-daily-brief/SKILL.md): Tổng hợp Morning Brief cho danh mục cá nhân.
   - [`news-sector-pulse`](file:///c:/src/news-scraper/plugins/fpts-market-intel/skills/news-sector-pulse/SKILL.md): Quét nhịp đập 11 ngành GICS & vĩ mô.
   - [`news-lakehouse-explorer`](file:///c:/src/news-scraper/plugins/fpts-market-intel/skills/news-lakehouse-explorer/SKILL.md): Kiểm toán `latest.json` & chạy SQL tùy biến.
4. **Trình Cài Đặt 1-Click**:
   - [`scripts/install_market_intel_plugin.py`](file:///c:/src/news-scraper/scripts/install_market_intel_plugin.py) & `.ps1`: Tự động kiểm tra DuckDB, ghim tệp ngoại tuyến và cài đặt sang `%USERPROFILE%\.gemini\config\plugins\fpts-market-intel`.

---

## 6. Kiểm Thử Hệ Thống & Kiểm Định Quy Chuẩn Git

1. **Bộ Kiểm Thử (Pytest Integrity)**:
   - **48/48 tests PASS** (Toàn bộ 39 tests hạ tầng Lakehouse/Publisher + 9 tests plugin `test_plugin_lakehouse_client.py` và `test_plugin_manifest.py`).
2. **Kiểm Định Hợp Đồng Tri Thức**:
   - `scripts/harness_cli.py doc lint` đạt 0 lỗi, index và database đồng bộ hoàn toàn.
3. **Cấu Hình Tự Động Hóa (Ops Daemon)**:
   - Đã kích hoạt `publish.enabled: true` trong [`project/config/ops.yaml`](file:///c:/src/news-scraper/project/config/ops.yaml).
4. **Quy Chuẩn Đóng Phiên (Rule 01 §7)**:
   - Cây làm việc sạch sẽ, commit chuẩn Conventional Commits kèm mã `(US-038)`.
