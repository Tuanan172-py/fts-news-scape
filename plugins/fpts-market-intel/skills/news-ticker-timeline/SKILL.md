---
name: news-ticker-timeline
description: Dựng dòng sự kiện của một mã cổ phiếu trong khoảng thời gian (từ ngày–đến ngày), gộp tin trùng, nhóm theo chủ đề và theo dõi sentiment theo tuần để chuẩn bị báo cáo cập nhật.
---

# Dòng Sự Kiện Cổ Phiếu (News Ticker Timeline)

Team Cơ bản dùng trước khi viết báo cáo Update/Initiation: *"3 tháng qua HPG có chuyện gì?"*. Kỹ năng trả về dòng thời gian story (đã gộp bài trùng tiêu đề giữa các báo), không phải danh sách bài rời rạc.

## 1. Khi nào kích hoạt
- *"Tổng hợp tin HPG từ 01/07 đến 30/09"*, *"VHM 6 tháng qua có sự kiện gì đáng chú ý?"*
- *"Lập dòng thời gian tin tức của MWG trong quý 3"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH timeline --target HPG --from 2026-07-01 --to 2026-09-30 --grain week
python $LH timeline --target HPG --days 90 --grain week --max-stories 80
```
- Bài được chọn theo thực thể `TICKER:<MÃ>` (cột `entities` hợp nhất `symbols`), nên bắt được cả bài chỉ nhắc mã trong nội dung.
- `periods`: thống kê theo tuần (`n_articles`, `n_stories`, `pos`, `neg`, `net_sent`, `hot`).
- `stories`: mỗi story có `first_published`, `title`, `n_sources`, `sources`, `summary`, `key_points`, `implication`, `sentiment`, `url`.
- `stories_total` > số story trả về nghĩa là đã giữ lại các story lan toả nhất; nêu rõ điều này.

## 3. Phân tích
1. Phân nhóm từng story vào một trong các chủ đề: **Kết quả kinh doanh**, **Dự án / Đầu tư**, **Cổ tức / Vốn**, **Nhân sự / Quản trị**, **Pháp lý / Rủi ro**, **Ngành / Vĩ mô liên quan**, **Thị trường / Giao dịch**. Phân loại dựa trên `title`, `summary`, `key_points`.
2. Chọn 5–10 mốc quan trọng nhất (ưu tiên `n_sources` cao, tin cấp thiết, sentiment mạnh).
3. Đọc chuỗi `periods`: tuần nào nhiều tin nhất (`peak_period`), sentiment chuyển chiều ở đâu.

## 4. Khuôn đầu ra
**[Đo lường]** Bảng theo tuần: `Tuần · Số bài · Số story · Tích cực · Tiêu cực · Net sentiment`.

**Các mốc chính**

| Ngày | Chủ đề | Sự kiện (tiêu đề) | Hàm ý (`implication`) | Sắc thái | Số nguồn |
|---|---|---|---|---|---|

**[Diễn giải]**
- Câu chuyện chính của mã trong kỳ (2–3 câu).
- Thay đổi so với đầu kỳ: điều gì mới, điều gì đảo chiều.
- Điểm cần theo dõi tiếp cho báo cáo.

## 5. Lưu ý
- `coverage.window_starts_before_data = true`: báo rõ dữ liệu chỉ bắt đầu từ `data_from`.
- Sentiment gắn với cả bài; bài nhắc nhiều mã thì sentiment có thể không riêng cho mã đang xét.
