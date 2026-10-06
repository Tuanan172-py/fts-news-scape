# Rebuttal 3: Red team (vận hành, governance, kinh tế), vòng phản biện chéo

Nhãn: [S] có nguồn, [V] kiểm tại máy (đọc mã hoặc tài liệu), [I] suy luận. Chưa gọi Jev lần nào.

## A. Tấn công Position 1 (Jev tiền xử lý, sắp thứ tự trước pack)

1. **Tầng ưu tiên không chọn bài vào đợt. Luận điểm "bài quan trọng nhất đi đợt đầu" sai về cơ chế.**
   - `load_candidates` chọn bài bằng `ORDER BY a.published_at DESC, a.url_title_hash LIMIT ?`.
   - `tier_of` chỉ chạy **sau** bước LIMIT, rồi `packed.sort(key=tier)` sắp lại **bên trong** đợt.
   - Nguồn: `project/scripts/article_pack.py:169-205` và đoạn quanh `:420-440`. [V]
   - Mọi lô của đợt chạy song song trong **một** `run_code` (AGENTS.md §6B). Vì vậy sắp lại bên trong đợt gần như không đổi thời điểm bài tới tay người dùng. [I]
   - Muốn Jev đổi đợt mà bài rơi vào thì phải sửa bộ chọn bài: quét cả tồn đọng, xếp theo Jev, rồi mới LIMIT. Lúc đó `--limit` nhỏ hơn tồn đọng biến thứ tự thành **bộ lọc** trên thực tế, đúng vùng §6B cấm. P1 tự nêu rủi ro này nhưng tính lợi ích như thể việc sửa bộ chọn đã xong. [I]
2. **Có chi phí ẩn ở bộ nhớ đệm DeepSeek.**
   - Mã ghi rõ: hai lần đóng gói cùng một tập bài phải ra packet giống nhau từng byte thì lần chạy lại mới trúng cache (`article_pack.py:196-200`). [V]
   - Docs Jev không nói gì về seed hay tính tất định (https://docs.typesafe.ai/models.md). [S]
   - Nếu `jev_score` lọt vào khoá sắp, `--repair` và lần chạy lại có thể trượt cache ở mọi token sau bài đầu tiên bị đổi chỗ. Phần DeepSeek đội lên có thể lớn hơn toàn bộ $0,03/ngày P1 trả cho Jev. [I]
3. **Câu `wl_<mã>` là nhận diện thực thể thứ hai.** §6C giao việc trích xuất thực thể độc quyền cho `article-processor`. Một nguồn phân tuyến người dùng song song là tách vùng độc quyền này ra, chứ không phải "chỉ sắp thứ tự". [V AGENTS.md §6C; I]
4. **Số "6–10 giây" và "recall tầng 1 tốt hơn" không kiểm được** nếu không có nhãn người. Bộ nhãn người P1 đề xuất chỉ 100 bài, trong khi tỉ lệ bài mat≥4 chưa ai đo. Nếu tỉ lệ ấy chừng 10% thì chỉ có khoảng 10 bài dương, quá ít để phân biệt "baseline + 15 điểm". [I]

## B. Tấn công Position 2 (Jev kiểm định sau LLM)

1. **Materiality không lên đầu bảng giao hàng như P2 viết.**
   - `_sort_key` trả về `(-ts_val, -score, ...)` (`project/src/export/user_output.py:287-297`). [V]
   - Thời gian đăng là khoá chính, materiality chỉ phá hoà khi hai bài trùng mốc thời gian.
   - Nên "có điểm materiality đã hiệu chuẩn" gần như không đổi thứ tự bài người dùng thấy. Muốn đổi thì phải là một quyết định sản phẩm: đổi khoá sắp. [I]
   - Lỗi này cũng có ở P1 và ở Bước 0 của chính tôi.
2. **Chuỗi leo thang dựa vào một agent thuộc lane đã ngừng.**
   - `adversarial-dod-verifier` có `stage_role: post-gold-qa`, đọc `data/agent_outputs/*.output.json` và mang luật `05-gold-agent-and-payload-invariants` (`.agents/registry.yaml:323-338`). [V]
   - Kích hoạt nó là một lần kích hoạt agent theo rule 07, cần skill và DoD mới cho Article Lane. P2 không tính chi phí này.
   - Bước "chuyển người xem" cũng không có ai nhận việc và chưa đo năng lực người xem. [I]
3. **Negative tổng hợp quá dễ, AUROC 0,85 bị thổi phồng.**
   - Tráo trích dẫn **giữa các bài** tạo ra cặp sai mà chỉ cần khớp chủ đề là bắt được.
   - Lỗi thật của mô hình là chọn nhầm đoạn **trong cùng bài**, hoặc hàm ý vượt quá đoạn trích. Ngưỡng pass phải đo trên loại negative này. [I]
4. **Giám sát drift ±2σ trên 14 ngày không kiểm được trong spike 3–5 ngày.** Đây là lợi ích hứa trước, chưa có proof. [I]
5. **Lập luận "rẻ hơn 4–7 lần" không có trọng lượng.** Lượt tự kiểm bằng flash ước khoảng $0,3–0,5/ngày, tức ở cả hai phía tiền đều không đáng kể. Thứ quyết định là chi phí governance Tier 3 (ADR, key, DPA, lớp agent mới), và P2 chưa cộng khoản này. [I]

## C. Điểm chung hai bài đều bỏ qua

- **Rate limit không ổn định.** Docs ghi giới hạn 1.200 RPM đang "adjusting dynamically" và có thể đổi không báo trước. Docs cũng chỉ nói tiếng ngoài tiếng Anh "handled but not equally well" (https://docs.typesafe.ai/models.md). [S]
- **Chữ của ADR 0009 D6** là "Mọi route agent = `deepseek-flash`", lý do là chi phí (`docs/decisions/0009*:39`). [V] Cả hai bài đề xuất sửa thành "mọi model sinh văn bản". Làm vậy mở cửa cho mọi mô hình phân loại sau này, không riêng Jev. ADR nên ghim tên nhà cung cấp và phiên bản, không nới theo loại mô hình. [I]

## D. Nhượng bộ (họ đúng, tôi sai hoặc thiếu)

- **Đặt Jev ngoài DSH là đúng**, cả P1 và P2 đều làm vậy: chạy như bước Python ở terminal, key lấy từ biến môi trường, không bao giờ là cổng của `--finish`. Cách này giữ bất biến "một đợt = một `run_code`". [V research_C]
- **P1 và P2 đúng, tôi sai về Cấp của spike.** AGENTS.md §0 xếp "API token" vào Cấp 3 theo đúng câu chữ. Tôi rút lập luận spike là Cấp 2. Việc cấp key cần người duyệt ở Hard Gate, dù spike không ghi DB.
- **P2 có lý về độc lập lỗi.** Flash tự kiểm flash thì lỗi tương quan, và `cite_k` là loại lỗi hiện chưa ai kiểm. Đây là giá trị Jev duy nhất tôi thấy không trùng với việc DeepSeek đã làm trong cùng lượt.
- **P1 trung thực khi ghi "0 token DeepSeek tiết kiệm".** Điều này xác nhận luận điểm kinh tế của tôi.
- **Cả ba bài cùng đồng ý** rằng `materiality-triage` (`registry.yaml:288-303`) đang ghi `pre-gold-gate` / "cổng rẻ" / KPI `gold_burn_reduction_pct`, trái ADR 0010. Đây là nợ governance, phải sửa bất kể có Jev hay không.

## E. Lập trường của tôi thay đổi thế nào

- **Bỏ luận điểm "Bước 0 lấp khoảng trống sắp thứ tự".** Thêm trường `m` chỉ có giá trị khi người dùng quyết định đổi khoá sắp, ví dụ `(ngày, -m, -ts)`. Đó là quyết định sản phẩm, cần hỏi người dùng trước.
- **Gộp `cite_k` và `mat` của P2 vào spike.** Loại bỏ toàn bộ kiến trúc tiền xử lý của P1. Bỏ `sent`, vì `sn` đã có sẵn gần như miễn phí.
- **Spike là Cấp 3 rút gọn:** story ở `blocked`, người duyệt key và ToS, chạy ngoại tuyến, chỉ ghi scratch. Chưa viết ADR 0011 trước khi spike PASS.
- **Kết luận tổng giữ nguyên:** không tích hợp vào sản xuất trong quý này.

## F. Các phương án tôi thực sự cấp kinh phí (xếp hạng)

1. **Dọn nợ governance, không liên quan Jev** (Cấp 2):
   - sửa `materiality-triage` về `stage_role` sắp thứ tự hoặc `retired`;
   - sửa `adversarial-dod-verifier` cho khớp Article Lane, bỏ `post-gold-qa` và luật 05-gold.

   KILL: không cần, vì đây là sửa sai lệch với ADR 0010 đã duyệt.
2. **Thêm `m` (1–5) vào `agent-output-v2-lean` trong chính lượt DeepSeek,** kèm câu hỏi cho người dùng về khoá sắp giao hàng (Cấp 2, thêm Cấp 3 nếu sửa data contract).

   KILL: trên 100 bài có nhãn analyst, nếu κ giữa `m` của DeepSeek và người < 0,4, hoặc người dùng không muốn đổi khoá sắp, thì bỏ trường `m`.
3. **Spike Jev ngoại tuyến chỉ gồm `cite_k` và `mat`** (tối đa 1 tuần, key đã được duyệt, không mở `monocle.db`). Negative phải là tráo đoạn **trong cùng bài** và hàm ý vượt trích dẫn, kèm 30 bài chèn injection.

   KILL (chỉ cần một):
   - AUROC `cite_k` < 0,75 trên negative trong cùng bài;
   - ECE > 0,12;
   - đổi nhãn khi chạy lại hoặc đảo option > 10%;
   - injection làm lệch > 20% số bài;
   - không có ToS hoặc DPA chấp nhận được;
   - giá hoặc rate limit đổi trong thời gian spike.
4. **Chạy cùng spike bằng AnyJev hoặc Laya cục bộ,** làm song song hoặc thay thế nếu mục 3 bị KILL vì ToS. Phương án này loại rủi ro nhà cung cấp và rủi ro dữ liệu ra ngoài.

   KILL: cùng ngưỡng với mục 3, cộng thêm điều kiện chạy 350 bài mất quá 15 phút trên máy vận hành.
5. **Không cấp kinh phí: Jev tiền xử lý của P1.** Chỉ xem lại khi radar cho thấy tồn đọng lớn hơn `--limit` ở ≥ 3 trong 14 ngày gần nhất, **và** có ADR cho phép bộ chọn bài xếp theo tầng mà không biến thành bộ lọc.

   KILL: tồn đọng luôn được xử lý hết trong ngày.
