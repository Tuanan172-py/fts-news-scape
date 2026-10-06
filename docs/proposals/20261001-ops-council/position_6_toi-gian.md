# Lập trường 6 — Phản biện tối giản (YAGNI) cho plan vận hành tự chủ 24/7

- **Ngày:** 2026-10-01
- **Vai:** devil's advocate, chỉ đọc. Nguồn: `plans/20261001-1100-autonomous-ops-24x7/plan.md`, `project/scripts/article_tick.py`, ADR 0011, `docs/proposals/20260923-agy-automation-council.md`, `docs/proposals/20260924-research-council.md`, `docs/OPEN-ITEMS.md`, `docs/SESSION-LATEST.md`, radar lúc 10:41.
- **Bối cảnh đội ngũ:** một người vận hành kiêm dev, một máy Windows, một lane.

---

## 1. Lập trường

Plan giải đúng bài toán gốc (không gì tự chạy, không gì tự báo), nhưng giải bằng một hệ điều phối cỡ đội SRE. Gốc vấn đề ở §1 của plan gồm ba thiếu sót: morninger chạy tay, `article_tick.py` chưa lên lịch, không cảnh báo khi chết. Cả ba đóng được bằng **Task Scheduler + healthchecks.io + một hàm gửi tin một chiều + timeout cho subprocess**, khoảng 150–250 dòng mã và 1–2 ngày công, dùng mã đã có và ADR 0011 đã duyệt. Phần còn lại của plan (DBOS, máy trạng thái 10 bước, breaker bền 7 lớp, outbox, bot 15 lệnh, TUI, ops-sentinel, canary, L3) nên hoãn cho tới khi có sự cố thật chứng minh nhu cầu, và xếp **sau** việc chặn mất dữ liệu Bronze và golden set.

Ý kiến: **duyệt P1 rút gọn, bác P2–P5 ở thời điểm này.**

---

## 2. Nhu cầu thật

| Đại lượng | Số đo / ước lượng | Nguồn |
|---|---|---|
| Bài đăng trong ngày tới 10:41 | 186 | radar 2026-10-01 |
| Một ngày đầy đủ gần nhất | 528 bài (đợt W0929_PROD) | radar, mục 2 |
| Nhịp tới trong giờ làm việc | khoảng 40 bài/giờ (186 bài từ khoảng 06:00 tới 10:41) | ước lượng, chưa đo theo giờ |
| Thời gian để đủ 100 bài | khoảng 2–2,5 giờ trong ngày; ban đêm và cuối tuần có thể không bao giờ đủ | suy từ dòng trên |
| Số đợt cần mỗi ngày | 4–6 đợt 100 bài | 400–530 bài / 100 |
| Lần mở đợt sensor kiểm mỗi ngày | 720 lần (mỗi 2 phút) cho 4–6 sự kiện | plan §5.1 |
| Độ tươi người dùng cuối cần | **không có tài liệu nào ghi SLO**. Giao xlsx (`write_user_output.py --date today`) đang chạy tay, theo ngày | plan §1, AGENTS.md §3 |

Hệ quả:

- **Ngưỡng 100 bài gần như không bao giờ là luật kích hoạt chính.** Với khoảng 40 bài/giờ, luật tuổi T2 (90 phút) luôn bắn trước T1. Thiết kế sensor 2 phút cho luật khối lượng là tối ưu cho một sự kiện hiếm khi xảy ra trước luật khác.
- **Độ trễ mở đợt ≤ 5 phút (R1) không mua được gì cho người dùng** khi đầu ra cuối là tệp xlsx theo ngày, giao tay. Chuỗi giá trị bị nghẽn ở khâu giao hàng, không ở khâu kích hoạt.
- **24/7 chỉ cần cho capture.** Cào tin rẻ, nguồn có thể gỡ bài, nên morninger nên sống 24/7. Phân tích thì "06:00–22:00 mỗi 30 phút + vét 07:15" phủ được tin đêm trước buổi sáng, trước giờ mở cửa 09:00.

---

## 3. Bảng phát hiện

| Mã | Mức | Phát hiện |
|---|---|---|
| S1 | Cao | **Mã đã được viết trước khi duyệt.** `project/src/ops/` có 12 tệp, 2.672 dòng (`wave_flow.py` 605, `store.py` 458, `dbos_flow.py` 152), tạo 10:35–10:41 hôm nay, chưa commit, cùng `project/config/ops.yaml`. Plan ghi "Chưa có dòng mã nào" và lane triển khai là high-risk, cần ADR 0012 + người duyệt. Đây là vi phạm Hard Gate của AGENTS.md §0, và tạo áp lực chi phí chìm lên quyết định của hội đồng. |
| S2 | Cao | **Mất dữ liệu đang tăng ngay trong phiên.** Dead-letter Bronze 1.408 (plan) thành 1.427 (radar 10:41), watermark bị chặn 228 thành 230. Radar xếp mục này HIGH và đứng trước 186 bài chờ. Plan chỉ đưa nó vào bản tin (§9, "không tự xử lý"). Tự động hoá khâu sau không cứu được bài không bao giờ tới Silver. |
| S3 | Cao | **Chất lượng phân tích chưa được đo.** Hội đồng 24/09: "đo đủ số lượng, không đo đúng"; không golden set; `agent_metrics` không có dòng nào cho `article-processor`; thứ tự đề xuất H6 đặt golden set trước A/B AGY. Plan đưa agy lên L2 (tự nạp DB) chỉ dựa trên "5 đợt sạch", tức sạch về kỹ thuật. Tự động hoá một pipeline chưa đo chất lượng là tăng tốc độ đưa sai số vào DB. |
| S4 | Trung bình | **Kích thước plan lệch tỉ lệ.** Ước lượng 4.000–5.000 dòng mã mới cho P0–P5 (đã 2.672 dòng ở bước đầu), gấp khoảng 5 lần `article_run.py` (932 dòng). Mỗi dòng là bề mặt bảo trì cho một người. Harness đã có 16 tài liệu, 9 rule, 18 skill cho một lane (hội đồng 24/09). |
| S5 | Trung bình | **DBOS giải bài toán hiếm.** Đợt kéo dài khoảng 15–45 phút, 4–6 đợt/ngày. Đầu ra lô đã nằm sẵn trên đĩa (`data/agent_outputs_article/`), `--repair` đã đóng gói lại đúng phần thiếu. Crash giữa đợt là sự kiện vài lần/tháng; hồi phục bằng tay một lệnh. Plan tự thừa nhận DBOS khuyến nghị Postgres cho production và cần spike. |
| S6 | Trung bình | **`article_tick.py` thiếu timeout thật.** `subprocess.run(prep_cmd, ...)` (dòng 348) và `subprocess.run(fin_cmd, ...)` (dòng 365) không có `timeout`. agy treo thì `.pipeline.lock` bị giữ vô hạn. Đây là lỗ hổng cần vá ngay, không cần daemon để vá. |
| S7 | Thấp | Ngưỡng lệch giữa các nguồn: ADR 0011 và `article_tick.py` dùng 50 bài, plan và `ops.yaml` dùng 100. Cần một giá trị, ghi một chỗ. |
| S8 | Thấp | Bot hai chiều điều khiển máy trong mạng công ty là bề mặt tấn công mới, và D1 (chính sách FPTS với Telegram) còn treo. Gửi một chiều không cần quyết định đó nặng bằng. |
| S9 | Thấp | `ops-sentinel` dùng agy để chẩn đoán sự cố mà loại phổ biến nhất chính là agy hỏng (AUTH, QUOTA, NETWORK). Plan §4.1 dùng đúng lý do này để không đặt agy làm điều phối viên, nhưng lại đặt nó làm người chẩn đoán. |

---

## 4. Phương án tối thiểu

### 4.1 Thành phần

| # | Thành phần | Nội dung | Mã mới | Công |
|---|---|---|---|---|
| M1 | Task Scheduler cho morninger | "At log on", chỉ khi người dùng đăng nhập (lý do Session 0 như plan §4.2), restart on failure mỗi 1 phút, tối đa 999 lần, tắt "stop if on battery" | `ops_install.ps1` khoảng 40 dòng | 0,25 ngày |
| M2 | Task Scheduler cho `article_tick.py` | Mỗi 30 phút, 06:00–22:00, mọi ngày; "Do not start a new instance" | chung tệp M1 | gộp M1 |
| M3 | Timeout + kill cây trong tick | `timeout=` cho hai `subprocess.run`, khi hết hạn gọi `taskkill /T /F /PID`; deadline 45 phút analyze, 10 phút finish | khoảng 25 dòng | 0,25 ngày |
| M4 | Vét đợt dở trước khi mở đợt mới | Đầu mỗi tick: đợt gần nhất có đầu ra mà chưa `--finish` thì chạy `--repair` rồi `--finish` (L2) hoặc báo (L1), thay vì đóng gói lại | khoảng 30 dòng | 0,5 ngày |
| M5 | Vòng xả backlog | Sau một đợt xong, nếu còn `pending ≥ ngưỡng` thì mở đợt tiếp trong cùng tick (trần 6 đợt/tick) | khoảng 10 dòng | gộp M4 |
| M6 | Luật tuổi | Thêm T2 "bài chờ lâu nhất > 90 phút" vào `evaluate_trigger` | khoảng 15 dòng | gộp M4 |
| M7 | healthchecks.io, hai check | `capture` ping trong job capture của morninger (chu kỳ 15', grace 15'); `tick` ping `/start`, `/0` hoặc `/fail` kèm 20 dòng log cuối (chu kỳ 30', grace 45', chỉ 06:00–22:00 bằng cron schedule của healthchecks) | khoảng 30 dòng | 0,25 ngày |
| M8 | Kênh cảnh báo | Dùng **tích hợp Telegram/ntfy/email có sẵn của healthchecks.io**. healthchecks chỉ báo khi đổi trạng thái up/down, tự khử trùng lặp. Không viết bot, không outbox. | 0 dòng | cấu hình 15 phút |
| M9 | Bản tin 08:00 và 18:00 | Task Scheduler chạy `ops_digest.py`: gọi radar, rút số bài, độ phủ đợt cuối, dead-letter, gửi một tin qua Bot API `sendMessage` (một chiều) hoặc ntfy | khoảng 60 dòng | 0,5 ngày |
| M10 | Nhật ký | stdout/stderr của tick ghi `C:\data\news-scape\ops_logs\tick_YYYY-MM-DD.log`; Windows Terminal profile quake chạy `Get-Content -Wait` trên tệp đó | 5 dòng + profile | 0,1 ngày |
| M11 | Dừng khẩn | Giữ `AGY_STOP` và standing order đã có | 0 | 0 |

Tổng: khoảng **175–220 dòng mã mới, 1,5–2 ngày công**, không phụ thuộc mới ngoài `requests`, không DB mới, không tiến trình thường trú mới. So với plan: khoảng 4.000–5.000 dòng, 3–5 tuần cho P0–P5, thêm `ops.db`, DBOS, python-telegram-bot, Textual.

### 4.2 Mức đáp ứng R1–R8

| Mã | Yêu cầu plan | Phương án tối thiểu | Ghi chú |
|---|---|---|---|
| R1 | Mở đợt ≤ 5' sau khi đạt ngưỡng | **Một phần**: ≤ 30' | Không có lợi ích người dùng nào đo được cho 5' khi giao xlsx theo ngày. Rút chu kỳ tick xuống 10' nếu cần, 0 dòng mã. |
| R2 | Tuổi bài chờ p95 ≤ 2 giờ | **Đạt** | T2 90' + tick 30' cho tuổi tối đa khoảng 2 giờ. |
| R3 | Tự hồi phục sau crash/reboot, chạy tiếp từ step cuối | **Phần lớn** | Restart do Task Scheduler. Đợt dở được M4 vét bằng `--repair`/`--finish`, không đóng gói lại phần đã có đầu ra. Không exactly-once ở mức step. |
| R4 | Phát hiện chết ≤ 10' | **Đạt** cho máy và capture (grace 15'); tick ≤ 45' | Rút grace nếu cần. |
| R5 | Timeout, báo mất kết nối | **Một phần** | Deadline cứng có (M3). Không breaker bền: quota hết thì các tick sau thất bại nhanh, healthchecks báo một lần khi chuyển down, báo lại khi up. Không phân lớp AUTH riêng trong cảnh báo; 20 dòng log cuối trong ping cho thấy nguyên nhân. |
| R6 | Mọi hành động thành sự kiện xem được ở mọi kênh | **Một phần** | Log theo ngày + lịch sử ping healthchecks + radar. Không có bảng sự kiện truy vấn được. |
| R7 | Can thiệp từ điện thoại | **Không** (trừ tạm dừng qua tắt check) | Xem tự phản biện §6. |
| R8 | Không phá bất biến | **Đạt** | Ít thành phần hơn, không đụng `--batch`, token, code-first. |

---

## 5. Danh sách cắt hoặc hoãn (xếp theo giá trị/chi phí thấp dần)

| Thành phần | Quyết định | Lý do | Điều kiện mở lại |
|---|---|---|---|
| `ops-sentinel` (LLM trực ban) | Cắt | Chẩn đoán lỗi provider bằng chính provider đó (S9). Tiêu chí nghiệm thu cần 10 sự cố ghi lại, mà phương án tối thiểu kỳ vọng vài sự cố/tháng. 20 dòng log trong cảnh báo đủ để một người đọc. | Hơn 5 sự cố/tuần mà người mất hơn 15 phút để chẩn đoán mỗi lần. |
| TUI Textual quake | Cắt | Trùng radar + tail log. Một profile Windows Terminal chạy `Get-Content -Wait` đáp ứng "bấm phím là thấy log" với 0 dòng mã. | Không có. |
| Bot hai chiều 15 lệnh | Hoãn vô thời hạn | Bề mặt điều khiển từ xa, D1 treo, mỗi lệnh cần test. Phần lớn lệnh (`/level`, `/provider`, `/failover`, `/order extend`) là thao tác vài lần/tháng, làm tại bàn được. | Người vận hành vắng máy thường xuyên trong giờ thị trường và có sự cố đòi can thiệp trong < 1 giờ. |
| DBOS + `ops.db` + máy trạng thái 10 trạng thái | Hoãn | S5. Đầu ra lô là tệp, `--repair` đã là cơ chế hồi phục. Thêm phụ thuộc, spike, lược đồ thứ hai. | Đo được hơn 2 lần/tháng mất tiến độ đợt mà M4 không vét được. |
| Canary | Hoãn | Chỉ có nghĩa khi có breaker HALF_OPEN. Lô đầu của đợt thật tự đóng vai canary. | Khi có breaker. |
| Breaker bền 7 lớp | Hoãn | healthchecks đã khử trùng lặp cảnh báo; tick 30' là backoff tự nhiên. Phân loại lỗi đã có trong runner. | Quota bị đốt lặp lại vì tick thử liên tục. Bản rẻ: tệp `C:\data\news-scape\BREAKER_UNTIL` do runner ghi khi gặp QUOTA/AUTH, tick đọc, khoảng 15 dòng. |
| Outbox cảnh báo | Cắt | healthchecks là outbox ngoài máy, có retry. | Không có. |
| Supervisor trong daemon | Cắt | Task Scheduler restart-on-failure + ping capture (phát hiện cả treo, không chỉ chết). | Không có. |
| Sensor 2 phút | Thay bằng tick 30' | §2: 720 lần kiểm cho 4–6 sự kiện. | Khi có SLO độ tươi dưới 30'. |
| L3 tự giao xlsx | Hoãn, nhưng **xếp trước** mọi mục trên khi có golden set | Đây là khâu người dùng chạm. Chưa đo chất lượng (S3) thì tự giao là đẩy sai số tới người dùng. | Golden set + eval đạt ngưỡng do người chốt. |
| Standing order mở rộng, thang L0–L3 tự hạ mức | Giữ bản có sẵn trong `article_tick.py` | Đã có L0–L2 và hạn 7 ngày. Không cần thêm logic tự hạ mức khi healthchecks báo thất bại. | — |

Với 2.672 dòng đã viết ở `project/src/ops/` (S1): không gộp vào nhánh khi chưa có ADR 0012. Có thể nhặt `procrun.py` (kill cây tiến trình) cho M3 nếu nó độc lập với `store.py` và DBOS.

---

## 6. Vấn đề hiện hữu bị plan đẩy xuống sau

1. **Dead-letter Bronze 1.427, tăng khoảng 20 bài trong vài giờ.** Đây là mất dữ liệu thật, radar gắn HIGH. Một ngày công cho việc này có giá trị cao hơn một ngày công cho bot.
2. **Watermark bị chặn 230 tệp.** OPEN-ITEMS mục gốc đã chỉ sửa đúng (`watermark = min` của phần chưa xong).
3. **Golden set 150–200 bài + `eval_article.py`** (hội đồng 24/09, cỡ M, "tiền đề cho mọi thứ"). Không có thước đo thì không biết agy ở L2 nạp vào DB cái gì, và không biết khi nào được lên L3.

Thứ tự đề xuất: M3 (timeout) → M1/M2/M7/M8 (lịch + dead-man) → sửa dead-letter/watermark → golden set → M4–M6, M9 → đánh giá lại plan đầy đủ bằng số sự cố đo được trong 4 tuần.

Tự động hoá một pipeline chưa đo chất lượng không sai hoàn toàn: tự động hoá cũng làm việc đo dễ hơn (đợt đều, dữ liệu đều). Nhưng tự động hoá **mức cao** (L2, L3, bot điều khiển, đội agent trực ban) trước khi đo là tối ưu sai chỗ: chi phí bảo trì đến ngay, lợi ích phụ thuộc vào chất lượng chưa biết.

---

## 7. Tự phản biện: phương án tối thiểu thiếu gì đáng tiền

| Điểm yếu | Mức nghiêm trọng thật | Đánh giá trung thực |
|---|---|---|
| **Treo mềm trong analyze**: agy vẫn sống, không ra lô, chưa tới deadline 45' | Trung bình | Phương án tối thiểu chỉ có deadline cứng, mất tối đa 45' mỗi lần. Plan đo tiến độ theo số tệp đầu ra, 0 token, và đó là ý tưởng rẻ, đáng chép vào M3 (thêm khoảng 20 dòng: poll số `*.output.json` mỗi phút, im lặng 15' thì kill). |
| **Đốt quota khi provider hỏng**: không breaker, tick thử lại mỗi 30' | Trung bình | Nếu agy trả 429 nhanh thì rẻ. Nếu agy chạy nửa đợt rồi 429 thì phần đầu đã tốn pool 5 giờ dùng chung với công việc tương tác. Bản breaker tệp 15 dòng ở §5 nên làm ngay ở M3, không đợi. |
| **Không can thiệp từ xa** | Thấp đến trung bình | AUTH hỏng thì vẫn phải về bàn đăng nhập lại, bot không cứu được. Tạm dừng từ xa thì giá trị thật, nhưng có thể làm bằng một lệnh duy nhất (bot nhận `/stop` tạo `AGY_STOP`) nếu D1 cho phép; không cần 15 lệnh. |
| **Mất vết kiểm toán có cấu trúc** | Thấp | Log văn bản grep được. Một người vận hành không cần truy vấn SQL trên sự kiện vận hành. |
| **Duyệt L1 từ điện thoại** | Trung bình | Đây là lý do mạnh nhất cho bot hai chiều. Phản biện: L1 là giai đoạn chuyển tiếp; cổng kỹ thuật ≥ 90% của `--finish` đã fail-loud; duyệt từ điện thoại mà không xem được nội dung bài thì là bấm theo phản xạ, không phải kiểm soát. Nên đi thẳng L2 khi 5 đợt sạch, và dành công sức cho golden set để cổng có nghĩa. |
| **Task Scheduler có lỗi cấu hình im lặng** (pin, "start when available", mất mật khẩu) | Trung bình | Đây là rủi ro thật của mọi phương án dựa trên Task Scheduler, kể cả plan (plan cũng dùng Task Scheduler làm gốc cây). healthchecks bắt được hậu quả trong 45'. |
| **Nợ khi quy mô tăng** (nhiều người dùng, nhiều nguồn, giao trong ngày) | Thấp hiện tại | Khi có SLO độ tươi dưới 30' hoặc lưu lượng gấp 3, phương án tối thiểu sẽ chật. Chi phí chuyển lúc đó thấp vì đơn vị thực thi vẫn là `article_run.py`, như plan thiết kế. |
| **Chi phí chìm 2.672 dòng** | — | Không phải lý do để triển khai. Nếu hội đồng chọn plan đầy đủ, lý do phải là sự cố đo được, không phải mã đã có. |

**Kết luận tự phản biện.** Hai thứ của plan thực sự đáng tiền và nên đưa vào phương án tối thiểu ngay: phát hiện treo bằng nhịp tiến độ theo tệp đầu ra, và một breaker tối giản dạng tệp cho QUOTA/AUTH. Cả hai cộng khoảng 35 dòng. Mọi thành phần còn lại cần một sự cố thật để biện minh, và 4 tuần chạy phương án tối thiểu với healthchecks sẽ cho đúng dữ liệu đó.
