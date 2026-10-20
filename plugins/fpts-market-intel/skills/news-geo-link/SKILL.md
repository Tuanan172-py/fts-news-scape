---
name: news-geo-link
description: Với một sự kiện hoặc quốc gia/khu vực địa chính trị (Mỹ, Trung Quốc, EU, Nga, Trung Đông), tìm các ngành và mã Việt Nam từng được nhắc cùng trong 1 năm qua và tin liên quan gần nhất.
---

# Liên Kết Địa Chính Trị (News Geo Link)

Team Vĩ mô dùng để chuyển một biến cố quốc tế thành danh sách ngành/mã trong nước cần chú ý.

## 1. Khi nào kích hoạt
- *"Mỹ áp thuế mới thì ngành nào của Việt Nam bị ảnh hưởng?"*
- *"Căng thẳng Trung Quốc liên quan đến mã nào?"*, *"Xung đột Trung Đông tác động ngành nào?"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH lookup --text "my"                                   # tra mã: MACRO_GEO:MY, MACRO_GEO:TRUNG_QUOC...
python $LH cooccur --target MACRO_GEO:MY --kinds IND_GICS3,TICKER --days 365
python $LH cooccur --target MACRO_GEO:MY --keywords "thuế" --kinds IND_GICS3,TICKER
python $LH cooccur --target xung_dot --kinds IND_GICS3,TICKER,ASSET_CLASS
python $LH timeline --target MACRO_GEO:MY --keywords "thuế" --days 30 --max-stories 15
```
- `by_kind`: thực thể đồng xuất hiện với `n_co`, `lift`, `net_sent`, `latest_title`.
- `timeline` 30 ngày cho bối cảnh mới nhất của sự kiện.

## 3. Phân tích
1. Chọn ngành/mã có `n_co` ≥ 3 và `lift` > 1; xếp theo mức độ phơi nhiễm.
2. Gán **kênh tác động**: Xuất khẩu, Chuỗi cung ứng / nguyên liệu, Dòng vốn / tỷ giá, Giá hàng hoá, Tâm lý.
3. Gán chiều: Hưởng lợi / Chịu thiệt / Chưa rõ, kèm trích dẫn bài.

## 4. Khuôn đầu ra
**[Đo lường]**

| Ngành / Mã | Số bài cùng nhắc | Lift | Sentiment TB | Tin gần nhất |
|---|---|---|---|---|

**[Diễn giải]**

| Ngành / Mã | Kênh tác động | Chiều | Lý do (trích dẫn) |
|---|---|---|---|

Kết luận 2–3 câu: mức độ phơi nhiễm của thị trường Việt Nam với sự kiện.

## 5. Lưu ý
- Đồng xuất hiện trong tin là tương quan truyền thông, không phải tỷ trọng doanh thu đã kiểm chứng.
- Mẫu nhỏ (`n_target_articles` < 20) phải ghi rõ.
