# Lập trường 3: Human-in-the-loop và trải nghiệm vận hành

- **Ngày:** 2026-10-01
- **Vai:** Thành viên 3 hội đồng phản biện `plans/20261001-1100-autonomous-ops-24x7/plan.md`
- **Phạm vi:** §5.3 thang tự chủ, §7 quan sát, §8 mặt điều khiển, §11 quyết định; đối chiếu `docs/proposals/agy-automation-council-2026-09-23.md`, ADR 0008 (amendment 2026-09-18) và mã nháp đã có trong `project/src/ops/` (chưa commit).
- **Nhãn bằng chứng:** [M] đọc mã · [D] tài liệu kho · [S] nguồn ngoài · [I] suy luận.

---

## 1. Lập trường

Plan đặt người vào vòng lặp ở **sai chỗ và sai liều lượng**. Cổng duyệt L1 nằm trước `--finish`, đúng lúc người duyệt có ít thông tin nhất: số bài nhận về đã có, nhưng kết quả cổng DoD, độ lệch so với bộ đối chiếu tất định và chi phí chỉ xuất hiện **sau** `--finish`. Tin duyệt trong mã nháp chỉ mang một con số `received/total` [M `wave_flow.py:344-346`]. Đó là định nghĩa của rubber stamp. Ngược lại, điểm tác động ra ngoài thật sự (giao xlsx cho người dùng cuối, gửi nội dung bài sang provider thứ ba) lại không có cổng có nội dung.

Với một người vận hành, ngân sách chú ý là tài nguyên khan hiếm nhất của hệ thống. Thiết kế đề xuất thay thế ở §3: **bỏ cổng duyệt từng đợt**, giữ tự động hoá kỹ thuật ở mức L2 ngay khi các chốt kỹ thuật đạt, và dồn sự chú ý của người vào ba điểm: (a) mẫu soát chất lượng có chủ đích mỗi ngày, (b) duyệt tệp giao hàng trước khi tới người dùng cuối cho tới khi đủ niềm tin, (c) các sự cố cần phán đoán. Ngân sách cảnh báo có tiếng chuông: tối đa 2 tin mỗi ngày trong vận hành bình thường.

Lưu ý mâu thuẫn quản trị: amendment ADR 0008 ghi rõ *"Không dựng lại cổng hỏi người dưới bất kỳ tên nào"* và *"lệnh operator = phê duyệt"* [D ADR 0008 §2 amendment]. Cổng L1 của plan là một cổng hỏi người trước khi nạp DB. Nếu giữ, ADR 0012 phải sửa tường minh amendment đó; nếu không, cổng L1 trái ADR đang hiệu lực.

---

## 2. Bảng phát hiện

| Mã | Mức | Phát hiện | Bằng chứng | Đề xuất |
|---|---|---|---|---|
| H1 | Chặn | Tin duyệt L1 chỉ có `received/total` và phần trăm. Không có kết quả DoD, tỷ lệ bản ghi hỏng, độ lệch thực thể so với bộ đối chiếu, mẫu bài, token/USD. Người duyệt không có căn cứ để từ chối, nên mọi lần bấm "Nạp DB" là phản xạ. | [M] `wave_flow.py:335-350`. [S] tổng quan 2025 về automation bias: đồng thuận với khuyến nghị sai là kết quả hành vi nhất quán nhất; giải thích dạng văn xuôi còn tăng mức phục tùng ([TechTarget](https://www.techtarget.com/it-strategy/feature/Human-in-the-loop-shouldnt-rubber-stamp-decisions), [Approval fatigue](https://tianpan.co/blog/2026/06/25/approval-fatigue-how-human-in-the-loop-gates-decay-into-rubber-stamps)). | Bỏ cổng duyệt từng đợt (§3). Nếu vẫn giữ trong giai đoạn đầu, chạy validator DoD ở chế độ khô (không nạp) trước khi hỏi và đưa vào tin các trường ở §3.2. |
| H2 | Chặn | Cổng L1 trái amendment ADR 0008 ("không dựng lại cổng hỏi người dưới bất kỳ tên nào"). Plan không nêu mâu thuẫn này. | [D] ADR 0008 amendment 2026-09-18; plan §5.3 | ADR 0012 phải chọn một: sửa amendment tường minh, hoặc bỏ cổng L1 và thay bằng chốt kỹ thuật cộng soát mẫu. |
| H3 | Chặn | Quá hạn duyệt thì đợt PARKED, nhưng PARKED không phải trạng thái "đang chạy", nên sensor mở đợt mới. Bài của đợt PARKED chưa nạp nên vẫn tính là pending, có khả năng bị đóng gói và phân tích lại. Chưa thấy cơ chế loại bài đang thuộc đợt dở trong bộ chọn. | [M] `store.py:17` (AWAIT_APPROVAL là active, PARKED thì không); `article_pack.py` không có điều kiện loại bài thuộc đợt chưa nạp [I, cần xác minh] | Chốt bất biến: bài thuộc đợt PARKED được giữ chỗ, không đóng gói lại. `/retry` trên đợt PARKED vì quá hạn duyệt chỉ chạy `--finish`. Thêm test. |
| H4 | Nặng | Trong lúc AWAIT_APPROVAL, đợt được coi là active, sensor ngừng mở đợt tới 120 phút. Một cuộc họp hai tiếng làm đứng cả pipeline; ban đêm T1 vẫn mở đợt, tin duyệt tới lúc 02:00 rồi PARKED lúc 04:00. | [M] `store.py:17`; [D] `ops.yaml` `approval_timeout_minutes: 120`, `age_rule_hours: [6,22]` | Không giữ đợt chờ người trong luồng chính. Nếu có cổng, đợt đã phân tích chuyển sang hàng "chờ nạp", sensor chạy tiếp. Ngoài giờ trực, không gửi yêu cầu duyệt; dồn vào bản tin sáng. |
| H5 | Nặng | Yêu cầu duyệt gửi ở mức `warn`, mà `warn` được gửi **im lặng**. Đúng thứ cần người hành động lại không có chuông; trong khi mỗi đợt DONE lại thành một tin `info` riêng, trái plan §7.3 ("gom vào bản tin"). | [M] `notify.py:13` `SILENT_SEVERITIES = {"warn","info","digest"}`; `wave_flow.py:348`, `wave_flow.py:411` | Tách trục "cần người" khỏi trục "mức độ". Tin cần hành động luôn có chuông trong giờ trực; `info` không bao giờ thành tin riêng. |
| H6 | Nặng | Tiêu chí "5 đợt sạch" chỉ đo kỹ thuật. `clean_streak` tăng cả khi đợt DONE vì "không còn bài để xử lý" và khi L3 giao xlsx lỗi. Người **từ chối** đợt (`/reject` → CANCELLED) và đợt PARKED quá hạn duyệt **không** reset chuỗi sạch. Tín hiệu chất lượng duy nhất mà người cung cấp bị bỏ qua khi xét lên mức. | [M] `wave_flow.py:407-421`, `wave_flow.py:513-514`, `wave_flow.py:549-552` | "Sạch" = đạt chốt kỹ thuật **và** soát mẫu không có lỗi nghiêm trọng **và** không bị người từ chối. `/reject` bắt buộc chọn lý do và reset chuỗi. Đợt rỗng không tính. |
| H7 | Nặng | Điều kiện L3 trong plan là "5 ngày L2 sạch", mã dùng chung bộ đếm 5 đợt và gợi ý lên mức bằng một nút bấm. Một buổi sáng nhiều tin có thể đưa hệ thống tới ngưỡng gợi ý giao xlsx tự động trong vài giờ. | [D] plan §5.3; [M] `wave_flow.py:414-418` | Lên L3 không bao giờ là một chạm: yêu cầu cửa sổ thời gian (≥ 5 ngày làm việc), số mẫu đã soát và lệnh gõ tay có lý do. |
| H8 | Nặng | Giao xlsx cho người dùng cuối là điểm duy nhất có tác động ra ngoài, nhưng plan chỉ có "người bật L3"; không có xem trước nội dung, không có SLA giao hàng, không có lối thu hồi tệp sai. Xem xét theo bối cảnh công ty chứng khoán: bản tin sai mã CP hoặc sai sắc thái tới tay người dùng là rủi ro uy tín và tuân thủ. | [D] plan §5.2, §5.3; ADR 0010 | Thêm cổng giao hàng có nội dung (§3.1 điểm D2). Ghi phiên bản tệp, cho phép `/recall <ngày>` thay tệp và báo người nhận. |
| H9 | Nặng | Chuyển sang OpenRouter có hàm ý gửi toàn văn bài báo tới một bên trung gian và nhà cung cấp mô hình khác, cùng thay đổi chi phí. Plan để `failover: ask` là một nút **[Chuyển OpenRouter]** lúc sự cố, khi người đang chịu áp lực thời gian. | [D] plan §6.3, §11 D5; hội đồng 23/09 rủi ro 4 "dữ liệu ra ngoài/ToS" | Quyết định dữ liệu và chi phí phải chốt một lần, bằng văn bản, ngoài lúc sự cố (D8 mới ở §4). Lúc sự cố chỉ còn nút thực thi chính sách đã duyệt; nếu chưa duyệt thì không hiện nút. |
| H10 | Nặng | Gia hạn standing order bằng `/order extend 7` một chạm. Cảnh báo "còn < 24h" cộng nút bấm sẽ thành thói quen gia hạn mà không xem lại. Standing order mất giá trị "lệnh operator tường minh". | [D] plan §5.3, §8.1; [M] `order.py:144-158` | Gia hạn kèm "bản kê tuần" bắt buộc hiển thị trước (§3.4). Gia hạn cần gõ lại mức và một dòng lý do. Hết hạn thì hạ về L2-không-giao-hàng, không về L0. |
| H11 | Nặng | `/diagnose` trả một lệnh kèm nút **[Chạy]**. Sentinel đọc `ops_events` và log, trong đó có trích đoạn stderr chứa nội dung bài (nguồn prompt injection đã được hội đồng 23/09 xếp rủi ro số 1). Nút chạy ngay sau giả thuyết bằng văn xuôi là điều kiện tối đa cho automation bias. | [D] plan §4.1, §8.1; hội đồng 23/09 §6.1; [S] HBS 2024: lời giải thích tăng mức phục tùng | Thiết kế lại ở §3.5: sentinel chỉ chọn mã lệnh trong danh mục đóng; tin hiển thị bằng chứng trước, giả thuyết sau, mô tả hậu quả và lệnh hoàn tác; lệnh có tác dụng phụ cần gõ lại mã đợt. |
| H12 | Vừa | Ước lượng tải tin: ở L1 với 10 đợt/ngày, mã nháp gửi khoảng 10 yêu cầu duyệt + 10 tin DONE + 2 bản tin + cảnh báo đầu/hồi phục của probe + gợi ý lên mức, tức 25–35 tin/ngày ngày bình thường; ngày có sự cố nhảy vọt. Ngưỡng Google SRE: dưới 2 sự cố cần hành động mỗi ca 12 giờ; mỗi trang báo phải cần trí tuệ, phản ứng máy móc thì không nên là trang báo. | [M] tính từ `wave_flow.py`, `probes.py:146-175`; [S] [Google SRE workbook: on-call](https://sre.google/workbook/on-call/), [SRE book: monitoring](https://sre.google/sre-book/monitoring-distributed-systems/) | Ngân sách cứng ở §3.3, đo bằng `ops_alerts` mỗi tuần, vượt ngân sách là lỗi thiết kế cần sửa. |
| H13 | Vừa | Ma trận §7.3 chưa actionable: nhiều dòng không kèm hành động cụ thể ("dead-letter tăng > 50/ngày", "repair vòng 2", "QUOTA"). `warn` ghi "không bắt buộc" nghĩa là không nên là tin đẩy. | [D] plan §7.3 | Mỗi cảnh báo đẩy phải có: điều gì xảy ra, hệ thống đã tự làm gì, người cần làm gì (một lệnh), hạn chót. Thiếu một trong bốn thì hạ thành sự kiện. |
| H14 | Vừa | Ba mặt điều khiển (Telegram, TUI quake, radar) cộng email healthchecks cho một người. Plan nói "mọi kênh chỉ đọc `ops_events`", nhưng TUI Textual bốn khung là tính năng lớn mà R6/R7 không đòi. | [D] plan §8 | MVP: Telegram + healthchecks + radar mở rộng. TUI chỉ bản `--tail` chỉ đọc, hoãn Textual tới khi có số đo cần dùng. |
| H15 | Vừa | Tập lệnh §8.1 thừa `/waves`, `/log` riêng (gộp được vào `/status` và `/wave <mã>`); thiếu `/ack` (nhận xử lý, tắt nhắc lại), `/snooze <giờ>` (đi họp), `/quiet` (giờ yên lặng), `/sample` (lấy mẫu soát), `/recall` (thu hồi giao hàng), `/handover` (chuyển người trực). | [D] plan §8.1 | Xem §3.6. |
| H16 | Vừa | Tự hạ mức sau 2 đợt hỏng, rồi gợi ý lên lại sau 5 đợt sạch, không có trễ (hysteresis) và không yêu cầu người xác nhận nguyên nhân gốc. Lỗi provider chập chờn sẽ tạo dao động L2-L1-L2 và chuỗi tin liên quan. | [M] `wave_flow.py:419-438`; [I] | Hạ mức tự động, lên mức chỉ sau khi người ghi nguyên nhân gốc (`/rca <đợt> <dòng>`) và đủ cửa sổ thời gian. Lỗi lớp provider (QUOTA, NETWORK) không tính vào chuỗi hỏng. |
| H17 | Vừa | Không có định nghĩa giờ trực, cuối tuần, người thay thế khi vắng. healthchecks và cảnh báo đỏ ban đêm đều đổ về một điện thoại. | [D] plan §11 D7 | Thêm D9, D10 ở §4. Ngoài giờ trực chỉ hai loại tin có chuông: máy/daemon chết và AUTH, và cả hai đều có thể đợi tới sáng nếu không có SLA đêm. |
| H18 | Nhẹ | Plan ghi "Chưa có dòng mã nào", trong khi `project/src/ops/` đã có khoảng 2.470 dòng chưa commit, gồm cả cổng duyệt và logic lên/xuống mức. Thiết kế HITL đang bị mã đi trước. | [M] `wc -l src/ops/*.py`; git status | Cập nhật trạng thái plan; mọi sửa HITL ở tài liệu này áp vào mã nháp trước khi duyệt ADR 0012. |
| H19 | Nhẹ | Gộp trùng `dedup_key` chỉ tăng bộ đếm trên tin đã gửi; người không thấy số lần lặp nếu tin đầu đã đi. | [M] `store.py:262-270`, `notify.py:102` | Bản tin liệt kê cảnh báo lặp kèm số lần; tin lặp vượt ngưỡng thì gửi một tin "đang lặp N lần" duy nhất. |

---

## 3. Thiết kế HITL đề xuất thay thế

### 3.1 Điểm quyết định của người

| Điểm | Khi nào | Người quyết định gì | Mặc định nếu im lặng |
|---|---|---|---|
| D0. Chính sách | Một lần, cập nhật theo quý | Provider được phép, dữ liệu được gửi ra ngoài, người nhận cảnh báo, giờ trực, SLA giao hàng | Không có chính sách thì không có failover |
| D1. Soát mẫu hằng ngày | 1 lần/ngày, 10 phút, giờ do người chọn | Chấm 5 bài lấy mẫu phân tầng (ưu tiên bài có mã watchlist, bài lệch với bộ đối chiếu, bài sắc thái mạnh): đúng/sai thực thể, tóm tắt trung thành, sắc thái | Không soát thì không được lên mức, không hạ mức |
| D2. Giao hàng | Trước mỗi lần xuất xlsx, cho tới khi đủ 10 ngày soát sạch | Xem bản xem trước: số dòng mỗi người dùng, 3 dòng đầu mỗi tệp, cờ bất thường | Quá hạn giao thì gửi bản tin "chưa giao" cho người vận hành, không tự giao |
| D3. Sự cố cần phán đoán | Khi chốt kỹ thuật đỏ hoặc lỗi lạ | Chọn trong danh mục hành động đóng | Hệ thống giữ trạng thái an toàn, không tự lặp |
| D4. Đổi mức tự chủ | Khi người muốn | Lên mức kèm lý do; hạ mức tự do | Chỉ hạ tự động |

Nạp DB **không** là điểm quyết định của người: chốt kỹ thuật (DB ghi được, nạp không lỗi, độ phủ ≥ 90%, tỷ lệ hỏng < 10%) đủ để quyết định, đúng tinh thần ADR 0008 amendment. Lỗi chất lượng phát hiện ở D1 được xử lý bằng chạy lại đợt, không bằng chặn trước.

### 3.2 Nội dung tin khi người phải quyết định (áp cho D2 và cổng L1 nếu vẫn giữ)

Mỗi tin quyết định có đủ năm khối, theo thứ tự:
1. **Việc cần quyết:** một câu, kèm hạn chót và mặc định nếu im lặng.
2. **Bằng chứng định lượng:** độ phủ hai lớp, tỷ lệ bản ghi bị validator loại, số bài lệch thực thể so với bộ đối chiếu tất định (số và tỷ lệ), phân bố sắc thái so với trung bình 7 ngày, token và USD so với trung vị.
3. **Bất thường:** chỉ liệt kê chỉ số lệch quá 2 độ lệch chuẩn so với 7 ngày; không có thì ghi "không có bất thường".
4. **Mẫu:** 2 bài lệch nhiều nhất (tiêu đề, mã CP mô hình trích, mã CP bộ đối chiếu trích), có lệnh `/sample <đợt>` để xem thêm. Chỉ siêu dữ liệu, không toàn văn, theo ràng buộc D1 của plan.
5. **Hành động:** nút có hậu quả ghi rõ ("Giao 6 tệp", "Giữ lại, báo tôi lúc 08:00").

### 3.3 Ngân sách cảnh báo mỗi ngày (một người)

| Loại | Kênh | Ngân sách | Ghi chú |
|---|---|---|---|
| Có chuông, trong giờ trực | Telegram | ≤ 2/ngày bình thường, ≤ 6/ngày có sự cố | Chỉ tin cần hành động trong 1 giờ |
| Có chuông, ngoài giờ trực | Telegram + healthchecks | 0 bình thường; chỉ máy/daemon chết và AUTH | Có thể tắt hẳn nếu D10 = không trực đêm |
| Im lặng | Telegram | ≤ 3/ngày | Bản tin 08:00, 17:30, và yêu cầu D2 |
| Không đẩy | `ops_events`, radar, `/status` | Không giới hạn | Mọi DONE, info, warn không cần hành động |

Đo hằng tuần: số tin có chuông, tỷ lệ tin có chuông dẫn tới hành động (mục tiêu ≥ 80%), thời gian tới `/ack`. Tỷ lệ hành động thấp là lỗi của luật cảnh báo, không phải của người.

### 3.4 Thay `/order extend 7` bằng gia hạn có xem lại

- Hai ngày trước hạn, bản tin chèn "bản kê tuần": số đợt, số đợt hỏng, kết quả soát mẫu D1, các lần người can thiệp, chi phí.
- Gia hạn bằng lệnh gõ `/order renew L2 7 <lý do>`; không có nút một chạm. Lý do và hash bản kê ghi vào standing order.
- Không soát mẫu đủ 3/5 ngày trong kỳ thì lệnh gia hạn bị từ chối kèm giải thích.
- Hết hạn không đưa về L0 (gây đứng pipeline, tạo áp lực gia hạn vội), mà về mức "L2 không giao hàng".

### 3.5 Thiết kế lại `/diagnose`

- Sentinel trả JSON: `{evidence: [mã sự kiện], hypothesis, action_code}`; `action_code` thuộc danh mục đóng (ví dụ `RETRY_FINISH`, `RELOGIN_AGY`, `RESET_BREAKER`, `NONE`). Daemon dựng lệnh từ mã, không dùng chuỗi lệnh do mô hình sinh.
- Tin hiển thị **bằng chứng trước** (sự kiện gốc, trích dẫn nguyên văn), giả thuyết sau, rồi "lệnh này sẽ làm gì, có hoàn tác được không".
- Hành động chỉ đọc hoặc hoàn tác được: một nút. Hành động không hoàn tác được: không có nút, người gõ lệnh kèm mã đợt.
- Đo: tỷ lệ người làm theo đề xuất và tỷ lệ đề xuất sai. Tỷ lệ làm theo gần 100% trong khi đề xuất sai > 0 là tín hiệu automation bias, cần báo trong bản kê tuần.
- Nội dung bài không được vào ngữ cảnh sentinel; log subprocess được lọc chỉ giữ dòng do mã dự án sinh.

### 3.6 Mặt điều khiển MVP cho R6/R7

| R | Đủ với |
|---|---|
| R6 nắm được hoạt động | `ops_events` + radar mục 4 + `/status` (gộp `/waves`) + `/wave <mã>` (gộp `/log`) + bản tin 2 lần/ngày |
| R7 can thiệp được | `/pause` `/resume` `/stop` `/retry` `/ack` `/snooze <giờ>` `/sample` `/deliver` `/recall` `/level` `/order renew` |
| Hoãn | TUI Textual, `/provider` đổi tay (theo chính sách D0), `/diagnose` tới P5 |

---

## 4. Quyết định bổ sung cần chốt (ngoài D1–D7)

| # | Câu hỏi | Lý do |
|---|---|---|
| D8 | Chính sách FPTS về gửi **toàn văn** bài báo tới Google (agy) và OpenRouter: tài khoản cá nhân hay miền công ty, có cần bộ phận CNTT/tuân thủ duyệt không | D1 của plan chỉ hỏi về Telegram (siêu dữ liệu); luồng dữ liệu lớn nhất ra ngoài là dữ liệu vào mô hình |
| D9 | Người thay thế khi vắng (nghỉ phép, ốm): có ai không, có quyền gì, cách bàn giao (`/handover`) | Một `chat_id` là điểm hỏng đơn |
| D10 | Giờ trực: có trực đêm và cuối tuần không. Nếu không, hệ thống ban đêm làm gì (chỉ T1, không giao hàng) | Quyết định ngân sách chuông ngoài giờ |
| D11 | SLA với người dùng cuối: bản tin xlsx phải có lúc mấy giờ, độ trễ tối đa của bài, ai được báo khi trễ | Không có SLA thì không biết cảnh báo nào là thật sự khẩn |
| D12 | Lối thu hồi: khi tệp giao sai, ai báo người dùng, thay tệp thế nào | Tác động ra ngoài cần đường lùi |
| D13 | Chuẩn chất lượng tối thiểu cho "sạch" (ví dụ ≤ 1 lỗi thực thể nghiêm trọng trên 5 bài soát) | Không có thì L2/L3 chỉ đo kỹ thuật |

---

## 5. Câu hỏi cho người vận hành

1. Mỗi ngày có thể dành chắc chắn bao nhiêu phút cho việc soát, và vào giờ nào?
2. Trong 2 tuần qua, có lần nào phát hiện lỗi chất lượng mà số đếm kỹ thuật không bắt được không? Lỗi dạng gì?
3. Lúc họp hoặc ngủ, có chấp nhận pipeline vẫn nạp DB mà không hỏi, miễn là giao hàng còn chờ duyệt không?
4. Người dùng cuối đang kỳ vọng nhận xlsx lúc mấy giờ, và có ai phàn nàn về độ trễ chưa?
5. Có được phép, theo chính sách FPTS, để Telegram trên điện thoại cá nhân nhận siêu dữ liệu vận hành không; nếu không, Teams có thay được không?
6. Nạp DB một đợt sai có gỡ lại được theo mã đợt không? Nếu gỡ được dễ, cổng trước `--finish` càng ít lý do tồn tại.

---

## 6. Nguồn

- [Google SRE workbook: being on-call](https://sre.google/workbook/on-call/) · [Google SRE book: monitoring distributed systems](https://sre.google/sre-book/monitoring-distributed-systems/) · [Rob Ewaschuk, My Philosophy on Alerting](https://docs.google.com/document/d/199PqyG3UsyXlwieHaqbGiWVa8eMWi8zzAn0YfcApr8Q/mobilebasic)
- [TechTarget: HITL shouldn't rubber-stamp decisions](https://www.techtarget.com/it-strategy/feature/Human-in-the-loop-shouldnt-rubber-stamp-decisions) · [Approval fatigue: HITL gates decay into rubber stamps](https://tianpan.co/blog/2026/06/25/approval-fatigue-how-human-in-the-loop-gates-decay-into-rubber-stamps) · [Bias in the Loop (arXiv 2509.08514)](https://arxiv.org/pdf/2509.08514)
- Bainbridge, L. (1983), *Ironies of Automation*; Parasuraman, R. & Manzey, D. (2010), *Complacency and Bias in Human Use of Automation*, Human Factors 52(3).
