
1. Phương pháp khai thác
	1. Parse HTML tĩnh
		1. Mô tả: áp dụng cho những trang web không đi không dùng API, hoặc không giải được API
		2. Cách hoạt động: Tải toàn bộ mã nguồn MTML về và dùng các bộ chọn (CSS/Selector/Xpath) để cắt lấy nội dung.
		3. Công cụ:
			1. Beautiful Soup: thư viện python, phù hợp xử lý từng trang đơn lẻ hoặc làm sạch dữ liệu HTML lộn xộn
			2. Scrapy: framework crawl bất đồng bộ nhiều trang cùng lúc
	2. API reverse engineering
		1. Mô tả:
		2. Các phương pháp
			1. Web API debugging: DevTool (F12), tab Network, lọc XHR/Fetch, tìm endpoint trả về Json chứa dữ liệu cần thiết
			2. Network monitoring: Thay vì nhìn thông tin hiển thị trên màn hình, phương pháp này "nghe lén" các gói tin mà trình duyệt gửi đi và nhận về từ máy chủ ở chế độ nền (background)
				1. Sử dụng Playwright để mở trình duyệt / network (giả lập/mô phòng hành vi người dùng)
				2. Nhận diện pattern -> tìm các request trả về dưới dạng json -> tìm các từ khóa trong URL như /api, /_Partials, /ajax, hoặc .ashx
				3. Replay: Coppy URL, heades, params của request đó để thử gọi bằng code (python/postman) -> Nếu trả về dữ liệu Json -> API ẩn
	3. Lựa chọn phương pháp
		1. ![[Pasted image 20260212105429.png]]
		2. Xác định nguồn tin/cấu trúc bài đăng -> API engineering
		3. Xử lý nội dung chi tiết: HTML parsing (để xử lý hoặc giữ lại nguyên bản nội dung gốc)
2. Workflow
	1. Input: URL, API endpoint, tham số
	2. Process: Request HTML, parse HTML
	3. Output: Cấu trúc bài đăng (Raw) mà nguồn tin cung cấp
3. 
4. 
