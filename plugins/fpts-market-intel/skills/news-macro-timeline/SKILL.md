---
name: news-macro-timeline
description: Dựng biên niên diễn biến một chủ đề vĩ mô, chính sách hoặc địa chính trị trong 3–6 tháng (tỷ giá, lãi suất, NHNN, thuế quan Mỹ, xung đột) theo tuần, chỉ ra lúc nóng lên, đỉnh điểm và các mốc phản ứng chính sách.
---

# Biên Niên Vĩ Mô & Địa Chính Trị (News Macro Timeline)

Team Vĩ mô dùng khi viết báo cáo chiến lược tháng/quý: nhìn lại toàn cảnh một biến số trong 3–6 tháng.

## 1. Khi nào kích hoạt
- *"Diễn biến tỷ giá 6 tháng qua"*, *"Tóm lược điều hành lãi suất của NHNN quý 3"*
- *"Căng thẳng thuế quan Mỹ diễn biến thế nào 3 tháng gần đây?"*, *"Biên niên xung đột Trung Đông"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH themes-list                                              # các chủ đề cấu hình sẵn
python $LH timeline --target ty_gia --days 180 --grain week --max-stories 80
python $LH timeline --target chinh_sach_tien_te --days 90 --grain week
python $LH timeline --target MACRO_GEO:MY --keywords "thuế" --days 180 --grain week
python $LH lookup --text "trung quoc"                               # tra mã thực thể địa chính trị
```
Chủ đề chưa có sẵn: dùng từ khoá trực tiếp (`--target "Biển Đỏ"`) hoặc đề nghị analyst bổ sung vào `config/themes.json`.

## 3. Phân tích
1. Từ `periods` (theo tuần), dựng **heatmap chữ**: mỗi tuần một mức *Nguội / Ấm / Nóng / Cao điểm* theo `n_articles` so với trung vị của chính chuỗi; ghi kèm `net_sent`.
2. Xác định các pha: bắt đầu nóng lên, đỉnh (`peak_period`), hạ nhiệt.
3. Trích **mốc chính sách** (quyết định, phát ngôn của NHNN, Bộ Tài chính, Chính phủ, Fed, chính phủ nước ngoài) và đặt cạnh pha tương ứng; ước lượng độ trễ từ lúc áp lực tăng tới phản ứng chính sách.
4. Tổng kết: câu chuyện đang ở pha nào, kịch bản tiếp theo cần theo dõi.

## 4. Khuôn đầu ra
**[Đo lường] Heatmap theo tuần**

| Tuần | Số bài | Số story | Mức nhiệt | Net sentiment | Sự kiện tiêu biểu |
|---|---|---|---|---|---|

**Mốc chính sách**

| Ngày | Chủ thể | Hành động / Phát ngôn | Pha của câu chuyện |
|---|---|---|---|

**[Diễn giải]** Diễn biến chính, các bước ngoặt, độ trễ chính sách, điểm cần theo dõi tiếp; viết được để chèn trực tiếp vào báo cáo chiến lược.

## 5. Lưu ý
- Kiểm tra `coverage.window_starts_before_data`; nếu dữ liệu ngắn hơn cửa sổ, ghi rõ.
- Mọi mốc phải có ngày đăng và tiêu đề nguồn.
