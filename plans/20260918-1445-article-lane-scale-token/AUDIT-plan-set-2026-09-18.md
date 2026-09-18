# AUDIT — Tập ba plan trước khi implement

|  |  |
| --- | --- |
| Ngày | 2026-09-18 |
| Phạm vi | `20260918-1133-l1-llm-lean-token` (SUPERSEDED) · `20260918-1445-article-lane-scale-token` (Master kỹ thuật) · `20260918-1624-dsh-token-economy-workmethod` (Tầng quy trình) |
| Mục đích | Audit logic và định hướng. **Không** chạy, **không** implement, **không** sửa ba plan. Tài liệu này chỉ nêu vấn đề và đề xuất cách giải. |
| Phương pháp | Tự kiểm chứng lại mọi khẳng định chịu lực bằng mã nguồn DSH `0.1.5` và file thật trong repo, không tin tài liệu nói về tài liệu |
| Kết quả | **4 mâu thuẫn chặn thực thi** · **7 lỗ hổng logic thiết kế** · **4 tiêu chí nghiệm thu sai** · **3 lỗi thứ tự phụ thuộc** · **4 vấn đề định hướng** · **2 con số sai** |

> **Kết luận một câu:** phần lõi kỹ thuật của tập plan là đúng và đã sống sót ba vòng audit, nhưng **không thể thi hành nguyên trạng** — bốn mâu thuẫn ở §2 làm hai phase đầu trượt nghiệm thu ngay khi chạy, và bảy lỗ hổng ở §3 sẽ chỉ lộ ra sau khi đã tiêu token.

---

## 1. Những gì tôi tự kiểm chứng (không lấy từ plan)

Ba khiếm khuyết P0 của plan 1624 đều **đúng**. Tôi tìm thêm một cái thứ tư mà cả ba plan bỏ sót.

| # | Khẳng định | Kết quả | Bằng chứng trực tiếp |
|:-:|---|---|---|
| V1 | `maxDepth: 0` cấm delegation hoàn toàn | **ĐÚNG** | `dsh-subagent/lib/types/child-agent.js:32-41` — `childDepth = delegationDepthOf(parent) + 1`; `if (maxDepth !== undefined && childDepth > maxDepth) throw`. Con đầu tiên là depth 1 > 0. `dsh-tool-subagent/README.md:53`: *"`0` forbids delegation"* |
| V2 | `run_code` được chèn **sau** lớp lọc `toolFilter` | **ĐÚNG, và chặt hơn plan 1624 mô tả** | `dsh-tools/lib/index.js:2874` — `if (this.modeFor(scope) !== "native") visible.set(RUN_CODE_NAME, ...)` nằm sau vòng `layers.every(layer => layer.admits(name))`. Thêm nữa `:2800` **ném lỗi** nếu `restrict()` cố đặt tên `run_code` |
| V3 | Pruner kết quả tool không đăng ký listener | **ĐÚNG** | `dsh-compaction-tool-result-pruner/lib/index.js` chỉ export class `ToolResultPruner` + `pruneSession()`; không có `ctx.on` nào |
| **V4** | **Không thể đặt `mode` cho agent con** | **PHÁT HIỆN MỚI** | `dsh-tool-subagent/lib/index.js:252-270` — schema `Config` có **đúng 9 khóa**: `provider`, `toolName`, `modelSelectionSettings`, `enableRunInBackground`, `backgroundMode`, `agentOptions`, `persona`, `toolFilter`, `maxDepth`. **Không có `mode`.** Mode giải theo chuỗi layer của cha (`dsh-tools:2668` `modeFor`) |
| V5 | SDK bên trong `run_code` của con `allow: []` là rỗng | **ĐÚNG** | `dsh-tools:2923` `sdkSchemas()` lọc bỏ `run_code` khỏi `view(scope).visible`; `visible` đã rỗng sau `allow: []` ⇒ SDK không khai tool nào |

**Hệ quả kết hợp V2 + V4 + V5:** Conductor ở `ptc` ⇒ mọi con đều `ptc` ⇒ mọi con đều có `run_code` không gỡ được. Con với `allow: []` nhận **đúng một tool là `run_code`, với SDK rỗng bên trong**. Nó không đọc được file (không có binding), nhưng **"tập tool hiệu lực = ∅" là trạng thái không tồn tại** với con PTC.

---

## 2. Bốn mâu thuẫn chặn thực thi

### M1 — Tiêu chí "0 tool" bất khả thi, làm trượt Phase 00 và Phase 03 của plan 1624

| Nơi | Nội dung |
|---|---|
| 1445 §2 bất biến 2 | "LLM không đọc file… **KHÔNG tool**" |
| 1445 §7 | `toolFilter: { allow: [] }` |
| 1624 E15 cách sửa | "worker chạy `mode: native` + `toolFilter.allow: []`" |
| 1624 Phase 00 acceptance | "**tập tool hiệu lực của worker = ∅ được in ra và lưu vào trace**" |
| 1624 Phase 03 acceptance | "**tập tool hiệu lực = ∅ (in ra)**" |

Theo V2/V4/V5, con PTC luôn có `run_code`. Hai tiêu chí nghiệm thu này **không bao giờ đạt**, và chúng là điều kiện đóng phase. Thi hành nguyên trạng thì Phase 00 trượt ở bước cuối, sau khi đã làm hết việc.

**Đề xuất giải:** chọn một trong hai, và ghi vào plan hợp nhất như một quyết định kiến trúc chứ không phải thí nghiệm.

| Phương án | Nội dung | Được | Mất |
|---|---|---|---|
| **P-A (khuyến nghị cho giai đoạn đầu)** | Giữ con PTC, chấp nhận `run_code` + SDK rỗng. Đổi tiêu chí thành: **"SDK của con khai 0 tool"** và **"số bước của con = 1"** | Dùng ngay hạ tầng hiện có; giữ được ledger vì con là Session có projcache; giữ được cô lập context của PTC (U4) | Còn cám dỗ model viết chương trình thừa ⇒ phải đo `turns` làm chỉ số hạng nhất |
| **P-B** | Worker chạy **ngoài tiến trình** (`headless` / `sdk-minimal`), native thật, 0 tool thật | Ranh giới vật lý tuyệt đối | `headless` **không xuất usage** ⇒ đe doạ chính cơ chế đo (xem D1); thêm một đường vận hành mới |

Tiêu chí nghiệm thu đúng trong cả hai phương án: **đo `turns == 1`**, không đo "tập tool = ∅".

### M2 — Plan 1624 tự mâu thuẫn về preset cho con

| Nơi | Nội dung |
|---|---|
| 1624 E3 | "con kế thừa composition của cha qua `composeFrom`, **không có khóa nào để tắt**" |
| 1624 Phase 01 | "Preset `news-scape-article`: `agent-instructions.config.maxBytes: 0`, … `mode: native`; **mount qua junction**" |

Preset áp cho **phiên**, không áp cho con. Nếu E3 đúng (nó đúng) thì preset `news-scape-article` chỉ có nghĩa khi worker là **một phiên riêng**, tức là đã ngầm chọn P-B. Nhưng plan 1624 vẫn liệt "PTC hay headless" là câu hỏi mở #2 và hoãn quyết định tới **Phase 04**.

⇒ **Phụ thuộc vòng:** Phase 01 dựng một preset chỉ hoạt động dưới kiến trúc mà Phase 04 mới chọn.

**Đề xuất giải:** chốt M1 **trước Phase 00**. Quyết định này là tiền đề của mọi phase, không phải kết quả của một thí nghiệm.

### M3 — Cổng ADR 0008: hai plan nói ngược nhau, và ngược với chỉ đạo đã có

| Nơi | Nội dung |
|---|---|
| Chỉ đạo của anh (2026-09-18) | "bỏ cổng ADR 0008 (người xác nhận), tôi sẽ quản lý theo batch hoặc wave" |
| 1445 §8 | Bỏ cổng, thay bằng lệnh wave tường minh; soạn sẵn bảng amendment |
| **1624 §0.3** | "**Phase 01 trở đi theo cổng ADR 0008 hiện hành** cho tới khi Phase 00 chứng minh sai số dự toán ≤ 20%; chỉ sau đó mới trình amendment gỡ cổng" |

Plan 1624 **dựng lại cái cổng anh đã bỏ**, và gắn điều kiện gỡ vào một chỉ số do chính nó định nghĩa.

**Đề xuất giải:** tách bạch hai thứ đang bị trộn.
- **Cổng phê duyệt con người** — anh đã bỏ. Không dựng lại dưới bất kỳ tên nào (1445 §13 anti-scope đã ghi đúng điều này).
- **Chốt kỹ thuật tự động** — giữ, vì chúng bảo vệ chất lượng chứ không xin phép: `est_ctx_peak` vượt ngưỡng thì tự chia batch; `parse_fail` vượt ngưỡng thì dừng wave.

Sai số dự toán ≤ 20% là **chỉ số quan sát**, không phải điều kiện mở khoá.

### M4 — `resolve_rate ≥ 85%` bị chính thiết kế làm sai ngay từ đầu

1624 §9 đặt `resolve_rate ≥ 85%` "theo nhóm thực thể". Nhưng nhóm `PER` (tên lãnh đạo) có resolver là `leaders.yaml`, mà 1445 §4.2 ghi rõ **"chưa có — seed từ `unlisted`, Phase 06"**.

⇒ Từ Phase 03 đến Phase 06, `resolve_rate` của `PER` là **0% theo thiết kế**. Nếu đo gộp, chỉ số tổng bị kéo xuống; nếu đo theo nhóm như §9 nói, nhóm `PER` trượt sàn ở mọi wave.

**Đề xuất giải:** `resolve_rate` đo **theo từng nhóm**, và **miễn trừ `PER`** cho tới khi `leaders.yaml` tồn tại. Ghi `PER` vào một chỉ số riêng: `per_discovery_count` (số tên người thu được để nuôi curator) — đó mới là giá trị của nhóm này trong giai đoạn đầu.

---

## 3. Bảy lỗ hổng logic trong thiết kế

### L1 — Bỏ trần 2.200 ký tự đã **âm thầm gỡ mất bất biến bảo vệ citations**

`rules/05` §2.3 (đang hiệu lực) quy định: *"Bộ lọc BẮT BUỘC loại bỏ theo **nguyên khối đoạn văn** (`<p>`). Tuyệt đối KHÔNG cắt tỉa, biên tập lại câu từ trong các đoạn văn giữ lại, nhằm đảm bảo mọi `source_span` luôn là chuỗi con nguyên văn."*

1445 §3.1 thay trần 2.200 bằng "Smart Semantic Paragraph Distillation" và mô tả việc **chọn** đoạn, nhưng **không tái khẳng định bất biến nguyên khối**. 1624 E8 chỉ bàn về kích thước, không bàn về tính nguyên văn.

Toàn bộ cơ chế citations-by-index (`c:[0,2]`) đứng trên giả định: `p[k]` là **chuỗi con nguyên văn** của `cleaned_text`. Nếu distillation có lúc nào cắt, nối, rút gọn hay sắp xếp lại đoạn, assertion của 1624 E7 (`p[k] in cleaned_text`) sẽ fail hàng loạt và mọi item bị requeue.

**Đề xuất giải:** ghi thành bất biến tường minh trong plan hợp nhất:

> **Distillation chỉ được phép BỎ trọn vẹn một đoạn. Cấm cắt, cấm nối, cấm sửa, cấm đổi thứ tự.** Mảng `p[]` là một tập con giữ nguyên thứ tự của các đoạn gốc, mỗi phần tử là chuỗi con nguyên văn của `cleaned_text`.

Và biến E7 từ "expander kiểm tra" thành **unit test của `article_pack.py`** — bắt lỗi ở nơi sinh ra nó, không phải ở nơi chịu hậu quả.

### L2 — "Trần mềm ≤1.000 token/bài" không phải là một ràng buộc

1624 E8 thay trần cứng 2.200 ký tự bằng "trần mềm ≤1.000 token/bài + histogram". Nhưng không định nghĩa **điều gì xảy ra khi vượt**. Một trần không có hành vi cưỡng chế thì không phải trần, chỉ là một lời chúc.

Hệ quả dây chuyền: `est_ctx_peak` (1445 §5.1, §6.1) và cơ chế tự chia batch đều dựa trên việc **ước lượng được kích thước packet**. Không có bound xác định thì không ước lượng được, và chốt tự động duy nhất của hệ thống mất cơ sở.

**Đề xuất giải:** distillation phải **tất định và có thứ tự bỏ xác định**:
1. Luôn giữ `p0` (sapo).
2. Xếp hạng các đoạn còn lại theo tín hiệu (có số liệu định lượng > có phát ngôn/pháp lý > còn lại).
3. Thêm dần theo thứ tự gốc cho tới khi chạm trần cứng token/bài.
4. Vượt trần ⇒ **bỏ đoạn hạng thấp nhất**, không cắt đoạn.

Khi đó packet size là hàm xác định của đầu vào, `est_ctx_peak` có nghĩa, và L1 được giữ nguyên.

### L3 — Hàng đợi ưu tiên **thừa hưởng điểm mù của code-first**, triệt tiêu chính giá trị của LLM

1445 §2 cho `Code-First Priority Sorter` chạy **trước**, dùng `{code_entities}` để xếp bài vào Tier 1 (khớp watchlist) hay Tier 2/3.

Nhưng §4.1 của chính plan đó ghi: ngành GICS chỉ có 1 alias nên code **không bao giờ** khớp `"đường sắt"`; §4.2 nói `COM` (thương hiệu con như `Bách Hóa Xanh`) và `THM` (chủ đề vĩ mô) là vùng code hay bỏ sót — **đó chính là lý do có LLM**.

⇒ Một bài mà code-first bỏ sót entity thuộc watchlist của user sẽ **không vào Tier 1**, và bị đẩy xuống Batch 2..N. Người dùng nhận chậm đúng những bài mà hệ thống được thiết kế để bắt tốt hơn code.

**Đề xuất giải:** chọn một.
- **Tier 1 thiên về recall:** đưa vào Tier 1 mọi bài có **bất kỳ tín hiệu yếu nào** liên quan watchlist (alias một phần, ngành của mã trong watchlist, từ khoá vĩ mô). Chấp nhận Tier 1 rộng hơn, vì chi phí một bài đã rẻ.
- **Hoặc** chạy một lượt `lite` (chỉ tiêu đề, ~150 token/bài) trên toàn bộ bài trong ngày để LLM gán ưu tiên, rồi mới xếp batch `full`. Tốn thêm một lượt nhưng ưu tiên đúng.

Đây là quyết định định hướng, phải chốt trước khi viết `article_pack.py`.

### L4 — `lite` bị gỡ một nửa; bài toán kinh tế của subscriber-gating chưa được giải lại

Kiểm tra trực tiếp trong 1445:

| Dòng | Nội dung | Ngụ ý |
|---:|---|---|
| §2 (dòng 146) | "TIER 2 & 3 … **vẫn xử lý full toàn bộ**" | 100% bài đi `full` |
| §3.1 (dòng 193-199) | Ví dụ packet **không còn trường `m`** | không còn phân biệt độ sâu |
| §1.4 (dòng 72) | cột "Article Lane (100 bài, `lite`)" | còn `lite` |
| §3.2 (dòng 228) | "`lite` ~ 30–40" | còn `lite` |
| §5.1 (dòng 314) | hàng "100 bài `lite`" | còn `lite` |
| §6.1 (dòng 368) | "5 batch × 100 bài (320 full / **180 lite**)" | còn `lite` |
| §6.2 (dòng 388) | cột ledger `depth_mix` | còn `lite` |

Kiến trúc nói một đằng, hợp đồng và bảng đo nói một nẻo.

Đây không phải lỗi biên tập mà là **một quyết định kinh tế chưa được ra**. Thiết kế cũ rẻ được là nhờ subscriber-gating: L1 (rẻ, chỉ tiêu đề) chạy trên 100% bài, Gold (đắt, có body) chỉ chạy trên 8–25% bài có người đăng ký. Gộp thành một agent xử lý `full` cho 100% bài nghĩa là **trả chi phí body cho toàn bộ**.

| Kịch bản (307 bài/ngày) | Token/ngày | Ghi chú |
|---|---:|---|
| 100% `full` (~1.220/bài) | ~375.000 | Bao phủ sâu toàn bộ |
| 35% `full` + 65% `lite` | ~165.000 | Bao phủ 100%, sâu có chọn lọc |

Chênh ~2,3 lần. Với backlog thì chênh tuyệt đối lớn hơn nhiều.

**Đề xuất giải:** ra quyết định tường minh và đồng bộ toàn bộ tài liệu theo nó. Khuyến nghị **giữ `full`/`lite`**, vì nó bảo toàn được mục tiêu nghiệp vụ "bao quát toàn bộ thị trường" mà không phải trả giá sâu cho tin không ai đọc — và vì `lite` vẫn cho ra thực thể đầy đủ để định tuyến watchlist, đúng vai trò L1 cũ.

### L5 — Không có cửa sổ sống chung và không có điều kiện quay lui

1624 E9 yêu cầu archive toàn bộ packet cũ, E10 yêu cầu deprecate 6 hạng mục, **"trong cùng phase"**. 1624 §10 có dòng rủi ro "hai nguồn sự thật" và giải bằng "archive + deprecate trong cùng phase" — tức là **cắt đứt đường cũ**.

Nếu làn mới trượt DoD trên dữ liệu thật, đường cũ đã bị gỡ và 2.118 packet đã bị archive. Không plan nào định nghĩa: điều kiện nào thì quay lui, quay lui bằng cách nào, và ai quyết.

**Đề xuất giải:** đường cũ chuyển sang trạng thái **đóng băng nhưng gọi được** (in cảnh báo, không xoá) trong ít nhất một chu kỳ vận hành đầy đủ. Điều kiện quay lui định lượng, ví dụ: DoD pass dưới 95% hoặc `parse_fail` trên 10% kéo dài hai wave liên tiếp. Archive chỉ thực hiện sau khi làn mới chạy sạch trọn một ngày.

### L6 — Mục tiêu off-peak ≥80% xung đột với ưu tiên giao sớm

1445 §2 và 1624 Phase 05: Batch 1 (Tier 1, bài giá trị nhất) **giao ngay** khi xong. 1624 §10 xác nhận Batch 1 chấp nhận giá peak.

Nhưng 1624 §9 đặt chỉ tiêu "Tỷ lệ chi phí off-peak **≥ 80% tổng wave**". Nếu Tier 1 luôn chạy giờ hành chính (đúng lúc peak: 08–11h và 13–17h giờ VN) và chiếm tỷ trọng đáng kể, chỉ tiêu này không đạt được vào những ngày nhiều tin ưu tiên — mà đó lại là những ngày hệ thống chạy đúng nhất.

**Đề xuất giải:** đổi mẫu số. Chỉ tiêu áp cho **chi phí bulk và backlog**, không áp cho tổng wave. Tier 1 có chỉ tiêu riêng là **độ trễ giao hàng**, và chi phí peak của nó được ghi nhận như chi phí có chủ đích.

### L7 — Nhóm `PER` phát sinh chi phí ba phase trước khi tạo ra giá trị

Đã nêu ở M4 về mặt chỉ số. Về mặt thiết kế còn một câu hỏi chưa ai đặt: **có nên để LLM phát `PER` ngay từ Phase 03 không?**

Lập luận giữ: chi phí vài token mỗi bài, và đây chính là nguyên liệu để xây `leaders.yaml` — không thu thập thì không bao giờ có. Lập luận bỏ: ba phase liền output không resolve được gì.

**Đề xuất giải:** **giữ**, nhưng khai báo đúng vai trò. `PER` ở giai đoạn đầu là **cơ chế thu thập dữ liệu cho catalog**, không phải cơ chế nhận diện. Đo bằng `per_discovery_count`, không đo bằng `resolve_rate`.

---

## 4. Bốn tiêu chí nghiệm thu sai hoặc không kiểm được

| # | Tiêu chí | Vấn đề | Sửa |
|:-:|---|---|---|
| N1 | "tập tool hiệu lực = ∅" (1624 Phase 00, 03) | Bất khả thi với con PTC (M1) | "SDK của con khai 0 tool" **và** "`turns == 1`" |
| N2 | "`cacheReadTokens` ≥ 95% kích thước prefix" (1624 E5) | Phụ thuộc hành vi cache phía nhà cung cấp, mà chính api-docs ghi là **best-effort, không đảm bảo**. Một phase có thể trượt vì lý do ngoài hệ thống | Chuyển thành **chỉ số theo dõi có ngưỡng cảnh báo**, không phải điều kiện đóng phase. Chỉ giữ tính chất kiểm được: prefix **byte-identical** giữa hai batch liên tiếp |
| N3 | DoD pass: "100%" (1624 Phase 03) vs "≥ 99% item" (1624 §9) | Hai số cho cùng một thứ trong cùng tài liệu | Chốt một số. Khuyến nghị **≥ 99% item** cho nghiệm thu, 100% là kỳ vọng không phải cổng |
| N4 | `parse_fail`: "< 2%" (Phase 03) vs "< 10% dừng wave" (§9) | Đọc như mâu thuẫn; thực ra là hai khái niệm khác nhau nhưng chưa bao giờ nói ra | Ghi rõ: **2% là ngưỡng nghiệm thu chất lượng**, **10% là ngưỡng ngắt mạch vận hành** |

Thêm một quan sát chung: nhiều tiêu chí đang trộn ba loại khác nhau mà không phân biệt — **điều kiện đóng phase** (phải đạt mới đi tiếp), **ngưỡng ngắt mạch** (chạm thì dừng máy), và **chỉ số quan sát** (chỉ để nhìn). Plan hợp nhất nên có một bảng duy nhất, mỗi chỉ số gắn đúng một loại.

---

## 5. Ba lỗi thứ tự phụ thuộc

### D1 — Xây thước đo trước khi chọn thứ cần đo

1624 Phase 00 xây `token_ledger.py` đọc JSONL của phiên, và ghi đúng rằng phải **duyệt `subagentCatalog` rồi cộng projcache từng con** vì burn của con không nằm trong `tokenUsage` của cha.

Nhưng nếu Phase 04 chọn **P-B (headless)**, worker không còn là con của phiên nào cả. 1624 §6.1 tự ghi: headless *"không `--json`, không usage"*. Ledger xây ở Phase 00 theo mô hình cha-con sẽ **không đọc được worker**, và phải viết lại.

⇒ **Quyết định kiến trúc (M1) phải đứng trước việc xây ledger**, hoặc ledger phải được thiết kế để đọc cả hai hình thái ngay từ đầu.

### D2 — Chốt tự động dựa trên đại lượng chưa có bound

`est_ctx_peak` điều khiển việc tự chia batch (1445 §5.1, §6.4). Nó ước lượng kích thước packet. Kích thước packet do distillation quyết định, mà distillation chưa có bound tất định (L2).

⇒ Vòng phụ thuộc: chốt an toàn dựa trên một ước lượng không có cơ sở. Giải L2 trước thì D2 tự hết.

### D3 — Lớp B được chẩn đoán là tốn hơn Lớp A nhưng lại sửa sau cùng

1624 §4 kết luận rất đúng: chi phí tỉ lệ với **số bước**, và toàn bộ token bị đốt nằm ở **phiên điều phối** (Lớp B), không ở worker (Lớp A). RUNBOOK hiện mô tả **5 bước mỗi wave**.

Nhưng artefact sửa Lớp B — `article_run.py` gộp cả wave vào **một lệnh** — nằm ở **Phase 04**, sau ba phase làm Lớp A.

`article_run.py` là một script điều phối 0 token, không phụ thuộc prefix, không phụ thuộc expander, không phụ thuộc worker mode. Nó rẻ và độc lập.

⇒ **Đảo thứ tự:** đưa `article_run.py` và kỷ luật vòng đời phiên (1624 §5.2-A) lên sớm. Nó cắt 5 bước xuống 1 ngay lập tức, cho toàn bộ công việc còn lại của chương trình — kể cả các phase đang phát triển.

---

## 6. Bốn vấn đề định hướng

### H1 — Errata nằm ngoài tài liệu mà nó sửa

1624 §3.2 ghi 21 errata cho 1445, nhưng 1445 **không được sửa**. Người đọc 1445 để implement sẽ:
- đặt `maxDepth: 0` (1445 §7 vẫn ghi vậy — đã xác minh là làm agent không spawn được),
- lo về trần 8K không tồn tại (1445 §12 vẫn ghi),
- nhắm tiêu chí "0 tool" bất khả thi.

Không ai đọc song song hai tài liệu khi đang viết code.

**Đề xuất giải:** hợp nhất thành **một** tài liệu quy phạm trước khi implement. 1133 giữ nguyên trạng thái SUPERSEDED làm hồ sơ thiết kế nền. 1624 giữ lại §6 (bề mặt DSH đã xác minh, có file:line) tách thành `docs/proposals/dsh-surface-verified-2026-09-18.md` để so lại khi nâng cấp DSH — phần này có giá trị độc lập và lâu dài.

### H2 — Vòng lặp audit tự nuôi

Mỗi vòng audit đọc sâu hơn vào DSH, phát hiện thêm sự thật, và vô hiệu hoá tiêu chí của vòng trước. Tài liệu này vừa làm đúng việc đó với 1624 (phát hiện V4 làm hỏng Phase 00/03 của nó).

| | Số |
|---|---:|
| Tổng dung lượng ba plan | 1.421 dòng |
| Errata 1624 ghi cho 1445 | 21 |
| Mâu thuẫn hiến pháp đã nêu | 8 |
| Khiếm khuyết P0 | 3, nay 4 |
| Câu hỏi mở | 8 |
| **Bài đã xử lý** | **0 / 307 hôm nay** |

**Đề xuất giải:** đặt một quy tắc quản trị: **không mở vòng audit mới khi chưa có một vòng thực thi xen giữa.** Tài liệu này là vòng audit cuối trước khi thi hành.

### H3 — Đường tới hạn chứa việc chưa ai yêu cầu

Excel hai cột Intent (`intent_llm`, `intent_code`, `intent_source`) là **Cấp 3**, cần ADR và story riêng (1624 E12), nằm ở Phase 05. Chính 1624 câu hỏi mở #7 hỏi: *"2 cột Intent Excel có thật cần cho người dùng?"*

Một hạng mục Cấp 3 mà chưa xác nhận có người dùng thì không nên nằm trên đường tới hạn.

**Đề xuất giải:** cắt khỏi chương trình. Dữ liệu `intent_source` vẫn được `article_expand.py` tính và lưu vào DB — chỉ hoãn phần **hiển thị ra Excel** cho tới khi có người hỏi. Chi phí hoãn bằng không, lợi ích là bỏ được một ADR khỏi đường tới hạn.

### H4 — Chương trình không có định nghĩa "xong"

Mỗi phase có acceptance, nhưng không tài liệu nào phát biểu **kết quả nghiệp vụ khi toàn chương trình hoàn tất**. Mục tiêu nghiệp vụ đã nêu là bao quát toàn bộ tin thị trường tài chính ở quy mô 500–1.000 bài/ngày với quota ổn định.

**Đề xuất giải:** thêm một định nghĩa xong ở cấp chương trình, đo bằng radar chứ không bằng ý kiến:

> Toàn bộ bài đăng trong ngày được xử lý xong trong ngày (radar báo độ phủ 100%), với chi phí mỗi bài **đo được** và ổn định qua bảy ngày liên tiếp, và không còn hàng đợi `failed` tồn dư sau mỗi chu kỳ.

Mọi phase nên chứng minh được nó đưa hệ thống tới gần định nghĩa đó.

---

## 7. Hai con số sai

### S1 — Backlog sai 4,8 lần

1624 §2.1 và Phase 05 tính chiến dịch backlog trên *"404 packet L1 × 25 bài ≈ **10.100 bài**"*, và §2.3 quy ra chi phí *"backlog 11.000 bài ≈ $6,8 / $3,4"*.

Đếm thật trong `project/data/agent_tasks/l1/`:

| | Số file | Số bài |
|---|---:|---:|
| Packet lô (`l1_batch_*`) | 95 | 1.805 |
| Packet lẻ (một bài mỗi file) | 313 | 313 |
| **Tổng** | **408** | **2.118** |

Giả định "mọi file là lô 25 bài" sai vì 313 trên 408 file là packet một bài. Con số đúng để hoạch định Phase 05 là **2.118**, không phải 10.100.

Lưu ý phân biệt: tồn đọng trong **DB** (theo `l1_backlog.py`: ~6.404 bài chưa L1, ~4.600 bài chờ Gold) là một đại lượng **khác** với tồn đọng **packet trên đĩa**. Hai con số này đang bị dùng lẫn.

### S2 — Quy kết công cụ của vệt 845K

1624 §2.4 ghi con số 845K trong 1445 là *"số của công cụ cũ (Antigravity/`agy`), không phải của DSH"*.

Vệt do anh cung cấp mở đầu bằng ba dòng **`Context injection`**, trong đó có **`@deepseek-ai/dsh-system-prompt`**, và kết thúc bằng khung `Usage … tok` của DSH. Đó là vệt **DSH**.

Nhầm lẫn có thể đến từ trường `agent_provider = 'antigravity'` trong `l1_outputs` — nhưng đó là một chuỗi hằng trong metadata output do skill quy định, không phải bằng chứng về runtime.

Điều chỉnh này quan trọng vì nó quyết định audit 845K còn hiệu lực hay không: **còn hiệu lực, và nó nói về chính DSH.**

---

## 8. Bảng quyết định — những gì phải chốt trước khi viết code

| # | Quyết định | Phương án | Khuyến nghị | Ảnh hưởng nếu chốt sai |
|:-:|---|---|---|---|
| Q1 | Hình thái worker | P-A con PTC (`run_code` + SDK rỗng) · P-B headless ngoài tiến trình | **P-A trước**, đo `turns`; chỉ chuyển P-B nếu `turns > 1` lặp lại | Sai thì ledger phải viết lại (D1) |
| Q2 | Độ sâu xử lý | 100% `full` · `full`/`lite` phân tầng | **`full`/`lite`** | Chênh ~2,3× chi phí/ngày (L4) |
| Q3 | Cách xếp Tier 1 | code-first · recall-biased · một lượt `lite` gán ưu tiên | **recall-biased** trước, vì rẻ và sửa được điểm mù | Người dùng nhận chậm đúng bài quan trọng (L3) |
| Q4 | Cổng ADR 0008 | bỏ hẳn (1445) · giữ có điều kiện (1624) | **Bỏ hẳn** theo chỉ đạo; chỉ giữ chốt kỹ thuật tự động | Dựng lại cổng anh đã bỏ (M3) |
| Q5 | Excel 2 cột Intent | làm ở Phase 05 · hoãn tới khi có người hỏi | **Hoãn**, vẫn lưu `intent_source` vào DB | Một ADR Cấp 3 thừa trên đường tới hạn (H3) |
| Q6 | Hợp nhất tài liệu | giữ ba plan + errata · hợp nhất thành một | **Hợp nhất** | Implement theo tài liệu đã bị errata phủ định (H1) |

---

## 9. Thứ tự phase đề xuất lại

Nguyên tắc: **quyết định kiến trúc trước, thước đo sau, Lớp B trước Lớp A, việc chưa ai cần thì ra khỏi đường tới hạn.**

| Thứ tự | Nội dung | Vì sao đứng đây | Token |
|:-:|---|---|:-:|
| 0 | Chốt Q1–Q6. Vá bốn P0 (`maxDepth` 0→1; sửa comment sai về `allow`+`ptc`; bỏ tiêu chí "0 tool"; sửa `rules/05` §4.4 còn cờ ADR 0008 đã cấm). Hợp nhất ba plan thành một | Mọi thứ sau đều phụ thuộc. Vá P0 là 3 dòng YAML + 2 ADR note | 0 |
| 1 | **Lớp B trước:** `article_run.py` một lệnh cho cả wave + kỷ luật vòng đời phiên + `handoff.py` | Cắt 5 bước xuống 1 cho **mọi** việc còn lại, kể cả việc đang phát triển. Độc lập với worker (D3) | 0 |
| 2 | Ledger + `ctx_probe` + `estimate_wave`, thiết kế theo hình thái đã chốt ở Q1 | Không đo thì mọi số sau lại là phỏng đoán | 0 |
| 3 | Prefix sinh tự động + `article_pack.py` với distillation **tất định, nguyên khối** (L1+L2) + Tier-1 theo Q3 | Bound xác định là tiền đề của `est_ctx_peak` | 0 |
| 4 | Worker một bước + `article_expand.py` + salvage + dual-track reconcile | Lõi cognitive; giờ đã có thước đo và packet có bound | flash |
| 5 | Chạy làn ngày cho tới khi đạt định nghĩa xong ở H4, giữ đường cũ đóng băng (L5) | Chứng minh trên dữ liệu thật trước khi gỡ đường cũ | flash |
| 6 | Archive + deprecate + chiến dịch backlog **2.118 bài** (S1) | Chỉ sau khi làn ngày chạy sạch một chu kỳ đầy đủ | flash |
| 7 | Khai phá catalog (`leaders.yaml`, curator) + amendment hiến pháp | Cần dữ liệu `unlisted` tích luỹ từ bước 5-6 | flash |

So với chương trình cũ: Lớp B từ Phase 04 lên bước 1; ledger phụ thuộc quyết định kiến trúc thay vì đi trước nó; Excel Cấp 3 ra khỏi đường tới hạn; archive lùi sau khi có bằng chứng thay vì cùng phase với cutover.

---

## 10. Những gì tập plan đã làm đúng và nên giữ nguyên

Để cân bằng, đây là phần lõi đã sống sót ba vòng audit độc lập và **không** bị tài liệu này chất vấn:

1. **Chi phí tỉ lệ với số bước, không tỉ lệ với số bài** (1624 §4). Đây là luận điểm đúng và quan trọng nhất của cả tập.
2. **Một lượt cho cả batch, nhiều bài một lượt.**
3. **Bản ghi quyết định tối giản + expander 0 token.** LLM chỉ phát phần ngữ nghĩa, code bù toàn bộ boilerplate.
4. **Citations theo chỉ số đoạn** — với điều kiện bổ sung bất biến nguyên khối ở L1.
5. **Prefix tĩnh đầu, packet động đuôi**, prefix sinh tự động từ catalog kèm hash.
6. **Đo bằng số thật từ JSONL, đo để nhìn không để chặn**, cùng sáu luật kế toán mà 1624 Phase 00 đã xác minh — phần này chính xác và nên giữ nguyên từng chữ.
7. **Hai audit vệt 845K và 154–300K** là tài sản chẩn đoán tốt nhất của repo.
8. **Nguyên lý "Bảo đảm bằng Xây dựng"** (1445 §1.6) — triệt tiêu động cơ tự kiểm chứng thay vì dặn dò trong prompt.

---

## 11. Quyết định đã chốt — Q1 = P-A (con PTC), không dùng SDK/headless

**Chốt ngày 2026-09-18 theo chỉ đạo:** worker là **subagent PTC in-process**. Không dùng `headless`, không dùng `sdk`/`sdk-minimal` ở giai đoạn hiện tại.

### 11.1 Ba vấn đề tự tiêu khi chốt P-A

| # | Vấn đề | Trạng thái sau quyết định |
|:-:|---|---|
| M2 | Plan 1624 tự mâu thuẫn về preset cho con | **Tiêu.** Không còn preset `news-scape-article`. Con kế thừa composition của Conductor. Hạng mục "Preset article + mount junction" phải **gỡ khỏi Phase 01** của 1624 |
| D1 | Ledger xây trước khi chọn hình thái đo | **Tiêu.** Con là một DSH Session có projcache riêng ⇒ luật kế toán mà 1624 Phase 00 đặc tả (duyệt `subagentCatalog`, cộng projcache từng con) **đúng và xây được ngay** |
| Q2 phụ thuộc | "PTC hay headless" của 1624 câu hỏi mở #2 | **Đóng.** Không cần thí nghiệm hai chế độ ở Phase 04. Gỡ hạng mục đó khỏi Phase 04 |

### 11.2 Ba ràng buộc mới mà P-A áp lên thiết kế

**R1 — Conductor bắt buộc ở `mode: ptc`. Đây là ràng buộc chịu lực, không phải tuỳ chọn.**

Dưới `ptc`, kết quả sub-call chỉ vào `tool/ptc-dispatch` trong log bền, không vào context của cha (U4 của 1624, nhất quán với `dsh-tools:2994` `collapses()`). Nếu Conductor chuyển sang `native`, output ~30.000 token của mỗi batch sẽ **rơi thẳng vào context Conductor**, làm sống lại đúng Lớp B mà cả tập plan đang chữa.

⇒ Ghi vào plan hợp nhất như một bất biến: *đổi Conductor sang `native` là phá vỡ kiến trúc.*

**R2 — Không thể gỡ AGENTS.md khỏi prefix của con.**

1624 E21 đề xuất `agent-instructions.config.maxBytes: 0` để gỡ AGENTS.md (~4.069 token) khỏi worker. Với P-A, khoá đó nằm ở **cấp phiên**, mà con dùng chung composition với Conductor — không thể đặt riêng cho con. Đặt ở cấp phiên thì Conductor cũng mất AGENTS.md, điều không mong muốn vì đó là authority gate.

Đánh giá tác động: AGENTS.md nằm ở **đầu prefix, tĩnh, byte-identical** ⇒ cache hit từ lần gọi thứ hai. Chi phí tiền gần như bằng không. Chi phí quota là 4.069 token nhân số batch.

⇒ **Chấp nhận, không chống.** Gỡ hạng mục `maxBytes: 0` khỏi Phase 01 của 1624.

**R3 — Con nhận ~640 token hướng dẫn về một SDK rỗng, kèm một câu lệnh mâu thuẫn.**

Đây là phát hiện mới, đo trực tiếp. Con PTC với `allow: []` nhận đủ hai section:

| Section | Nội dung | Kích thước đo được |
|---|---|---:|
| `tools:ptc-only` | *"`run_code` is the only tool you can call directly — a tool call naming any other tool fails. **Reach every tool the SDK declares below from inside the program.**"* | ~40 token |
| `tools:sdk` | Toàn bộ hướng dẫn viết chương trình `run_code`, kết thúc bằng `interface ToolArgsMap {}` và `interface ToolOutputMap {}` — **rỗng** | **1.802 ký tự ≈ 600 token** |

Vì `ToolName = keyof {}` là `never`, đối tượng `tools` không có binding nào. Nhưng prompt vẫn **bảo con hãy với tới các tool "SDK khai bên dưới"**, trong khi bên dưới không khai gì.

Hai hệ quả:
- **Chi phí:** ~640 token nằm trong prefix tĩnh ⇒ cache hit, tiền không đáng kể; quota cộng thêm ~640 token mỗi batch.
- **Rủi ro hành vi:** prompt đang **mời** model viết chương trình. Nếu nó thử `tools.x(...)`, lời gọi thất bại và tốn thêm ít nhất một bước — đúng thứ kiến trúc này tồn tại để triệt tiêu.

⇒ **Bắt buộc trong `ARTICLE_SYSTEM_CORE`:** persona phải vô hiệu hoá câu lệnh trên một cách tường minh, đại ý *"Bạn không có tool nào. Không gọi `run_code`. Không viết chương trình. Trả lời bằng một mảng JSON duy nhất trong thông điệp cuối."* Persona đứng ở `order 0`, trước cả hai section trên, nên cần nhắc lại điều này ở cuối packet để nó nằm gần điểm sinh output.

⇒ **Chỉ số canh gác:** `turns` của con. Bằng 1 là đạt. Lớn hơn 1 nghĩa là con đã sa vào `run_code` và persona cần sửa. Đây là tiêu chí thay thế cho "tập tool = ∅" đã bị bác ở M1.

### 11.3 Tiêu chí nghiệm thu sau khi chốt P-A

Thay ba tiêu chí cũ bằng ba tiêu chí kiểm được:

| Cũ (bất khả thi hoặc sai) | Mới |
|---|---|
| "tập tool hiệu lực của worker = ∅" | **`sdkSchemas` của con rỗng** (in ra, lưu trace) — kiểm được, và đúng là thứ ta điều khiển được |
| — | **`turns` của mỗi con = 1** — chỉ số canh gác cho R3 |
| "`cacheReadTokens` ≥ 95% kích thước prefix" | **prefix byte-identical giữa hai batch liên tiếp** (kiểm được, thuộc quyền ta) + `cacheReadTokens` là **chỉ số theo dõi** có ngưỡng cảnh báo, không phải cổng đóng phase |

### 11.4 Hạng mục phải gỡ khỏi plan 1624 vì đã lỗi thời

| Nơi | Hạng mục | Lý do gỡ |
|---|---|---|
| Phase 00 acceptance | "tập tool hiệu lực = ∅" | M1 — bất khả thi với con PTC |
| Phase 01 | Preset `news-scape-article` + mount junction | R1/M2 — con không nhận preset riêng |
| Phase 01 | `agent-instructions.config.maxBytes: 0` | R2 — không đặt được cho riêng con |
| Phase 03 | `mode: native` cho `agent_article` | V4 — không có khoá `mode` trong row subagent |
| Phase 03 acceptance | "tập tool hiệu lực = ∅ (in ra)" | M1 |
| Phase 04 | Thí nghiệm PTC vs headless | Q1 đã chốt |
| §5.3 | Bảng bốn chế độ thực thi | Giữ làm tham khảo, ghi rõ **đã chọn PTC**; ba dòng còn lại không nằm trong phạm vi |
| §12 câu hỏi mở #2 | — | Đã trả lời |

### 11.5 Năm quyết định còn treo

| # | Quyết định | Khuyến nghị | Ảnh hưởng |
|:-:|---|---|---|
| Q2 | Độ sâu: 100% `full` hay phân tầng `full`/`lite` | **`full`/`lite`** | Chênh ~2,3 lần token/ngày (L4). **Cần chốt trước khi viết `article_pack.py`** |
| Q3 | Cách xếp Tier 1 | **recall-biased** | Bài watchlist bị xếp nhầm xuống batch sau (L3) |
| Q4 | Cổng ADR 0008 | **Bỏ hẳn** theo chỉ đạo đã có; chỉ giữ chốt kỹ thuật tự động | 1624 §0.3 đang dựng lại cổng (M3) |
| Q5 | Excel 2 cột Intent | **Hoãn**, vẫn lưu `intent_source` vào DB | Bỏ một ADR Cấp 3 khỏi đường tới hạn (H3) |
| Q6 | Hợp nhất ba plan thành một | **Hợp nhất** | Tránh implement theo tài liệu đã bị errata phủ định (H1) |

Trong năm cái trên, **Q2 chặn sớm nhất** vì nó quyết định cấu trúc packet và do đó quyết định `article_pack.py`, `est_ctx_peak` và cột `depth_mix` của ledger.
