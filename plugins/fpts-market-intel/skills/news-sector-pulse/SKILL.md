---
name: news-sector-pulse
description: Đánh giá nhịp đập và sắc thái tin tức theo 11 nhóm ngành GICS và xu hướng thị trường từ News Lakehouse.
---

# Kỹ Năng Nhịp Đập Ngành & Thị Trường (News Sector Pulse)

Kỹ năng này giúp chuyên viên phân tích đo lường xung lực thông tin và ma trận tâm lý theo từng nhóm ngành hoặc toàn thị trường qua các chu kỳ giao dịch gần nhất.

---

## 1. Khi Nào Kích Hoạt Kỹ Năng Này
- Chuyên viên hỏi về tổng thể thị trường: *"Tâm lý thị trường tuần qua như thế nào?", "Quét nhịp đập các ngành trong 7 ngày gần nhất"*.
- Chuyên viên hỏi về một ngành cụ thể: *"Ngành Ngân hàng dạo này tin tức ra sao?", "Ngành Bất động sản có nhiều tin xấu không?"*.

---

## 2. Quy Trình Trích Xuất Dữ Liệu (Execution Protocol)

### Bước 1: Trích Xuất Xu Hướng Sắc Thái Toàn Thị Trường
Chạy lệnh dòng lệnh để lấy thống kê phân bổ theo ngày:
```powershell
python "%USERPROFILE%\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py" sector --json
```

### Bước 2: Truy Vấn Chuyên Sâu Từng Ngành (Nếu Có Yêu Cầu Cụ Thể)
Nếu chuyên viên yêu cầu soi sâu một ngành (ví dụ: Ngân hàng, Bất động sản, Thép):
```powershell
python "%USERPROFILE%\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py" query --sql "SELECT published_at, title, symbols, summary, implication, sentiment FROM {articles} WHERE title LIKE '%ngân hàng%' OR title LIKE '%lãi suất%' ORDER BY published_at DESC LIMIT 10" --json
```

---

## 3. Quy Chuẩn Trình Bày Báo Cáo

### A. Bảng Đo Lường Nhịp Đập Thị Trường Theo Ngày
| Ngày giao dịch | Tổng số bài viết | Tích cực (`pos`) | Tiêu cực (`neg`) | Trung lập (`neu`) | Tỷ lệ Lạc quan (Net Pos %) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| `YYYY-MM-DD` | `Total` | `N` | `N` | `N` | `(Pos - Neg) / Total %` |

### B. Nhận Định Sóng Tin Tức Ngành
1. **Ngành đón sóng thông tin hỗ trợ**: Các nhóm ngành có tỷ lệ tin tích cực đột biến (ví dụ: giải ngân đầu tư công, chính sách lãi suất thấp).
2. **Ngành chịu áp lực thông tin bất lợi**: Các nhóm ngành đối mặt với tin tiêu cực gia tăng (ví dụ: áp lực nợ xấu, thanh tra, giá nguyên vật liệu đầu vào tăng).
