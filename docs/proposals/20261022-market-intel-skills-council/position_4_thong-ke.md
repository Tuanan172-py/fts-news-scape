# Vị trí 4 — Kiểm định thống kê

Sandbox 2026-10-22: 34.043 bài, 8 nguồn.

## Kết luận chính

1. **Méo lớn nhất đến từ khâu làm giàu (enrichment), không phải từ khối lượng.** Có 13.261 bài (39%) mang `intent_source=''`. Các bài này không có summary hay entity, và có `sentiment='neutral'`, `time_sensitivity='today'`; đây là giá trị mặc định, không phải nhãn LLM. Lens không loại các bài này ra, nên pulse, `is_hot`, lift và độ phủ entity đều sai một cách hệ thống.
2. Phân vị pulse gần như vô nghĩa: 95 trên 133 ngày lịch sử có `net_sent = 0`.
3. Buzz z bị sàn SD 0,5 chi phối: chỉ 2 bài trên nền 0 đã cho z = 4. Không có chuẩn hoá theo khối lượng thu thập hay theo thứ trong tuần.
4. `resolve_target` coi mọi chuỗi 3 ký tự là mã cổ phiếu. Mã `TICKER:HCM`, đang đứng đầu kho, phần lớn thực ra là TP.HCM.
5. Test chỉ phủ các trường hợp dữ liệu sạch; không có test nào cho các hành vi trên.

## Phép đo

**M1. Khối lượng và nguồn.** Số bài trung bình mỗi ngày tăng vọt theo thời gian:

| Giai đoạn | Bài/ngày | Số nguồn |
|---|---|---|
| 2025-10 đến 2026-06 | 1,3–6,5 | 1–2 |
| 2026-07 | 17,9 | 4 |
| 2026-08 | 144,6 | 7 |
| 2026-09 | 393,2 | 8 |
| 2026-10 | 838 | 8 |

Riêng cafef chiếm 49% số bài. **Không có bài nào ngày 2026-10-20.** Từ tháng 9, thứ Bảy có 1.627 bài, Chủ nhật 1.663, còn thứ Hai 6.265.

**M2. Làm giàu.**
- Nhóm `intent_source=''` (13.261 bài) đều mang neutral/today và không có summary.
- Nhóm `agent` của tháng 8 có 99,5% bài không summary và sentiment toàn neutral.
- Tỷ lệ bài được làm giàu trong ngày chỉ vượt 50% kể từ 2026-09-18; các ngày thường của tháng 10 chỉ đạt 36–69%.
- Từ 09-18, `corr(tỷ lệ làm giàu, net_sent)` = 0,665 và `corr(n_ngày, net_sent)` = −0,624. Nghĩa là net_sent theo ngày chủ yếu đo xem hôm đó được xử lý bao nhiêu bài. Ví dụ: ngày 10-12 làm giàu 36%, net 0,13; ngày 10-17 làm giàu 99,6%, net 0,49.

**M3. Pulse** (`sentiment_pulse(days=7)`).
- Ngày 10-21: net 0,234, phân vị **85,7** trên 133 kỳ. Nếu chỉ tính 28 ngày có ít nhất 50% bài được làm giàu thì phân vị chỉ là **32,1**.
- Ngày 09-15: net 0,002 (chỉ 7% bài được làm giàu), nhưng phân vị lại là **98,0**, trong khi `hot_net_sent_pctile` = 1,0.

**M4. is_hot.** Có 23.300 bài `today` và 401 bài `urgent`, nên `is_hot` đúng với 69,6% số bài; riêng ngày 10-21 là 618/1.062. Trong nhóm agent: urgent có net −0,466, today có net 0,069.

**M5. Buzz** (lookback 20, min_articles 2). Số cờ bật, kèm số cờ có mean < 1:

| Ngày | Số cờ | Cờ có mean < 1 |
|---|---|---|
| 10-19 | 11 | 6 |
| 10-21 | 19 | 14 |
| 09-10 | 14 | 10 |

- Ví dụ: TNI có 2 bài, mean 0, SD 0, cho ra z = 4,0.
- Ngày 10-19 có 1.437 bài, gấp 1,86 lần trung bình 20 ngày trước đó.
- Tôi thử chuẩn hoá: dùng Poisson trên share-of-voice, kỳ vọng = mean × N_ngày/N̄_nền, cờ khi z ≥ 3 và n ≥ 3. Khi đó số cờ còn 2/11 ngày 10-19 và 11/19 ngày 10-21 (cờ mới là tập con của cờ cũ). *Đây là đề xuất, chưa backtest.*

**M6. Vận tốc chủ đề.** Tỷ lệ m7_30 và m30_90 của toàn thị trường:

| Ngày | m7_30 | m30_90 |
|---|---|---|
| 09-10 | 1,52 | 2,66 |
| 10-05 | 1,51 | 2,09 |
| 10-21 | 0,99 | 1,89 |

- Cả 20 chủ đề đều có m30_90 từ 1,36 đến 3,0, chỉ vì kho tăng khối lượng.
- Ở ngày 09-10 hoặc 10-05, một chủ đề giữ nguyên thị phần vẫn chạm sát ngưỡng "Tăng tốc" 1,5.
- `krx` bị xếp "Tăng tốc" chỉ với n7 = 2.

**M7. Gộp tin.**
- Tỷ lệ gộp là 4,18% (32.619 story trên 34.043 bài).
- **Gộp sai:** 33 nhóm (90 bài) trải dài hơn 7 ngày, phần lớn là tiêu đề định kỳ. Ví dụ: "nhìn lại diễn biến nhóm cổ phiếu được các công ty chứng khoán khuyến nghị tuần qua" (09-11 → 10-16), "BID CBTT về giao dịch với bên có liên quan" (07-09 → 10-09).
- **Bỏ sót:** trong tháng 9–10 có 447 cặp bài khác nguồn, cùng ngày, khác story_key nhưng Jaccard theo từ ≥ 0,6. Để so sánh, chỉ có 1.020 nhóm đa nguồn được gộp. Ví dụ: F88 có 3 tiêu đề khác nhau về chuyển sàn HOSE; tin SHB/S&P; VinMetal–Danieli ("bắt tay" và "hợp tác").

**M8. Entity.**
- 65,6% số bài không có entity nào. Chỉ 20,3% bài có TICKER, và tỷ lệ này giảm từ 89,7% (tháng 6) xuống 14,4% (tháng 10).
- `TICKER:HCM` có 892 bài: 420 bài có chữ "TP.HCM" hoặc "Hồ Chí Minh" trong tiêu đề, chỉ 33 bài nhắc HSC. Lỗi đến từ cột `symbols`.
- Kind TICKER còn lẫn VNINDEX, VN30, USD-VND, GC=F.
- `resolve_target("dầu")` trả về `TICKER:DẦU` với 0 bài. FED, GDP, IPO đều cho 0 kết quả, trong khi tiêu đề có lần lượt 227, 100, 87 bài nhắc tới.
- "Mỹ", "vàng", "Vingroup" rơi vào nhánh tìm keyword bằng ILIKE thay vì khớp `MACRO_GEO:MY`, `ASSET_CLASS:VANG`, `TICKER:VIC`.

**M9. Sentiment theo nguồn** (từ tháng 9). Net dao động từ 0,109 (cafef) đến 0,457 (baodautu). Nhóm agent nghiêng dương: 7.758 bài pos so với 2.794 bài neg. Có 10 bài lưu sentiment dạng chuỗi dict, nên `sent_score` = NULL.

**M10. Thời gian.** Mọi bản ghi có offset +07:00 nên ngày đúng. 36,0% bài đăng sau 15:00, 12,2% cuối tuần, 483 bài chỉ có ngày (`T00:00:00`).

**M11. Lift.**
- `n_all` đếm cả bài không có entity: 34.026 bài, trong khi chỉ 11.703 bài có entity. Vì vậy lift bị phóng đại khoảng **2,91 lần**. Ví dụ: HPG–VIC có lift 16,09 (giá trị đúng khoảng 5,5); HPG–THEP có lift 29,76.
- Không có ngưỡng support tối thiểu: MY–TFC có n_co = 4, lift 9,49; MY–DPM có n_co = 3, lift 8,3.

## Lỗi/méo theo mức độ

| id | mức | phát hiện | bằng chứng | cách sửa |
|---|---|---|---|---|
| S1 | Cao | Bài chưa làm giàu bị coi là nhãn thật | `lakehouse_client.py:209-214` | Thêm cờ `is_enriched`; sentiment/hot chỉ tính trên bài đã làm giàu; mọi lens báo `enriched_share` |
| S2 | Cao | Lịch sử phân vị pulse toàn số 0 | `:763-771` | Chỉ dùng kỳ có `enriched_share` ≥ 0,8; nếu ít hơn 20 kỳ thì đặt `sufficient=false` |
| S3 | Cao | `is_hot` gồm cả `today`, chiếm 70% số bài | `:214`, `:421` | Chỉ coi `urgent` là hot |
| S4 | Cao | Lift phóng đại ~2,9 lần, không có support | `:904`, `:934` | n_all = số bài có entity; yêu cầu n_co ≥ 5, kèm khoảng tin cậy |
| S5 | Cao | HCM thực chất là TP.HCM; mọi chuỗi 3 ký tự bị coi là mã | `:280-281`, `symbols` | Đối chiếu danh mục mã niêm yết; thêm stoplist; khớp không dấu |
| S6 | TB | Sàn SD 0,5 cho z = 4 với 2 bài; không chuẩn hoá khối lượng hay thứ trong tuần | `:45`, `:691-696` | Poisson trên share-of-voice, n ≥ 3, tách nền ngày thường và cuối tuần |
| S7 | TB | Vận tốc chủ đề không chia cho tốc độ chung của thị trường | `:836-863` | Báo tỷ lệ theo share; nâng ngưỡng xét lên n7 ≥ 5 |
| S8 | TB | Bỏ sót tin cùng sự kiện nhưng tiêu đề diễn đạt khác | `:207-208` | Gộp gần đúng (Jaccard ≥ 0,6, trong ±1 ngày, có chung entity) |
| S9 | TB | Gộp nhầm tiêu đề định kỳ qua nhiều tuần | `:207-208` | Đưa ngày (hoặc cửa sổ 3 ngày) vào khoá gộp |
| S10 | Thấp | Ngày 10-20 trống nhưng không có cảnh báo | `:649-651` | Báo ngày trống trong `coverage` |
| S11 | Thấp | Tin đăng sau 15:00 và cuối tuần tính vào ngày lịch | `:206` | Thêm `trade_date` |
| S12 | Thấp | Sentiment dạng dict bị thành NULL | `:209-213` | Parse trường `polarity` |

Về test: fixture chỉ chứa bài đã làm giàu. `:267` (buzz), `:312` (chỉ kiểm lift > 1) và `:245` (resolve) đều không có ca sàn SD, ca support thấp, ca từ thường 3 ký tự hay ca tiêu đề định kỳ.

## Đề xuất ưu tiên

1. **S1–S3 trước** (thêm cờ `is_enriched`). Trong M3, phân vị 85,7 so với 32,1 cho thấy kết luận có thể đảo chiều.
2. **S4–S5:** sửa mẫu số lift, đặt support ≥ 5, áp danh mục mã và stoplist.
3. **Chuẩn hoá khối lượng (S6–S7):** tính theo share. Nền chỉ dùng dữ liệu từ 2026-09-18, tối thiểu 15 ngày thường.
4. **Gộp tin (S8–S9):** kiểm bằng 200 cặp gán nhãn tay. *Suy luận:* tỷ lệ bỏ sót có thể ≥ 30% số nhóm đa nguồn.
5. **Test hồi quy** cho S1–S9: fixture có bài chưa làm giàu, tiêu đề định kỳ, "dầu"/HCM, và cặp hiếm.
