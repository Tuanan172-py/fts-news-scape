# Ideator A: Retrieve-then-choose (sinh ứng viên, rồi Jev Choice)

Nhãn: [S] có nguồn · [V] đã kiểm tại máy ngày 24/09 · [I] suy luận. Tài liệu này không gọi Jev, không ghi DB, không chạy pipeline.

## 0. Dữ kiện nền

- [V] Kho `entities.json` có 1262 thực thể, trong đó 1093 TICKER. Thuộc tính ticker có `gics1/2/3`, `tier` (742 ở tier 1, 351 ở tier 2) và `market_cap_bil`. Trường `exchange` rỗng ở cả 1093 mã, nên không chia shard theo sàn được.
- [V] Cỡ nhóm ticker: GICS1 lớn nhất là Công nghiệp với 237 mã, vừa dưới trần 255. GICS3 có 50 nhóm, nhóm lớn nhất 84 mã (Thực phẩm, Xây dựng). 42 mã không có GICS1 (giá trị None hoặc nan).
- [V] Nếu mỗi option mang `what` (canonical_name) và 3 alias thì 1093 option dài khoảng 120K ký tự, tức khoảng 110 ký tự mỗi option.
- [S] Jev choice nhận tối đa 255 option và trả probabilities cùng confidence. Noul trả P(có). Jev không trích span và không tự chọn nhiều nhãn. Trần là 64K tổng và 32K cho state cộng câu dài nhất. Giá $0.042 cho 1M input.
- [I] Chưa đo tokenizer của Jev với tiếng Việt. Ước lượng tạm 1 token cho 2–3 ký tự, nên một shard 237 option khoảng 26K ký tự, tức 9–13K token. Shard này có thể chạm trần 32K nếu trần tính cả option. Cần đo trước.
- Ràng buộc quản trị (AGENTS.md §6): trích xuất thực thể là vùng độc quyền của `article-processor`; bộ sinh ứng viên bằng code không được biến thành bộ nhận diện; đầu ra Jev chỉ là tín hiệu kiểm như `code_first`, không tính là "đã phân tích"; thêm nhà cung cấp là việc Cấp 3, cần ADR.

## 1. Brainstorm rộng (12 hướng, chưa lọc)

- (1) Choice trực tiếp trên GICS3/GICS2/GICS1 kèm NONE. (2) Alias fold sinh ứng viên, Jev gỡ nhập nhằng. (3) LLM trả mention, code truy hồi top-K, Jev chọn. (4) Tìm theo tầng type → GICS1 → GICS3 → ticker.
- (5) 5–12 shard ≤255 theo GICS1, hỏi song song, vòng chung kết. (6) Noul cho từng thực thể trong nhóm nhỏ vĩ mô/định chế/chỉ số/tài sản (khoảng 37). (7) D7: hỏi thực thể nào là chủ thể chính của tiêu đề. (8) Xác nhận `unlisted_candidates` thật sự không có trong kho.
- (9) Dò khoảng trống alias khi Jev chọn NONE mà mention rất giống một thực thể. (10) Đảo thứ tự option để đo độ lệch vị trí. (11) Chia shard theo vốn hoá (tier). (12) Hỏi cặp đôi "A hay B" cho các cặp hay nhầm (Vinaconex với Vinaconex 21/25).

## 2. Phát triển sâu (6 ý)

### A1. Gắn ngành GICS bằng Choice cộng Noul. Độ sơ khai: sẵn thử
- **Mô tả.** Ngành GICS là ứng dụng "đẹp" nhất vì cả 3 tầng đều vừa trần 255: 11, 28 và 51 thực thể ngành (50 nhóm GICS3 có ticker). Tiêu đề hay nói về ngành mà không nêu tên ngành, ví dụ "Đề xuất áp dụng giá bán lẻ điện theo khung giờ" [V, W365] thuộc ngành Điện. Alias fold phải bỏ từ trần "điện" vì trùng nghĩa (`_context_guards.yaml`), nên dễ hụt. Jev đọc cả câu nên không phụ thuộc từ khoá.
- **Luồng.** Mỗi bài gồm tiêu đề và đoạn đầu (tối đa 2 đoạn).
  1. Hỏi choice GICS3 (51 option cộng NONE) để lấy ngành chính.
  2. Hỏi noul cho top 5 ngành theo xác suất để có nhiều nhãn.
  3. Code kiểm GICS1/GICS2 cho nhất quán với cây ngành.
  4. So kết quả với ngành LLM đã gắn (`IND_*`) để ra ba nhãn: đồng ý, LLM thiếu, LLM thừa.
- **Câu hỏi mẫu:**
```json
{"state":"Tiêu đề: Đề xuất áp dụng giá bán lẻ điện theo khung giờ\nĐoạn 1: ...",
 "questions":{"nganh_chinh":{"type":"choice","question":"Bài báo này chủ yếu nói về ngành kinh tế nào?",
   "options":[{"id":"IND_GICS3:DIEN","what":"Ngành điện: phát điện, truyền tải, giá điện, EVN, điện mặt trời",
      "not_for":"điện thoại, tàu điện, diễn biến","examples":["giá bán lẻ điện","nhiệt điện than"]},
     {"id":"IND_GICS3:NUOC","what":"Cấp thoát nước sạch","not_for":"trong nước, nhà nước, nước ngoài"},
     {"id":"NONE","what":"Không nói về một ngành cụ thể (vĩ mô chung, xã hội, chính trị)"}]},
  "co_DIEN":{"type":"noul","question":"Bài này có liên quan trực tiếp tới ngành điện không?"}}}
```
- **Lợi ích.**
  - Phủ được các liên hệ ngầm với ngành, mà alias không làm được.
  - Tận dụng được `not_for` để thay các danh sách `block_in`.
  - Chi phí gần bằng 0: khoảng 3–4K token cho mỗi bài, tức khoảng $0.00015 [I].
- **Nhược điểm.**
  - Jev đọc nghĩa đen [S], nên có thể gắn ngành cho tiêu đề chỉ nhắc chữ "điện" một cách bâng quơ. Ví dụ "TP.HCM đề xuất cắt điện, nước với công trình vi phạm" [V] không phải tin ngành Điện hay Nước.
  - Chưa có số đo tiếng Việt.
  - Thứ tự option ảnh hưởng kết quả.
- **Thí nghiệm nhỏ nhất.** Lấy 92 tiêu đề W365, hỏi GICS3 theo 2 thứ tự option. Đo tỷ lệ đồng ý với ngành LLM đã gắn, độ lệch giữa hai thứ tự, và kết quả trên 10 câu bẫy chứa "điện", "nước", "quỹ". Chi phí dưới $0.05.

### A2. Alias fold sinh ứng viên, Jev gỡ nhập nhằng. Độ sơ khai: khả thi
- **Mô tả.** EntityRegistry đã trả ứng viên theo alias. Khi một chuỗi khớp nhiều thực thể, hoặc khớp một alias nằm trong danh sách `_context_guards`, Jev chọn thực thể đúng hoặc NONE.
- **Ví dụ.**
  - [V] "Xây dựng CDC tiếp tục tạm ngừng kinh doanh chi nhánh miền Nam": TICKER:CDC trong kho là CTCP Chương Dương, không rõ có cùng công ty không.
  - [V] "Giầy Thượng Đình có tân Tổng Giám đốc là lãnh đạo Vinaconex": GTD khớp đúng. "Vinaconex" có thể khớp nhầm V21/VCC (Vinaconex 21/25), trong khi alias trần "Vinaconex" không tồn tại trong kho.
- **Câu hỏi mẫu:** `{"cdc":{"type":"choice","question":"Cụm 'CDC' trong tiêu đề chỉ công ty nào?","options":[{"id":"TICKER:CDC","what":"CTCP Chương Dương, niêm yết mã CDC"},{"id":"NONE","what":"Một công ty khác không có trong danh sách"}]}}`
- **Lợi ích.**
  - Vị trí trong luồng không thay đổi: vẫn là đối chiếu tất định, Jev chỉ tăng độ chính xác của bước kiểm.
  - Mỗi bài chỉ tốn 0–3 câu hỏi.
- **Nhược điểm.**
  - Jev không có kiến thức ngoài danh sách option, nên với "CDC" nó chỉ đoán theo nghĩa bề mặt.
  - Recall vẫn bị trần bởi alias: thực thể nào không có alias thì không bao giờ thành ứng viên.
- **Thí nghiệm.** Lấy 50 trường hợp code_first và LLM bất đồng trong `article_mentions`, cho Jev phân xử, rồi so với nhãn người gán.

### A3. LLM mention, truy hồi top-K, Jev chọn: liên kết thực thể. Độ sơ khai: khả thi
- **Mô tả.**
  - LLM vẫn nhận diện chuỗi mention từ tiêu đề (vùng độc quyền không đổi).
  - Code truy hồi top-K (K ≤ 20) bằng alias fold, bỏ dấu, n-gram ký tự và fuzzy trên canonical_name.
  - Jev chọn thực thể hoặc NONE. Kết quả dùng để kiểm `entity_id`, `in_list` và `unlisted_candidates` của LLM.
- **Ví dụ.**
  - [V] Mention "Sovico Group" không có trong kho. Nếu Jev chọn NONE với confidence cao, `unlisted_candidates` được xác nhận.
  - [V] Mention "Vinaconex" cho top-K gồm V21, VCC, NONE. Nếu Jev chọn NONE thì có thể kho thiếu mã mẹ, và đây là tín hiệu bổ sung alias (hướng 9).
  - [V] "Phát triển Đô thị UDJ" khớp TICKER:UDJ, cần xác nhận.
- **Câu hỏi mẫu:** `{"link_1":{"type":"choice","question":"Tên 'Vinaconex' trong tiêu đề chỉ thực thể nào?","options":[{"id":"TICKER:V21","what":"CTCP Vinaconex 21, công ty con"},{"id":"TICKER:VCC","what":"CTCP Vinaconex 25"},{"id":"NONE","what":"Tổng công ty Vinaconex (mẹ) hoặc đơn vị khác không có trong danh sách"}]}}`
- **Lợi ích.**
  - Tách rõ vai trò: LLM trích mention, code chỉ truy hồi, Jev quyết một lựa chọn đóng.
  - Mô phỏng đúng cách làm entity linking chuẩn.
  - Sinh được việc cụ thể để bảo trì kho alias.
- **Nhược điểm.**
  - Phụ thuộc chất lượng mention từ LLM.
  - Option NONE có thể hút xác suất quá mức khi mô tả của nó quá rộng.
  - Cần một bước ghép mention với chuỗi trong tiêu đề, việc này đã có trong citations.
- **Chi phí [I].** 3–5 mention mỗi bài, mỗi mention khoảng 1K token. 100 bài khoảng 0.5M token, tức khoảng $0.02.
- **Thí nghiệm.** Lấy toàn bộ `unlisted_candidates` và `in_list=false` của W365, chạy Jev theo top-K, đếm số trường hợp thực ra đã có trong kho (LLM hụt) và số trường hợp kho thiếu alias.

### A4. Giải đấu theo shard GICS1 (5–12 shard ≤255, vòng chung kết). Độ sơ khai: ý tưởng
- **Mô tả.** Dùng làm kiểm recall khi cả LLM và alias đều trả rỗng.
  - Chia 1093 mã theo 11 GICS1, thêm một shard cho 42 mã chưa có GICS. Mỗi shard kèm NONE.
  - Hỏi các shard song song. Shard nào có option khác NONE với P > 0.5 thì đưa vào vòng chung kết (≤12 option).
- **Nhược điểm.**
  - Context rot khi có 237 option dài [S].
  - Prompt lớn: 9–13K token mỗi shard, khoảng 100K token mỗi bài [I].
  - Xác suất NONE giữa các shard không so sánh được với nhau.
  - Rủi ro báo động giả tăng theo số shard.
- **Thí nghiệm.** Lấy 20 tiêu đề mà cả hai nguồn trả rỗng, thêm 20 tiêu đề đã biết mã, đo recall@1 và số báo động giả.

### A5. Tìm theo tầng: type, GICS1, GICS3, ticker. Độ sơ khai: ý tưởng
- **Mô tả.** Hỏi 3–4 câu choice nối tiếp nhau, mỗi tầng ≤84 option. Rẻ hơn A4 khoảng 5 lần.
- **Nhược điểm.**
  - Lỗi ở tầng trên lan xuống tầng dưới.
  - Tiêu đề về công ty đa ngành, ví dụ Vingroup (GICS là BĐS, nhưng tin về VinFast), bị lạc tầng.
  - Không làm song song được.
- **Thí nghiệm.** Chạy cùng bộ 40 tiêu đề của A4, so recall và chi phí giữa A4 và A5.

### A6. Vĩ mô, định chế và chỉ số bằng Noul từng thực thể (khoảng 37 câu mỗi bài). Độ sơ khai: khả thi
- **Mô tả.** Tập nhỏ và cố định gồm 9 MACRO_THEME, 8 MACRO_GEO, 7 INSTITUTION, 6 INDEX và 7 ASSET_CLASS. Hỏi noul cho từng thực thể thì có nhiều nhãn.
- **Ví dụ [V].** "Quan chức Fed: Lạm phát vẫn ở quá cao" phải ra FED, LAM_PHAT và MY. "Nâng hạng FTSE: 'Sóng' tỷ USD mở ra" phải ra NANG_HANG_TTCK.
- **Nhược điểm.**
  - P(yes) ≠ 1 − P(no) [S], nên cần hiệu chuẩn ngưỡng cho từng thực thể.
  - "Mỹ" và "Hoa Kỳ" chịu lỗi đọc nghĩa đen.
- **Chi phí [I].** 37 câu dùng chung state, khoảng 2K token mỗi bài.

## 3. Rủi ro chung và cách giảm

- **Thứ tự option.** Hỏi 2 hoán vị, lấy trung bình, và coi độ chênh giữa hai lần là độ bất định.
- **Prompt injection trong state.** Tiêu đề là dữ liệu ngoài. Cần bọc tiêu đề trong khung và không để câu hỏi phụ thuộc chỉ dẫn nằm trong state.
- **Không seed.** Kết quả không lặp lại được hoàn toàn, nên phải lưu probabilities thô để kiểm toán.
- **Tiếng Việt chưa có số đo.** Có thể mô tả option song ngữ (Anh cộng Việt). Cần đo cả hai cách.
- **Quản trị.** Mọi hướng ở đây chạy shadow sau đợt và ghi vào bảng riêng. Không cổng, không thay LLM, không tính vào độ phủ. Nếu thay bằng AnyJev (Apache-2.0) thì vẫn cần ADR, vì AnyJev có mô hình riêng (liên quan ADR 0009 D6).

## 4. Hai ý tưởng tin nhất

1. **A1, ngành GICS bằng Choice cộng Noul.**
   - Là chỗ duy nhất cả không gian nhãn vừa trần 255 mà không cần bộ sinh ứng viên.
   - Lấp đúng điểm yếu đã đo của alias fold: từ ngành trùng nghĩa, liên hệ ngành không nêu tên.
   - Rẻ nhất, thử được ngay trên 92 tiêu đề W365.
2. **A3, mention LLM, top-K, Jev chọn.**
   - Giữ nguyên ranh giới LLM độc quyền trích xuất.
   - Biến Jev thành bộ phân xử liên kết với tập đóng, đúng thế mạnh của choice.
   - Sinh trực tiếp hai sản phẩm: xác nhận `unlisted_candidates` và danh sách alias còn thiếu. Ví dụ thực tế là "Vinaconex" đang không có mã mẹ trong kho.
