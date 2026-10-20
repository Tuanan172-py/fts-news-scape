---
name: news-theme-trend
description: Radar câu chuyện đầu tư và chủ đề vĩ mô (đầu tư công, nâng hạng, KRX, bán dẫn, lãi suất...) đang nóng lên hay nguội đi, so sánh lượng tin 7 ngày với 30 và 90 ngày.
---

# Radar Câu Chuyện Đầu Tư (News Theme Trend)

Team Vĩ mô / Chiến lược dùng để biết câu chuyện nào đang được truyền thông bơm trở lại, câu chuyện nào đã nguội, tương tự đường MA ngắn cắt MA dài của tần suất tin.

## 1. Khi nào kích hoạt
- *"Câu chuyện đầu tư nào đang nóng tuần này?"*, *"Chủ đề nâng hạng còn được nhắc nhiều không?"*
- *"Ngành nào đang được truyền thông chú ý tăng tốc?"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH themes                                    # toàn bộ chủ đề trong config/themes.json
python $LH themes --themes nang_hang,krx,dau_tu_cong
python $LH themes --kind IND_GICS3 --top 15          # xếp hạng theo ngành
python $LH themes --kind MACRO_THEME
```
Mỗi dòng: `n7`, `n30`, `n90`, `stories7`, `m7_30` (tốc độ 7 ngày / tốc độ 30 ngày), `m30_90`, `net_sent7`, `net_sent30`, `state`, `top_titles_7d`.

## 3. Phân tích
1. Phân vòng đời từng chủ đề:
   - **Hình thành / Bùng lại**: `m7_30` ≥ 1.5 và `m30_90` ≤ 1.
   - **Tăng tốc**: `m7_30` ≥ 1.5 và `m30_90` > 1.
   - **Bão hoà**: `m7_30` khoảng 0.67–1.5 và `m30_90` > 1.
   - **Thoái trào**: `m7_30` ≤ 0.67.
2. Đọc `top_titles_7d` để nêu chất xúc tác khiến chủ đề nóng lên.
3. So `net_sent7` với `net_sent30`: câu chuyện đang được kể tích cực hơn hay tiêu cực hơn.

## 4. Khuôn đầu ra
**[Đo lường]**

| Chủ đề | Tin 7N | Tin 30N | Tin 90N | m7/30 | m30/90 | Net sent 7N | Trạng thái |
|---|---|---|---|---|---|---|---|

**[Diễn giải]**
- Câu chuyện đang nổi lên (kèm chất xúc tác, có trích dẫn).
- Câu chuyện đang thoái trào.
- Gợi ý nhóm cổ phiếu liên quan (có thể gọi `news-sector-impact` để tìm mã).

## 5. Lưu ý
- `state = "Chưa đủ lịch sử"` hoặc `coverage.sufficient_for_90d = false`: nêu rõ, không kết luận vòng đời.
- Chủ đề định nghĩa bằng thực thể và từ khoá trong `config/themes.json`; analyst có thể bổ sung.
