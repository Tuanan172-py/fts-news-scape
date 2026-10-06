# Runbook — Xuất bản dữ liệu lên SharePoint

- **Loại tài liệu:** hướng dẫn thao tác (how-to).
- **Đối tượng:** người vận hành.
- **Cập nhật:** 2026-10-06
- **Quyết định liên quan:** ADR 0020

Lý do thiết kế nằm ở [ADR 0020](../../../docs/decisions/0020-data-plane-sharepoint-co-che-xuat-ban.md).

## 1. Mục đích

Xuất bản một chiều dữ liệu của ngày đã đóng sang thư mục `FRA - Data\news` trên SharePoint. Chuyên viên và fpa-toolkit đọc ở đó, không đọc tầng ghi.

Mỗi ngày gồm năm loại tệp:

| Đường dẫn dưới đích | Nội dung |
|---|---|
| `review/monocle_review_<YYYYMMDD>.db` | bản `VACUUM INTO` của DB vận hành, giữ 7 bản gần nhất |
| `parquet/<bảng>/year=YYYY/month=MM/part-<YYYYMMDD>.parquet` | `articles`, `analysis`, `mentions` của ngày |
| `bronze/YYYY/MM/DD/<nguồn>.tar.xz` | HTML thô và `.meta.json` của ngày |
| `users/output/<user>/<YYYY-MM-DD>.xlsx` | tệp giao hàng của ngày |
| `_manifest/<YYYYMMDD>.json`, `_manifest/latest.json` | danh sách tệp, kích thước, SHA256, số dòng |

## 2. Điều kiện

- Máy vận hành có shortcut `FRA - Data` đồng bộ qua OneDrive, và tài khoản có quyền ghi.
- Thư mục `news` đặt "Always keep on this device".
- Mọi lệnh dưới đây chạy với thư mục hiện tại là `project/`.
- Không đặt `NEWS_SCAPE_PUBLISH_DIR` thì publisher tắt và không ghi gì.

## 3. Các bước

| Bước | Hành động | Kết quả mong đợi |
|---|---|---|
| 1 | `[Environment]::SetEnvironmentVariable("NEWS_SCAPE_PUBLISH_DIR", "<đường dẫn FRA - Data>\news", "User")` | Biến môi trường người dùng có giá trị sau khi mở terminal mới |
| 2 | `python scripts/publish.py --date yesterday --dry-run` | In bảng tệp ở trạng thái `planned`, đích chưa có tệp mới |
| 3 | `python scripts/publish.py --date yesterday` | Trạng thái `ok`, `_manifest/latest.json` trỏ tới ngày hôm qua |
| 4 | Sửa `config/ops.yaml`, đặt `publish.enabled: true` | Khối `publish` bật |
| 5 | `Stop-ScheduledTask news-scape-ops; Start-ScheduledTask news-scape-ops` | Daemon chạy lại và nạp cấu hình mới |
| 6 | `python scripts/ops_daemon.py once` | Phép đo `publish` khoẻ |

Sau bước 6, daemon xuất bản ngày hôm qua một lần mỗi ngày, sau giờ `publish.hour`. Kết quả ghi thành sự kiện `publish.ok`, `publish.partial` hoặc `publish.failed`.

Lệnh tay:

```powershell
python scripts/publish.py --date 2026-10-04            # một ngày cụ thể
python scripts/publish.py --date yesterday --force     # kiểm và chép lại phần thiếu
python scripts/publish.py --target D:\thu-nghiem\news  # đích khác cho lần chạy này
```

Mã thoát: 0 khi `ok` hoặc `disabled`, 2 khi `partial`, 1 khi `failed`.

## 4. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trạng thái `disabled` | Chưa đặt `NEWS_SCAPE_PUBLISH_DIR` trong phiên đang chạy | Đặt biến ở bước 1, mở terminal mới hoặc restart daemon |
| Tệp ở trạng thái `conflict` | Đích có tệp cùng tên, khác SHA256. Publisher không ghi đè | So hai bản, chuyển bản sai ra ngoài `news`, chạy lại lệnh |
| Probe báo "OneDrive.exe không chạy" | OneDrive đã thoát hoặc chưa đăng nhập | Mở OneDrive, chờ đồng bộ xong |
| Probe báo "đích không ghi được" | Mất quyền ghi hoặc thư mục bị khoá | Kiểm quyền trên SharePoint, kiểm shortcut còn tồn tại |
| Probe báo tệp xung đột hoặc partial cũ | OneDrive sinh bản `-DESKTOP-`, hoặc lần chép trước dừng giữa chừng | Xoá tệp `.partial` và bản xung đột, chạy lại lệnh |
| Probe báo `latest.json` cũ | Daemon chưa xuất bản quá `publish.stale_hours` giờ | Xem sự kiện `publish.*` bằng `/log 15`, chạy lệnh tay ở bước 3 |

Lỗi xuất bản không chặn thu thập và phân tích. Lần chạy sau làm tiếp phần thiếu, dựa vào manifest và staging.

## 5. Quay lui

1. Đặt `publish.enabled: false` trong `config/ops.yaml`, restart daemon.
2. Xoá biến `NEWS_SCAPE_PUBLISH_DIR` nếu cần tắt cả lệnh tay.
3. Ngày xuất bản lỗi: xoá tệp của ngày đó và manifest tương ứng ở đích.
4. Sửa `_manifest/latest.json` để trỏ về manifest tốt gần nhất.

Dữ liệu ở tầng ghi không đổi khi tắt publisher.

## 6. Tham chiếu

- Mã: `src/export/publisher.py`, `scripts/publish.py`, `probe_publish` trong `src/ops/probes.py`.
- Cấu hình: khối `publish` trong `config/ops.yaml`.
- Vận hành daemon: [ops-daemon.md](ops-daemon.md).
