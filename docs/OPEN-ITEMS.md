# OPEN-ITEMS — việc tồn đọng của tuyến L1 → giao hàng người dùng

- **Cập nhật:** 2026-09-17 (bổ sung C5 manh mối Errno 22, C6 tối ưu cycle, C7 metric phát hiện)
- **Bối cảnh:** rà soát vì sao mapping từ L1 sang danh mục người dùng ghi nhận rất ít số liệu.
- **Số đo tham chiếu:** trên **bản sao** `project/data/monocle.db` (7.219 articles, chụp 2026-09-07).
  Chưa có thay đổi nào được áp lên DB vận hành.
- Đóng một mục: chuyển sang §D kèm **Kết quả đo thực tế**, đừng xoá.

---

## REPO-1. Mã lên kho tổ chức, dữ liệu lên SharePoint (ADR 0020, US-038) — việc còn lại, 2026-10-05

Kế hoạch và hướng dẫn từng bước: [`plans/20261005-1800-us038-repo-to-chuc-va-data-plane/plan.md`](../plans/20261005-1800-us038-repo-to-chuc-va-data-plane/plan.md).

| Mục | Ai | Việc | Trạng thái |
|---|---|---|---|
| N1 | Người | `git push fpa import/clean-20261005:refs/heads/main` | CHẶN mọi bước sau |
| N2 | Người | Chuyển `C:\data\news-scape\raw_html` cũ vào archive | Chờ |
| N3 | Người | Duyệt ADR 0020, kiểm quyền ghi `sites/FRA/Data`, tạo `news/` | CHẶN A4 |
| A1–A3 | Agent | Chuyển nhánh sang `fpa/main`, cách ly test, `core/paths.py` | Chờ N1 |
| N4 | Người + agent | Khung chuyển đổi: mã sang `C:\src\news-scraper`, dữ liệu sang `C:\data\news-scape` | Chờ A3 |
| A4, N5 | Agent, người | Publisher L1 và kiểm lần xuất bản đầu | Chờ N3, N4 |
| N6, N7 | Người | Ngừng đồng bộ thư mục mã cũ sau 14 ngày; xin ứng dụng Graph cho L2 | Sau |

---

## CON-1. Hợp đồng đầu ra thống nhất cho mọi provider (ADR 0017, US-034) — việc còn lại, 2026-10-05

Đã làm: schema `article-compact-v2` và module `article_contract.py` (nguồn chân lý), bộ kiểm dùng chung cho agy, openrouter, opencode và bộ bung, gỡ mặc định ngữ nghĩa ở expander, một khung đầu vào, tham số chuẩn, meta bắt buộc, lô chuẩn 50, `--analyze` từ chối runner lạ, `provider_conformance.py`, prefix và rule 11.

Người vận hành làm hoặc quyết định:

1. **[ĐÓNG 2026-10-06 — người vận hành] DSH không còn dùng.** Runner hiện hành là `agy` và opencode (Muse Spark 1.3). Không cần restart host DSH. Nếu sau này dùng lại DSH thì restart host trước (prefix `b7cd7e93820adc5e`, rule 09).
2. **[PENDING theo yêu cầu người vận hành 2026-10-06, chưa nghiệm thu] Gán nhãn bộ vàng 30 bài** (`sn`, `ts`, tập TIC) rồi chạy `provider_conformance.py baseline` với đầu ra của agy. Chưa có bộ vàng thì chưa chấm được provider khác. Ngưỡng tạm: mức agy trừ 5 điểm phần trăm.
3. **Sổ cái token chưa gắn nguồn theo meta.** `token_ledger.py --source` chỉ nhận `dsh` và `agy`, nên chi phí openrouter và opencode vẫn bị gán sai. Cần mở rộng `--source` và đọc `usage` từ meta.
4. **opencode chưa có `--runner`.** Adapter `opencode_native_run.py` đã dùng bộ kiểm chung, nhưng đợt vẫn do phiên OpenCode điều khiển bằng tay. Việc nâng thành runner chính thức cần quyết định riêng.
5. **Giảm tỷ lệ bị từ chối ở giai đoạn đầu.** Đo trước khi siết: agy 5,5% `c` ngắn và 1,8% `k` ngắn, openrouter 9,3% `k` dài. Đo lại bằng kịch bản audit sau vài đợt, và điều chỉnh prefix nếu một loại lỗi vượt vài phần trăm.
6. **Xung đột với ADR 0016 P3.** Trường `same_event_as` mà ADR 0016 dự kiến thêm sẽ bị schema đóng (`additionalProperties: false`) từ chối. Đổi hợp đồng phải sửa schema trước.
7. **Đợt DSH cũ** (W09241605, W09241723, W365, W1, W2) dùng lược đồ thực thể khác và không tái mở rộng được dưới resolver hiện tại.
8. **Hằng số v1 còn sót** ở `src/agent/packet.py`, `batch_handoff.py`, `dod.py`.
9. **Chưa có đợt chạy thật dưới cổng mới.** Phát lại đợt `W10051050` (sinh bằng prefix cũ) cho 38/100 bản ghi bị từ chối, 32 bài do `c` có 5 hoặc 6 chỉ số. Prefix mới đã nói rõ 2 đến 4, nhưng tỷ lệ từ chối mới chưa đo. Chạy một đợt agy 50 bài trước khi nâng daemon lên L1.
10. **Đường vá đã sửa** để dùng cùng bộ kiểm với bộ bung (`pending_batches`, `wave_received_ids`). Trước đó bản ghi sai vẫn được tính là đã nhận nên không bao giờ được vá. Đợt `W10051050` và `W10051042` đang `Lỗi` từ 04/10 (độ phủ dưới 90%, tỷ lệ hỏng vượt ngưỡng); chạy `--repair` thay vì `--finish`.
11. **`max_tokens` của OpenRouter** nâng từ 24000 lên 32000 để giảm cắt cụt. Cần đo xem lô 50 bài có còn bị `PARTIAL` do trần đầu ra không.
12. **[2026-10-05, Tier 3 — XONG] Packet cũ Silver và đợt W10051122 HOÀN TẤT.** Chẩn đoán "tin vắn" ban đầu sai: đo lại Silver cho thấy cả 500 bài đều đủ đoạn văn; packet đóng lúc Silver chưa có nên chỉ còn đoạn trích RSS ngắn (ADR 0018, Human duyệt hướng a). Đã sửa: lane đọc Silver trước (pack/runner/wp v1.1), `--repair` làm mới packet cũ, expand dồn hàng cũ, ingest bỏ qua tệp rỗng. W10051122 HOÀN TẤT 15:30: L1 500/500, nội dung 500/500, OpenRouter free $0. Chú ý: tồn tại ADR 0018 thứ hai chưa commit (`0018-loai-bai-mong...`, US-036, hướng loại bài mỏng) — hai hướng cần người gộp số hiệu và chốt phạm vi.

---

## CAP-1. Thu thập trọn vẹn, cụm hoá trùng lặp, tín hiệu insight (ADR 0013, 0016, US-033) — việc còn lại, 2026-10-02

Đã làm: sổ phát hiện URL, chuẩn hoá khoá bài theo 7 nguồn, gỡ lọc mờ ở tầng cào, phân trang theo watermark (baodautu, tnck), đối chiếu sitemap (baodautu, cafef, tnck, vneconomy), cào bù và phục hồi Bronze, cụm hoá, kế thừa kết quả cho bài chép, bảng tín hiệu và sheet Radar chú ý.

Số đo lúc bắt đầu (02/10, so với sitemap): cafef thiếu 64%, tnck 68%, baodautu 44%, vneconomy 9%. Radar có dòng "Độ phủ thu thập". Tác vụ nền xả tồn đọng chạy theo ngân sách; xem `python scripts/capture_reconcile.py status`.

Người vận hành làm hoặc quyết định:

1. **Bronze ghi sai gốc: đã gộp, còn chờ khởi động lại morninger (US-036, 2026-10-05; mã US-035 cũ đã đổi theo ADR-0021 G4).** 2.750 tệp ở `<gốc repo>/data/raw_html` đã chuyển vào `project/data/raw_html`. 1.607 tệp trùng tên khác nội dung nằm ở `C:\data
ews-scape
ecovered
oot_raw_html_conflicts_20261005`. `RawStore` nay neo vào `PROJECT_ROOT`, lần cào lỗi không ghi đè bản tốt, khoá `silver_failures` được chuẩn hoá. **Người vận hành:** khởi động lại `python -m src.morninger` (PID 42208, chạy từ 02/10) để nhận mã mới, rồi kiểm `pipeline_radar.py status`: dòng Bronze kẹt phải về 0. Phần còn lại của `<gốc repo>/data` đã dọn theo phương án E: `silver`, `work_packages`, `agent_tasks`, `agent_outputs*` (259 tệp) sang `C:\data\news-scape\recovered\root_data_20261005`; 4 CSV `exports` chưa có ở project đã gộp vào `project/data/exports`, 1 CSV trùng tên giữ ở `recovered`. Các điểm ghi `exports`, `notifications`, `staging`, `work_packages` đã neo vào `PROJECT_ROOT`. Còn dùng đường dẫn tương đối nhưng thuộc lane L1/Gold đã ngừng: `batch_handoff.py`, `l1_router.py`, `packet.py`, `runner.py`, `l1_runner.py`.
2. **Ba nguồn chưa có kênh đối chiếu độc lập:** vietstock, vietnambiz, thoibaotaichinhvietnam. Sitemap của chúng cũ hoặc không có. Độ phủ của ba nguồn này chưa đo được.
3. **fireant là API, không cào bù được theo URL.** Bài fireant ở trạng thái `discovered` được lấy lại khi chúng xuất hiện lại trong danh sách API; nếu không, chúng sang `dead_letter` sau 5 lần thử.
4. **Tải xử lý tăng.** Cào bù thêm vài trăm bài mỗi ngày cho ngày hôm nay và hôm qua. Daemon ở L1 sẽ tự đưa chúng vào đợt, nên token tăng tương ứng. Token là số ghi nhận, không phải cổng (ADR 0010).
5. **P3 chế độ chênh** (ADR 0016 §2.8): cần quyết định đổi hợp đồng `agent-output-v2-lean` và một đợt thử có người duyệt mẫu `same_event_as`. Hiện bài `candidate` vẫn được phân tích đầy đủ, nên chưa tiết kiệm được phần này.
6. **I3 đối chiếu với giá:** cần nguồn OHLCV và xác minh điều khoản sử dụng. Cho tới khi có, các chỉ số trong `signal_daily` chỉ được gọi là mức độ chú ý và giọng điệu báo chí, không phải tín hiệu giao dịch.
7. **Diễn giải `ama_z`:** nền thưa kết hợp sàn độ lệch chuẩn 0,5 làm z phình lớn với mã ít được nhắc (đo được z từ 17 đến 27). Radar chỉ hiện mã có ít nhất 3 bài và 2 nguồn. Độ phủ phân tích mới khoảng 21 đến 34%, nên cần đọc kèm `coverage_pct`.
8. **Giao hàng chưa gộp dòng theo cụm.** Bài chép vẫn xuất thành dòng riêng với kết quả kế thừa. Gộp dòng đổi cấu trúc tệp giao hàng nên cần quyết định riêng.
9. **`test_cli_entrypoints.py` vẫn ghi DDL vào DB vận hành** (tồn đọng từ 24/09). Bộ test được chạy với `--ignore` cho tệp này.

---

## OPS-1. Vận hành tự chủ khi máy mở (ADR 0012 + sửa đổi 01/10, US-029) — việc còn lại, 2026-10-01

Trạng thái:
- Daemon `news-scape-ops` và watchdog `news-scape-ops-watchdog` đã cài, priority 4. Daemon đang ở **L0**: chỉ đo và báo, không tự tiêu token.
- B2–B7 của hội đồng đã sửa, mỗi mục có test (`tests/test_ops_council_fixes.py`).
- Đợt thật đầu tiên qua daemon (W10011351) DONE: 100/100 bài, nạp DB qua cổng `--finish`.

Người vận hành làm, theo thứ tự (runbook `project/docs/operations/ops-daemon.md` §1):

1. **[ĐÓNG 2026-10-05] Telegram:** token đã thay (BotFather `/revoke`, 15:07). Daemon gửi được tin lúc 15:09. Token mới đã xuất hiện trong một phiên chat agent; muốn sạch hẳn thì `/revoke` lần nữa và tự chạy `ops_daemon.py telegram --token` ở terminal của mình.
2. **Cấp quyền tự chủ (người vận hành tự cấp):** `/level L1` trên Telegram. Lần cấp 05/10 10:40 tự hạ về L0 sau 2 đợt hỏng (W10051042, W10051050, do packet cũ của ADR 0018, nay đã nhả).
3. (Tuỳ chọn) healthchecks.io, period 1 ngày, nếu muốn biết khi máy tắt lâu.
4. **Ngoài phạm vi (task riêng của người vận hành):** khoảng 10,9 nghìn bài tồn đọng ngoài `lookback_days`. Giao hàng xlsx cấu hình theo người dùng (D11) cũng là story riêng.
5. **ops-sentinel:** draft. Chấm 10 lần chẩn đoán thật để chuyển active (rule 07).
6. **`max_tokens` của OpenRouter:** đã nâng 24000 → 32000 (CON-1 mục 11), vẫn là một trần; cần đo `PARTIAL`.
7. **[ĐÓNG 2026-10-06] Khởi động lại daemon thoát oan:** sau `schtasks /End` + `/Run`, tiến trình con cũ còn giữ `ops_daemon.lock` vài giây nên bản mới thoát mã 3. Sửa: `acquire_single_instance` chờ ân hạn `daemon.lock_grace_seconds` (45 s). Test `tests/test_ops_restart_lock.py`, kiểm thật trên task.

---

## OPS-2. Giám sát multi-agent (ADR 0014, US-031) — việc còn lại, 2026-10-01

Đã xong: vết `ops_spans`, Phòng điều khiển (`python scripts/ops_daemon.py open`, http://127.0.0.1:8787), bản tin giám sát, lệnh `/map /trace /agent /mandate /improve`, mandate 30 ngày tự gia hạn có điều kiện, hộp thư cải tiến.

Người vận hành làm:

1. **Thu hồi token bot Telegram.** Token đã nằm trong cuộc trò chuyện tạo bot. Vào @BotFather, `/revoke`, rồi `python scripts/ops_daemon.py telegram --token <TOKEN_MỚI>` và khởi động lại daemon.
2. **Cấp mandate:** gõ `/level L1` trên Telegram rồi bấm **Xác nhận**. Từ lúc đó hệ thống tự chạy và tự gia hạn khi khoẻ. Lưu ý: ở L1, daemon sẽ tự xử lý bài ngày hôm nay và hôm qua; phiên OpenCode ghi 382 bài ngày 01/10 là việc người dùng tự xử lý, nên cân nhắc trước khi cấp.
3. **Xem hộp thư cải tiến** (màn Cải tiến hoặc `/improve`). Đang có 1 đề xuất tự sinh từ dữ liệu thật: Bronze dead-letter tăng quá ngưỡng trong ngày.

Việc kỹ thuật còn treo (chưa làm trong US-031):

| Việc | Ghi chú |
|---|---|
| Nghiệm thu P0 bằng đợt thật qua daemon | Chưa có đợt nào chạy sau khi bật vết. Đợt đầu tiên ở L1 hoặc `/run` sẽ cho cây vết đầy đủ; các đợt cũ hiện hiển thị "chưa có span" |
| Span cho runner OpenRouter và adapter `opencode_native_run.py` | Chỉ `AgyRunner` được đo. Đợt chạy bằng runner khác không có cây vết cấp lô |
| `harness-auditor` lên active | Cần 10 lần chẩn đoán đúng theo rule 07. Hiện đề xuất do operator tất định `improvement-proposer` sinh |
| Truy cập Phòng điều khiển từ xa (D-B) | Cần CNTT cho đường hầm có xác thực; Telegram `/map`, `/trace` thay tạm |
| Thử Arize Phoenix qua OpenTelemetry (D-C) | Span đã giữ trường tương thích; cần một spike nhỏ |
| Golden set chất lượng phân tích | Phòng điều khiển hiện chỉ đo độ phủ, độ trễ, token; không đo đúng sai |

---

## OPS-3. Ổn định pipeline tự chạy (audit 05/10, US-037) — việc còn lại, 2026-10-05

1. **Nối vào phiên US-036 (thu thập):** cào bù đang xả chậm vì `gap_backfill_limit` mặc định 40 và `gap_budget_seconds` 120 chưa có trong `config/settings.yaml`; chu kỳ 10 phút với 700 URL cafef chờ. Radar vẫn khuyên `recapture` cho `raw_missing`, trái với CAP-1 mục 1 (gộp `data/raw_html` rồi derive lại). Người vận hành đã đồng ý sao chép, không cào lại web.
2. **Nhả đợt hỏng** (cần xác nhận): W10021650, W10051042, W10051050. Chạy `--repair` (không `--finish`) nếu muốn giữ bài, hoặc `/cancel <đợt>` để nhả.
3. **Chạy lô agy 50 bài một lần có tệp phản hồi thô** để biết nguyên nhân lô trả 0 bài; kết quả quyết định có hạ lô xuống 25 hay không (CON-1 mục 9 và 11).
4. **`--runner opencode` chính thức** (CON-1 mục 4): chạy tay bằng OpenCode hiện đăng ký provider `dsh` mặc định; cần nhãn đúng khi có runner mới.
5. **Cấp lại L1** khi đủ điều kiện ổn định (kế hoạch mục 5): ba đợt liền DONE, độ phủ thu thập thiếu dưới 2%, không đợt tay vô hình.

## A0. RÀ SOÁT END-TO-END 2026-09-17 — mất dữ liệu âm thầm & ngõ cụt trạng thái

Rà soát toàn tuyến Bronze → Silver → L1 → Gold → giao hàng. Con số nền: **7.203 bài đã cào,
424 bài qua cổng giao hàng**; `work_items`: `pending=3585, claimed=304, done=135, held=2`.
Khoảng cách đó không phải do quota Gold — dưới đây là các cơ chế làm rơi bài.

### A0-1. [P0 · ĐÃ KIỂM CHỨNG] Watermark Silver nhảy cóc ⇒ mất bài VĨNH VIỄN

`project/src/pipeline/derive.py:130` — `watermark_new = max(ok_ts)` chỉ lấy max của bài **thành
công**; `_should_process` (dòng 51-57) trả `fetch_ts > watermark`. Một file Bronze lỗi có
`fetch_ts` cũ hơn một bài thành công sẽ **vĩnh viễn không bao giờ thoả điều kiện** nữa.

Không cảnh báo, không retry counter, không dead-letter — chỉ một dòng log rồi `continue`
(dòng 115-117). Bronze bắt trọn 100% bài vẫn vô nghĩa nếu Silver lặng lẽ đánh rơi.
**Sửa đúng:** watermark phải là `min(fetch_ts của phần CHƯA xong)`, không phải `max` của phần đã xong.

### A0-2. [P0 · ĐÃ KIỂM CHỨNG] `run_daily.ps1 -Mode full` là vòng lặp tự huỷ

`param` khai `[ValidateSet('api')] $Agent` (dòng 19) nên nhánh `'hierarchy'` (dòng 108-110)
**không bao giờ chạy được**; nhánh `default` chỉ in hướng dẫn. Sau đó `CleanPackets` (dòng 138)
`Get-ChildItem 'data/agent_tasks' -Filter '*.task.json' -Recurse` xoá **mọi** packet kể cả trong
`l1/`. Chuỗi `full` = xuất packet → in chữ → ingest khi chưa có output → **xoá sạch packet vừa xuất**.

**Cảnh báo vận hành:** chạy `-Mode ingest` hoặc `-Mode full` lúc này sẽ xoá trắng **155 packet L1**
đang chờ. Dùng `-KeepPackets` cho tới khi sửa xong.

### A0-3. [P0 · ĐÃ KIỂM CHỨNG] AutoPilot va chạm tên batch ⇒ ingest lại dữ liệu cũ

`auto_pilot.py:66-72` bỏ qua batch nếu `<batch>.output.json` đã tồn tại, nhưng
`split_tasks_into_batches` đánh số lại từ `batch_01` **mỗi lần chạy**. Hiện `data/agent_outputs/`
có `batch_01`–`batch_02` (17/09) lẫn `batch_03`–`batch_11` (**14/09**). Lần chạy tới: skip toàn bộ
batch mới, ingest lại dữ liệu 3 ngày trước, rồi in "hoàn tất 100%". AutoPilot không bao giờ dọn
thư mục output.

Kèm theo: `run_cmd` (dòng 29-31) chỉ *in* lỗi không raise; `except Exception` (dòng 89) nuốt cả
`FileNotFoundError` khi thiếu `agy`; không timeout, không kiểm output đã sinh, không retry.

### A0-4. [P1] Bốn ngõ cụt trạng thái — bài kẹt vĩnh viễn, không có đường quay lại

| Trạng thái | Sinh ra khi | Vì sao kẹt |
|---|---|---|
| `work_items='failed'` | Trượt DoD Gold (`runner.py:276` → `catalog.mark_failed`) | `reclaim_stale` chỉ thu `claimed`; `claim()` chỉ chọn `pending`. Không script nào requeue |
| `l1_tasks='failed'` | Trượt DoD L1 (`l1_runner.py:140, 231`) | `upsert_l1_task` cố ý giữ status (`store.py:477-480`); `drain_code_first` chỉ lấy `pending` |
| `work_items='held'` | `silver_ok` hoặc `pkg_ok` sai (`run.py:111`) | `Catalog.enqueue` dùng `INSERT OR IGNORE` ⇒ sửa nguyên nhân xong hàng cũ vẫn không về `pending` |
| `work_items='claimed'` | Worker nhận việc | `reclaim_stale` chỉ chạy **bên trong** `claim()`; không ai claim thì treo mãi (hiện 304 hàng) |

### A0-5. [P2] Các lỗi chức năng khác

- **`l1_ingest.py:83` dùng `json.loads` nhưng module KHÔNG `import json`** (đã kiểm chứng) →
  `NameError` bị nuốt bởi `except Exception: pass` (dòng 88-89) ⇒ khối dọn `l1_batch_*.task.json`
  **chưa từng chạy một lần nào**.
- **`news_cron` vừa thừa vừa va chạm**: chạy `run_once.py` 16:00 hằng ngày; nhánh `--once` của
  `orchestrator.main` (dòng 253-262) **không chiếm scheduler lock** ⇒ cào song song với morninger
  (đang bận ~56% thời gian). morninger đã bao trọn capture + derive ⇒ nên tắt task này.
  - **2026-09-24 — mã đã sửa, còn bước vận hành (H):** khoá tệp `C:\data\news-scape\capture.lock`
    (`src/core/proclock.py` `SingleInstanceLock`, hệ điều hành tự nhả khi tiến trình chết) được
    morninger, `orchestrator` và `run_once.py` chiếm trước khoá DB; tiến trình thứ hai thoát mã 1.
    Khoá DB `pipeline_state` không đủ: hai morninger (khởi động 17/09 14:55 và 15:16) chạy song
    song đến nay, và `news_cron` 23/09 16:11 vẫn cào 24 phút đè lên morninger. Còn phải: tắt
    `news_cron`, dừng hai morninger cũ (còn chạy job `l1_route` đã ngừng), khởi động lại **một**
    morninger bằng mã mới. Chỉ khi morninger chạy mã mới thì khoá tệp mới có hiệu lực.
- **DoD L1 hai luồng không đồng nhất**: code-first truyền registry (`l1_runner.py:124`), luồng đọc
  output subagent **không truyền** (dòng 214) ⇒ `entity_id` lạ không bị chặn ở luồng agent.
- **Sản xuất packet không có consumer**: job `l1_route` (thêm 2026-09-17) chạy mỗi 15 phút sinh
  packet `needs_agent`, nhưng không job nào tiêu thụ ⇒ `data/agent_tasks/l1/` phình đều (155 file).

### A0-6. [P3] Hiệu năng, vệ sinh, tái lập

- `rederive_incremental` đọc/parse **mỗi `.meta.json` 3 lần** mỗi chu kỳ (`derive.py:95, 131, 132`)
  ≈ 22k lượt đọc/30 phút trên OneDrive.
- `checkpoint_reached` chỉ đạt khi `backlog == 0`; một file mới nhất luôn lỗi ⇒ `export_silver_manifest`
  **không bao giờ tự chạy**.
- `article_versions` thêm một hàng mỗi lần re-derive cùng bài khi meta thiếu `fetch_ts`
  (`derive.py:55-56` luôn process; `store.py:383` INSERT thuần, không UPSERT).
- Không có job retention: `data/work_packages` 7.289 file, `data/silver` 7.289 file,
  `agent_tasks/l1/archive` 2.461 file.
- `user_output.gated_rows` nạp toàn bộ bảng vào RAM rồi lọc ngày bằng Python (dòng 166-177).
- **Tái lập & bảo mật**: `auto_pilot.py:80-88` gọi CLI ngoài `agy` kèm cờ
  `--dangerously-skip-permissions`; binary nằm ở `C:\Users\anpt\AppData\Local\agy\bin\agy.exe`,
  **ngoài repo, không pin version, không có trong `requirements.txt`** ⇒ không tái lập được trên
  máy khác hay CI, và chạy tác nhân ngoài với kiểm tra quyền bị tắt.

---

## A. CHẶN — cần người duyệt trước khi chạm dữ liệu thật

### A1. [ĐÃ DUYỆT 2026-09-09] ADR 0003 chuyển sang `accepted`

`docs/decisions/0003-code-first-l1-delivery.md` — đã chuyển trạng thái sang `accepted`. Cơ chế
vật chất hoá kết quả tra danh mục tất định (`code_first`) vào `l1_outputs` đã được phê duyệt.

### A2. [ĐÃ DUYỆT & THỰC THI 2026-09-09] ADR 0004 phần D (Phương án D1)

`docs/decisions/0004-gold-value-gate-va-du-lieu-gia-lap.md`.
Đã phê duyệt Phương án D1 và thực thi `scripts/verify_gold_quality.py --apply` trên database:
toàn bộ 1.274 bản ghi Gold giả lập/template đã được hạ `dod_pass=0` (giữ nguyên `output_json`),
rút hoàn toàn khỏi deliverable người dùng và quay về hàng đợi Gold. Xem D14.

> **Đối chiếu 2026-10-06 (chỉ đọc):** A2 đúng. `--apply` đã chạy ngày 09/09 trên máy vận hành, sau
> bản sao lưu `monocle_backup_260909_pre_a2.db`. DB vận hành hiện tại `C:\data\news-scape\monocle.db`
> còn 1.092/1.274 id gốc, tất cả `dod_pass=0`, `output_json` giữ nguyên; 182 id còn lại bị ghi đè
> ngày 10/09 bởi lượt chạy lại Gold. Xem `FACT-adr-0004-d4-applied-to-operational-db`.

### A3. Chưa có gì chạy trên DB vận hành

Toàn bộ số liệu trong tài liệu này đo trên bản sao. Máy vận hành phải `git pull` rồi chạy §B.
**Bước sao lưu là bắt buộc** — quy trình có `ALTER TABLE l1_outputs ADD COLUMN l1_source`.

> **Đối chiếu 2026-10-06 (chỉ đọc):** A3 đã lỗi thời ngay ở commit 3b6003b. Mục này viết trên máy dev
> (commit 31d539d) về bản sao. Trên DB vận hành, cả A2 lẫn cột `l1_outputs.l1_source` đều đã có
> trước 17/09 (đối chiếu `monocle_backup_pre_adr0007_260917.db`).

---

## B. Các bước triển khai bắt buộc

### B1. Phải re-derive Silver, nếu không bản sửa tiêu đề vô tác dụng với backlog

3.910 work-package hiện có **không mang trường `title`**; bản sửa (commit `7cb0f44`) chỉ áp cho
gói sinh mới. Chạy trước §B2:

```powershell
cd project
.venv\Scripts\python scripts\rederive_from_bronze.py
```

`rederive_from_bronze.py` duyệt lại TOÀN BỘ Bronze, không dùng watermark.

### B2. Chuỗi chạy lần đầu

```powershell
cd project

# BẮT BUỘC — bước sau đổi schema
Copy-Item data\monocle.db data\monocle_backup_260909.db

.venv\Scripts\python scripts\maintenance\refresh_aliases.py --dry-run
.venv\Scripts\python scripts\maintenance\refresh_aliases.py

.venv\Scripts\python scripts\l1_ingest.py --code-first --dry-run
.venv\Scripts\python scripts\l1_ingest.py --code-first

.venv\Scripts\python scripts\maintenance\heal_orphans.py --dry-run
.venv\Scripts\python scripts\maintenance\heal_orphans.py

.venv\Scripts\python scripts\maintenance\relativize_paths.py
.venv\Scripts\python -c "from src.db.store import ArticleStore; from src.handoff.catalog import Catalog; print(Catalog(ArticleStore()).reclaim_stale())"

.venv\Scripts\python scripts\run_user_workflow.py --date all
```

Kỳ vọng: ~2.200–2.400 dòng cho 4 user. Lệch nhiều thì dừng, đối chiếu
`.venv\Scripts\python scripts\l1_backlog.py`.

### B3. Rút phần cần Agent (~282 bài `needs_agent`)

```powershell
.venv\Scripts\python scripts\l1_route.py --review missed --all --mini-batch 25
```

Với mỗi `data\agent_tasks\l1\l1_batch_XX.task.json`: gọi Subagent theo
`.agents/skills/l1-entity-matcher/SKILL.md`, ghi **một mảng JSON** vào
`data\agent_outputs_l1\l1_batch_XX.output.json`. Rồi:

```powershell
.venv\Scripts\python scripts\l1_ingest.py data\agent_outputs_l1\
.venv\Scripts\python scripts\run_user_workflow.py --days 30
```

### B4. Kiểm chứng bản sửa tiêu đề trên dữ liệu thật

Chưa làm được trên máy dev: toàn bộ `data/raw_html` là placeholder OneDrive chưa tải (client
không chạy), nên 122/122 bài lệch đều không đọc được Bronze. Sau §B1, đối chiếu:

```sql
SELECT COUNT(*) FROM l1_tasks t JOIN articles a ON a.url_title_hash = t.article_id
WHERE TRIM(t.title) <> TRIM(a.title);     -- kỳ vọng: 0 (trước đó: 122/1.320)
```

### B5. [ĐÃ THỰC THI 2026-09-09] Sinh lại `entities.csv` / `entities.xlsx`

Đã sửa lỗi thiếu đường dẫn `sys.path` trong `scripts/build_entities.py` và chạy thành công:
nạp từ `FRA - Data`, đồng bộ toàn bộ alias chuyên gia từ `config/`, sinh mới 2.072 thực thể cho cả
`entities.json`, `entities.csv`, `entities.xlsx`, `taxonomy.json` và `stats.json`. Xem D15.

---

## C. Quyết định còn treo

### C1. 685 dòng `l1_outputs` nguồn `agent` (lô 25/08) mang nhiễu cũ

22 nhãn `IND_GICS*:QUY` mà matcher hiện tại phản đối. ADR 0003 quy định bản `agent` được ưu tiên
hơn `code_first` nên chưa đụng. Ba lựa chọn:

1. chạy lại Subagent L1 cho nhóm đó;
2. cho `code_first` ghi đè các dòng `agent` cũ hơn một mốc thời gian — **lật một điều khoản của
   ADR 0003**, phải sửa ADR;
3. để nguyên.

Đối chiếu: **0/28** nhãn từ `code_first` bị matcher hiện tại phản đối.

### C2. Không có runner LLM — hàng đợi chỉ dài thêm

Không module nào trong repo gọi API LLM (`requirements.txt` không có SDK nào); `run_daily.ps1`
gọi `scripts/agent_stub.py` — **file không tồn tại**. Hiện tồn: ~282 bài `needs_agent`,
3.781 `work_items` chờ Gold.

Chọn: chạy tay theo §B3, hay dựng runner tự động (phải chốt provider trước).

### C3. `url_title_hash = sha256(url + title)` — khoá định danh chứa trường thay đổi được

Toà soạn sửa tít sau khi đăng là sinh hash mới: 12 bài cùng một URL nằm dưới nhiều hash,
`heal_orphans.py` phải bỏ qua chúng vì ràng buộc `UNIQUE(url)`. Sửa đúng là chuyển định danh
sang URL chuẩn hoá, giữ title làm thuộc tính — **mức ADR, cần rehash toàn bộ**. Chưa soạn.

### C4. Alias nhập nhằng nghĩa mà tầng tất định không giải được

Đã xử lý theo intent trong `config/entities/aliases/_context_guards.yaml` (`drop_bare` cho
`Nước`/`Điện`/`Giấy`/`Quỹ`, `block_in` cho `MACRO_GEO:MY`). Phần còn lại là suy luận ngữ cảnh —
thuộc Subagent. `BTC` cố ý trỏ **cả hai** `ASSET_CLASS:TIEN_MA_HOA` và
`INSTITUTION:BO_TAI_CHINH`: hai thực thể cùng mức quan trọng, giữ recall cho cả hai phía.

### C5. Silver mỏng ở 2 nguồn nhỏ

`fireant.vn` 8/33 và `tinnhanhchungkhoan.vn` 4/32 work-package có `cleaned_text` < 200 ký tự.

**Manh mối mới (2026-09-17)** — log vận hành cho thấy Bronze của fireant có file đọc KHÔNG được:

```
WARNING | _extract_from_bronze | read bronze failed
  data/raw_html\fireant.vn\20260907\e669e1e3…f99ade4f.html: [Errno 22] Invalid argument
```

Bronze không đọc được thì Silver rỗng — rất có thể đây chính là nguyên nhân gốc của C5 chứ không
phải lỗi bóc tách. Bước điều tra đầu tiên: kiểm tra file đó có tồn tại thật và đọc được bằng tay
không (`Errno 22` trên Windows thường là path/tên file không hợp lệ hoặc file bị OneDrive
dehydrate — xem rule 03 Bất biến 4 về Files On-Demand Pinning).

### C6. Tối ưu chi phí chu kỳ capture trước khi hạ interval dưới 10 phút

Đo 2026-09-17: cycle = **335s**, trong đó cafef 124s (fetch 900 item → 5 bài mới) và fireant 87s
(600 item → 0 bài mới) chiếm 63%. Đã chốt đặt `capture_interval_minutes: 10` để có ~40% biên dự
phòng. Muốn xuống 5 phút phải giảm chi phí cycle trước.

Hướng: **dừng phân trang sớm** khi gặp một trang mà toàn bộ item đã nằm trong `seen_articles`.
Rủi ro phải kiểm soát: phân trang nông quá là bỏ sót bài — đi ngược mục tiêu gốc của US-011.
Cần test trên dữ liệu thật trước khi bật.

### C7. Metric "bài bị nguồn xóa" chưa đếm theo thời điểm phát hiện

Radar hiện hiển thị "N bài đăng hôm nay / M tổng tích lũy". Con số theo ngày đăng luôn thấp hơn
thực tế vì bài bị gỡ thường được phát hiện muộn hơn ngày đăng. Dữ liệu để làm đúng đã có sẵn:
`metadata_json.capture_retry.last_at`. Chưa có truy vấn theo trường này.

---

## D. Đã đóng — đừng mở lại

| # | Vấn đề | Kết quả đo thực tế |
|---|--------|--------------------|
| D1 | Cổng export bỏ qua toàn bộ kết quả tất định; bài `route=resolved` nằm `pending` vĩnh viễn | Bài qua cổng **424 → 1.529**; khớp danh mục AnPT **146 → 791**; user có output **1 → 4** |
| D2 | `make_aliases()` bơm mọi chuỗi trong ngoặc thành alias → `"(Việt Nam)"` thành alias của `TICKER:IVS` | `TICKER:IVS` khớp sai **164 → 0** |
| D3 | `seen_articles` đánh dấu ngay lúc cào trong khi `articles` ghi bất đồng bộ | 429/429 bài mồ côi đều nằm trong `seen_articles`; nay ghi **cùng transaction**; `heal_orphans.py` thu hồi **437 bài** |
| D4 | `work_items` kẹt `claimed`, không có đường nhả | **304 → 0** (`Catalog.reclaim_stale()`) |
| D5 | `packet_path` lưu đường dẫn tuyệt đối của 2 máy | **1.787 dòng** chuyển sang tương đối theo `PROJECT_ROOT` |
| D6 | `l1_route` sắp nguồn theo chuỗi đường dẫn → 400 file đầu tiên 100% là `vneconomy.vn`, trần 50/lần chạy không bao giờ chạm 5 domain còn lại | Sắp theo thời gian |
| D7 | `VyPTT` có file đăng ký nhưng bị `default: false` tắt im lặng | Đã bật + cảnh báo log; xoá `A.yaml`/`B.yaml` (nhóm ví dụ viết tay) |
| D8 | `"TP.HCM"` khớp nhầm `TICKER:HCM`; `"quý 3"` khớp `IND_GICS*:QUY`; `"Xăng dầu Việt Nam"` (PLX) sinh `TICKER:OIL` | Guard ngữ cảnh trái, guard dấu cho alias 1 từ ngắn, khử chồng lấn tên chứng khoán |
| D9 | DoD L1 không kiểm `entity_id` có thật → `"INDUSTRY_GICS3:THEP"` sai dạng vẫn qua cổng rồi định tuyến cho 0 người | `check_l1_dod` kiểm registry |
| D10 | Silver lấy `h1` = header trang hồ sơ doanh nghiệp làm tiêu đề (122/1.320 bài), làm mất cả mã cổ phiếu | Giải tiêu đề bằng đối chiếu `sha256(url+title)` với `url_title_hash`; **chờ kiểm chứng §B4** |
| D11 | `process_l1_pipeline.py` là matcher thứ hai đang trôi khác, `build_l1_output` đóng dấu `agent_provider="gemini"` + timestamp cố định | Rút còn lớp vỏ uỷ quyền; provenance khai đúng `code_first`/`deterministic` |
| D12 | ~~2.677/7.219 bài `content_text` mỏng~~ — **xếp nhầm, không phải lỗi pipeline** | Mỏng là `articles.content_text` (đường RSS của scraper). `cleaned_text` của Silver — thứ L1/Gold thực sự đọc — thì lành: mẫu 400 gói có 374 bài ≥1.000 ký tự, cafef **0/137** mỏng |
| D13 | ADR 0003 còn ở `proposed` | Đã duyệt sang `accepted` ngày 2026-09-09; code-first sẵn sàng cho pipeline |
| D14 | 1.117/1.274 bản ghi Gold là sản phẩm của regex nhưng mang nhãn LLM (ADR 0004 D) | Đã duyệt Phương án D1; `verify_gold_quality.py --apply` đã hạ `dod_pass=1`: **1.274 → 0 (0.0%)**, deliverable sạch template |
| D15 | `build_entities.py` lỗi thiếu `sys.path` và thiếu `pyarrow`; `entities.csv/xlsx` cũ | Đã sửa `sys.path`, cài `pyarrow`; sinh mới 2.072 thực thể cho cả master json, csv, xlsx, taxonomy |
| D16 | Token burn Gold quá cao do payload 4.000 chars và export toàn bộ pending không ai đọc (ADR 0005) | **Subscriber-Gated Export**: claim 947/1.505 bài, bỏ 558 bài unmonitored (-37.1% token); **Semantic Pruner 2.200 chars** (-47% token/bài); tổng tiết kiệm ~66.7% |
| D17 | L1 false positives danh từ riêng tiếng Việt (*Mỹ Thuận, Á Mỹ, Mỹ Tho, Bà Kim Nga, Nga Rose*) | **Morphological & Compound Guard** (`_blocked_by_morphology`): FP `MY` **14 → 0**, FP `NGA` tên người **→ 0** |
| D18 | Sót tin CBTT VNDirect (bị stoplist nuốt), nhầm PGD ngân hàng với mã CP, sót tin công ty con (US-010, US-011) | **Positional Exemption** (`^VND:`): cứu **36/36 bài CBTT**; **Bank PGD Guard**: FP `PGD` **36 → 0**; **Ecosystem Aliasing**: nhận diện thêm VinFast, Bách Hóa Xanh, WinCommerce, FE Credit |
| D19 | Xử lý dứt điểm toàn bộ 258 bài L1 ngày 14/09; chống burn token do tool loop; đóng gói End-to-End Playbook | **258/258 bài PASS DoD 100%**; 0 task tồn đọng; nạp 4.921 L1 outputs; chuẩn hóa Rule 01 (Strict 2-I/O), ban hành `end-to-end-operations-playbook.md` |

**Kiểm tay sau khi sửa:** 25 dòng ngẫu nhiên của AnPT → **0/29 mã không có căn cứ trong tiêu đề**.
**pytest:** 413 passed (100% green, cập nhật 2026-09-17 — gồm 10 test CLI entry point chạy thật
qua subprocess, bổ sung sau sự cố 3 lỗi sản xuất vô hình với test import hàm).

---

## E. NEMOTRON 3 ULTRAFREE EVAL (US-NEMO01, 2026-10-01) — việc mới phát sinh

### E1. Repair duplicate batch bug (Cấp 2)

**Mô tả:** `cmd_repair` chạy lần 2 tạo cả `r02` (repair trực tiếp gốc) VÀ `r01_r01` (repair của repair lần 1), nhưng lô `r01` (repair lần 1) không được chạy tự động.

**Hệ quả:** 5 lô r01 (179 bài) phải chạy thủ công qua runner. Tổng repair batches: 20 thay vì 15.

**File:** `project/scripts/article_run.py` hàm `cmd_repair` (dòng 323-423)

**Sửa:** Logic tạo repair batch cần loại trừ các batch đã có repair pending (r01) thay vì tạo repair của repair.

### E2. Token ledger không ghi cho OpenRouterRunner (Cấp 2)

**Mô tả:** `token_ledger.py append --source openrouter --since <epoch>` không tìm thấy phiên DSH worker vì OpenRouterRunner không chạy trong DSH.

**Hệ quả:** Chi phí token free-tier vô hình, chỉ đoán qua context usage 88%.

**File:** `project/scripts/token_ledger.py`, `project/scripts/article_run.py` (hàm `cmd_finish` dòng 691-702)

**Sửa:** Ledger đọc `usage` từ `meta.json` của các batch thay vì query DSH sessions.

### E3. Model partial response rate cao (Cấp 3 - theo dõi)

**Mô tả:** Nemotron 3 UltraFree trả partial (~65 bài/100 lô đầu) vs Muse Spark (100/100). Cần 2 vòng repair để đạt 500 bài.

**Hệ quả:** Tăng thời gian 17%, token +48%, độ phức tạp vận hành.

**Theo dõi:** So sánh quality output (sentiment, key_points, citations) giữa 2 model trước khi quyết định chuẩn hóa.

### E4. Concurrency limit free tier (Cấp 2 - vận hành)

**Mô tả:** OpenRouter free tier ~20 req/phút → concurrency=2 tối đa. DSH concurrency=10.

**Hệ quả:** Thời gian wave ~56 phút vs 48 phút Muse Spark.

**Workaround:** Chạy sequential waves, hoặc dùng paid tier nếu cần throughput cao.

