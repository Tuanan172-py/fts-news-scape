# Thiết kế — Notify: phủ TOÀN thị trường, không bỏ sót

Cập nhật: 2026-07-26 · Đối tượng: người vận hành muốn hiểu "bài nào được đẩy vào
`data/notifications/*.log` và vì sao". Code: `src/notifier/file_notify.py` `_matches()`;
cấu hình: `config/notifications.yaml`.

> Phân biệt với [03-source-strategy.md §4](03-source-strategy.md): filter **tầng scraper**
> (`filter.any`/`filter.none`) quyết định bài có **vào DB** không. Doc này nói về filter
> **tầng notify** — bài đã vào DB thì có được **đẩy alert** không.

## 1. Mục tiêu

Notify log là dòng tin để theo dõi **từng ngày**. Yêu cầu: phủ **toàn bộ thông tin thị
trường** — cổ phiếu, doanh nghiệp, cơ quan quản lý/sở ban ngành, vĩ mô, vi mô, trong nước
& quốc tế — **không bỏ sót**; chỉ loại **tin lá cải thuần** (giải trí/tai nạn/đời sống).

Bài học: bản đầu dùng `match: true` (ghi tất) → ngập lá cải, vô dụng. Bản siết chặt (chỉ 30
mã + ít keyword) → sót nhiều tin CK ngoài watchlist. Lời giải là **nhiều cách tiếp cận bổ
sung nhau**, không dựa 1 kiểu match.

## 2. Ba cách tiếp cận trong 1 engine (`_matches`)

Mỗi rule hỗ trợ 3 kiểu điều kiện (OR trong 1 rule), quét theo thứ tự:

| Điều kiện | Ý nghĩa | Giải quyết |
|---|---|---|
| `sources: [domain...]` | khớp nếu `article.source_domain` thuộc list | nguồn 100% tài chính, và **nguồn EN** (tiêu đề tiếng Anh → keyword VN vô dụng) |
| `has_symbol: true` | khớp nếu bài gắn **bất kỳ mã CK** nào | tin của mã **ngoài watchlist** (HND, BSR, SAS…) — không sót mã nào |
| `match.any: [kw...]` | substring trên `title + symbols` (lowercase) | tin kinh tế từ báo tổng hợp không gắn mã |

Rule **khớp đầu tiên thắng** → xếp từ cụ thể (watchlist) đến rộng (keyword).

## 3. Bốn tầng rule (`config/notifications.yaml`)

1. **`watchlist`** — 30 blue-chip (keyword) → highlight riêng, ưu tiên cao nhất.
2. **`symbol`** — `has_symbol: true` → mọi bài có mã, kể cả ngoài watchlist.
3. **`finance`** — `sources` ghi TẤT từ:
   - Tài chính VN chuyên biệt: cafef, fireant, vietstock, tnck, vneconomy, vndirect, vietnambiz
   - Sàn: hnx.vn, api.hsx.vn
   - **Báo lớn — ta chỉ subscribe chuyên mục kinh tế/kinh doanh** của họ nên nội dung bản
     chất là thị trường: dantri, vnexpress, tuoitre, thanhnien, znews, vietnamplus, vietnamnet
   - **Quốc tế EN**: yahoo, cnbc, fed, marketwatch, oilprice, barrons, wsj, investors
4. **`market`** — CHỈ còn **cafebiz** (home.rss trộn lá cải) đi qua ~90 từ khoá kinh tế rộng:
   chứng khoán · doanh nghiệp/vi mô (lợi nhuận, cổ đông, HĐQT, M&A) · ngân hàng/tiền tệ ·
   **cơ quan quản lý/sở ban ngành** (chính phủ, bộ tài chính, UBCK, thuế, nghị định) ·
   **vĩ mô** (GDP, CPI, lạm phát, FDI, xuất nhập khẩu) · ngành (BĐS, dầu khí, thép, hàng
   không) · quốc tế (Fed, giá dầu, phố Wall). Loại tin không keyword = lá cải.

**Vì sao chỉ cafebiz ở tầng keyword?** Mọi feed khác đều là chuyên mục kinh tế (hoặc nguồn
tài chính thuần) → ghi tất là an toàn. Riêng cafebiz lấy `home.rss` = superset trộn giải
trí/đời sống → cần keyword lọc.

## 4. Độ phủ đo trên DB thật (2787 bài, 2026-07-26)

| Phiên bản filter | Giữ |
|---|---|
| `match: true` (ghi tất) | 100% — nhưng ngập lá cải |
| Siết: watchlist + 21 keyword | 61% — sót nhiều tin CK |
| + `has_symbol` + `sources` (tài chính/quốc tế) | 88% |
| + báo chuyên mục kinh tế vào `sources` | 97% |
| + keyword tín hiệu kinh doanh cho cafebiz | **98%** |

Kết quả cuối: **giữ 2721 (98%)** — `finance` 1570, `watchlist` 1059, `symbol` 66, `market` 21+.
**Bỏ 66 (2.4%), TẤT CẢ là cafebiz lá cải thuần** (nuôi dạy con, showbiz, tai nạn, sức khỏe).
Kiểm tra: **0 bài có mã CK bị bỏ, 0 tin kinh tế bị bỏ**.

## 5. Đánh đổi & núm chỉnh

- Đẩy về 100% = thêm `cafebiz.vn` vào `sources`, nhưng lá cải quay lại (~66 bài/mẫu).
- Muốn theo dõi hẹp hơn (chỉ blue-chip) = bỏ rule `symbol` + `finance`, giữ `watchlist`.
- Thêm nguồn mới: nếu là chuyên mục kinh tế/tài chính → thêm domain vào `sources`; nếu là
  báo tổng hợp trộn nội dung → để keyword tầng `market` lo.

## 6. Câu hỏi mở

- Keyword `market` là allow-list thủ công → nguồn tổng hợp mới (nếu thêm) có thể sót vài chủ
  đề; cân nhắc đưa thẳng vào `sources` nếu feed đã là chuyên mục kinh tế.
- Chưa phân biệt mức độ ưu tiên alert (mọi tag ghi cùng định dạng). Nếu cần, thêm cột severity.
