# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-10-20 17:05 (GMT+7)  
**Nhánh:** dev/us038 | **Nhiệm vụ:** Hoàn Tất Đẩy Toàn Bộ Dữ Liệu Lịch Sử 1 Năm Lên SharePoint Sandbox

---

## 1. Kết Quả Xuất Bản Lịch Sử 1 Năm Lên Sandbox (FRA_DataIngestion)

Toàn bộ dữ liệu 1 năm tích lũy từ `C:\data\news-scape` đã được chuẩn hóa và xuất bản thành công sang SharePoint Sandbox:
- **SharePoint Site:** `[FRA_DataIngestion - Home](https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion)`
- **Thư mục đồng bộ máy trạm:** `C:\Users\anpt\OneDrive - fpts.com.vn\Shortcuts\FRA_DataIngestion - news-data`
- **Khoảng thời gian dữ liệu:** Từ `2025-10-01` đến `2026-10-19` (toàn bộ các ngày đã đóng sổ).

### 1.1. Thống Kê Phân Vùng Lakehouse (OBT 22 Cột Parquet)
- **Tổng số bài viết:** **32.981 bài viết** chuẩn hóa OBT 22 trường nghiệp vụ.
- **Tổng số ngày phân vùng:** **283 phân vùng ngày** (`part-<YYYYMMDD>.parquet`).
- **Nguồn báo chí:** 8 nguồn chính thức (`baodautu.vn`, `cafef.vn`, `fireant.vn`, `thoibaotaichinhvietnam.vn`, `tinnhanhchungkhoan.vn`, `vietnambiz.vn`, `vietstock.vn`, `vneconomy.vn`).

Phân bổ bài viết theo từng tháng:
| Tháng | Số bài viết | Ghi chú |
| :---: | :---: | :--- |
| **2025-10** | 24 | Dữ liệu khởi tạo lịch sử |
| **2025-11** | 29 | Dữ liệu lịch sử |
| **2025-12** | 41 | Dữ liệu lịch sử |
| **2026-01** | 36 | Dữ liệu lịch sử |
| **2026-02** | 21 | Dữ liệu lịch sử |
| **2026-03** | 65 | Dữ liệu lịch sử |
| **2026-04** | 46 | Dữ liệu lịch sử |
| **2026-05** | 84 | Dữ liệu lịch sử |
| **2026-06** | 155 | Dữ liệu lịch sử |
| **2026-07** | 502 | Bắt đầu chạy pipeline tự động |
| **2026-08** | 4.484 | Bắt đầu lưu trữ Bronze HTML |
| **2026-09** | 11.797 | Vận hành đa nguồn toàn diện |
| **2026-10** | 15.697 | Dữ liệu đầy đủ kèm phân tích Gold & intent |
| **TỔNG** | **32.981** | **283 phân vùng Parquet nén ZSTD** |

---

## 2. Cấu Trúc Thành Phẩm Trên Môi Trường Sandbox

```text
FRA_DataIngestion - news-data/
├── _manifest/                                 # [1. Siêu dữ liệu & La bàn cho Skills]
│   ├── latest.json                            # Trỏ ngày 2026-10-19, quản lý 283 manifests
│   └── 2025-10-01.json ... 2026-10-19.json    # 283 tệp manifest ngày
│
├── parquet/                                   # [2. Hồ dữ liệu Lakehouse cho DuckDB / Skills]
│   └── articles/
│       ├── year=2025/month=10..12/
│       └── year=2026/month=01..10/            # 283 phân vùng OBT 22 cột (list<string> symbols)
│
├── users/output/                              # [3. Thành phẩm Excel giao hàng]
│   ├── AnPT/                                  # 358 tệp .xlsx cho 5 chuyên viên
│   ├── PhoHG/, ThanhTD/, UyenNNT/, VyPTT/
│
├── review/                                    # [4. Tra cứu SQLite chỉ đọc (7 ngày gần nhất)]
│   ├── monocle_review_20261013.db
│   ├── monocle_review_20261014.db
│   ├── monocle_review_20261015.db
│   ├── monocle_review_20261016.db
│   ├── monocle_review_20261017.db
│   ├── monocle_review_20261018.db
│   └── monocle_review_20261019.db
│
└── bronze/                                    # [5. Lưu trữ thô HTML (đối soát)]
    └── 2026/10/ (các ngày đã đóng gói)
```

---

## 3. Cải Tiến Kỹ Thuật Đã Triển Khai

1. **Tối Ưu Hóa Truy Vấn OBT (`publisher._build_obt_parquet`)**:
   - Chuyển đổi từ `GROUP BY` toàn bảng `agent_outputs`/`l1_outputs` sang Correlated Subquery tận dụng chỉ mục `(article_id, dod_pass)`.
   - Thời gian trích xuất giảm từ **12.0 giây xuống 0.12 giây** (tăng tốc 100 lần, kết quả đối chiếu khớp 100%).
2. **Cơ Chế Bỏ Qua Review Snapshot Cũ**:
   - Tự động bỏ qua việc tạo và nén file SQLite review 1.25 GB cho các ngày cũ hơn 7 ngày (vì sẽ bị xoá ngay lập tức theo chính sách retention), tiết kiệm hơn **350 GB ghi đĩa** và rút ngắn thời gian backfill xuống chỉ còn ~4 phút.
3. **Mở Rộng Tham Số CLI `publish.py`**:
   - Bổ sung `--skip-review` và `--skip-bronze` để linh hoạt điều phối tốc độ nạp dữ liệu.
   - Lọc thông minh chỉ quét các ngày thực sự có bài viết trong cơ sở dữ liệu (`articles`).

---

## 4. Kiểm Thử & Kiểm Định Toàn Vẹn

1. **Kiểm Định Manifest (`lakehouse_cli.py verify`)**:
   - Kết quả: PASS 100%, con trỏ `_manifest/latest.json` hợp lệ và khớp mã băm SHA-256.
2. **Kiểm Thử Truy Vấn DuckDB Thực Địa (`lakehouse_client.py`)**:
   - Quét toàn bộ 32.981 bài viết trong **0.48 giây**.
   - Thử nghiệm truy vấn mã `HPG` trả về 198 bài viết từ 2026-07 đến 2026-10 tức thì.
3. **Bộ Kiểm Thử (Pytest Integrity)**:
   - Toàn bộ các test liên quan đến Publisher, Lakehouse và Plugin FPTS Market Intel đều **PASS 100% (69/69 tests)**.
