### method

- **Method**: Phân tích các request mạng (network requests) khi trang web hoạt động -> xác định được API nội bộ mà CafeF sử dụng để tải tin tức: `https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx`.
- **Phương pháp mới**: Chuyển hướng script, thay vì parse HTML, script sẽ gọi trực tiếp vào API này với các tham số truyền vào `symbol`, `pageIndex`, và `pageSize`.
- **Ưu điểm**:
    - **Hiệu quả**: Nhanh hơn so với việc tải và parse toàn bộ trang HTML.
    - **Ổn định**: Ít bị ảnh hưởng bởi các thay đổi về giao diện (UI) của trang web.
    - **Dữ liệu có cấu trúc**: API trả về dữ liệu dạng JSON, dễ xử lý hơn.

### story:
1. HTML tĩnh sử dùng requests và BeautifulSoup để tải HTML nhưng thất bại do:
		• HTML tải về không chứa dữ liệu tin tức (thẻ div#div_data_news không tồn tại).
		• Lý do: CafeF sử dụng kỹ thuật Dynamic Loading (tải động) bằng JavaScript/AJAX. Dữ liệu chỉ được tải về sau khi giao diện web đã hiển thị.
2. Quy trình thực hiện tìm api endpoint
	1. Mở Công cụ phát triển (DevTools): Truy cập trang CafeF trên trình duyệt và nhấn F12 (hoặc chuột phải -> Inspect), chuyển sang tab Network.
	2. Tương tác & Kích hoạt: Tải lại trang (F5) hoặc cuộn xuống dưới/bấm nút "Xem thêm" để trang web thực hiện hành động tải dữ liệu.
	3. Lọc gói tin (Filtering):
	    ◦ Trong tab Network, chọn bộ lọc Fetch/XHR (đây là loại request thường chứa dữ liệu JSON/XML).
	    ◦ Quan sát các request xuất hiện khi dữ liệu tin tức hiện ra trên màn hình.
	4. Nhận diện Endpoint:
	    ◦ Tìm kiếm các request có phản hồi (Response) dạng JSON chứa nội dung tin tức.
	    ◦ Đã phát hiện file có tên News.ash

### workflow
* API endpoint: https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx
* Method: GET
* Headers:
	* User-Agent: Giả lập trình duyệt
	* Referer: https://cafef.vn/
* Parameter:
	*  `symbol`: Mã cổ phiếu (ví dụ: `HPG`, `VIC`)
	* `pageIndex`: Số trang (Bắt đầu từ 1).
	* `pageSize`: Số lượng tin mỗi lần gọi (Dự án đang set `100` để giảm số lần request).
**Ví dụ Code Python (Giả lập):**

```
import requests

url = "https://cafef.vn/du-lieu/Ajax/PageNew/News.ashx"
params = {
    "symbol": "FPT",
    "pageIndex": 1,
    "pageSize": 100
}
headers = {
    "User-Agent": "Mozilla/5.0...",
    "Referer": "https://cafef.vn/"
}

response = requests.get(url, params=params, headers=headers)
data = response.json() # Trả về danh sách bài viết dạng JSON
```