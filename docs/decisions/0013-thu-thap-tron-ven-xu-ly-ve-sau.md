# ADR 0013 — Thu thập trọn vẹn, xử lý về sau

- **Ngày:** 2026-10-01
- **Trạng thái:** **accepted** về nguyên tắc. Người dùng ghim ngày 2026-10-01: "lấy về tất cả, không bỏ sót; loại trùng, làm sạch là bước xử lý về sau; raw có bao nhiêu tin cần lấy về tất cả; thiết kế kiến trúc cần đảm bảo yêu cầu không bỏ sót". Các thay đổi mã và lược đồ để thực thi nguyên tắc này đi theo story riêng.
- **Lane:** high-risk: bất biến kiến trúc, ảnh hưởng mọi bộ cào và lược đồ DB.
- **Rule thực thi:** `.agents/rules/10-thu-thap-tron-ven.md`.
- **Liên quan:** `docs/proposals/dedup-architecture-2026-10-01.md`, `docs/proposals/insight-analytics-2026-10-01.md`.

## Bối cảnh

Số đo ngày 2026-10-01 (DB vận hành, chỉ đọc):

1. `base_scraper` loại bài theo độ giống tiêu đề trước khi lưu: 439 bài trong 3 ngày, 202 bài (46%) loại nhầm. Không có Bronze, không còn URL.
2. Đối chiếu sitemap chính thức của baodautu từ 20/09 đến 01/10: kho chỉ có khoảng 50% số bài, ví dụ 30/09 sitemap có 101 bài, kho có 57. Nguyên nhân: chỉ cào trang 1 của 6 chuyên mục.
3. Theo ADR 0012, máy tắt thì mọi thứ dừng. Bộ cào cafef có khoảng nghỉ 11–16 giờ, và chỉ đọc trang đầu (`PageSize: 20`).
4. 1.461 tệp Bronze nằm ở dead-letter Silver: có raw nhưng nội dung không tới được bước phân tích.

Ngoài ra, tần suất và độ rộng đưa tin của một chủ đề là tín hiệu đầu tư. Bỏ bài trùng ở tầng cào làm mất chính tín hiệu này.

## Quyết định

1. Thu thập là tầng **không lọc**. Mọi chọn lọc nằm sau Bronze và không xoá bài.
2. Thêm **sổ phát hiện** (`discovered_urls`): mọi URL thấy được đều được ghi trước khi lọc, kèm vòng đời trạng thái. Không có trạng thái "đã bỏ".
3. Bộ cào phân trang theo **watermark** và tự bù sau thời gian máy tắt.
4. **Đối chiếu độc lập** hằng ngày với sitemap hoặc API theo ngày của từng nguồn. Thiếu thì cào bù.
5. **Trùng lặp được giữ và cụm hoá.** Bài trùng được miễn LLM bằng kế thừa kết quả, và được đếm đủ vào chỉ số tần suất.
6. Radar có thước đo **độ phủ thu thập**. Thiếu > 2% trong một ngày là ĐỎ.

## Hệ quả

- Tải cào tăng: khoảng 20% do bỏ lọc mờ, cộng phần cào bù theo sitemap (baodautu gấp đôi). Chấp nhận được với `rate_limit` hiện tại.
- Số bài vào Article Lane tăng. Token không tăng tương ứng nhờ cụm hoá trùng lặp (đề xuất dedup P2).
- Cấu hình `fuzzy_dedup` ở bộ cào bị gỡ. Tham số chuyên mục chỉ còn quyết định thứ tự cào, không quyết định phạm vi.

## Phương án đã loại

- **Giữ lọc mờ ở tầng cào nhưng nâng ngưỡng.** Vẫn bỏ bài không dấu vết, vẫn mất tín hiệu tần suất.
- **Chỉ cào chuyên mục tài chính.** Tin vĩ mô, chính sách, doanh nghiệp nằm rải ở nhiều chuyên mục. Phân loại là việc của bước xử lý.
