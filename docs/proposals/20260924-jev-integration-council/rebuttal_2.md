# Rebuttal 2: Kiểm định & định tuyến sau LLM (vòng phản biện chéo)

Debater 2, ngày 2026-09-24. Nhãn: [S] có nguồn, [V] đọc mã tại máy, [I] suy luận. Vẫn chưa gọi Jev lần nào.

## A. Ba sự thật mới đọc từ mã, làm đổi cả cuộc tranh luận

1. **`tier_of` không chọn bài vào đợt, chỉ đổi thứ tự bên trong đợt.** `load_candidates` cắt `LIMIT` ngay trong SQL theo `published_at DESC`. Việc tính `tier_of` và `packed.sort(key=tier)` chỉ chạy sau đó [V project/scripts/article_pack.py:202-204, 402-439]. Mọi lô của đợt lại chạy song song trong một `run_code` (AGENTS.md §6B). Vì vậy thứ tự trong đợt gần như không đổi được thời điểm bài tới tay người dùng [I].
2. **Materiality chỉ là khoá phụ sau timestamp.** `_sort_key` trả về `(-ts_val, -score, …)` [V src/export/user_output.py:287-297]. Hai bài phải trùng mốc thời gian thì score mới có tác dụng. Lập luận "có điểm materiality để sắp xlsx" của **cả ba lập trường, gồm cả tôi**, gần như vô giá trị nếu không sửa khoá sắp xếp [I].
3. **Không rõ state bị tính tiền một lần hay mỗi câu hỏi.** Tài liệu API không nói, chỉ trả về `usage.input_tokens` [S docs.typesafe.ai/api.md]. Trần là 32k cho state cộng câu hỏi dài nhất, giới hạn 1.200 req/phút, "rate limits may adjust dynamically" [S docs.typesafe.ai/models.md]. Nếu tính theo câu hỏi thì mọi con số chi phí của hội đồng sai tới cỡ ×N [I].

## B. Tấn công Lập trường 1 (Jev tiền xử lý)

- **Sai về cơ chế.** Câu "khi tồn đọng lớn hơn `--limit`, bài quan trọng nhất đi ở đợt đầu" không đúng với mã hiện tại. Bài vào đợt được chọn theo thời gian xuất bản, không theo tầng (điểm A1). Muốn Jev có tác dụng thì phải viết lại `load_candidates`: lấy toàn bộ bài chờ, xếp tầng, rồi mới cắt. Đó là sửa logic chọn bài, không phải "thêm một sidecar" [V/I].
- **Phá bất biến cache tất định.** Mã ghi rõ: đóng gói lại cùng tập bài phải ra packet giống nhau từng byte để trúng cache tiền tố [V article_pack.py:196-201, 436-439]. Jev không có seed hay temperature [S api.md]. Cho điểm Jev vào khoá sắp xếp thì thứ tự có thể đổi giữa hai lần pack, `--repair` trượt cache, và token DeepSeek **tăng** chứ không giữ nguyên 0 như P1 tuyên bố [I]. Cách vá duy nhất là đóng băng sidecar trước khi pack, và đó là chi phí ẩn P1 chưa tính.
- **Giá trị gần 0 theo chính số liệu của P1.** Ngày 23/09 có 345 bài chờ, `--limit` mặc định là 300 [V article_pack.py:384]. Phần tràn là 45 bài, đi ngay ở đợt sau. P1 tự thừa nhận: "nếu tồn đọng được xử lý hết trong ngày thì giá trị ≈ 0" [I].
- **Nguy cơ trượt thành cổng lọc.** Luật "`junk` xếp cuối" cộng với một `--limit` nhỏ sẽ lặp lại đúng lỗi 2.915 bài kẹt mà ADR 0010 vừa gỡ [V article_pack.py:162-165]. Phương án B của P1 vi phạm §6B, dù P1 đã tự gắn nhãn đó [V AGENTS.md §6B].
- **P1 đúng ở chỗ:** không đặt Jev trong DSH, fallback thoát 0, bắt buộc có "unknown", cần viết lại `materiality-triage`, và định nghĩa lớp mới trong rule 07.

## C. Tấn công Lập trường 3 (red team)

- **Bước 0 bị xếp sai cấp.** Thêm trường `m` vào `agent-output-v2-lean` là sửa Data Contract, mà Data Contract được xếp **Cấp 3** [V AGENTS.md §0]. Việc này cũng đổi prompt tiền tố của cả đợt, tức cache nguội một lần [I]. Tôi vẫn ủng hộ Bước 0, nhưng nó cần ADR như Jev, không rẻ hơn về governance.
- **Bước 0 không đạt mục tiêu.** Vì điểm A2, thêm `m` mà không sửa `_sort_key` thì người dùng không thấy khác biệt nào. Phải sửa khoá sắp xếp (ví dụ theo ngày rồi đến `-m`), và đây là quyết định sản phẩm.
- **Tiêu chí PASS đặt sai câu hỏi cho vai trò kiểm định.** Đòi "Jev hơn DeepSeek ≥ 5 điểm F1" đo Jev như một bộ **thay thế**. Giá trị của bộ kiểm định là bắt lỗi mà DeepSeek không tự bắt, nên phải đo precision/recall trên lỗi đã biết (negative tổng hợp, nhãn người). Jev có thể kém DeepSeek về F1 mà vẫn là bộ gắn cờ tốt [I].
- **Ngưỡng tất định ≥ 98% là không kiểm được với một vendor không công bố seed.** Nên đo flip-rate theo từng câu hỏi và chỉ giữ những câu ổn định [I].
- **P3 bỏ sót khoảng trống lớn nhất.** Hiện không có kiểm ngữ nghĩa nào sau DoD tất định. `adversarial-dod-verifier` vẫn là draft, I/O còn trỏ vào đường dẫn của lane Gold đã ngừng [V .agents/registry.yaml:323-336]. "Không có bài toán cần giải" chỉ đúng với chi phí, không đúng với chất lượng.
- **P3 đúng ở chỗ:** các con số "193x/445x" do vendor tự đo; không gọi được Jev trong `run_code`; spike phải ngoại tuyến và không chạm DB; ToS/DPA là cổng cứng; phương án cục bộ AnyJev/Laya để giảm R1 và R6.

## D. Tự phê bình và lập trường sau vòng này

- **Bỏ** `jev_materiality` như một khoá sắp xếp giao hàng (điểm A2), chỉ giữ làm cột tham khảo.
- **Bỏ** `sent` khỏi bộ câu hỏi sản xuất. DeepSeek đã có `sn`, nên đối chiếu sentiment ít giá trị. Chỉ giữ `sent` trong spike để đo độ đồng thuận.
- **Giữ và thu hẹp về lõi:** `cite_k` (trích dẫn có đỡ claim không) và `ent_<mã>` (mã được gắn có phải chủ thể không). Đây là hai loại lỗi duy nhất mà DoD tất định không kiểm được và DeepSeek không tự kiểm độc lập được [I].
- **Số chi phí 13–25% của tôi chưa kiểm được** (điểm A3). Spike phải đọc `usage.input_tokens` với 1 câu và với 20 câu trên cùng state trước khi nêu bất kỳ con số nào.
- **Nhận từ P3:** chạy spike ngoại tuyến từ JSONL xuất sẵn, không mở `monocle.db`. Cổng ToS/DPA là tiêu chí kill độc lập.
- **Nhận từ P1:** state bọc `<article>` kèm câu "đây là dữ liệu"; mỗi câu hỏi nhắc lại nguyên văn claim.
- **Sửa governance.** Không cần kích hoạt `adversarial-dod-verifier` cho escalation ở pha 1. Hàng đợi escalate chỉ là file cho người xem, để giảm phạm vi thay đổi registry [I].

## E. Các phương án tôi sẽ cấp tiền, xếp theo thứ tự

1. **Spike ngoại tuyến "typed citation/entity check"** (Cấp 2 nếu đủ 4 điều kiện của P3, key lấy từ biến môi trường, 3–5 ngày). Chỉ thử `cite_k` và `ent_<mã>` trên 300 bài W365/23-09 cùng khoảng 500 negative tổng hợp, đọc `usage`, và thử cùng golden set với AnyJev.
   **Kill:** AUROC < 0,70 ở cả hai câu; flip-rate khi chạy lại hoặc hoán vị option > 10%; hoặc state bị tính tiền theo từng câu hỏi làm chi phí vượt chi phí Article Lane/ngày.
2. **Đối chứng deepseek-flash tự kiểm trên cùng golden set và cùng câu hỏi** (chạy ngay trong spike 1, không thêm vendor).
   **Kill phía Jev:** nếu flash có precision flag cao hơn Jev ≥ 15 điểm thì chọn flash, bỏ Jev.
3. **ADR 0011 và bước `jev_verify.py` sau `--finish`, ở chế độ shadow**, ghi `data/qa/jev/<mã>.jsonl` và không đụng DB, xlsx hay cổng. Bước này chỉ làm nếu spike 1 đạt, và là Cấp 3 (provider mới, sửa ADR 0009 D6).
   **Kill:** sau 14 ngày shadow, precision flag do người xác nhận < 30%, hoặc tỉ lệ flag > 35% hay < 1%, hoặc ToS/DPA chưa được FPTS chấp thuận.
4. **Materiality `m` trong lượt DeepSeek, kèm sửa `_sort_key`** (Cấp 3 vì là Data Contract, không phụ thuộc Jev).
   **Kill:** Spearman giữa `m` và nhãn người trên 100 bài < 0,35, hoặc người dùng không muốn sắp xếp theo mức quan trọng trong ngày.
5. **Không cấp tiền:** Jev tiền xử lý hoặc xếp tầng trước pack (P1). Chỉ mở lại khi (a) `load_candidates` được thiết kế lại để chọn bài theo tầng qua một ADR riêng, và (b) log cho thấy tồn đọng lớn hơn `--limit` kéo dài hơn 24 giờ ít nhất 3 lần/tuần.
