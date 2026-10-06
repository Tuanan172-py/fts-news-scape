# ADR 0020 — Data plane trên SharePoint: cơ chế xuất bản một chiều

- **Loại tài liệu:** giải thích (explanation), ghi lại một quyết định.
- **Ngày:** 2026-10-05
- **Trạng thái:** accepted
- **Lane:** high-risk (đổi nơi lưu dữ liệu, thêm luồng ghi ra kho dùng chung của Khối)
- **Story:** US-038
- **Kế thừa:** ADR 0012 (ops_daemon), ADR 0013 (thu thập trọn vẹn), ADR 0019.
- **Người duyệt:** người dùng duyệt ngày 2026-10-05. Ba câu hỏi ở §6 còn chờ trả lời; publisher (A4) chỉ ghi lên SharePoint khi câu 1 có câu trả lời "có".

## 1. Bối cảnh

Mục tiêu: mã nguồn sống trên GitHub `Research-FPA/news-scraper`, toàn bộ dữ liệu và dữ liệu sinh ra khi vận hành được quản lý trên SharePoint.

Số đo trên máy vận hành ngày 2026-10-05:

| Hạng mục | Thực tế |
|---|---|
| `FRA - Data` | Thư viện teamsite `fptscomvn.sharepoint.com/sites/FRA/Data`, gắn vào OneDrive cá nhân bằng shortcut. Files On-Demand: thư mục và tệp ở trạng thái chỉ-trên-mây (thuộc tính `Unpinned`, `RecallOnDataAccess`). |
| Thư mục kho mã | Cũng là thư viện teamsite `sites/FRA_DataIngestion`, đồng bộ qua OneDrive. Kho Git (`.git`) đã tách ra `C:/gitdirs/news-scape.git`. |
| Dữ liệu nóng trong thư mục kho | Khoảng 6,6 GB dưới `project/data` (raw_html 3,2 GB, silver 1,2 GB, work_packages 1,2 GB, packet, output agent) và `users/output`, đều đi qua đồng bộ OneDrive. |
| Dấu hiệu đồng bộ gây hại | `archive_conflicts` 194 MB, tệp `*-DESKTOP-*`, guard chống OneDrive trong `resolve_db_path` và `user_output.py`. |
| DB vận hành | `C:\data\news-scape\monocle.db` (746 MB, WAL), `ops.db`. Đúng chỗ. |

Ràng buộc kỹ thuật không đổi được:

- SQLite WAL hỏng khi tệp `-wal`, `-shm` bị đồng bộ hoặc khoá bởi tiến trình đồng bộ.
- OneDrive tải lên bất đồng bộ, không có xác nhận trong tiến trình ghi. Máy khác có thể thấy tệp dở dang hoặc bản cũ.
- Đồng bộ chậm rõ khi thư viện vượt khoảng 300.000 mục. Bronze và Silver sinh hàng chục nghìn tệp nhỏ mỗi tuần.
- Hai máy ghi cùng tên tệp sinh bản xung đột theo tên máy.
- Shortcut gắn với phiên Windows của một người. OneDrive tạm dừng khi máy tiết kiệm pin hoặc mạng tính phí.

## 2. Quyết định

### 2.1. Hai tầng, một chiều

```
Máy vận hành  C:\data\news-scape   ──publisher──▶   SharePoint  FRA - Data/news/
  tầng ghi: DB, Bronze, Silver,        một chiều,       tầng xuất bản, chỉ thêm:
  packet, output agent, logs           một nơi ghi      review/, parquet/, bronze/, users/, _manifest/
```

- **Tầng ghi** ở ổ SSD cục bộ, ngoài OneDrive. Chỉ `ops_daemon` và các lệnh vận hành ghi vào đây. Đường dẫn duy nhất qua `MONOCLE_DATA_DIR`.
- **Tầng xuất bản** trên SharePoint là nguồn dùng chung của Khối. Chỉ job `publisher` ghi. Không tiến trình nào đọc ngược từ đây để ghi vào tầng ghi, trừ đầu vào do người sửa (mục 2.4).
- Không đặt SQLite đang mở, packet đang chạy hay tệp theo từng bài lên SharePoint.

### 2.2. Bố cục tầng xuất bản

| Đường dẫn dưới `FRA - Data/news/` | Nội dung | Nhịp | Ghi đè |
|---|---|---|---|
| `review/monocle_review_<YYYYMMDD>.db` | `VACUUM INTO` từ DB vận hành, chỉ đọc | hằng ngày, giữ 7 bản | không |
| `parquet/<bảng>/year=YYYY/month=MM/part-<YYYYMMDD>.parquet` | articles, mentions, analysis | hằng ngày | không |
| `bronze/YYYY/MM/DD/<nguồn>.tar.xz` | raw_html và meta.json của ngày, nén | hằng ngày, sau khi ngày đóng | không |
| `users/output/<user>/<YYYY-MM-DD>.xlsx` | giao hàng | theo `write_user_output` | không |
| `users/subscriptions/` | đăng ký do chuyên viên sửa | người sửa | có (đầu vào) |
| `_manifest/<YYYYMMDD>.json`, `_manifest/latest.json` | danh sách tệp, kích thước, SHA256, số dòng | mỗi lần xuất bản | chỉ `latest.json` |

Bronze nén bằng `.tar.xz` của `tarfile` trong thư viện chuẩn, để publisher không thêm dependency như zstd.

### 2.3. Giao thức ghi

1. Dựng tệp hoàn chỉnh ở `C:\data\news-scape\publish_staging\`.
2. Chép sang SharePoint với tên tạm `.<tên>.partial`, rồi đổi tên trong cùng thư mục.
3. Ghi manifest của lần xuất bản sau cùng, `latest.json` ghi cuối cùng.
4. Người đọc (fpa-toolkit, chuyên viên) chỉ đọc tệp có trong `latest.json` và kiểm SHA256. Tệp không có trong manifest coi như chưa tồn tại.
5. Tên tệp mang ngày, không ghi đè, nên không phát sinh xung đột hai máy.

### 2.4. Đầu vào do người sửa

`users/subscriptions` và nguồn thực thể (`FRA - Data/company_data`, `industry_classification`) được đọc bằng cách chép về `C:\data\news-scape\inputs\` trước mỗi lần dùng. Thư mục nguồn đặt "Always keep on this device" để tránh tải theo yêu cầu khi daemon chạy.

### 2.5. Thang suy giảm

| Mức | Cơ chế | Điều kiện dùng |
|---|---|---|
| L1 (mặc định) | Thư mục đồng bộ OneDrive `FRA - Data`, qua `NEWS_SCAPE_PUBLISH_DIR` | máy vận hành có shortcut, người vận hành đăng nhập |
| L2 | Microsoft Graph API với tài khoản dịch vụ, tải lên có xác nhận và eTag | khi cần chạy không phụ thuộc tài khoản cá nhân, hoặc khi L1 trễ quá ngưỡng |
| L0 | Không xuất bản, dữ liệu vẫn an toàn ở tầng ghi, radar báo ĐỎ | OneDrive dừng hoặc mất quyền ghi |

Publisher không bao giờ chặn đường thu thập và phân tích. Lỗi xuất bản chỉ làm lần xuất bản sau gánh phần còn thiếu, dựa vào manifest.

### 2.6. Probe sức khoẻ cho `ops_daemon`

- Tiến trình `OneDrive.exe` đang chạy.
- Thư mục xuất bản ghi được (ghi rồi xoá một tệp `.probe` trong `_manifest/`).
- Không có tệp `*-DESKTOP-*` hay `*.partial` cũ hơn 2 giờ dưới `news/`.
- `latest.json` không cũ hơn 26 giờ.

Mỗi probe ĐỎ gửi Telegram theo kênh hiện có.

### 2.7. Thư mục kho mã ra khỏi OneDrive

Khi GitHub là nơi giữ mã, bản sao trên thư viện `FRA_DataIngestion` thành thừa và là nguồn xung đột. Cây làm việc chuyển về `C:\src\news-scraper`, Task Scheduler và preset DSH trỏ theo. Việc này làm cùng lúc chuyển dữ liệu nóng sang `C:\data\news-scape`, trong một khung dừng daemon.

## 3. Phương án đã loại

| Phương án | Lý do loại |
|---|---|
| Đặt `monocle.db` và dữ liệu nóng thẳng trên thư mục đồng bộ SharePoint | SQLite WAL hỏng khi `.db`, `-wal`, `-shm` đồng bộ lệch nhịp. Dự án đã có dấu vết xung đột (`archive_conflicts`, `*-DESKTOP-*`) |
| Đồng bộ hai chiều toàn bộ `C:\data\news-scape` lên SharePoint | Hàng chục nghìn tệp nhỏ mỗi tuần làm chậm đồng bộ của cả thư viện. Hai máy ghi cùng tên sinh xung đột |
| Máy chủ CSDL (PostgreSQL) ngay từ đầu | Cần IT cấp máy chủ và chuyển đổi lược đồ. Giữ làm đích dài hạn (phương án A2 của plan 2026-10-02) |
| Hàng đợi outbox/inbox qua SharePoint cho nhiều laptop trong đợt này | Hàng đợi phân tán không có khoá trên nền đồng bộ. Tách ra ADR riêng khi có nhu cầu |

## 4. Hệ quả

- Cần `core/paths.py` làm nguồn đường dẫn duy nhất trước khi chuyển dữ liệu. Hiện khoảng 100 tệp tự dựng đường dẫn `data/...`.
- DB đang lưu đường dẫn Bronze tương đối theo `PROJECT_ROOT` (`raw_store.py`, `silver_failures`). Chuyển dữ liệu kèm chuyển đổi các dòng này.
- Hàng đợi phân tán qua SharePoint (outbox/inbox cho worker) không thuộc ADR này.

## 5. Quay lui

- Tắt publisher bằng cờ cấu hình. Dữ liệu ở tầng ghi không đổi, thu thập và phân tích chạy tiếp.
- Tệp đã xuất bản là bất biến, có tên theo ngày. Xoá thư mục ngày lỗi và manifest tương ứng, rồi đặt `latest.json` về lần xuất bản tốt gần nhất.
- Khung chuyển thư mục (N4) có quy trình quay lui riêng trong plan US-038. Cài lại Task Scheduler từ thư mục cũ, khôi phục DB từ bản `pre-cutover`.

## 6. Câu hỏi mở cần người duyệt

1. Tài khoản vận hành có quyền ghi trên `sites/FRA/Data` không, và có được tạo thư mục `news/` không.
2. Có cấp được tài khoản dịch vụ và app registration cho mức L2 không.
3. Hạn mức dung lượng của thư viện `FRA/Data`. raw_html hiện 3,2 GB chưa nén. HTML nén xz thường còn 10–20%, nên Bronze nén ước dưới 1 GB mỗi tháng, cần đo lại bằng gói ngày đầu tiên.
