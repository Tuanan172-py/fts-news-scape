# Runbook — ops_daemon: vận hành tự chủ khi máy mở, người chỉ giám sát (ADR 0012, 0014)

Mọi lệnh chạy với cwd = `project/`, Python = `C:\venvs\news-scape\Scripts\python.exe`.

Mô hình: **máy mở thì hệ thống chạy, máy ngủ hoặc tắt thì mọi thứ dừng và bài nằm chờ.** Máy thức lại thì luật tuổi T2 vét phần tồn đọng thành chuỗi đợt. Không tắt sleep, không auto-logon, không loại trừ Defender.

## 1. Cài đặt một lần

| # | Việc | Lệnh |
|---|---|---|
| 1 | Đo thử, không mở đợt | `python scripts/ops_daemon.py once` |
| 2 | Tạo bot với @BotFather, nhắn `/start` cho bot **trong chat riêng**, rồi lưu token và chat id | `python scripts/ops_daemon.py telegram --token <TOKEN>` |
| 3 | (Tuỳ chọn) healthchecks.io để biết máy tắt lâu: period 1 ngày, grace vài giờ | `python scripts/ops_daemon.py healthcheck --url https://hc-ping.com/<uuid>` |
| 4 | Đăng ký task daemon và task watchdog, chạy ngay, tạo phím tắt Ctrl+Alt+O | `powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Register -Start -Shortcut` |
| 5 | Cấp mandate L1 (30 ngày, tự gia hạn khi hệ thống khoẻ) | gõ `/level L1` trên Telegram rồi bấm **Xác nhận**, hoặc `python scripts/ops_daemon.py order --level L1` |

- Bí mật nằm ở `C:\data\news-scape\secrets\ops.env`, ngoài kho mã và ngoài OneDrive.
- Không có mandate thì daemon ở **L0**: chỉ báo "đủ ngưỡng", không tự tiêu token. `/run` vẫn mở được một đợt theo lệnh của bạn.
- Bot chỉ nhận lệnh trong chat riêng, từ đúng người có mã trong danh sách. Nhóm bị từ chối.

## 2. Hằng ngày

- **Điện thoại:** bản tin giám sát 08:00, 18:00 và tin ngoại lệ. Đợt bình thường không có tin riêng (đặt `alerts.push_wave_info: true` nếu muốn); chỉ sự cố mới có chuông. Tra nhanh bằng `/map`, `/trace`, `/agent <id>`, `/mandate`, `/improve`.
- **Tại bàn:** `python scripts/ops_daemon.py open` mở **Phòng điều khiển** (http://127.0.0.1:8787, chỉ nghe máy này). Ctrl+Alt+O vẫn mở bảng điều khiển chữ trong quake window.
- **Radar:** mục 3 "Vận hành tự chủ" của `pipeline_radar.py status`.

## 3. Mức tự chủ

| Mức | Daemon tự làm | Người làm |
|---|---|---|
| L0 | Đo, báo | Bấm **Chạy đợt** (`/run`) nếu muốn |
| L1 | Đủ điều kiện thì mở đợt và chạy trọn: preflight → đóng gói → phân tích → vá → nạp DB qua cổng `--finish` | Xử lý cảnh báo, soát mẫu chất lượng |

- Không có nút duyệt từng đợt (amendment ADR 0008): cổng kỹ thuật của `--finish` quyết việc nạp DB.
- Giao xlsx không thuộc vòng đời đợt; DB là nguồn sự thật, giao hàng cấu hình theo người dùng.
- Mandate có hạn tối đa 30 ngày và **tự gia hạn** khi còn dưới 7 ngày và hệ thống khoẻ: không có sự kiện đỏ trong 24 giờ, chuỗi đợt sạch ≥ 5, không có chuỗi đợt hỏng, không có lượt gọi công cụ trái Zero-Tool trong 7 ngày. Không đủ điều kiện thì dừng gia hạn và báo lý do. Mandate đã hết hạn không tự cấp lại; gia hạn tay bằng `/order extend <ngày>` (bấm **Xác nhận**).
- 2 đợt hỏng liên tiếp thì L1 tự về L0 và báo đỏ.
- Lệnh nâng quyền (`/level L1`, `/order extend`, `/provider`, `/failover auto`) đều cần bấm xác nhận lần hai.

## 4. Bài của đợt và giới hạn thử lại

- Bài đã vào một đợt bị **giữ chỗ** cho tới khi đợt DONE hoặc CANCELLED. Đợt PARKED hay FAILED vẫn giữ bài, nên không đợt nào khác phân tích lại chúng.
- Mỗi bài được đóng gói tối đa `max_attempts_per_article` lần (mặc định 2). Quá số đó mà vẫn chưa qua DoD thì bài không được tự thử lại, và không làm luật tuổi T2 bắn lại vô hạn.
- Muốn nhả bài của một đợt hỏng cho đợt sau: `/cancel <đợt>`.
- Tồn đọng ngoài phạm vi `lookback_days` không thuộc phạm vi tự động; xử lý bằng task riêng.

## 5. Xử lý cảnh báo

| Cảnh báo | Nghĩa | Làm gì |
|---|---|---|
| 🔴 ops_daemon không còn nhịp tim | Watchdog thấy daemon chết hai lần kiểm liên tiếp trong lúc máy mở | `Start-ScheduledTask news-scape-ops`, xem `ops_logs/daemon.out.log` |
| 🔴 agy mất phiên đăng nhập | Breaker AUTH | Mở terminal, đăng nhập lại `agy`, rồi bấm **Reset agy** (`/reset agy`). Đợt PARKED tự chạy tiếp khi còn standing order. |
| 🟡 hết hạn mức (429) | Breaker QUOTA, tự mở lại sau 5 giờ | Không cần làm gì; hoặc `/provider openrouter`. |
| 🟠 mất kết nối provider | Breaker NETWORK | Kiểm mạng. Breaker tự thử lại sau 10'. |
| 🟠 Đợt FAILED/PARKED | Cổng `--finish` đỏ, độ phủ < 90% hoặc workflow dừng | **Chẩn đoán**, rồi **Chạy lại** (`/retry <đợt>`) hoặc **Huỷ, nhả bài** (`/cancel <đợt>`). |
| 🟠 [capture] cào tin đứng | morninger chết hoặc nguồn lỗi | Supervisor tự khởi động lại. Quá trần thì `/capture restart`. |
| 🔴 Tự hạ mức | 2 đợt hỏng liên tiếp | Chẩn đoán, sửa gốc, rồi `/level L1`. |

## 6. Dừng và quay lui

- Dừng khẩn: `/stop` (xác nhận hai bước), tạo `AGY_STOP`. Đợt đang chạy dừng ở ranh giới bước kế tiếp; **bước nạp DB đang chạy không bị cắt ngang**. Gỡ: `/unstop`.
- Tạm ngừng mở đợt mới: `/pause`, tiếp tục bằng `/resume`.
- Daemon chết thì Job Object kill trọn cây `article_run` → `agy` đang chạy, nên không lô nào tiêu token khi không ai giám sát.
- Gỡ hẳn: `scripts\ops_install.ps1 -Uninstall`, rồi vận hành tay bằng `article_run.py` như trước.

## 7. Tệp và nhật ký

| Đường dẫn | Nội dung |
|---|---|
| `C:\data\news-scape\ops.db` | Sự kiện, cảnh báo (outbox), breaker, đợt, bài giữ chỗ, số lần thử, lệnh |
| `C:\data\news-scape\ops_dbos.db` | Checkpoint workflow DBOS |
| `C:\data\news-scape\ops_logs\YYYY-MM-DD.jsonl` | Bản sao sự kiện theo ngày (bí mật đã che) |
| `C:\data\news-scape\ops_logs\waves\<đợt>\<bước>.log` | stdout/stderr từng bước; `exclude.txt` là tập bài bị loại khi đóng gói |
| `C:\data\news-scape\ops_logs\daemon.out.log`, `capture.log` | Đầu ra của daemon và của morninger do daemon sinh |
| `C:\data\news-scape\agy_standing_order.yaml` | Mức tự chủ, hạn, provider, failover |
| `project/config/ops.yaml` | Ngưỡng, deadline, lịch bản tin, chính sách breaker |

Sửa `config/ops.yaml` hoặc mã `src/ops` thì cần khởi động lại daemon: `schtasks /End /TN news-scape-ops`, rồi `schtasks /Run /TN news-scape-ops`.

## 8. Giám sát và cải tiến (người chỉ còn vai này)

| Màn (Phòng điều khiển) | Trả lời |
|---|---|
| Toàn cảnh | Bản đồ agent từ registry, màu theo vết hôm nay; dải trạng thái; điểm khác thường |
| Đợt | Gantt và cây vết: actor, skill, script, công cụ gọi, token, thời gian từng span |
| Tác nhân | Đặc tả từ registry và KPI 7 ngày của từng agent |
| Sự cố | Breaker, phép đo sức khoẻ, sự kiện cảnh báo, chẩn đoán của sentinel |
| Cải tiến | Hộp thư đề xuất kèm bằng chứng; **Mở story**, **Hoãn**, **Bác** |

- Vết ở bảng `ops_spans` (`ops.db`). Một đợt chưa có span nếu chạy trước khi bật US-031 hoặc chạy tay.
- Đề xuất tự sinh không bao giờ tự thi hành. **Mở story** tạo intake và story `US-IMP-nnn` ở trạng thái `planned`. **Hoãn** và **Bác** ẩn đề xuất 30 ngày.
- Cổng 8787 bị chiếm thì Phòng điều khiển bỏ qua (sự kiện `control_room.bind_failed`), daemon vẫn chạy. Đổi cổng trong `config/ops.yaml`, mục `control_room`.
- Sửa mã `src/ops` hoặc `config/ops.yaml` cần khởi động lại daemon.
