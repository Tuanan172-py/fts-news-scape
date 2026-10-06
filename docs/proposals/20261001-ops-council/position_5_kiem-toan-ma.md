# Vị trí 5 — Kiểm toán mã so với plan vận hành tự chủ 24/7

- **Ngày:** 2026-10-01
- **Phạm vi:** mã chưa commit trên nhánh `feature/article-lane-remove-gates`: `project/src/ops/` (15 module, khoảng 3.600 dòng, vẫn đang được phiên khác viết thêm trong lúc kiểm), `project/scripts/ops_daemon.py`, `project/scripts/ops_console.py`, `project/config/ops.yaml`, diff `openrouter_runner.py` và `agy_runner.py`, `project/tests/test1.py`, `openrouter/check_key.py`.
- **Phương pháp:** chỉ đọc. Kiểm cú pháp bằng `ast.parse` (mọi tệp đều qua) cộng `compile` cho `test1.py`. Không chạy pytest, daemon hay đợt. Đối chiếu với `article_run.py`, `article_pack.py`, `article_tick.py`, `agy_runner.py`, `pipeline_radar.py`.
- **Sự thật nền:** plan ghi "Chưa có dòng mã nào" và xếp phần triển khai vào lane high-risk, phải có ADR 0012 và người duyệt trước khi code. `docs/decisions/` hiện dừng ở 0011, nhưng mã, `ops.yaml` và `ops_daemon.py` đều trích "ADR 0012". Mã đã đi trước cổng.

---

## 1. Bản đồ mã ↔ plan

| Mục plan | Module hiện có | Mức hiện thực | Khác plan |
|---|---|---|---|
| §3.2 DBOS, spike P0 | `dbos_flow.py` (DBOS 3.2.0 đã cài trong venv), `config.py` (`ops_dbos.db`) | Workflow `wave_workflow`, step bọc `DirectOps`, `DBOS.recv/send` cho duyệt, `APP_VERSION` ghim | **Chọn DBOS mà chưa có spike.** Song song lại tự viết bảng `ops_waves` (status, step, progress_at) trong `store.py`. Hệ thống có hai nguồn trạng thái đợt: DBOS và `ops_waves` (xem C3). |
| §4.2 Supervisor | `supervisor.py` | Backoff 10→300 s, trần 5 lần/30', chế độ `external` khi `capture.lock` đang bị giữ | Đúng plan. |
| §4.2 Task Scheduler, wakepy, Job Object | (không có) | Chưa có `ops_install.ps1`, chưa giữ nguồn | `procrun.kill_tree` dùng psutil thay Job Object (C13). |
| §5.1 Sensor T1/T2/T3 | `sensor.py`, `daemon.sensor_tick` | Đủ ba luật. Có `force`, `paused`, `AGY_STOP`, WIP=1 | `lookback_days=1`: backlog cũ hơn nằm "ngoài phạm vi tự động" (C8). |
| §5.1 Định nghĩa `pending` | `sensor.read_pending` → `article_pack.load_candidates(only_pending=True)` | Loại code-first qua `ANALYZED_L1` | Khớp radar. **Không khớp** `count_pending_articles` (C8). |
| §5.2 Máy trạng thái | `wave_flow.drive_wave`, `WaveSteps` | preflight → prepare → analyze/repair ≤2 → duyệt → finish → deliver | **Thiếu bước canary.** L0 bị xử lý như L1 trong `drive_wave` (C9, C10). |
| §5.2 Deadline, nhịp tiến độ | `procrun.run_step` | Deadline, im lặng theo chữ ký tệp `*.output.json`, kill cây | Hàm dừng `stop_fn` áp cho cả `--finish` (C4). |
| §5.3 Standing order, tự hạ mức | `order.py`, `wave_flow.finalize` | Hạn ≤7 ngày, băm lệnh, hạ một bậc sau 2 đợt hỏng, gợi ý lên bậc sau 5 đợt sạch | Đúng plan. Ngày hết hạn dùng `date.today()` theo giờ máy (C16). |
| §6.1 Phân loại lỗi | `breakers.classify`, `classify_batch` | Đủ 7 lớp | AUTH chỉ nhận ra bằng regex trên văn bản. Runner không phát lớp AUTH/NETWORK (C7). |
| §6.2 Breaker bền | `breakers.Breakers`, bảng `provider_breakers` | CLOSED/OPEN/HALF_OPEN, `reopen_at`, AUTH mở vô hạn | Đúng plan, trừ canary. |
| §6.3 Chuyển provider | `daemon.sensor_tick` | `never/ask/auto` | Đúng plan. |
| §7.1 `ops_events` + JSONL | `store.emit` | Ghi DB và `ops_logs/YYYY-MM-DD.jsonl` | Đúng plan. Nhật ký bước ghi ở `ops_logs/waves/<wave>/<step>.log`. |
| §7.2 Outbox | `store.alert`, `notify.drain_alerts` | Gộp theo `dedup_key` 30', thử lại | Đúng plan. |
| §7.3 Bản tin, probe | `reports.py`, `probes.py`, `daemon.digest_tick` | Bản tin 08:00/18:00, probe capture/db/disk/dead-letter/order theo cạnh | `probe_db` giành khoá ghi mỗi 60 s (C12). |
| §8.1 Telegram | `daemon._telegram_loop`, `commands.py`, `notify.TelegramClient` | Đủ bảng lệnh và thêm `/unstop`, `/cancel`, `/reset`, `/capture`, `/digest` | Gộp vào daemon, không có `telegram_bot.py` riêng. Danh sách trắng và xác nhận hai bước còn yếu (C11). |
| §8.2 Console | `scripts/ops_console.py`, `store.ops_commands` | Hộp thư lệnh qua DB | Chưa có profile quake. |
| §8.3 Radar mục 4 | (không có) | Chưa có | — |
| §4.1, P5 ops-sentinel | `sentinel.py` | agy một lượt, có danh sách trắng lệnh, không tự thi hành | Chưa có trong `.agents/registry.yaml` (Rule 07). |
| P1–P5 bằng chứng | (không có) | **Không có test nào** cho `src/ops` | Không đạt định nghĩa Done của mọi phase. |

**Kết luận bản đồ.** Mã đã phủ P1 đến P5 cùng lúc, trái lộ trình WIP=1 "quan sát trước, tự động sau" của §10. Các tệp `events.py`, `alerts.py` và `telegram_bot.py` trong plan đã bị gộp vào `store.py`, `notify.py` và `daemon.py`.

---

## 2. Đối chiếu số liệu `ops.yaml` với plan

| Tham số | Plan | `ops.yaml` | Đánh giá |
|---|---|---|---|
| Ngưỡng T1 / tuổi T2 / chu kỳ sensor | 100 / 90' / 2' | 100 / 90 / 120 s | Khớp |
| T2 chỉ áp ban ngày | 06:00–22:00 (D6) | `age_rule_hours: [6, 22]` | Khớp |
| Khung vét T3 | "07:15 … ±15'" | `07:15-07:45` … | Plan mơ hồ. Mã kế thừa `article_tick.py:191`. Cần chốt trong ADR. |
| limit / batch | 100 / 50 | 100 / 50 | Khớp |
| Deadline preflight / prepare / analyze / repair / finish / deliver | 1 / 5 / 45 / 20 / 10 / 5 | 2 / 5 / 45 / 25 / 10 / 5 | Preflight và repair lệch |
| Im lặng tiến độ | 15' | 25' | Lệch, nhưng 25' hợp lý hơn: một lô agy có thể mất 2 × 630 s |
| Breaker TIMEOUT / NETWORK / QUOTA | 3→30' / 3→10' / mốc 5 giờ | 3/30, 3/10, 300' | Khớp |
| EMPTY | lặp 2 lần thì tính như TIMEOUT | `empty_trip: 2` mở breaker riêng | Lệch nhẹ |
| Duyệt L1, tự hạ mức, standing order | 120' / 2 / ≤7 ngày | 120 / 2 / 7 | Khớp |
| Supervisor, capture, dead-letter, dedup | 10 s→5', 5 lần/30', 30', 50, 30' | Khớp | Khớp |
| Phạm vi bài chờ | Cả backlog, chạy chuỗi đợt | `lookback_days: 1` | **Lệch nghĩa** (C8) |

---

## 3. Bảng phát hiện

| Mã | Mức | Vị trí | Phát hiện | Đề xuất sửa |
|---|---|---|---|---|
| C1 | Chặn | toàn bộ `src/ops/`, `ops.yaml:1`, `scripts/ops_daemon.py:1` | Mã high-risk được viết trước ADR 0012 và trước spike P0. Phương án DBOS đã được chọn ngầm (`dbos_flow.py:8`), đồng thời vẫn tự viết bảng lease/trạng thái `ops_waves` (`store.py:62-80`). `dbos` và `psutil` chưa có trong `requirements.txt`. 0 test. | Đóng băng. Lập ADR 0012, chạy spike trên `dbos_flow.py` hiện có. Spike phải chọn **một** nguồn trạng thái đợt. |
| C2 | Nặng | `notify.py:33`, `daemon.py:450`, `notify.py:132`, `sentinel.py:289` | **Lộ token bot Telegram.** Token nằm trong URL. `requests.ConnectionError` in ra `…url: /bot<TOKEN>/getUpdates…`, và `str(exc)[:200]` được ghi vào `ops_events`, JSONL và `ops_alerts.last_error`. Từ đó token đi tiếp ra `/log` trên Telegram và vào ngữ cảnh mà sentinel gửi cho agy. Sự cố mất mạng mà plan muốn báo lại chính là lúc token bị ghi. | Che `bot\d+:[\w-]+` trước mọi lần ghi lỗi. Thêm test cho hàm che. |
| C3 | Nặng | `daemon.py:104-122`, `daemon.py:253`, `wave_flow.py:189,197-201,223` | Một step ném ngoại lệ (manifest JSON hỏng, `map.json` hỏng, `disk_usage`, lỗi DB) làm workflow DBOS chuyển ERROR, còn `ops_waves` vẫn ở ANALYZING/PREPARED. `reconcile()` chỉ chạy lúc khởi động, nên `sensor_tick` dừng mãi ở `active_wave()`. WIP khoá chết, heartbeat vẫn xanh, không có cảnh báo nào. | Gọi `reconcile` mỗi nhịp sensor. Bọc `drive_wave` bằng try/except rồi `finalize(FAILED)`. Thêm probe "đợt hoạt động quá tổng deadline". |
| C4 | Nặng | `wave_flow.py:165-168`, `wave_flow.py:362`, `commands.py:113-121,137-144` | `stop_fn` (AGY_STOP, `/cancel`) và deadline 10' áp cho cả `--finish`, nên `kill_tree` có thể chạy **giữa lúc nạp DB** (`l1_ingest`, `agent_ingest`). Plan §8.1 yêu cầu huỷ ở ranh giới bước kế tiếp. Sau khi bị kill, đợt thành FAILED và bị tính là hỏng, có thể kéo theo tự hạ mức. | Bước `finish` không nhận `stop_fn`. Quá deadline thì cảnh báo, không kill. Chứng minh nạp lại là idempotent. |
| C5 | Nặng | `sensor.py:96-100,160`, `daemon.py:264-291` | **Vòng lặp bài độc.** Bài không bao giờ đạt `dod_pass` vẫn "pending". T2 đo tuổi theo `fetched_at` cũ, nên kích hoạt ngay sau mỗi đợt, tạo chuỗi đợt nhỏ vô hạn trên cùng một nhóm bài. Không có trần số lần thử theo bài. | Thêm bảng số lần thử theo bài trong `ops.db`. Bài đã thử ≥ N đợt thì loại khỏi T2 và báo người. Đây là trần số lần thử, không phải trần token. |
| C6 | Nặng | diff `openrouter_runner.py` (`"max_tokens": 24000`; `article_pack.py:66` = 900 token/bài) | Lô 50 bài cần khoảng 45K token đầu ra, nên trần 24K **chắc chắn cắt cụt**. Bộ salvage theo cặp ngoặc mới thêm làm lô thiếu bài một cách im lặng. Như vậy là trần token chia lô hộ, trái ADR 0010 và bất biến §6.B. Các điểm khác của diff: bỏ `response_format`; trạng thái mới `CACHED` không có trong `RUNNER_STATUS_MAP` (`breakers.py:199-202`) nên rơi về FATAL; cache nhận mọi đầu ra có ≥1 bản ghi, kể cả lô thiếu; `max_attempts` giảm 3→2; biến `in_block` không dùng; không có test. | Bỏ `max_tokens` hoặc đặt theo trần thật của model. Thêm `CACHED: OK` vào map. Thêm test `salvage_json_records` cho cả mảng bị cắt lẫn `{"r":[…` bị cắt. |
| C7 | Vừa | `breakers.py:185-196`, `wave_flow.py:24,306` | Regex chạy trên đuôi log toàn văn: `\b40[13]\b`, `\b429\b`, `quota`, `timeout` khớp cả số đếm ("429 bài") hay cờ `--print-timeout`. Một AUTH giả mở breaker vô hạn. `_BATCH_LINE` chỉ lấy dòng đầu của thông điệp lỗi nhiều dòng. `agy_runner` không bao giờ phát AUTH (`agy_runner.py:520-526` gom về FATAL). | Runner ghi lớp lỗi có cấu trúc (một dòng JSON mỗi lô). Chỉ chạy regex trên stderr của provider, không chạy trên log của bước. |
| C8 | Vừa | `ops.yaml:10`, `sensor.py:89`, `daemon.py:290`, `reports.py:56`, `article_tick.py:164-175`, `article_pack.py:456-458`, `wave_flow.py:250,509` | (a) Backlog ngoài 2 ngày không bao giờ được tự xử lý, trái plan §5.1. (b) T1 cộng bài của 2 ngày nhưng đợt chỉ lấy `target_date`, nên đợt có thể dưới 100 bài. (c) Ba định nghĩa pending lệch nhau: radar và sensor dùng `load_candidates` (có cả bài chỉ có `content_text`), còn `count_pending_articles` bắt buộc JOIN `work_items`. Cả hai đều loại code-first. (d) Đóng gói ra 0 bài (`return 2`, không có manifest) làm đợt FAILED và bị tính là hỏng, nên tự hạ mức có thể đến từ race chứ không từ lỗi. | Chốt một hàm pending duy nhất dùng chung cho cả ba. Đóng gói ra 0 bài thì `DONE`, không tính là hỏng. ADR quyết định phạm vi backlog. |
| C9 | Vừa | `wave_flow.py:514-522`, `breakers.py:335-336` | Không có canary: breaker HALF_OPEN cho chạy thẳng đợt 100 bài. Vòng repair không gọi lại `breakers.allow`, nên vẫn gọi provider khi breaker vừa OPEN vì TIMEOUT/EMPTY. | Kiểm `allow` trước mỗi vòng. Khi HALF_OPEN thì `--limit 5` một lô. |
| C10 | Vừa | `wave_flow.py:533`, `daemon.py:284-291` | L0 trong `drive_wave` được xử lý như L1, và `/run` ở L0 mở đợt L1 (tiêu token rồi chờ duyệt). Sensor chặn L0 đúng cách, nhưng đường thủ công vượt định nghĩa "L0 chỉ cảnh báo". | Ghi rõ trong ADR rằng `/run` tương đương một lần uỷ quyền L1. |
| C11 | Vừa | `scripts/ops_daemon.py:169-175`, `daemon.py:464-466`, `commands.py:113-194` | `ops_daemon telegram` tự đưa **mọi** chat từng nhắn bot vào danh sách trắng. Danh sách trắng xét theo chat, không theo người gửi (`from.id`). Chỉ `/stop` có xác nhận hai bước, còn `/reject`, `/reset`, `/level L3`, `/provider` thì không. Token được truyền qua đối số dòng lệnh. Tệp bí mật `ops.env` là văn bản thô, trong khi plan nêu Credential Manager hoặc biến môi trường. | Bắt người vận hành xác nhận chat id. Kiểm `from.id`. Thêm xác nhận hai bước cho lệnh nâng quyền. Đọc token từ stdin. |
| C12 | Vừa | `daemon.py:215`, `probes.py:200`, `src/db/preflight.py:73` | `probe_write` (BEGIN IMMEDIATE, CREATE TABLE, rollback) chạy mỗi 60 s trên `monocle.db`, tranh khoá ghi với `--finish` và morninger. Khi chờ quá 5 s, probe phát cảnh báo **critical giả** ngay trong lúc nạp. | Bỏ qua probe khi đợt ở FINISHING, hoặc giãn chu kỳ ra 15'. |
| C13 | Vừa | `procrun.py:40-63`, `agy_runner.py:441-450` | `kill_tree` lấy cây tiến trình qua psutil theo PPID. Trên Windows, cháu mồ côi (cha đã chết) không còn được liệt kê. `subprocess.run(timeout)` của `agy_runner` chỉ giết agy, bỏ lại các tiến trình con. Plan yêu cầu Job Object. | Gắn mỗi bước vào một Job Object có `KILL_ON_JOB_CLOSE`. |
| C14 | Vừa | `project/tests/test1.py` | Không phải test: không có hàm `test_`. `compile` báo `future feature anotations is not defined` (dòng 1). Thiếu import `Literal`/`List`, method nằm lồng trong `__init__`, `(?R)` không được `re` hỗ trợ, có khoá `"0messages"`. Ở mức module, tệp đọc `openrouter/.env` và **gọi mạng thật** tới OpenRouter. Tên tệp không khớp `test_*.py` nên pytest không thu, và tệp không chạm `monocle.db`. | Xoá tệp. `openrouter/check_key.py` không hardcode key (đọc `.env`, đã được gitignore) và chỉ in JSON của `/auth/key`. Nên dời tệp này về `openrouter/` công cụ hoặc xoá. |
| C15 | Nhẹ | `breakers.py:356-391`, `store.py:346-359` | Đọc rồi ghi qua hai kết nối riêng: một lệnh `/reset` từ luồng Telegram có thể bị `record()` của luồng workflow ghi đè. `upsert_wave` chạy SELECT rồi mới INSERT mà không có `BEGIN IMMEDIATE`. Với WIP=1 thì rủi ro thấp. | Gộp vào một giao dịch `BEGIN IMMEDIATE`. |
| C16 | Nhẹ | `order.py:231,246,324`, `sensor.py:96` | Phần lõi dùng `VN_TZ` có múi giờ, và `parse_iso` gán +07 cho chuỗi không múi, khớp `now_vn_iso` (`models.py:82`). Riêng hạn của standing order dùng `date.today()` theo giờ máy. `MIN(fetched_at)` so sánh chuỗi, nên chỉ đúng khi định dạng đồng nhất. | Dùng `now_vn().date()` cho cả phần standing order. |
| C17 | Nhẹ | `dbos_flow.py:48-115`, `wave_flow.py:479-486,578-605` | Rule 06: các method công khai của `DirectOps`, `DbosOps` và `WaveOps` không có docstring. Docstring của step DBOS chỉ có một dòng, thiếu `Args/Returns`. Không có từ trong blacklist, không có TODO. Emoji chỉ xuất hiện trong chuỗi xuất ra (`notify.py:12`, `reports.py:12`), không trong docstring. | Bổ sung docstring kiểu Google. |
| C18 | Nhẹ | `supervisor.py:74` | Mỗi lần restart mở một handle log mới mà không đóng. | Giữ handle trên đối tượng và đóng khi tiến trình thoát. |

---

## 4. Kiểm định bất biến

| Bất biến | Kết quả |
|---|---|
| Token chỉ là số ghi nhận (ADR 0010) | `src/ops` **đạt**: không có trần hay ngưỡng token. QUOTA chỉ được xử lý theo phản ứng. Diff `openrouter_runner` **vi phạm** (C6). |
| Không script giả lập agent | Đạt. Sensor, breaker và report chỉ đếm và phân loại vận hành. Chẩn đoán ngữ nghĩa thuộc về `ops-sentinel` (agy). Đầu ra của sentinel bị ép về danh sách trắng (`sentinel.py:218-220,317-321`) và chỉ thi hành khi người bấm nút. |
| Code-first không tính là phân tích | Đạt qua `ANALYZED_L1` (`article_pack.py:181`). |
| Một đợt một chương trình, `--batch` là cách chia lô duy nhất | Đạt ở `src/ops` (`--limit 100 --batch 50`). Bị phá gián tiếp bởi `max_tokens` (C6). |
| Bí mật không hardcode | Đạt: không thấy giá trị bí mật nào trong mã. **Vi phạm khi ghi log** (C2). |
| Bot chỉ gửi siêu dữ liệu | Phần lớn đạt. Riêng lý do FAILED nhúng 300 ký tự đuôi log của `--finish` và stderr của agy (`wave_flow.py:297,547`) mà không lọc. Cần chặn mọi nội dung bài trước khi gửi. |

## 5. Diff `agy_runner.py`

Diff thêm các tham số keyword-only `agent_name`, `description`, `instruction_guard` có giá trị mặc định giữ nguyên hành vi cũ, nên tương thích ngược. Sentinel dùng các tham số này để dựng hồ sơ `ops-sentinel`. Diff không có test.

---

## 6. Kết luận

**Đóng băng chờ ADR 0012. Giữ mã làm ứng viên, không viết lại.**

- **Đáng giữ.** Phần lõi tất định có cấu trúc tốt, gần plan và kiểm thử được nhờ tiêm phụ thuộc (`executor`, `db_probe`, `spawn`, `clock`, `call`). Gồm: `store`, `sensor`, `breakers`, `order`, `procrun`, `notify`, `reports`, `probes`, `supervisor`, `commands`, `sentinel`.
- **Chưa được chạy.** Không được chạy `ops_daemon.py run` khi chưa đủ ba điều kiện:
  1. ADR 0012 được duyệt, trong đó chốt C8 (phạm vi backlog, định nghĩa pending), C10 và khung giờ T3.
  2. Sửa xong C2–C6.
  3. Có bộ test cho `src/ops` dùng `ops.db` tạm và fake executor, **không** chạm `monocle.db` thật.
- **Spike P0** phải chạy trên chính `dbos_flow.py` (kill giữa analyze rồi khôi phục) và chốt một nguồn trạng thái đợt duy nhất. Hiện tồn tại song song DBOS và `ops_waves`, kèm `reconcile` chỉ chạy lúc khởi động: đây là gốc của C3.
- **Tách riêng.** Diff `openrouter_runner.py` cần story riêng, không đi chung lô với `src/ops`. Xoá `project/tests/test1.py`.
