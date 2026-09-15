---
name: daily-brief-synthesizer
description: Tổng hợp bản tin cuối ngày cá nhân hóa theo watchlist từng user từ dữ liệu Gold, mỗi luận điểm dẫn nguồn article_id để truy vết.
---
# Daily Brief Synthesizer Skill

> **Mục đích:** Hướng dẫn Subagent Pro cô đọng dữ liệu Gold trong ngày thành một bản tin markdown riêng cho mỗi user thực, neo mọi luận điểm về `article_id`.

## 1. Đầu vào & Gom theo User

- **Nguồn Gold**: Đọc dữ liệu đã ingest trong ngày từ `data/monocle.db`, gồm `agent_outputs` (join `l1_outputs`), gom theo từng user qua watchlist.
- **Trường dùng cho mỗi mục**: `article_id`, `summary`, `key_points`, `implication`, `sentiment`, `time_sensitivity`, `l1_entities`.
- **Watchlist user**: Danh sách entity/mã cổ phiếu user theo dõi. Chỉ giữ mục có `l1_entities` giao với watchlist user.
- **Chế độ đọc**: Gọi `view_file` một lần trên dữ liệu tổng hợp trong ngày đã gom theo user.

## 2. Ràng buộc Danh tính User (Zero Hallucination User Manifest)

1. Đọc `users/input/manifest.yaml` để lấy tập user thực được BẬT (hiện tại: `AnPT`).
2. Chỉ sinh brief cho user có trong manifest. Bỏ qua mọi tên ngoài danh sách.
3. Cấm bịa user hư cấu, cấm gộp nhiều user vào một brief.
4. User không có mục nào chạm watchlist trong ngày -> ghi brief với các mục rỗng và một dòng ghi chú "Không có tin chạm watchlist trong ngày", không suy diễn thêm.

## 3. Nhiệm vụ Tổng hợp Bản tin

Với mỗi user thực, sinh một bản tin markdown gồm ba mục:

1. **Điểm nóng theo dõi**:
   - Chọn 3–7 tin trọng yếu nhất chạm watchlist user, ưu tiên `time_sensitivity` cao và `implication` tác động lớn.
   - Mỗi tin: 1–2 câu súc tích diễn giải cô đọng + hàm ý, kết bằng `(article_id)`.
2. **Roll-up chủ đề vĩ mô**:
   - Gom các tin cùng MACRO_THEME (lãi suất, tỷ giá, đầu tư công, giá hàng hóa...) thành một nhận định ngắn cho mỗi chủ đề.
   - Mỗi nhận định dẫn kèm các `(article_id)` nguồn cấu thành.
3. **Cần quan sát**:
   - Liệt kê diễn biến có `time_sensitivity` ∈ {`urgent`, `today`} đáng theo dõi tiếp trong 24 giờ tới.
   - Mỗi dòng nêu mốc cần theo dõi + `(article_id)`.

### Ràng buộc nội dung

- Mỗi luận điểm BẮT BUỘC dẫn nguồn dạng `(article_id)` để truy vết.
- Chỉ dùng số liệu có trong dữ liệu Gold; cấm đưa con số ngoài dữ liệu.
- Chỉ tham chiếu entity thuộc watchlist user.
- Diễn giải cô đọng, không sao chép nguyên văn `summary` Gold.

## 4. Output

Ghi bằng `write_to_file` vào `users/output/<user>/brief-<date>.md` — một file markdown cho mỗi user.

Cấu trúc:

```markdown
# Bản tin cuối ngày — <user> — <date>

## Điểm nóng theo dõi
- <Diễn giải cô đọng tin 1 + hàm ý>. (<article_id>)
- <Diễn giải cô đọng tin 2 + hàm ý>. (<article_id>)

## Roll-up chủ đề vĩ mô
- **Lãi suất**: <nhận định ngắn>. (<article_id>, <article_id>)
- **Tỷ giá**: <nhận định ngắn>. (<article_id>)

## Cần quan sát
- <Diễn biến urgent/today + mốc theo dõi>. (<article_id>)
```

## 5. Định nghĩa Hoàn thành (DoD `dod-gatekeeper#brief`)

- Mọi mục điểm nóng trích dẫn `article_id` có thật trong dữ liệu ngày.
- Chỉ tham chiếu entity thuộc watchlist user.
- Không lặp lại nguyên văn `summary` Gold; diễn giải cô đọng.
- Chỉ sinh brief cho user thực trong `users/input/manifest.yaml`.

## 6. Chế độ I/O

- **Đọc**: `view_file` trên dữ liệu tổng hợp trong ngày (`agent_outputs` + `l1_outputs` từ `data/monocle.db`) và `users/input/manifest.yaml`.
- **Ghi**: `write_to_file` một file brief cho mỗi user.
- **Điều phối**: Mỗi user một lô (`wave_batch: 1`), một luồng (`concurrency: 1`).

## 7. Khai báo Hệ thống

- **Registry** (`.agents/registry.yaml`): `id: daily-brief-synthesizer`, `class: cognitive`, `status: draft`, `model: pro`, `dod_contract: dod-gatekeeper#brief`.
- **Pipeline** (`.agents/pipeline.yaml`): stage `daily_brief`, `optional: true`, `needs: [deliver]`.
- **Định vị deliverable**: Bản tin markdown là deliverable bậc cao bổ sung cho file Excel hiện có (`users/output/<user>/<date>.xlsx`), không thay thế.
