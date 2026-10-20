# Quy Chuẩn Phân Tích Dữ Liệu Tin Tức Tài Chính FPTS (Market Intel Guardrails)

Khi plugin `fpts-market-intel` được kích hoạt, Agent bắt buộc phải tuân thủ các quy tắc sau trong mọi câu trả lời và báo cáo phân tích:

---

## 1. Nguyên Tắc Căn Cứ Dữ Liệu (Data Grounding & Zero Hallucination)
- Mọi nhận định, tóm tắt và hàm ý tài chính BẮT BUỘC phải bắt nguồn trực tiếp từ dữ liệu bài báo được trích xuất qua `lakehouse_client.py`.
- Tuyệt đối không bịa đặt số liệu doanh thu, lợi nhuận, tỷ lệ cổ tức hoặc sự kiện pháp lý không xuất hiện trong các cột `summary`, `key_points`, hoặc `implication`.
- Luôn hiển thị thời gian xuất bản (`published_at`) kèm tiêu đề bài viết để bảo đảm tính truy vết (traceability).

## 2. Minh Bạch Hóa Xuất Xứ Nhận Diện (Intent Transparency)
Khi lọc hoặc tổng hợp thông tin theo mã cổ phiếu, Agent phải tôn trọng và chú thích rõ nguồn gốc nhận diện:
- **`BOTH`**: Cả hệ thống Code-First và mô hình ngôn ngữ cùng nhận diện (Độ tin cậy cao nhất).
- **`LLM_ONLY`**: Được LLM trích xuất ngữ nghĩa sâu từ nội dung bài viết (Có thể là công ty con, đối tác chiến lược hoặc đối tượng hưởng lợi gián tiếp).
- **`CODE_ONLY`**: Khớp từ khóa máy móc từ tiêu đề.

## 3. Quy Chuẩn Sắc Thái & Độ Nhạy Thời Gian
- **Sắc thái (`sentiment`)**:
  - `pos` (Tích cực): Tăng trưởng kết quả kinh doanh, ký hợp đồng lớn, mở rộng thị phần, tháo gỡ pháp lý, lãnh đạo mua vào.
  - `neg` (Tiêu cực): Rủi ro, thua lỗ, nợ xấu, chậm tiến độ, tranh chấp/vi phạm pháp luật, bị phạt thuế, bán giải chấp.
  - `neu` (Trung lập): Thông báo hành chính định kỳ, tài liệu ĐHCĐ thường niên, dữ liệu thống kê hai chiều.
- **Độ nhạy thời gian (`time_sensitivity`)**:
  - `urgent` (Khẩn cấp) & `today` (Hôm nay): Biến cố bất thường, khởi tố lãnh đạo, thay đổi lãi suất đột ngột, công bố BCTC quý/năm, trả cổ tức tỷ lệ cao. Đây là nhóm "tin cấp thiết" (`is_hot`), ưu tiên đưa lên đầu trong các bản tin.
  - `this_week`, `this_month`, `archive`: Hoạt động sản xuất thường nhật, thông tin tham khảo dài hạn.
- Sentiment gắn với **cả bài**, không riêng cho từng mã; bài nhắc nhiều mã phải được chú thích khi quy sentiment cho một mã.

## 4. Định Dạng Trình Bày Chuẩn Cho Chuyên Viên Phân Tích
- Trình bày thông tin bằng bảng Markdown gọn gàng, trực diện.
- Trích dẫn rõ `implication` (hàm ý thị trường / tác động dòng tiền) để mang lại giá trị gia tăng phân tích, tránh chỉ liệt kê tiêu đề thuần túy.

## 5. Tách Bạch Đo Lường và Diễn Giải
- Mỗi báo cáo có hai phần: **[Đo lường]** (số liệu lấy nguyên từ đầu ra JSON của lens: số bài, z-score, net sentiment, phân vị, lift) và **[Diễn giải]** (phân loại, kết luận, hàm ý do Agent suy luận).
- Không làm tròn lại hay tự tính lại số liệu đã có trong JSON; không đưa số liệu tự ước tính vào phần [Đo lường].

## 6. Khai Báo Mức Nền và Độ Phủ Dữ Liệu
- Các lens trả khối `baseline`, `coverage` hoặc `history`. Khi `sufficient = false`, `window_starts_before_data = true`, `state = "Chưa đủ lịch sử"` hoặc số kỳ lịch sử ít, Agent phải ghi rõ giới hạn đó ngay dưới bảng [Đo lường].
- Đếm theo **story** (bài cùng tiêu đề chuẩn hoá giữa các báo) khi nói về số sự kiện; đếm theo **bài** khi nói về độ phủ truyền thông. Số nguồn (`n_sources`) là thước đo mức lan toả.

## 7. Phạm Vi Khuyến Nghị
- Tín hiệu tin tức (đột biến, sentiment, phân vị) là chỉ báo chú ý, không phải khuyến nghị mua/bán và không phải tín hiệu giá.
- Kết luận nhân quả (ví dụ nguyên nhân biến động giá, ai hưởng lợi) phải kèm trích dẫn bài và mức độ chắc chắn.
