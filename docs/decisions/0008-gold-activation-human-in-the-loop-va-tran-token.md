# ADR 0008 — Kích hoạt Gold bắt buộc có người trong vòng lặp & trần token

- **Ngày:** 2026-09-17
- **Trạng thái:** **accepted** (người dùng chỉ định 2026-09-17: *"bắt buộc human phải ở trong loop
  và đưa ra permission"*)
- **Lane:** **high-risk** — kiểm soát chi phí token & quyền kích hoạt tác nhân ngoài
- **Story:** US-017 · **Tác động:** `scripts/auto_pilot.py`, `scripts/run_daily.ps1`, `src/agent/batch_handoff.py`
- **Kế hoạch:** `plans/20260917-1420-pipeline-integrity-remediation/phase-02-destructive-automation.md`

---

## 1. Bối cảnh & Vấn đề

`auto_pilot.py:80-88` gọi CLI ngoài `agy` kèm cờ **`--dangerously-skip-permissions`**:

```
agy -p <prompt> --dangerously-skip-permissions --effort low
```

Bốn vấn đề chồng lên nhau:

1. **Không có người trong vòng lặp.** Tác nhân LLM được kích hoạt tự động, tiêu thụ token của tài
   khoản người dùng mà không ai xác nhận. Cờ `--dangerously-skip-permissions` tắt luôn lớp hỏi
   quyền của chính công cụ đó.
2. **Không có trần chi phí.** Không giới hạn số batch, không ước lượng token trước khi chạy, không
   dừng khi vượt ngân sách.
3. **Thất bại im lặng, báo thành công giả.** `run_cmd` (dòng 29-31) chỉ *in* lỗi rồi đi tiếp;
   `except Exception` (dòng 89) nuốt cả `FileNotFoundError` khi thiếu `agy`; dòng 100 in
   "hoàn tất 100%" vô điều kiện. Kết hợp với lỗi va chạm tên batch (`batch_NN` đánh số lại từ 01
   mỗi lần chạy), hệ thống có thể **ingest lại dữ liệu cũ rồi báo thành công**.
4. **Không tái lập được.** `agy.exe` nằm ở `C:\Users\anpt\AppData\Local\agy\bin\`, ngoài repo, không
   pin version, không có trong `requirements.txt`.

## 2. Quyết định

### 2.1 Không kích hoạt Gold khi chưa có xác nhận tường minh của người dùng

Mọi đường dẫn dẫn tới việc gọi `agy` (hay bất kỳ runner LLM nào sau này) **bắt buộc dừng lại xin
xác nhận**, hiển thị trước:

- số batch và số bài sẽ xử lý,
- ước lượng token/chi phí,
- chế độ `--effort` sẽ dùng.

Chạy không xác nhận chỉ được phép qua cờ tường minh (ví dụ `--yes`) do người vận hành tự gõ, và
mặc định luôn là **hỏi**.

### 2.2 Bỏ cờ `--dangerously-skip-permissions` khỏi đường chạy mặc định

Cờ này chỉ được dùng khi người vận hành chủ động bật, kèm ghi log rõ ràng. Mặc định để công cụ
`agy` giữ nguyên lớp hỏi quyền của nó.

### 2.3 Trần token theo lần chạy

Thêm tham số trần (số batch tối đa và/hoặc ngân sách token ước lượng). Vượt trần thì **dừng sạch và
báo cáo phần đã làm**, theo đúng khuôn mẫu `--budget-seconds` đã áp cho `backfill_deferred` hôm nay.

### 2.4 Thất bại phải ồn ào

`run_cmd` trả mã khác 0 khi lệnh con lỗi; bỏ `except` trần; kiểm tra file output **thật sự được
sinh** trước khi coi batch là xong; dòng tổng kết phản ánh số batch thành công thật.

### 2.5 `run_daily.ps1 -Mode full` bị bỏ hẳn

`full` hiện không chạy Gold (`[ValidateSet('api')]` chặn nhánh `hierarchy`, nhánh `default` chỉ in
chữ) nhưng vẫn xoá packet. Chỉ còn `emit` và `ingest`; việc gọi tác nhân nằm ở bước giữa do người
vận hành chủ động kích hoạt theo §2.1.

### 2.6 `agy` trở thành phụ thuộc được khai báo

Pin version, ghi vào tài liệu cài đặt, và kiểm tra sự tồn tại **trước** khi chạy (thay vì để
`FileNotFoundError` bị nuốt).

## 3. Phương án đã cân nhắc

| Phương án | Vì sao không chọn |
|---|---|
| Giữ nguyên, chỉ vá va chạm batch | Không giải quyết việc token bị tiêu thụ không ai duyệt — đúng mối lo người dùng nêu |
| Thay `agy` bằng SDK trong repo | Đổi kiến trúc lớn; cần ADR riêng và chốt nhà cung cấp. Không chặn đợt vá này |
| Tự động hoàn toàn kèm trần token, không hỏi | Người dùng chỉ định rõ **bắt buộc** có người trong vòng lặp; trần token một mình không thay thế được sự đồng ý |

## 4. Hệ quả

**Tích cực:** không còn khả năng đốt token ngoài ý muốn; thất bại lộ ra ngay thay vì bị che bởi
"hoàn tất 100%"; Gold tái lập được trên máy khác.

**Tiêu cực:** Gold **không còn chạy hoàn toàn không người trực**. Đây là đánh đổi có chủ đích —
người dùng ưu tiên kiểm soát chi phí hơn tự động hoá trọn vẹn. Hàng đợi Gold sẽ dài ra trong thời
gian không có người kích hoạt; radar phải hiện rõ để không bị quên.

## 5. Nghiệm thu

| Tier | Điều kiện |
|---|---|
| Unit | Thiếu `agy` → báo lỗi rõ ràng, mã thoát khác 0, **không** nuốt |
| Unit | Hai lần gọi `split_tasks_into_batches` sinh tên batch khác nhau |
| Unit | Vượt trần batch/token → dừng sạch, báo cáo phần đã làm |
| Integration | `agy` giả lập lỗi → **không** in "hoàn tất 100%" |
| **Platform** | Chạy thật: xác nhận có bước hỏi quyền trước khi tiêu thụ token |
