# Runbook — Cài đặt và vận hành ops_daemon

- **Loại tài liệu:** hướng dẫn thao tác (how-to).
- **Đối tượng:** người vận hành.
- **Cập nhật:** 2026-10-01
- **Quyết định liên quan:** ADR 0012, ADR 0014

Lý do thiết kế nằm ở các ADR. Danh sách lệnh, tệp và tham số nằm ở [tài liệu tham chiếu](ops-daemon-reference.md).

## 1. Mục đích

Cài `ops_daemon`, cấp mandate và xử lý cảnh báo hằng ngày, để đợt tự chạy khi máy đang mở.

## 2. Điều kiện

- Máy đang mở và đã đăng nhập. Task Scheduler chạy dưới tài khoản của bạn, không chạy khi máy ngủ hoặc tắt.
- Python venv ở `C:\venvs\news-scape`. Mọi lệnh dưới đây chạy với thư mục hiện tại là `project/`.
- Một bot Telegram tạo bằng @BotFather, và một cuộc trò chuyện riêng với bot. Bot không nhận lệnh từ nhóm.

## 3. Các bước

| Bước | Hành động | Kết quả mong đợi |
|---|---|---|
| 1 | `python scripts/ops_daemon.py once` | In số bài chờ và các phép đo sức khoẻ. Không mở đợt, không gửi tin |
| 2 | Nhắn `/start` cho bot trong cuộc trò chuyện riêng | Bot ghi nhận bạn là người gửi |
| 3 | `python scripts/ops_daemon.py telegram --token <TOKEN> --chat-id <MÃ>` | Tin thử đến điện thoại; `C:\data\news-scape\secrets\ops.env` có token và mã chat |
| 4 | `powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Register -Start` | Hai task `news-scape-ops` và `news-scape-ops-watchdog` ở trạng thái Running hoặc Ready |
| 5 | `python scripts/ops_daemon.py status` | Dòng đầu ghi "Daemon: sống" |
| 6 | `python scripts/ops_daemon.py open` | Phòng điều khiển mở trên trình duyệt, chip tổng thể là Khoẻ hoặc Cần xem |
| 7 | Gõ `/level L1` trên Telegram, rồi bấm **Xác nhận** | `/mandate` báo L1 và hạn 30 ngày |

Sau bước 7, máy mở và đủ điều kiện thì daemon tự mở và chạy trọn đợt. Bạn không phải bấm gì từng đợt.

## 4. Xử lý sự cố

Xếp theo mức nghiêm trọng, nặng nhất trước. Tin Telegram có cùng thứ tự: nhãn mức, ảnh hưởng, việc cần làm, lệnh xem thêm.

| Mức | Dấu hiệu | Nghĩa là | Việc cần làm |
|---|---|---|---|
| Khẩn | Tin "ops_daemon không còn nhịp tim" | Watchdog thấy daemon chết hai lần kiểm liên tiếp lúc máy đang mở | `Start-ScheduledTask news-scape-ops`, rồi xem `ops_logs/daemon.out.log` |
| Khẩn | Tin "agy mất phiên đăng nhập" | Breaker mở vì lỗi đăng nhập, đợt tạm dừng | Mở terminal, đăng nhập lại `agy`, bấm **Reset** hoặc gõ `/reset agy` |
| Khẩn | Tin "Cào tin dừng" | `morninger` chết quá số lần cho phép | Xem `ops_logs/capture.log`, rồi gõ `/capture restart` |
| Lỗi | Tin "Đợt ...: lỗi" hoặc "tạm dừng" | Cổng nạp đỏ, độ phủ dưới 90% hoặc workflow dừng | Bấm **Chẩn đoán**, rồi **Chạy lại** (`/retry <đợt>`) hoặc `/cancel <đợt>` để nhả bài |
| Lỗi | Tin "Mất kết nối tới agy" | Breaker mở vì lỗi mạng | Kiểm mạng. Breaker tự thử lại sau 10 phút |
| Lỗi | Tin "Mandate ... không tự gia hạn" | Hệ thống chưa đủ điều kiện khoẻ | Xử lý nguyên nhân trong tin, hoặc gõ `/order extend 30` |
| Cảnh báo | Tin "agy hết hạn mức" | Breaker mở tới giờ làm mới hạn mức | Chờ tự thử lại, hoặc gõ `/provider openrouter` |
| Cảnh báo | Phòng điều khiển không mở | Cổng 8787 đang bị tiến trình khác dùng | Đổi `control_room.port` trong `config/ops.yaml`, khởi động lại daemon |

## 5. Quay lui

| Mục tiêu | Cách làm |
|---|---|
| Dừng khẩn ngay | Gõ `/stop` rồi bấm xác nhận. Cờ `AGY_STOP` chặn đợt mới. Gỡ bằng `/unstop` |
| Chỉ ngừng mở đợt mới | Gõ `/pause`. Tiếp tục bằng `/resume` |
| Thu hồi mandate | Gõ `/level L0` |
| Tắt Phòng điều khiển | Đặt `control_room.enabled: false` trong `config/ops.yaml` |
| Gỡ hẳn daemon | `powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Uninstall`, rồi chạy tay bằng `article_run.py` |

Sửa `config/ops.yaml` hoặc mã trong `src/ops` thì khởi động lại daemon: `schtasks /End /TN news-scape-ops`, rồi `schtasks /Run /TN news-scape-ops`.

## 6. Tham chiếu

- [Tài liệu tham chiếu ops_daemon](ops-daemon-reference.md): mức tự chủ, điều kiện gia hạn, màn hình, tệp và nhật ký, cấu hình.
- ADR 0012: lý do thiết kế control plane. ADR 0014: giám sát multi-agent và mandate.
- Bảng thuật ngữ: [GLOSSARY](../../../docs/GLOSSARY.md).
