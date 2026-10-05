# Phase 01 — Watermark Silver: chặn mất bài vĩnh viễn

- Parent: [plan.md](plan.md) · Ưu tiên: **P0** · **Q2 đã chốt** — không còn chặn
- Quyết định: bảng **`silver_failures`** riêng, ngưỡng **5 lần thử** → dead-letter
- **Hard Gate đã duyệt:** [ADR 0007](../../docs/decisions/0007-silver-watermark-integrity-va-bang-silver-failures.md)
- Bằng chứng: `docs/OPEN-ITEMS.md` §A0-1

## Vấn đề

`project/src/pipeline/derive.py`:

```python
def _should_process(fetch_ts, watermark):     # dòng 51-57
    return fetch_ts > watermark

watermark_new = max(ok_ts) if ok_ts else watermark    # dòng 130 — max của CHỈ bài thành công
```

Bài lỗi (`continue` dòng 115-117, `raw_missing`, `raw_read_error`) không góp vào `ok_ts`. Nếu file A
(`fetch_ts` 10:00) lỗi còn file B (11:00) thành công, watermark nhảy lên 11:00 và **A vĩnh viễn
không bao giờ thoả `> watermark`**. Không cảnh báo, không retry, không dead-letter — chỉ một dòng log.

Đây là lý do mọi nỗ lực "không bỏ sót" ở Bronze bị vô hiệu: Bronze giữ đủ bài, Silver lặng lẽ đánh rơi.

## Thiết kế

Watermark chuyển sang ngữ nghĩa **low-water mark**: không bao giờ vượt qua lỗi chưa giải quyết.

```
watermark_new = min(fetch_ts của các lỗi CHƯA dead-letter)   nếu có lỗi
              = max(ok_ts)                                    nếu sạch
```

Rủi ro ngược là head-of-line blocking: một file hỏng vĩnh viễn chặn đứng Silver. Nên bắt buộc có sổ
lỗi kèm ngưỡng bỏ cuộc. **Q2 đã chốt: bảng `silver_failures` riêng, ngưỡng 5 lần** (ADR 0007 §2.2):

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `meta_path` | TEXT PK | Đường dẫn `.meta.json`, tương đối theo `PROJECT_ROOT` |
| `url_title_hash` | TEXT | Liên kết về `articles` khi xác định được |
| `fetch_ts` | TEXT | Mốc dùng để chặn watermark |
| `attempts` | INTEGER | Tăng mỗi chu kỳ derive |
| `last_error` | TEXT | Thông điệp lỗi gần nhất |
| `last_at` | TEXT | ISO `+07:00` |
| `dead_letter` | INTEGER | 0/1 — khi 1 thì thôi chặn watermark |

- Mỗi chu kỳ derive: file lỗi tăng `attempts`; file thành công **bị xoá khỏi bảng** (không để rác).
- `attempts >= 5` → **dead-letter**: ngừng chặn watermark, log mức ERROR, và **hiện trên radar**
  (bắt buộc — dead-letter im lặng là quay lại đúng lỗi đang sửa).

## Việc phải làm

1. `derive.py` — thay công thức watermark; đọc/ghi `silver_failures`; xoá hàng khi bài thành công.
2. `store.py` — `CREATE TABLE IF NOT EXISTS silver_failures` (không đụng bảng cũ, không mất dữ liệu).
   **Sao lưu `monocle.db` trước lần chạy đầu** (ADR 0007 §4.3).
3. `pipeline_radar.py` — thêm dòng "Bài Bronze kẹt/dead-letter ở Silver: N", kèm khuyến nghị
   `HIGH` khi N > 0. Không có dòng này thì coi như chưa xong phase.
4. Sửa luôn nghịch lý `silver_ok=False` nhưng `pkg_ok=True` vẫn trả `ok=True` (`run.py:122`) — bài
   như vậy hiện vẫn đẩy watermark qua nó nên không bao giờ được derive lại.

## Nghiệm thu

| Tier | Cách chứng minh |
|---|---|
| Unit | File lỗi có `fetch_ts` cũ hơn file thành công: chu kỳ sau **vẫn** được chọn lại (test này hiện fail trên code cũ) |
| Unit | Đủ ngưỡng lần thử → vào dead-letter, watermark được phép tiến |
| Unit | File thành công bị xoá khỏi sổ lỗi, không kẹt lại |
| Integration | Tạo Bronze hỏng xen kẽ Bronze tốt, chạy `rederive_incremental` nhiều lượt, khẳng định không bài nào biến mất |
| **Platform** | Chạy trong morninger thật, quan sát log 2 chu kỳ derive liên tiếp + radar hiện số dead-letter |

## Rủi ro

- **Head-of-line blocking** nếu ngưỡng đặt quá cao hoặc sổ lỗi hỏng → Silver đứng im. Giảm thiểu:
  log ERROR mỗi khi watermark bị chặn quá 2 chu kỳ liên tiếp.
- **Backlog dồn**: lần chạy đầu sau khi sửa có thể lôi lại nhiều bài cũ từng bị bỏ qua. Cần chạy
  thử với `--dry-run` hoặc trên bản sao DB trước để biết khối lượng.
