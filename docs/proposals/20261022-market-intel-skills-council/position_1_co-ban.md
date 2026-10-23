# Vị trí 1 — Analyst Cơ bản

## Kết luận chính
- **Khung skill đúng nghề, dữ liệu chưa đủ tin cậy để đưa vào báo cáo.** Có ba lỗi đo được:
  - sentiment tháng 08/2026 gần như toàn `neutral`;
  - gộp story chỉ khi tiêu đề trùng y hệt, nên tin trùng lọt qua;
  - khi cắt `max-stories`, kết quả lệch về các tin cũ nhất.
- **Độ phủ thực tế theo mã khoảng 3 tháng**: HPG có dữ liệu từ 07/2026, không phải 1 năm. Cờ `window_starts_before_data` vẫn báo `false` nên che mất giới hạn này. Catalyst "6–12 tháng" hiện chưa làm được.
- **Gán mã còn nhiễu**: khoảng 25% bài gắn HPG nhắc ≥5 mã. Có nhầm thực thể: HCM là TP.HCM, HRC là thép HRC. Sentiment của cả bài bị quy cho mã sai chiều.
- **Thiếu use case cốt lõi** dù dữ liệu đã có: mùa KQKD, sự kiện doanh nghiệp (cổ tức/phát hành/ĐHCĐ/nội bộ), so sánh cùng ngành.

## Bằng chứng đã chạy
Các lệnh dưới đây chạy `lakehouse_client.py` ngày 22/10/2026. "BC n" là mục số n.

1. `timeline --target {HPG,FPT,VCB,VHM,MWG} --days 90 --grain month --max-stories 40`
   - Cả 5 mã: tháng 08 có pos = neg = 0. Ví dụ HPG tháng 08: 47 bài, neu 47, hot 47.
   - 40 story trả về dồn vào giai đoạn 24/07 đến đầu 08. HPG: 27/40 story có `n_sources = 1`, không story nào quá 2 nguồn.
   - Trùng lặp: "HPG: Báo cáo tình hình **Q**uản trị…" (29/07) và "…**q**uản trị…" (30/07) thành 2 story.
   - Nhiễu: "DMX: Cổ phiếu tân binh…" nằm trong HPG; "35 cổ phiếu tăng trần" nằm trong FPT và VCB.
2. `query`, dữ liệu tháng 08:
   - Sentiment: `neutral` 4.477 bài, còn lại vài chuỗi dict `{'overall': 0.8, 'polarity': 'positive'}` không khớp CASE (`lakehouse_client.py:209-213`).
   - `time_sensitivity = today` ở 4.484/4.484 bài, nên `is_hot` bị thổi phồng.
3. `intent_source` thực tế chỉ có `agent` 17.521, `code_first` 2.913, `inherited` 348, rỗng 13.261. `rules/AGENTS.md:14-16` đòi `BOTH/LLM_ONLY/CODE_ONLY`, nên không thực thi được.
4. `timeline --target HPG --days 365`: kỳ đầu tiên có dữ liệu là 2026-07 (6 bài); 10/2025–06/2026 không có bài nào.
5. Catalyst:
   - `BSR` + "Dung Quất": 7 story, chỉ trong 09–10/2026.
   - `VHM` + "Cổ Loa": 0.
   - "Dung Quat" (không dấu): 0, trái với lời khuyên "bỏ dấu" ở `news-catalyst-tracker/SKILL.md:24`.
   - "Hòa Phát" ra 93, "Hoà Phát" ra 3, do lọc `ILIKE` thô (`lakehouse_client.py:311,315`).
   - Cùng sự kiện nhà máy thép ray có 3 tiêu đề khác nhau nên thành 3 story.
6. `cooccur --target gia_thep --days 365`:
   - Tốt: HPG n_co 65 / lift 23,95; NKG 14 / 70,4; HSG 9 / 35,0.
   - Nhiễu: `TICKER:HCM` đi với tin "hợp long cầu… sông Sài Gòn"; `TICKER:HRC` đi với tin "thuế CBPG thép HRC"; VIC lọt vào qua cụm "lồng thép".
   - `giá cước`: chỉ 23 bài, và FPT lọt vào qua "giá cước truyền hình".
7. `ticker --symbol VCB --limit 8`: 6/8 bài là tin lãi suất/ngành chung. Bài đầu tiên gắn `positive`, nhưng `key_points` ghi "VCB… chịu áp lực bán ròng".
8. `query` đếm tiêu đề 08–10/2026: cổ tức 463, phát hành/chào bán 526, người nội bộ 163, KQKD/BCTC 94, ĐHĐCĐ 52. Tiêu đề CBTT có dạng `MÃ: …`.
9. `timeline --target HPG,HSG,NKG` bị hiểu thành từ khoá, ra 0 story. Không so sánh được nhiều mã.
10. `brief --watchlist HPG,VCB,FPT,MWG,VHM`: FPT có 16 story, mở đầu bằng "KQKD 9 tháng". HPG và MWG mỗi mã chỉ 2 story, đều là tin tổng hợp nhiều mã.

## Đánh giá từng skill

| Skill | Quyết định | Lý do |
|---|---|---|
| news-ticker-timeline | **Sửa (P0)** | Đúng use case báo cáo Update. Lỗi: cắt story theo thứ tự `first_published` tăng dần (`lakehouse_client.py:534-537`); gộp theo tiêu đề y hệt (`:207-208`); sentiment tháng 08 rỗng (BC 1–2). |
| news-catalyst-tracker | **Sửa** | Phép đối chiếu "phát ngôn với thực tế" có giá trị nhất. Nhưng "6–12 tháng" vượt quá dữ liệu (BC 4), và lời khuyên bỏ dấu là sai (BC 5). |
| news-sector-impact | **Giữ, sửa nhẹ** | Lift cho HPG/NKG/HSG đúng trực giác. Cần lọc thực thể nhầm (HCM, HRC) và thu hẹp từ khoá `thép` (BC 6). |
| news-ticker-screener | **Gộp vào timeline** | Trigger "dạo này HPG có tin gì" (`SKILL.md:13`) trùng timeline 7 ngày. Lens `ticker` không gộp story; cột `BOTH/LLM` (`:51`) không có trong dữ liệu; đầu ra nhiễu (BC 3, 7). |
| news-daily-brief | **Giữ** | Dùng được cho mã có tin riêng (FPT). Cần ưu tiên tin "mã chính" hơn tin tổng hợp (BC 10). |

## Thiếu use case
Phần này là suy luận nghiệp vụ; dữ liệu sẵn có lấy từ BC 8.
- **Mùa KQKD** (đang diễn ra Q3): mã nào trong watchlist hoặc ngành đã công bố KQKD 9T, kết quả tăng hay giảm.
- **Sự kiện doanh nghiệp**: GDKHQ cổ tức, phát hành, ĐHCĐ, giao dịch người nội bộ (ví dụ "MWG: Thông báo giao dịch… Nguyễn Đức Tài"). Mục này bắt buộc trong báo cáo Update.
- **So sánh đối thủ cùng ngành**: HPG với HSG/NKG (BC 9).
- **Sổ guidance của ban lãnh đạo** theo mã (kế hoạch LN, cổ tức, capex) để đối chiếu với KQKD. Catalyst hiện chỉ làm được theo từng dự án.
- **Dự báo của CTCK khác** (ví dụ "Shinhan dự báo LNST HPG +56%") để tham chiếu consensus, gắn nhãn là ý kiến bên thứ ba.
- **Trigger** còn thiếu các cụm analyst hay dùng: "KQKD", "BCTC Q3", "ĐHĐCĐ", "GDKHQ", "chốt quyền", "nội bộ mua/bán", "so với cùng ngành".

## Đề xuất ưu tiên
**P0 — sửa lens/dữ liệu (chặn mọi skill Cơ bản)**
1. Gắn cờ chất lượng theo kỳ (tỷ lệ neutral/today bất thường) và chuẩn hoá sentiment dạng dict. Nếu kỳ không có sentiment thì ghi "không khả dụng", không in net_sent 0.
2. Thêm độ phủ theo đối tượng: `first_article_for_target`.
3. Cắt story theo hot → mới nhất → trải đều theo kỳ. Gộp story theo mã + ngày ±1 + độ tương đồng tiêu đề.
4. Thêm `n_symbols` và cờ "mã chính" (mã nằm trong tiêu đề). Mặc định loại bài có ≥5 mã.
5. Chuẩn hoá dấu khi lọc từ khoá. Sửa `rules/AGENTS.md:14-16` theo giá trị `intent_source` thật.

**P1 — skill mới (xếp theo giá trị)**
1. **`news-corporate-actions`**: lọc cổ tức/phát hành/ĐHCĐ/nội bộ/nhân sự bằng regex tiêu đề CBTT, 0 token, theo mã hoặc watchlist và khoảng ngày. Dữ liệu dồi dào (BC 8); analyst hiện phải chép tay mục này.
2. **`news-earnings-season`**: theo ngành hoặc watchlist, liệt kê mã đã công bố KQ quý, con số lấy từ `key_points`, so với kế hoạch nếu bài có nhắc.
3. **`news-peer-compare`**: `--target` nhận danh sách mã, xuất bảng số story, tỷ lệ tốt/xấu, chủ đề chính và các mốc khác biệt giữa các mã.

**P2**
- Gộp screener vào timeline.
- Catalyst: thêm sổ guidance; sửa mô tả thành "trong phạm vi dữ liệu".
- Sector-impact: blacklist thực thể nhầm; thu hẹp từ khoá trong `themes.json`.
- Mở rộng trigger theo các cụm ở mục Thiếu use case.
