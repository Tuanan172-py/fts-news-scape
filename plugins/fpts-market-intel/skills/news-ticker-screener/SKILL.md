---
name: news-ticker-screener
description: Soi tin tức chuyên sâu theo mã cổ phiếu (HPG, VCB, VIC...), lọc luận điểm chính, hàm ý dòng tiền và sắc thái từ News Lakehouse.
---

# Kỹ Năng Soi Tin Tức Cổ Phiếu (News Ticker Screener)

Kỹ năng này giúp chuyên viên phân tích nhanh chóng tra cứu, chắt lọc và đánh giá toàn diện các tin tức liên quan đến một hoặc nhiều mã cổ phiếu cụ thể từ News Lakehouse cục bộ.

---

## 1. Khi Nào Kích Hoạt Kỹ Năng Này
- Chuyên viên hỏi về một mã cổ phiếu: *"Dạo này HPG có tin gì mới?", "Soi tin tức mã VCB", "VIC có sự kiện gì đáng chú ý không?"*.
- Chuyên viên muốn lọc tin theo sắc thái: *"Lọc các tin tiêu cực của MWG tuần qua", "Xem tin tích cực về ngành Thép"*.

---

## 2. Quy Trình Trích Xuất Dữ Liệu (Execution Protocol)

### Bước 1: Gọi Công Cụ `lakehouse_client.py`
Chạy lệnh dòng lệnh để lấy danh sách bài viết dưới dạng JSON:
```powershell
python "%USERPROFILE%\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py" ticker --symbol <TICKER> --limit 15 --json
```
*(Nếu chuyên viên yêu cầu lọc riêng tin tích cực hoặc tiêu cực, thêm tham số `--sentiment pos` hoặc `--sentiment neg`).*

Bài được chọn theo thực thể `TICKER:<MÃ>` trong cột `entities` (hợp nhất với `symbols`), nên bắt được cả bài chỉ nhắc mã trong nội dung. Khi chuyên viên hỏi theo khoảng thời gian (*"3 tháng qua"*, *"từ ngày… đến ngày…"*), chuyển sang kỹ năng `news-ticker-timeline`.

### Bước 2: Phân Tích & Tổng Hợp Dữ Liệu
Sau khi nhận mảng JSON từ công cụ:
1. **Tính toán Chỉ số Tâm lý Ròng (Net Sentiment)**:
   - Đếm số bài `positive`, `negative`, `neutral`.
   - Kết luận xu hướng tâm lý tin tức: Tích cực lấn át, Tiêu cực rủi ro, hay Cân bằng trung tính.
2. **Lọc Luận Điểm Nổi Bật**:
   - Trích xuất các sự kiện thuộc nhóm `urg` hoặc `today` lên trước.
   - Nhặt các luận điểm định lượng từ `key_points` và `implication`.

---

## 3. Quy Chuẩn Trình Bày Báo Cáo Cho Chuyên Viên

Agent bắt buộc trình bày kết quả theo cấu trúc sau:

### A. Tóm Tắt Tâm Lý Cổ Phiếu: `<MÃ_CP>`
- **Số bài viết ghi nhận**: `N` bài (trong các ngày gần nhất).
- **Phân bổ tâm lý**: `X` Tích cực | `Y` Tiêu cực | `Z` Trung lập $\rightarrow$ **Xu hướng chung: [Tích cực / Tiêu cực / Thận trọng]**.

### B. Bảng Chi Tiết Tin Tức Trọng Tâm
| Ngày / Giờ | Tiêu đề | Luận điểm chính (`key_points`) | Hàm ý thị trường (`implication`) | Sắc thái | Nguồn gốc |
| :--- | :--- | :--- | :--- | :---: | :---: |
| `YYYY-MM-DD HH:MM` | Tiêu đề bài báo | Các luận điểm gạch đầu dòng | Tác động doanh thu/dòng tiền/thị giá | `pos`/`neg` | `BOTH`/`LLM` |

### C. Đánh Giá Tác Động Đầu Tư (Key Takeaways)
- Tóm lược trong 2–3 gạch đầu dòng các yếu tố cần lưu ý trong phiên giao dịch hiện tại hoặc kế tiếp.
