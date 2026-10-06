# Ideator C: LLM trích mention, Jev link vào kho, code chỉ cơ học

> Nhãn: [S] có nguồn, [V] kiểm chứng tại máy, [I] suy luận. Chưa gọi Jev lần nào, nên mọi ước lượng về Jev đều là [I].
> Phạm vi: bàn ý tưởng. Thêm nhà cung cấp mới là Cấp 3 (cần ADR và người duyệt), và vướng ADR 0009 D6 "mọi model là deepseek-flash".

## 0. Dữ kiện làm nền

- [V] Kho `entities.json` thiếu alias thương hiệu phổ biến. NVL chỉ có "Đầu tư Địa ốc No Va", **không có "Novaland"**. VCG **không có "Vinaconex"**. "Sovico" không có ở đâu (grep trong `config/entities/` ra rỗng). Đợt W365 có các tiêu đề "Novaland chốt ngày phát hành gần 801 triệu cổ phiếu để xử lý nợ", "Giầy Thượng Đình có tân Tổng Giám đốc là lãnh đạo Vinaconex", "Sovico Group tiếp tục tất toán một lô trái phiếu".
- [V] Kho có sẵn alias mơ hồ: INSTITUTION:NHNN có alias "Thống đốc" và "tín phiếu"; MACRO_GEO:MY có "Washington" và "Wall Street"; VIC gom cả "GSM", "Xanh SM", "VinFast".
- [V] Có tiêu đề không nêu tên riêng: "Một cổ phiếu ngân hàng giảm kịch sàn sau chuỗi tăng nóng", "Doanh nghiệp của con trai Chủ tịch Tân Hoàng Minh sắp thâu tóm một công ty chứng khoán".
- [S research_A] Jev: `choice` nhận tối đa 255 option, option mang được `what/not_for/examples`, trả probabilities và confidence. `noul` trả P(yes), không có confidence. Jev không trích span, chưa có số đo cho tiếng Việt và nhạy với thứ tự option.
- Nguyên tắc chia vai [I]: LLM là **nguồn duy nhất sinh mention** (surface form và unlisted). Code chỉ **truy hồi ứng viên** từ kho (bỏ dấu, n-gram, alias) và ghép JSON. Jev chỉ **chọn trong tập đóng** do code đưa ra, không bao giờ tự đi tìm thực thể trong bài.

## 1. Brainstorm rộng (12 hạt giống)

1. Jev chạy sau LLM: link mention do LLM trả về vào kho (choice trên top-K). 2. Jev chạy trước LLM: gợi ý ứng viên vào packet. 3. Trọng tài ba bên khi LLM và code-first bất đồng. 4. Vòng học alias từ các unlisted lặp lại. 5. Entity card chuẩn hoá để làm option. 6. Chấm vai trò (chủ thể / nhắc phụ / bối cảnh) cho mỗi entity đã link. 7. Phân ngành GICS3 cho unlisted_candidates. 8. Dedup cùng sự kiện theo cặp (entity, loại sự kiện). 9. Định tuyến watchlist theo điểm vai trò. 10. Phát hiện "tiêu đề ẩn danh" để ưu tiên LLM đọc sâu. 11. Liên kết mẹ-con (Sovico với HDB/VJC) dưới dạng quan hệ, không dưới dạng alias. 12. Đo độ trôi của kho: tỷ lệ mention không link được, theo tuần.

## 2. Phát triển sâu

### Ý 1. Linker hậu kỳ: LLM trích mention, code truy hồi top-K, Jev `choice` (khả thi)
- **Mô tả**: chạy sau `--finish`. Với mỗi mention LLM đã trả (kể cả unlisted), code truy hồi tối đa 20 ứng viên từ kho bằng bỏ dấu và n-gram, thêm option `NONE_IN_KB`. Jev chọn một. So với `entity_id` LLM đã gắn để ra đồng thuận hoặc bất đồng.
- **Luồng**: `l1-entity-output-v1` (LLM) → script truy hồi (tất định) → Jev → bảng shadow `entity_link_check` (chỉ báo cáo).
- **Mẫu**:
```json
{"state": "Headline: Novaland chốt ngày phát hành gần 801 triệu cổ phiếu để xử lý nợ\nMention: \"Novaland\"",
 "questions": {"link_m0": {"type": "choice", "text": "Which listed company does the mention refer to?",
   "options": {"TICKER:NVL": {"what": "No Va Land Investment Group, real-estate developer, HOSE", "examples": ["Novaland", "Đầu tư Địa ốc No Va"]},
               "TICKER:NLG": {"what": "Nam Long Investment, real-estate developer"},
               "NONE_IN_KB": {"what": "Not in this list, or not a company"}}}}}
```
- **Lợi**: nhắm đúng lỗ hổng [V] nêu trên. Alias thiếu nên code-first trượt, LLM vẫn có thể gắn đúng, và Jev xác nhận độc lập. Đây là điểm D7 của hội đồng. Không thêm bước nào vào phiên điều phối.
- **Nhược**: Jev chỉ tốt ngang card của option. Top-K trượt thì Jev cũng chịu. Vì nhạy thứ tự nên phải chạy hai lần với thứ tự đảo. Tiếng Việt chưa đo.
- **Chi phí [I]**: khoảng 150 token/option × 10, cộng tiêu đề khoảng 60, ra khoảng 1,6k token/mention. 100 bài × 4 mention × 2 lần đảo ≈ 1,3M token ≈ **$0,05/đợt**.
- **Thí nghiệm nhỏ nhất**: 50 mention W365 gán nhãn tay. Đo accuracy của Jev, LLM và code-first. Tách riêng tập "alias thiếu" (Novaland, Vinaconex).

### Ý 2. Entity card: biến kho thành option giàu ngữ cảnh (sẵn thử phần code)
- **Mô tả**: sinh tĩnh cho mỗi entity một card tiếng Anh dài tối đa 40 từ: `what` (tên, ngành GICS3, sàn), `examples` (alias), `not_for` (những nhầm lẫn đã biết, ví dụ "GSM" là Xanh SM chứ không phải chuẩn di động; "Thống đốc" chỉ tính khi là Thống đốc NHNN). Code lắp card từ `attributes`, entity-curator duyệt.
- **Luồng**: `entities.json` + `_context_guards.yaml` → `entity_cards.json` (build tất định) → dùng cho Ý 1, 3, 4.
- **Lợi**: Prefix/Suffix guard có sẵn được tái dùng làm `not_for`. Card vẫn dùng được với AnyJev nếu bỏ TypeSafe [S research_B].
- **Nhược**: curator phải viết tay `not_for`. Card dài làm chi phí tăng tuyến tính theo K. Một card sai là lỗi hệ thống, lan sang mọi đợt.
- **Chi phí**: 0 token để build; 1.262 card × khoảng 40 từ.
- **Thí nghiệm**: làm card cho 30 entity hay bị nhầm (VIC/GSM, NHNN/"Thống đốc", MY/"Wall Street"). Chạy Ý 1 với card tối giản và card đầy đủ, so accuracy.

### Ý 3. Trọng tài ba bên khi bất đồng (khả thi)
- **Mô tả**: `build_mentions` đã đối chiếu LLM với code-first. Chỉ khi hai bên khác nhau mới gọi Jev `choice` với các option {id của LLM, id của code, BOTH, NEITHER}. Kết quả chỉ là **nhãn cờ** cho người rà, không ghi đè kết quả của LLM.
- **Ví dụ**: "Phiên đầu nâng hạng FTSE: VN-Index có lúc mất gần 33 điểm, VJC tăng trần trong ATC". Code thấy cả VN-Index và VJC; LLM có thể chỉ giữ VN-Index làm chủ thể. "Ngân hàng Nhà nước mở thêm kênh bơm tiền VND" khớp NHNN; alias "tín phiếu" có thể kéo NHNN vào những bài chỉ nói về lợi suất.
- **Mẫu**: `{"arb": {"type": "choice", "text": "Which entity is actually mentioned in the headline?", "options": {"A": {card LLM}, "B": {card code}, "BOTH": {}, "NEITHER": {}}}}`
- **Lợi**: chỉ gọi trên tập nhỏ ([I] khoảng 10–20% số mention), nên rẻ nhất. Đầu ra là hàng đợi rà sắp theo confidence.
- **Nhược**: cả ba bên có thể cùng sai. "BOTH" là multi-label giả. Dễ trượt thành "code + Jev thay LLM", tức vi phạm §6C nếu ai đó dùng nhãn này để sửa kết quả.
- **Chi phí**: dưới $0,01/đợt. **Thí nghiệm**: lấy mọi ca bất đồng trong W365, người gán nhãn 40 ca, đo xem Jev có đẩy đúng ca lỗi lên đầu hàng đợi không (precision@10).

### Ý 4. Vòng học alias: unlisted lặp lại thành đề xuất alias cho entity-curator (khả thi, giá trị cao)
- **Mô tả**: script đếm surface form trong `unlisted_candidates` và các mention không link được, qua nhiều đợt. Form nào xuất hiện từ 3 bài trở lên thì hỏi Jev xem form đó có phải tên gọi của entity X không, với X lấy từ top-K code truy hồi (`noul` cho từng cặp, thêm một `choice` tổng). Đầu ra là PR đề xuất vào `aliases/*.yaml`, do **người hoặc entity-curator duyệt**.
- **Mẫu**:
```json
{"state": "Surface form: \"Vinaconex\"\nContexts:\n1) Giầy Thượng Đình có tân Tổng Giám đốc là lãnh đạo Vinaconex\n2) ...",
 "questions": {"is_VCG": {"type": "noul", "text": "Is \"Vinaconex\" a common name for Vietnam Construction and Import-Export Corporation (VCG)?"},
               "is_parent_only": {"type": "noul", "text": "Is this a parent group that is not itself a listed company?"}}}
```
- **Lợi**: sửa tận gốc lỗ hổng [V] (Novaland, Vinaconex). Bộ đối chiếu tất định tốt lên mà code không phải "đoán". Jev chỉ chấm độ tin để xếp hàng duyệt, không tự ghi vào kho.
- **Nhược**: tên tập đoàn mẹ (Sovico) dễ bị gán nhầm thành alias của công ty con (HDB/VJC), nên cần câu `is_parent_only`, và quan hệ mẹ-con phải là một loại bản ghi riêng. Vì P(yes)≠1−P(no) nên chỉ dùng để xếp hạng, không đặt ngưỡng tuyệt đối.
- **Chi phí**: vài chục form mỗi tuần × khoảng 800 token, gần như 0. **Thí nghiệm**: lấy 20 form unlisted lặp nhiều nhất qua W1 đến W365, so thứ hạng Jev đưa ra với phán quyết của curator.

### Ý 5. Chấm vai trò entity: chủ thể / nhắc phụ / bối cảnh (giữa ý tưởng và khả thi)
- **Mô tả**: với mỗi entity đã link, Jev `choice` giữa 3 mức vai trò, dựa trên tiêu đề và đoạn đầu. Kết quả là cột thông tin cho định tuyến watchlist và cho dedup.
- **Ví dụ**: "Giầy Thượng Đình có tân Tổng Giám đốc là lãnh đạo Vinaconex": GTD là chủ thể, VCG là nhắc phụ. "Sai lầm của Warren Buffett khi bỏ lỡ một cổ phiếu tăng 9.000%": không mã VN nào là chủ thể.
- **Mẫu**: `{"role_GTD": {"type": "choice", "text": "What role does Thuong Dinh Footwear (GTD) play in this headline?", "options": {"SUBJECT": {"what": "The news is about this company"}, "SECONDARY": {"what": "Mentioned as a related party"}, "CONTEXT": {"what": "Background only"}}}}`
- **Lợi**: giảm giao nhầm tin, lỗi đắt nhất với người dùng [I]. Đây là D7 mở rộng từ "đúng/sai" sang "mức độ".
- **Nhược**: hội đồng đã xếp D12 (định tuyến) vào loại xâm vùng LLM [S council]. Nếu điểm vai trò **quyết định** việc giao hàng thì nó thành một cổng mới, trái nguyên tắc "mọi bài xử lý đầy đủ". Chỉ được dùng làm cột thông tin hoặc để sắp xếp trong xlsx.
- **Chi phí**: khoảng 1,5 lần Ý 1. **Thí nghiệm**: 60 cặp (bài, entity) gán nhãn tay, đo độ đồng thuận giữa Jev và LLM (LLM đã có `materiality`). Nếu hai bên đã khớp trên 90% thì Ý 5 là thừa.

### Ý 6. Phân ngành GICS3 cho unlisted_candidates (khả thi)
- **Mô tả**: unlisted (Tân Hoàng Minh, Sovico, Berkshire) không có ticker nhưng vẫn định tuyến được theo ngành. Jev `choice` trên 51 INDUSTRY_GICS3, thấp hơn trần 255 option [V số lượng].
- **Lợi**: user theo dõi ngành nhận được cả tin về doanh nghiệp chưa niêm yết. Tập đóng, đúng sở trường của Jev.
- **Nhược**: doanh nghiệp đa ngành (Sovico có hàng không, ngân hàng, BĐS) cần multi-label, mà chạy noul × 51 thì tốn gấp nhiều lần. Tên riêng ít ngữ cảnh khiến Jev dễ đoán theo nghĩa đen ("Hoàng Minh" không gợi ra ngành nào).
- **Thí nghiệm**: 30 unlisted gán nhãn ngành tay, so top-1 và top-3.

### Ý 7. Dedup cùng sự kiện theo khoá (entity, sự kiện) (ý tưởng)
- **Mô tả**: W365 có ít nhất 4 tiêu đề cùng tả sự kiện "khối ngoại bán ròng khoảng 700 tỷ ngày nâng hạng FTSE" [V]. Code gom ứng viên theo entity đã link, ngày và SimHash; Jev `noul` từng cặp "hai tiêu đề này có tả cùng một sự kiện không".
- **Nhược**: Jev so số kém [S research_A], mà 700 tỷ với 500 tỷ lại là hai sự kiện khác nhau, đúng failure mode đó. Chồng lấn với agent draft `story-dedup-clusterer`. **Thí nghiệm**: 40 cặp gần trùng, đo riêng nhóm chỉ khác nhau ở con số.

### Ý 8. Jev chạy trước LLM, gợi ý ứng viên trong packet (ý tưởng, không khuyến nghị)
- Đưa "các ứng viên có thể" vào packet cho deepseek-flash đọc. Nhược: LLM bị neo (anchoring) vào gợi ý, phép đối chiếu mất tính độc lập. Thêm một bước trước phiên điều phối, trái bất biến "một đợt = một run_code". Lợi về token gần như 0 vì phần đắt là đọc trọn bài [S council]. Ghi lại ở đây để loại.

## 3. Rủi ro chung
- Governance: "link" của Jev là một quyết định ngữ nghĩa, nên phải giữ ở vai **kiểm, không thay**. Không cột Jev nào được ghi vào `l1_*` hay làm đổi phép đếm độ phủ.
- Prompt injection trong state: tiêu đề là văn bản từ bên ngoài. State phải bọc thành trường rõ ràng, không nối câu hỏi vào sau tiêu đề.
- AnyJev (mã nguồn mở) giữ cùng giao diện, nên các ý trên không khoá vào một nhà cung cấp [S research_B].

## 4. Hai ý tôi tin nhất
1. **Ý 4: vòng học alias có người duyệt.** Lỗ hổng alias là sự thật đã kiểm (Novaland, Vinaconex, Sovico). Jev chỉ xếp hạng đề xuất, và đầu ra đổ vào kho alias mà code-first vốn đang dùng. Không chạm vùng độc quyền của LLM, chi phí gần 0, lợi ích cộng dồn theo thời gian.
2. **Ý 1 + Ý 2: linker hậu kỳ dùng entity card.** Đây là D7 của hội đồng được cụ thể hoá: LLM trích mention, code truy hồi top-K, Jev chọn trong tập đóng có card. Làm card trước (0 token, vẫn có ích nếu bỏ Jev), rồi chạy thí nghiệm 50 mention để quyết định Spike 0.
