# Lập trường 4 — Red team: an ninh và chế độ hỏng

- **Đối tượng phản biện:** `plans/20261001-1100-autonomous-ops-24x7/plan.md` (bản 2026-10-01).
- **Phạm vi đọc:** plan, mã chưa commit `project/src/ops/*` (16 module), `project/config/ops.yaml`, `openrouter/check_key.py`, `git diff project/src/agent/openrouter_runner.py`, `project/tests/test1.py`, `.gitignore`, `openrouter/.gitignore`, `scripts/article_run.py` (`cmd_finish`), `scripts/l1_ingest.py`, `scripts/token_ledger.py`.
- **Phương pháp:** chỉ đọc. Không chạy pytest, đợt, daemon. Không gọi Telegram, OpenRouter, healthchecks. Không in giá trị bí mật.
- **Kết luận một dòng:** thiết kế control plane tất định là đúng hướng, nhưng mặt điều khiển từ xa hiện được bảo vệ bằng đúng một yếu tố (`chat.id`), kênh được chọn (Telegram) đang bị chặn ở Việt Nam, và mã đã viết trước khi ADR 0012 được duyệt.

---

## 1. Mô hình đe doạ

| Tài sản | Vì sao quan trọng |
|---|---|
| Quyền điều khiển pipeline (mức tự chủ, provider, nạp DB, giao xlsx) | Một lệnh sai làm dữ liệu đi ra bên thứ ba hoặc giao tệp sai cho người dùng nội bộ |
| Bot token Telegram, URL ping healthchecks, OpenRouter key, phiên đăng nhập agy | Ai cầm token bot là đọc được mọi cảnh báo và giả được phản hồi; ai cầm OpenRouter key là tiêu tiền của tài khoản |
| Nội dung bài, danh mục theo dõi, tên người dùng nội bộ | Danh mục mã CP theo dõi của công ty chứng khoán là thông tin nghiệp vụ; tên nhân viên là dữ liệu cá nhân |
| Tính toàn vẹn `monocle.db`, `token_ledger` | Đợt nạp dở hoặc sổ cái nhân đôi làm sai số liệu báo cáo |
| Tư thế an ninh của máy công ty | Plan đề xuất loại trừ Defender và auto-logon |

| Tác nhân | Đường vào |
|---|---|
| Người nhặt được hoặc trộm điện thoại đã mở khoá | Ứng dụng Telegram đang đăng nhập, bấm nút còn hiệu lực |
| Kẻ chiếm tài khoản Telegram (SIM swap, OTP qua SMS, phiên Telegram Web/Desktop để quên trên máy khác) | Gửi lệnh từ đúng `chat_id` trong danh sách trắng |
| Thành viên nhóm (nếu `chat_id` là nhóm) | Mã chỉ kiểm `chat.id`, không kiểm người gửi |
| Nội dung web bên ngoài (bài báo, thông điệp lỗi) | Lọt vào đuôi nhật ký, rồi vào ngữ cảnh của `ops-sentinel` |
| Hạ tầng mạng (proxy/TLS inspection của FPTS, nhà mạng chặn Telegram) | Thấy hoặc chặn lưu lượng bot; token nằm trong URL |
| Chính hệ thống (lỗi, reboot, cập nhật agy, OneDrive) | Hỏng giữa bước ghi, tiến trình trùng, tệp bị đồng bộ hoặc dehydrate |

---

## 2. Bảng phát hiện

Mức: **Chặn** (không triển khai P1/P4 khi chưa xử lý) · **Nặng** · **Vừa** · **Nhẹ**.

| Mã | Mức | Kịch bản tấn công hoặc hỏng | Bằng chứng | Biện pháp |
|---|---|---|---|---|
| R1 | Chặn | **Kênh chính bị chặn ở Việt Nam.** Cục Viễn thông (Bộ KH&CN) ngày 21/05/2025 yêu cầu nhà mạng chặn Telegram; báo chí ghi nhận khó truy cập không VPN từ 25/05/2025. Máy công ty chỉ dùng được Telegram qua VPN hoặc proxy ngoài, gần như chắc chắn trái chính sách CNTT của FPTS. Long polling thất bại liên tục, outbox phình (R11), toàn bộ R7 (điều khiển từ xa) không có. | Plan §3.3 chọn Telegram làm kênh chính; D1 chỉ hỏi "có được dùng theo chính sách FPTS không", không nhắc lệnh chặn. | D1 đổi thành câu hỏi văn bản cho bộ phận CNTT và Tuân thủ. Kênh chính thay bằng kênh được phê duyệt trong công ty (Teams/Outlook nội bộ, hoặc ntfy tự host trong mạng FPTS). Telegram chỉ còn là tuỳ chọn nếu có xác nhận bằng văn bản. |
| R2 | Chặn | **Một yếu tố xác thực, lệnh nâng quyền một chạm.** Kẻ cầm điện thoại gửi `/level L3`: nếu standing order hết hạn, mã tự gia hạn tối đa 7 ngày rồi đặt L3, tức tự nạp DB và tự giao xlsx. `/failover auto` + `/provider openrouter` đẩy bài ra bên thứ ba. `/unstop` gỡ cờ dừng mà người tại máy vừa đặt. `/reset agy` bỏ qua breaker AUTH. Chỉ `/stop` có xác nhận, và xác nhận gõ tay được (`/stop confirm`). Nhóm chat: mọi thành viên điều khiển được. | `daemon.py` `_handle_update`: chỉ so `chat.id`, không kiểm `from.id`, không kiểm `chat.type`. `commands.py:145-182` (`/level` tự `extend` tới `max_order_days`; `/provider`, `/failover`, `/unstop`, `/reset` không xác nhận). Nút không có nonce hay hạn. | Danh sách trắng theo cặp `user_id` + chat riêng (`chat.type == "private"`). Chia lệnh ba hạng: **đọc** (`/status /waves /log /digest`), **vận hành** (`/pause /stop /approve /reject /retry /run`), **nâng quyền** (`/level /order /provider /failover /reset /unstop`). Hạng nâng quyền chỉ nhận từ console cục bộ, hoặc từ xa kèm TOTP 6 số. Mỗi nút mang nonce một lần, hết hạn sau 15 phút. Bắt buộc mật khẩu 2 lớp Telegram, không dùng OTP SMS. `/stop` vẫn một chạm (hạ quyền luôn an toàn); `/unstop` chỉ cục bộ. |
| R3 | Nặng | **Bot token rò qua chuỗi ngoại lệ.** `requests` đưa URL vào thông điệp lỗi (`Max retries exceeded with url: /bot<token>/getUpdates`). Chuỗi này được lưu vào `ops_alerts.last_error` và `ops_events` (kể cả JSONL), hiện trên `/log` và TUI, và đi vào ngữ cảnh `ops-sentinel`, tức gửi sang Google qua agy. | `notify.py:33` (token trong `base` URL), `notify.py:132` (`str(exc)[:300]` vào `last_error`), `daemon.py` `_telegram_loop` (`str(exc)[:200]` vào sự kiện `telegram.poll_error`), `sentinel.py:95` (`store.events(limit=40)` không lọc mức `debug`). | Một hàm `redact()` dùng chung, chạy trên mọi chuỗi trước khi ghi `ops_events`, `ops_alerts`, JSONL, nhật ký bước: che `bot\d+:[\w-]+`, `sk-or-[\w-]+`, URL healthchecks, `Bearer …`. Có test hồi quy với ngoại lệ `ConnectionError` thật. |
| R4 | Nặng | **Bí mật để dạng văn bản thuần, một phần trong OneDrive.** `openrouter/.env` (gitignored nhưng nằm trong thư mục OneDrive của công ty) đã được đồng bộ lên đám mây, lưu cả lịch sử phiên bản. `secrets/ops.env` là tệp thuần, không ACL. Plan nói "Credential Manager" nhưng mã không dùng. | `openrouter/.env` có 3 khoá (đã kiểm độ dài, không in giá trị); `openrouter/.gitignore:1`. `config.py:127,131-171` (`load_secrets`, `write_secret` ghi thuần). `openrouter_runner.py` đọc `OPENROUTER_ENV = PROJECT_ROOT.parent / "openrouter" / ".env"`. | Xoay vòng OpenRouter key hiện tại (coi như đã lộ do nằm trong lịch sử OneDrive). Chuyển mọi bí mật sang `keyring` (Windows Credential Manager); tệp dự phòng nếu có thì đặt ngoài OneDrive và `icacls` chỉ cho người dùng hiện tại. Đặt trần chi tiêu trên OpenRouter key. `openrouter/.env.example` hiện chỉ chứa giá trị mẫu (đã kiểm độ dài), giữ nguyên. |
| R5 | Nặng | **Failover đưa bài vào chương trình stealth có huấn luyện.** Model mặc định của runner OpenRouter là một stealth model. Điều khoản chương trình stealth của OpenRouter cho phép nhà cung cấp ẩn danh ghi đầy đủ và dùng nội dung để huấn luyện, trừ khi thẻ model nói khác. `failover=auto` trong mã tự chuyển provider mà không kiểm điều kiện "người đã duyệt trước dữ liệu và chi phí" như plan §6.3 viết. Ngoài bài báo công khai, prompt còn mang system core của dự án (cần kiểm xem có chứa danh mục theo dõi hay không), tức hàm ý mối quan tâm đầu tư của công ty chứng khoán. | `openrouter_runner.py:47` (`DEFAULT_MODEL`), payload không có `provider.data_collection`/ZDR. `daemon.py` `sensor_tick`: `if order.failover == "auto" and self.breakers.allow(other)[0]: provider = other`. | Cấm model stealth và model không có cam kết không lưu (whitelist model trong `ops.yaml`). Gửi `provider: {"data_collection": "deny"}` hoặc chỉ dùng endpoint ZDR. `auto` chỉ có hiệu lực khi standing order chứa bản ghi duyệt (model, điều khoản, hash, ngày). Ghi `provider`, `model` vào provenance mỗi bài. |
| R6 | Nặng | **`/stop` và `AGY_STOP` giết `--finish` giữa chừng; `--finish` không nguyên tử.** `--finish` là chuỗi tiến trình con: expand → `l1_ingest` → `agent_ingest` → verify → ledger → handoff. Bị kill (hoặc Windows Update reboot) giữa hai lệnh nạp thì lớp thực thể có, lớp nội dung không. Nạp dùng `INSERT OR REPLACE` nên chạy lại an toàn, nhưng `token_ledger` dùng `INSERT` thường, chạy lại sau bước ledger sinh dòng trùng. Đợt bị huỷ ở bước finish rơi vào FAILED và tính vào chuỗi tự hạ mức. Plan §8.1 hứa "huỷ ở ranh giới step kế tiếp", mã thì kill ngay. | `wave_flow.py` `_run`: `stop_fn=lambda: self.stop_requested(...)` áp cho mọi bước, kể cả `finish`. `procrun.py run_step`: `stop_fn()` → `kill_tree`. `article_run.py:633-657`. `token_ledger.py:238,283`. | Bước `finish` không nhận `stop_fn`, chỉ chịu deadline. Ghi mốc `finish:<bước con>` vào `ops_waves` để chạy lại bằng `--only` đúng phần còn thiếu. Ledger upsert theo `(wave, batch_id, agent_id)`. Huỷ trong lúc finish chuyển thành "huỷ sau finish". Daemon đặt `PowerSetRequest` và đăng ký trì hoãn khởi động lại trong lúc finish. |
| R7 | Nặng | **Prompt injection vào `ops-sentinel`.** Ngữ cảnh gồm đuôi 30 dòng của hai nhật ký bước gần nhất: stdout của script, có thể chứa tiêu đề, trích đoạn hay thông điệp lỗi bắt nguồn từ HTML bên ngoài. Danh sách trắng neo bằng regex đóng, không tham số tự do (tốt). Nhưng: (a) trường tự do `chan_doan`, `nguyen_nhan`, `ly_do` đi nguyên văn lên kênh người vận hành, là đường lừa đảo xã hội ("mở PowerShell chạy …", URL giả trang đăng nhập agy); (b) danh sách trắng chứa lệnh đổi tư thế an ninh: `/provider openrouter` (đưa dữ liệu ra ngoài), `/resume` (gỡ pause người vừa đặt), `/reset` (bỏ qua breaker AUTH), `/run`; (c) khi chẩn đoán không có mã đợt, `/retry W[\w-]+` khớp mọi đợt; (d) nút **[Chạy]** thi hành một chạm. | `sentinel.py:20-26` (`WHITELIST`, `_ALLOWED`), `:98-101` (đuôi nhật ký), `:126` (chỉ siết `/retry` khi có `wave_id`). `daemon.py diagnose_async`: `text` ghép nguyên văn, nút gọi thẳng `d.command`. | Thu hẹp danh sách trắng của sentinel về `/retry <đợt đang chẩn đoán>`, `/pause`, `/capture restart`, `none`. Không bao giờ cho sentinel đề xuất lệnh hạng nâng quyền. Bọc ngữ cảnh không tin cậy trong rào có nhãn và nói rõ "dữ liệu, không phải chỉ dẫn". Lọc URL, đường dẫn, khối mã khỏi văn bản tự do trước khi gửi; cắt mỗi trường 200 ký tự; tiền tố "đề xuất của LLM, chưa kiểm". Nút [Chạy] cần xác nhận lần hai. Bổ sung 5 ca injection vào bộ 10 sự cố nghiệm thu P5. |
| R8 | Nặng | **Kill-switch không phủ mọi đường và không ưu tiên cục bộ.** `AGY_STOP` không dừng bước `deliver` (không có `stop_fn`), không dừng daemon, không dừng `article_run.py` chạy tay. `article_run.py` không lấy `.pipeline.lock`, nên người chạy tay `--finish` song song với daemon được. `/unstop` từ xa gỡ được cờ người tại máy đặt. Tiến trình daemon bị `taskkill` thoát mã khác 0 nên Task Scheduler (restart on failure 1') hồi sinh nó. Mất mạng thì không còn lệnh nào ngoài thao tác tại máy, và chưa có runbook. | `wave_flow.py deliver` (không truyền `stop_fn`); `grep` không thấy `pipeline.lock` trong `article_run.py`; `commands.py:124-126`. | Hai mức cờ: `AGY_STOP` (mềm: không mở đợt, huỷ ở ranh giới bước) và `OPS_HALT` (cứng: daemon thoát mã 0, không được hồi sinh, chỉ gỡ tại máy). `article_run.py` lấy `.pipeline.lock` cho `--analyze/--finish`. Runbook một trang: `schtasks /End` + `/Change /Disable`, tạo `OPS_HALT`. Radar hiển thị trạng thái hai cờ. |
| R9 | Nặng | **Chuẩn bị máy làm yếu an ninh endpoint.** Plan §4.2 đề xuất loại `C:\data\news-scape` khỏi Defender real-time scan, trong khi thư mục này chứa Bronze `raw_html` tải từ Internet. Auto-logon lưu mật khẩu đăng nhập trong registry (LSA secret). Tắt sleep, tắt khoá có thể trái GPO. | Plan §4.2 "Chuẩn bị máy", D2. | Không loại trừ cả thư mục. Nếu cần hiệu năng SQLite thì xin CNTT loại trừ theo đường dẫn tệp cụ thể (`*.db`, `*.db-wal`). Auto-logon chỉ với máy chuyên dụng và tài khoản do CNTT cấp. Mọi thay đổi `powercfg`/GPO đi qua phiếu CNTT. |
| R10 | Nặng | **Triển khai trước khi duyệt.** Plan ghi "Chưa có dòng mã nào" và lane triển khai là high-risk, cần ADR 0012 cùng duyệt. Thực tế `project/src/ops/` đã có 16 module (tạo 10:35–10:45 hôm nay, chưa commit), gồm luồng Telegram hai chiều, sentinel, failover tự động. Hội đồng đang phản biện một tài liệu đã lạc hậu so với mã. | `ls -la project/src/ops/`, `git status` (untracked). AGENTS.md §0 Cấp 3. | Đóng băng nhánh mã cho tới khi ADR 0012 được duyệt; hoặc cập nhật plan cho khớp mã rồi phản biện lại. Không bật `NEWS_SCAPE_TG_TOKEN` trên máy thật trước khi R1–R3 đóng. |
| R11 | Vừa | **Outbox không backoff, không hạn.** Telegram bị chặn thì luồng gửi thử lại mỗi 3 giây vô thời hạn, `attempts` tăng mãi. Khi thông lại, tin cũ đổ dồn, kèm nút vẫn bấm được ("Lên L3", "Dùng openrouter", "Gia hạn 7 ngày"). | `daemon.py _alert_loop` (`wait(3)`), `notify.drain_alerts` (không TTL, không trần `attempts`). | Backoff mũ tới 15'. TTL theo mức (info 2 giờ, warn 12 giờ, critical không hết). Tin quá hạn gộp thành một bản tóm tắt, bỏ nút. Nút mang hạn (R2). Toast Windows làm kênh cục bộ dự phòng. |
| R12 | Vừa | **Rò siêu dữ liệu ra kênh không mã hoá đầu cuối.** Bot API không có E2E; máy chủ Telegram (và proxy TLS của công ty) thấy mọi tin. Cảnh báo breaker và `--finish` đính 300 ký tự cuối nhật ký: đường dẫn `C:\Users\<tên>\OneDrive - fpts.com.vn\…` lộ tên nhân viên và tổ chức; `write_user_output.py` in danh sách người dùng bật, đi vào nhật ký `deliver` rồi vào ngữ cảnh sentinel. Plan §8.1 cam kết "không nội dung" nhưng không có cơ chế lọc. | `wave_flow.py` `_record_breaker(..., res.tail[-300:])`, `drive_wave` (`fin[2][-300:]` vào `reason`); `write_user_output.py:36,54`. | Tin gửi ra ngoài dựng từ danh sách trường cho phép (mã đợt, trạng thái, số đếm, lớp lỗi, lệnh xem tại máy), không bao giờ đính `tail`. Chi tiết chỉ xem qua console cục bộ. Tên người dùng nội bộ coi là dữ liệu cá nhân. |
| R13 | Vừa | **Dữ liệu đợt vẫn nằm trong OneDrive.** Guard "không OneDrive" chỉ áp cho `ops.db`; packet và đầu ra mô hình vẫn ở `project/data/agent_tasks/article/` và `agent_outputs_article/` trong OneDrive. Rủi ro: tệp bị OneDrive giữ khoá lúc ghi, bản xung đột `-DESKTOP-` (đã từng xảy ra, có trong `.gitignore`), Files On-Demand dehydrate tệp cũ, nhịp tiến độ đếm sai, nội dung bài cùng đầu ra phân tích được đẩy lên đám mây. | `wave_flow.py:19-21` (`TASK_DIR`, `OUT_DIR` dưới `PROJECT_ROOT`); `config.py:115-117` chỉ chặn `data_dir`. | Chuyển `agent_tasks/` và `agent_outputs*/` ra `C:\data\news-scape\` (đổi đường dẫn qua `resolve_db_path`). Preflight từ chối chạy khi hai thư mục này nằm trong OneDrive. |
| R14 | Vừa | **Không xoay vòng nhật ký, đĩa đầy.** JSONL theo ngày, `waves/<đợt>/<bước>.log` ghi nối, `ops_events`, bảng hệ thống DBOS, `capture.log` không có retention. Đĩa đầy thì SQLite lỗi, vòng chính ghi lỗi vào chính DB lỗi. `probe_disk` chỉ cảnh báo. | `store.py` (không có lệnh xoá), `procrun.py` (`open(log_path, "a")`). | Retention 30 ngày cho JSONL và nhật ký bước, trần 5 MB mỗi tệp bước, dọn `ops_events` debug sau 7 ngày. Đĩa dưới ngưỡng: daemon vào chế độ chỉ ping healthchecks `/fail` kèm lý do. |
| R15 | Vừa | **`ops.db` hoặc `ops_dbos.db` hỏng hay bị xoá.** Breaker mất trạng thái nên đóng lại và đốt quota; workflow dở bị `reconcile` đánh FAILED; offset Telegram về 0 nên lệnh cũ được xử lý lại. | `daemon.py reconcile`, `tg_offset` lưu trong `ops_state`. | `PRAGMA quick_check` khi khởi động. Sao lưu hằng ngày bằng `sqlite3 .backup`. Không mở được `ops.db` thì chạy L0, chỉ ping healthchecks. Bỏ qua cập nhật Telegram cũ hơn thời điểm khởi động. |
| R16 | Vừa | **agy tự cập nhật.** Hội đồng 23/09 đã thấy 1.2.7 → 1.2.9. Định dạng `stream-json` đổi thì parser trả rỗng, breaker EMPTY; nặng hơn, hành vi hồ sơ không tool có thể đổi. Plan liệt kê probe "agy version?", nhưng `probes.py` không có. | `probes.py` (5 probe, không có version). | Ghim phiên bản nếu agy cho phép; probe phiên bản mỗi giờ; đổi phiên bản thì hạ về L1, chạy canary 5 bài và cảnh báo. |
| R17 | Vừa | **Đồng hồ.** `now_vn()` cố định +07:00 và `_due` dùng `monotonic` (đúng). Nhưng standing order dùng `date.today()` theo giờ hệ thống; mã đợt `W%m%d%H%M` không có năm. Máy lệch giờ (NTP domain lỗi, pin CMOS) làm khung T3 và hạn standing order sai, healthchecks vẫn xanh. | `order.py` (`date.today()`), `daemon.py open_wave`. | Thống nhất `now_vn().date()`. Probe lệch giờ bằng header `Date` của phản hồi healthchecks (lệch > 2' thì cảnh báo). |
| R18 | Nhẹ | **URL ping healthchecks là bí mật kiểu bearer.** Ai có URL giả được nhịp tim và che sự cố chết máy. | `notify.ping_healthcheck`, body ping gửi `active=…`. | Dùng ping key + slug, cho qua `redact()`, không ghi vào sự kiện. |
| R19 | Nhẹ | **Tệp thử nghiệm có gọi mạng thật.** `project/tests/test1.py` đọc OpenRouter key và gọi API ngay ở mức module; hiện lỗi cú pháp (`anotations`) nên làm pytest báo lỗi thu thập, phá bất biến "pytest 100% PASS"; sửa chữ thì mỗi lần pytest gọi mạng bằng key thật. `openrouter/check_key.py` in toàn bộ JSON của `/auth/key` (không in key) và dùng đường dẫn tương đối. | `project/tests/test1.py:1,13-31`; `openrouter/check_key.py:5-21`. | Xoá `test1.py` khỏi `tests/` hoặc chuyển thành script thủ công ngoài bộ test. Test mạng phải đánh dấu `@pytest.mark.network` và mặc định bỏ qua. |

---

## 3. Tuân thủ (mức rủi ro, không thay ý kiến pháp chế)

- **Luật An ninh mạng 2018** và quy định về an toàn hệ thống thông tin của công ty chứng khoán (văn bản do Bộ Tài chính, UBCKNN ban hành): một kênh điều khiển từ xa vào hệ thống chạy trên máy công ty, đi qua dịch vụ nước ngoài đang bị nhà mạng trong nước chặn, gần như chắc chắn cần phê duyệt của CNTT và Tuân thủ. Bộ phận Tuân thủ FPTS cần xác định văn bản áp dụng cụ thể; tài liệu này không trích điều khoản.
- **Dữ liệu cá nhân.** Luật Bảo vệ dữ liệu cá nhân số 91/2025/QH15 có hiệu lực từ 01/01/2026, kế thừa khung của Nghị định 13/2023. Tên người dùng nội bộ, đường dẫn hồ sơ có tên nhân viên là dữ liệu cá nhân. Gửi chúng qua Telegram, Google (agy) hay OpenRouter là chuyển dữ liệu ra nước ngoài và cần căn cứ xử lý. Cách tránh rẻ nhất: không gửi (R12).
- **Thông tin nghiệp vụ.** Danh mục mã theo dõi và mức quan tâm theo mã là thông tin nội bộ. Bài báo công khai không nhạy cảm, nhưng tổ hợp "bài nào được ưu tiên" thì có.

---

## 4. Bổ sung FMEA §9

| Sự cố | Phát hiện | Tự xử lý | Người nhận gì |
|---|---|---|---|
| Telegram bị chặn hoặc proxy chặn | `getUpdates`/`sendMessage` lỗi liên tục > 15' | Backoff, chuyển kênh dự phòng (toast, email nội bộ) | Cảnh báo qua kênh dự phòng; healthchecks vẫn độc lập |
| Kill hoặc reboot giữa `--finish` | Mốc `finish:<bước con>` chưa đóng khi khởi động | Chạy lại bằng `--only` phần còn thiếu, ledger upsert | 🟠 "finish dở, đã chạy tiếp" |
| Hai tiến trình `--finish` cùng đợt (người chạy tay) | `.pipeline.lock` bận | Tiến trình thứ hai thoát | Thông báo tại terminal |
| Daemon trùng (Task Scheduler + chạy tay) | `ops_daemon.lock` (đã có) | Thể hiện sau thoát mã 3 | Sự kiện; không cảnh báo |
| Đĩa đầy | `probe_disk` < 5 GB, rồi < 1 GB | Ngừng mở đợt; < 1 GB thì chế độ tối thiểu | 🔴 qua healthchecks `/fail` |
| `ops.db` hỏng | `quick_check` lỗi | Chạy L0, bỏ cập nhật Telegram cũ | 🔴 |
| agy đổi phiên bản | Probe version | Hạ L1, canary | 🟡 |
| Đồng hồ máy lệch | So header `Date` | Không mở đợt theo T3 | 🟡 |
| OneDrive giữ khoá hoặc dehydrate tệp đợt | `PermissionError`/`OSError` trên thư mục đợt | Không áp dụng nếu đã chuyển ra `C:\data` (R13) | 🟠 |
| Máy khoá màn hình, GPO đăng xuất phiên rảnh hoặc ép khởi động lại | healthchecks im lặng; Event Log 1074 | Không tự xử lý được | 🔴 healthchecks; xin CNTT ngoại lệ GPO |
| Phiên đăng nhập agy hết hạn trong hồ sơ cô lập của sentinel | Lỗi AUTH riêng của sentinel | `/diagnose` trả "sentinel không chạy được" | 🟡, không ảnh hưởng đợt |
| Điện thoại mất hoặc tài khoản Telegram bị chiếm | Lệnh nâng quyền không có TOTP bị từ chối; lệnh lạ trong `human.command` | Từ chối, ghi sự kiện | 🔴 qua kênh dự phòng; runbook thu hồi token bot (`/revoke` với BotFather) |
| Prompt injection làm sentinel đề xuất lệnh lạ | Lệnh ngoài danh sách trắng bị ép `none` | Không thi hành | Sự kiện `sentinel.rejected` |
| Failover sang OpenRouter khi chưa duyệt điều khoản dữ liệu | Standing order thiếu bản ghi duyệt | Không chuyển, PARKED | 🟠 kèm nút chỉ ở hạng nâng quyền |

---

## 5. Điều plan và mã làm đúng

- Agy không làm vòng điều phối; control plane tất định, 0 token, sống độc lập với provider (§4.1).
- Dead-man ngoài máy là tín hiệu duy nhất bắt được máy chết; đã chọn đúng (§3.3, §4.2).
- `ops-sentinel` chạy hồ sơ cô lập `tools: []`, `permissions.allow: []`, chỉ đề xuất; danh sách trắng neo bằng regex đóng, lệnh lạ bị ép `none` (`sentinel.py:24-27,124-127`).
- Daemon một thể hiện bằng khoá `msvcrt` (`daemon.py acquire_locks`); `ops.db` ngoài OneDrive có guard tường minh (`config.py:115-117`).
- Standing order thiếu hoặc hết hạn thì về L0; tự hạ mức sau 2 đợt hỏng; mọi lệnh không chỉ đọc ghi `human.command` làm vết kiểm toán.
- Breaker bền phân lớp AUTH/QUOTA/NETWORK, không biến token thành cổng (đúng ADR 0010).
- Nạp DB dùng `INSERT OR REPLACE`, nên chạy lại nạp là an toàn; `DBOS application_version` được ghim để không bỏ rơi đợt dở khi sửa mã.
- Bot chỉ dùng long polling: không mở cổng vào, không cần IP public.
- `/stop` thiên về an toàn (hạ quyền), có xác nhận hai bước.

---

## 6. Điều kiện để lập trường này chuyển sang "đồng ý"

1. R1 có câu trả lời bằng văn bản của CNTT/Tuân thủ, hoặc kênh chính đã đổi.
2. R2, R3, R7 đóng trước P4 (điều khiển hai chiều) và P5 (sentinel); P1 chỉ gửi đi được phép sau khi R3, R12 đóng.
3. R6, R8 đóng trước khi lên L2.
4. R5 đóng trước khi `failover` được nhận giá trị khác `never`.
5. R10: plan cập nhật khớp mã hiện có, hoặc mã đóng băng tới khi ADR 0012 được duyệt.

## 7. Nguồn

- Lệnh chặn Telegram tại Việt Nam: [The Record](https://therecord.media/vietnam-orders-telegram-messaging-ban), [Al Jazeera](https://www.aljazeera.com/news/2025/5/24/vietnam-orders-ban-on-popular-messaging-app), [RFA](https://www.rfa.org/english/vietnam/2025/05/23/vietnam-telegram-ban/).
- OpenRouter: [Stealth Program EULA](https://openrouter.ai/terms/stealth), [Zero Data Retention](https://openrouter.ai/docs/guides/features/zdr).
- Luật 91/2025/QH15: [VnEconomy](https://vneconomy.vn/nhung-diem-moi-trong-luat-bao-ve-du-lieu-ca-nhan-tu-112026.htm), [LuatVietnam](https://english.luatvietnam.vn/dan-su/law-on-personal-data-protection-law-no-91-2025-qh15-405135-d1.html).
