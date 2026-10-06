# Ideator B: Jev thay heuristic guard (Noul phân xử ngữ cảnh)

Nhãn: [S] có nguồn, [V] đã kiểm tại máy (đọc mã, truy vấn DB chỉ đọc ngày 24/09), [I] suy luận. Không gọi API Jev.

## 0. Số đo nền: guard hiện có bao nhiêu và chặn được bao nhiêu

- [V] Guard viết tay trong `src/agent/entities.py`: `CODE_STOPLIST` (19 mã: GDP, CPI, FED, USD, CEO, IPO...), `_CODE_LEFT_BLOCK_RE` (TP.HCM, UBND HCM), guard PGD (regex trái/phải + danh sách 16 tiền tố ngân hàng "MBB:", "TCB:"...), bỏ TICKER tier 2 trừ tiêu đề CBTT, `GENERIC_ALIAS_STOPLIST`, `_blocked_by_morphology` cho `MACRO_GEO:MY` và `MACRO_GEO:NGA` (khoảng 50 dòng, 3 tập từ khoá tay).
- [V] `_context_guards.yaml`: 7 mục (NUOC, QUY x2, DIEN, GIAY dùng `drop_bare` + `block_in`; MY, VANG chỉ `block_in`).
- [V] Kho alias: 2.678 khoá alias đã fold; **60 khoá dùng chung cho hơn 1 thực thể** (nam viet → ANV/NAV; duc giang → DGC/MGG; vinpearl → VIC/VPL; dong nam a → MACRO_GEO/SSB; bat dong san → 3 thực thể); **211 khoá một từ** (TICKER 123, MACRO_GEO 19, INDEX 12, INSTITUTION 11, ASSET_CLASS 11, INDUSTRY 15...).
- [V] Chạy `detect()` trên 13.911 tiêu đề trong `articles`: 8.457 tiêu đề có ít nhất 1 thực thể. Guard ngữ cảnh + hình thái chỉ bắn **122 lần trên 122 tiêu đề (0,9%)**: ctx MY 56 (Mỹ Đình), ctx VANG 38 ("đất vàng"), morph MY 20 (Mỹ Thuận, Mỹ Thủy), morph NGA 8 (Nguyễn Thị Nga). PGD xuất hiện trong 39 tiêu đề, gần như toàn bộ là "PGD" của ngân hàng.
- [V] Số tiêu đề chứa từ trần mơ hồ: Mỹ 568, nước 544, vàng 487, Nga 280, điện 272, quỹ 176. Trên 3.000 tiêu đề đầu: 101 tiêu đề (3,4%) có từ 2 mã chứng khoán trở lên.
- [I] Hệ quả: guard **chặn** ít (0,9%), nên xoá guard mang lại ít về độ chính xác. Giá trị thật nằm ở hai chỗ khác: (1) `drop_bare` làm **mất recall** mà hiện không đo ("siêu dự án điện 60.000 tỷ" không gắn ngành điện), (2) chi phí bảo trì: mỗi lỗi mới đòi thêm một nhánh `if`.
- [I] Ràng buộc quản trị: kết quả code-first không tính là "đã phân tích" (AGENTS.md §6B), nên cải thiện code-first chỉ nâng chất lượng **đối chiếu** trong `build_mentions`, không thay `article-processor`. Jev là mô hình thứ hai, trái ADR 0009 D6: mọi ý tưởng dưới đây là Cấp 3, cần ADR trước khi chạm runtime.

## 1. Brainstorm rộng (8 hướng)

1. Noul phân xử từ địa danh/quốc gia một từ (Mỹ, Nga, Nhật, Đức...) thay `_blocked_by_morphology`.
2. Choice phân nghĩa cho alias ngành là từ thông dụng (nước, điện, quỹ, giấy, vàng), khôi phục alias trần đang bị `drop_bare`.
3. Noul phân xử va chạm mã 3 ký tự với viết tắt (PGD, HCM, và các mã tier 2) thay regex PGD + stoplist.
4. Choice chọn một trong các thực thể dùng chung alias (60 khoá), có option "không phải thực thể nào".
5. Choice gán vai trò thực thể trong tiêu đề: chủ thể / nhắc phụ / so sánh-đối thủ / nguồn tin / bối cảnh địa danh.
6. Jev làm trọng tài chỉ khi code-first và LLM bất đồng, đẩy ca khó cho người duyệt.
7. Jev chạy offline đào guard mới: đề xuất cụm `block_in` cho người biên tập, runtime giữ nguyên tất định.
8. Noul tách công ty mẹ/công ty con cùng thương hiệu (Masan Group MSN vs Masan Consumer MCH, Vingroup VIC vs Vinpearl VPL).

## 2. Phát triển sâu

### Ý 1. Noul thay guard hình thái cho Mỹ/Nga (độ sơ khai: khả thi)
- Luồng: `detect()` bỏ `_blocked_by_morphology` và `block_in` của MY, sinh ứng viên `MACRO_GEO:MY` mỗi khi khớp "Mỹ"; script gọi Jev cho **chỉ** ứng viên thuộc danh sách alias mơ hồ; P(yes) dưới ngưỡng thì gắn nhãn `code_first_rejected`, không xoá.
- Mẫu: `{"state":"Tiêu đề: CII chào bán 6.7 ngàn tỷ đồng trái phiếu để triển khai cao tốc Trung Lương - Mỹ Thuận","questions":{"q_my":{"type":"noul","question":"In this Vietnamese headline, does the word 'Mỹ' refer to the United States (the country)? Place names like Mỹ Thuận, Mỹ Đình, Phú Mỹ and words like thẩm mỹ, mỹ phẩm are NOT the United States."}}}`
- Ví dụ thật [V]: "Siêu sân vận động ... lớn gấp 2,6 lần sân Mỹ Đình"; "Chủ tịch Tập đoàn BRG Nguyễn Thị Nga nhận nhiệm vụ đặc biệt"; đúng nghĩa: "Chứng khoán Mỹ tăng điểm nhờ lợi suất...".
- Lợi ích: xoá khoảng 50 dòng mã + 3 tập từ khoá; phủ được ca guard viết hoa bỏ sót [I]: "Mỹ" đứng cuối tiêu đề vẫn là tên người, hoặc "Mỹ" + từ viết hoa đúng nghĩa Hoa Kỳ nhưng chưa có trong `_INTL_AFTER_MY` (tập này đã phải thêm tay "hegseth", "pentagon").
- Nhược: 848 tiêu đề (Mỹ + Nga) phải gọi Jev để sửa 84 ca; tiếng Việt chưa có số đo [S]; Jev đọc nghĩa đen, "Nga" trong tên người có thể lọt; P(yes) và P(no) không bù nhau nên phải chốt ngưỡng trên tập nhãn.
- Chi phí [I]: khoảng 150 token/câu hỏi x 848 = 0,13M token = 0,005 USD cho toàn kho; độ trễ 70–500 ms/câu, chạy song song được.
- Thí nghiệm nhỏ nhất: 122 tiêu đề guard đã chặn + 120 tiêu đề "Mỹ/Nga" đúng nghĩa lấy ngẫu nhiên; so Jev với guard. Đạt khi Jev khớp guard ≥ 95% và tìm thêm ca guard sai.

### Ý 2. Choice phân nghĩa, khôi phục alias trần ngành (độ sơ khai: khả thi)
- Luồng: bỏ `drop_bare` cho NUOC, DIEN, QUY, GIAY; ứng viên từ alias trần đi qua choice; `block_in` hiện có chuyển thành `not_for` và `examples` của option (không mất tri thức đã tích luỹ).
- Mẫu: `{"state":"Tiêu đề: Chaebol Hàn Quốc ... lập công ty làm siêu dự án điện 60.000 tỷ","questions":{"q_dien":{"type":"choice","question":"What does 'điện' mean in this headline?","options":{"power_industry":{"what":"electricity generation, power plants, power utilities","examples":["nhiệt điện","dự án điện"]},"other":{"what":"any other meaning","not_for":["điện thoại","điện tử","điện máy","Điện Biên","mất điện on a ship"]}}}}}`
- Lợi ích: đo được lần đầu recall bị `drop_bare` bỏ mất; tri thức guard vẫn nằm trong YAML, chỉ đổi vai từ "chặn" sang "gợi ý".
- Nhược: khối lượng lớn nhất (nước 544, điện 272, quỹ 176) mà đa số là nhiễu; câu "mất điện trên tàu khu trục" đúng nghĩa điện nhưng không phải ngành, Jev nghĩa đen dễ sai; thứ tự option ảnh hưởng kết quả [S].
- Chi phí [I]: khoảng 250 token x 1.000 tiêu đề = 0,25M token, dưới 0,02 USD.
- Thí nghiệm: 100 tiêu đề chứa "điện" trần, người gán nhãn ngành/không; đo recall gain so với `drop_bare` và độ chính xác của Jev. Chạy lại với đảo thứ tự option để đo độ nhạy.

### Ý 3. Noul cho va chạm mã 3 ký tự (độ sơ khai: sẵn thử)
- Luồng: bỏ regex PGD và danh sách 16 tiền tố ngân hàng; mã nằm trong danh sách "mã trùng viết tắt" (PGD, HCM, mã tier 2) sinh ứng viên, Jev xác nhận.
- Mẫu: `{"state":"Tiêu đề: MBB: Quyết định thành lập PGD Tân Ba, Phan Xích Long, Chợ Bà Chiểu","questions":{"q_pgd":{"type":"noul","question":"Does 'PGD' here mean the listed company PV Gas Distribution (stock code PGD)? 'PGD' as short for a bank transaction office (phòng giao dịch) is NOT the company."}}}`
- Lợi ích: 39 ca PGD thật [V] là bộ kiểm có sẵn; giải được lớp lỗi thay vì từng mã; mở đường thả dần mã tier 2 đang bị bỏ.
- Nhược: Jev không biết danh mục mã Việt Nam, phải nhồi mô tả vào câu hỏi; CODE_STOPLIST (GDP, USD...) rẻ và đúng tuyệt đối, không nên thay.
- Thí nghiệm: 39 tiêu đề PGD + 20 tiêu đề "Khí thấp áp PGD" tổng hợp từ tin CBTT; đạt khi 0 dương tính giả.

### Ý 4. Choice giải 60 alias dùng chung (độ sơ khai: khả thi)
- Luồng: ứng viên có alias trùng nhiều thực thể thì Jev chọn; option lấy `canonical_name` + GICS3 từ `entities.json` làm `what`; luôn có option `none`.
- Mẫu: `{"state":"Tiêu đề: Thuế chống bán phá giá cá tra đối với Nam Việt, Caseamex cao hơn mức sơ bộ gần 4 lần","questions":{"q_namviet":{"type":"choice","question":"Which company does 'Nam Việt' refer to?","options":{"TICKER:ANV":{"what":"CTCP Nam Việt, pangasius (cá tra) exporter"},"TICKER:NAV":{"what":"CTCP Nam Việt (NAV), building materials"},"none":{"what":"neither company"}}}}}`
- Ví dụ [V]: "Hóa chất Đức Giang thay loạt lãnh đạo" (DGC, không MGG); "Khói mù xuyên biên giới bao trùm Đông Nam Á" (địa lý, không SSB).
- Lợi ích: hiện `detect()` trả **cả hai** mã, sai chắc một; Jev choice có confidence, là đúng dạng bài toán của Jev.
- Nhược: tần suất thấp (Nam Việt 1, Vinpearl 3, Đức Giang 43 tiêu đề); một phần giải được bằng sửa alias (vinpearl nên chỉ thuộc VPL).
- Thí nghiệm: toàn bộ tiêu đề chứa một trong 60 khoá; người gán nhãn; đo accuracy và confidence hiệu chuẩn.

### Ý 5. Choice gán vai trò thực thể (độ sơ khai: ý tưởng)
- Luồng: sau khi LLM hoặc code-first chốt danh sách, mỗi thực thể một câu choice: `subject`, `secondary`, `comparison`, `source_or_speaker`, `location_context`.
- Mẫu: `{"state":"Tiêu đề: HSBC và J.P. Morgan cùng định giá Masan hơn 110.000 đồng/cp...","questions":{"q_role_MSN":{"type":"choice","question":"What role does Masan play in this headline?","options":{"subject":{},"secondary":{},"comparison":{},"source_or_speaker":{},"location_context":{}}}}}` (HSBC ở đây là `source_or_speaker`, không phải chủ thể).
- Lợi ích: phân biệt "Vingroup gánh còng lưng, FPT và Masan Consumer hụt bước" (ba chủ thể) với tiêu đề chỉ nhắc ngân hàng làm nguồn; dùng cho **thứ tự** xếp tầng, không cho độ sâu.
- Nhược: chồng lấn trường `role` nếu `l1-entity-output-v1` bổ sung; đây là phân tích ngữ nghĩa, vùng độc quyền LLM theo §6C; Jev không multi-label gốc.
- Thí nghiệm: 101 tiêu đề có ≥ 2 mã; so vai trò Jev với nhận định của `article-processor` trong đợt gần nhất.

### Ý 6–8 (tóm tắt)
- Ý 6 trọng tài bất đồng: chỉ gọi Jev khi code-first và LLM lệch (đúng kết luận D7 hội đồng trước [S]); rẻ nhất, không đổi quyền quyết định của LLM. Sẵn thử.
- Ý 7 đào guard offline: chạy noul trên toàn kho mỗi tuần, gom ca P(yes) thấp theo cụm n-gram quanh alias, đề xuất dòng `block_in` mới cho người duyệt. Runtime vẫn 100% tất định, không vi phạm D6 ở đường chạy. Sẵn thử.
- Ý 8 mẹ/con cùng thương hiệu: choice MSN/MCH, VIC/VPL/VHM; phụ thuộc Ý 4.

## 3. Bảng rủi ro chung
- Tiếng Việt chưa có số đo [S]; mọi ngưỡng phải chốt trên tập nhãn tiếng Việt riêng.
- Xoá guard tất định rồi phụ thuộc dịch vụ ngoài (early access, không seed) biến lỗi ổn định thành lỗi ngẫu nhiên [I]; nên giữ guard làm dự phòng khi Jev lỗi mạng.
- Prompt injection trong tiêu đề gần như bằng 0 (câu ngắn, nguồn báo chí) [I].
- Giá trị nghiệp vụ trần thấp: code-first không được tính là phân tích, nên mọi cải thiện chỉ nâng nhãn đối chiếu [I].

## 4. Hai ý tưởng tin nhất
1. **Ý 7, Jev đào guard offline.** Giữ runtime tất định, tri thức mới đi qua người duyệt vào `_context_guards.yaml`, không đụng ADR 0009 D6 ở đường chạy. Đo được ngay: chạy 848 tiêu đề Mỹ/Nga + 487 "vàng", xem Jev có tìm ra ca guard bỏ sót (ví dụ giả định: "giờ vàng", "tuổi vàng", tên người "Mỹ" cuối câu) hay không.
2. **Ý 1 + Ý 3 ở chế độ shadow**, thử trên 122 ca guard đã chặn + 39 ca PGD + mẫu đúng nghĩa. Nếu Jev khớp guard ≥ 95% trên tiếng Việt thì mới có cơ sở lập ADR cho phép xoá khoảng 60 dòng `if` (morphology MY/NGA, PGD). Không đạt thì bỏ, chi phí thí nghiệm dưới 0,01 USD.
