# Rule 10 — Thu thập trọn vẹn, xử lý về sau

> Bất biến cấp dự án, người dùng ghim ngày 2026-10-01. Quyết định: `docs/decisions/0013-thu-thap-tron-ven-xu-ly-ve-sau.md`.

## 1. Nguyên tắc

Nguồn có bao nhiêu bài thì lấy về bấy nhiêu. Thu thập không lọc, không bỏ, không xoá. Mọi thao tác chọn lọc (loại trùng, làm sạch, phân loại, xếp ưu tiên, quyết định có gọi LLM hay không) là bước xử lý **sau** khi bài đã nằm trong Bronze, và không bao giờ xoá bài khỏi kho.

## 2. Luật cứng

1. **Không lọc ở tầng cào.** Bộ cào không được loại bài theo độ giống tiêu đề, chuyên mục, từ khoá, độ dài hay độ liên quan. Ngoại lệ duy nhất: bản sao kỹ thuật cùng một bài (cùng URL chuẩn hoá, hoặc cùng mã bài của nguồn). Bản sao này vẫn được ghi lại thành bí danh.
2. **Mọi URL phát hiện được đều có dấu vết.** URL thấy ở listing, RSS, API hay sitemap phải được ghi vào sổ phát hiện **trước** mọi bước lọc. Không có trạng thái cuối nào mang nghĩa "đã bỏ". Trạng thái cuối hợp lệ là `captured`, `alias`, `gone` (nguồn trả 404/410), hoặc `dead_letter` (lỗi có lý do, được thử lại).
3. **Không bỏ sót vì giới hạn trang.** Bộ cào phân trang theo watermark: đọc tiếp cho tới khi gặp bài đã có, không dừng cứng ở trang 1. Khi máy chạy lại sau thời gian tắt hoặc ngủ, bộ cào tự bù phần thiếu.
4. **Có kênh đối chiếu độc lập.** Nguồn có sitemap, news sitemap hoặc API theo ngày thì được đối chiếu mỗi ngày. Bài có trong kênh đối chiếu mà thiếu trong kho thì được cào bù và ghi vào thước đo độ phủ thu thập.
5. **Trùng lặp là dữ liệu, không phải rác.** Bài trùng được giữ đủ nguồn, thời điểm và URL. Bài trùng có thể được miễn bước LLM bằng cách kế thừa kết quả của bài gốc, nhưng vẫn được tính vào mọi chỉ số tần suất và độ rộng đưa tin.
6. **Raw bất biến.** `raw_html` và `.meta.json` ở Bronze không bị sửa hay xoá. Dọn dẹp chỉ áp cho bảng phái sinh có thể dựng lại.

## 3. Kiểm định

- Radar có dòng **độ phủ thu thập** theo nguồn và theo ngày: số bài kênh đối chiếu báo, số bài đã có trong kho, số bài thiếu.
- Thiếu so với kênh đối chiếu > 2% trong một ngày là mục ĐỎ.
- Mọi thay đổi bộ cào phải có test chứng minh không có đường mã nào bỏ bài mà không ghi dấu vết.

## 4. Phản mẫu đã gặp (2026-10-01)

| Phản mẫu | Hậu quả đo được |
|---|---|
| Loại bài theo `token_set_ratio ≥ 90` ở `base_scraper` | 439 bài bị loại trong 3 ngày, 202 bài loại nhầm, không có Bronze, không cào lại được |
| `pages_per_cycle: 1` và chỉ cào một số chuyên mục | baodautu chỉ có khoảng 50% số bài trong sitemap chính thức, đều mỗi ngày |
| Máy tắt 11–16 giờ, bộ cào chỉ đọc trang đầu | không có cơ chế bù khi chạy lại |
