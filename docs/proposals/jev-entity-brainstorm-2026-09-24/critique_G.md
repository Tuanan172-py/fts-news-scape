# Critic G: governance, chất lượng dữ liệu, an toàn (Jev cho nhận diện thực thể L1)

Nhãn: [S] có nguồn, [V] kiểm tại máy ngày 24/09 (đọc mã chỉ đọc), [I] suy luận. Không gọi Jev, không ghi DB.

## 0. Ba dữ kiện quản trị làm nền

- [V] Bộ chọn bài dùng **danh sách đen**: `ANALYZED_L1 = "o.dod_pass = 1 AND COALESCE(o.l1_source, 'agent') <> 'code_first'"` (`scripts/article_pack.py:166`). Mọi giá trị `l1_source` mới (ví dụ `jev`, `relinked`) sẽ **tự động được tính là "đã phân tích"** và loại bài khỏi đợt sau. Đây là lỗ hổng cụ thể nhất của cả chủ đề này.
- [V] ADR 0009 D6 viết "Mọi route agent = `deepseek-flash`"; lý do ghi trong ADR là chi phí token (cấm `v4-pro`). Theo câu chữ, D6 ràng buộc route agent trên DSH. Jev gọi ngoài DSH không phải "route agent", nhưng theo tinh thần thì vẫn là một model thứ hai, và AGENTS.md §6C nói "Mọi model là deepseek-flash". Muốn đưa Jev vào runtime thì phải có ADR sửa D6, không lách bằng câu chữ.
- [V] `article_expand.build_mentions` đã có nhãn `intent_source` (BOTH / CODE_ONLY / LLM_ONLY). Đây là chỗ cắm tự nhiên cho nhãn kiểm, nên không cần thêm cột vào `l1_*`.

## 1. Jev là "model" hay "script"?

- [I] **Là model.** Jev xác suất, không seed, phán đoán ngữ nghĩa và không tất định. Vì vậy nó không được hưởng chế độ "script 0 token" của §6A, và không được đặt trong `detect()` rồi gọi là "đối chiếu tất định".
- [I] Nhưng Jev **về cấu trúc không trích xuất được**: không sinh văn bản, không trích span [S]. Nó chỉ chọn trong tập đóng do bên khác đưa vào. Nên đặt Jev vào lớp thứ ba, "model-verifier": được phán xử, không được sinh.
- [I] Hệ quả: §6C ("No Script Emulation") không phải rủi ro chính. Rủi ro chính là **Jev thay LLM qua cửa sau**, khi nhãn của Jev bắt đầu sửa, xoá hoặc bổ sung `entity_id` của `article-processor`.
- Theo rule 07, nếu Jev vào runtime thì phải có mục trong `.agents/registry.yaml` (class, ranh giới I/O, DoD). Khi chưa có mục đó thì mọi thí nghiệm chỉ là spike offline.

## 2. Nếu Jev ghi `entity_id` vào DB

- **Không ghi vào `l1_outputs`.** Kết quả Jev đi vào bảng riêng, ví dụ `entity_link_check(article_id, mention, candidate_ids, chosen_id, probs_json, option_order_hash, provider, provider_version, created_at)`. Việc tạo bảng mới là đổi schema, tức Cấp 3.
- Nếu buộc phải có `l1_source` mới (ví dụ `jev_verify`) thì **không được tính vào độ phủ**. Điều kiện tiên quyết là đổi bộ chọn sang **danh sách trắng**: `l1_source = 'agent'`. Nên đổi ngay cả khi không làm Jev, vì phép đếm độ phủ ≥ 90% của `--finish` cũng phải dùng cùng danh sách trắng này.
- Kết quả "nối lại" của B1 (Ideator D) là tra bảng tất định trên chuỗi do LLM sinh. Nó hợp lệ để **kiểm**, nhưng nếu ghi đè `in_list` hay `entity_id` của LLM thì thành "đối chiếu để thay", trái §6B. Chỉ được ghi thành nhãn `relinked_exact` đi kèm, còn bản gốc của LLM giữ nguyên.

## 3. Rủi ro xuyên suốt

- **Injection.** Ideator B cho rằng rủi ro "gần như bằng 0". Tôi không đồng ý: tiêu đề đến từ RSS và trang bên thứ ba, và Jev có failure mode injection trong state [S]. Bù lại, đầu ra của Jev chỉ là xác suất nên bán kính thiệt hại chỉ là một nhãn sai, **với điều kiện nhãn không có quyền ghi**. Biện pháp: bọc state thành trường, bộ đỏ 20 tiêu đề (k5 của Ideator D), và không bao giờ đưa thân bài dài vào state.
- **Trôi phiên bản.** Jev đang early access (`jev-1.13.0`) và không seed. Mỗi dòng phải lưu `provider_version`. Khi đổi phiên bản thì chạy lại golden set và so ECE trước khi tin tiếp. Ngưỡng hiệu chuẩn trên phiên bản cũ mặc định hết hiệu lực.
- **Tiếng Việt.** Chưa có số đo [S]. Mọi ngưỡng phải chốt trên tập nhãn tiếng Việt. Nếu mô tả option bằng tiếng Anh thì đó là một biến thí nghiệm, không phải mặc định.
- **Tính tất định của bộ đối chiếu.** Đặt Jev vào `detect()` (Ideator B, Ý 1 và Ý 2) thì `code_first` không còn tái lập được, và phụ thuộc vào mạng. Lỗi ổn định sẽ thành lỗi ngẫu nhiên, còn nhãn BOTH/CODE_ONLY mất nghĩa kiểm toán.
- **Cổng trá hình.** Jev lỗi hoặc timeout **không được** làm `--finish` thoát khác 0. Điểm Jev chỉ được dùng để sắp **thứ tự**, không quyết định bài nào được xử lý hay được giao (§6B "mọi bài xử lý đầy đủ"). Không đặt trần hay ngưỡng chi phí Jev nào: token là số ghi nhận.
- **Lock-in.** Giao diện choice/noul/score có bản mở là AnyJev [S], và entity card (Ideator C, Ý 2) là tài sản trung lập. Nên thiết kế cho giao diện chung, không gắn vào TypeSafe.
- **Dữ liệu ra ngoài.** Tiêu đề là tin công khai, rủi ro thấp. Tuy vậy, khoá API là Cấp 3 (AGENTS.md §0), và **không đưa watchlist của người dùng vào state hay option**.

## 4. AnyJev cục bộ khác gì

- **Khác:** không có nhà cung cấp mới, không có dữ liệu ra ngoài, không cần API token, pin được phiên bản và có thể seed. Nhờ vậy rủi ro drift, lock-in và rò dữ liệu giảm rõ.
- **Không khác:** AnyJev vẫn là một LLM mở, tức vẫn là model ngoài `deepseek-flash`, nên vẫn cần ADR sửa D6 và vẫn là Cấp 3. Thêm vào đó là rủi ro chuỗi cung ứng (trọng số, phụ thuộc Python) và chi phí vận hành máy. Chạy offline như spike đo lường (M1 của Ideator D) thì không cần ADR, **miễn là không chạm DB vận hành**.

## 5. Chấm từng ý (rủi ro governance và dữ liệu, 1 = thấp, 5 = cao)

| Ý | Rủi ro | Lý do chính | Điều kiện để sống |
|---|---|---|---|
| D-B1 nối unlisted tất định | 2 | Tra bảng trên chuỗi LLM, không đọc tiêu đề; nguy cơ ghi đè | Chỉ ghi nhãn `relinked_exact`, không sửa `in_list`; ADR ngắn |
| D-B2 / C-4 vòng học alias, người duyệt | 1 | Đầu ra là PR vào YAML, runtime giữ tất định | Jev chỉ xếp hạng; `entity-curator` giữ Tier-3 gate |
| B-7 đào guard offline | 1 | Runtime không đổi | Như trên; lưu `provider_version` cho mỗi đề xuất |
| C-2 entity card | 1 | Build tĩnh, 0 token, có ích cả khi bỏ Jev | Card sai lan sang mọi đợt: cần review và version |
| D-M1 bàn hiệu chuẩn | 1 | Spike đo, không chạm runtime | Golden set cố định; kill k1–k5 |
| A-3 / C-1 linker hậu kỳ top-K | 2 | Đúng vai verifier (D7 của hội đồng) | Bảng shadow riêng; không làm đổi phép đếm |
| C-3 / B-6 trọng tài bất đồng | 2 | Dễ trượt thành "code + Jev sửa LLM" | Nhãn chỉ là hàng đợi cho người rà, không có quyền ghi |
| D-J1 / A-2 / B-4 phân giải alias trùng | 2 | Phạm vi hẹp, tập đóng | Shadow; nhãn gắn vào CODE_ONLY, không xoá |
| D-J2 noul "chủ thể tiêu đề" | 3 | Vai trò là ngữ nghĩa, vùng LLM | Chỉ là cột thông tin; không lọc giao hàng |
| A-1 ngành GICS bằng choice | 3 | Tự gán ngành toàn bài, tức là nhận diện chứ không kiểm | Chỉ so với `IND_*` của LLM; không bổ sung ngành |
| A-6 noul vĩ mô/định chế | 3 | Như A-1: Jev thành bộ nhận diện thứ hai | Như A-1 |
| C-6 GICS3 cho unlisted | 3 | Tạo thông tin mới mà LLM chưa trả | Chỉ là gợi ý cho curator, không vào định tuyến |
| B-1 / B-3 Jev thay guard trong `detect()` | 4 | Phá tính tất định của bộ đối chiếu, phụ thuộc mạng | Chỉ chạy shadow; xoá guard phải có ADR và số đo ≥95% |
| B-2 bỏ `drop_bare` và phân nghĩa bằng Jev | 4 | Như B-1, cộng khối lượng nhiễu lớn | Đo recall offline trước; runtime giữ `drop_bare` |
| B-5 / C-5 vai trò để định tuyến | 4 | Nếu quyết định giao hàng thì thành cổng mới | Chỉ dùng để sắp xếp trong xlsx |
| A-4 / A-5 giải đấu theo shard hoặc theo tầng | 5 | Jev quét cả kho, tức là bộ nhận diện song song thay LLM | Loại khỏi runtime; chỉ dùng làm thước đo recall |
| C-7 dedup theo cặp | 3 | Trùng `story-dedup-clusterer`; Jev so số kém | Để agent dedup quyết định |
| C-8 Jev trước LLM | 5 | Neo LLM, phá tính độc lập, thêm bước vào điều phối | Loại (Ideator C cũng đã loại) |

## 6. Ranh giới đề xuất (để ý tốt vẫn sống)

1. **Vai:** LLM sinh mention; code chỉ truy hồi và tra bảng; Jev (hoặc AnyJev) chỉ chọn trong tập đóng. Không thành phần nào ngoài `article-processor` được ghi vào `l1_outputs` hoặc `agent_outputs`.
2. **Nơi ở:** sau `--finish`, ngoài phiên điều phối, ghi vào bảng shadow riêng, có `provider_version` và `option_order_hash`. Jev lỗi thì bỏ qua và ghi log, không bao giờ làm đổi mã thoát.
3. **Quyền:** nhãn Jev chỉ dùng để (a) xếp hàng cho người rà, (b) đề xuất alias hoặc guard qua PR có người duyệt, (c) làm cột thông tin. Không lọc, không cắt độ sâu, không chặn giao hàng.
4. **Việc làm ngay, không cần Jev:** đổi `ANALYZED_L1` và phép đếm độ phủ sang danh sách trắng `l1_source = 'agent'`. Kèm một test chứng minh `l1_source` lạ không được tính.
5. **Trình tự:** B1 + B2 + entity card (0 nhà cung cấp) → M1 offline với AnyJev → ADR sửa D6 và cho phép provider mới → mới đến Jev SaaS shadow. Khi thiếu ADR thì mọi thứ dừng ở spike offline trên bản sao DB.
