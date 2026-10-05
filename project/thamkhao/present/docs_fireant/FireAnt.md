Method & Syntax (Phương thức & Cú pháp)
FireAnt cung cấp API theo chuẩn RESTful, trả về dữ liệu dạng JSON.

A. Xác thực (Authentication)
Khác với các nguồn "API ẩn" (như CafeF, Vietstock), FireAnt yêu cầu xác thực nghiêm ngặt.
• Header bắt buộc: Authorization: Bearer <token>.
• Token: Được lưu trong file cấu hình secrets.yaml (key: fireant_token).
• Lưu ý: Token có thời hạn (expire), cần cơ chế refresh hoặc cập nhật thủ công nếu request trả về lỗi 401/403.

Các bước lấy token sau khi loginAccount
1. Mở https://fireant.vn trên Chrome/Edge → đăng nhập tài khoản FireAnt của anh (đăng ký miễn phí nếu chưa có).
2. Nhấn F12 để mở DevTools → chọn tab Network (Mạng).
3. Trong ô filter của Network, gõ: restv2.fireant.vn
4. Bấm reload trang (F5) hoặc click vào một mã cổ phiếu bất kỳ → danh sách request tới restv2.fireant.vn hiện ra. Click vào một request bất kỳ (vd posts?...).
5. Ở panel bên phải chọn tab Headers → kéo xuống mục Request Headers → tìm dòng:
Authorization: Bearer eyJhbGciOiJ...
6. Copy toàn bộ chuỗi sau chữ "Bearer " (chuỗi dài bắt đầu bằng eyJ...). Không copy chữ "Bearer ".

B. Endpoints
1. Lấy danh sách tin (List API):
    ◦ URL: https://restv2.fireant.vn/posts
    ◦ Method: GET
    ◦ Parameters quan trọng:
        ▪ symbol: Mã cổ phiếu (VD: FPT, VIC).
        ▪ type: Loại bài (thường dùng 1 cho tin tức chính thống).
        ▪ page: Số trang (bắt đầu từ 0 hoặc 1 tùy ngữ cảnh, thường là 1).
        ▪ pageSize: Số lượng bài/request (VD: 20)
2. Lấy chi tiết tin
	1. URL: https://restv2.fireant.vn/post/{postID}
	2. Method: GET
	3. Mục đích: Lấy content đầy đủ (HTML) để trích xuất nội dung (do API danh sách trả về body rỗng)
	
----------
Workflow tích hợp vào dự án
1. Load config:
	1. Auth: Xác thực bearer token
	2. Watchlist: Load danh sách cổ phiếu hàng ngày
2. Loop & Fetch
	1. Duyệt qua từng mã cổ phiếu trong danh sách, gọi API/post.
3. Fillter
	1. Lọc trường date
4. Detail Fetching
	1. Lấy post_id của trang tin sau bộ lọc
	2. Call API /post/{post_id}
	3. Merge lại trường /content vào cấu trúc bài đăng trả về từ post
5. Save
	1. Lưu object JSON (bao gồm cả metadata) xuống file để giữ nguyên cấu trúc.
Mô tả:
![[Pasted image 20260212113035.png]]

