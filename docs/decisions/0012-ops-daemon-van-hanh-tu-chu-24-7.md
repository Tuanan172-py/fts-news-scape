# ADR 0012 — Control plane vận hành tự chủ 24/7: ops_daemon, workflow DBOS, Telegram HITL

- **Ngày:** 2026-10-01
- **Trạng thái:** **accepted**, thay thế một phần bởi ADR 0014: standing order 7 ngày đã thành mandate 30 ngày tự gia hạn, và các cấp L2, L3 đã gỡ. Người dùng duyệt ngày 2026-10-01 ("đồng ý thực thi toàn bộ kế hoạch"), theo thiết kế `plans/20261001-1100-autonomous-ops-24x7/plan.md`. Đọc khối "SỬA ĐỔI 2026-10-01" bên dưới trước thân bài; các mục 24/7, L0–L3 và nút duyệt ở thân bài đã hết hiệu lực.
- **Lane:** high-risk: automation substrate, DB vận hành mới (`ops.db`), kênh điều khiển từ xa.
- **Story:** US-029.
- **Kế thừa:** ADR 0010 (Article Lane duy nhất, token là số ghi nhận), ADR 0011 (runner agy, `article_tick.py`, `AGY_STOP`, standing order).

> ## SỬA ĐỔI 2026-10-01 (sau hội đồng phản biện) — có hiệu lực, thay các mục mâu thuẫn bên dưới
>
> Nguồn: `docs/proposals/ops-council-2026-10-01.md` §2 (mục Chặn B1–B7) và §9 (quyết định D1', D8–D14 của người vận hành).
>
> **Mô hình vận hành (D9, D10).** Không chạy 24/7. Máy mở thì daemon chạy; máy ngủ hoặc tắt thì mọi thứ dừng, bài nằm chờ. Bỏ tắt sleep, auto-logon, loại trừ Defender. Dead-man chính là task watchdog cục bộ (`ops_daemon.py watchdog` mỗi 5'), chỉ báo khi nhịp tim cũ ở hai lần kiểm liên tiếp, nên không báo giả lúc máy ngủ. healthchecks.io thành tuỳ chọn.
>
> **Thang tự chủ còn L0 và L1.**
> - L0 chỉ đo và báo.
> - L1 mở đợt khi đủ điều kiện và chạy trọn tới nạp DB, không có cổng duyệt từng đợt, khớp amendment ADR 0008 ("không dựng lại cổng hỏi người dưới bất kỳ tên nào"). Trạng thái `AWAIT_APPROVAL`, lệnh `/approve`, `/reject` đã gỡ.
> - Tệp lệnh cũ ghi L2/L3 được đọc thành L1.
> - `article_tick.py` (ADR 0011) vẫn hiểu L1 là "chỉ phân tích". Tệp lệnh daemon ghi L1 nên `article_tick` chạy tay sẽ an toàn theo hướng không nạp DB. `article_tick` không còn được lên lịch.
>
> **Giao hàng (D11)** không thuộc vòng đời đợt; DB là nguồn sự thật, giao hàng là quy trình riêng cấu hình theo người dùng (story riêng).
>
> **Dữ liệu (D8).** Được gửi toàn văn bài đã làm sạch cho mọi provider. Packet chỉ mang `i/t/p`. Dữ liệu nội bộ (log, cấu hình, secret) không đi theo payload; mọi sự kiện, cảnh báo và ngữ cảnh `ops-sentinel` đi qua `src/ops/redact.py`.
>
> **Sửa các mục Chặn:**
>
> | Mã | Sửa |
> |---|---|
> | B2 | `ops_wave_articles` giữ chỗ bài cho đợt chưa DONE/CANCELLED; sensor và `article_pack --exclude-file` bỏ qua bài giữ chỗ |
> | B3 | Tiến trình bước tạo ở trạng thái treo, gắn Job Object `KILL_ON_JOB_CLOSE` của daemon rồi mới chạy (vượt qua job `SILENT_BREAKAWAY_OK` của launcher venv) |
> | B4 | `ops_article_attempts`; bài đóng gói đủ `max_attempts_per_article` lần không được tự thử lại |
> | B5 | `redact()` che token Telegram, URL healthchecks, khoá `sk-`, Bearer trước mọi lần ghi và trong lỗi gửi Telegram |
> | B6 | `--finish` không nhận AGY_STOP/`/cancel` giữa chừng; cờ dừng chỉ đọc ở ranh giới trước bước nạp. Sổ cái agy thay dòng cũ khi chạy lại |
> | B7 | Workflow bắt ngoại lệ của step và chốt FAILED; daemon đối chiếu workflow ở mỗi nhịp sensor (`APP_VERSION = ops-v2`) |
> | R2 | Telegram chỉ nhận chat riêng, `from.id` trùng chat id trong danh sách; cấu hình bot không tự thêm nhóm; lệnh nâng quyền cần xác nhận |
>
> **Tải lên DB vận hành.** Sensor không đọc cột nội dung, và không đo khi đang có đợt. Probe thử ghi không chạy khi đang có đợt.
>
> **Hai lỗi chỉ lộ ra khi chạy dưới Task Scheduler:**
> - **Priority.** Task mặc định chạy ở priority 7, tức CPU và I/O ưu tiên thấp, và mọi tiến trình con đều thừa hưởng mức này. Hệ quả đo được: một lượt sensor mất 1,3 s khi chạy tay nhưng 40–396 s khi chạy trong task. `ops_install.ps1` nay đặt `-Priority 4`; sau khi sửa, lượt đo có kèm tồn đọng còn 6,2 s.
> - **Đường dẫn agy.** PATH của người dùng lưu `%LOCALAPPDATA%\agy\bin` ở dạng chưa bung biến, nên `agy` trần báo WinError 2 (đợt W10011351, 0 token). `agy_runner.resolve_agy()` tìm theo thứ tự: `AGY_BIN`, PATH, PATH đã bung biến, rồi vị trí cài đặt.
>
> Bằng chứng: `tests/test_ops_council_fixes.py` (test mang mã B2–B7, R2, D9, D10).

## 1. Bối cảnh

Đo ngày 2026-10-01:
- Các khâu end-to-end đã chạy được.
- `morninger` được khởi động tay; nó chết khi máy khởi động lại hoặc khi đăng xuất.
- `article_tick.py` chưa được lên lịch ở đâu.
- Không có heartbeat, không có cảnh báo vận hành.
- Không có trạng thái bền của đợt: crash giữa đợt là mất dấu.
- Người vận hành phải có mặt để kích hoạt từng đợt.

## 2. Quyết định

1. **Control plane là Python tất định, 0 token** (`project/src/ops/`), chạy một tiến trình `ops_daemon.py run`.
   - Task Scheduler giữ tiến trình này bằng hai trigger: lúc đăng nhập, và lặp mỗi 5 phút làm watchdog.
   - Task chạy dưới tài khoản người dùng: agy đọc thông tin đăng nhập trong hồ sơ người dùng, Session 0 không thấy được.
   - agy **không** làm vòng điều phối.
2. **Lớp bền là DBOS 3.x** trên SQLite riêng `C:\data\news-scape\ops_dbos.db`.
   - Mỗi đợt là một workflow `wave-<mã>[-r<n>]`, mỗi bước là một step có checkpoint.
   - `application_version` được ghim (`ops-v1`), vì DBOS chỉ khôi phục workflow cùng phiên bản.
   - Spike trên máy này đạt: kill giữa bước 2 thì bước 1 không chạy lại, bước 2 chạy lại, cùng ID trả kết quả cũ.
   - Bước có thể chạy lại (at-least-once), nên `prepare` bỏ qua khi manifest đã có. `analyze` chuyển sang `--repair` khi đã có đầu ra, nên không tiêu lại token cho lô đã xong.
3. **Trạng thái vận hành** nằm trong `C:\data\news-scape\ops.db`, gồm `ops_events`, `ops_alerts` (outbox), `provider_breakers`, `ops_state`, `ops_waves`, `ops_commands`.
   - **Không đổi lược đồ `monocle.db`.**
   - Sự kiện được ghi kèm bản sao JSONL tại `ops_logs/`.
4. **Sensor** chạy mỗi 2 phút ở luồng riêng. Phạm vi: bài chờ hôm nay và hôm qua, theo đúng bộ chọn `article_pack.load_candidates`. Mở đợt khi thoả một trong ba luật:
   - **T1:** ≥ 100 bài chờ.
   - **T2:** bài chờ lâu nhất > 90 phút, chỉ áp trong 06–22h.
   - **T3:** chạm khung giờ vét.

   Mỗi lúc chỉ một đợt (WIP đợt = 1). Đợt lấy 100 bài, chia lô 50. Tồn đọng cũ hơn phạm vi chỉ được báo, không tự xử lý.
5. **Thang tự chủ L0–L3**, do standing order có hạn ≤ 7 ngày quyết định. Thiếu lệnh hoặc lệnh hết hạn thì về L0.

   | Mức | Daemon làm gì |
   |---|---|
   | L0 | Chỉ báo, kèm nút **Chạy đợt** |
   | L1 | Phân tích xong thì chờ nút **Nạp DB**; quá 120 phút thì đợt PARKED |
   | L2 | Tự `--finish` |
   | L3 | Thêm bước giao xlsx |

   2 đợt hỏng liên tiếp thì tự hạ một bậc. 5 đợt sạch liên tiếp thì chỉ gợi ý lên bậc, người quyết.
6. **Circuit breaker bền theo provider**.
   - Lớp lỗi: AUTH, QUOTA, NETWORK, TIMEOUT, EMPTY.
   - AUTH mở tới khi người reset. QUOTA mở 5 giờ. NETWORK và TIMEOUT mở sau 3 lỗi liên tiếp.
   - Hết hạn mở thì chuyển HALF_OPEN và thử lại.
   - Đợt PARKED vì provider tự chạy tiếp khi breaker cho phép.
   - Chuyển provider theo standing order: `never` (mặc định), `ask` hoặc `auto`.
   - **Không có trần token**: bác bỏ "quota guard 3M token/ngày" của hội đồng 23/09 vì trái ADR 0010.
7. **Timeout nhiều tầng.**
   - Lượt gọi agy: 600 s, đã có trong runner.
   - Deadline từng bước: analyze 45 phút, finish 10 phút, các bước khác theo `config/ops.yaml`.
   - Tiến độ của analyze đứng yên quá 25 phút thì coi là treo.
   - Quá hạn thì kill cả cây tiến trình.
8. **Phát hiện chết bằng ba tín hiệu độc lập.**
   - Nhịp tim cục bộ mỗi 60 s.
   - Ping healthchecks.io ngoài máy (dead-man).
   - Probe theo cạnh: cào tin tươi, DB ghi được, đĩa, dead-letter tăng, hạn standing order.
9. **Human-in-the-loop.**
   - Telegram bot dùng long polling, chỉ nhận lệnh từ `chat_id` trong danh sách trắng, chỉ gửi siêu dữ liệu vận hành.
   - Bảng điều khiển `ops_console.py` mở bằng Ctrl+Alt+O trong quake window của Windows Terminal.
   - Radar có mục "Vận hành tự chủ".
   - Mọi lệnh của người đều thành sự kiện `human.command`.
10. **`ops-sentinel`** (agy, một lượt, không tool, draft) chẩn đoán khi được gọi. Nó chỉ đề xuất một lệnh trong danh sách trắng, dưới dạng nút bấm.

## 3. Hệ quả

- Thêm phụ thuộc `dbos`, `psutil`.
- `build_sandbox_profile` có thêm tham số `agent_name`, `description`, `instruction_guard`; giá trị mặc định giữ hành vi cũ.
- Khi daemon sống ở mức ≥ L1, radar không đề xuất mở đợt tay.
- `article_tick.py` vẫn chạy tay được và dùng chung `.pipeline.lock` với daemon.

## 4. Quay lui

- Dừng ngay: `/stop`, hoặc tạo `C:\data\news-scape\AGY_STOP`.
- Gỡ hẳn: `scripts\ops_install.ps1 -Uninstall`.
- Pipeline trở về vận hành tay qua `article_run.py`. Không dữ liệu nào trong `monocle.db` phụ thuộc `ops.db`.
