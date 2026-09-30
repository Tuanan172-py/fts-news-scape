---
trigger: always_on
---
# 02 — Financial Domain Scoring & Semantic Guidelines

Tiêu chuẩn suy luận ngữ nghĩa tài chính cho Agent xử lý bài đăng (Article Lane — chuẩn `v2-lean`):

## 1. Tiêu chuẩn Phân loại Độ nhạy Thời gian — `time_sensitivity` (`ts`)

Chọn đúng 1 trong 5 mã chuẩn sau:

| Mã | Giá trị đầy đủ | Tiêu chuẩn sự kiện thực tế |
| :--- | :--- | :--- |
| **`urg`** | `urgent` | • Biến cố bất thường, sự kiện khẩn cấp tác động tức thì tới giao dịch phiên hiện tại/kế tiếp.<br/>• Khởi tố, bắt giam lãnh đạo chủ chốt; đình chỉ hoạt động, hủy niêm yết bắt buộc.<br/>• Thay đổi đột ngột lãi suất điều hành, chính sách tỷ giá hoặc thuế quan lớn. |
| **`today`** | `today` | • Công bố kết quả kinh doanh quý/năm, tài liệu họp ĐHCĐ bất thường.<br/>• Ký hợp đồng kinh tế lớn, kế hoạch chia cổ tức tỷ lệ cao, giao dịch thoái vốn/mua gom của cổ đông lớn.<br/>• Thay đổi nhân sự cấp cao (bổ nhiệm/miễn nhiệm Chủ tịch, TGĐ). |
| **`week`** | `this_week` | • Hoạt động sản xuất kinh doanh thường nhật, tiến độ triển khai dự án định kỳ.<br/>• Thông tin hội nghị, ký kết biên bản ghi nhớ (MOU) ban đầu.<br/>• Nhận định thị trường tuần, phân tích ngành không có số liệu biến động đột biến. |
| **`month`** | `this_month` | • Kế hoạch dài hạn trung hạn, báo cáo thống kê vĩ mô định kỳ tháng/quý.<br/>• Lịch trình tái cơ cấu, lộ trình áp dụng chuẩn mực kế toán/pháp lý mới. |
| **`arch`** | `archive` | • Bài viết tổng kết sự kiện lịch sử, tin tức giáo dục kiến thức tài chính chung.<br/>• Hoạt động tài trợ từ thiện, an sinh xã hội, PR thương hiệu thuần túy không có dữ liệu tài chính. |

## 2. Tiêu chí Phân loại Sắc thái — `sentiment` (`sn`)

Chọn đúng 1 trong 3 mã: `pos`, `neg`, `neu` (tương ứng `positive`, `negative`, `neutral`):

- **`pos` (`positive`)**: Phản ánh cơ hội kinh doanh, lợi nhuận tăng trưởng, mở rộng thị phần, tháo gỡ pháp lý thành công, lãnh đạo đăng ký mua vào.
- **`neg` (`negative`)**: Phản ánh rủi ro, thua lỗ, nợ xấu gia tăng, chậm tiến độ dự án, vi phạm pháp luật/thuế, lãnh đạo bị bán giải chấp hoặc đăng ký thoái vốn.
- **`neu` (`neutral`)**: Phản ánh thông tin công bố định kỳ, dữ liệu thống kê khách quan, bài viết phân tích cân bằng 2 chiều hoặc lịch trình hành chính.

## 3. Cấu trúc Hàm ý Thị trường — `implication` (`im`)

- `implication` phải trả lời trực tiếp câu hỏi: *"Sự kiện này tác động như thế nào đến doanh nghiệp, doanh thu, dòng tiền hoặc thị giá cổ phiếu liên quan?"*
- Tránh viết chung chung kiểu "Nội dung phản ánh thông tin quan trọng". Phải chỉ rõ thực thể hưởng lợi hoặc chịu rủi ro. Độ dài tối thiểu 40 ký tự.

---

## 4. Phụ lục Kế thừa — Thang điểm `materiality_score` (Archived Specification)

> [!IMPORTANT]
> **TRẠNG THÁI: ĐÃ NGỪNG ÁP DỤNG TRONG RUNTIME HIỆN HÀNH (ADR 0010 & AGENTS.md §6A).**
> - Runtime Article Lane (`v2-lean`) và User Output (`.xlsx`) **KHÔNG** sử dụng trường này để tối ưu token và thời gian phản hồi.
> - Agent **CẤM** sinh trường `materiality` hoặc `materiality_score` trong kết quả phân tích.
> - Bảng dưới đây chỉ lưu trữ phục vụ tra cứu lịch sử và cơ sở dữ liệu nếu có quyết định tái kích hoạt sau này qua quy trình ADR Cấp 3.

*Quy chuẩn cũ theo hợp đồng `agent-output-v1`: Thang số thực 0.1 → 1.0:*
- `0.80 – 1.00` *(Critical)*: Khởi tố lãnh đạo, M&A lớn, tăng vốn đột biến, hủy niêm yết, chính sách vĩ mô khẩn.
- `0.50 – 0.79` *(Material)*: BCTC quý/năm, trúng thầu dự án lớn, cổ tức cao, đổi nhân sự cấp cao.
- `0.30 – 0.49` *(Minor)*: Hoạt động thường nhật, ký MOU, giao dịch cổ đông nhỏ.
- `0.10 – 0.29` *(Noise)*: Hoạt động từ thiện, PR thương hiệu chung, bài nhận định không số liệu mới.
