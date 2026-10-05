# Phase 03 — Đường requeue cho bốn ngõ cụt trạng thái

- Parent: [plan.md](plan.md) · Ưu tiên: **P1** · Phụ thuộc: phase-01 · **Q4 đã chốt (c) — lai**
- Bằng chứng: `docs/OPEN-ITEMS.md` §A0-4

> Các kết luận dưới đây do Explore subagent báo cáo kèm số dòng; tôi **chưa tự kiểm chứng từng
> cái** như đã làm với P0. Bước đầu tiên của phase là xác minh lại trước khi sửa.

## Bốn ngõ cụt

| Trạng thái | Sinh ra khi | Vì sao kẹt |
|---|---|---|
| `work_items='failed'` | Trượt DoD Gold (`runner.py:276` → `catalog.mark_failed`) | `reclaim_stale` chỉ thu `claimed`; `claim()` chỉ chọn `pending`. Không script nào requeue |
| `l1_tasks='failed'` | Trượt DoD L1 (`l1_runner.py:140, 231`) | `upsert_l1_task` cố ý giữ status (`store.py:477-480`); `drain_code_first` chỉ lấy `pending` |
| `work_items='held'` | `silver_ok` hoặc `pkg_ok` sai (`run.py:111`) | `Catalog.enqueue` dùng `INSERT OR IGNORE` ⇒ sửa nguyên nhân xong hàng cũ vẫn không về `pending` |
| `work_items='claimed'` | Worker nhận việc | `reclaim_stale` chỉ chạy **bên trong** `claim()`; không ai claim thì treo mãi (~304 hàng) |

Hệ quả chung: sửa được nguyên nhân gốc cũng **không cứu được bài đã kẹt** — phải can thiệp SQL tay.

## Thiết kế

Theo **Q4** (khuyến nghị lai):

1. **`held` → tự động.** Nguyên nhân thường là lỗi cấu hình/schema đã sửa (đúng ca
   `deleted_at_source` vi phạm enum hôm nay). Khi derive chạy lại và lần này `pkg_ok=True`,
   `Catalog.enqueue` phải **UPSERT về `pending`** thay vì `INSERT OR IGNORE`. Kèm trần số lần để
   không quay vòng vô hạn nếu nguyên nhân chưa thật sự sửa.
2. **`failed` → theo lệnh.** Thêm `scripts/maintenance/requeue.py` với
   `--state {failed,held} --layer {l1,gold} --limit N [--dry-run]`. Trượt DoD thường là vấn đề nội
   dung thật, không nên tự động thử lại vô tội vạ.
3. **`claimed` → nhả tự động.** Đưa `reclaim_stale()` thành **job scheduler riêng** trong morninger
   (đề xuất 30 phút/lần) thay vì chỉ chạy bên trong `claim()`. Đây là lý do 304 hàng treo: không ai
   claim thì không ai nhả.
4. Đồng thời sửa `claim()` gọi `reclaim_stale()` cho **từng** item trong vòng lặp
   (`runner.py:169-173`) → N lần full-scan UPDATE. Gọi một lần trước vòng lặp.

## Việc phải làm

- Xác minh lại 4 kết luận trên bằng cách đọc trực tiếp (bước bắt buộc, xem ghi chú đầu file).
- `Catalog.enqueue`: UPSERT có điều kiện cho `held`.
- `scripts/maintenance/requeue.py` mới, mặc định `--dry-run`.
- Job `reclaim_stale` trong `morninger.build_scheduler` (theo mẫu job `l1_route` đã có).
- `pipeline_radar.py`: hiện số lượng từng trạng thái kẹt, kèm khuyến nghị lệnh requeue tương ứng.

## Nghiệm thu

| Tier | Cách chứng minh |
|---|---|
| Unit | `held` + nguyên nhân đã sửa → derive lại đưa về `pending` |
| Unit | `held` + nguyên nhân chưa sửa, lặp quá ngưỡng → dừng quay vòng |
| Unit | `requeue.py --dry-run` không đụng DB; bỏ `--dry-run` mới đổi trạng thái |
| Unit | `reclaim_stale` nhả đúng hàng `claimed` quá timeout, không đụng hàng còn hạn |
| **Platform** | Chạy morninger thật, quan sát job reclaim bắn và số `claimed` giảm trên radar |

## Rủi ro

Requeue tự động không có trần sẽ tạo vòng lặp đốt tài nguyên — đúng lỗi đã mắc với backfill hôm nay
(fetch lại URL chết mỗi 5 phút). Trần số lần thử là **bắt buộc**, không phải tuỳ chọn.
