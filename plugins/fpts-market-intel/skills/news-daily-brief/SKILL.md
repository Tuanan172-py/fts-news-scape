---
name: news-daily-brief
description: Tổng hợp bản tin sáng (Morning Brief) hoặc bản tin cuối ngày từ News Lakehouse, lọc các sự kiện khẩn cấp và theo dõi danh mục cá nhân.
---

# Kỹ Năng Lập Bản Tin Thị Trường (News Daily Brief)

Kỹ năng này giúp chuyên viên phân tích tự động tạo bản tin giao ban sáng (Morning Brief) hoặc tổng kết cuối ngày một cách có cấu trúc, chắt lọc từ toàn bộ các nguồn tin tức tài chính chính thống đã qua kiểm định chất lượng Gold.

---

## 1. Khi Nào Kích Hoạt Kỹ Năng Này
- Chuyên viên gõ lệnh hoặc yêu cầu: *"Tổng hợp Morning Brief hôm nay"*, *"Điểm tin thị trường sáng nay"*, *"Bản tin đầu ngày có sự kiện gì quan trọng?"*.
- Chuyên viên yêu cầu lọc tin khẩn cấp: *"Có tin gì nóng cần chú ý trong phiên không?"*.

---

## 2. Quy Trình Trích Xuất Dữ Liệu (Execution Protocol)

### Bước 1: Trích Xuất Tin Tức Khẩn Cấp
Chạy lệnh dòng lệnh để lấy danh sách tin tức có độ nhạy thời gian cao nhất (`urg`, `today`):
```powershell
python "%USERPROFILE%\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py" urgent --limit 25 --json
```

### Bước 2: Phân Loại & Lọc Trùng Lặp Sự Kiện
Nhóm các bài viết thu được thành 3 khối nghiệp vụ:
1. **Khối Vĩ Mô & Chính Sách**: Lãi suất điều hành NHNN, tỷ giá USD/VND, thanh khoản thị trường, chính sách thuế, gói tín dụng.
2. **Khối Doanh Nghiệp Trọng Tâm**: BCTC quý, biến động nhân sự cấp cao, trả cổ tức tỷ lệ cao, giao dịch cổ đông lớn, dự án trúng thầu.
3. **Khối Cảnh Báo Rủi Ro**: Khởi tố, thanh tra, xử phạt vi phạm pháp luật/thuế, giải chấp cổ phiếu lãnh đạo, tranh chấp hợp đồng.

---

## 3. Cấu Trúc Trình Bày Bản Tin Chuẩn FPTS

```markdown
# FPTS MORNING BRIEF — ĐIỂM TIN ĐẦU NGÀY
*Ngày: YYYY-MM-DD | Nguồn: FPTS News Lakehouse Intelligence*

---

### I. ĐIỂM NÓNG VĨ MÔ & THỊ TRƯỜNG CHUNG
- **Tiêu đề / Sự kiện**: [Nội dung tóm tắt ngắn]
  - *Hàm ý*: [Tác động tới thanh khoản thị trường hoặc nhóm ngành liên quan]

---

### II. DOANH NGHIỆP TRỌNG TÂM TRONG PHIÊN
| Mã CP | Sự kiện chính | Sắc thái | Hàm ý thị trường / Tác động giá |
| :---: | :--- | :---: | :--- |
| **HPG** | Ký kết hợp đồng xuất khẩu sang thị trường mới... | `pos` | Kỳ vọng cải thiện biên lợi nhuận Q4. |
| **VCB** | Công bố ngày đăng ký cuối cùng nhận cổ tức... | `pos` | Dòng tiền hỗ trợ giữ nhịp chỉ số. |

---

### III. CẢNH BÁO RỦI RO & SỰ KIỆN ĐỘT BIẾN (WATCHOUT)
- [Cảnh báo rủi ro về doanh nghiệp hoặc mã cổ phiếu có tin tức tiêu cực đáng kể]
```
