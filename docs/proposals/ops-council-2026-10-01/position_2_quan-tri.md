# Lập trường thành viên 2 — Quản trị và bất biến

- **Đối tượng phản biện:** `plans/20261001-1100-autonomous-ops-24x7/plan.md`
- **Ngày:** 2026-10-01
- **Phạm vi:** đối chiếu plan và phần mã đã xuất hiện trong cây làm việc với `AGENTS.md`, `docs/HARNESS.md`, `docs/FEATURE_INTAKE.md`, ADR 0008/0010/0011, hội đồng agy 23/09, `.agents/registry.yaml`, `.agents/pipeline.yaml`, Rule 06/07/08/09.
- **Phương pháp:** chỉ đọc. Lệnh đã chạy: `git status`, `git log`, `pipeline_radar.py status`, `harness_cli.py query matrix`, `harness_cli.py query contract`.

---

## 1. Lập trường

Thiết kế đúng hướng về kiến trúc: Python giữ vai conductor tất định, agy chỉ là hàm nhận thức, token không thành cổng, `--finish` giữ cổng kỹ thuật. Về quản trị, plan **không thể duyệt ở trạng thái hiện tại**, vì ba lý do:

1. **Hard Gate đã bị vượt trên thực tế.** Plan tự xếp phần triển khai vào high-risk và ghi "cần ADR 0012 và duyệt trước khi code", nhưng trong cây làm việc đã có 16 module `project/src/ops/` (3.657 dòng tại thời điểm đọc, sinh từ 10:35 tới sau 10:43 hôm nay, sau plan lúc 10:09), gồm cả phần của P2, P4, P5. Chưa có ADR 0012, chưa có tệp story, story `US-029` đã `in_progress` mà ma trận không có bằng chứng.
2. **Mã đã viết làm rỗng ý nghĩa standing order.** Đợt có thể tự chạy và tiêu token khi standing order đã hết hạn (đường tự chạy lại sau breaker). Mức tự chủ lên thẳng L3 bằng một lệnh, không kiểm điều kiện. Một nút "Gia hạn 7 ngày" được đẩy kèm cảnh báo.
3. **Nguồn chân lý điều phối bị tách đôi.** Thứ tự bước của đợt nằm cứng trong `drive_wave`, còn `pipeline.yaml` vẫn mô tả lane DSH `--batch 100` qua `run_code`. Plan chỉ nhắc sửa registry, không nhắc sửa pipeline.

Đề xuất: **đóng băng phần mã**. Park `US-029` sang `blocked` với lý do "chờ ADR". Soạn ADR (đổi số, xem G3), người duyệt xong mới cho mã đi tiếp theo đúng thứ tự phase.

---

## 2. Bảng phát hiện

Mức: **Chặn** (không được đi tiếp), **Nặng** (phải sửa trong ADR/plan trước khi duyệt), **Vừa** (sửa trước phase liên quan), **Nhẹ** (ghi nhận).

| Mã | Mức | Phát hiện | Bằng chứng | Đề xuất |
|---|---|---|---|---|
| G1 | Chặn | Code trước ADR, vượt Hard Gate. Plan ghi "Chưa có dòng mã nào" và "cần ADR 0012 và duyệt trước khi code". Thực tế đã có `src/ops/{daemon,dbos_flow,wave_flow,sensor,breakers,order,commands,notify,probes,reports,sentinel,store,supervisor,procrun,config}.py` cùng `config/ops.yaml`, chưa commit. Mã tự xưng "theo ADR 0012" trong khi ADR không tồn tại. | `plan.md:4-5`; `src/ops/__init__.py:1`; `config/ops.yaml:1`; `wave_flow.py:490`; `ls docs/decisions/` dừng ở 0011; `FEATURE_INTAKE.md:33-55,64`; `HARNESS.md:24,60` | Park `US-029` (`blocked`, lý do "chờ ADR, người duyệt"). Giữ mã ở nhánh riêng, không merge. Chỉ spike P0 (scratch) được chạy trước khi duyệt. |
| G2 | Chặn | `project/tests/test1.py` hỏng cú pháp (`from __future__ import anotations`) nên làm vỡ bước thu thập của `pytest tests/` và vi phạm AGENTS §7 (100% PASS, `ast.parse`). Ở cấp module, tệp này đọc `OPENROUTER_API_KEY` từ `openrouter/.env` và gọi mạng tới `openrouter.ai`. Nếu sửa xong lỗi cú pháp, mỗi lần chạy pytest sẽ gửi khoá ra ngoài, chạm Hard Gate "External API / secrets". Tệp không thuộc plan nào. | `tests/test1.py:1,13-25`; `openrouter/check_key.py:5-16` | Gỡ `test1.py` khỏi `tests/` trước mọi lần chạy pytest. Kiểm khoá OpenRouter là việc thủ công, không đặt trong bộ test. |
| G3 | Nặng | Số ADR 0012 đã được giữ chỗ cho việc khác: kế hoạch kiểm toán 24/09 dành 0012 cho "ngữ nghĩa đã phân tích, giao hàng bài code_first, cổng `--finish` 90% hay 100%", điều kiện chặn đợt backlog. Plan 01/10 lấy lại đúng số này. | `plans/20260924-1627-.../plan.md:77,114,131,141-142`; `R2-architecture-critique.md:195,243` | Kiểm lại số kế tiếp còn trống. ADR vận hành tự chủ lấy số mới (0013 hoặc sau, sau khi tra). Ghi tham chiếu chéo để ADR cổng `--finish` không bị bỏ quên. |
| G4 | Nặng | Chạy tiếp đợt mà không có standing order hợp lệ. `retry_wave` ép mức tối thiểu L1 với lý do "chạy lại do người bấm là một lần duyệt", nhưng hàm này còn được gọi **tự động** khi breaker đóng (`wave.auto_resume`). Kết quả: đợt PARKED vì provider sẽ tự phân tích lại, tiêu token, kể cả khi lệnh đã hết hạn và mức hiệu lực là L0. Trái ADR 0008 (amendment, điểm 1), và trái hội đồng 23/09 vốn coi standing order là "lệnh tường minh có thời hạn". | `daemon.py:257-263,358-360`; `order.py:35-48`; ADR 0008 `:45`; hội đồng `:109` | Tự chạy lại chỉ khi `order.effective_level() != "L0"` tại thời điểm chạy. Nếu không, chuyển thành cảnh báo kèm nút. Viết test: lệnh hết hạn + breaker đóng thì không mở workflow. |
| G5 | Nặng | Lên mức không kiểm điều kiện. `/level L3` được chấp nhận bất cứ lúc nào, tự tạo lệnh 7 ngày nếu chưa có, và **xoá `fail_streak`**, tức xoá luôn lịch sử dùng để tự hạ mức. Điều kiện "5 đợt L1 sạch", "5 ngày L2 sạch" chỉ là gợi ý, không phải ràng buộc. Không có dòng nào ghi trace harness, trong khi plan §8.1 và hội đồng 23/09 đều đòi. | `commands.py:145-156`; `wave_flow.py:409-418`; `plan.md:214-217,317`; hội đồng `:109`; `grep harness src/ops` rỗng | Lệnh lên mức phải kiểm điều kiện đo được trong `ops.db`. Thiếu điều kiện thì từ chối và nói thiếu gì. Mỗi lần đổi mức, gia hạn hay đổi provider ghi một dòng `harness_cli.py trace` (actor, mức cũ/mới, hash lệnh). Không xoá `fail_streak` khi đổi mức. |
| G6 | Nặng | "Đợt sạch" chưa có định nghĩa. Mã cộng `clean_streak` cho mọi `DONE`, kể cả đợt "Không còn bài để xử lý" (0 bài), đợt phải vá 2 vòng và đợt giao xlsx lỗi. Đợt rỗng ban đêm theo T2 có thể tự tích đủ 5 "đợt sạch". | `wave_flow.py:507-509,548-553,407-410` | ADR định nghĩa: sạch = đã nạp DB, `--finish` thoát 0, n ≥ 20 bài, ≤ 1 vòng vá, không PARKED. Đợt 0 bài không mở workflow. |
| G7 | Nặng | Gia hạn bằng một chạm làm rỗng ý nghĩa duyệt. Cảnh báo L0 đẩy sẵn nút "Gia hạn 7 ngày". `/order extend` tự nâng L0 lên L1. `extend` tính lại từ hôm nay, giữ nguyên mức cũ (có thể là L3). Kết quả: L3 được gia hạn vô thời hạn bằng phản xạ bấm nút trên điện thoại, không thấy lại điều kiện hay số đo. | `daemon.py:284-289`; `commands.py:158-165`; `order.py:144-158` | Gia hạn phải hiện tóm tắt 7 ngày qua (số đợt, độ phủ, sự cố, token) và xác nhận hai bước. Mức ≥ L2 chỉ được gia hạn từ máy (console), không qua Telegram. Không đặt nút gia hạn trong cảnh báo. |
| G8 | Nặng | Hai nguồn chân lý điều phối. Rule 07 §2 cấm điều phối ngoài manifest, nhưng thứ tự bước nằm cứng trong `drive_wave`. `pipeline.yaml` vẫn ghi `--batch 100`, `run_code`, DSH, không có stage sensor/daemon. Plan đổi `master-orchestrator` (conductor, "gọi cognitive qua invoke_subagent, đọc pipeline.yaml") thành `ops_daemon`, mà daemon không đọc manifest. | `.agents/rules/07-*.md:16-17`; `pipeline.yaml:28-57`; `registry.yaml:27-36`; `wave_flow.py:489-560`; `plan.md:383` | ADR phải chốt một trong hai hướng: (a) daemon đọc chuỗi bước từ `pipeline.yaml`, hoặc (b) `pipeline.yaml` mô tả đúng đường agy (batch 50, sensor, cổng L1/L2), kèm một test đối chiếu `drive_wave` với manifest. Sửa mô tả `master-orchestrator` cho khớp class. |
| G9 | Vừa | Ngưỡng độ phủ bị lặp. `wave_flow.MIN_COVERAGE = 0.90` chép từ `article_run.py`, trong khi chính ADR 0012 (theo nghĩa cũ, G3) còn treo câu hỏi 90% hay 100%. Hai hằng số sẽ trôi lệch nhau. | `wave_flow.py:22,524-531`; `article_run.py:47,891` | Đọc ngưỡng từ một nơi (import hằng của `article_run`, hoặc chỉ dựa vào mã thoát của `--finish`). Kiểm độ phủ trước `--finish` chỉ được dùng để quyết định vá, không được thành cổng thứ hai. |
| G10 | Vừa | Plan viết lại tham số của ADR 0011 đã accepted nhưng tự nhận là "mở rộng, không đảo ngược": ngưỡng 50 lên 100, khung giờ 07:30 sang 07:15 ±15', thay lịch Task Scheduler của `article_tick.py` bằng daemon, thêm OpenRouter làm failover. Các điểm này là sửa nội dung ADR 0011 §6. | `plan.md:150,181-185,370`; ADR 0011 `:41-45`; `article_tick.py:31` | ADR mới ghi rõ "supersedes ADR 0011 §6" và cập nhật trạng thái của 0011. |
| G11 | Vừa | Failover tự động sang OpenRouter chỉ cần `/failover auto` gõ qua Telegram. Plan (§6.3) đòi "người đã duyệt trước điều kiện dữ liệu và chi phí", nhưng mã không kiểm gì thêm. Gửi nội dung bài sang một nhà cung cấp mới là Hard Gate (provider endpoint, chính sách dữ liệu). Ngoài ra `openrouter_runner.py` đang sửa dở, chưa commit, nằm ngoài story nào, tức là một luồng việc thứ hai song song với US-029. | `daemon.py:270-276`; `plan.md:252`; `git diff --stat` (`openrouter_runner.py` +88/−15) | `auto` chỉ được bật khi có ADR/quyết định ghi trong harness về OpenRouter (dữ liệu, chi phí, DoD tương đương). Đưa thay đổi `openrouter_runner.py` vào một story riêng, hoặc park nó. |
| G12 | Vừa | Canary "1 lô 5 bài" là một cách chia lô thứ hai, trái bất biến "`--batch` là cách chia lô duy nhất". Nó còn là di sản của quota guard 23/09 mà plan đã bỏ. | `plan.md:201,242`; AGENTS §6B | Nếu giữ canary, mô tả nó thành một đợt riêng `--limit 5 --batch 5` qua đúng lệnh hiện có. Hoặc bỏ hẳn, để HALF_OPEN thử bằng lô đầu của đợt thật. |
| G13 | Vừa | `ops-sentinel` chưa đi đủ quy trình Rule 07 §4. Plan không nêu `dod_contract`, `io_boundary`, `kpis`, SKILL.md, hay stage trong `pipeline.yaml`. Tiêu chí "≥ 8/10 đúng lệnh" chưa có cách ghi `agent_metrics`. Dù vậy `sentinel.py` đã được viết (thuộc P5) trước cả P0. Danh sách trắng có `/run` và `/provider openrouter`, nên agent đề xuất được đường tiêu token hoặc đổi provider. | `rules/07-*.md:24-31`; `plan.md:373,383`; `sentinel.py:20-26` | Entry draft phải có đủ 5 bước trước khi gọi thật. Bỏ `/run` và `/provider openrouter` khỏi danh sách trắng, chỉ để các lệnh khôi phục trạng thái (`/retry`, `/reset`, `/resume`, `/capture restart`, `none`). Ghi KPI qua `harness_cli.py metric --agent ops-sentinel`. |
| G14 | Vừa | Thứ tự phase sai rủi ro. P2 cho đợt tự chạy ở L1 trước P3 (phân loại AUTH/NETWORK, breaker bền, deadline, kill cây, chaos test). Trong 5 đợt nghiệm thu P2, một lần agy treo hoặc mất đăng nhập sẽ không được xử lý đúng. P3 và P4 xếp `normal` dù chạm External API, scheduler flow và hành vi đã test (3–4 cờ). P4 còn "Lên L2", tức một quyết định quản trị (H3 của hội đồng 23/09) bị gói vào lane normal. | `plan.md:368-373`; `FEATURE_INTAKE.md:20-55`; hội đồng `:137-138` | Thứ tự: P0 → P1 → P3 (chaos bằng fake-agy) → P2 → P4 → P5. Lên L2 và L3 là cổng người riêng (H), không thuộc phase. P3 gắn lane high-risk, hoặc ít nhất normal kèm duyệt vì chạm provider. |
| G15 | Vừa | Rule 08 và Rule 09 chưa nhắc tới daemon hay agy. Plan liệt kê DSH là provider dự phòng, nhưng DSH bắt buộc qua cổng 14 hạng mục và người mở phiên mới, nên không thể tự động hoá. Mã chỉ có `agy` và `openrouter`. Ngoài ra `ops_events` được gọi là "nguồn sự thật duy nhất của vận hành", song song với radar là điểm vào duy nhất của Rule 08. | `plan.md:15,142,268`; `order.py:12`; `rules/09-*.md` | Bỏ DSH khỏi danh sách failover. Bổ sung Rule 08: radar mục 4 đọc `ops.db`, và `/status` gọi radar chứ không tính lại. Ghi rõ ranh giới: `ops_events` là nhật ký vận hành, radar là điểm vào. |
| G16 | Nhẹ | `SESSION-LATEST.md` ghi "chưa code", trong khi cây làm việc đã có mã. Bàn giao sai sự thật. | `docs/SESSION-LATEST.md:5,21` | Viết lại khi đóng phiên. |
| G17 | Nhẹ | Bản tin và cảnh báo mang 20 dòng cuối của log lỗi. Log runner có thể chứa tiêu đề bài, trái cam kết "chỉ siêu dữ liệu" gửi Telegram (D1). | `plan.md:280,325` | Lọc phần đuôi lỗi chỉ còn mã lỗi và lớp lỗi trước khi đưa vào outbox. |
| G18 | Nhẹ | `article_tick.py` mặc định L1 khi thiếu standing order (mã đã có từ US-028). Daemon mới về L0, nên hai đường cùng giữ `.pipeline.lock` có ngữ nghĩa mặc định ngược nhau. | `article_tick.py:259-261,279-280`; `order.py:44-47` | Khi daemon thay lịch tick, sửa mặc định của `article_tick.py` về L0 hoặc gỡ lịch của nó. |

---

## 3. Điều plan làm đúng

- **Bỏ quota guard 3M token/ngày** của hội đồng 23/09, đúng ADR 0010 §5 và ADR 0011 §5. Breaker QUOTA chỉ phản ứng khi provider báo 429. Đây là điều kiện sẵn sàng của provider, không phải trần token, nên không vi phạm. `ops.yaml` không có tham số token nào.
- **Giữ agy ở vai hàm nhận thức**, không làm vòng điều phối 24/7. Khớp ADR 0011 "Python là conductor". Lý do "điều phối viên chết cùng provider" là lý do quản trị đúng.
- **Không đổi lược đồ `monocle.db`.** `ops.db` tách riêng, ngoài OneDrive.
- **`--finish` giữ fail-loud, không tự lặp.** Cổng kỹ thuật không bị nới.
- **`pending` dùng chung `load_candidates(only_pending=True)`** với bộ chọn bài, nên code-first không được tính (`sensor.py:90`).
- **Một đợt một workflow, WIP đợt = 1, `--batch 50`** đúng ADR 0011.
- **Daemon ở L0 chỉ cảnh báo**, không mở đợt (`daemon.py:284`). Riêng đường tự chạy lại là ngoại lệ, xem G4.
- **`ops-sentinel` chỉ đề xuất**, có danh sách trắng kiểm bằng regex, không tự thi hành.
- **Lệnh của người thành sự kiện `actor=human`**, có `chat_id` whitelist, xác nhận hai bước cho `/stop`.
- **P1 "quan sát trước, tự động sau"** là thứ tự đúng.

---

## 4. Câu hỏi cho người vận hành

1. Mã `src/ops/` được viết theo yêu cầu của người hay do agent tự làm? Nếu là yêu cầu, người có chấp nhận hạ phần này xuống "spike chưa duyệt" và park US-029 cho tới khi ADR được duyệt không?
2. Câu hỏi cổng `--finish` 90% hay 100% (giữ chỗ ADR 0012 từ 24/09) đã chốt chưa? Daemon tự nạp DB ở L2 phụ thuộc trực tiếp vào câu trả lời này.
3. Standing order có phải là sự đồng ý tiêu token thay cho "lệnh tường minh" của ADR 0008 không? Nếu có, ADR mới cần sửa trạng thái ADR 0008, và đường tự chạy lại (G4) phải tuân theo.
4. Gia hạn standing order mức L2/L3 có được phép làm từ điện thoại không, hay chỉ tại máy?
5. Gửi nội dung bài sang OpenRouter đã được duyệt về dữ liệu và chi phí chưa? Nếu chưa, `failover: auto` phải bị khoá cứng.
6. `pipeline.yaml` sẽ là nguồn mà daemon đọc, hay chỉ là tài liệu được đồng bộ bằng test? Hai hướng có chi phí khác nhau.
7. Thay đổi đang dở trong `openrouter_runner.py` thuộc story nào?
