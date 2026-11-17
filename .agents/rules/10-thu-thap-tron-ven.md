# Rule 10 — Thu thập trọn vẹn, xử lý về sau

> Bất biến cấp dự án, người dùng ghim ngày 2026-10-01. Quyết định: `docs/decisions/0013-thu-thap-tron-ven-xu-ly-ve-sau.md`.

## 1. Nguyên tắc

Nguồn có bao nhiêu bài thì lấy về bấy nhiêu. Thu thập không lọc, không bỏ, không xoá. Mọi thao tác chọn lọc (loại trùng, làm sạch, phân loại, xếp ưu tiên, quyết định có gọi LLM hay không) là bước xử lý **sau** khi bài đã nằm trong Bronze, và không bao giờ xoá bài khỏi kho.

## 2. Luật cứng

1. **Không lọc ở tầng cào.** Bộ cào không được loại bài theo độ giống tiêu đề, chuyên mục, từ khoá, độ dài hay độ liên quan. Ngoại lệ duy nhất: bản sao kỹ thuật cùng một bài (cùng URL chuẩn hoá, hoặc cùng mã bài của nguồn). Bản sao này vẫn được ghi lại thành bí danh.
2. **Mọi URL phát hiện được đều có dấu vết.** URL thấy ở listing, RSS, API hay sitemap phải được ghi vào sổ phát hiện **trước** mọi bước lọc. Không có trạng thái cuối nào mang nghĩa "đã bỏ". Trạng thái cuối hợp lệ là `captured`, `gone` (nguồn trả 404/410), hoặc `dead_letter` (lỗi có lý do, được thử lại). Biến thể URL của một bài đã có nằm ở bảng `url_aliases`, không phải một trạng thái riêng.
3. **Không bỏ sót vì giới hạn trang.** Bộ cào phân trang theo watermark: đọc tiếp cho tới khi gặp bài đã có, không dừng cứng ở trang 1. Khi máy chạy lại sau thời gian tắt hoặc ngủ, bộ cào tự bù phần thiếu.
4. **Có kênh đối chiếu độc lập.** Nguồn có sitemap, news sitemap hoặc API theo ngày thì được đối chiếu mỗi ngày. Bài có trong kênh đối chiếu mà thiếu trong kho thì được cào bù và ghi vào thước đo độ phủ thu thập.
5. **Trùng lặp là dữ liệu, không phải rác.** Bài trùng được giữ đủ nguồn, thời điểm và URL. Bài trùng có thể được miễn bước LLM bằng cách kế thừa kết quả của bài gốc, nhưng vẫn được tính vào mọi chỉ số tần suất và độ rộng đưa tin.
6. **Raw bất biến.** `raw_html` và `.meta.json` ở Bronze không bị sửa hay xoá. Dọn dẹp chỉ áp cho bảng phái sinh có thể dựng lại.

## 3. Kiểm định

- Radar có dòng **độ phủ thu thập** theo nguồn và theo ngày: số bài kênh đối chiếu báo, số bài đã có trong kho, số bài thiếu.
- Thiếu so với kênh đối chiếu > 2% trong một ngày là mục ĐỎ.
- Mọi thay đổi bộ cào phải có test chứng minh không có đường mã nào bỏ bài mà không ghi dấu vết.

## 3.1. Lệnh thực thi

```powershell
python scripts/capture_reconcile.py status                      # độ phủ theo ngày, theo nguồn
python scripts/capture_reconcile.py run --limit 100 --budget 600  # đối chiếu sitemap rồi cào bù
python scripts/capture_reconcile.py recapture --limit 100        # phục hồi Bronze đã mất
```

Morninger gọi `capture_reconcile.py run` sau mỗi chu kỳ capture. Từ 2026-11-11:

- Kênh đối chiếu: sitemap của baodautu, tnck, cafef, vneconomy, thoibaotaichinhvietnam (sitemap theo tháng), vietstock (`sitemap.xml` 37 MB, tối đa 6 giờ một lần, bỏ chuyên mục PR 4511); vietnambiz dùng trang chuyên mục có ngày (`/<chuyên mục>/trang-N.htm`).
- Cửa sổ đối chiếu tự giãn: `max(3, số ngày từ lần đối chiếu thành công trước + 2)`, tối đa 35 ngày. Máy tắt từ tối thứ Sáu thì sáng thứ Hai vẫn đối chiếu lại thứ Sáu.
- fireant và nhánh API của cafef đọc lùi theo `offset`/`PageIndex` tới mốc lần chạy đủ trước trừ 2 giờ (`src/core/catchup.py`, tối đa 14 ngày).
- Bài cào bù lấy ngày đăng từ `article:published_time` của trang (`src/core/htmldate.py`).
- Probe `capture_channels` báo khi một nguồn đối chiếu không có dòng độ phủ mới trong 24 giờ, hoặc khi một bộ cào chạm trần phân trang trong 6 giờ.
- Sitemap tháng của baodautu hỏng phía báo từ 2026-10-23 (trả "Not found act function sitemap_month"); baodautu chỉ còn phân trang theo mốc và probe sẽ báo đỏ cho tới khi báo sửa.

## 4. Phản mẫu đã gặp (2026-10-01)

| Phản mẫu | Hậu quả đo được |
|---|---|
| Loại bài theo `token_set_ratio ≥ 90` ở `base_scraper` | 439 bài bị loại trong 3 ngày, 202 bài loại nhầm, không có Bronze, không cào lại được |
| `pages_per_cycle: 1` và chỉ cào một số chuyên mục | baodautu chỉ có khoảng 50% số bài trong sitemap chính thức, đều mỗi ngày |
| Máy tắt 11–16 giờ, bộ cào chỉ đọc trang đầu | không có cơ chế bù khi chạy lại |
| Bài nổi bật lặp trên mọi trang danh sách (2026-11) | phân trang theo mốc không bao giờ gặp trang "đã biết", baodautu chạm trần 107/475 chu kỳ |
| Cào bù theo URL không đọc ngày đăng (2026-11) | 13.480 bài thiếu `published_at`, nằm ngoài mọi đợt theo ngày |
| Đối chiếu sitemap chưa từng chạy | cafef thiếu 64% và tnck thiếu 68% so với sitemap mà không ai biết |
| Bronze nằm trong thư mục đồng bộ OneDrive | 2.045 bài còn trong kho nhưng mất tệp raw, chưa rõ nguyên nhân |
