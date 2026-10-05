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

## 7. Chạy tay (bài tồn và thử tác nhân)

Chạy tay là đường chính thức để dọn bài tồn đọng và so sánh năng lực các provider. Mọi đợt tay tự đăng ký vào `ops.db`, có vết, và đi qua cùng cổng kiểm va chạm.

| Chế độ | Dùng khi | Giữ chỗ bài | Nạp DB | Đầu ra |
|---|---|---|---|---|
| `backlog` | Dọn bài ngoài phạm vi tự động | Có | Có, bằng `--finish` | `data/agent_outputs_article/` |
| `bench` | Thử provider hoặc model khác trên cùng tập bài | Không | Không, `--finish` bị từ chối | `data/agent_bench/<đợt>/` |
| `adhoc` | Việc tay khác (mặc định) | Có | Có | `data/agent_outputs_article/` |

Lệnh mẫu, chạy với thư mục hiện tại là `project/`:

```powershell
python scripts/article_run.py --wave W<mã> --date 2026-09-20 --limit 100 --batch 50 --mode backlog --runner openrouter
python scripts/article_run.py --wave W<mã> --runner openrouter --analyze --mode backlog
python scripts/article_run.py --wave W<mã> --repair --runner openrouter
python scripts/article_run.py --wave W<mã> --finish
```

Quy tắc:

- Provider khoá theo đợt ở lần mở đầu tiên. Đổi provider giữa đợt bị từ chối; muốn thử provider khác thì mở đợt mới ở chế độ `bench`.
- Khi daemon đang chạy một đợt, lệnh tay bị từ chối. Cờ `--force` bỏ qua kiểm này và khoá provider, đồng thời ghi sự kiện `provider.override`.
- Bài đang thuộc đợt chưa xong bị loại tự động. Bài đã hết lượt thử của daemon vẫn chọn được ở chế độ `backlog`.
- Mỗi vòng vá tính một lần thử cho từng bài còn thiếu. `/retry` bị từ chối khi đợt đã vá quá hai lần `max_repair_rounds`.
- Sau mỗi đợt hỏng không do provider, sensor nghỉ `wave.cooldown_minutes` (mặc định 30 phút) trước khi mở đợt mới. `/run` bỏ qua thời gian nghỉ.

## 8. Phân luồng

Mỗi đợt thuộc đúng một luồng, xác định bởi luật mở đợt trong cột `trigger` (mã `src/ops/lanes.py`). Mỗi luồng chỉ có tối đa một đợt đang chạy. Các luồng chạy song song và không chặn nhau.

| Luồng | Ai mở | Luật mở đợt | Provider | Phạm vi bài | Nạp DB |
|---|---|---|---|---|---|
| Tự động (auto) | Daemon | T1, T2, T3, `/run`, chạy lại | Theo mandate, khoá theo đợt | Trong `sensor.lookback_days` | Có |
| Bài tồn (backlog) | Người, `--mode backlog` hoặc `adhoc` | Chạy tay | Chọn lúc mở, khoá theo đợt | Bất kỳ ngày; bài đang thuộc đợt khác bị loại | Có |
| Thử nghiệm (bench) | Người, `--mode bench` | Chạy tay | Chọn lúc mở | Cùng tập bài với luồng khác | Không |

Quy tắc phân luồng:

- Sensor, `/run` và `/retry` chỉ xét đợt của luồng tự động. Đợt tay đang chạy không làm daemon ngừng mở đợt.
- Hai luồng không lấy trùng bài. Bài đã thuộc đợt chưa xong bị loại khi đóng gói. Luồng thử nghiệm không giữ chỗ nên không bị loại.
- `/stop` và `AGY_STOP` huỷ mọi đợt đang chạy ở cả ba luồng.
- Muốn đẩy bài cụ thể vào luồng tự động thì không dùng chạy tay: để sensor mở đợt, hoặc gõ `/run`.
