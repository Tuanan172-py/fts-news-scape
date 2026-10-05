# Rebuttal 1: Debater 1 (Tiền xử lý) phản biện chéo

Ngày 2026-09-24. Nhãn: [S] có nguồn, [V] đã kiểm tại máy (đọc mã, chỉ đọc), [I] suy luận. Vẫn chưa gọi Jev lần nào.

## 0. Tự phản biện trước: tiền đề của Lập trường 1 sai ở mã hiện tại

- `load_candidates` chọn bài theo `ORDER BY a.published_at DESC, a.url_title_hash` rồi mới `LIMIT ?` [V article_pack.py:202-204]. `tier_of` chỉ được gọi **sau** khi đã chọn xong, và `packed.sort(key=tier)` chỉ đổi thứ tự **bên trong** đợt [V article_pack.py:420, 439]. Như vậy tầng ưu tiên hôm nay không quyết định bài nào vào đợt đầu. Tôi đã mô tả sai điều này.
- Trong một đợt, mọi lô chạy song song trong cùng một `run_code` (AGENTS.md §6B). Thứ tự bên trong đợt gần như không đổi thời điểm bài tới tay người dùng [I].
- Mã ghi rõ thứ tự packet phải tất định từng byte để trúng prefix cache [V article_pack.py:197-201]. API Jev không có seed [S docs.typesafe.ai/api.md, không nêu seed]. Khi sắp theo điểm Jev, lần đóng gói lại có thể cho packet khác, làm trượt cache. Đó là chi phí ẩn tôi đã bỏ sót [I].
- Ở khâu giao hàng, `_sort_key` trả `(-ts_val, -score, …)` [V user_output.py:287-297]. Materiality chỉ là khoá phụ, chỉ có tác dụng khi hai bài trùng mốc thời gian. Cả ba lập trường (tôi, P2 "sắp thứ tự bằng jev_materiality", P3 "sửa `_sort_key`") đều ngầm cho rằng điền điểm vào thì thứ tự sẽ đổi. Không đúng, nếu không đổi luôn thứ tự khoá, mà đổi khoá thì là quyết định sản phẩm [V].
- **Hệ quả:** tôi rút phương án "Jev trước pack". Muốn thứ tự có nghĩa, phải chèn tầng vào câu SQL chọn bài, nghĩa là đổi bộ chọn. Việc này sát ranh giới "thứ tự thành bộ lọc" của §6B mà chính tôi đã cảnh báo.

## 1. Tấn công Lập trường 2 (kiểm định sau LLM)

1. **AUROC trên negative tổng hợp bị thổi phồng.** Đổi trích dẫn giữa hai bài khác nhau là lỗi thô, lệch cả chủ đề lẫn thực thể. Lỗi thật của deepseek-flash là đoạn cùng bài, gần nghĩa, nhưng không đỡ claim. Ngưỡng AUROC ≥ 0,85 có thể đạt trên tập tổng hợp mà vẫn vô dụng với lỗi thật [I]. Cần hard negative: đoạn khác trong **cùng** bài, cùng thực thể.
2. **Định tuyến theo `confidence` với câu Noul chưa chắc làm được.** api.md chỉ nói "Choice and Score answers also carry a `confidence`" [S docs.typesafe.ai/api.md]. `ent_<mã>` và `inj` là Noul, vậy cần kiểm xem Noul có trả xác suất không trước khi đặt τ_hi/τ_lo [I].
3. **Chi phí người bị giấu.** Precision flag ≥ 50% nghĩa là tới một nửa số flag là báo động giả. Với 3–20% của 350 bài, mỗi ngày có 10–70 bài phải người hoặc agent xem lại. Chi phí này lớn hơn $0,07 tiền Jev nhiều lần, và lập trường không định giá nó [I].
4. **Leo thang sang `adversarial-dod-verifier` là kích hoạt thêm một agent draft** [V registry.yaml:323-334, `stage_role: post-gold-qa`, `cost_budget.tokens_per_item: 500`]. Entry này còn mang tư duy lane Gold và có trần token, trái ADR 0010 và luật "token là ghi nhận". Như vậy là hai thay đổi Cấp 3 gộp làm một, trái WIP=1.
5. **Sai lệch nhỏ:** P2 ghi "≤ 32k token" cho state + đoạn văn. Trần thật là 32k cho state cộng câu hỏi dài nhất, và 64k cho cả request [S docs.typesafe.ai/models.md]. Với khoảng 20 câu `cite_k`, mỗi câu nhắc lại claim, request cần tính cả hai trần.
6. **Lập trường 2 đúng ở chỗ:** kiểm trích dẫn là khoảng trống thật mà không lượt DeepSeek nào lấp được một cách độc lập. Đây là use case duy nhất trong ba bài mà Jev có lợi thế cấu trúc (khác họ mô hình, trả xác suất có kiểu). Tôi nhận ý này.

## 2. Tấn công Lập trường 3 (red team)

1. **"Bước 0 là Cấp 2" sai phân loại.** Thêm trường `m` vào `agent-output-v2-lean` là sửa Data Contract, mà AGENTS.md §0 xếp đích danh vào Cấp 3 [V AGENTS.md §0]. Việc này còn kéo theo sửa `article_expand.py`, cổng DoD `agent_ingest.py` và cả schema đọc của `user_output.py` [I]. Tôi vẫn đồng ý nên làm, nhưng phải đi đúng làn Cấp 3.
2. **Bước 0 không sửa được thứ tự giao hàng**, vì lý do đã nêu ở §0: materiality chỉ là khoá phụ sau timestamp [V user_output.py:297].
3. **Tiêu chí PASS thiên lệch.** Nếu yêu cầu "Jev hơn DeepSeek ≥ 5 điểm macro-F1" thì Jev chỉ được chấp nhận khi thay thế DeepSeek. Với vai trò bộ kiểm độc lập, tiêu chí đúng là giá trị gia tăng: Jev bắt được lỗi mà DeepSeek bỏ sót. P3 không có chỉ số này [I].
4. **Lặp lại ≥ 98% là ngưỡng chưa có cơ sở.** Không có seed [S api.md], và chưa ai đo flip-rate. P2 dùng ≥ 90%, tôi dùng ≤ 10%. Chưa có dữ liệu thì chọn con số nào cũng là đoán [I].
5. **Lập trường 3 đúng ở chỗ:** không có bài toán chi phí nào để giải. Spike phải ngoại tuyến, đọc JSONL xuất sẵn, không mở `monocle.db`. Cần làm sạch entry `materiality-triage` (`stage_role: pre-gold-gate`, `cost_budget.tokens_per_item: 120`) dù có Jev hay không [V registry.yaml:288-299]. Có AnyJev/Laya chạy cục bộ làm đường lui cho rủi ro nhà cung cấp.

## 3. Lập trường mới của tôi (gộp)

Bỏ vai trò "tiền xử lý thứ tự". Giữ ba điều: không bao giờ gate, không tính là "đã phân tích", và phân lớp `typed-classifier`. Nhận từ P2 use case kiểm trích dẫn. Nhận từ P3 spike ngoại tuyến, AnyJev/Laya làm baseline cục bộ, và việc làm sạch registry.

## 4. Các phương án tôi sẽ cấp vốn (theo thứ tự)

| # | Phương án | Cấp | Tiêu chí dừng (kill) |
|---|---|---|---|
| 1 | Sửa governance, không cần Jev. Viết lại entry `materiality-triage` và `adversarial-dod-verifier` cho khớp ADR 0010: bỏ `pre-gold-gate`/`post-gold-qa`, bỏ trần token | 2 (registry là tài liệu điều phối) | Người duyệt yêu cầu gộp vào ADR lớn hơn thì chuyển sang ADR đó, không làm riêng |
| 2 | Spike ngoại tuyến "kiểm trích dẫn + thực thể" với Jev, chạy song song AnyJev hoặc Laya cục bộ trên cùng tập vàng 300 bài. Tập vàng có **hard negative cùng bài**. Chỉ số chính: số lỗi thật do người xác nhận mà DeepSeek bỏ sót, Jev bắt được. Cộng thêm flip-rate và Δ khi chèn injection | 2 nếu dùng key cá nhân và chỉ ghi scratch; nếu key tổ chức thì 3 | AUROC trên hard negative < 0,70; flip-rate > 10%; injection làm lệch > 20% số bài; precision flag < 30%; không có ToS/DPA chấp nhận được; quá 1 tuần |
| 3 | Materiality từ chính `article-processor`: thêm trường `m` và **đồng thời** quyết định khoá sắp của xlsx (materiality trước hay timestamp trước) | 3 (đổi data contract) | Người dùng FRA không muốn đổi thứ tự xlsx: chỉ thêm cột, không đổi khoá. κ(`m`, người) < 0,4 trên 100 bài: bỏ trường |
| 4 | Chỉ khi #2 PASS: `jev_verify.py` sau `--finish` và trước giao hàng, ghi sidecar, cột xlsx chỉ đọc `jev_flag`. Làm kèm ADR 0011 (lớp `typed-classifier`, sửa ADR 0009 D6), radar `jev-status`, `token_pricing`, và test fallback | 3 | Sau 14 ngày shadow: tỉ lệ flag thật < 1% hoặc > 35%; hoặc giá/rate limit đổi [S models.md: "may change without notice"] |
| — | Không cấp vốn: Jev trước pack (lập trường cũ của tôi), Jev lọc tin rác (Phương án B) | — | Chỉ mở lại khi bộ chọn bài được sửa để tầng quyết định bài nào vào đợt, và log cho thấy tồn đọng tầng cuối > 48 giờ |

Nguồn: docs.typesafe.ai/api.md, docs.typesafe.ai/models.md (truy cập 2026-09-24).
