# ADR 0014 — Giám sát multi-agent: vết ops_spans, Phòng điều khiển, Telegram giám sát, mandate tự gia hạn

- **Ngày:** 2026-10-01
- **Trạng thái:** **accepted**. Người vận hành duyệt ngày 2026-10-01 ("đồng ý thực thi toàn bộ quy trình, với các mục quyết định cần chốt đồng ý định hướng đề xuất"), theo `plans/20261001-1500-supervisor-control-room/plan.md` và các quyết định D-A đến D-E trong đó.
- **Lane:** high-risk cho phần uỷ quyền (mandate tự gia hạn); normal cho phần quan sát.
- **Story:** US-031.
- **Kế thừa và sửa đổi:** ADR 0008 (không dựng lại cổng hỏi người), ADR 0010 (token chỉ ghi nhận), ADR 0012 (ops_daemon). Mục standing order 7 ngày của ADR 0012 được thay bằng mandate ở §2.4.

## 1. Bối cảnh

Sau ADR 0012 hệ thống tự chạy trọn một đợt, nhưng người vận hành chưa thấy được các agent tương tác ra sao, mỗi bước chạy script nào, gọi công cụ nào, tốn bao nhiêu, và hỏng ở đâu. Người vận hành quyết định đổi vai: không còn bấm chấp thuận, chỉ giám sát và cải tiến quy trình.

Hiện trạng đo được: `registry.yaml` đã khai sẵn skill, entrypoint, I/O, công cụ cho phép và KPI của từng agent. Chỗ trống là bản ghi lúc chạy. Bên trong `article_run.py` mỗi khâu chỉ để lại một tệp log, và `AgyRunner` đọc được `tool_invoked` cùng `denied_actions` nhưng bỏ đi sau khi phân loại lỗi. Bảng `agent_metrics` chưa có dòng nào.

## 2. Quyết định

### 2.1 Hai lớp dữ liệu

- **Bản đồ tĩnh** từ `registry.yaml` và `pipeline.yaml`: ai tồn tại, class, skill, đọc ghi ở đâu, công cụ được phép.
- **Vết lúc chạy** trong bảng `ops_spans` của `ops.db`. Một đợt là một cây span: `workflow` → `step` → `script`, `agent`, `gate`. `trace_id` là mã đợt, `actor_id` khớp id trong registry, thuộc tính gồm model, token, độ trễ, `tool_invoked`, `denied_actions`, `prefix_hash`, số lần thử. Trường tương thích OpenTelemetry để đẩy sang Phoenix hay Langfuse sau này mà không đổi mã tạo span (D-C).
- Mã tạo span (`src/ops/trace.py`) **không làm gì khi thiếu biến môi trường** `OPS_TRACE_DB`, `OPS_TRACE_WAVE`, `OPS_TRACE_PARENT`. Chạy tay `article_run.py` không ghi gì và không đổi hành vi. Mọi lỗi ghi vết bị nuốt: vết hỏng không bao giờ làm hỏng đợt.
- Span có mã cố định theo (đợt, lần thử, bước), nên workflow chạy lại sau crash ghi đè thay vì nhân bản.
- Điểm đặt span: từng step trong `wave_flow`; từng khâu trong `article_run.py` (đóng gói, bung, nạp L1, nạp Gold, hậu kiểm, sổ cái, bàn giao); từng lô trong `AgyRunner`. Chỉ `AgyRunner` được đặt span; runner OpenRouter và adapter OpenCode chưa được đo.
- KPI từng tác nhân ghi vào `agent_metrics` của `harness.db` khi đợt chốt, rút từ vết. Khi `resolve_paths` nhận thư mục chỉ định tường minh (kiểm thử), KPI ghi vào thư mục đó, không đụng `harness.db` thật.

### 2.2 Phòng điều khiển

Một máy chủ HTTP trong daemon, `ThreadingHTTPServer`, không thêm thư viện, chỉ nghe `127.0.0.1` (D-B: chưa truy cập từ xa). Năm màn: Toàn cảnh, Đợt, Tác nhân, Sự cố, Cải tiến.

- Chỉ nhận yêu cầu có header `Host` là địa chỉ cục bộ (chống DNS rebinding).
- Thao tác ghi duy nhất là quyết định đề xuất cải tiến, và cần mã thông hành sinh mới mỗi lần khởi động, do trang tự nhúng.
- Máy chủ tắt `SO_REUSEADDR`: trên Windows tuỳ chọn này cho phép hai tiến trình bind chung một cổng, khác với Linux. Cổng bị chiếm thì Phòng điều khiển bỏ qua, daemon vẫn chạy.
- Dữ liệu chỉ đọc từ `ops.db`; không có nguồn sự thật thứ hai.

### 2.3 Telegram đổi vai

Hết nút chấp thuận từng đợt. Đợt bình thường chỉ vào bản tin tổng hợp (`alerts.push_wave_info: false`); tin riêng chỉ khi ngoại lệ. Bản tin 08:00 và 18:00 liệt kê từng tác nhân (span, tỷ lệ thành công, token, độ trễ), điểm khác thường (lệch quá 2 độ lệch chuẩn so với 7 ngày, tối thiểu 5 đợt, D-D) và số đề xuất đang mở. Lệnh mới: `/map`, `/trace`, `/agent`, `/mandate`, `/improve`, `/prop`.

### 2.4 Mandate tự gia hạn có điều kiện (D-A)

Standing order 7 ngày của ADR 0012 được thay bằng mandate 30 ngày. Khi còn dưới 7 ngày và hệ thống khoẻ, daemon gia hạn thêm 30 ngày và ghi sự kiện `mandate.renewed`. Điều kiện khoẻ, kiểm mỗi 10 phút:

1. không có sự kiện mức đỏ trong 24 giờ;
2. chuỗi đợt sạch ≥ 5;
3. không có chuỗi đợt hỏng;
4. không có lượt gọi công cụ trái Zero-Tool trong 7 ngày.

Không đủ điều kiện thì **dừng gia hạn**, báo lý do và để hạn tự cạn về L0. Hai điều không đổi: mandate chưa từng cấp hoặc đã hết hạn **không bao giờ tự cấp lại** (đó là hành động của người, `/level L1`), và `/stop` luôn thu hồi được. Lệnh nâng quyền vẫn cần bấm xác nhận lần hai (ADR 0012).

Điều này không dựng lại cổng hỏi người, đúng tinh thần amendment ADR 0008. Nó thay một chốt an toàn có tính thời gian bằng chốt có tính điều kiện, nên cần ADR này.

### 2.5 Hộp thư cải tiến (D-E)

Tác nhân mới `improvement-proposer` (operator, 0 token) quét vết và KPI mỗi giờ bằng các bộ phát hiện tất định: lượt đầu thiếu bài và token ở bước vá, bộ nhớ đệm không được dùng lại, vi phạm Zero-Tool, breaker mở lặp, bài hết lượt thử, dead-letter tăng. Tối đa 5 đề xuất mới mỗi tuần; đề xuất Hoãn hoặc Bác không nêu lại trong 30 ngày; vi phạm bất biến luôn xếp đầu.

Đề xuất **không bao giờ tự thi hành**. Chỉ **Mở story** mới gọi `harness_cli intake` và `story add` (`US-IMP-nnn`, `planned`). Bộ phát hiện chỉ đo, không sinh nội dung ngữ nghĩa, nên không vi phạm quy tắc cấm script giả lập agent.

## 3. Những gì không làm

- **`harness-auditor` chưa lên active.** Plan dự kiến, nhưng đó là agent LLM và rule 07 đòi bằng chứng kích hoạt chưa có. Đề xuất do operator tất định sinh ra thay thế.
- **Chưa truy cập từ xa** (D-B). Telegram `/map` và `/trace` lo nhu cầu xem nhanh.
- **Chưa có Phoenix hay Langfuse** (D-C), chỉ giữ sẵn tương thích.
- **Chưa cấp mandate.** Daemon ở L0 cho tới khi người vận hành gõ `/level L1` và xác nhận.
- **Nghiệm thu P0 bằng đợt thật qua daemon chưa có** tại thời điểm viết. Vết được kiểm bằng test với tiến trình giả và AgyRunner giả. Đợt thật đầu tiên sau khi bật L1 là bằng chứng còn thiếu.

## 4. Hệ quả

- Tăng hai lần ghi `ops.db` cho mỗi span; ghi theo bước và theo lô, không theo bài.
- Sensor không còn đo khi đang có đợt, và không đọc cột nội dung, để giám sát không cạnh tranh với đợt.
- Cổng nạp, bất biến token chỉ ghi nhận và quy tắc "một đợt, một chương trình" không đổi.

## 5. Quay lui

`control_room.enabled: false` trong `config/ops.yaml` tắt Phòng điều khiển. Xoá biến môi trường `OPS_TRACE_*` (hoặc không đặt) thì mã tạo span ngừng ghi. `alerts.push_wave_info: true` trả lại tin riêng cho từng đợt. Mandate quay về hạn cố định bằng cách đặt `autonomy.renew_when_days_left: -1`.
