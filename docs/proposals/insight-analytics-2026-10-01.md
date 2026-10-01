# Đề xuất hướng khai thác insight từ dữ liệu tin (2026-10-01)

> Trạng thái: **đề xuất, chờ duyệt**. Góc nhìn: data analyst khám phá dữ liệu hiện có.
> Số liệu minh hoạ đo trên DB vận hành (chỉ đọc), 11.591 bài từ 01/09, trong đó 3.873 bài có kết quả nhận diện thực thể và 3.120 bài có phân tích nội dung. Các con số minh hoạ **chưa được kiểm chứng với giá hay khối lượng giao dịch**. Đây là hướng đi, chưa phải tín hiệu dùng được ngay.
> Liên quan: `docs/proposals/dedup-architecture-2026-10-01.md` (cụm trùng là đầu vào), ADR 0013 (thu thập trọn vẹn).

## 1. Dữ liệu đang có

| Trường | Nguồn | Độ phủ |
|---|---|---|
| tiêu đề, nội dung, nguồn, thời điểm đăng | `articles` | toàn bộ |
| thực thể: mã CP, ngành GICS3, chỉ số, vĩ mô, loại tài sản | `l1_outputs` (mô hình) | khoảng 33% |
| tóm tắt, luận điểm, hàm ý, `sentiment`, `time_sensitivity`, trích dẫn | `agent_outputs` (mô hình) | khoảng 27% |
| cụm trùng, vai trò trong cụm | chưa có (dedup P1) | |
| giá, khối lượng giao dịch | **chưa có** | |

Ranh giới theo AGENTS.md §6.C: các phép **đếm, gộp, chuẩn hoá thống kê** trên kết quả đã có là việc cơ học, script làm, 0 token. Mọi trường **ngữ nghĩa mới** (ví dụ cờ bài PR) phải do `article-processor` sinh ra và là thay đổi hợp đồng (Cấp 3).

## 2. Sáu hướng tiếp cận

### H1. Chú ý truyền thông bất thường

**Ý tưởng.** Số bài nhắc tới một mã hay một chủ đề tăng đột biến so với mức nền của chính nó. Đây đúng là ý "báo chí đẩy tần suất đăng tin" mà người dùng nêu.

**Cơ sở.** Da, Engelberg và Gao (2011, *In Search of Attention*): chú ý tăng đi trước áp lực mua ngắn hạn rồi đảo chiều. Barber và Odean (2008): nhà đầu tư cá nhân mua ròng cổ phiếu "gây chú ý". Fang và Peress (2009): cổ phiếu ít được báo chí nhắc có lợi suất cao hơn (phần bù bị lãng quên).

**Chỉ số.**
- `ama_z`: z-score số bài mỗi ngày theo mã, so với nền 20 ngày, chuẩn hoá theo thứ trong tuần (cuối tuần chỉ còn khoảng 190 bài/ngày so với khoảng 500).
- `breadth`: số nguồn khác nhau đưa tin. Một nguồn đăng 5 bài khác với 5 nguồn mỗi nguồn 1 bài.
- `share`: tỷ trọng của mã trên tổng số bài trong ngày. Dùng tỷ trọng để chỉ số không tăng giả mỗi lần thêm nguồn mới.
- `silence`: mã trong watchlist không có bài nào trong N ngày.

**Minh hoạ (25–29/09 so với nền từ 02/09):**

| Mã | z | Bài/ngày gần đây | Nền | Số nguồn | Sentiment |
|---|---:|---:|---:|---:|---|
| KOS | 7,5 | 4,0 | 0,2 | 4 | 9 tiêu cực, 3 trung tính |
| PVT | 6,6 | 7,3 | 0,5 | 8 | 6 tích cực, 9 tiêu cực |
| NT2 | 4,5 | 2,3 | 0,1 | 5 | 5 tích cực |
| VGC | 4,5 | 2,7 | 0,2 | 5 | 6 tích cực |
| GMD | 3,4 | 3,7 | 0,5 | 6 | 6 tích cực, 1 tiêu cực |

KOS là trường hợp "chú ý tăng mạnh, nhiều nguồn, tiêu cực áp đảo", đúng loại cảnh báo người dùng cần thấy đầu ngày.

### H2. Tin cũ đăng lại và tốc độ lan truyền (dựa trên cụm trùng)

**Ý tưởng.** Cùng một tin được nhiều trang đăng lại không thêm thông tin, nhưng thêm lượt tiếp xúc với nhà đầu tư.

**Cơ sở.** Tetlock (2011, *All the News That's Fit to Reprint*): thị trường phản ứng thái quá với tin cũ được đăng lại, rồi đảo chiều. Phản ứng mạnh hơn ở cổ phiếu có nhiều nhà đầu tư cá nhân, một đặc điểm của thị trường Việt Nam.

**Chỉ số** (cần bảng cụm của dedup P1):
- `stale_ratio`: tỷ lệ bài `copy` hoặc `same_event` không có `novelty` trên tổng số bài của mã trong ngày.
- `cascade_minutes`: thời gian từ bài đầu tiên tới bài thứ 3 trong cụm.
- `n_updates`: số bản cập nhật có tin mới. Câu chuyện còn sinh diễn biến hay đã bão hoà.
- `first_source`: nguồn nào đưa trước.

Đây là lý do kỹ thuật cho chốt "không xoá bài trùng": `stale_ratio` và `cascade_minutes` chỉ tính được khi giữ đủ mọi thành viên cụm cùng nguồn và thời điểm.

### H3. Sentiment có hiệu chỉnh

**Ý tưởng.** Sentiment thô bị lệch theo nguồn và theo số lần đăng lại. Cần tách hai thứ.

**Lệch theo nguồn (đo được):**

| Nguồn | Số bài | Tích cực | Tiêu cực |
|---|---:|---:|---:|
| baodautu.vn | 297 | 66% | 14% |
| fireant.vn | 65 | 63% | 8% |
| thoibaotaichinhvietnam.vn | 188 | 54% | 14% |
| vneconomy.vn | 432 | 52% | 16% |
| cafef.vn | 1.223 | 42% | 21% |
| vietstock.vn | 348 | 40% | 27% |

Một bài "tích cực" từ baodautu mang ít thông tin hơn một bài "tích cực" từ vietstock. Thêm nguồn có giọng tích cực sẽ làm chỉ số sentiment chung tăng giả.

**Chỉ số.**
- `net_sent_story`: mỗi câu chuyện một phiếu, lấy từ bài gốc và các bản cập nhật. Đo **sự thật** tốt hay xấu.
- `net_sent_volume`: mỗi bài một phiếu. Đo **mức khuếch đại**.
- Chênh lệch giữa hai chỉ số trên cho biết báo chí đang thổi phồng hay đang dìm một câu chuyện.
- `net_sent_norm`: trừ mức nền của từng nguồn trước khi gộp.
- `dispersion`: độ phân tán sentiment giữa các nguồn cho cùng một mã. Phân tán cao là dấu hiệu bất định. PVT là ví dụ: 6 tích cực, 9 tiêu cực trong 3 ngày.
- `sent_shift`: thay đổi `net_sent_norm` giữa hai cửa sổ liên tiếp. Bắt điểm đảo chiều.

**Cơ sở.** Tetlock (2007, *Giving Content to Investor Sentiment*): mức bi quan trong báo chí dự báo áp lực giảm giá rồi hồi phục.

### H4. Chủ đề và câu chuyện nổi lên

**Ý tưởng.** Theo dõi tỷ trọng của từng chủ đề vĩ mô, ngành hoặc chính sách theo thời gian, và phát hiện chủ đề bùng lên. Ví dụ "nâng hạng thị trường chứng khoán", "nhà ở xã hội", "HNX chuyển sang HOSE".

**Cơ sở.** Shiller (2019, *Narrative Economics*): câu chuyện lan truyền như dịch bệnh và dẫn dắt hành vi. Kleinberg (2002): thuật toán phát hiện bùng nổ trên chuỗi thời gian sự kiện.

**Cách làm.** Dùng luôn mã thực thể mô hình đã gán (`IND_GICS3:*`, `MACRO*`, `ASSET_CLASS:*`) làm chủ đề, không cần trường LLM mới. Tính tỷ trọng ngày, chạy phát hiện bùng nổ, ra bản đồ nhiệt ngành theo tuần.

### H5. Mạng liên kết thực thể

**Ý tưởng.** Hai mã thường xuyên được nhắc chung trong một bài là có liên kết kinh tế: chuỗi cung ứng, cùng hệ sinh thái, cùng chịu một chính sách. Khi một mã có tin xấu, các mã liên kết là ứng viên chịu lan truyền.

**Cơ sở.** Scherbina và Schlusche (*news-implied linkages*): cổ phiếu được nhắc chung trong tin có lợi suất lan truyền với độ trễ. Hoberg và Phillips: mạng ngành dựng từ văn bản.

**Chỉ số.** Đồ thị đồng xuất hiện theo cửa sổ 30 ngày, trọng số PMI. Theo dõi độ trung tâm thay đổi và cạnh mới xuất hiện (hai mã lần đầu được nhắc chung).

### H6. Thời điểm và nguồn

**Phân bố giờ đăng (đo được, 3.873 bài có thực thể):**
- 23% đăng trước giờ mở cửa (trước 9:00);
- 30% đăng sau 15:00, khi phiên HOSE đã đóng lúc 14:45;
- khoảng 53% số tin tới ngoài phiên giao dịch.

**Chỉ số.**
- Gắn mỗi tin vào phiên chịu tác động đầu tiên: tin sau 14:45 tính cho phiên hôm sau. Đây là điều kiện bắt buộc trước khi làm H7.
- **Độ trễ từ công bố chính thức tới báo chí**: tin công bố thông tin (tiêu đề dạng `MBB: Nghị quyết HĐQT…`) so với bài phân tích cùng sự kiện. Đo nguồn nào đi trước, nguồn nào chỉ đăng lại.
- **Điểm tin cậy nguồn**: tỷ lệ đưa trước, tỷ lệ bài gốc trên bài chép, độ lệch sentiment.

## 3. Kiểm chứng: điều kiện để thành tín hiệu

### H7. Event study với giá và khối lượng

Mọi chỉ số ở trên chỉ là mô tả cho tới khi được đối chiếu với thị trường. Kho chưa có bảng giá. Cần:

1. Một bảng OHLCV ngày (và khối lượng khớp) cho toàn bộ mã niêm yết. Nguồn ứng viên: API dữ liệu mà các bộ cào fireant, vndirect đang dùng. Cần xác minh điều khoản sử dụng.
2. Câu hỏi kiểm chứng đầu tiên, đơn giản nhất: `ama_z` hôm nay có dự báo khối lượng bất thường phiên kế tiếp không. Theo tài liệu, đây là quan hệ ổn định nhất.
3. Sau đó mới kiểm tới lợi suất bất thường theo `net_sent_norm`, `stale_ratio`, `dispersion`.

Nếu không có bước này, báo cáo cho người dùng chỉ được trình bày là "mức độ chú ý" và "giọng điệu báo chí", không được gọi là tín hiệu giao dịch.

## 4. Thiên lệch cần kiểm soát

| Thiên lệch | Kiểm soát |
|---|---|
| Thêm nguồn làm số đếm tăng giả | dùng `share` và z-score theo nguồn, không dùng số tuyệt đối |
| Chỉ khoảng 27–33% số bài có kết quả mô hình | báo độ phủ đi kèm mọi chỉ số. Kế thừa kết quả cho bài trùng (dedup P2) để nâng độ phủ. Không dùng bản code-first làm đầu vào (AGENTS.md §6.B). |
| Bỏ sót ở tầng thu thập (baodautu khoảng 50%) | sửa theo ADR 0013 **trước** khi tin vào chỉ số chú ý |
| Bài PR, quảng cáo bất động sản làm sentiment tích cực giả | đề xuất thêm cờ `is_promotional` do mô hình sinh (Cấp 3, đổi hợp đồng) |
| Ngày nghỉ, cuối tuần | nền theo thứ trong tuần, gắn tin vào phiên giao dịch kế tiếp |
| Tiêu đề hỏng làm gộp nhầm | chặn tiêu đề hỏng (dedup P0.3) |

## 5. Kiến trúc dữ liệu

Toàn bộ chỉ số là **bảng phái sinh dựng lại được**. Bảng có thể xoá và dựng lại từ `articles`, `l1_outputs`, `agent_outputs`, `cluster_members`, đúng rule 10 §2.6.

```
articles + l1_outputs + agent_outputs + cluster_members
        │
        ▼  scripts/signal_build.py  (0 token, tất định, chạy sau --finish)
signal_daily(entity_id, trade_date, n_articles, n_sources, n_stories, share,
             ama_z, stale_ratio, cascade_minutes, n_updates,
             net_sent_story, net_sent_volume, net_sent_norm, dispersion, sent_shift,
             first_source, coverage_pct)
entity_links(entity_a, entity_b, window_end, n_co, pmi)
source_profile(source, window_end, pos_rate, neg_rate, lead_rate, original_rate)
        │
        ├─ radar / ops_console: dòng "Chú ý bất thường hôm nay"
        └─ write_user_output.py: sheet "Radar chú ý" theo watchlist của từng người dùng
```

## 6. Lộ trình

| Pha | Việc | Phụ thuộc | Cấp |
|---|---|---|---|
| I1 | `signal_build.py` cho H1, H3 (phần không cần cụm), H4, H6. Sheet "Radar chú ý". | dữ liệu hiện có | 3 (bảng mới, đổi đầu ra giao hàng) |
| I2 | H2 và `net_sent_story` | dedup P1 (bảng cụm) | 2 |
| I3 | Bảng giá OHLCV và event study H7 cho `ama_z` → khối lượng | nguồn dữ liệu giá, xác minh điều khoản | 3 |
| I4 | H5 mạng liên kết, `source_profile` | I1 | 2 |
| I5 | Cờ `is_promotional`, trích khuyến nghị của công ty chứng khoán (tiêu đề dạng `TCBS:`, `VCBS:`) | đổi hợp đồng `agent-output-v2-lean` | 3 |

Thứ tự ưu tiên khuyến nghị: **ADR 0013 C1–C2 (thu thập đủ) → dedup P1 → I1 → I3**. Chỉ số chú ý dựng trên dữ liệu thiếu 50% ở một nguồn sẽ đo sai độ rộng đưa tin. Vì vậy thu thập đủ phải làm trước.

## 7. Tài liệu tham khảo

- Barber, B. & Odean, T. (2008). All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors. *Review of Financial Studies*.
- Da, Z., Engelberg, J. & Gao, P. (2011). In Search of Attention. *Journal of Finance*.
- Fang, L. & Peress, J. (2009). Media Coverage and the Cross-section of Stock Returns. *Journal of Finance*.
- Tetlock, P. (2007). Giving Content to Investor Sentiment: The Role of Media in the Stock Market. *Journal of Finance*.
- Tetlock, P. (2011). All the News That's Fit to Reprint: Do Investors React to Stale Information? *Review of Financial Studies*.
- Kleinberg, J. (2002). Bursty and Hierarchical Structure in Streams. *KDD*.
- Shiller, R. (2019). *Narrative Economics*. Princeton University Press.
- Hoberg, G. & Phillips, G. (2016). Text-Based Network Industries and Endogenous Product Differentiation. *Journal of Political Economy*.
- Scherbina, A. & Schlusche, B. Economic Linkages Inferred from News Stories and the Predictability of Stock Returns. Working paper.
