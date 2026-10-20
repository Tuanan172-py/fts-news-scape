---
name: news-buzz-radar
description: Mỗi sáng lọc ra các mã (hoặc ngành, chủ đề) có lượng tin đột biến so với trung bình 20 phiên, kèm tỷ lệ tin cấp thiết, thay đổi sentiment và độ lan toả nguồn để phân biệt sự kiện thật với tin bơm PR.
---

# Radar Mã Nóng Tin (News Buzz Radar)

Team Thị trường / Kỹ thuật dùng đầu phiên: *"Mã nào đang nóng tin bất thường?"*. Đột biến lượng tin thường đi trước hoặc cùng lúc với biến động thanh khoản.

## 1. Khi nào kích hoạt
- *"Mã nào nóng tin hôm nay?"*, *"Top cổ phiếu đột biến tin tức"*
- *"Ngành nào đang được nhắc nhiều bất thường?"*, *"Đột biến tin ngày 15/05"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH buzz --top 10                         # ngày mới nhất, mã cổ phiếu
python $LH buzz --date 2026-05-15 --top 10
python $LH buzz --kind IND_GICS3 --top 10        # theo ngành
python $LH buzz --kind MACRO_THEME --min-articles 3
```
Mỗi dòng: `z` (độ lệch so với mức nền), `n_today`, `mean_n`, `hot_share` (tỷ lệ tin cấp thiết), `net_sent`, `base_sent`, `sent_delta`, `n_sources`, `n_stories`, `top_titles`, `flag` (`z ≥ 2`).

## 3. Phân tích
Với từng mã có `flag = true`, phân loại đột biến:
- **Sự kiện trọng yếu**: nhiều nguồn độc lập (`n_sources` ≥ 3), có tin cấp thiết, tiêu đề chứa sự kiện cụ thể (KQKD, M&A, pháp lý, chính sách).
- **Nghi bơm tin / PR**: ít nguồn hoặc nhiều story gần giống nhau, nội dung quảng bá, sentiment tích cực đồng loạt mà thiếu sự kiện cụ thể.
- **Ăn theo ngành / vĩ mô**: mã chỉ xuất hiện trong tin chung của ngành (tiêu đề nhắc nhiều mã).
- **Rủi ro**: `sent_delta` âm mạnh, tin tiêu cực cấp thiết.
Khi cần thêm bằng chứng: `python $LH timeline --target <MÃ> --days 7 --grain day`.

## 4. Khuôn đầu ra
**[Đo lường]**

| Mã | Tin hôm nay | TB nền | z | Tin cấp thiết | Net sent (Δ) | Số nguồn |
|---|---|---|---|---|---|---|

**[Diễn giải]**

| Mã | Phân loại | Sự kiện chính (tiêu đề) | Gợi ý cho team kỹ thuật |
|---|---|---|---|

## 5. Lưu ý
- `baseline.sufficient = false` (ít hơn 20 ngày nền): ghi rõ "mức nền mới có N ngày, z chỉ mang tính tham khảo".
- Mức nền tính theo ngày có dữ liệu, không trừ ngày nghỉ lễ.
- Đây là tín hiệu chú ý, không phải khuyến nghị mua/bán.
