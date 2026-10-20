---
name: news-price-explainer
description: Giải thích nguyên nhân một phiên biến động giá mạnh (trần, sàn, khối lượng đột biến) bằng toàn bộ tin của mã, ngành và vĩ mô trong cửa sổ T-3 đến T+2 quanh ngày đó.
---

# Giải Mã Biến Động Giá (News Price Explainer)

Team Kỹ thuật và Cơ bản dùng khi nhìn chart thấy một cây nến bất thường: *"Ngày 15/05 VHM giảm sàn vì tin gì?"*. Analyst cung cấp mã và ngày; kỹ năng không có dữ liệu giá.

## 1. Khi nào kích hoạt
- *"Vì sao HPG tăng trần ngày 12/08?"*, *"Phiên 15/05 VHM giảm mạnh do đâu?"*
- *"Khách hỏi sao MWG giảm hôm qua"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH window --target VHM --date 2026-05-15
python $LH window --target VHM --date 2026-05-15 --before 5 --after 1
```
- `direct`: story của chính mã, có `offset_days` (âm là trước ngày biến động).
- `sector_entities` và `sector`: tin của ngành mà mã thường thuộc về (suy từ đồng xuất hiện 1 năm).
- `macro`: tin vĩ mô cấp thiết trong ngày T-1 và T.
- `no_direct_news = true`: không có tin riêng của mã trong cửa sổ.

## 3. Phân tích
1. Xếp hạng nguyên nhân khả dĩ: tin riêng của mã gần ngày T nhất và lan toả nhất xếp trước; sau đó tin ngành; sau đó vĩ mô.
2. Kiểm tra chiều: sentiment của tin có cùng chiều với biến động analyst mô tả không.
3. Tin sau ngày T (`offset_days` > 0) chỉ dùng để xác nhận hoặc giải thích muộn, không phải nguyên nhân.
4. Nếu `no_direct_news` và tin ngành/vĩ mô yếu: kết luận **"Không có tin giải thích"**. Bản thân điều này là tín hiệu (có thể do dòng tiền, thông tin chưa công bố).

## 4. Khuôn đầu ra
**Kết luận nhanh (1–2 câu)**: nguyên nhân khả dĩ nhất và mức độ chắc chắn (*Cao / Trung bình / Thấp*).

**[Đo lường] Bằng chứng**

| T± | Ngày | Nhóm (Mã / Ngành / Vĩ mô) | Tiêu đề | Sắc thái | Số nguồn |
|---|---|---|---|---|---|

**[Diễn giải]** Chuỗi nhân quả ngắn, các nguyên nhân thay thế, điều cần kiểm tra thêm (giao dịch nội bộ, khối ngoại…).

## 5. Lưu ý
- Không suy đoán số liệu giá; chỉ dùng mô tả biến động do analyst cung cấp.
- Tin ngày nghỉ và sau 14:45 thường tác động phiên kế tiếp.
