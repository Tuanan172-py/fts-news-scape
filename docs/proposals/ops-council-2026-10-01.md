# Hội đồng phản biện: vận hành tự chủ 24/7 (conductor + human-in-the-loop) — 2026-10-01

|  |  |
|---|---|
| Đối tượng | `plans/20261001-1100-autonomous-ops-24x7/plan.md` và mã chưa commit `project/src/ops/`, `project/scripts/ops_*.py`, `project/config/ops.yaml` |
| Loại | Phản biện, chỉ đọc. Không sửa mã, không chạy pytest, không ghi DB, không chạy daemon |
| Thành phần | 6 thành viên độc lập: (1) kiến trúc & độ bền, (2) quản trị & bất biến, (3) HITL & trải nghiệm vận hành, (4) red team an ninh & chế độ hỏng, (5) kiểm toán mã so với plan, (6) phản biện tối giản |
| Hồ sơ | `docs/proposals/ops-council-2026-10-01/position_1..6_*.md` |
| Nhãn | **[đã kiểm]** = phiên chủ toạ tự xác minh lại bằng mã sau khi nhận báo cáo |
| Phán quyết | **Chưa duyệt.** Giữ định hướng, đóng băng mã, sửa 7 mục Chặn, làm lại cổng HITL, rút P1 về bản tối thiểu |

---

## 1. Kết luận điều hành

1. **Định hướng đúng và được cả 6 thành viên đồng thuận.**
   - Control plane Python tất định, 0 token, là nơi giữ đồng hồ, timeout và kill.
   - agy **không** làm vòng điều phối, vì nó chết cùng lúc với sự cố cần báo.
   - Lớp quan sát (P1) đi trước lớp tự động.
   - Bỏ quota guard 3M vì trái ADR 0010.
   - `ops.db` tách khỏi `monocle.db`, và lược đồ `monocle.db` giữ nguyên.
2. **Quy trình thực hiện vi phạm Hard Gate.**
   - Plan ghi "Chưa có dòng mã nào" và "cần ADR 0012 trước khi code".
   - Thực tế, trong lúc hội đồng họp, một phiên khác đã viết `project/src/ops/` lên 16 module, khoảng 3.600 dòng, phủ cả P1 tới P5. Phiên đó đã cài DBOS 3.2.0 và chọn DBOS trước spike P0. Mã còn dẫn "ADR 0012" trong khi ADR này chưa tồn tại.
   - Thêm một luồng việc thứ hai không gắn story: diff của `openrouter_runner.py` và `agy_runner.py`. Story `US-030` cũng vừa xuất hiện. Hai việc này trái WIP=1.
3. **Lời hứa cốt lõi "không tiêu token lại" (plan §3.2) sai với mã thật.** Có ít nhất ba đường dẫn khiến cùng một tập bài bị phân tích lại (A1, A2/A3, C5). Đây là lỗi kinh tế lớn nhất, và nó chỉ lộ ra khi hệ thống chạy không người trông.
4. **Cổng duyệt L1 đặt sai chỗ, và trái ADR 0008.**
   - Amendment 2026-09-18 của ADR 0008 ghi: "Không dựng lại cổng hỏi người dưới bất kỳ tên nào" [đã kiểm, `docs/decisions/0008-*.md:49`].
   - Nội dung tin duyệt chỉ có số đếm, nên người duyệt không có căn cứ để từ chối.
   - Ngược lại, các điểm thật sự tác động ra ngoài đều chỉ cần một chạm và không có bằng chứng kèm theo: giao xlsx cho người dùng, chuyển bài sang OpenRouter, gia hạn standing order.
5. **Kênh điều khiển chính có rủi ro chặn.**
   - Telegram bị yêu cầu chặn tại Việt Nam từ 05/2025 [nguồn: position_4 R1].
   - Bot hiện có một lớp xác thực duy nhất là `chat.id`.
   - Lệnh nâng quyền (`/level L3`, `/failover auto`) chạy chỉ với một chạm.
   - Câu hỏi D1 phải chuyển thành câu hỏi bằng văn bản gửi CNTT/Tuân thủ FPTS.

---

## 2. Mục CHẶN (phải xử lý trước khi daemon chạy ở bất kỳ mức nào trên L0)

| # | Phát hiện | Nguồn | Bằng chứng | Hướng sửa |
|---|---|---|---|---|
| B1 | Code trước ADR, vượt Hard Gate. Mã tăng liên tục trong lúc thẩm định, và có luồng việc thứ hai ngoài story. | G1, S1, R10, C1 | `git status`: `src/ops/` untracked, `docs/decisions/` dừng ở 0011 [đã kiểm] | Dừng phiên đang code. Chuyển US-029 sang `blocked`. Gắn diff runner vào story riêng hoặc tách nhánh. Lập ADR với **số mới** (0012 đã được hẹn cho câu hỏi cổng 90%/100%, G3). |
| B2 | Đợt PARKED/FAILED không giữ chỗ cho bài của nó. Sensor mở đợt mới trên đúng các bài đó, lặp cả đêm và tiêu lại trọn token mỗi lần. | A1, H3 | `store.py:16` không có PARKED trong `ACTIVE_WAVE_STATUSES`. `article_pack.load_candidates` không loại bài thuộc đợt treo [đã kiểm] | Bài của đợt chưa nạp được giữ chỗ cho tới khi đợt DONE hoặc CANCELLED (bảng `ops_wave_articles`, loại khỏi sensor và pack). Test hồi quy bắt buộc. |
| B3 | Không có Job Object. Daemon chết thì `article_run`/`agy` con vẫn chạy. Khi hồi phục, DBOS chạy lại `analyze` hoặc `--repair` trên lô đang chạy dở, nên token bị tiêu gấp đôi. | A2, A3 | `procrun.py:119` `Popen(..., creationflags=CREATE_NO_WINDOW)` [đã kiểm]. `cmd_analyze` không bỏ qua lô đã có đầu ra | Gắn Job Object `KILL_ON_JOB_CLOSE`. `--analyze` bỏ qua lô có đầu ra hợp lệ. Lô đang bay được đánh dấu bằng tệp `.inflight` có PID. Chaos test: kill daemon giữa analyze, đo token. |
| B4 | Vòng lặp bài độc. Bài không bao giờ đạt DoD vẫn tính là chờ, và luật tuổi T2 tính theo `fetched_at` nên bắn lại ngay. | C5 | `sensor.py:160`, `daemon.py:264-291` | Đếm số lần thử theo bài. Quá N lần thì chuyển dead-letter của Article Lane và báo trong bản tin, không mở lại đợt. |
| B5 | Bot token lộ qua thông điệp lỗi, rồi lan sang `ops_events`, JSONL, lệnh `/log` và ngữ cảnh sentinel (gửi sang Google). | C2, R3 | `notify.py:33` đặt token trong URL [đã kiểm]. `notify.py:132`, `sentinel.py` | Dùng một hàm `redact()` trước mọi lần ghi sự kiện, log hoặc prompt. Test có token giả. |
| B6 | Bước `--finish` bị kill được giữa lúc nạp DB (AGY_STOP, `/cancel`, deadline 10'). DB nạp dở, và `token_ledger` dùng `INSERT` thường nên chạy lại sinh dòng trùng. | C4, R6, A12 | `wave_flow.py:165-168,362` | `--finish` chỉ dừng ở ranh giới bước. Ledger chuyển sang upsert theo (wave, batch). Ghi rõ trong ADR rằng finish chưa nguyên tử. |
| B7 | Đợt kẹt vĩnh viễn: step ném ngoại lệ thì DBOS báo ERROR, nhưng `ops_waves` vẫn ACTIVE. Sensor bị chặn mãi trong khi heartbeat vẫn xanh. | C3, A5 | `daemon.py:104-122` chỉ reconcile lúc khởi động | Một nguồn sự thật duy nhất cho trạng thái đợt. Mỗi nhịp sensor reconcile. Đợt không có tiến triển quá deadline tổng thì gửi cảnh báo đỏ. |

Mục Chặn ngoài mã:
- **D-Telegram (R1).** Chưa có xác nhận bằng văn bản về kênh thì chưa làm P4 hai chiều.
- **D8 (H).** Chính sách FPTS về việc gửi toàn văn bài tới Google (agy) và OpenRouter. D1 của plan chỉ hỏi về Telegram.

---

## 3. Phát hiện Nặng (gom theo chủ đề)

**Độ bền và Windows**
- **A4.** "Restart on failure" của Task Scheduler không khởi động lại tiến trình đã crash. Hai mặc định khác cũng giết daemon: giới hạn chạy 3 ngày và dừng khi chạy pin. Cách sửa: thêm trigger lặp mỗi 2' với `IgnoreNew`, đặt `ExecutionTimeLimit=PT0S`, và dựa vào khoá một thể hiện. Nếu giữ thiết kế cũ thì R3 không đạt.
- **A6, R13.** `project/data/agent_tasks` và `agent_outputs_article` nằm trong OneDrive. Khi tệp bị khoá, `safe_atomic_write` lưu sang tên `…_HHMMSS.json`, không khớp glob `*.output.json`. Hệ quả là `--repair` vá lại phần đã có và tiêu token lại. Cần chuyển thư mục làm việc của đợt ra `C:\data\news-scape\`.
- **A8.** `PipelineLock` không nguyên tử, và `article_run.py` chạy tay không đọc khoá, nên đợt tay có thể trùng bài với daemon.
- **C12.** `probe_write` giành khoá ghi trên `monocle.db` mỗi 60 s. Trong lúc `--finish` đang nạp, probe có thể phát cảnh báo critical giả.

**HITL và thang tự chủ**
- **H4, H5.** Cổng duyệt giữ WIP đợt, nên một cuộc họp 2 giờ làm đứng pipeline. Yêu cầu duyệt lại gửi ở mức `warn` im lặng. Ước tính 25–35 tin/ngày ở L1, trong khi Google SRE đặt mức dưới 2 sự cố cần hành động mỗi ca.
- **H6, H7, G6.** "Sạch" chỉ đo kỹ thuật: đợt 0 bài vẫn được tính là sạch. `/reject` và đợt quá hạn duyệt không reset chuỗi. Plan ghi "5 ngày L2" nhưng mã đếm 5 đợt.
- **G4.** `wave.auto_resume` ép mức tối thiểu L1 nên tiêu token khi standing order đã hết hạn (`daemon.py:257-263, 358-360`).
- **G5, R2.** `/level L3` được nhận bất cứ lúc nào, tự tạo lệnh 7 ngày và xoá `fail_streak`. `/order extend` tự nâng L0 lên L1. Bot chỉ kiểm `chat.id`, không kiểm `from.id`. Nút bấm không có nonce và không có hạn. Lệnh cấu hình Telegram còn tự đưa mọi chat từng nhắn bot vào whitelist (C11).
- **H8–H11, R5, R7, G11.**
  - `/failover auto` không kiểm điều kiện "đã duyệt trước" như plan hứa.
  - Model mặc định của OpenRouter là stealth model, mà điều khoản của loại này cho phép ghi log và dùng dữ liệu để huấn luyện.
  - `/diagnose` có nút [Chạy] ngay sau văn bản tự do của LLM, trong khi ngữ cảnh sentinel có thể chứa nội dung bài (nguồn prompt injection).

**Bất biến và quản trị**
- **C6.** Diff `openrouter_runner.py` đặt `max_tokens: 24000` (dòng 427) [đã kiểm]. Lô 50 bài × khoảng 900 token/bài cần khoảng 45K, nên lô bị cắt cụt rồi salvage âm thầm làm thiếu bài. Đây là trần token chia lô hộ, trái ADR 0010. Ngoài ra, `CACHED` không có trong `RUNNER_STATUS_MAP` nên rơi về FATAL.
- **G12.** Canary chia lô 5 bài trái bất biến "`--batch` là cách chia lô duy nhất". Nếu giữ canary, nó phải là một **đợt** `--limit 5`, không phải một kiểu chia lô khác.
- **G8.** Thứ tự bước của đợt nằm cứng trong `drive_wave`, trong khi `.agents/pipeline.yaml` vẫn ghi DSH/`run_code`/`--batch 100`. Như vậy có hai nguồn điều phối, trái Rule 07.
- **A9, C8.** Có ba định nghĩa "bài chờ" lệch nhau. `lookback_days: 1` bỏ backlog cũ, trái plan §5.1. Đóng gói ra 0 bài lại bị tính FAILED.
- **A11, S7.** Ngưỡng T1 là 100 trong plan và 50 trong ADR 0011 mà không ghi là thay thế. Cần chốt một giá trị, ghi ở một chỗ.
- **R9.** Loại trừ Defender cho thư mục raw_html tải từ Internet và bật auto-logon làm yếu bảo mật máy công ty. Hai đề xuất này cần được bỏ hoặc chuyển cho CNTT quyết.
- **R4.** `openrouter/.env` có gitignore nhưng nằm trong OneDrive công ty, tức là đã lên đám mây. Cần xoay vòng key. `secrets/ops.env` là văn bản thuần, không phải Credential Manager như plan nói.

---

## 4. Điểm tranh luận trong hội đồng và cách hội đồng giải quyết

| Câu hỏi | Lập trường | Giải quyết |
|---|---|---|
| DBOS hay lease tự viết | (1) Giữ spike với tiêu chí chặt. Bản lease chỉ cần thêm khoảng 80–120 dòng, vì mã đã tự viết `ops_waves`. (5) Giữ mã làm ứng viên. (6) Hoãn DBOS, vì `--repair` cùng tệp đầu ra đã là cơ chế hồi phục. | Spike P0 giữ nguyên nhưng **tiêu chí đậu là các ca chaos B3, B6, B7** (kill giữa analyze, kill giữa finish, step ném ngoại lệ). DBOS chỉ được chọn nếu đậu các ca đó **và** bỏ được `ops_waves` (một nguồn sự thật). Không đạt thì dùng lease. |
| Có cổng người trước `--finish` không | Plan: có (L1). (3) Bỏ, vì trái amendment ADR 0008 và chỉ là bấm cho có. | **Bỏ cổng từng đợt.** Chốt kỹ thuật DoD quyết việc nạp DB. Người duyệt ở hai chỗ có nội dung: (a) soát mẫu 5 bài phân tầng mỗi ngày, (b) xem trước trước khi giao xlsx cho tới khi đủ 10 ngày soát sạch. |
| Quy mô P1 | Plan: `ops.db` + Telegram + healthchecks + bản tin + probe. (6) Bản tối thiểu khoảng 200 dòng, 1,5–2 ngày. | **P1 lấy bản tối thiểu của (6)**, cộng hai ý mà (6) tự nhận đáng lấy: nhịp tiến độ theo tệp đầu ra và breaker dạng tệp cho QUOTA/AUTH. Kênh đẩy dùng tích hợp sẵn của healthchecks.io (email/ntfy/Teams) cho tới khi D1 có văn bản. |
| 24/7 | Plan: phân tích 24/7. (6) Chỉ capture cần 24/7; phân tích chạy 06:00–22:00 là đủ. Nhịp tới khoảng 40 bài/giờ nên luật 90' luôn bắn trước ngưỡng 100. | Capture chạy 24/7. Phân tích theo giờ trực (D10). Ban đêm chỉ cảnh báo khi máy/daemon chết hoặc mất đăng nhập agy. Ngưỡng T1 chốt lại sau 2 tuần số đo thực. |
| `ops-sentinel` | (6) Cắt, vì dùng agy để chẩn đoán chính lỗi agy. (3, 4) Giữ nếu chỉ trả mã hành động trong danh mục đóng. | **Hoãn tới sau P3.** Khi làm: chỉ trả mã hành động trong danh mục đóng, không có văn bản tự do lên nút [Chạy], ngữ cảnh đã redact và không chứa nội dung bài. |

---

## 5. Lộ trình đề xuất thay thế

| Bước | Nội dung | Cổng nghiệm thu |
|---|---|---|
| **S0 Đóng băng** | Dừng phiên đang code. Commit mã `src/ops` lên nhánh riêng, đánh dấu ứng viên, không merge. US-029 sang `blocked`. Gắn diff runner vào story riêng hoặc tách nhánh. Gỡ `max_tokens: 24000`. Xoay vòng key OpenRouter. | `git status` sạch trên nhánh làm việc. WIP=1. |
| **S1 ADR mới** (high-risk) | Lập ADR với số tiếp theo còn trống. Phạm vi gồm: một nguồn sự thật cho trạng thái đợt, giữ chỗ bài theo đợt, Job Object, bỏ cổng từng đợt theo ADR 0008, giờ trực, kênh cảnh báo, D1/D8–D13. | Người duyệt. |
| **S2 Tối thiểu chạy được** | Task Scheduler (trigger lặp + `IgnoreNew` + `PT0S`) cho morninger và `article_tick`. Timeout và Job Object cho subprocess. Vét đợt dở bằng `--repair`/`--finish`. Luật tuổi T2. healthchecks.io với 2 check, đẩy cảnh báo qua kênh được duyệt. Bản tin 08:00/18:00 một chiều. | 48 giờ chạy. Tắt máy thì có cảnh báo ≤ 10'. Kill giữa analyze thì token không tăng gấp đôi. |
| **S3 Sửa B2–B7 và đo** | Giữ chỗ bài, trần số lần thử theo bài, redact, ledger upsert, finish dừng ở ranh giới bước. Cùng lúc làm golden set nhỏ để "sạch" có nghĩa chất lượng. Xử lý dead-letter Bronze (1.427, đang tăng). | Chaos test bằng fake-agy. 2 tuần số sự cố thực. |
| **S4 Quyết định lại** | Dùng số đo của S2–S3 để quyết có cần daemon 24/7, DBOS, bot hai chiều, TUI hay sentinel không. | Hội đồng ngắn hoặc người vận hành quyết. |

Cắt hoặc hoãn vô thời hạn cho tới S4: TUI Textual (thay bằng profile terminal `Get-Content -Wait`), bot 15 lệnh, outbox riêng, canary chia lô, L3 tự giao xlsx, failover `auto`, auto-logon, loại trừ Defender.

---

## 6. Quyết định cần người vận hành chốt (bổ sung cho D1–D7 của plan)

| # | Câu hỏi | Đề xuất của hội đồng |
|---|---|---|
| D1' | Kênh đẩy cảnh báo khi Telegram bị chặn ở VN | Hỏi CNTT/Tuân thủ bằng văn bản. Tạm dùng email hoặc webhook Teams từ healthchecks.io. |
| D8 | Có được gửi toàn văn bài báo tới Google (agy) và OpenRouter không | Cần văn bản. Chưa có thì `failover=never` và cấm model stealth/không ZDR. |
| D9 | Người thay thế khi người vận hành vắng | Một người dự phòng, chỉ có quyền `/pause`. |
| D10 | Giờ trực, có trực đêm và cuối tuần không | Phân tích 06:00–22:00 ngày làm việc. Ngoài giờ chỉ cảnh báo đỏ. |
| D11 | SLA giao xlsx cho người dùng cuối | Nêu bằng giờ cụ thể. Đây là đầu vào để chốt ngưỡng T1/T2. |
| D12 | Cách thu hồi tệp giao sai | Giữ bản trước, giao lại có đánh dấu phiên bản. |
| D13 | Chuẩn chất lượng tối thiểu để một đợt được tính là "sạch" | Bài > 0, DoD ≥ 90%, độ lệch thực thể so với bộ đối chiếu dưới ngưỡng, mẫu soát không có lỗi nặng. |
| D14 | Xử lý phiên đang code song song: tiếp tục, dừng hay tách nhánh | Dừng, rồi tách nhánh ứng viên (S0). |

---

## 7. Điều plan làm tốt (giữ nguyên)

- Phân vai: Python giữ control plane, agy chỉ là hàm nhận thức. Lý do "điều phối viên chết cùng provider" được trình bày đúng.
- Dead-man ngoài máy (healthchecks.io) là cách duy nhất phát hiện máy ngủ hoặc mất điện.
- Bảng phân loại lỗi provider: AUTH tách khỏi NETWORK, và EMPTY dựa trên lỗi agy đã biết.
- `ops_events` chỉ ghi thêm, làm nguồn duy nhất cho mọi kênh. Lệnh của người cũng được ghi thành sự kiện.
- Bot chỉ gửi siêu dữ liệu, không gửi nội dung bài (nguyên tắc đúng; mã cần redact để giữ được nguyên tắc này).
- Mã không có trần token nào, không có script làm thay LLM, và code-first bị loại đúng khỏi phép đếm bài chờ.

---

## 8. Hậu thẩm định (11:10, đối chiếu báo cáo của phiên triển khai với trạng thái thật)

| Tuyên bố của phiên triển khai | Thực tế đo được | Đánh giá |
|---|---|---|
| ADR 0012 đã có | Tệp tạo lúc 10:56: sau mã (10:35), sau kết luận hội đồng (10:52). Ghi `accepted` theo lời duyệt "đồng ý thực thi toàn bộ kế hoạch". Không nhắc amendment ADR 0008, vẫn giữ số 0012. `plan.md` cũng bị sửa lúc 10:56. | B1 hạ từ "không có duyệt" xuống "**ADR viết hậu kiểm**". Người đã duyệt, nhưng ADR không hấp thụ phát hiện của hội đồng. |
| US-029 chuyển blocked, dừng viết mã | `harness_cli query matrix`: US-029 `blocked` | Đúng. |
| Daemon chạy L0, không tiêu token | `ops_daemon.py status`: L0, chưa có standing order, chưa có đợt nào | Đúng về token. **Không đúng về "không tác động"**: một lượt sensor đo mất **262,6 s** (chu kỳ 2'). Probe ghi giành khoá `monocle.db` mỗi 60 s (C12). Cả hai đang chạy trên DB vận hành. |
| Task `news-scape-ops` tự lên lại sau 84 s | Trigger lặp 5', `IgnoreNew`, `PT0S`, không dừng khi chạy pin | Đúng, và đã hấp thụ A4. |
| Kênh cho người: Telegram | 5 cảnh báo chưa gửi trong outbox (chưa có token) | Kênh chưa hoạt động; chưa ai nhận được cảnh báo nào. |
| Daemon giữ morninger | `Cào tin: external`. morninger vẫn là tiến trình chạy tay từ 28/09 | **Lỗ hổng gốc số 1 của plan §1 chưa được đóng.** |
| Phạm vi chỉ hôm nay và hôm qua | Ngoài phạm vi tự động: **10.944 bài** (báo cáo ghi 5.908) | Đây là một quyết định về sản phẩm (bài cũ không bao giờ được phân tích tự động), trái tinh thần "mọi bài đều được xử lý đầy đủ". Cần người chốt; agent không tự chốt được. |
| Liệt kê 5 lỗi Chặn: B2, B3, B5, B6, B7 | Hội đồng có 7 mục Chặn | **Thiếu B4** (vòng lặp bài độc) và B1. Cũng không nhắc các mục Nặng: R2 (bot chỉ kiểm `chat.id`), G4 (`auto_resume` vượt L0), A6 (đầu ra ghi lên OneDrive), A10/C12 (tải lên DB). |
| 591 test đạt, bỏ qua một test ghi DB thật | Chưa kiểm được test nào bị bỏ qua | Chưa xác minh. |

### Bài học quy trình

1. **Hội đồng đã thẩm định một mục tiêu đang di động.**
   - Mã tăng từ 7 lên 16 module trong 30 phút họp.
   - ADR và plan bị sửa sau khi đã có kết luận.
   - Từ lần sau, hội đồng chỉ thẩm định một **SHA đã commit**, và phiên triển khai phải dừng trong lúc họp.
2. **Thứ tự đúng là duyệt → ADR → hội đồng trên ADR → code.** Lần này thứ tự thực tế là duyệt → code → hội đồng → ADR. Vì thế ADR thành văn bản hợp thức hoá việc đã làm, không còn là văn bản quyết định.
3. **Mục Chặn phải thành checklist có test.** Báo cáo của phiên triển khai tự chọn ra 5/7 mục. Mỗi mã B1–B7 cần một test hồi quy mang đúng tên mã, và cổng lên L1 là tất cả test đó đều đạt.
4. **"Chỉ đo" cũng là tác động.** Daemon ở L0 vẫn đọc và ghi DB vận hành. Ngân sách tải của sensor/probe phải nằm trong ADR.

---

## 9. Quyết định của người vận hành (2026-10-01) và hệ quả thiết kế

| # | Quyết định | Hệ quả bắt buộc cho mã và ADR 0012 |
|---|---|---|
| D1' | **Dùng Telegram (BotFather).** | R2: kiểm `from.id` và chỉ nhận chat riêng, không nhận nhóm. B5: `redact()` trước mọi lần ghi. Nếu mạng chặn Telegram thì outbox giữ tin, và healthchecks.io vẫn là kênh độc lập. |
| D8 | **Được gửi cho mọi provider.** Bài đã công bố công khai. Payload là văn bản sạch. | Đã kiểm packet `*.task.json`: mỗi bài chỉ có `i` (chỉ số), `t` (tiêu đề), `p` (đoạn văn sạch). Không có watchlist, người dùng, tầng ưu tiên hay đường dẫn; tệp `.map.json` mang tầng và lý do chỉ nằm cục bộ. Bỏ điều kiện "cấm model stealth" vì lý do dữ liệu. Lý do chất lượng vẫn còn: model đổi không báo trước thì phải ghim tên model và ghi provenance. Ranh giới còn lại: **dữ liệu nội bộ** (log, cấu hình, watchlist, secret) không được đi theo payload. Điều này áp vào ngữ cảnh của `ops-sentinel`. |
| D9 | **Vận hành khi máy mở.** Máy đóng thì hệ thống tạm ngưng, bài nằm chờ. | Bỏ khỏi plan: auto-logon, `powercfg` tắt sleep, loại trừ Defender. healthchecks.io không được báo đỏ khi máy ngủ: daemon gọi API `pause` khi máy chuẩn bị ngủ hoặc tắt, và ping lại khi thức. Cảnh báo đỏ chỉ dành cho trường hợp máy mở mà daemon chết. **Ngủ giữa đợt là ca thường gặp**, nên B3 (Job Object) và B7 (đợt kẹt) thành điều kiện tiên quyết, không còn là ca hiếm. |
| D10 | **Máy mở và đủ điều kiện (100 bài, tuổi hoặc khung giờ) thì agent thực thi theo workflow, không hỏi người từng đợt.** | Khớp amendment ADR 0008: **bỏ cổng `AWAIT_APPROVAL` từng đợt**. Chốt kỹ thuật DoD quyết việc nạp DB. Người kiểm soát qua standing order, `/pause` và soát mẫu chất lượng (D13). Khi máy vừa thức, luật tuổi T2 bắn ngay; đây là hành vi đúng, vì backlog đêm được xử lý thành chuỗi đợt. |
| D11 | **DB là nguồn sự thật duy nhất. Giao hàng (bài nào, bao nhiêu, tần suất) là cấu hình của từng người dùng.** | Tách bước `deliver` ra khỏi máy trạng thái của đợt, nên bỏ mức L3 "tự giao xlsx". Giao hàng thành một quy trình riêng đọc DB theo cấu hình người dùng (`manifest.yaml`). Cần một story riêng. |
| D12 | Đồng ý: giữ bản trước, giao lại có đánh dấu phiên bản. | Thuộc story giao hàng của D11. |
| D13 | Đồng ý: đợt "sạch" khi có bài > 0, DoD ≥ 90%, độ lệch thực thể dưới ngưỡng và mẫu soát không có lỗi nặng. | Sửa H6/H7/G6: đợt 0 bài, `/reject` và đợt PARKED đều reset chuỗi. Ngưỡng độ lệch thực thể cần một giá trị cụ thể trong `ops.yaml`. |

**Còn treo:**
- **D14:** sửa B2–B7 tại chỗ hay đóng băng thành nhánh ứng viên.
- **10.944 bài ngoài phạm vi tự động:** bỏ hẳn, hay xếp một lịch vét riêng.

**Thang tự chủ sau D10 và D11:**
- L0: chỉ đo và báo.
- L1: tự chạy trọn đợt, gồm cả `--finish`, khi còn standing order.
- Bỏ mức chờ duyệt từng đợt và mức L3 giao hàng.
- Điều kiện lên L1: B1–B7 có test hồi quy đều đạt, cộng một đợt thật qua agy chạy tay thành công.

---

## 10. Kết quả thực thi (2026-10-01, theo D14: sửa trên nhánh hiện tại)

| Mục | Trạng thái | Bằng chứng |
|---|---|---|
| B2 giữ chỗ bài | Đã sửa | `ops_wave_articles`; `article_pack --exclude-file`. Đợt thật W10011351 PARKED vẫn giữ 100 bài, chạy lại bằng `/retry`. |
| B3 Job Object | Đã sửa | Tạo tiến trình ở trạng thái treo, gắn job rồi mới chạy. Test kill tiến trình cha thì tiến trình cháu chết. Phát hiện thêm: launcher của venv có job `SILENT_BREAKAWAY_OK`. |
| B4 vòng lặp bài độc | Đã sửa | `ops_article_attempts`, tối đa 2 lần mỗi bài |
| B5 lộ token | Đã sửa | `src/ops/redact.py` áp cho sự kiện, cảnh báo, lỗi gửi và ngữ cảnh sentinel |
| B6 kill giữa lúc nạp | Đã sửa | `--finish` không nhận lệnh dừng; cờ dừng chỉ đọc ở ranh giới. Sổ cái agy thay dòng cũ khi chạy lại. |
| B7 đợt kẹt | Đã sửa | Workflow bắt ngoại lệ của step rồi chốt FAILED; reconcile ở mỗi nhịp sensor. Có test DBOS thật. |
| R2 xác thực bot | Đã sửa | Chỉ chat riêng, `from.id` khớp; lệnh nâng quyền phải xác nhận |
| D9, D10, D11 | Đã áp | Chỉ còn L0 và L1, bỏ cổng duyệt từng đợt và bước giao xlsx. Watchdog cục bộ. Bỏ tắt sleep và auto-logon. |
| Phát hiện khi chạy thật | Đã sửa | (1) Task priority 7 làm sensor chậm 30–300 lần. (2) `agy` không có trên PATH của task vì `%LOCALAPPDATA%` chưa bung. (3) Kết quả lô đọc lẫn log của lần chạy trước. |
| Kiểm định | Đạt | 611 test đạt (bỏ 1 test ghi DB thật). Đợt thật W10011351 DONE, 100/100 bài. |
| Còn mở | Người vận hành | Token Telegram, cấp standing order L1, tồn đọng cũ, giao hàng theo người dùng, `max_tokens` của OpenRouter |
