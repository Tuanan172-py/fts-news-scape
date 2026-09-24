# Jev cho nhận diện thực thể L1: nối tiêu đề vào kho thực thể (brainstorm)

- **Loại:** brainstorm, ý tưởng còn sơ khai, **chưa phải đề xuất**. Chưa có ADR, chưa đổi runtime.
- **Ngày:** 2026-09-24
- **Nguồn tổng hợp:** `jev-entity-brainstorm-2026-09-24/` gồm ideas_A (truy hồi rồi chọn), ideas_B (Jev thay guard), ideas_C (LLM trích, Jev nối), ideas_D (phản đề và phương pháp đo), critique_F (khả thi kỹ thuật), critique_G (quản trị, dữ liệu, an toàn). Tài liệu liền trước: `jev-integration-council-2026-09-24.md`.
- **Nhãn:** [S] có nguồn · [V] đã kiểm tại máy (các ideator và critic, đọc chỉ đọc) · [I] suy luận.
- **Phạm vi:** không gọi API Jev, không ghi DB, không chạy pipeline. Mọi con số về Jev đều là [I] cho tới khi đo.

---

## 0. Tóm tắt

1. **Jev không nhận diện được thực thể, chỉ phân xử được.** [S] Jev không trích span và không sinh văn bản. Nó chỉ chọn trong một tập đóng (`choice` ≤255 option) hoặc trả P(có) (`noul`). Vì vậy luôn phải có một bên khác sinh ứng viên. Theo luật dự án, bên đó là LLM `article-processor` (mention) cộng code tra kho (ứng viên). Jev chỉ còn vai **model-verifier**: chọn và kiểm, không sinh, không ghi đè.
2. **Phần giá trị lớn nhất không cần Jev.** [V critique_F] 206 cặp "unlisted nhưng có trong kho" ở W365 đều do LLM ghi mã nhóm sai dạng (`ASSET_CLASS:`, `MACRO_GEO`, `IND_GICS3:`...), nên `IntentResolver` loại khỏi danh mục. Sửa bước chuẩn hoá mã nhóm và chạy vòng học alias (Novaland, Vinaconex, KienlongBank, PVCFC...) tốn 0 token và không cần nhà cung cấp mới.
3. **Jev chỉ còn đất ở ba nhóm hẹp có tập đóng nhỏ:** (a) phân giải alias nhập nhằng bằng entity card, (b) vai trò chủ thể của mã trong tiêu đề (D7 của hội đồng trước), (c) xếp hạng hàng đợi alias cho người duyệt. Ngành GICS3 là nhóm phụ thứ tư.
4. **Lỗ quản trị phải vá trước mọi thứ:** [V critique_G] bộ chọn bài dùng danh sách đen (`l1_source <> 'code_first'`, `scripts/article_pack.py:166`). Bất kỳ `l1_source` mới nào (`jev`, `relinked`) sẽ tự được tính là "đã phân tích". Cần đổi sang danh sách trắng `l1_source = 'agent'`, dù có làm Jev hay không.
5. **Trình tự:** Spike -1 (0 token, không Jev) → golden set tiêu đề → entity card → bàn hiệu chuẩn offline (deepseek-flash, AnyJev cục bộ, baseline đã sửa) → ADR sửa D6 → lúc đó mới đến Jev SaaS chạy shadow.

---

## 1. Bài toán và ràng buộc cứng

**Bài toán.** Cho tiêu đề bài báo tài chính tiếng Việt (có thể thêm 1–2 đoạn đầu), nối mọi thực thể được nhắc tới về `entity_id` trong kho `project/data/entities/entities.json` (1262 thực thể, 1093 TICKER) hoặc về NIL, và biết thực thể nào là chủ thể.

| # | Ràng buộc | Nguồn | Hệ quả cho Jev |
|---|---|---|---|
| R1 | Trích xuất thực thể là vùng độc quyền của LLM `article-processor` | AGENTS.md §6C | Jev không được sinh thực thể, chỉ được kiểm |
| R2 | Đối chiếu tất định chỉ để kiểm, không để thay; `code_first` không tính là "đã phân tích" | §6B | Kết quả Jev không được ghi vào `l1_outputs` hay `agent_outputs`, không đổi phép đếm độ phủ |
| R3 | Mọi model là `deepseek-flash` (ADR 0009 D6) | §6C, ADR 0009 | Jev SaaS hay AnyJev ở runtime đều cần ADR sửa D6 |
| R4 | Nhà cung cấp mới, API token, đổi schema DB là Cấp 3 | AGENTS.md §0 | Dừng ở hard gate, cần ADR và người duyệt |
| R5 | Mọi bài được xử lý đầy đủ; tầng ưu tiên chỉ quyết định thứ tự | §6B | Điểm Jev không được lọc bài, cắt độ sâu hay chặn giao hàng |
| R6 | Token là số ghi nhận, không phải cổng | §6B | Không đặt trần hay ngưỡng chi phí Jev |
| R7 | Một đợt là một lệnh `run_code` | §6B | Jev không được chen vào phiên điều phối; chỉ chạy sau `--finish` |
| R8 | Cổng của đợt là cổng kỹ thuật (`--finish` thoát 0) | §6B | Jev lỗi hoặc timeout không được đổi mã thoát |
| R9 | `choice` ≤255 option; 32K cho state cộng câu dài nhất, 64K tổng | [S] Jev | 1093 TICKER không vừa một câu; phải có bộ sinh ứng viên top-K |
| R10 | Không trích span, không multi-label gốc, P(yes)≠1−P(no), nhạy thứ tự option, không seed, tiếng Việt chưa có số đo | [S] Jev | Phải chạy 2 hoán vị, lưu xác suất thô, chốt ngưỡng trên tập nhãn tiếng Việt |
| R11 | Không đưa watchlist của người dùng vào state hay option | critique_G | Chỉ tiêu đề công khai và card của kho được đi ra ngoài |

---

## 2. Ưu và nhược điểm của Jev cho entity linking vào kho

| Ưu điểm | Nhược điểm |
|---|---|
| **Đúng dạng bài toán "chọn trong tập đóng".** Sau khi có ứng viên top-K, nối thực thể là một câu `choice` có NONE; Jev trả probabilities và confidence [S]. | **Không tự nhận diện được.** Không trích span [S], nên recall bị trần bởi bộ sinh ứng viên. Top-K trượt thì Jev cũng trượt [I]. |
| **Option mang được tri thức phủ định.** `what` / `not_for` / `examples` [S] cho phép chuyển `block_in` trong `_context_guards.yaml` và Prefix/Suffix guard thành gợi ý thay vì luật `if` [I, ideas_B, ideas_C]. | **Không biết thế giới ngoài option.** Jev không biết Vinaconex là mẹ của V21/VCC, không biết TCBS thuộc TCB. Kho không có trường `parent` thì ý mẹ/con chết [V ideas_D, critique_F]. |
| **Rẻ và nhanh.** $0,042/1M input, output miễn phí, 70–500 ms [S]. Các ước lượng đều dưới $0,05/đợt kể cả chạy 2 hoán vị [I]. | **Tiếng Việt chưa có số đo** [S]. Mô tả option tiếng Anh hay tiếng Việt là một biến thí nghiệm chưa ai đo. |
| **Có xác suất để xếp hàng rà soát.** Dùng confidence để sắp hàng đợi cho người hay curator thì an toàn hơn dùng ngưỡng tuyệt đối [I, critique_F]. | **Hiệu chuẩn khó dùng làm ngưỡng.** `noul` không có confidence; P(yes)≠1−P(no) [S]; ngưỡng phải chốt theo từng câu hỏi. |
| **Độc lập với LLM đang dùng.** Là tín hiệu thứ hai, khác họ mô hình, để kiểm `entity_id` của deepseek-flash (D7 của hội đồng) [S council]. | **Không tất định, không seed** [S]. Đặt vào `detect()` thì `code_first` mất tính tái lập, lỗi ổn định thành lỗi ngẫu nhiên [I, critique_G]. |
| **Giao diện có bản mở.** AnyJev (Apache-2.0) dùng cùng `choice/noul/score` [S], nên entity card và câu hỏi không bị khoá vào TypeSafe. | **Nhạy thứ tự option** và **đọc nghĩa đen** [S]. "Mất điện trên tàu khu trục" đúng nghĩa "điện" nhưng không phải ngành Điện [V ideas_B]. |
| **Tập nhỏ vừa trần một câu.** GICS1/2/3 (11/28/51), vĩ mô và định chế (37) không cần bộ sinh ứng viên [V ideas_A]. | **Không multi-label gốc** [S]. Doanh nghiệp đa ngành (Sovico) hay "BOTH/NEITHER" phải mô phỏng bằng nhiều câu `noul`, xác suất không cộng được. |
| **Không cần đọc trọn bài.** State chỉ là tiêu đề cộng đoạn đầu, nên rủi ro context rot thấp khi K ≤ 20 [I]. | **Context rot khi option dài** [S]. Shard 237 mã khoảng 9–13K token, có thể chạm 32K nếu option tính vào trần [I ideas_A]. |
| | **Prompt injection trong state** [S]. Tiêu đề đến từ RSS bên thứ ba (xem bất đồng B/G ở mục 5). |
| | **Quản trị nặng:** nhà cung cấp mới (Cấp 3), va chạm ADR 0009 D6, early access `jev-1.13.0` có thể trôi phiên bản [S, critique_G]. |
| | **Giá trị biên thấp.** Phần lỗi lớn nhất sửa được bằng 0 token (mục 0 điểm 2); `code_first` không tính là phân tích nên nâng chất lượng đối chiếu chỉ nâng nhãn kiểm [V critique_F, I ideas_B]. |

---

## 3. Bản đồ ý tưởng (đã gộp trùng lặp)

Thang: **Khả thi** và **Giá trị** 1–5 lấy từ critique_F; **Rủi ro** 1–5 (quản trị và dữ liệu) lấy từ critique_G; **Độ chín**: sẵn thử / khả thi / ý tưởng / loại.

| Mã | Tên (ý gốc được gộp) | Vị trí trong luồng | Câu hỏi Jev | Khả thi | Giá trị | Rủi ro | Độ chín |
|---|---|---|---|---|---|---|---|
| **N0** | Chuẩn hoá mã nhóm trong `IntentResolver` + làm lộ nhập nhằng `setdefault` (D-B1 được F định vị lại) | Sau `--finish`, tra bảng trên chuỗi LLM đã trích | Không có | 5 | 5 | 2 | sẵn thử |
| **N1** | Danh sách trắng `l1_source = 'agent'` cho bộ chọn bài và phép đếm độ phủ (G) | `article_pack.py`, `--finish` | Không có | 5 | 5 (an toàn) | 1 | sẵn thử |
| **L1** | Entity card: sinh card tĩnh cho mỗi thực thể (C-Ý2) | Build tất định từ `entities.json` + `_context_guards.yaml` | Là option cho mọi câu `choice` | 5 | 4 | 1 | sẵn thử (phần code) |
| **L2** | Vòng học alias có người duyệt, gộp với đào guard offline (C-Ý4, D-B2, B-Ý7) | Hàng tuần, ngoài pipeline, nối vào `scripts/maintenance/audit_alias_false_positives.py` | `noul` "chuỗi X có phải tên gọi của thực thể Y", `noul` "đây là tập đoàn mẹ không niêm yết"; chỉ để xếp hạng | 5 | 4 | 1 | khả thi |
| **L3** | Linker hậu kỳ: mention LLM → top-K → Jev chọn (A3, C-Ý1) | Sau `--finish`, chỉ cho mention chưa nối được sau N0 | `choice` K ≤ 20 card + `NONE_IN_KB` | 4 | 2→3 | 2 | khả thi |
| **L4** | Phân giải alias nhập nhằng và alias là từ thường (A2, B-Ý4, D-J1) | Ứng viên có ≥2 ID hoặc alias thuộc danh sách từ thường | `choice` các ID + NIL, có `not_for` | 4 | 3 | 2 | khả thi |
| **L5** | Vai trò chủ thể của mã trong tiêu đề, kiêm trọng tài bất đồng (B-Ý5, C-Ý5, D-J2, B-Ý6, C-Ý3) | Sau `--finish`, chỉ cho LLM_ONLY và ca bất đồng theo `intent_source` | `choice` SUBJECT / SECONDARY / CONTEXT, hoặc `noul` khẳng định + phủ định | 4 | 4 | 3 | khả thi |
| **L6** | Một câu GICS3 cho hai việc: ngành của bài và ngành của unlisted (A1, C-Ý6) | Sau `--finish`, so với `IND_*` của LLM | `choice` 51 GICS3 + NONE | 4 | 3 | 3 | sẵn thử (sau N0) |
| **L7** | Noul cho 37 thực thể vĩ mô, định chế, chỉ số (A6) | Sau `--finish`, so với GEO/THM/INS của LLM | 37 `noul` chung state | 3 | 2 | 3 | ý tưởng |
| **L8** | Jev thay guard hình thái Mỹ/Nga, PGD, mã trùng viết tắt (B-Ý1, B-Ý3) | Chỉ shadow đo; runtime giữ guard | `noul` "'Mỹ' ở đây là Hoa Kỳ?" | 4 | 2 | 4 | khả thi (chỉ đo) |
| **L9** | Khôi phục alias trần ngành, phân nghĩa bằng Jev (B-Ý2) | Chỉ đo recall offline | `choice` nghĩa của "điện/nước/quỹ" | 3 | 2 | 4 | ý tưởng (chỉ đo) |
| **L10** | Quan hệ mẹ/con và thương hiệu (B-Ý8, D-J3) | Cần trường `parent` trong kho trước | `choice` chính X / mẹ / con / không liên quan | 2 | 3 | 2 | ý tưởng, bị chặn bởi dữ liệu |
| **L11** | Embedding tìm ứng viên, Jev xếp lại (D-J4) | Thay bộ truy hồi n-gram | `choice` top-5 + NIL | 3 | 2 | 2 | ý tưởng |
| **M1** | Bàn hiệu chuẩn nhiều hệ (D-M1, F thêm hệ 0) | Spike offline trên bản sao DB | Toàn bộ câu hỏi của L3–L6 | 4 | 5 | 1 | khả thi (khung đo chung) |
| X1 | Giải đấu shard GICS1 trên 1093 mã (A4) | | | 2 | 1 | 5 | **loại** |
| X2 | Tìm theo tầng type → GICS1 → GICS3 → ticker (A5) | | | 2 | 1 | 5 | **loại** |
| X3 | Dedup sự kiện theo cặp tiêu đề (C-Ý7) | | | 2 | 2 | 3 | **loại** |
| X4 | Jev chạy trước LLM, gợi ý ứng viên vào packet (C-Ý8) | | | 1 | 1 | 5 | **loại** |

---

## 4. Ba concept được phát triển sâu nhất

Chung cho cả ba concept (ranh giới theo critique_G):
- **Vai:** LLM sinh mention; code chỉ truy hồi và tra bảng; Jev (hoặc AnyJev) chỉ chọn trong tập đóng.
- **Nơi ở:** sau `--finish`, ngoài phiên điều phối. Ghi vào bảng shadow riêng, không vào `l1_outputs` hay `agent_outputs`. Tạo bảng mới là Cấp 3, nên trong giai đoạn spike chỉ ghi tệp JSONL trên bản sao.
- **Quyền:** nhãn Jev chỉ để (a) xếp hàng cho người rà, (b) đề xuất alias hay guard qua PR có người duyệt, (c) làm cột thông tin. Không lọc, không cắt độ sâu, không chặn giao hàng. Jev lỗi thì bỏ qua và ghi log, không đổi mã thoát.
- **Kiểm toán:** mỗi dòng lưu `provider`, `provider_version`, `option_order_hash`, xác suất thô của cả 2 hoán vị.

Lược đồ bản ghi shadow (đề xuất, chưa tạo):

```json
{"article_id": "…", "mention": "Novaland", "llm_entity_id": "TICKER:NVL", "llm_in_list": true,
 "candidate_ids": ["TICKER:NVL", "TICKER:NLG", "NONE_IN_KB"],
 "task": "link|ambiguity|role|gics3|alias_rank",
 "probs_order_a": {"TICKER:NVL": 0.91, "TICKER:NLG": 0.03, "NONE_IN_KB": 0.06},
 "probs_order_b": {"TICKER:NVL": 0.88, "TICKER:NLG": 0.04, "NONE_IN_KB": 0.08},
 "verdict": "agree|disagree|uncertain", "provider": "jev|anyjev|deepseek-flash",
 "provider_version": "jev-1.13.0", "option_order_hash": "…", "created_at": "…"}
```

### Concept 1: Linker hậu kỳ có entity card (L1 + L3 + L4)

**Ý chính.** Sau khi N0 đã nối hết phần tra bảng được, phần dư là các chuỗi cần fuzzy hoặc cần gỡ nhập nhằng (Novaland, KienlongBank, PVCFC, "Nam Việt", "Thăng Long"). Code truy hồi top-K từ kho bằng bỏ dấu, n-gram ký tự và alias. Jev chọn một trong K card hoặc `NONE_IN_KB`. Kết quả so với `entity_id` / `in_list` mà LLM đã trả.

**Luồng.**
1. `l1-entity-output-v1` (LLM) → N0 chuẩn hoá mã nhóm và tra bảng (tất định).
2. Mention còn lại: chưa nối được, hoặc khớp ≥2 ID, hoặc khớp alias thuộc danh sách từ thường (TTL, OGC, NVB, TNI, DHA [V ideas_D]).
3. Script truy hồi K ≤ 20 ứng viên, lắp card từ `entity_cards.json` (L1).
4. Jev `choice` × 2 hoán vị → bản ghi shadow `task=link` hoặc `task=ambiguity`.
5. Bất đồng giữa Jev và LLM đi vào hàng đợi rà, sắp theo confidence. Bản gốc của LLM giữ nguyên.

**Mẫu card (L1), build tất định, curator duyệt `not_for`:**

```json
{"TICKER:TTL": {"what": "Tổng Công ty Thăng Long – CTCP, doanh nghiệp xây dựng hạ tầng niêm yết mã TTL",
                "examples": ["Tổng Công ty Thăng Long", "TTL"],
                "not_for": ["Đại lộ Thăng Long", "cầu Thăng Long", "Hoàng thành Thăng Long", "địa danh Hà Nội"]},
 "TICKER:VIC": {"what": "Tập đoàn Vingroup, đa ngành: bất động sản, ô tô VinFast, taxi Xanh SM",
                "examples": ["Vingroup", "VinFast", "Xanh SM"],
                "not_for": ["GSM là chuẩn di động", "CEO cá nhân không nêu Vingroup"]}}
```

**Mẫu câu hỏi (ca alias là từ thường):**

```json
{"state": "HEADLINE: «Đường gom Đại lộ Thăng Long ngập sâu 1m, Hà Nội cấm xe đi qua»\nMENTION: «Thăng Long»",
 "questions": {"link_m0": {"type": "choice",
   "question": "Trong tiêu đề, cụm được đánh dấu MENTION chỉ thực thể nào trong danh sách?",
   "options": [
     {"id": "TICKER:TTL", "what": "Tổng Công ty Thăng Long – CTCP, doanh nghiệp xây dựng niêm yết",
      "not_for": "tên đường, cầu, địa danh"},
     {"id": "NONE_IN_KB", "what": "Địa danh, tên đường, hoặc thực thể không có trong danh sách"}]}}}
```

**Ví dụ tiêu đề [V, W365]:**
- "Novaland chốt ngày phát hành gần 801 triệu cổ phiếu để xử lý nợ": kho thiếu alias "Novaland" cho NVL. Kỳ vọng: Jev chọn NVL, đồng ý với LLM; đồng thời sinh một đề xuất alias cho Concept 3.
- "Thuế chống bán phá giá cá tra đối với Nam Việt, Caseamex...": "nam việt" dùng chung ANV/NAV; resolver hiện lấy cái nạp trước (`setdefault`) [V critique_F]. Kỳ vọng: ANV.
- "Xây dựng CDC tiếp tục tạm ngừng kinh doanh chi nhánh miền Nam": mã CDC là Chương Dương, nhưng "Xây dựng CDC" là CCC [V ideas_D]. Đây là ca bẫy: Jev chỉ thấy card, nên có thể chọn sai theo bề mặt.

**Cách ghi không vi phạm luật.** Chỉ ghi bản ghi shadow. Không sửa `entity_id` hay `in_list` của LLM (R2). Không tạo `l1_source` mới (R2, N1). Không gọi trong phiên điều phối (R7).

**Điểm yếu cần đo.** Tỷ lệ top-K trượt; NONE hút xác suất khi mô tả quá rộng [I ideas_A]; ca kiểu "Xây dựng CDC" mà Jev không có tri thức ngoài card.

### Concept 2: Vai trò chủ thể trong tiêu đề, kiêm trọng tài bất đồng (L5)

**Ý chính.** Đây là D7 của hội đồng trước, được ba ideator (B, C, D) độc lập đề xuất. Với mỗi mã LLM đã gắn, hỏi mã đó là chủ thể, được nhắc phụ, hay chỉ là bối cảnh. Chỉ hỏi cho LLM_ONLY và ca bất đồng theo `intent_source` của `build_mentions`, nên số câu giảm khoảng 3 lần [I critique_F].

**Luồng.**
1. `article_expand.build_mentions` đã gắn BOTH / CODE_ONLY / LLM_ONLY [V critique_G].
2. Chọn mã LLM_ONLY (W365: 289 mã [V ideas_D]) và ca bất đồng.
3. Jev `choice` 3 mức, hoặc hai câu `noul` khẳng định và phủ định (vì P(yes)≠1−P(no)).
4. Ghi `task=role` vào bản ghi shadow. Có thể thành **cột thông tin** trong xlsx hoặc khoá sắp xếp. Không lọc giao hàng (R5).

**Mẫu câu hỏi:**

```json
{"state": "HEADLINE: «KIS triển khai ưu đãi cho khách hàng mở mới tài khoản ký quỹ»\nLEAD: «…»",
 "questions": {
   "role_VND": {"type": "choice",
     "question": "Công ty Chứng khoán VNDIRECT (mã VND) đóng vai trò gì trong tiêu đề và đoạn đầu?",
     "options": [
       {"id": "SUBJECT", "what": "Tin nói trực tiếp về công ty này"},
       {"id": "SECONDARY", "what": "Được nhắc như một bên liên quan"},
       {"id": "CONTEXT", "what": "Không được nhắc, hoặc chỉ là bối cảnh chung"}]},
   "about_VND_yes": {"type": "noul", "question": "Tin này nói chủ yếu về VNDIRECT (mã VND)?"},
   "about_VND_no":  {"type": "noul", "question": "Tin này KHÔNG nói về VNDIRECT (mã VND)?"}}}
```

**Ví dụ tiêu đề [V]:**
- "KIS triển khai ưu đãi..." → LLM gắn VND (sai; KIS không niêm yết). Kỳ vọng CONTEXT.
- "Tỷ giá euro ngày 21/9" → LLM gắn TCB, VCB, BID, STB, CTG từ thân bài. Kỳ vọng SECONDARY/CONTEXT cho cả năm.
- "Giầy Thượng Đình có tân Tổng Giám đốc là lãnh đạo Vinaconex" → GTD là SUBJECT, Vinaconex là SECONDARY.
- "Sai lầm của Warren Buffett khi bỏ lỡ một cổ phiếu tăng 9.000%" → không mã VN nào là SUBJECT.

**Cách ghi không vi phạm luật.** Vai trò là phán đoán ngữ nghĩa, vùng của LLM (§6C) [critique_G]. Vì vậy nhãn chỉ để kiểm và xếp hàng rà, không xoá mã của LLM, không quyết định bài nào được giao. Nếu `l1-entity-output-v1` sau này có trường `role` do LLM trả, concept này chuyển thành phép đối chiếu hai nguồn, và thí nghiệm E4 quyết định nó có thừa hay không.

### Concept 3: Vòng học alias có người duyệt, Jev chỉ xếp hạng (L2)

**Ý chính.** Lỗ alias là sự thật đã kiểm: NVL thiếu "Novaland", VCG thiếu "Vinaconex", KLB thiếu "KienlongBank", DCM thiếu "PVCFC", TCX thiếu "TCBS", DSE thiếu "DNSE"; ngược lại có alias gây nhiễu như "Đại Dương" → OGC, "Quốc Dân" → NVB [V ideas_C, ideas_D]. Vòng này sửa cả code-first lẫn resolver phía LLM, và **chạy được không cần Jev**. Jev chỉ sắp thứ tự hàng đợi cho `entity-curator` và người duyệt.

**Luồng.**
1. Sau N0, script đếm surface form trong `unlisted_candidates` và mention chưa nối được qua nhiều đợt. Form xuất hiện ≥3 bài vào hàng đợi **dương** (alias thiếu).
2. Nối vào `audit_alias_false_positives.py` để có hàng đợi **âm** (alias gây nhiễu, ca CODE_ONLY sai).
3. Với mỗi form, code truy hồi top-K. Jev hỏi `noul` từng cặp, cộng `noul` "tập đoàn mẹ không niêm yết".
4. Đầu ra là PR đề xuất vào `aliases/*.yaml`, `brand_aliases.yaml` hoặc `_context_guards.yaml`. Người duyệt mới được gộp. Alias mới ngắn phải qua `_context_guards.yaml`.

**Mẫu câu hỏi:**

```json
{"state": "SURFACE_FORM: «Vinaconex»\nCONTEXTS:\n1) «Giầy Thượng Đình có tân Tổng Giám đốc là lãnh đạo Vinaconex»\n2) «…»",
 "questions": {
   "is_VCG": {"type": "noul", "question": "Is «Vinaconex» a common name for Vietnam Construction and Import-Export JSC (stock code VCG)?"},
   "is_V21": {"type": "noul", "question": "Is «Vinaconex» a common name for Vinaconex 21 JSC (stock code V21)?"},
   "is_parent_only": {"type": "noul", "question": "Does «Vinaconex» here refer to a parent group that is not itself a listed company?"}}}
```

**Cách ghi không vi phạm luật.** Runtime giữ nguyên tất định. Tri thức mới đi qua người duyệt vào YAML. Jev không ghi vào kho. Vì P(yes)≠1−P(no), điểm chỉ dùng để xếp hạng, không đặt ngưỡng tuyệt đối. Quan hệ mẹ/con (Sovico với HDB/VJC) phải là loại bản ghi riêng, không phải alias.

---

## 5. Ý tưởng bị loại và lý do

| Ý | Lý do loại |
|---|---|
| X1 Giải đấu shard GICS1 trên 1093 mã (A4) | Khoảng 100K token mỗi bài, có nguy cơ chạm 32K/shard, NONE giữa các shard không so được, báo động giả cộng dồn [critique_F]. Về quản trị, Jev quét cả kho tức là thành bộ nhận diện song song thay LLM (rủi ro 5) [critique_G]. Chỉ giữ ý "thước đo recall" trong spike, không vào runtime. |
| X2 Tìm theo tầng (A5) | Lỗi lan tầng, tuần tự 4 × 500 ms, công ty đa ngành (Vingroup/VinFast) lạc tầng [critique_F]. Cùng lý do quản trị với X1. |
| X3 Dedup sự kiện theo cặp (C-Ý7) | Jev so số kém [S], mà "700 tỷ" với "500 tỷ" là hai sự kiện. Trùng `story-dedup-clusterer`. |
| X4 Jev trước LLM (C-Ý8) | Gây neo cho LLM, phá tính độc lập của phép đối chiếu, thêm bước trước phiên điều phối (trái R7). Ideator C tự loại. |
| Xoá guard tất định trong `detect()` (phần runtime của B-Ý1/Ý2/Ý3) | Guard chỉ bắn 0,9% tiêu đề [V ideas_B]; thay bằng dịch vụ không seed biến lỗi ổn định thành lỗi ngẫu nhiên và làm `code_first` mất tính tái lập [critique_F, critique_G]. Giữ lại ở dạng **L8/L9 chỉ đo**. `CODE_STOPLIST` đúng tuyệt đối, không thay. |
| Vai trò chủ thể dùng để **định tuyến** (phần "quyết định giao hàng" của B-Ý5/C-Ý5) | Thành cổng mới, trái R5. Chỉ giữ ở dạng cột thông tin hoặc khoá sắp xếp (Concept 2). |

### Bất đồng giữa ideator và critic (giữ nguyên, không làm mờ)

1. **Con số 26% unlisted-trong-kho (D vs F).** Ideator D coi 578/2206 chuỗi là "lỗ nối về kho lớn nhất" và đề xuất B1 relink mới. Critic F chỉ ra B1 **đã có** trong `IntentResolver`, và 206/206 ca trượt đo được là do mã nhóm sai dạng, nên con số của D bị thổi phồng. Hệ quả của F: A3, C-Ý1, D-B1 đang ước lượng lợi ích trên nền sai. Hai bên cũng đo trên nền khác nhau (D: 365 bài, 2206 chuỗi; F: 92 bản ghi parse được, 549 cặp; đường dẫn đọc cũng khác, `agent_outputs_l1` và `agent_outputs_article`). Chưa đối chiếu được; Spike -1 phải chốt lại một nền duy nhất.
2. **B1 có cần ADR không (D vs F vs G).** D: cần ADR quyết định bản nối có được tính là "đã phân tích". F: không cần, vì mô hình đã quyết thực thể, chỉ cần ghi `method` mới. G: hợp lệ để kiểm, nhưng chỉ được ghi nhãn `relinked_exact` đi kèm, không sửa `in_list`, và cần một ADR ngắn. Tài liệu này nghiêng về G (thận trọng nhất), nhưng quyết định thuộc Human (câu hỏi Q2).
3. **Jev thay guard (B vs F, G).** Ideator B muốn xoá khoảng 60 dòng `if` (morphology Mỹ/Nga, PGD) nếu Jev khớp guard ≥95%. F cho giá trị 2 vì guard chỉ bắn 0,9%. G chấm rủi ro 4 vì phá tính tất định của bộ đối chiếu. B vẫn có lý ở một điểm mà critic không bác: `drop_bare` làm mất recall mà hiện không ai đo. Nên giữ L9 như một phép đo recall, không như thay đổi runtime.
4. **Prompt injection (B vs G).** B: rủi ro "gần như bằng 0" vì tiêu đề ngắn, nguồn báo chí. G: không đồng ý, tiêu đề đến từ RSS bên thứ ba; bán kính thiệt hại chỉ nhỏ khi nhãn Jev không có quyền ghi. Tài liệu này theo G: bọc state thành trường, bộ đỏ 20 tiêu đề (k5), không đưa thân bài dài vào state.
5. **Giá trị của GICS3 (A vs F, G).** A xếp A1 là ý tin nhất vì cả không gian nhãn vừa trần 255. F: LLM đã phát nhóm IND, chỉ bị rơi do mã nhóm sai dạng, nên giá trị 3 và phải đo lại sau N0. G: Jev tự gán ngành toàn bài là nhận diện chứ không phải kiểm (rủi ro 3), chỉ được so với `IND_*` của LLM.
6. **AnyJev cục bộ có thoát Cấp 3 không (D vs G).** D ưu tiên AnyJev để "tránh hard gate Cấp 3 và va chạm D6". G: AnyJev vẫn là một model ngoài deepseek-flash, nên **ở runtime** vẫn cần ADR sửa D6; chỉ spike offline không chạm DB vận hành mới không cần ADR. Hai bên đồng ý phần spike, bất đồng phần runtime.
7. **Cách đọc ADR 0009 D6 (G tự nêu).** Câu chữ D6 là "mọi route agent = deepseek-flash", lý do là chi phí token; Jev gọi ngoài DSH không phải "route agent". G vẫn kết luận không được lách bằng câu chữ vì AGENTS.md §6C nói "mọi model". Chưa ideator nào phản bác, nhưng đây là điểm Human cần chốt.
8. **Số khoá alias dùng chung.** B đếm 60 (trên index alias của `detect`), F đếm 54 (canonical + alias toàn kho). Khác cách đếm, không mâu thuẫn bản chất.

---

## 6. Chuỗi thí nghiệm đề xuất, từ rẻ nhất

Mọi thí nghiệm chạy offline trên bản sao DB hoặc tệp đầu ra W365 đọc chỉ đọc. Không thí nghiệm nào làm cổng chặn đợt. Chi phí token chỉ ghi nhận.

| Bước | Tên | Cần Jev? | Cấp | Chi phí | Đầu ra |
|---|---|---|---|---|---|
| **E0** | Spike -1: chuẩn hoá mã nhóm trong `IntentResolver`, trả danh sách ứng viên thay vì `setdefault`, đổi bộ chọn và phép đếm sang danh sách trắng `l1_source = 'agent'`, kèm test hồi quy | Không | Cấp 2 (story + test); riêng phần đổi bộ chọn nên có Human duyệt vì chạm ngữ nghĩa độ phủ | 0 token | Tỷ lệ unlisted-trong-kho mới của W365 trên **một nền duy nhất**; danh sách mention còn chưa nối được |
| **E1** | Golden set tiêu đề | Không | Cấp 2 | Công người | Khoảng 320 cặp (bài, mention, entity_id/NIL, phạm vi title/lead, vai trò) |
| **E2** | Entity card cho 30 thực thể hay nhầm (VIC/GSM, NHNN/"Thống đốc", MY/"Wall Street", TTL, OGC, NVB, ANV/NAV...) | Không | Cấp 2 | 0 token | `entity_cards.json` bản thử, curator duyệt `not_for` |
| **E3** | Vòng học alias không Jev (Concept 3, bước 1–2) | Không | Cấp 2 | 0 token | Top-30 form dương + hàng đợi âm; đếm bao nhiêu form thật sự có ID |
| **E4** | Bàn hiệu chuẩn M1, offline | Có (AnyJev cục bộ) | Spike offline, không chạm DB vận hành | Máy cục bộ + token deepseek-flash | Bảng so sánh các hệ trên 3 tác vụ |
| **E5** | Jev SaaS shadow | Có | **Cấp 3**: ADR sửa D6 + ADR nhà cung cấp + API token, Human duyệt | < $0,05/đợt [I] | Bản ghi shadow thật trên đợt thật |

**Golden set (E1)** theo thiết kế của Ideator D:
- **Phân tầng:** BOTH 60, CODE_ONLY 48, LLM_ONLY mã CP 80, unlisted-trong-kho 60 (**lấy lại sau E0**), alias trùng 30, bẫy chữ Latin 3 ký tự 20 (CEO, SBV, KIS, FPT/FTS), mẹ/con và thương hiệu 25, bộ đỏ injection 20.
- **Tầng khó:** (a) alias là từ thường, (b) tên người, (c) thương hiệu con, (d) mẹ/con, (e) mã Latin trùng từ thường, (f) mã và tên lệch nhau ("Xây dựng CDC").
- **Gán nhãn:** 2 người độc lập, đo Cohen κ, người thứ ba phân xử. Cặp κ thấp tách thành tầng "mơ hồ thật", không tính cho hệ nào.

**Các hệ so sánh trong E4** (mỗi hệ chạy trên cùng 3 tác vụ: L4 nhập nhằng, L3 link phần dư, L5 vai trò; thêm L6 GICS3 nếu còn thời gian):
- **(0)** Resolver đã sửa sau E0 (baseline bắt buộc, theo critique_F).
- **(i)** B1 + B2: tra bảng cộng alias đã học ở E3.
- **(ii)** deepseek-flash được hỏi **đúng cùng câu hỏi** với cùng card, trả `confidence` 0–1 trong schema. Nhánh này không thêm model mới.
- **(iii)** AnyJev cục bộ (Apache-2.0), cùng giao diện `choice/noul`, cùng card; option tiếng Việt và tiếng Anh là hai biến thể.
- **(iv)** Jev SaaS: **chỉ sau khi có ADR** (E5). Trước đó để trống cột.

**Chỉ số:** P/R/F1 của bước nối (micro, theo type, theo tầng khó); NIL accuracy; ECE 10 bin cho hệ có xác suất; coverage@P≥0,95; |ΔP| khi đảo thứ tự option; AUROC của P(yes) cho vai trò; p95 độ trễ.

**Ngưỡng kill** (Ideator D, vi phạm một điều là dừng hệ Jev/AnyJev tương ứng):
- **k1:** F1 trên các tầng khó (a)(c)(d)(e) không vượt baseline (0)+(i) ít nhất 5 điểm.
- **k2:** ECE > 0,08, hoặc không tốt hơn ECE của deepseek-flash (ii). Nếu (ii) đã có ECE ≤ 0,08 thì Jev không có lý do tồn tại.
- **k3:** > 10% cặp có |ΔP| > 0,15 khi đảo thứ tự option.
- **k4:** Accuracy trên tiêu đề tiếng Việt thấp hơn bản dịch tiếng Anh của cùng tiêu đề quá 5 điểm.
- **k5:** p95 > 800 ms mỗi bài, hoặc có 1 ca injection lọt qua trong bộ đỏ 20 tiêu đề.

**Ngưỡng riêng cho L5 (vai trò):** nếu (ii) deepseek-flash và nhãn người đồng thuận > 90% thì Concept 2 thừa, đưa `role` vào schema của LLM thay vì thêm verifier.

**Nhánh quyết định sau E4:**
- AnyJev đạt, Jev chưa đo: có thể dừng ở AnyJev offline làm công cụ curator (Concept 3), không cần runtime.
- Cả hai đạt và vượt (ii) rõ: soạn ADR sửa D6 cho vai model-verifier, sau đó E5.
- (ii) đạt ngang: không thêm model; dùng câu hỏi và card với chính deepseek-flash trong một bước kiểm riêng (vẫn phải cân R7).

---

## 7. Câu hỏi mở cho Human

1. **Q1. Danh sách trắng `l1_source`.** Có đồng ý đổi `ANALYZED_L1` và phép đếm độ phủ ≥90% sang `l1_source = 'agent'` ngay (E0), độc lập với Jev?
2. **Q2. Bản nối tra bảng.** Kết quả chuẩn hoá mã nhóm và tra bảng trên chuỗi LLM đã trích (N0) được ghi thế nào: sửa thẳng `in_list` (theo F), hay chỉ nhãn `relinked_exact` đi kèm với ADR ngắn (theo G)?
3. **Q3. ADR 0009 D6.** D6 áp cho "route agent trên DSH" hay "mọi model trong dự án"? Một model-verifier chạy offline ngoài DSH có cần ADR không?
4. **Q4. AnyJev ở runtime.** Nếu E4 đạt, có chấp nhận một model mở chạy cục bộ (vận hành máy, chuỗi cung ứng trọng số) như lớp thứ ba "model-verifier", hay chỉ cho dùng làm công cụ curator offline?
5. **Q5. Công gán nhãn.** Ai gán nhãn golden set khoảng 320 cặp (2 người + 1 phân xử)? Có chấp nhận quy mô nhỏ hơn cho vòng đầu?
6. **Q6. Trường `parent` trong kho.** Có muốn mở kho thực thể để chứa quan hệ mẹ/con (Sovico → HDB/VJC, TCB → TCX, Masan → MCH)? Đây là đổi data contract (Cấp 3) và là điều kiện của L10.
7. **Q7. Vai trò chủ thể.** Nên đưa trường `role` vào `l1-entity-output-v1` do LLM trả (thay đổi schema), hay giữ LLM như cũ và để verifier bên ngoài chấm?
8. **Q8. Bảng shadow.** Khi qua giai đoạn spike, có chấp nhận thêm bảng `entity_link_check` vào DB vận hành (Cấp 3), hay giữ kết quả ở tệp JSONL ngoài DB?
9. **Q9. Ngôn ngữ option.** Card viết tiếng Việt, tiếng Anh hay song ngữ làm mặc định, khi chưa có số đo tiếng Việt của Jev?
