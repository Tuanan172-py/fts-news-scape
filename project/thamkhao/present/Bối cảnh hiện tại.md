Quy trình theo dõi vị thế khuyến nghị
Trong module Tin tức
- Hiện trạng: đã hoạt động
- Nguồn: 1 nguồn Vietstock duy nhất
- Nội dung
	- Tiêu đề
	- đường dẫn


Phương pháp áp dụng
	Parse HTML tĩnh từ URL cụ thể: 
		- base_url = f"https://finance.vietstock.vn/{ticker}/tin-moi-nhat.htm"
		- technique:
			- request: gửi thẳng HTTP để lấy nội dung web
			- BeautifulSoup: Parse tĩnh HTML để trích xuất dữ liệu
			- parse:
				- Tìm tất cả <table> trên trang
				- Duỵet qua từng (<tr>) và (<td>)
		Workflow: 
			- Input(): Danh sách watchlist
			- process: request url -> Trích xuất (tin tức, tiêu đề, link, ngày đăng...) -> Thông tin được format (xlsx)


Trạng thái
	- Lấy được thông tin (đường dẫn) cho danh sách watchlist.
Đánh giá
	- Chưa trích xuất nội dung thông tin
	- Có duy nhất 1 nguồn dữ liệu là vietstock
	- Chưa có tóm tắt thông tin, chưa có đánh giá thông tin tự động
	- User phải comment thủ công quan điểm tin tức.

