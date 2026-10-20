---
name: news-sentiment-pulse
description: Đo tâm lý tin tức toàn thị trường, theo ngành hoặc theo chủ đề theo ngày/tuần, tách riêng tin khẩn cấp và so với phân vị của chính nó trong 1 năm qua.
---

# Nhịp Tâm Lý Tin Tức (News Sentiment Pulse)

Team Thị trường / Kỹ thuật dùng để đo tâm lý đám đông qua tin tức: tỷ lệ tin tích cực/tiêu cực, đặc biệt nhóm tin cấp thiết (`urgent`, `today`), và vị trí hiện tại so với lịch sử 1 năm.

## 1. Khi nào kích hoạt
- *"Tâm lý tin tức thị trường tuần này thế nào?"*, *"Tin tức hôm nay bi quan hay lạc quan so với mọi khi?"*
- *"Sắc thái tin ngành Ngân hàng 30 ngày qua"*, *"Tâm lý tin về lãi suất đang ra sao?"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH pulse --days 30 --grain day                 # toàn thị trường
python $LH pulse --days 90 --grain week --target IND_GICS3:NGAN_HANG
python $LH pulse --days 30 --target lai_suat            # theo chủ đề trong config/themes.json
```
- `series`: mỗi kỳ có `n_articles`, `pos`, `neg`, `neu`, `net_sent` (từ -1 đến 1), `hot`, `hot_pos`, `hot_neg`, `hot_net_sent`.
- `latest.net_sent_pctile`, `latest.hot_net_sent_pctile`: phân vị (0–100) của kỳ mới nhất trong `history`.
- `sectors`: phân rã theo ngành GICS trong cửa sổ.
- Không biết mã ngành: `python $LH lookup --text "ngan hang"`.

## 3. Phân tích
1. Đọc xu hướng `net_sent` và `hot_net_sent` qua các kỳ, chỉ ra điểm đảo chiều.
2. Diễn giải phân vị: ≥ 90 là lạc quan cực độ so với lịch sử, ≤ 10 là bi quan cực độ, giữa là bình thường.
3. Chỉ ra 2–3 ngành kéo tâm lý lên/xuống mạnh nhất từ `sectors`.
4. Muốn biết nguyên nhân của một kỳ cực trị: gọi `timeline` hoặc `urgent` để lấy tiêu đề làm bằng chứng.

## 4. Khuôn đầu ra
**[Đo lường]**

| Kỳ | Tổng bài | Tích cực | Tiêu cực | Net sentiment | Tin cấp thiết (tích cực/tiêu cực) |
|---|---|---|---|---|---|

- Phân vị kỳ mới nhất: `net_sent_pctile` / `hot_net_sent_pctile` (trên `periods_used` kỳ lịch sử).
- Ngành nổi bật: bảng `entity_id · n_articles · net_sent`.

**[Diễn giải]** 3–5 gạch đầu dòng: trạng thái tâm lý, điểm đảo chiều, ngành dẫn dắt, mức độ cực trị.

## 5. Lưu ý
- Sentiment là sắc thái truyền thông của cả bài, không phải tín hiệu giá.
- `history.periods_used` < 60 (ngày) hoặc < 12 (tuần) thì phải ghi rõ "phân vị chưa đủ tin cậy".
