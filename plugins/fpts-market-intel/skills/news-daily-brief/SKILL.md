---
name: news-daily-brief
description: Lập bản tin sáng (Morning Brief) ba tầng từ News Lakehouse — tin của watchlist/danh mục, vĩ mô qua đêm, và các tin được nhiều báo cùng đăng nhất — kèm danh sách mã nóng tin bất thường.
---

# Bản Tin Sáng Ba Tầng (News Daily Brief)

Bàn Morning / Tư vấn dùng mỗi sáng. Thay vì liệt kê tin dàn trải, bản tin chia ba tầng theo mức liên quan và độ lan toả.

## 1. Khi nào kích hoạt
- *"Tổng hợp Morning Brief hôm nay"*, *"Điểm tin sáng cho danh mục HPG, VCB, FPT, MWG"*
- *"Có tin gì nóng cần chú ý trong phiên không?"*

## 2. Thu thập dữ liệu (0 token)
```powershell
$LH = "$env:USERPROFILE\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py"
python $LH status                                            # kiểm tra độ tươi trước khi viết
python $LH brief --watchlist HPG,VCB,FPT,MWG                 # ngày mới nhất + tin qua đêm
python $LH brief --date 2026-10-19 --watchlist HPG,VCB --lookback-days 2   # sau cuối tuần
```
- `watchlist`: story theo từng mã (tin cấp thiết và lan toả xếp trước).
- `macro`: story vĩ mô, chính sách, địa chính trị, hàng hoá không gắn mã cụ thể.
- `spread`: story được ≥ 2 báo cùng đăng, xếp theo `n_sources`.
- `buzz`: mã có lượng tin đột biến (`z ≥ 2`); xem `buzz.baseline.sufficient`.
- Không có watchlist: hỏi analyst danh mục, hoặc bỏ tầng 1 và ghi rõ.

## 3. Phân tích
1. Mỗi tầng chọn tin quan trọng nhất, gộp tin cùng sự kiện, viết 1 dòng sự kiện + 1 dòng hàm ý.
2. Ưu tiên tin `is_hot` (khẩn cấp / trong ngày) và `n_sources` cao.
3. Gắn cảnh báo cho tin tiêu cực trọng yếu (pháp lý, khởi tố, giải chấp, thua lỗ).

## 4. Khuôn đầu ra
```markdown
# FPTS MORNING BRIEF — <YYYY-MM-DD>
*Nguồn: FPTS News Lakehouse · Dữ liệu đến <data_to> · Cửa sổ <from> → <to>*

## I. Danh mục theo dõi
| Mã | Sự kiện | Sắc thái | Hàm ý | Nguồn |
|---|---|---|---|---|

## II. Vĩ mô & chính sách qua đêm
- **<Sự kiện>** — <hàm ý> *(nguồn, giờ đăng)*

## III. Tin lan toả nhất
| Sự kiện | Số báo đăng | Báo đăng đầu tiên | Sắc thái |
|---|---|---|---|

## IV. Mã nóng tin bất thường
| Mã | Tin hôm nay / TB nền | z | Sự kiện chính |
|---|---|---|---|

## Cảnh báo
- <tin tiêu cực trọng yếu, nếu có>
```

## 5. Lưu ý
- `status.is_stale = true`: đặt cảnh báo dữ liệu cũ ở đầu bản tin.
- Không đưa khuyến nghị mua/bán; chỉ tóm lược tin và hàm ý có trong dữ liệu.
