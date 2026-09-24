# Critic F: khả thi kỹ thuật của các ý tưởng Jev cho nhận diện thực thể L1

Nhãn: [S] có nguồn · [V] kiểm tại máy ngày 24/09 (đọc mã, đọc chỉ đọc `data/agent_outputs_article/article_W365_*.output.json`) · [I] suy luận. Không gọi Jev, không ghi DB.

## 0. Phát hiện chặn trước mọi ý tưởng: lỗ "unlisted nhưng có trong kho" là lỗi định dạng mã nhóm

- [V] `IntentResolver` (`src/agent/intent_resolve.py`) **đã** tra chuỗi LLM về kho bằng `_fold` trên canonical_name và aliases, theo loại được phép của mã nhóm. Tức B1 của Ideator D đã có sẵn trong mã.
- [V] Nhưng `resolve_one` trả "ngoài danh mục" ngay khi `group not in VALID_GROUPS` (11 mã: TIC, COM, PER, FND, IDX, EXC, IND, GEO, THM, AST, INS).
- [V] Trong 92 bản ghi W365 parse được, 314/549 cặp (57%) có mã nhóm sai dạng: `THM:TÍN DỤNG` 45, `ASSET_CLASS:...` 43, `IND_GICS3:...` 39, `MACRO_GEO` 39, `INS:...` 32, `EXCHANGE` 25, `IND_GICS2` 25, `INSTITUTION` 24, `INDEX` 23.
- [V] 387 cặp (không tính PER) rơi vào unlisted. 206 cặp trong số đó khớp đúng một khoá trong kho, và **cả 206 đều do mã nhóm sai dạng**. Không có ca nào mà mã nhóm đúng lại vẫn trượt.
- [I] Con số 578/2206 (26%) của Ideator D chủ yếu cùng một gốc: mô hình lẫn mã nhóm với entity_id/type của kho. Bước sửa là chuẩn hoá mã nhóm (lấy phần trước `:`, ánh xạ `ASSET_CLASS→AST`, `MACRO_GEO→GEO`, `INSTITUTION→INS`, `EXCHANGE→EXC`, `INDEX→IDX`, `IND_GICS*→IND`, `MACRO_THEME→THM`). Đây là tra bảng thứ LLM đã quyết, không phải "giả lập trí tuệ" (§6C). Kèm một test hồi quy, và siết ví dụ trong `build_article_prefix.py`.
- [I] Hệ quả: A3, C-Ý1, D-B1 đang ước lượng lợi ích trên nền số bị thổi phồng. Phải sửa bước chuẩn hoá và đo lại W365 **trước khi** tính giá trị của bất kỳ linker nào.
- [V] Rủi ro thứ hai trong resolver: `_by_type_name` dùng `setdefault`, nên khoá dùng chung trong cùng một loại (ví dụ "nam việt" → ANV/NAV) **âm thầm lấy thực thể nạp trước**. `detect()` thì trả cả hai. Ở phía LLM, nhập nhằng bị che mất chứ không phải được giải. Đây mới là chỗ J1/A2/B-Ý4 có đất. Toàn kho có 54 khoá canonical+alias dùng chung giữa các thực thể (Ideator B đếm 60 trên index alias của `detect`).

## 1. Ràng buộc API đối chiếu nhanh

- 255 option: GICS1/2/3 (11/28/51), vĩ mô và định chế (37) vừa trần. 1093 TICKER thì không. Mọi ý "toàn kho mã" đều phải chia shard.
- 32K cho state cộng câu dài nhất [S]. Chưa rõ option có tính vào 32K hay chỉ vào 64K. A4 phụ thuộc hoàn toàn vào chỗ này, nên phải hỏi TypeSafe hoặc đo trước.
- Noul không có confidence, và P(yes) ≠ 1−P(no). Ý nào dùng noul làm ngưỡng tuyệt đối phải hiệu chuẩn theo từng câu hỏi. Dùng để xếp hạng thì an toàn.
- Không có multi-label gốc. "BOTH" trong C-Ý3 và top-5 noul trong A1 là mô phỏng, xác suất giữa các câu không cộng được với nhau.
- Không seed và nhạy thứ tự option. Chạy 2 hoán vị làm chi phí ×2. Mọi con số chi phí dưới đây đã ×2.
- Chi phí gần như không bao giờ là rào cản ($0,042/1M). Rào cản thật là **trễ × số câu** và **ADR Cấp 3** (ADR 0009 D6).

## 2. Chấm từng ý (Khả thi K 1–5, Giá trị G 1–5)

| Ý | K | G | Nhận xét kỹ thuật |
|---|---|---|---|
| A1 GICS3 choice + noul top-5 | 4 | 3 | Vừa trần 255. Nhưng [V] LLM đã phát nhóm IND, chỉ bị rơi do mã nhóm sai dạng (`IND_GICS3:` 39, `IND_GICS2:` 25). Đo lại sau khi chuẩn hoá. Bước "code kiểm nhất quán cây GICS" có sẵn qua `attributes.gics1/2/3`. |
| A2 alias fold → Jev gỡ nhập nhằng | 4 | 3 | Trùng B-Ý4 và D-J1. Nên gộp thành một thí nghiệm. |
| A3 mention LLM → top-K → Jev | 4 | 2→3 | Trùng C-Ý1. Nền 26% là số thổi phồng (mục 0). Còn giá trị thật ở phần dư: KienlongBank, PVCFC, Novaland, là ca cần fuzzy hoặc n-gram. |
| A4 giải đấu shard GICS1 | 2 | 1 | 12 shard, mỗi bài khoảng 100K token. Có nguy cơ chạm 32K/shard. NONE giữa các shard không so được với nhau. Báo động giả cộng dồn. Loại. |
| A5 tìm theo tầng | 2 | 1 | Lỗi lan tầng và tuần tự (4 × 500 ms). Vingroup/VinFast lạc tầng. Loại. |
| A6 noul 37 thực thể vĩ mô | 3 | 2 | Kỹ thuật chạy được, nhưng 37 câu × 2 hoán vị là khoảng 74 câu/bài. Chưa rõ state có bị tính lại mỗi câu không; nếu có thì khoảng 20–40K token/bài, vẫn rẻ. Chồng lấn nhóm GEO/THM/INS mà LLM đã phát (bị rơi do mã nhóm sai dạng). |
| B-Ý1 noul Mỹ/Nga thay morphology | 4 | 2 | Guard chỉ bắn 0,9% tiêu đề. Xoá guard tất định để dựa vào dịch vụ không seed thì chuyển lỗi ổn định thành lỗi ngẫu nhiên. Chỉ nên làm shadow đo. |
| B-Ý2 khôi phục alias trần ngành | 3 | 2 | Đo được recall mất do `drop_bare`, nhưng LLM đã gắn IND. Khoảng 1.000 câu/kho là rẻ. Ví dụ "mất điện trên tàu" là đúng failure mode đọc nghĩa đen. |
| B-Ý3 noul PGD/mã trùng viết tắt | 4 | 2 | 39 ca, lớp lỗi hẹp. `CODE_STOPLIST` đã đúng tuyệt đối, không nên thay. |
| B-Ý4 choice 60 alias dùng chung | 4 | 3 | Ghép với mục 0 (resolver `setdefault`), vì ca "first-wins" đang bị che ở phía LLM. |
| B-Ý5 / C-Ý5 / D-J2 vai trò chủ thể | 4 | 4 | Ba ideator cùng ý, đúng D7 của hội đồng. Choice 3–5 mức dùng được confidence. Cảnh báo §6C: chỉ làm cột thông tin, không làm cổng. |
| B-Ý6 / C-Ý3 trọng tài bất đồng | 4 | 3 | `reconcile()` đã sinh nhãn BOTH/LLM_ONLY/CODE_ONLY. Chỉ cần đọc `intent_source`. "BOTH/NEITHER" là multi-label giả, nên tách thành 2 câu noul. |
| B-Ý7 đào guard offline | 4 | 3 | Đã có `scripts/maintenance/audit_alias_false_positives.py` làm khung. Nối Jev vào đó thay vì viết script mới. |
| B-Ý8 mẹ/con | 2 | 3 | Kho không có trường `parent`, nên thiếu dữ kiện thì chết (cùng kết luận với D-J3). |
| C-Ý2 entity card | 5 | 4 | Build tất định, 0 token, dùng được cho Jev, AnyJev và cả prompt deepseek. Là hạ tầng cho mọi ý choice. Rủi ro: một card sai là lỗi hệ thống. |
| C-Ý4 / D-B2 vòng học alias | 5 | 4 | Chạy được **không cần Jev**. Jev chỉ xếp hạng. Phải chạy sau khi chuẩn hoá mã nhóm, nếu không hàng đợi sẽ đầy HOSE/Fed giả. |
| C-Ý6 GICS3 cho unlisted | 4 | 2 | Tên riêng ít ngữ cảnh ("Tân Hoàng Minh"), nên phải kèm tiêu đề trong state. Sovico đa ngành cần multi-label. Ghép với A1: cùng một câu choice GICS3. |
| C-Ý7 dedup sự kiện | 2 | 2 | Jev kém so số [S]. Trùng `story-dedup-clusterer`. Loại. |
| C-Ý8 Jev trước LLM | 1 | 1 | Trái "một đợt = một run_code", gây neo. Đồng ý loại. |
| D-B1 relink tất định | 5 | 5 | Đã có trong `IntentResolver`. Việc thật là chuẩn hoá mã nhóm (mục 0). Không cần ADR "tính là đã phân tích", vì mô hình đã quyết thực thể. Chỉ cần ghi nhận `method` mới. |
| D-J1 | 4 | 3 | Gộp với A2 và B-Ý4. |
| D-J3 mẹ/con | 2 | 3 | Thiếu `parent` (xem B-Ý8). |
| D-J4 embedding top-k | 3 | 2 | Thêm hạ tầng. n-gram ký tự trên 1.262 tên đã đủ cho top-K. |
| D-M1 bàn hiệu chuẩn 4 hệ | 4 | 5 | Phải là khung đo chung cho mọi ý Jev. Cần thêm hệ (0) "resolver đã sửa mã nhóm". |

## 3. Tính sai hoặc thiếu trong chi phí

- A4: "khoảng 100K token/bài" là đúng bậc, nhưng rào cản là trần 32K/shard và trễ, không phải tiền.
- C-Ý1: khoảng $0,05/đợt là hợp lý, nhưng giả định 4 mention/bài. [V] W365 có khoảng 6 cặp/bài (549/92). Sau khi chuẩn hoá, chỉ còn gọi cho phần chưa link được, nên số câu **giảm** mạnh.
- A6, B-Ý2: chưa tính ×2 hoán vị và việc state có thể bị tính lại cho mỗi câu. Vẫn dưới $0,01/đợt, không đổi kết luận.
- D-J2: "1.000 câu/đợt × 400 token" không khớp nền. 289 mã LLM_ONLY × 2 dạng hỏi (khẳng định/phủ định) × 2 hoán vị là khoảng 1.150 câu. Con số đúng bậc, nhưng lý do là như vậy.
- Mọi ý đều bỏ qua trễ. 70–500 ms × vài trăm câu, chạy song song thì ổn, tuần tự (A5) thì không.

## 4. Đề xuất ghép (các ideator chưa ghép)

1. **Spike -1, 0 token, không Jev:** chuẩn hoá mã nhóm trong `IntentResolver` cộng test, làm lộ nhập nhằng `setdefault` (trả danh sách ứng viên thay vì lấy cái đầu), rồi đo lại tỷ lệ unlisted-trong-kho của W365. Mọi baseline của D-M1 phải lấy từ đây.
2. **Card + choice nhập nhằng = một thí nghiệm:** C-Ý2 card làm option cho A2, B-Ý4, D-J1 và phần "first-wins" của resolver. Một golden set, hai hoán vị.
3. **Một câu GICS3 cho hai việc:** A1 (ngành của bài) và C-Ý6 (ngành của unlisted) dùng chung option 51 GICS3 + NONE, chỉ khác câu hỏi. Chung card, chung đo độ lệch vị trí.
4. **Vai trò chủ thể (B-Ý5/C-Ý5/D-J2) đặt trên `intent_source`:** chỉ hỏi cho LLM_ONLY và bất đồng (B-Ý6), không hỏi mọi thực thể. Như vậy vừa là trọng tài vừa là D7, số câu giảm khoảng 3 lần.
5. **Vòng học alias (C-Ý4/D-B2) nối vào `audit_alias_false_positives.py` (B-Ý7):** một hàng đợi curator duy nhất, gồm alias thiếu (dương) và alias gây nhiễu (âm). Jev chỉ xếp hạng.

## 5. Kết luận

- Không ý nào cần Jev để lấy phần giá trị lớn nhất. Phần đó là sửa chuẩn hoá mã nhóm và vòng học alias.
- Jev còn đất ở ba nhóm hẹp có tập đóng nhỏ: nhập nhằng alias có card, vai trò chủ thể, và ngành GICS3.
- Loại A4, A5, C-Ý7, C-Ý8.
- Mọi phép thử với Jev SaaS vẫn là Cấp 3 (ADR sửa D6). Nên ưu tiên AnyJev cục bộ cho D-M1.
