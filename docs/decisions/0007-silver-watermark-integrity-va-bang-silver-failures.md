# ADR 0007 — Toàn vẹn watermark Silver & bảng `silver_failures`

- **Ngày:** 2026-09-17
- **Trạng thái:** **accepted** (người dùng duyệt hướng đi 2026-09-17; ADR lập theo AGENTS.md §0 Cấp 3)
- **Lane:** **high-risk** — đổi schema `monocle.db` (Hard Gate)
- **Story:** US-016 · **Tác động:** `src/pipeline/derive.py`, `src/pipeline/run.py`, `src/db/store.py`, `scripts/pipeline_radar.py`
- **Kế hoạch:** `plans/20260917-1420-pipeline-integrity-remediation/phase-01-silver-watermark-integrity.md`

---

## 1. Bối cảnh & Vấn đề

Rà soát end-to-end 2026-09-17 phát hiện **mất dữ liệu âm thầm** ở tầng Silver.

`src/pipeline/derive.py`:

```python
def _should_process(fetch_ts, watermark):     # dòng 51-57
    return fetch_ts > watermark

watermark_new = max(ok_ts) if ok_ts else watermark    # dòng 130 — max của CHỈ bài thành công
```

Bài lỗi (`continue` dòng 115-117, `raw_missing`, `raw_read_error`) không góp vào `ok_ts`. Nếu file A
có `fetch_ts` 10:00 bị lỗi còn file B 11:00 thành công, watermark nhảy lên 11:00 và **A vĩnh viễn
không bao giờ thoả `> watermark`** nữa. Không cảnh báo, không đếm số lần thử, không dead-letter —
chỉ một dòng log rồi đi tiếp.

Thêm một đường rò nữa: bài `silver_ok=False` nhưng `pkg_ok=True` vẫn trả `res["ok"]=True`
(`run.py:122`) nên watermark vẫn đẩy qua, và bài đó không bao giờ được derive lại.

**Hệ quả nghiêm trọng về mặt kiến trúc:** toàn bộ nỗ lực "không bỏ sót bài tin" ở tầng Bronze
(US-011, US-012, US-015) bị vô hiệu ngay tầng kế tiếp. Bronze giữ đủ bài, Silver lặng lẽ đánh rơi,
và bài đã rơi thì không bao giờ tới L1, Gold hay tay người dùng. Số đo liên quan: 7.203 bài đã cào,
424 bài qua cổng giao hàng.

## 2. Quyết định

### 2.1 Watermark chuyển sang ngữ nghĩa low-water mark

```
watermark_new = min(fetch_ts của các lỗi CHƯA dead-letter)   nếu còn lỗi
              = max(ok_ts)                                    nếu sạch
```

Watermark **không bao giờ vượt qua một lỗi chưa được giải quyết**.

### 2.2 Bảng mới `silver_failures` (đổi schema — Hard Gate)

Rủi ro ngược của 2.1 là head-of-line blocking: một file hỏng vĩnh viễn chặn đứng Silver. Nên bắt
buộc có sổ lỗi bền vững kèm ngưỡng bỏ cuộc.

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `meta_path` | TEXT PK | Đường dẫn `.meta.json` (tương đối theo `PROJECT_ROOT`) |
| `url_title_hash` | TEXT | Liên kết về `articles` khi xác định được |
| `fetch_ts` | TEXT | Mốc thời gian dùng để chặn watermark |
| `attempts` | INTEGER | Số lần đã thử, tăng mỗi chu kỳ derive |
| `last_error` | TEXT | Thông điệp lỗi gần nhất |
| `last_at` | TEXT | ISO `+07:00` |
| `dead_letter` | INTEGER | 0/1 — khi 1 thì thôi chặn watermark |

- **Ngưỡng dead-letter: 5 lần thử** (đồng bộ `deferred_max_attempts` của backfill).
- Bài thành công bị **xoá khỏi bảng**, không để rác tích tụ.

### 2.3 Dead-letter bắt buộc phải nhìn thấy được

`pipeline_radar.py` phải hiện "Bài Bronze kẹt / dead-letter ở Silver: N", kèm khuyến nghị `HIGH`
khi N > 0. **Dead-letter im lặng là quay lại đúng lỗi đang sửa**, nên đây là điều kiện nghiệm thu
bắt buộc chứ không phải tuỳ chọn.

## 3. Phương án đã cân nhắc

| Phương án | Vì sao không chọn |
|---|---|
| **JSON blob trong `pipeline_state`** — không đổi schema, lane `normal`, làm ngay | Người dùng chọn bảng riêng để **truy vấn và báo cáo** được. JSON blob khó lọc theo domain/thời gian, khó nối với `articles`, và phình dần trong một ô |
| Giữ `max(ok_ts)`, thêm danh sách "luôn thử lại" | Vẫn là sổ lỗi, chỉ khác chỗ lưu; không giải quyết việc watermark đã vượt qua bài lỗi từ các lần chạy trước |
| Bỏ watermark, mỗi chu kỳ quét lại toàn bộ | 7.402 file × 3 lượt đọc/chu kỳ trên OneDrive — đã là điểm nghẽn hiệu năng hiện tại |

## 4. Hệ quả

**Tích cực:** không còn đường mất bài âm thầm giữa Bronze và Silver; mọi ca rơi đều có hồ sơ truy
vấn được và hiện trên radar.

**Tiêu cực / rủi ro phải quản:**

1. **Head-of-line blocking** nếu ngưỡng quá cao hoặc sổ lỗi hỏng → Silver đứng im. Giảm thiểu: log
   mức ERROR khi watermark bị chặn quá 2 chu kỳ liên tiếp.
2. **Backlog dồn ở lần chạy đầu** — có thể lôi lại nhiều bài từng bị bỏ qua. **Bắt buộc chạy thử
   trên bản sao DB trước** để biết khối lượng.
3. **Migration**: bảng mới tạo qua `CREATE TABLE IF NOT EXISTS` trong `ArticleStore`, không đụng
   bảng cũ, không mất dữ liệu. Vẫn **bắt buộc sao lưu `monocle.db` trước khi chạy lần đầu**.

## 5. Nghiệm thu

| Tier | Điều kiện |
|---|---|
| Unit | File lỗi có `fetch_ts` cũ hơn file thành công: chu kỳ sau **vẫn** được chọn lại (test này fail trên code hiện tại) |
| Unit | Đủ 5 lần thử → `dead_letter=1`, watermark được phép tiến |
| Unit | Bài thành công bị xoá khỏi `silver_failures` |
| Integration | Bronze hỏng xen kẽ Bronze tốt, chạy nhiều lượt, khẳng định không bài nào biến mất |
| **Platform** | Chạy trong morninger thật, 2 chu kỳ derive liên tiếp + radar hiện số dead-letter |

Story chỉ đạt `implemented` khi có đủ tier Platform (AGENTS.md rule 06 §4.4).
