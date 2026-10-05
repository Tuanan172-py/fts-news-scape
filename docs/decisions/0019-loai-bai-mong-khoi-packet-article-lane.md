# ADR 0019 — Loại bài mỏng khỏi packet Article Lane

- **Loại tài liệu:** giải thích (explanation), ghi lại một quyết định.
- **Ngày:** 2026-10-05
- **Trạng thái:** accepted
- **Lane:** normal
- **Story:** US-036 (cùng đợt với E1 dedupe và cổng wave-global)
- **Kế thừa:** ADR 0010, ADR 0013, ADR 0016 và ADR 0017.
- **Người duyệt:** người dùng duyệt ngày 2026-10-05 (chọn "Loại khỏi packet").

## 1. Bối cảnh

Số đo phiên 2026-10-05 trên 3 đợt Article Lane (700 bài):

- 202 bài có tổng đoạn văn packet 102–494 ký tự. Toàn bộ trượt cổng Gold vì thiếu trích dẫn đủ dài.
- Ba ngưỡng trích dẫn nằm ở ba nơi mà không có kiểm khớp nào.
- Số "chờ phân tích" của radar đếm cả bài mỏng, trong khi đợt sau không lấy được chúng.

## 2. Quyết định

### 2.1. Định nghĩa bài mỏng

Bài mỏng khi mảng đoạn văn đúng như bước đóng gói sẽ gửi cho mô hình có **dưới hai đoạn đạt `MIN_CITATION_CHARS`**. Đo ở pack-time bằng `is_thin`.

### 2.2. Loại khỏi packet, đếm riêng

- `load_candidates(..., exclude_thin=True)` (mặc định) loại bài mỏng. Mọi nơi gọi hàm này thấy cùng một con số.
- Radar in thêm dòng "Bài mỏng chờ Silver", không gộp vào "chờ phân tích".
- Fail-open: không đọc được nội dung thì giữ bài, để vòng đóng gói loại sau như cũ.
- Bài mỏng được nhận lại khi gói Silver về, hoặc qua đường vá làm mới của ADR 0016.

### 2.3. Một ngưỡng duy nhất

`MIN_CITATION_CHARS` chuẩn nằm ở `src/agent/article_contract.py`. Test chốt ba nơi bằng nhau.

## 3. Phương án đã loại

- **Chỉ chạy L1 cho bài mỏng:** vẫn tốn token nhận diện mà không thêm coverage Gold.
- **Giữ nguyên, chỉ cảnh báo:** tồn tiếp tục vào đợt, fail cổng finish và giữ bài của cả đợt.

## 4. Hệ quả

- Token Gold không còn đốt cho bài trượt tất định.
- Không đổi schema DB, không đổi hợp đồng đầu ra — chỉ đổi tập bài vào packet.

## 5. Quay lui

Bật lại bằng `exclude_thin=False` ở từng lệnh gọi, hoặc `git revert` commit US-036. Không cần migrate dữ liệu.
