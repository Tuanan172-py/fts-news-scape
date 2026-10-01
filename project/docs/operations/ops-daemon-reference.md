# Tham chiếu — ops_daemon

- **Loại tài liệu:** tham chiếu (reference).
- **Cập nhật:** 2026-10-01
- **Quyết định liên quan:** ADR 0012, ADR 0014

Cách cài đặt và xử lý cảnh báo nằm ở [runbook](ops-daemon.md). Tài liệu này chỉ liệt kê sự kiện và tham số.

## 1. Mức tự chủ

| Mức | Daemon tự làm | Người làm |
|---|---|---|
| L0 | Đo và báo | Gõ `/run` khi muốn mở một đợt |
| L1 | Khi đủ điều kiện thì mở đợt và chạy trọn: kiểm tra trước, đóng gói, phân tích, vá, nạp DB qua cổng `--finish` | Xử lý cảnh báo, soát mẫu chất lượng |

- Không có nút duyệt từng đợt. Cổng kỹ thuật của `--finish` quyết định việc nạp DB (ADR 0008).
- Giao hàng không thuộc vòng đời đợt. DB là nguồn sự thật, việc giao hàng là quy trình riêng.
- Hai lần đợt lỗi liên tiếp thì L1 tự về L0 và báo mức khẩn.
- Lệnh nâng quyền (`/level L1`, `/order extend`, `/provider`, `/failover auto`) cần bấm xác nhận lần hai.

## 2. Mandate

| Thuộc tính | Giá trị |
|---|---|
| Hạn tối đa | 30 ngày |
| Xét tự gia hạn | Khi còn dưới 7 ngày |
| Điều kiện khoẻ | Không có sự kiện mức khẩn trong 24 giờ; chuỗi đợt sạch từ 5; không có chuỗi đợt hỏng; không có lượt gọi công cụ trái Zero-Tool trong 7 ngày |
| Không đủ điều kiện | Dừng gia hạn, báo lý do, hạn tự cạn về L0 |
| Đã hết hạn hoặc chưa cấp | Không bao giờ tự cấp lại; người cấp bằng `/level L1` |

Luật mở đợt (T1, T2, T3) định nghĩa trong [bảng thuật ngữ](../../../docs/GLOSSARY.md).

## 3. Phòng điều khiển

Địa chỉ `http://127.0.0.1:8787`, chỉ nghe máy này. Mở bằng `python scripts/ops_daemon.py open`.

| Màn | Nội dung |
|---|---|
| Toàn cảnh | Chip tổng thể, hàng việc cần người, bản đồ tác nhân, đợt gần nhất, điểm khác thường |
| Đợt | Danh sách đợt, biểu đồ Gantt và cây vết của một đợt |
| Tác nhân | Đặc tả từ registry và KPI 7 ngày của từng tác nhân |
| Sự cố | Breaker, phép đo sức khoẻ, sự kiện cảnh báo, chẩn đoán của sentinel |
| Cải tiến | Hộp thư đề xuất: **Mở story**, **Hoãn 30 ngày**, **Bác 30 ngày** |

## 4. Tệp và nhật ký

| Đường dẫn | Nội dung |
|---|---|
| `C:\data\news-scape\ops.db` | Sự kiện, cảnh báo, đợt, vết, bài giữ chỗ, số lần thử, breaker, lệnh, đề xuất |
| `C:\data\news-scape\ops_dbos.db` | Checkpoint workflow DBOS |
| `C:\data\news-scape\ops_logs\YYYY-MM-DD.jsonl` | Bản sao sự kiện theo ngày, bí mật đã che |
| `C:\data\news-scape\ops_logs\waves\<đợt>\<bước>.log` | Đầu ra từng bước; `exclude.txt` là tập bài bị loại khi đóng gói |
| `C:\data\news-scape\ops_logs\daemon.out.log` | Đầu ra của daemon |
| `C:\data\news-scape\ops_logs\capture.log` | Đầu ra của `morninger` do daemon sinh |
| `C:\data\news-scape\agy_standing_order.yaml` | Mandate: mức, hạn, provider, failover |
| `C:\data\news-scape\secrets\ops.env` | Token Telegram, mã chat, địa chỉ healthchecks |
| `project/config/ops.yaml` | Ngưỡng, hạn chót từng bước, lịch bản tin, chính sách breaker |

## 5. Bài của đợt và giới hạn thử lại

- Bài đã vào một đợt được giữ chỗ cho tới khi đợt xong hoặc bị huỷ. Đợt tạm dừng hoặc lỗi vẫn giữ bài.
- Mỗi bài được đóng gói tối đa `wave.max_attempts_per_article` lần (mặc định 2). Quá số đó mà chưa qua cổng DoD thì bài không tự thử lại.
- `/cancel <đợt>` nhả bài của một đợt đã dừng.
- Bài tồn đọng ngoài `sensor.lookback_days` không thuộc phạm vi tự động.

## 6. Hành vi khi dừng

- `/stop` đặt cờ `AGY_STOP`. Đợt đang chạy dừng ở ranh giới bước kế tiếp.
- Bước nạp DB đang chạy không bị cắt ngang.
- Daemon chết thì Job Object kết thúc cả cây `article_run` và `agy`, nên không lô nào tiêu token khi không ai giám sát.
