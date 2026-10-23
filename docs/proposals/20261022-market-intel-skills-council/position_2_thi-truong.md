# Vị trí 2 — Analyst Thị trường/Kỹ thuật

## Kết luận chính

1. **Sentiment và "tin cấp thiết" hiện bị nhiễm giá trị mặc định của bài chưa qua LLM. Đây là lỗi P0.** Mọi bài trước 2026-09-11 đều mang `neutral` + `today` và không có summary. Từ 09/2026 vẫn còn 41–51% bài như vậy (6.950 bài trong 10/2026). Vì `is_hot` gộp `today` (`lakehouse_client.py:214`), `hot_share` lên tới 0,6–1,0 ở hầu hết dòng nên gần như không còn phân biệt được gì. Phân vị của pulse cũng đang so với một năm "net_sent = 0" giả.
2. **Buzz đo tỷ lệ xử lý nhiều hơn đo độ nóng tin.** Bài chưa xử lý không có thực thể nên không được đếm. Tỷ lệ chưa xử lý dao động 0% (cuối tuần) đến 64% (12/10), nên n_today và mức nền dao động theo pipeline, không theo thị trường.
3. **z-score thiên về mã ít tin.** Sàn SD = 0,5 (`:44`) khiến mã 4 bài/nền 0,3 có z = 7,4 và đứng trên TCB 21 bài/nền 6,4 (z = 3,92). Ngày 21/10 có 19/47 mã đủ điều kiện bị gắn cờ (40%), trong đó 9 mã chỉ có ≤ 3 bài.
4. **Thời điểm chưa gắn với phiên giao dịch.** `pub_date` là ngày lịch (`:207`). Mức nền là "20 ngày có dữ liệu" (`:649`), gồm cả thứ Bảy/Chủ nhật (~270 bài/ngày so với 900–1.500 ngày thường) và bỏ qua ngày trống 2026-10-20. Có 38% bài đăng sau 14:45 nhưng vẫn tính vào phiên T.
5. **Tin đa nguồn chưa gộp đúng.** `story_key` chỉ là tiêu đề chuẩn hoá (`:208`): ngày 21/10 có 1.062 bài nhưng ra 1.010 story (chỉ gộp được 5%). Ví dụ BMS "tạm hoãn niêm yết HOSE" có 3 báo nhưng bị tính thành 3 story, mỗi story 1 nguồn.

## Bằng chứng đã chạy

| Lệnh | Kết quả đo được |
|---|---|
| `status` | `latest_day 2026-10-21`, `is_stale false`, `total_unique_articles 1062` (chỉ là của partition mới nhất, dễ hiểu nhầm). Ngày 2026-10-20 không có dữ liệu nhưng không có cảnh báo nào. |
| `query` theo tháng | `neu_share = 1.0, today_share = 1.0, no_sum = 1.0` từ 2025-10 đến 2026-08; 09/2026: 0,67/0,65/0,51; 10/2026: 0,58/0,61/0,41. Bài sentiment khác neutral đầu tiên: 2026-09-11. |
| `query` trong 10/2026 | Nhóm no_summary: `neutral·today` 6.950 bài, trung bình 0,0 thực thể và 0,03 mã/bài. |
| `query` giờ/ngày (từ 09/2026) | Trước 9:00: 4.869; 9:00–14:45: 12.868; sau 14:45: 10.819 bài. Ngày thường 500–1.561, cuối tuần 263–308 bài/ngày. |
| `buzz --top 10` (27 s) | OCB z 7,4 (n 4, nền 0,3); ABB 7,2; VND 6,4; …; TCB z 3,92 (n 21, nền 6,4, 5 nguồn). |
| `buzz --date 2026-10-19` | BMP z 7,9 (n 4, nền 0,05); LPB z 4,02, trong đó tin lan toả nhất là "vinh danh Thương hiệu… APEA" (4 nguồn, mang tính PR). |
| `buzz --top 500` | 47 mã đủ điều kiện, 19 mã gắn cờ, 9 mã có n ≤ 3. |
| `pulse --days 14` (10 s) | Net sent ngày thường 0,13–0,24, cuối tuần 0,28–0,49 (tỷ lệ bài chưa xử lý cuối tuần = 0). Ngày 21/10: `net_sent_pctile 85.7`, `hot_net_sent_pctile 96.2`. |
| `pulse --grain week` | Từ 07/2026 đến tuần 07/09, mọi tuần có net 0,000. Tuần 19/10 có `pctile 91.3/97.8`, `periods_used 46`. |
| `window VND 2026-10-21` (17,6 s) | Hai bài đăng lúc 17:48 và 21:03 vẫn mang `offset_days 0`. Tin vĩ mô hợp lý (sóng giảm lãi suất). |
| `window HPG 2026-10-20` | Ngày T không có dữ liệu nhưng không có cờ báo. `sector_entities` = THEP + **CONG_TY_CHUNG_KHOAN** (suy từ đồng xuất hiện trong báo cáo của CTCK); `sector` = 0 story. |

**Suy luận:** Top mã 21/10 đúng sự kiện (KQKD Q3, OCB đổi TGĐ, GCF bị phạt) nhưng sai thứ hạng: TCB, mã có độ phủ lớn nhất, chỉ đứng thứ 8.

## Đánh giá từng skill

| Skill | Giữ/sửa/gộp/bỏ | Lý do |
|---|---|---|
| news-buzz-radar | **Sửa** | Hữu ích nhất cho đầu phiên. Cần chuẩn hoá theo tổng tin trong ngày (share/lift), nền theo ngày giao dịch, z Poisson hoặc sàn n ≥ 3–5, đếm theo cụm sự kiện, bỏ `hot_share` tới khi `is_hot` sạch. Ngưỡng "n_sources ≥ 3" (SKILL.md:25) chưa dùng được vì story gộp kém. |
| news-sentiment-pulse | **Sửa lớn (tạm khoá phân vị)** | Net sentiment phụ thuộc vào tỷ lệ bài được LLM xử lý. Phân vị so với lịch sử toàn số 0 là sai. Chỉ nên tính trên bài đã xử lý, lịch sử bắt đầu từ 2026-09-11, `periods_used` ghi theo số kỳ đã xử lý, và tách ngày thường/cuối tuần. Bảng `sectors` đang lẫn GICS2 với GICS3 (trùng NGAN_HANG). |
| news-price-explainer | **Sửa** | Khung T-3…T+2 dùng được. Cần quy bài về phiên (sau 14:45/ngày nghỉ sang phiên kế), báo ngày T trống, dùng bảng mã→ngành cố định thay đồng xuất hiện. Lưu ý 14:45 (SKILL.md:33) mới là chữ, chưa có trong code. |
| news-daily-brief (phần buzz) | **Giữ, sửa theo buzz** | Gọi `buzz(top=5)` (`:976`) rồi mới lọc cờ, nên nhận đúng các lỗi của buzz. Cần báo `days_without_data` và tỷ lệ bài chưa xử lý ở đầu bản tin. Nên **gộp** news-buzz-radar vào news-daily-brief như một tầng, đồng thời vẫn giữ lệnh `buzz` riêng. |

## Thiếu use case

- **Trong phiên:** dữ liệu chỉ đến hết ngày hôm trước (10h ngày 22/10 vẫn chưa có bài ngày 22). Chưa có lens nào theo giờ.
- **Tin xác nhận và tin đồn:** chưa tách CBTT ("BID: CBTT…", "Nghị quyết HĐQT") khỏi bình luận, cũng chưa tách bài tổng hợp nhiều mã khỏi tin riêng (ABB, VND, CTD lên buzz nhờ bài tổng hợp).
- **Độ tươi theo phiên:** `status` chưa báo ngày trống và tỷ lệ bài chưa qua LLM.

## Đề xuất ưu tiên

**P0 (trước khi giao cho analyst)**
1. Coi bài `summary` rỗng là "chưa xử lý": loại khỏi sentiment/`is_hot`/phân vị, và báo `processed_share` ở mọi lens.
2. Buzz: chuẩn hoá theo tổng bài của ngày, nền theo ngày giao dịch, sàn n và z Poisson; báo các ngày trống trong cửa sổ nền.
3. Định nghĩa lại "tin cấp thiết" chỉ gồm `urgent` (≈ 1,4% số bài), hoặc `urgent` + `today` nhưng chỉ tính trên bài đã xử lý.

**P1**
4. Cột `session_date` (cắt lúc 15:00 giờ +07, cuối tuần và ngày lễ chuyển sang phiên kế) dùng cho buzz, window và brief.
5. Gộp story theo cụm sự kiện (mã + loại sự kiện + ngày, hoặc so tiêu đề gần giống), để `n_sources` thực sự đo mức lan toả.
6. Gắn cờ bài tổng hợp nhiều mã (> 5 mã/bài) và hạ trọng số khi tính buzz.

**P2: tối đa 3 skill mới**
1. **news-intraday-alert** (ưu tiên 1): khi ingest có độ trễ dưới 1 giờ, quét tin `urgent`/CBTT của watchlist theo giờ trong phiên.
2. **news-confirm-vs-rumor** (ưu tiên 2): phân loại theo nguồn, chia thành CBTT/HOSE/HNX, báo chí và diễn đàn, rồi theo dõi thời gian từ tin đầu tiên đến xác nhận.
3. **news-lead-lag** (ưu tiên 3, cần dữ liệu giá): đo độ trễ từ tin đến biến động giá/khối lượng; chỉ làm khi có ≥ 6 tháng dữ liệu xử lý đủ (hiện ~6 tuần).
