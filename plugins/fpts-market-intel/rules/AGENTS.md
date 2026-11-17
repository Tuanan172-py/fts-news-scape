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
- Mặc định mọi lens (`buzz`, `pulse`, `themes`, `cooccur`, `brief`) chỉ tính thực thể `role = primary` có nguồn `BOTH` hoặc `LLM_ONLY`. Thực thể `mentioned` và `CODE_ONLY` chỉ được đưa vào khi chạy với `--include-mentions` và phải ghi rõ trong báo cáo.

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

- `coverage.window_starts_before_dense = true` hoặc `history_starts_before_dense = true`: cửa sổ lùi qua mốc `dense_data_from` (ngày kho đạt mật độ đủ dày, thường vài chục đến vài trăm bài/ngày). Dữ liệu trước mốc rất thưa, phải ghi "lịch sử thưa trước <ngày>" và không kết luận xu hướng dài hạn từ đoạn đó.
- `baseline.regime_from` / `coverage.entity_regime_from`: pipeline gán thực thể đã đổi chế độ (`config/regimes.json`). `buzz` và `themes` chỉ so sánh với dữ liệu từ mốc này; khi `baseline.warnings` có nội dung hoặc `state = "Chưa đủ lịch sử"`, không nêu kết luận "tăng tốc" hay "đột biến" dựa trên chúng.
- `pulse` gom theo phiên giao dịch (`coverage.basis = trade_date`): tin sau 14:45 ICT và tin cuối tuần thuộc phiên kế tiếp, nên một kỳ có thể gồm nhiều ngày lịch.

## 7. Phạm Vi Khuyến Nghị
- Tín hiệu tin tức (đột biến, sentiment, phân vị) là chỉ báo chú ý, không phải khuyến nghị mua/bán và không phải tín hiệu giá.
- Kết luận nhân quả (ví dụ nguyên nhân biến động giá, ai hưởng lợi) phải kèm trích dẫn bài và mức độ chắc chắn.

## 8. Đọc Phân Kỳ và Phân Biệt Tin PR với Tin Xúc Tác
- Luôn đọc `hot_net_sent` (tin cấp thiết) và `effect_net_sent` (trọng số cấp thiết và độ lan tỏa nguồn) trước `net_sent` (sắc thái truyền thông chung). Chênh lệch giữa `net_sent` và `hot_net_sent` là tín hiệu phân kỳ: tâm lý chung khác tâm lý của nhóm tin cấp thiết; phải nêu rõ và không gộp thành một kết luận.
- Đối chiếu phân kỳ giữa bối cảnh quốc tế (thực thể Fed, DXY) và trong nước (NHNN, tỷ giá, lãi suất) bằng hai truy vấn riêng, không suy luận từ một con số tổng.
- Tin PR thương hiệu, giải thưởng, lễ kỷ niệm không phải chất xúc tác định giá. Khi kết luận tác động thị trường, chỉ dựa vào tin có `implication` nêu cơ chế cụ thể (chính sách, kết quả kinh doanh, M&A, pháp lý) và loại bài PR khỏi bằng chứng. Cột phân loại sự kiện chưa có trong dữ liệu, nên việc lọc dựa trên đọc `title` và `implication`.
- Khi diễn giải truyền dẫn theo ngành, đối chiếu `sectors` với các nhóm ngành trụ của rổ `--universe vn30` do analyst xác nhận; không tự gán cơ chế truyền dẫn không có trong bài báo.

## 9. Mốc Point-in-Time, Câu Chuyện và Độ Tươi (ADR-0033)

- Câu hỏi "tại thời điểm T đã biết gì" phải chạy với `--cutoff YYYY-MM-DDTHH:MM` (giờ ICT). Mốc cắt lọc theo `available_at` = muộn hơn giữa giờ báo đăng và giờ hệ thống cào được, không lọc theo `published_at`.
- `capture_lag_min` là độ trễ cào (phút). Bài có `published_at_precision = 'date'` không có giờ trong ngày: không được xếp vào phiên sáng hay chiều.
- Đếm câu chuyện bằng `story_key`: dùng `story_id` của cụm nội dung khi có, nếu không có thì dùng tiêu đề chuẩn hoá. `story_n_sources` là số nguồn cùng đưa tin, một tín hiệu độ lan toả.
- `trade_date` theo lịch nghỉ HOSE trong `config/trading_calendar.json`. Khi `status` báo năm chưa đối chiếu (`verified=false`), phải ghi chú điều đó trong báo cáo có dùng phiên giao dịch.
- Mở đầu mọi báo cáo bằng `status`: nêu `freshness.newest_analyzed_at`, số bài đã cào nhưng chưa lên production (`freshness.unpublished_captured`), và `pit_coverage`. Không khẳng định "không có tin" khi còn bài chưa lên production.
- CLI dùng cache cục bộ ở `%LOCALAPPDATA%\fpts-market-intel\cache`. Thêm `--no-cache` khi nghi cache sai; cache tự làm mới khi dữ liệu đổi.
