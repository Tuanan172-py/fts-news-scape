---
name: news-sector-impact
description: Khi có một tin ngành hoặc biến số đầu vào (giá thép Trung Quốc, thuế chống bán phá giá, giá cước, giá dầu), tìm các mã và ngành từng xuất hiện cùng chủ đề đó trong 1 năm qua để đánh giá ai hưởng lợi, ai chịu thiệt.
---

# Tác Động Ngành Từ Một Sự Kiện (News Sector Impact)

Team Cơ bản dùng để trả lời nhanh *"Tin X ảnh hưởng tới mã nào?"* dựa trên lịch sử đồng xuất hiện trong kho tin 1 năm, sau đó LLM gán chiều tác động.

## 1. Khi nào kích hoạt
- *"Trung Quốc giảm xuất khẩu thép thì mã nào bị ảnh hưởng?"*
- *"Giá cước vận tải biển tăng, cổ phiếu nào hưởng lợi?"*
- *"Thuế chống bán phá giá tôn mạ liên quan tới doanh nghiệp nào?"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH cooccur --target gia_thep --days 365 --kinds TICKER,IND_GICS3 --top 15
python $LH cooccur --target "giá cước" --days 365 --top 15
python $LH cooccur --target gia_thep --keywords "Trung Quốc" --days 365
python $LH timeline --target "giá cước" --days 30 --max-stories 15   # tin gần nhất làm bối cảnh
```
- `by_kind.TICKER` / `by_kind.IND_GICS3`: `n_co` (số bài cùng xuất hiện), `lift` (> 1 là liên quan hơn mức trung bình), `net_sent`, `last_date`, `latest_title`.
- Ưu tiên mã có cả `n_co` ≥ 3 và `lift` cao; `n_co` thấp là tín hiệu yếu.

## 3. Phân tích
1. Với từng mã/ngành, đọc `latest_title` và (nếu cần) `python $LH timeline --target <MÃ> --keywords "<chủ đề>" --days 365 --max-stories 5` để xác định **vai trò**: *Thượng nguồn (nhà cung cấp)*, *Hạ nguồn (người dùng đầu vào)*, *Đối thủ / Thay thế*, *Liên quan gián tiếp*.
2. Gán **chiều tác động** cho sự kiện mới: Hưởng lợi / Chịu thiệt / Trung tính, kèm lý do một câu.
3. Nêu các tiền lệ: lần gần nhất chủ đề này nóng lên, các mã đã được nhắc thế nào.

## 4. Khuôn đầu ra
**[Đo lường]**

| Mã / Ngành | Số bài cùng xuất hiện | Lift | Sentiment TB | Tin gần nhất |
|---|---|---|---|---|

**[Diễn giải]**

| Nhóm | Mã | Vai trò | Lý do (có trích dẫn) |
|---|---|---|---|
| Hưởng lợi | | | |
| Chịu thiệt | | | |

## 5. Lưu ý
- Đồng xuất hiện là tương quan truyền thông, không phải quan hệ chuỗi cung ứng đã kiểm chứng. Vai trò do LLM suy luận phải có trích dẫn bài.
- Nếu `n_target_articles` nhỏ (< 20), ghi rõ mẫu ít.
