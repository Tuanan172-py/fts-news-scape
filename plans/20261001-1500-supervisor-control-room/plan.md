# Phòng điều khiển giám sát: người vận hành chỉ giám sát và cải tiến quy trình

- **Ngày:** 2026-10-01
- **Trạng thái:** đã duyệt và triển khai P0–P4 ngày 2026-10-01 (ADR 0014, US-031). Còn treo: nghiệm thu P0 bằng đợt thật, `harness-auditor` active, truy cập từ xa; xem `docs/OPEN-ITEMS.md` OPS-2.
- **Lane:** phần quan sát (P0–P3) là normal. Phần uỷ quyền tự gia hạn (P4) là high-risk, cần ADR riêng và người duyệt trước khi code.
- **Kế thừa:** ADR 0008 (không dựng cổng hỏi người), ADR 0010 (Article Lane duy nhất, token chỉ ghi nhận), ADR 0011 (agy headless), ADR 0012 (ops_daemon), `.agents/registry.yaml`, `.agents/pipeline.yaml`.
- **Quyết định đầu vào của người vận hành (2026-10-01):** quy trình agy headless được giữ nguyên. Người chỉ còn giám sát và cải tiến quy trình; không còn bấm chấp thuận từng đợt.

---

## 0. Tóm tắt

Hệ thống đã tự chạy trọn một đợt. Thứ còn thiếu là **tầm nhìn**: người vận hành chưa thấy được các agent tương tác ra sao, mỗi bước chạy script nào, gọi công cụ nào, tốn bao nhiêu, và đã hỏng ở đâu.

Thiết kế gồm ba phần:

1. **Hai lớp dữ liệu.** *Bản đồ* tĩnh dựng từ `registry.yaml` và `pipeline.yaml` (ai tồn tại, skill nào, đọc ghi ở đâu, công cụ được phép). *Vết* động ghi lúc chạy vào bảng `ops_spans` (ai đã chạy, lúc nào, kết quả, token). Hai lớp chồng lên nhau thành một sơ đồ sống.
2. **Phòng điều khiển (Control Room).** Một trang web cục bộ do daemon phục vụ, không cần phụ thuộc mới: toàn cảnh, đợt và cây vết, từng tác nhân, sự cố, cải tiến.
3. **Telegram đổi vai.** Thôi làm nơi bấm chấp thuận; thành nơi báo ngoại lệ, bản tin giám sát và tra nhanh `/map`, `/trace`.

Người vận hành chỉ còn hai việc: xem toàn cảnh khi muốn, và duyệt các đề xuất cải tiến trong hộp thư cải tiến.

---

## 1. Hiện trạng đo được

| Thành phần | Có gì | Thiếu gì |
|---|---|---|
| Bản đồ tác nhân | `registry.yaml` khai sẵn mỗi agent: `class`, `skill`, `entrypoint`, `io_boundary.read/write`, `tools_allowed`, `kpis`. `pipeline.yaml` khai các cạnh `needs` | Chưa có công cụ nào vẽ ra |
| Vết lúc chạy | `ops_events` ghi mức bước (`step.started`, `batch.done`, `wave.done`) | Không có cây cha con. Bên trong `article_run.py` (đóng gói, bung, nạp DoD, hậu kiểm, sổ cái) chỉ để lại một tệp log |
| Công cụ agent gọi | `AgyRunner` đọc được `tool_invoked` và `denied_actions` từng lô | Giá trị này bị bỏ đi sau khi phân loại, không lưu |
| Token | `token_ledger` trong `harness.db` | Không gắn với từng span; `agent_metrics` chưa có dòng nào |
| Tương tác giữa agent | Daemon gọi tuần tự, agy chạy song song theo lô | Không thấy được thứ tự, độ chồng lấn, thời gian chờ |
| Kênh người | Telegram, `ops_console.py` | Cả hai chỉ có danh sách sự kiện phẳng |

**Điều cần nói thẳng về "skill" và "tool".** Agent chạy lúc vận hành không nạp skill động: `article-processor` mang skill dưới dạng persona cố định (`ARTICLE_SYSTEM_CORE.md`, có `prefix_hash`), và khai `tools: []`. Vì vậy cột "skill" trong Phòng điều khiển là *skill khai trong registry cho agent đó*, và cột "công cụ" trả lời câu hỏi giám sát đúng: số lượt gọi công cụ phải bằng 0, và mọi lượt bị hook từ chối được đếm là vi phạm. Skill governance (`dod-gatekeeper`, `token-auditor`, `harness-auditor`) là skill của phiên tương tác, không chạy trong đợt; chúng xuất hiện ở lớp *cải tiến*, không ở lớp vết.

---

## 2. Kiến trúc đích

```
 registry.yaml + pipeline.yaml ──► BẢN ĐỒ (tĩnh) ─────────────┐
                                                               ▼
 ops_daemon ─┐                                          ┌──────────────┐     ┌─ Control Room (web, 127.0.0.1)
 article_run ┼─ span(...) ──► ops.db / ops_spans ──────►│  API đọc     │────►│   toàn cảnh · đợt · cây vết
 AgyRunner  ─┤   (OPS_TRACE_WAVE trong env, không có   │ /api/state   │     │   tác nhân · sự cố · cải tiến
 ingest/gates┘    thì không làm gì)                     │ /api/trace   │     └─ Telegram: ngoại lệ, bản tin,
                                                        └──────────────┘        /map, /trace
 harness.db (token_ledger, agent_metrics, backlog) ───────────────────────► vòng cải tiến
```

Nguyên tắc: **một nguồn sự thật** (`ops.db`), mọi mặt giám sát chỉ đọc. Mã tạo span không có tác dụng phụ khi chạy tay (thiếu biến môi trường thì bỏ qua), nên không đổi hành vi của `article_run.py` đang chạy.

### 2.1 Mô hình vết `ops_spans`

```
ops_spans(span_id, trace_id,          -- trace_id = mã đợt
          parent_id, kind,            -- workflow | step | script | agent | tool | gate | human
          name, actor_id,             -- actor_id khớp id trong registry.yaml
          skill, entrypoint,          -- sao chép từ registry lúc ghi
          started_at, ended_at, status,   -- ok | fail | timeout | skipped
          attrs_json,                 -- model, batch, n_items, tokens_in/out, tool_calls,
                                      -- denied_actions, rc, prefix_hash, attempt
          input_ref, output_ref)      -- đường dẫn tệp hoặc "bảng:số dòng"
```

Trường tương thích OpenTelemetry (trace, span, parent, thời gian, thuộc tính) để sau này đẩy sang Phoenix hay Langfuse mà không đổi mã nguồn tạo span.

### 2.2 Điểm đặt span (rẻ, không đổi logic)

| Điểm | Span tạo ra |
|---|---|
| `wave_flow` mỗi step | `step` (đã có sự kiện, thêm cha con) |
| `article_run.py` | `script` cho từng khâu: `article_pack`, `article_expand`, `l1_ingest`, `agent_ingest`, `verify_wave`, `token_ledger`, `handoff` |
| `AgyRunner.run_batch` | `agent` cho từng lô, với `attrs` lấy từ `meta.json`: token, độ trễ, số lần thử, `tool_invoked`, `denied_actions`, `prefix_hash` |
| `check_dod`, `check_l1_dod`, `verify_wave` | `gate` kèm số bài đạt, trượt, lý do trượt thường gặp |
| `commands.execute` | `human` (đã có `human.command`) |
| `ops-sentinel` | `agent` với đề xuất và kết quả |

---

## 3. Phòng điều khiển

Một tiến trình HTTP trong daemon (`ThreadingHTTPServer`, chỉ nghe `127.0.0.1`), một tệp HTML tĩnh và vài đường JSON. Không thêm thư viện.

| Màn | Trả lời câu hỏi | Nội dung |
|---|---|---|
| **Toàn cảnh** | Hệ thống có đang khoẻ và đang làm gì không | Dải trạng thái (daemon, cào tin, mandate còn bao ngày, breaker, bài chờ, tuổi bài chờ lâu nhất). Bản đồ agent sống: nút là agent trong registry, cạnh là `needs` và luồng dữ liệu, màu theo trạng thái, huy hiệu số bài và token trong ngày |
| **Đợt** | Một đợt đã diễn ra thế nào | Danh sách đợt; chọn một đợt thì ra biểu đồ Gantt các span và cây vết. Mỗi nút cây hiện: actor, skill, entrypoint, công cụ gọi, token, thời gian, đầu vào và đầu ra |
| **Tác nhân** | Từng agent đang ra sao | Thẻ agent: đặc tả từ registry (class, skill, model, `tools_allowed`, `io_boundary`), xu hướng KPI 7 ngày, các span gần nhất, vi phạm |
| **Sự cố** | Có gì bất thường | Trạng thái breaker, probe, dòng thời gian sự cố, chẩn đoán của sentinel và kết cục |
| **Cải tiến** | Nên đổi gì ở quy trình | Hộp thư đề xuất (xem §5), xu hướng KPI, liên kết tới story và ADR |

Truy cập: máy bàn qua `http://127.0.0.1:<cổng>`; phím tắt hiện có (`Ctrl+Alt+O`) mở thêm trang này. Truy cập từ điện thoại ngoài mạng cần một đường hầm công khai, thuộc chính sách CNTT và nằm ngoài P0–P3 (xem §7, D-B).

---

## 4. Telegram đổi vai

| Trước | Sau |
|---|---|
| Nút **Chạy đợt**, **Nạp DB**, gia hạn standing order | Không còn việc nào cần chấp thuận từng đợt. L1 chạy tự động |
| Mỗi đợt xong một tin | Đợt bình thường chỉ vào bản tin tổng hợp. Tin riêng chỉ khi ngoại lệ |
| Bản tin 08:00 và 18:00 liệt kê số đếm | Bản tin giám sát: mỗi agent một dòng (số span, tỷ lệ ok, token, độ trễ), kèm các điểm khác thường so với 7 ngày |
| `/status`, `/waves`, `/log` phẳng | Thêm `/map` (sơ đồ chữ trạng thái từng agent), `/trace <đợt>` (cây vết dạng chữ), `/agent <id>` |

Ngân sách chuông: 0 tin có chuông khi mọi thứ bình thường; 1 tin khi một ngoại lệ mới xuất hiện (daemon chết lúc máy mở, mất đăng nhập agy, đợt FAILED hai lần liên tiếp, KPI vượt ngưỡng lệch).

---

## 5. Vòng cải tiến

Người vận hành đóng vai người cải tiến quy trình, nên cần một đường vào có bằng chứng:

1. Mỗi đợt ghi một dòng `agent_metrics` cho từng agent: `parse_fail_rate`, `repair_rate`, `dod_pass_rate`, `resolve_rate`, token mỗi bài, độ trễ, số lần thử lại. (Hiện bảng này trống.)
2. `harness_cli propose` và agent `harness-auditor` (draft) đọc xu hướng, `friction_backlog` và vết, rồi sinh đề xuất kèm bằng chứng: lô nào, đợt nào, chỉ số nào.
3. Hộp thư cải tiến liệt kê đề xuất. Mỗi đề xuất có ba nút: **Mở story**, **Hoãn**, **Bác**. Chỉ **Mở story** mới đi tiếp vào quy trình story, intake và ADR của repo.
4. Đề xuất tự sinh **không bao giờ tự thi hành**. Đây là chỗ người vận hành giữ quyền.

---

## 6. Lộ trình (WIP = 1, mỗi phase một story, có bằng chứng)

| Phase | Nội dung | Lane | Bằng chứng nghiệm thu |
|---|---|---|---|
| **P0** Vết | Bảng `ops_spans`, `src/ops/trace.py` (no-op khi thiếu env), đặt span ở `wave_flow`, `AgyRunner`, các khâu của `article_run`. Chưa có giao diện | normal | Một đợt thật cho ra cây vết đầy đủ trong DB. Chạy tay `article_run.py` không ghi gì. Test có tên mã |
| **P1** API và Toàn cảnh | Máy chủ HTTP cục bộ, `/api/state`, bản đồ sống dựng từ registry + trạng thái | normal | Mở trang thấy mọi agent `active` đúng như registry; một đợt chạy thì nút đổi màu theo thời gian thực |
| **P2** Đợt và Tác nhân | Gantt, cây vết, thẻ agent, KPI 7 ngày; ghi `agent_metrics` mỗi đợt | normal | Từ một tin "Đợt xong" lần ra đúng cây vết; KPI khớp `token_ledger` |
| **P3** Telegram giám sát | Bản tin giám sát, ngoại lệ có chuông, `/map`, `/trace`, `/agent`; bỏ nút chấp thuận từng đợt | normal | Một ngày chạy: 0 tin có chuông khi bình thường; ngoại lệ giả lập ra đúng một tin |
| **P4** Mandate và cải tiến | Uỷ quyền tự gia hạn có điều kiện (D-A); hộp thư cải tiến; `harness-auditor` lên active theo rule 07 | **high-risk** | ADR riêng được duyệt; 7 ngày không cần người bấm gì mà không có sự cố bị bỏ sót |

---

## 7. Quyết định cần người vận hành chốt

| # | Câu hỏi | Đề xuất |
|---|---|---|
| D-A | Standing order hiện hết hạn sau 7 ngày và phải gia hạn tay. Giữ, hay đổi thành **mandate tự gia hạn khi hệ thống khoẻ**? | Mandate 30 ngày, tự gia hạn khi đủ điều kiện (không có sự cố mức đỏ trong 24 giờ, chuỗi đợt sạch ≥ 5, không vi phạm tool). Có sự cố đỏ thì dừng gia hạn và về L0. Người vẫn thu hồi được bằng `/stop`. Đổi này là thay một chốt an toàn nên cần ADR (P4) |
| D-B | Có cần xem Phòng điều khiển từ điện thoại ngoài văn phòng không? | Chưa. P0–P3 chỉ cục bộ. Telegram `/map`, `/trace` đã trả lời được nhu cầu xem nhanh. Nếu cần, hỏi CNTT về đường hầm có xác thực (Telegram Mini App cũng đòi URL HTTPS công khai) |
| D-C | Dùng giao diện tự viết hay công cụ có sẵn (Arize Phoenix qua OpenTelemetry)? | Tự viết trước: dữ liệu đã nằm trong `ops.db`, không thêm hạ tầng, và cây vết có cột riêng của dự án (skill, entrypoint, cổng DoD). Giữ span tương thích OpenTelemetry để thử Phoenix sau bằng một spike nhỏ |
| D-D | Ngưỡng "khác thường" trong bản tin giám sát | Lệch hơn 2 độ lệch chuẩn so với 7 ngày gần nhất, tối thiểu 5 đợt dữ liệu |
| D-E | Hộp thư cải tiến cho phép tự sinh đề xuất bao nhiêu mỗi tuần | Tối đa 5, xếp theo tác động đo được |

---

## 8. Rủi ro đã biết

- **Giám sát làm chậm chính hệ thống.** Ghi span vào `ops.db` ở nhịp mỗi bước và mỗi lô, không ghi theo bài. Máy chủ HTTP chỉ đọc. Đợt đo ở P0: thời gian đợt không tăng quá 2%.
- **Hai nguồn sự thật.** Tránh bằng cách mọi giao diện chỉ đọc `ops_spans`; `ops_events` giữ vai nhật ký người đọc.
- **Giao diện cho người cảm giác kiểm soát giả.** Trang chỉ hiện những gì đo được. Chỗ không đo được (ví dụ chất lượng tóm tắt) phải hiện "chưa đo", không hiện số đẹp. Golden set vẫn là việc nợ.
- **Bài tồn đọng ngoài phạm vi tự động** (khoảng 10,9 nghìn bài) hiện không có trong tầm nhìn; Toàn cảnh phải hiện con số này để không bị quên.
