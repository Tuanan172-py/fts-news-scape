# ADR 0018 — Một trích dẫn là đủ cho bài tin vắn một đoạn văn

- **Loại tài liệu:** giải thích (explanation), ghi lại một quyết định.
- **Ngày:** 2026-10-05
- **Trạng thái:** accepted
- **Lane:** high-risk
- **Story:** không có (vận hành đợt W10051122)
- **Kế thừa:** ADR 0017 (hợp đồng đầu ra thống nhất). Thu hẹp `minItems` trích dẫn của `agent-output-v2-lean` từ 2 xuống 1; ngưỡng ngữ nghĩa 2 trích dẫn giữ nguyên ở DoD, trừ bài một đoạn văn.
- **Người duyệt:** người vận hành duyệt hướng (a) trong phiên 2026-10-05.

## 1. Bối cảnh

Đợt W10051122 (500 bài, OpenRouter free $0, 5 vòng vá) đạt 499/500 bản ghi, L1 100%, nhưng nội dung chỉ 360/500 (72% < ngưỡng 90%) nên `--finish` từ chối đúng thiết kế. Toàn bộ ~140 bài thiếu là tin vắn đúng một đoạn văn (mẫu 199 ký tự); hợp đồng đòi tối thiểu 2 trích dẫn nên không worker nào qua được, vá thêm cũng vô ích. Đây là trần hợp đồng, không phải lỗi worker hay persona.

## 2. Quyết định

- Bài có dưới 2 đoạn văn đạt độ dài trích dẫn thì một trích dẫn hợp lệ là đủ.
- Bộ bung đánh dấu bản ghi dạng này bằng `citation_basis: "single-paragraph"`; cổng DoD nới ngưỡng trích dẫn xuống 1 đúng khi có dấu này.
- Lược đồ `agent-output-v2-lean` hạ `minItems` của `citations` xuống 1 (hình thức); ngưỡng ngữ nghĩa mặc định 2 giữ nguyên trong DoD.

## 3. Phương án đã loại

| Phương án | Lý do loại |
|---|---|
| Miễn gold cho tin vắn | Mất tóm tắt, luận điểm, hàm ý của ~28% đợt; giao hàng thưa đi mà không có lợi kỹ thuật nào |
| Loại tin vắn khỏi mẫu số verify | Mẫu số verify thành khái niệm hai tốc độ, khó giải thích trong hậu kiểm và sổ cái |

## 4. Hệ quả

**Được:**

- W10051122 vượt ngưỡng 90% nội dung mà không tốn thêm token mô hình.
- Các đợt sau không còn kẹt vì tin vắn; hợp đồng kiểm ở `article_contract.py` vốn đã có `need = min(C_MIN, eligible)`, nay bộ bung và DoD khớp với nó.

**Phải chấp nhận:**

- Bản ghi 1 trích dẫn có căn cứ mỏng hơn; người đọc cần cột/dấu phân biệt khi giao hàng (việc theo dõi).

## 5. Quay lui

Bỏ dấu `citation_basis` ở bộ bung, trả `minItems` về 2 và xóa nhánh nới ngưỡng trong `check_dod`. Người thực hiện: bất kỳ ai có quyền sửa mã Article Lane, cần chạy lại `pytest` trước khi vận hành.

## 6. Việc theo dõi

- [ ] Re-expand + `--finish` W10051122, đối chiếu hậu kiểm đạt ≥90% cả hai lớp.
- [ ] Cột giao hàng phân biệt bài 1 trích dẫn (xây dựng khi chạm `user_output`).
- [ ] Đo tỷ lệ `single-paragraph` các đợt sau để quyết định có cần tách luồng tin vắn riêng không.
