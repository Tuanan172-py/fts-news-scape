# ADR 0018 — Thân bài Silver cho lane và một trích dẫn cho bài một đoạn

- **Loại tài liệu:** giải thích (explanation), ghi lại một quyết định.
- **Ngày:** 2026-10-05
- **Trạng thái:** accepted
- **Lane:** high-risk
- **Story:** không có (vận hành đợt W10051122)
- **Kế thừa:** ADR 0017 (hợp đồng đầu ra thống nhất).
- **Người duyệt:** người vận hành duyệt hướng (a) trong phiên 2026-10-05.

## 1. Bối cảnh

Đợt W10051122 đạt 499/500 bản ghi sau 5 vòng vá. L1 vào đủ 100%. Nội dung chỉ vào 360/500 nên `--finish` từ chối đúng thiết kế. Đo packet cho thấy ~140 bài mang đúng một đoạn văn. Đo lại Silver cho thấy cả 500 bài đều đủ đoạn văn. Packet đóng lúc Silver chưa có nên chỉ còn đoạn trích RSS ngắn. Trích dẫn cũ vì thế không đối chiếu được vào thân bài mới.

## 2. Quyết định

- Packet, bộ lọc mỏng và gói công việc đều đọc thân bài Silver đầy đủ trước.
- Gói công việc cũ tự dựng lại ở lần nạp tới (phiên bản 1.1).
- Bài đã có bản ghi nhưng packet cũ được đóng gói lại từ Silver (làm mới).
- Khi bung, mỗi bài chỉ giữ hàng của lô có đầu ra thô mới nhất.
- Bài thật sự một đoạn văn thì một trích dẫn là đủ, có dấu `citation_basis`.

## 3. Phương án đã loại

| Phương án | Lý do loại |
|---|---|
| Vá tiếp quanh bản ghi cũ | Trích dẫn cũ không vào thân mới nên mọi vòng vá đều trượt |
| Miễn gold cho tin vắn | Mất tóm tắt và hàm ý của ~28% đợt mà không sửa nguyên nhân |

## 4. Hệ quả

**Được:**

- Trích dẫn đối chiếu được vì packet và cổng kiểm đọc cùng thân bài.
- Đợt cũ kẹt vì packet cũ có đường quay lại mà không tốn thêm thiết kế mới.

**Phải chấp nhận:**

- Ba vòng vá cũ của W10051122 tốn thêm một lượt chạy lại trên thân mới.
- Gói công việc 1.0 phải dựng lại, tốn một lần đọc Silver cho mỗi bài.

## 5. Quay lui

Trả `resolve_body_text` về thứ tự cũ (gói RSS trước). Giữ nguyên packet mới vì chúng đã đúng. Người thực hiện: bất kỳ ai có quyền sửa mã Article Lane.

## 6. Việc theo dõi

- [ ] Re-pack làm mới + chạy lại + `--finish` W10051122, đối chiếu phủ ≥90%.
- [ ] Xóa packet cũ khi đợt xong để kho không phình.
- [ ] Đo tỷ lệ packet cũ ở các đợt lỗi còn lại (W10051042, W10051050).
