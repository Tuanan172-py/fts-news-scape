# Phase 02 — Chặn tự động hoá phá hoại (`run_daily.ps1` + AutoPilot)

- Parent: [plan.md](plan.md) · Ưu tiên: **P0** · **Q6, Q7 đã chốt** — không còn chặn
- Quyết định: **bỏ hẳn `-Mode full`**; Gold **bắt buộc có người cấp quyền tường minh** trước khi
  tiêu thụ token; bỏ `--dangerously-skip-permissions` khỏi đường mặc định
- **Hard Gate đã duyệt:** [ADR 0008](../../docs/decisions/0008-gold-activation-human-in-the-loop-va-tran-token.md)
- Bằng chứng: `docs/OPEN-ITEMS.md` §A0-2, §A0-3

## 2a. `run_daily.ps1` xoá packet chưa xử lý

`CleanPackets` (dòng 138) quét `data/agent_tasks` với `-Recurse -Filter '*.task.json'` rồi xoá
**tất cả**, kể cả packet trong `l1/` chưa ai chạm tới. Hiện có **163 packet L1** sẽ bị xoá trắng.

Đồng thời `-Mode full` không hề chạy Gold: `[ValidateSet('api')]` (dòng 19) khiến nhánh
`'hierarchy'` (dòng 108-110) không bao giờ tới được, nhánh `default` chỉ in hướng dẫn. Chuỗi `full`
= xuất packet → in chữ → ingest khi chưa có output → **xoá sạch packet vừa xuất**.

**Việc phải làm:**

1. `CleanPackets` chỉ được xoá packet **đã hoàn tất**: đối chiếu `l1_tasks.status='done'` /
   `agent_outputs` đã ingest / đã archive. Packet không có bằng chứng hoàn tất thì **giữ lại**.
   Đây là thay đổi cấu trúc — sau khi sửa, việc xoá nhầm phải là *không thể*, không chỉ là
   *khó xảy ra*.
2. Mặc định đảo chiều: giữ packet là mặc định, muốn xoá phải khai `-CleanPackets` tường minh
   (hiện đang ngược: `-KeepPackets` mới giữ).
3. **Bỏ hẳn `-Mode full`** (Q7a). Chỉ còn `emit` và `ingest`; việc gọi tác nhân nằm ở bước giữa,
   do người vận hành chủ động kích hoạt theo ADR 0008.
4. Gỡ luôn nhánh `'hierarchy'` chết (`ValidateSet` chặn nên không bao giờ tới được) thay vì để lại
   code không thể chạy.

## 2b. AutoPilot va chạm tên batch

`auto_pilot.py:66-72` bỏ qua batch nếu `<batch>.output.json` đã tồn tại, nhưng
`split_tasks_into_batches` (`src/agent/batch_handoff.py:173-179`) **đánh số lại từ `batch_01` mỗi
lần chạy**. Thực trạng đã kiểm chứng: `data/agent_outputs/` có `batch_01`–`batch_02` (17/09) lẫn
`batch_03`–`batch_11` (**14/09**). Lần chạy tới sẽ skip toàn bộ batch mới, ingest lại dữ liệu 3 ngày
trước, rồi in "hoàn tất 100%".

**Việc phải làm:**

1. Tên batch phải **duy nhất theo lần chạy**: `batch_<YYYYMMDDTHHMM>_<NN>`. Sau đó cơ chế "skip nếu
   output đã tồn tại" mới đúng nghĩa idempotent thay vì va chạm.
2. AutoPilot phải **archive hoặc dọn** `data/agent_outputs/` sau khi ingest thành công — hiện không
   bao giờ dọn nên rò rỉ vĩnh viễn.
3. `run_cmd` (dòng 29-31) phải **raise / trả mã khác 0** khi lệnh con lỗi. Hiện chỉ *in* lỗi rồi đi
   tiếp, và `except Exception` (dòng 89) nuốt cả `FileNotFoundError` khi thiếu `agy`.
4. Thêm timeout cho mỗi lần gọi agent, và **kiểm tra file output thật sự được sinh** trước khi coi
   batch là xong.
5. Dòng tổng kết không được in "hoàn tất 100%" vô điều kiện (dòng 100) — phải phản ánh số batch
   thật sự thành công.
6. **Cổng cấp quyền (Q6 / ADR 0008 §2.1)** — phần người dùng nhấn mạnh nhất. Trước khi gọi `agy`,
   AutoPilot **bắt buộc dừng lại hiển thị và xin xác nhận**:
   - số batch + số bài sẽ xử lý,
   - ước lượng token/chi phí,
   - chế độ `--effort` sẽ dùng.

   Mặc định luôn là **hỏi**. Chỉ chạy thẳng khi người vận hành tự gõ cờ tường minh (`--yes`).
7. **Bỏ `--dangerously-skip-permissions`** khỏi lệnh mặc định (ADR 0008 §2.2); chỉ bật khi người
   vận hành chủ động yêu cầu, kèm ghi log rõ.
8. **Trần token/batch theo lần chạy** (ADR 0008 §2.3) — vượt trần thì dừng sạch và báo cáo phần đã
   làm, theo đúng khuôn mẫu `--budget-seconds` đã áp cho `backfill_deferred`.
9. Kiểm tra `agy` **tồn tại trước khi chạy**; pin version và ghi vào tài liệu cài đặt (ADR 0008 §2.6).
10. `PYTHON_EXEC` hardcode (dòng 22) khác logic dò python của `run_daily.ps1:67-77` — thống nhất một
    nguồn.

## Dọn dẹp trạng thái hiện tại

`data/agent_outputs/batch_03..11.output.json` là dữ liệu **14/09 đã ingest xong**. Trước khi bật lại
AutoPilot phải archive chúng đi, nếu không lỗi va chạm vẫn tái diễn dù đã sửa cách đánh số.
**Thao tác xoá/di chuyển file dữ liệu — cần anh xác nhận trước khi thực hiện.**

## Nghiệm thu

| Tier | Cách chứng minh |
|---|---|
| Unit | `CleanPackets` giữ nguyên packet chưa hoàn tất, chỉ xoá packet đã done |
| Unit | Hai lần gọi `split_tasks_into_batches` liên tiếp sinh tên khác nhau |
| Unit | `run_cmd` gặp lệnh lỗi → trả mã khác 0, không nuốt |
| Integration | AutoPilot với `agy` giả lập lỗi → báo thất bại, **không** in "hoàn tất 100%" |
| **Platform** | Chạy `run_daily.ps1 -Mode emit` rồi kiểm 163 packet L1 còn nguyên |

## Rủi ro

Sửa `CleanPackets` sai chiều sẽ khiến packet không bao giờ được dọn → phình đĩa. Cần test cả hai
chiều: packet done **phải** bị xoá, packet chưa done **phải** được giữ.
