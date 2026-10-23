# Vị trí 3 — Analyst Vĩ mô/Địa chính trị & Morning

## Kết luận chính
1. **Với cửa sổ 3–6 tháng, bộ skill vĩ mô cho kết luận sai mà không cảnh báo.** Lượng tin tăng do mở rộng thu thập, nhưng `themes` và `timeline` đếm số tuyệt đối, không chuẩn hoá theo tổng lượng tin. Cờ độ phủ chỉ xét độ dài dữ liệu, không xét mật độ.
2. **`themes.json`** bắt nhầm (từ khoá quá rộng), bỏ sót (chưa dùng thực thể có sẵn) và thiếu chủ đề lõi: khối ngoại, xuất khẩu, ngân sách, Trung Quốc.
3. **`news-daily-brief` chưa giống morning note thật.** Thiếu ba khối: quốc tế qua đêm, khối ngoại, lịch hôm nay. Tầng vĩ mô lẫn tin nhiễu, còn `is_hot` không phân biệt được tin nào gấp.
4. **`news-geo-link`** gần như trả bảng rỗng vì rất ít bài được gắn thực thể, và có lỗi gán nhầm mã.

## Bằng chứng đã chạy
**[Đo lường]** Chạy lens trên dữ liệu đến 2026-10-21:
- **Số bài theo tháng:** 2025-10..2026-06 mỗi tháng 21–155 bài; 2026-07 có 502; 08 có 4.484; 09 có 11.797; 10 có 16.759. Tổng toàn kho: n30 = 20.922, n90 = 33.286, n180 = 33.786. Suy ra **m30/90 của toàn kho ≈ 1,88**.
- **`themes`:** 18/20 chủ đề có `m30_90` từ 1,36 đến 2,5, tức chỉ phản ánh mức tăng thu thập. Lens vẫn báo `sufficient_for_90d: true`. `krx` bị gắn "Tăng tốc" dù n7 = 2. Nhãn của lens (Ổn định/Hạ nhiệt) không khớp bốn pha mà SKILL dùng.
- **`timeline ty_gia` 180 ngày, theo tuần:** chỉ 13/26 tuần có dòng; tuần trống bị bỏ, không điền 0. `window_starts_before_data: false`, nên không có cảnh báo nào. Đỉnh rơi vào tuần 2026-09-28 (54 bài), còn tháng 8 chỉ 1–16 bài/tuần.
- **Sentiment:** tin trung tính chiếm 100% ở tháng 7 và tháng 8, 67% ở tháng 9, 58% ở tháng 10. `net_sent = 0` của tháng 8 là **thiếu nhãn, không phải trung lập**.
- **Gộp story:** tháng 10 có 16.759 bài nhưng 15.880 story, tức gần như không gộp được bài giữa các báo.
- **Bắt nhầm (tiêu đề thật):**
  - `xung_dot` bắt cả "Mở rộng quyền đầu tư của đảng viên…" (do cụm "xung đột lợi ích").
  - `ban_dan` có từ khoá "chip" nên bắt cả "Blog chứng khoán: Dòng tiền chọn lọc" (do "blue-chip").
  - `gia_thep` có từ khoá "thép" nên bắt cả bài cầu đường.
- **Bỏ sót:**
  - 313 bài nhắc Iran/Hormuz/Israel, trong đó **232 bài (74%) nằm ngoài `xung_dot`**.
  - `thue_quan_my` để trống `entities` dù dữ liệu có `MACRO_THEME:THUE_THUONG_MAI`.
  - `nang_hang` bỏ qua `MACRO_THEME:NANG_HANG_TTCK` (41 bài).
- **Gắn thực thể:** chỉ 34% số bài (11.708/34.043) có thực thể.
- **`cooccur`:**
  - `xung_dot` có 462 bài nhưng chỉ 4 lần cùng xuất hiện với ngành Dầu khí; FPT đứng đầu nhờ bài "FPT mở văn phòng tại Ai Cập".
  - `MACRO_GEO:MY` kèm từ khoá "thuế" có 57 bài, chỉ ra 2 ngành, mỗi ngành `n_co = 1`. Ngưỡng `n_co ≥ 3` của SKILL vì vậy cho **bảng rỗng**.
  - `Hormuz` cho `TICKER:PPI` với lift 131,88. Đây là chỉ số PPI bị nhận nhầm thành mã cổ phiếu.
- **`brief` ngày 2026-10-21:**
  - Cửa sổ lọc theo `pub_date`, không có giờ chốt.
  - Tầng vĩ mô có 12 story, **cả 12 đều `is_hot` và `n_sources = 1`**; tỷ lệ tin "hot" của tháng 10 là 62%. Lẫn tin nhiễu như "Thần đồng AI 17 tuổi", "Chân dung… bổ nhiệm".
  - Buzz cho OCB z = 7,4 chỉ với 4 bài.
- **Kho có đủ tin cho chủ đề còn thiếu (số bài):** khối ngoại 608, xuất khẩu 705, ngân sách/nợ công 481, lợi suất 321, Trung Quốc 1.005, tiêu đề chứa Nghị định/Thông tư/Nghị quyết 591.

**[Suy luận]** Analyst chạy "biên niên tỷ giá 6 tháng" sẽ viết "áp lực tỷ giá nóng lên rõ từ tháng 9". Kết luận đó không bảo vệ được, vì chuỗi trước tháng 8 gần như trống.

## Đánh giá từng skill
| Skill | Quyết định | Lý do |
|---|---|---|
| news-macro-timeline | Sửa (P0) | Chuẩn hoá theo thị phần tin, điền 0 cho tuần trống, cảnh báo tuần thưa và giai đoạn chưa có sentiment. |
| news-theme-trend | Sửa (P0) | Tính m7/30 và m30/90 trên thị phần tin; đặt ngưỡng n7 ≥ 10 trước khi gắn "Tăng tốc"; thống nhất nhãn giữa lens và SKILL. |
| news-geo-link | Sửa, hạ kỳ vọng | Gắn thực thể quá thưa; cần danh sách đen mã trùng từ viết tắt (PPI, CPI…) và mở rộng theo từ khoá ngành. |
| news-daily-brief | Sửa (P0/P1) | Thêm giờ chốt (15h hôm trước → 7h), các khối Quốc tế qua đêm, Khối ngoại và Lịch hôm nay; lọc tin nhiễu; bỏ `is_hot` khỏi tiêu chí xếp hạng. |

## Thiếu use case
- **Lịch sự kiện sắp tới:** FOMC, NHNN, CPI/GDP của GSO, kỳ review FTSE/MSCI, ngày hiệu lực thuế. Hiện skill chỉ nhìn quá khứ.
- **Tóm lược chính sách theo cơ quan ban hành** (NHNN, Bộ Tài chính, UBCKNN, Chính phủ, Quốc hội), kèm số hiệu văn bản.
- **Đối chiếu hai chủ đề có độ trễ**, ví dụ Fed với tỷ giá, xung đột với giá dầu.

**Sửa `themes.json`:**
- Thêm thực thể có sẵn: `THUE_THUONG_MAI` cho `thue_quan_my`, `NANG_HANG_TTCK` cho `nang_hang`.
- Từ khoá cho `xung_dot`: thêm Iran, Israel, Hormuz, Gaza, Biển Đông.
- Thêm trường `exclude_keywords` (ví dụ "xung đột lợi ích", "blue-chip").
- Đổi "chip" thành "chip bán dẫn"/"vi mạch"; với `gia_thep`, chỉ giữ "giá thép" và "HRC".
- Bỏ từ khoá "Ngân hàng Nhà nước" khỏi `chinh_sach_tien_te` vì chồng lấn với `lai_suat`.
- Thêm chủ đề: `khoi_ngoai`, `xuat_nhap_khau`, `ngan_sach_no_cong`, `loi_suat_my_dxy`, `trung_quoc`, `the_che_chinh_sach`, `nong_san`.

## Đề xuất ưu tiên
- **P0:** Chuẩn hoá theo thị phần tin và cảnh báo mật độ/gián đoạn sentiment ngay trong lens (`themes`, `timeline`). Sửa `themes.json` như trên. Thêm danh sách đen mã trùng từ viết tắt.
- **P1:**
  - Nâng cấp `news-daily-brief` theo khuôn morning note thật.
  - Skill mới **#1 `news-policy-digest`**: tóm lược theo cơ quan ban hành.
- **P2:**
  - Skill mới **#2 `news-event-calendar`**: lịch sự kiện sắp tới. Cần trích xuất ngày tương lai; nên kiểm chứng khả thi trước.
  - Skill mới **#3 `news-theme-compare`**: đối chiếu hai chủ đề có độ trễ, chỉ làm sau khi xong P0.
  - Cân nhắc gộp `news-geo-link` vào skill này nếu tỷ lệ gắn thực thể không cải thiện.
