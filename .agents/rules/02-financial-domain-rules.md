---
trigger: always_on
---
# 02 — Financial Domain Scoring & Semantic Guidelines

Quy tắc định lượng và tiêu chuẩn suy luận tài chính cho Subagent Gold Analyst trên Antigravity 2.0:

## 1. Thang điểm Trọng yếu Tài chính — `materiality_score`

**THANG DUY NHẤT: số thực 0–1** (`agent-output-v1`: `materiality.score`, `minimum: 0`,
`maximum: 1`). Khoảng khuyến nghị khi chấm là `0.1 → 1.0`. Tuyệt đối KHÔNG dùng thang khác
(3/5, 1–5, phần trăm) ở bất kỳ rule, doc hay code nào — đã từng lệch và gây hiểu nhầm ngưỡng.

| Dải điểm | Phân cấp | Tiêu chuẩn sự kiện thực tế |
| :--- | :--- | :--- |
| **0.80 – 1.00** | **Tối quan trọng** *(Critical)* | • Khởi tố, bắt giam lãnh đạo chủ chốt (Chủ tịch, TGĐ).<br/>• M&A quy mô lớn, thâu tóm chi phối, sáp nhập doanh nghiệp.<br/>• Tăng vốn điều lệ / phát hành cổ phiếu đột biến tỷ lệ lớn.<br/>• Hủy niêm yết, phá sản, xử phạt đình chỉ hoạt động.<br/>• Thay đổi chính sách vĩ mô, lãi suất điều hành, thuế quan lớn. |
| **0.50 – 0.79** | **Quan trọng vừa** *(Material)* | • Báo cáo tài chính quý/năm (lãi kỷ lục, lỗ đột biến, hoàn thành kế hoạch).<br/>• Ký kết hợp đồng kinh tế/trúng thầu dự án lớn.<br/>• Kế hoạch chia cổ tức bằng tiền mặt hoặc cổ phiếu tỷ lệ cao.<br/>• Thay đổi nhân sự cấp cao (bổ nhiệm/miễn nhiệm thành viên HĐQT, Kế toán trưởng). |
| **0.30 – 0.49** | **Ảnh hưởng nhẹ** *(Minor)* | • Hoạt động sản xuất kinh doanh thường nhật.<br/>• Ký kết biên bản ghi nhớ hợp tác ban đầu (MOU).<br/>• Giao dịch cổ phiếu của cổ đông nhỏ, người có liên quan khối lượng ít.<br/>• Lịch họp ĐHCĐ thường niên, công bố tài liệu họp. |
| **0.10 – 0.29** | **Nhiễu / PR** *(Noise)* | • Hoạt động tài trợ thể thao, từ thiện, an sinh xã hội.<br/>• Khai trương chi nhánh bán lẻ nhỏ, bài viết PR thương hiệu chung.<br/>• Bài viết nhận định chung không có số liệu mới. |

## 2. Tiêu chí Phân loại Sắc thái — `sentiment`

- **`positive`**: Phản ánh cơ hội kinh doanh, lợi nhuận tăng trưởng, mở rộng thị phần, tháo gỡ pháp lý thành công, lãnh đạo đăng ký mua vào.
- **`negative`**: Phản ánh rủi ro, thua lỗ, nợ xấu gia tăng, chậm tiến độ dự án, vi phạm pháp luật/thuế, lãnh đạo bị bán giải chấp hoặc đăng ký thoái vốn.
- **`neutral`**: Phản ánh thông tin công bố định kỳ, dữ liệu thống kê khách quan, bài viết phân tích cân bằng 2 chiều hoặc lịch trình hành chính.

## 3. Cấu trúc Hàm ý — `implication`

- `implication.text` phải trả lời trực tiếp câu hỏi: *"Sự kiện này tác động như thế nào đến doanh nghiệp, dòng tiền và cổ phiếu liên quan?"*
- Tránh viết chung chung kiểu "Nội dung phản ánh thông tin quan trọng". Phải chỉ rõ thực thể hưởng lợi hoặc chịu rủi ro.
