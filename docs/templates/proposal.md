# Đề xuất — <chủ đề>

- **Loại tài liệu:** giải thích (explanation). Một đề xuất tách ba phần: phán quyết, nhật ký thực thi, kết quả.
- **Ngày:** YYYY-MM-DD
- **Trạng thái:** draft | decided | executed | superseded
- **Lane:** tiny | normal | high-risk
- **Hồ sơ nguồn:** đường dẫn bằng chứng và báo cáo thành viên

## Quy ước mã

Mọi mã tham chiếu trong tài liệu (A1, G3, D-A) phải được định nghĩa tại đây.

| Mã | Nghĩa |
|---|---|
| A1, A2, ... | Phát hiện về kiến trúc |
| D-A, D-B, ... | Quyết định cần người vận hành chốt |

## 1. Phán quyết

Kết luận cố định, viết một lần. Không sửa sau khi trạng thái chuyển sang `decided`.

## 2. Phát hiện

| Mã | Phát hiện | Bằng chứng | Mức |
|---|---|---|---|
| X1 | Mô tả một câu | `tệp:dòng` hoặc số đo | Chặn, Nặng, Vừa hoặc Nhẹ |

## 3. Quyết định của người vận hành

| Mã | Quyết định | Ngày | Hệ quả |
|---|---|---|---|

## 4. Nhật ký thực thi

Chỉ nối thêm. Mỗi dòng có ngày, việc đã làm và bằng chứng. Phần này không thay đổi phán quyết ở mục 1.

| Ngày | Việc | Bằng chứng |
|---|---|---|

## 5. Kết quả

Trạng thái cuối của từng mã phát hiện: đã xử lý, còn mở, hoặc không làm và lý do.
