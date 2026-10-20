---
name: news-catalyst-tracker
description: Theo dõi tiến độ một luận điểm đầu tư hoặc dự án trong 6–12 tháng (pháp lý dự án BĐS, nhà máy, lộ trình nâng hạng), đối chiếu phát ngôn trước đây với diễn biến thực tế.
---

# Theo Dõi Chất Xúc Tác (News Catalyst Tracker)

Team Cơ bản dùng khi theo một câu chuyện dài hạn có tin rải rác nhiều tháng: tiến độ Dung Quất 2, pháp lý dự án Cổ Loa, lộ trình nâng hạng. Câu hỏi cốt lõi: **thực tế đang nhanh hay chậm hơn so với những gì đã được nói?**

## 1. Khi nào kích hoạt
- *"Tiến độ dự án Dung Quất 2 của BSR đến đâu rồi?"*
- *"Theo dõi pháp lý dự án Vinhomes Cổ Loa 12 tháng qua"*
- *"Lộ trình nâng hạng thị trường đã đi được bao xa?"*

## 2. Thu thập dữ liệu (0 token)
Đối tượng là mã hoặc chủ đề, thu hẹp bằng từ khoá của dự án/luận điểm (`--keywords`, nhiều từ khoá cách nhau bằng dấu phẩy được áp dụng **cùng lúc**).
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH timeline --target BSR --keywords "Dung Quất" --days 365 --grain month
python $LH timeline --target VHM --keywords "Cổ Loa" --days 365 --grain month
python $LH timeline --target nang_hang --days 365 --grain month   # chủ đề cấu hình sẵn
python $LH timeline --target "Dung Quất" --days 365 --grain month # chỉ dùng từ khoá
```
Nếu ít kết quả, nới từ khoá (bỏ dấu, dùng tên ngắn) hoặc bỏ `--target` mã và dùng từ khoá làm đối tượng.

## 3. Phân tích
1. Lập **sổ mốc tiến độ**: mỗi story là một mốc. Gán trạng thái mốc: *Kế hoạch / Phát ngôn*, *Phê duyệt / Pháp lý*, *Triển khai*, *Hoàn thành*, *Trì hoãn / Vướng mắc*.
2. Trích **phát ngôn và cam kết** (mốc thời gian, con số, người nói) từ `key_points`, ghi rõ ngày nói.
3. Đối chiếu: với mỗi cam kết có hạn, tìm bằng chứng thực hiện ở các story sau đó. Kết luận **Đúng hạn / Chậm / Chưa có bằng chứng / Đã điều chỉnh kế hoạch**.
4. Đánh giá tốc độ chung so với kỳ vọng ban đầu.

## 4. Khuôn đầu ra
**[Đo lường]** Số bài và số story theo tháng (từ `periods`), tháng sôi động nhất.

**Sổ mốc tiến độ**

| Ngày | Trạng thái mốc | Sự kiện | Phát ngôn / Con số | Nguồn |
|---|---|---|---|---|

**Đối chiếu cam kết**

| Cam kết (ngày nói) | Hạn | Bằng chứng gần nhất | Kết luận |
|---|---|---|---|

**[Diễn giải]** Tiến độ nhanh hay chậm so với phát ngôn, rủi ro trễ hạn, mốc kế tiếp cần theo dõi.

## 5. Lưu ý
- Chỉ kết luận "chậm" khi có bằng chứng về hạn đã qua; thiếu tin thì ghi "chưa có bằng chứng", không suy đoán.
- Trích dẫn đầy đủ ngày đăng và tiêu đề cho mỗi phát ngôn.
