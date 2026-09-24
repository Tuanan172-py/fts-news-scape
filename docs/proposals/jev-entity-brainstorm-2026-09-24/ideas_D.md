# Ideator D: phản biện và phương pháp đo (Jev cho nhận diện thực thể L1)

Nhãn: [S] có nguồn, [V] kiểm chứng tại máy (đọc chỉ đọc `data/agent_outputs_l1/article_W365_*.output.json`, `data/entities/entities.json`), [I] suy luận.

## 0. Phản đề: dữ liệu W365 nói gì trước khi bàn Jev
- [V] W365 có 365 bài. Mã CP theo `intent_source`: BOTH 60, CODE_ONLY 8, LLM_ONLY 289. Mọi loại: BOTH 74, CODE_ONLY 285, LLM_ONLY 499.
- [V] **Lỗ lớn nhất không nằm ở phân giải nhập nhằng mà ở bước nối về kho.** 578/2206 (26%) chuỗi trong `unlisted_candidates` khớp đúng alias, code hoặc tên chuẩn có trong kho, trải trên 235/365 bài: HOSE 38, FTSE Russell 31, Fed 25, VN-Index 24, Bộ Tài chính 20, NHNN 12... LLM nhận ra đúng thực thể nhưng xếp vào "ngoài danh mục".
- [V] Có thực thể trong kho mà cả hai nguồn đều bỏ sót vì thiếu alias: "KienlongBank" (KLB, alias chỉ có "Kiên Long"), "PVCFC" (DCM), "TCBS" (TCX, code bỏ sót, LLM bắt được), "DNSE" (DSE, code bỏ sót).
- [V] CODE_ONLY sai do alias là từ thường: "Đại lộ Thăng Long" → TTL, "Đại Dương" → OGC, "Quốc Dân" → NVB, "Thành Nam" → TNI, "Hóa An" → DHA. Kho có 60 alias trùng nhau, ví dụ "đông nam á" = {MACRO_GEO:DONG_NAM_A, TICKER:SSB}, "nam việt" = {NAV, ANV}, "vinpearl" = {VIC, VPL}.
- [V] LLM_ONLY sai hoặc lan rộng: "Phân bón Cà Mau" → thêm GAS, "PVCFC" → GAS (thiếu DCM), "KIS" → VND, "UDJ" → thêm BCM, "Tỷ giá euro ngày 21/9" → TCB, VCB, BID, STB, CTG (lấy từ thân bài), "Tập đoàn Nam Mê Kông" → CTG.
- [I] Kết luận phản đề: ở tầng tiêu đề, việc có ích nhất là (1) nối chuỗi LLM đã trích về ID trong kho và (2) bổ sung alias. Cả hai không cần Jev. Jev chỉ có chỗ đứng ở nhóm hẹp: alias nhập nhằng, quan hệ mẹ/con và câu hỏi "mã này là chủ thể hay chỉ được nhắc tới".
- [S] Giới hạn của Jev theo đề bài: không trích span, không sinh văn bản, chưa có số đo tiếng Việt, P(yes) ≠ 1−P(no), thứ tự option ảnh hưởng kết quả, có thể bị prompt injection qua state. [I] Vì không trích span, Jev luôn cần một bên khác sinh ứng viên (LLM, alias hoặc embedding). Jev chỉ phân xử được, không nhận diện được.

## 1. Golden set tiêu đề (thiết kế)
- Nguồn: 365 bài W365, chỉ đọc. Đơn vị chấm là cặp (bài, bề mặt nhắc tới, entity_id|NIL, phạm vi title/lead/body, vai trò chủ thể/được nhắc).
- Chọn mẫu phân tầng, khoảng 320 cặp: BOTH 60 (toàn bộ), CODE_ONLY mã CP 8 + 40 loại khác, LLM_ONLY mã CP 80, unlisted-trong-kho 60, alias trùng 30, bẫy chữ Latin 3 ký tự 20, mẹ/con hoặc thương hiệu 25.
- Phân loại ca khó, lấy ví dụ thật từ W365 [V]:
  (a) Alias trùng hoặc là từ thường: Thăng Long, Đại Dương, Quốc Dân, Đông Nam Á.
  (b) Tên người: "CEO Phạm Nhật Minh Hoàng ra mắt dịch vụ taxi..." (LLM gắn VIC), "con trai Chủ tịch Tân Hoàng Minh" (→ UPS).
  (c) Thương hiệu con: KienlongBank, PVCFC, Green SM, WinMart (alias của MSN).
  (d) Mẹ/con: TCBS→TCX và TCB, Masan (MSN)→MCH/MML/MSR, Phân bón Cà Mau→DCM và GAS.
  (e) Code Latin trùng từ thường: "CEO" (mã C.E.O) trong "CEO Phạm...", "SBV" (Siam Brothers, cũng là viết tắt tiếng Anh của NHNN), "KIS" (công ty chứng khoán không niêm yết) và FPT/FTS ("Chứng khoán FPT" là FTS, không phải FPT).
  (f) Cặp code và tên lệch nhau: "Xây dựng CDC" là CCC, trong khi mã CDC là Chương Dương.
- Gán nhãn: 2 người độc lập, đo Cohen κ, người thứ ba phân xử. Cặp có κ thấp tách thành tầng "mơ hồ thật" và không tính cho bất kỳ hệ nào.
- Chỉ số: P/R/F1 của bước nối (micro, theo type và theo tầng khó); NIL accuracy (tỷ lệ gắn NIL đúng); ECE 10 bin cho mọi hệ có trả xác suất; coverage@P≥0.95 (tỷ lệ cặp giữ lại khi ngưỡng đạt precision 0,95); độ nhạy thứ tự option (|ΔP| khi đảo option); p95 độ trễ.
- Ngưỡng dừng (kill) cho Jev [I], vi phạm một điều là dừng:
  (k1) F1 trên các tầng khó (a)(c)(d)(e) không vượt baseline B1+B2 ít nhất 5 điểm.
  (k2) ECE > 0,08, hoặc ECE không tốt hơn điểm tự tin của deepseek-flash.
  (k3) Hơn 10% cặp có |ΔP| > 0,15 khi đảo thứ tự option.
  (k4) Accuracy tiếng Việt thấp hơn bản dịch tiếng Anh của cùng tiêu đề quá 5 điểm.
  (k5) p95 > 800 ms mỗi bài, hoặc có 1 ca prompt injection lọt qua trong bộ đỏ 20 tiêu đề.

## 2. Ý tưởng (baseline trước, Jev sau)

### B1. Nối lại tất định `unlisted_candidates` về kho, không dùng Jev (sẵn thử)
- Mô tả: sau `--finish`, đối chiếu từng chuỗi unlisted với alias đã fold (casefold, bỏ dấu, bỏ tiền tố CTCP). Khớp duy nhất thì đánh dấu `relinked_exact`. Khớp nhiều ID thì chuyển sang hàng đợi nhập nhằng.
- Luồng: LLM sinh bề mặt, script tra bảng. Script không đọc tiêu đề nên không phạm "No Script Emulation" [I]. ADR vẫn phải quyết định bản nối này có được tính là "đã phân tích" hay không.
- Ví dụ: "HOSE" → EXCHANGE:HOSE, "Fed" → INSTITUTION:FED.
- Lợi ích [V]: gỡ tới 578 chuỗi trên 235 bài, chi phí 0 token. Nhược điểm: bó tay với KienlongBank và PVCFC nếu thiếu alias.
- Thí nghiệm nhỏ nhất: chạy offline trên 5 tệp W365, đếm số chuỗi nối được và chấm tay 50 mẫu.

### B2. Khai thác alias từ đầu ra LLM (khả thi)
- Mô tả: gom các chuỗi unlisted lặp lại nhiều lần hoặc viết HOA (TCBS, DNSE, PVCFC, KienlongBank) rồi đưa `entity-curator` đề xuất alias. Người duyệt trước khi ghi vào `brand_aliases.yaml`.
- Lợi ích: sửa tận gốc cho cả code lẫn LLM. Chi phí: vài phút người duyệt mỗi tuần. Nhược điểm: alias ngắn làm tăng dương tính giả (cùng họ với lỗi TTL), nên mọi alias mới phải qua `_context_guards.yaml`.
- Thí nghiệm: danh sách top-30 chuỗi unlisted ngoài kho của W365, đếm số chuỗi thật sự có ID.

### J1. Jev `choice` phân giải alias nhập nhằng (khả thi)
- Luồng: alias hoặc B1 sinh tập ứng viên (≥2 ID, hoặc 1 ID có alias là từ thường), Jev chọn một ứng viên hoặc NIL. Chỉ chạy ở chế độ shadow.
- Ví dụ: "Đường gom Đại lộ Thăng Long ngập sâu 1m, Hà Nội cấm xe đi qua".
```json
{"state":"Tiêu đề: Đường gom Đại lộ Thăng Long ngập sâu 1m, Hà Nội cấm xe đi qua",
 "questions":{"thang_long":{"type":"choice","question":"Cụm 'Thăng Long' trong tiêu đề chỉ điều gì?",
  "options":[{"id":"TICKER:TTL","what":"Tổng Công ty Thăng Long, doanh nghiệp xây dựng niêm yết","not_for":"tên đường, cầu, địa danh"},
             {"id":"NIL","what":"địa danh, tên đường hoặc thực thể không có trong danh mục"}]}}}
```
- Lợi ích: sửa đúng loại lỗi CODE_ONLY [V]. Chi phí [I]: khoảng 300 token/câu hỏi, khoảng 30 câu/đợt, dưới $0,001. Nhược điểm: thứ tự option, tiếng Việt chưa đo, thêm một nhà cung cấp (Cấp 3, va chạm ADR 0009 D6).
- Thí nghiệm: 30 cặp tầng (a) chạy 2 thứ tự option, so với guard hiện có và với deepseek-flash khi hỏi đúng câu đó.

### J2. Jev `noul` kiểm "chủ thể tiêu đề" cho mã LLM_ONLY (khả thi, là D7 của hội đồng trước)
- Luồng: LLM gắn mã, Jev hỏi riêng từng mã xem tiêu đề cộng đoạn đầu có nói về doanh nghiệp này không. Kết quả dùng để gắn nhãn vai trò (chủ thể/được nhắc), không xoá mã.
```json
{"state":"Tiêu đề: KIS triển khai ưu đãi cho khách hàng mở mới tài khoản ký quỹ\nĐoạn đầu: ...",
 "questions":{"q_VND":{"type":"noul","question":"Bài này có nói chủ yếu về CTCP Chứng khoán VNDIRECT (mã VND) không?"}}}
```
- Lợi ích [V]: 289 mã LLM_ONLY, trong đó nhiều mã đến từ thân bài (5 ngân hàng cho bài "Tỷ giá euro"). Nhãn vai trò giúp xếp hạng và định tuyến theo watchlist. Nhược điểm: P(yes)≠1−P(no) nên phải hỏi cả dạng phủ định; Jev đọc nghĩa đen. Chi phí [I]: khoảng 1.000 câu/đợt × 400 token ≈ $0,02.
- Thí nghiệm: 80 cặp LLM_ONLY đã gán nhãn vai trò, tính AUROC của P(yes).

### J3. Jev `choice` cho quan hệ mẹ/con và thương hiệu (ý tưởng)
- Options: {chính doanh nghiệp X, công ty mẹ của thực thể được nhắc, công ty con/thương hiệu, không liên quan}. Ví dụ "TCBS hoàn tất chuyển giao ghế Tổng Giám đốc" × {TCX, TCB}, "PVCFC mở rộng..." × {DCM, GAS}.
- Lợi ích: đưa quan hệ vào dữ liệu thay vì để gắn phẳng. Nhược điểm: Jev không biết quan hệ sở hữu nên phải nhét dữ kiện vào `what`, tức là kho cần thêm trường `parent`. Không có kho quan hệ thì ý tưởng này chết.
- Thí nghiệm: 25 cặp tầng (d), so với deepseek-flash khi hỏi đúng câu đó.

### J4. Embedding tìm ứng viên, Jev xếp lại top-k (ý tưởng)
- Luồng: embedding của 1262 tên chuẩn và alias, lấy top-5 cho mỗi chuỗi unlisted không khớp exact (KienlongBank ~ Kiên Long), rồi Jev `choice` top-5 cộng NIL.
- Nhược điểm: thêm hạ tầng embedding cho tiếng Việt. Top-5 thường đủ rõ để người duyệt ở B2 chọn luôn, nên Jev có thể thừa [I].

### M1. Bàn so sánh hiệu chuẩn: deepseek tự trả confidence, Jev và AnyJev cục bộ (phương pháp)
- Chạy cùng golden set qua 4 hệ: (i) deepseek-flash trả `confidence` 0–1 trong schema, (ii) Jev, (iii) AnyJev (Apache-2.0, chạy cục bộ, không thêm nhà cung cấp), (iv) B1+B2. Chấm theo chỉ số và ngưỡng dừng ở mục 1.
- Lợi ích: trả lời thẳng câu hỏi "Jev thêm được gì". Nếu (i) đã có ECE ≤ 0,08 thì Jev không có lý do tồn tại.

## 3. Hai ý tưởng tin nhất
1. **B1 + B2 trước mọi việc với Jev.** [V] Riêng 26% chuỗi unlisted đang nằm sẵn trong kho đã là phần lỗi lớn nhất và có thể sửa với 0 token, 0 nhà cung cấp mới. Mọi phép đo Jev phải lấy B1+B2 làm baseline, nếu không thì Jev được ghi nhận thành quả của việc vá alias.
2. **M1 chạy với J1 và J2 làm hai tác vụ đo, chỉ shadow, có ngưỡng dừng k1–k5.** Nhóm hẹp (alias trùng, chủ thể tiêu đề) là nơi duy nhất một bộ phân xử có hiệu chuẩn có thể trội hơn. Ưu tiên AnyJev cục bộ trước Jev SaaS để tránh hard gate Cấp 3 và va chạm ADR 0009 D6 cho tới khi có số đo tiếng Việt.

Quản trị [I]: Jev SaaS là nhà cung cấp mới (Cấp 3) và phải có ADR sửa D6 trước khi gọi API thật. B1 cần ADR xác định bản nối từ bề mặt LLM có được tính là "đã phân tích" hay không. Không ý tưởng nào được dùng làm cổng chặn đợt.
