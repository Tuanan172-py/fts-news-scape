# Plan — Kinh tế Token DSH & Phương án Làm việc (Token-Economy Workmethod)

|  |  |
| --- | --- |
| Ngày | 2026-09-18 (rev 2 — sau khi xác minh mã nguồn DSH 0.1.5-rc.1) |
| Trạng thái | **SUPERSEDED** — thay thế bởi [plan hợp nhất 20260918-1651-article-lane-unified](../20260918-1651-article-lane-unified/plan.md). Giữ làm hồ sơ; **§6 (bề mặt DSH kèm file:line) vẫn còn hiệu lực**, dùng khi nâng cấp DSH. |
| Phân loại | **Cấp 2 — NORMAL** cho doctrine + operator script + preset. **Cấp 3** cho: (a) amendment ADR 0008 gỡ cổng, (b) Data Contract deliverable Excel 2 cột, (c) `.agents/rules/05` §4 đang làm trái ADR 0008, (d) sửa `maxDepth` trong ADR 0009 §2.2 |
| Nền tảng | `docs/decisions/0009` · `docs/decisions/0008` · `plans/20260917-1538-dsh-harness-integration/plan.md` · audit 845K/154–300K trong `plans/20260918-1445-article-lane-scale-token/plan.md` §1 · **xác minh mã nguồn DSH `0.1.5-rc.1` + `api-docs.deepseek.com` ngày 2026-09-18** |
| Quan hệ với 2 plan cũ | `20260918-1133-l1-llm-lean-token` vẫn **SUPERSEDED**. `20260918-1445-article-lane-scale-token` giữ vai trò **Master Plan kỹ thuật**, nhưng phải hấp thu §3 (errata E1–E21) + §5 (doctrine) + §6 (bề mặt DSH) trước khi triển khai. Plan này là **tầng quy trình** nằm trên nó. |
| Câu chốt định vị | Chi phí token tỉ lệ với **số bước (step)**, không tỉ lệ với số bài. Mỗi bước gửi lại **toàn bộ** transcript đã kết nạp, không có cắt tỉa. |

---

## 0. Cổng phê duyệt

1. Anh duyệt plan này.
2. **Phase 00 (đo lường + sửa khiếm khuyết đang sống)** là read-only trên DB vận hành: chạy được ngay sau khi duyệt, không tiêu token model.
3. **Phase 01 trở đi** theo cổng ADR 0008 hiện hành **cho tới khi** Phase 00 chứng minh sai số dự toán ≤ 20%; chỉ sau đó mới trình amendment gỡ cổng (§3, E11).
4. Ba khiếm khuyết P0 ở §3.4 phải được vá **trước** mọi wave tiêu token, vì chúng làm hỏng chính cơ chế cưỡng chế mà hai plan dựa vào.

Ngoài phạm vi: chất lượng ngữ nghĩa phân tích tài chính, schema `monocle.db` (trừ bảng `token_ledger` mới).

---

## 1. Kết luận điều tra

1. **Hai plan cũ đúng về chẩn đoán vi mô, sai về tầng chi phí.** Toàn bộ 845K/154–300K token bị đốt nằm ở **phiên tương tác**, không nằm ở wave worker. Hai plan tối ưu rất kỹ worker nhưng không có một dòng nào ràng buộc **phương án làm việc của phiên điều phối**. Bằng chứng: `docs/SESSION-LATEST.md:15` — phiên 17/09 chạy bằng `subagent` generic vì **chưa ở preset Conductor**.
2. **Nguyên nhân gốc của vệt 845K là lỗi vận hành, không phải lỗi thiết kế `toolFilter`.** `.dsh/settings.yaml` khai preset mặc định **không phải** `news-scape-conductor`, nên con được spawn không có `toolFilter` nào cả. Biện pháp đúng là **preflight guard từ chối chạy khi phiên sai preset**, không phải thêm ràng buộc trong prompt.
3. **Ba khiếm khuyết P0 đang sống, làm vô hiệu chính cơ chế cưỡng chế của H2** (§3.4): `maxDepth: 0` khiến `agent_l1`/`agent_gold` **không thể spawn**; `mode: ptc` + `toolFilter` làm ranh giới 2-I/O **đảo ngược ý định**; và **không có cơ chế nào chặn transcript phình** trong thực tế (§3.2 E16). Chưa plan nào phát hiện ba điểm này.
4. **DSH đã ship sẵn gần hết cơ chế mà hai plan định tự xây.** Có profile `headless`, `sdk`, `sdk-minimal`; có `dsh-token-meter`, `dsh-spill-policy`, `dsh-repeat-tool-reminder`, `dsh-output-retention`, `dsh-hook-protocol`, `dsh-invariants`. Đề xuất chiến lược: **không xây bundle H3**, mà cấu hình/gắn plugin có sẵn và chỉ viết script miền-nghiệp-vụ.

---

## 2. Bối cảnh số thật

### 2.1 Số của hệ thống (radar, 0 token)

```
Bao phủ L1 bài đăng hôm nay : 0/303 (0.0%) · còn 100 needs_agent chờ · 45 chưa định tuyến
Tồn đọng kẹt                : work_items 189 failed · l1_tasks 85 failed
Packet trên đĩa             : L1 404 files/batches · Gold 2 files/batches
```

404 packet L1 × 25 bài ≈ **10.100 bài** chờ một consumer chưa tồn tại ("producer không có consumer", `docs/OPEN-ITEMS.md` A0-5). **Không plan nào xử lý số này.**

### 2.2 Số của nhà cung cấp (đã kiểm chứng lại 2026-09-18)

`deepseek-flash` = **DeepSeek-V4.1-Flash** ([pricing](https://api-docs.deepseek.com/quick_start/pricing)):

| Khoản (USD / 1M token) | Off-peak | Peak |
| --- | ---: | ---: |
| Input — cache hit | $0,003 | $0,006 |
| Input — cache miss | $0,15 | $0,30 |
| Output | $0,60 | $1,20 |

- **Peak: 01:00–04:00 và 06:00–10:00 UTC, T2–T6** = 08:00–11:00 và 13:00–17:00 giờ VN. Off-peak = **50%**.
- Cache: tự động, **prefix từ token 0**, đơn vị **64 token**, **không phí ghi cache**, không đảm bảo hit 100%, entry xoá sau vài giờ–vài ngày ([caching](https://api-docs.deepseek.com/news/news0802)).
- Context 1M · max output 384K · **thinking BẬT mặc định** ([V4.1-Flash](https://api-docs.deepseek.com/news/news260910)).
- **Không có giới hạn TPM/RPM**; concurrency flash 2.500. Con số "≤100.000 tokens/phút" trong `.agents/rules/05` §4.4 là **bịa**.
- Từ 04:00 UTC 14/09/2026, `deepseek-v4-pro` **route sang V4.1-Flash với giá Flash** ⇒ lý do chi phí của D6 tạm hết hiệu lực.

### 2.3 Hệ quả chi phí

Với Article Lane `full` ~1.220 token/bài: 303 bài/ngày ≈ **$0,19 peak / $0,09 off-peak**; 1.000 bài/ngày ≈ **$0,62 / $0,31**; backlog 11.000 bài ≈ **$6,8 / $3,4**.

**Tiền không phải ràng buộc.** Ràng buộc thật là **quota token của tài khoản** (nếu có) và **quán tính của transcript**. Ledger phải ghi **đồng thời** `quota_tokens` (hit + miss + out + reasoning) và `billed_usd`. Đây là **câu hỏi mở #1** (§12).

### 2.4 Số thật của DSH trên chính máy này (đọc từ `session_projcache` + JSONL, 2026-09-18)

| Phiên | turns/steps | uncached in | output | cache read | hit | pressure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Phiên lớn nhất `session-1317a0f2` | 112 turns / 292 steps | 833.467 | 227.072 | 69.321.984 | 98,81% | 409.079 / 1.000.000 |
| `session-1e91b67e` | 14 turns | 103.026 | 91.364 | 9.727.872 | 98,95% | — |
| `session-d7477826` (17/09) | 3 turns | 72.855 | 52.479 | 2.081.536 | 96,62% | — |
| Phiên research này | 1 turn / 43 steps | 158.277 | 57.462 | 4.286.720 | 96,44% | 198.420 / 1.000.000 |

Ba kết luận rút ra từ số thật:

1. **Đối soát tuyệt đối đã chứng minh**: tại `tokenUsage.seq=283`, tổng lưu trong projcache **bằng đúng** từng token với tổng các event `assistant/message` (`seq ≤ 283`) trong JSONL của cùng phiên (143.662 / 53.029 / 3.549.056 / 0). ⇒ Ledger dựng trên JSONL là **nguồn chuẩn**, projcache dùng để đối soát chéo.
   Lưu ý đối chiếu với con số anh đưa: `session-1317a0f2` (112 turns / 292 steps) có **833.467 uncached input** — cùng bậc với "845K" trong audit, nhưng **chưa xác minh là cùng một phiên**. Con số ghi trong `plans/20260918-1445-...` §1.1 vẫn là **số của công cụ cũ** (Antigravity/`agy`), không phải của DSH; từ nay mọi báo cáo chi phí phải nêu rõ **thước nào** (uncached · quota-equivalent · USD).
2. **Cache hit 96–99% là bình thường** ⇒ thiết kế giữ vệ sinh prefix (§5.B) là đúng hướng và đòn bẩy thật nằm ở **số bước**, không ở prefix.
3. **Chi phí bị chi phối bởi giá cache-hit** ($0,003–0,006/1M): 69M cache read chỉ tốn ~$0,2–0,4, trong khi 833K uncached tốn ~$0,25. Nghĩa là **tối ưu số bước và tối ưu cache có cùng trọng số** — không được bỏ cái nào.

---

## 3. Đánh giá hai plan & errata bắt buộc

### 3.1 Giữ nguyên — chất lượng cao

| # | Nội dung giữ |
| --- | --- |
| K1 | Audit vệt 845K và 154–300K: đo file thật, dựng lại bằng số, hệ số lãng phí 12,1×, hiệu suất 0,7%. Tài sản chẩn đoán tốt nhất của repo. |
| K2 | **"Bảo đảm bằng Xây dựng"**: triệt tiêu công cụ vật lý + citations theo chỉ số ⇒ LLM hết động cơ tự kiểm chứng. |
| K3 | **Minimal Decision Record + expander 0 token**: LLM chỉ phát quyết định ngữ nghĩa, code bù boilerplate. Đòn bẩy lớn nhất. |
| K4 | "Đo, không gate" + giữ ADR 0008 §2.4 "thất bại phải ồn ào". |
| K5 | Priority-Queue 2 tầng + Dual-Track Intent để giải trình. |
| K6 | G1 (packet `indent=2`) — **đã kiểm chứng lại**: `project/src/agent/batch_handoff.py:146` gọi `safe_json_dump(..., indent=2)`. Chẩn đoán đúng 100%. |

### 3.2 Errata bắt buộc sửa trước khi triển khai

| # | Phát hiện | Bằng chứng | Sửa |
| :-: | --- | --- | --- |
| **E1** | **Sai tầng chi phí.** Hai plan tối ưu worker, không ràng buộc phương án làm việc của **phiên điều phối**. | plan 1445 §1.1; `SESSION-LATEST.md:15` | Bổ sung §5 thành điều khoản bắt buộc; Phase 04 thực thi. |
| **E2** | **Sai nguyên nhân gốc.** Không phải "`toolFilter` không cưỡng chế được" mà là **phiên sai preset nên không có `toolFilter`**. | `.dsh/settings.yaml` (preset mặc định không phải conductor); `SESSION-LATEST.md:15` | Preflight guard ở §5.F, Phase 01. |
| **E3** | **"Preset worker riêng" cho con trái ADR 0009 §2.2/D1**: con kế thừa composition của cha qua `composeFrom`, **không có khóa nào để tắt**. | `dsh-subagent/lib/index.js:543`; `dsh-tool-subagent/lib/index.js:252-270` (schema không có khóa `inherit`/`preset`) | Chọn: chấp nhận + **đo** overhead của con, hoặc đặt composition tinh gọn ở **cấp phiên** (preset riêng hoặc profile/overlay). |
| **E5** | **Acceptance vô nghĩa**: "hit ratio ≥ 80% từ batch 2" không đạt được khi miss 85K/hit 7K. | plan 1445 §10 Phase 03 | Định nghĩa lại: `cacheReadTokens` ≥ 95% **kích thước prefix**, ghi `hit_ratio_prefix` không ghi `hit_ratio_total`. |
| **E6** | **`IND` không có luật resolve.** GICS chỉ 1 alias = canonical name ⇒ `"thép"`, `"đường sắt"` không resolve chắc chắn; §4.2 khẳng định resolver mà không có thuật toán/ngưỡng. | plan 1445 §4.1 tự mâu thuẫn | Bắt LLM phát **canonical name** cho `IND` (digest 90 ID đã trong prefix, 0 token thêm) ⇒ resolve exact-string; đo `resolve_rate`, **sàn 85%**, dưới sàn ⇒ `unlisted`. |
| **E7** | **Citations-by-index chưa có bất biến kiểm được.** | plan 1445 §3.2; `rules/05` §2.3 | Expander **bắt buộc** khẳng định `p[k] in cleaned_text`; sai ⇒ requeue item. |
| **E8** | **Bỏ trần 2.200 ký tự mà không đặt trần thay thế** ⇒ packet có thể phình, phá mục tiêu 600–900 token/bài. | plan 1445 §3.1 vs §1.4 | Trần mềm **≤1.000 token/bài**; `article_pack.py` in **histogram phân bố**. |
| **E9** | **Không có migration cho tồn đọng**: 404 packet L1 + 2 packet Gold format cũ; tên batch trùng đã gây ingest lại dữ liệu cũ. | radar 2026-09-18; `OPEN-ITEMS.md` A0-3 | Phase 02 archive toàn bộ `data/agent_tasks/l1/` + `data/agent_tasks/*.task.json`, định tuyến lại qua `article_pack.py`. |
| **E10** | **Thiếu danh sách nghỉ hưu.** Repo đã từng có 2 matcher trôi khác nhau (D11) và 2 đường DoD L1 (A0-5). | `OPEN-ITEMS.md` D11, A0-5 | Phase 03 deprecate tường minh 6 hạng mục. |
| **E11** | **Chưa xử lý xung đột hiến pháp** khi hợp nhất L1+Gold: `AGENTS.md` §6A/§6B, `rules/01`, `rules/05` §2.7, ADR 0003/0005. | `AGENTS.md` §6; `rules/01:29-31`; `rules/05:61-67` | Phase 06 amendment. Plan 1445 §15 **thiếu**. |
| **E12** | **Đổi 2 cột Excel là đổi Data Contract** nhưng plan 1445 khai Cấp 2. | `project/src/export/user_output.py:37-44` | Nâng **Cấp 3**, ADR + story riêng. |
| **E13** | **Thiếu biến đắt nhất trong ma trận thí nghiệm: `reasoningEffort`.** Thinking BẬT mặc định, tính giá **output**. | plan 1445 §11 không có biến này | Thêm biến, đo `reasoningTokens` **và** DoD recall. |
| **E14** | **`maxDepth: 0` cấm delegation HOÀN TOÀN**, không phải "chặn đệ quy". Con đầu tiên đã ở depth 1 ⇒ `1 > 0` ⇒ ném `SubagentDepthError`. **Preset đang chạy khai `maxDepth: 0` cho cả `agent_l1` và `agent_gold` ⇒ hai tool này chưa bao giờ spawn được.** Đây là lý do thứ hai (ngoài sai preset) khiến phiên 17/09 phải dùng `subagent` generic (mặc định `maxDepth: 3`). | `dsh-subagent/lib/types/child-agent.js:32-41` (`childDepth = delegationDepthOf(parent) + 1; if (maxDepth !== undefined && childDepth > maxDepth) throw new SubagentDepthError`); `dsh-tool-subagent/README.md:53` *"`0` forbids delegation"*; `agent.cordis.yml:188,206` | **Sửa thành `maxDepth: 1`** (cho phép đúng 1 tầng, chặn cháu). Sửa ADR 0009 §2.2, plan 1445 §7, D1 table. |
| **E15** | **`toolFilter` + `mode: ptc` đảo ngược ý định 2-I/O.** Under non-`native` mode, `run_code` được **thêm lại SAU** khi áp restriction; nên `allow: [read, write]` **không** gỡ hết tool khác, và dưới `ptc` thì gọi trực tiếp `read`/`write` bị từ chối `UNKNOWN_TOOL` (chỉ với tới được từ trong `run_code`). Muốn con **0 tool** phải là `mode: native` + `allow: []`. | `dsh-tools/lib/index.js:2874` (`if (this.modeFor(scope) !== "native") visible.set(RUN_CODE_NAME, …)`), `:2994` (PTC collapse), `:2839-2844` (restriction chỉ lọc tầng kế thừa) | Phase 00/03: worker chạy `mode: native` + `toolFilter.allow: []`. Ghi rõ trong preset. |
| **E16** | **Không có gì chặn transcript phình trong thực tế.** `dsh-compaction-tool-result-pruner` **không đăng ký listener nào** — chỉ được gọi từ trong một lượt compaction; mà compaction chỉ tự chạy ở **80%** cửa sổ context (1M ⇒ 800K). Kết quả văn bản thuần **không** được lưu theo tham chiếu, nằm nguyên văn trong log và bị gửi lại **mỗi bước**. | `dsh-compaction-tool-result-pruner/lib/index.js:11,137`; `dsh-compaction-basic/lib/index.js:15,111,888,902`; `dsh-session/lib/index.js:1204,1269` | Đây là cơ chế chính xác đứng sau vệt 845K. Không dựa vào pruner; **cắt bằng thiết kế** (§5.A, §5.C) và đặt ngưỡng đóng phiên thấp hơn nhiều. |
| **E17** | **`maxTokens` mặc định là 256.000, không phải 8K.** Plan 1445 §12 nêu rủi ro "quên `maxTokens` ⇒ mặc định 8K cắt cụt batch 100" — **sai**; adapter DeepSeek đặt `DEFAULT_MAX_TOKENS = 256e3`, và con kế thừa `maxTokens` của cha. | `dsh-llm-deepseek/lib/index.js:1394,1998`; `dsh-subagent/lib/types/child-agent.js:79-92` | Sửa rủi ro và giữ khai `maxTokens` như **chặn trên chủ động** (chống trần 384K), không phải chống cắt cụt 8K. |
| **E18** | **`maxParallelSubCalls: 3` của ADR 0009 §2.5 chưa được cấu hình ở đâu cả**; mặc định là **10** (và không phải khóa của row subagent mà của `dsh-tools`). | `dsh-tools/lib/index.js:2575`; preset/`dsh-base`/web patch đều không đặt | Cấu hình thật ở row `@deepseek-ai/dsh-tools` hoặc bỏ hẳn van wave (rate limit đã bỏ — §2.2). |
| **E19** | **Phiên bản hỗn hợp**: `@deepseek-ai/dsh` (CLI) là **0.1.5-rc.1**, nhưng một số plugin là **0.1.5-rc.2** (vd `dsh-token-meter`); và hai đường dẫn cài là **junction tới cùng một cây nguồn**. | `npx/package.json` pin `^0.1.5-rc.1`; `dsh-token-meter/package.json` rc.2; SHA256 khớp trên 4 file mẫu | Sửa tài liệu ghi "0.1.5-rc.2" cho CLI; ghi phiên bản **theo từng package** khi cần. |
| **E20** | **Khóa cấu hình sai bị bỏ qua im lặng.** Schemastery merge extras through, và row subagent không tự kiểm khóa lạ ⇒ gõ nhầm `toolFIlter` ⇒ con **giữ nguyên toàn bộ tool** mà không có cảnh báo. | `schemastery/lib/index.mjs:486`; `dsh-tool-subagent/lib/index.js:252-270` (không có kiểm khóa) | Phase 01/03 acceptance: **khẳng định tập tool hiệu lực** (`system-prompt/assemble` → `tools[]`, hoặc `ctx.tools.view(scope).visible`), không tin YAML. |
| **E21** | **Thông điệp kết thúc của con KHÔNG có trần**, và AGENTS.md được nạp lại cho **mọi** con. | `dsh-subagent/lib/index.js:661,2475` (chỉ có dòng tóm tắt 120 ký tự và diagnostics 4096 byte bị chặn); `dsh-agent-instructions/lib/index.js:1270,668` | Con phải ép phát JSON gọn. Cấp phiên worker: đặt `agent-instructions.config.maxBytes: 0` để **gỡ AGENTS.md** (cơ chế hợp lệ đã xác minh). |

### 3.3 Mâu thuẫn hiến pháp & khiếm khuyết đang sống (phát hiện mới)

| # | Vấn đề | Bằng chứng | Đề xuất |
| :-: | --- | --- | --- |
| **C1** | `.agents/rules/05` §4.4 **vẫn chỉ định** `agy -p "<prompt>" --dangerously-skip-permissions --effort low`. ADR 0008 §2.2 (**accepted**) đã bỏ cờ này. Agent nạp `rules/05` sẽ **vô hiệu hoá cổng người**. | `rules/05:108-110` vs `ADR 0008:48-51` | Phase 00 sửa (fix 1 dòng, lỗ hổng quản trị). |
| **C2** | `rules/05` §4 đặt định mức 1.770 token/bài, "≤100.000 token/phút", trần ngày 350.000. Audit thật: 30.800–60.000 token/bài Gold; api-docs: **không có TPM/RPM**. | `rules/05:78-111` vs plan 1445 §1.5 | Thay bằng số đo từ ledger; không giữ hằng số vô nguồn. |
| **C3** | `preset.yml` mô tả preset là **"read-only … không spawn agent"** nhưng `agent.cordis.yml` định nghĩa `agent_l1` + `agent_gold` + PTC. | `preset.yml:1-5` vs `agent.cordis.yml:174-238` | Cập nhật `preset.yml`. |
| **C4** | D6 cấm `deepseek-v4-pro` vì chi phí, nhưng pro hiện **route sang Flash với giá Flash**. | api-docs news260910 | Ghi chú ADR 0009 §2.3 + guard kiểm lại khi V4.1-Pro ra. |
| **C5** | **`maxDepth: 0`** ở ADR 0009 §2.2 + 3 tài liệu ⇒ H2 chưa từng chạy được. **P0.** | xem E14 | Đổi thành `1`; ghi ADR amendment + trace (rule 07). |
| **C6** | **`maxParallelSubCalls: 3`** ở ADR 0009 §2.5 không tồn tại trong cấu hình. **P0.** | xem E18 | Cấu hình thật hoặc gỡ khỏi ADR. |
| **C7** | Comment trong `agent.cordis.yml:170-173` khẳng định `allow: [read, write]` khiến *"mọi tool khác biến mất khỏi prompt và bị từ chối thực thi"* — **sai dưới `mode: ptc`**. **P0.** | xem E15 | Sửa comment + đổi mode cho worker. |
| **C8** | Rủi ro "mặc định 8K cắt cụt" trong plan 1445 §12 là **sai**; đồng thời preset **chưa** có `reasoningEffort` ⇒ con chạy ở mức `high` của `settings.yaml`. | E17; `.dsh/settings.yaml` `reasoningEffort: high` | Sửa §12; đặt effort cho worker và **cưỡng chế** bằng hook `agent/request` (§5.F). |

### 3.4 Ba khiếm khuyết P0 phải vá trước mọi wave tiêu token

| # | Triệu chứng | Hậu quả nếu không vá |
| :-: | --- | --- |
| P0-1 (E14) | `agent_l1`/`agent_gold` ném `SubagentDepthError` ở lần gọi đầu | Wave rơi về `subagent` generic ⇒ mất toàn bộ ranh giới 2-I/O ⇒ tái diễn vệt 845K |
| P0-2 (E15) | `mode: ptc` + `allow` không cho con 0-tool; `read`/`write` không gọi trực tiếp được | "Zero-tool worker" — giả định chịu lực của plan 1445 — **không đạt**; con vẫn có `run_code` để tự mở vòng khám phá |
| P0-3 (E16) | Không có pruner/cắt tỉa ngoài compaction ở 80% | Transcript phình không chặn; đây chính là cơ chế của 845K |

---

## 4. Chẩn đoán gốc — công thức chi phí (đã hiệu chỉnh theo mã nguồn)

Đơn vị chi phí là **bước (step)**, không phải lượt gọi tool. Trong một bước, model phát một assistant message; mọi tool call trong đó chạy song song (trần 10) và **chỉ sinh thêm MỘT request** kế tiếp mang toàn bộ kết quả.

```
billed_input ≈ Σ_{s=1..S} ( P + Σ_{j<s} (U_j + O_j) )   ≈  S·P + O(S²)
S = số bước;  P = prefix (system prompt + tool schema + AGENTS.md + skill catalog)
```

Ba tính chất quyết định thiết kế:

1. **Bậc hai theo số bước.** Vệt 845K: nội dung *duy nhất* 82K nhưng bị tính ~990K ⇒ **khuếch đại 12,1× đến từ `S`**. Cắt nội dung 50% giảm ~4% hoá đơn; cắt `S` từ 19 xuống 1 giảm ~93%.
2. **Gộp tool call trong một bước là rẻ** (10 call = 1 request, không phải 10). Gộp **bước** mới là đòn bẩy.
3. **Ghi đè kết quả tool là thứ duy nhất cắt được vòng lặp** — vì `read` được **miễn spill** (`dsh-spill-policy`: *"`read` is skipped … to avoid a `read → spill → read again` loop"*) và pruner không chạy ngoài compaction. Nội dung đã vào context thì **ở lại đến hết phiên**.

**Hai lớp đốt token độc lập:**

| Lớp | Ở đâu | Chịu bởi | Thuốc |
| --- | --- | --- | --- |
| **A — Worker** | Mỗi lần gọi LLM xử lý bài | Subagent con | 1 bước/batch · 0 tool · packet ở **đuôi** · MDR + expander · `maxTokens` chặn trên · effort đo được |
| **B — Phiên điều phối** | Phiên DSH của người vận hành | Conductor + người | 1 bước/wave · operator-first · handoff 0 token · đóng phiên sau wave · ngưỡng context thấp |

Hai plan cũ chỉ chữa Lớp A. **Lớp B chưa ai chữa**, và ở nhịp 300 bài/ngày nó có thể tốn hơn Lớp A: RUNBOOK §3 mô tả **5 bước cho mỗi wave** (radar → đọc DAG → cổng → chạy → báo cáo); mỗi bước gửi lại toàn bộ transcript đang phình, và **không có gì cắt nó** (E16).

---

## 5. Phương án làm việc — 4 Lane & 6 nhóm quy tắc

### 5.1 Bốn làn công việc

| Lane | Ai làm | Chi phí kỳ vọng | Dùng khi |
| --- | --- | --- | --- |
| **L0 — Cấu hình & Script** | preset YAML, hook, `guard()`, operator Python | **0 token** | Việc lặp lại ≥2 lần, hoặc ràng buộc nào phải luôn đúng |
| **L1 — Operator** | `run_code` gọi `pwsh`/`read`/`write` bên trong chương trình; chỉ `return` số | ~50–200 token/bước | Mọi thao tác cơ học: pack, expand, ingest, ledger, radar |
| **L2 — Cognitive worker** | một lần gọi LLM cho một batch | ~150 (lite) / ~1.220 (full) token/bài | Quyết định ngữ nghĩa: thực thể, tóm tắt, hàm ý, sentiment, chọn đoạn chứng cứ |
| **L3 — Human** | anh | — | Duyệt plan/ADR, chọn ưu tiên, xử lý bất thường |

**Quy tắc vàng:** một việc chỉ leo lên lane cao hơn khi lane thấp hơn **không thể** làm được. Đảo chiều "No Script Emulation": **cấm dùng LLM để giả lập script**.

### 5.2 Sáu nhóm quy tắc

**A. Vòng đời phiên (chữa Lớp B)**

- **A1.** Một phiên = một mục tiêu = một wave. Xong wave ⇒ ghi handoff ⇒ **đóng phiên**. Mở phiên mới rẻ hơn nhiều so với mang transcript phình, vì prefix vẫn hit cache (cache ở phía provider, không gắn với session).
- **A2.** Một wave = **một bước**. `article_run.py --wave N` gộp radar + pack + spawn + expand + ingest + ledger vào **một** lệnh; Conductor gọi nó trong **một** `run_code`. Không tách "kiểm tra trạng thái" thành bước riêng.
- **A3.** Đầu phiên nạp **tối đa 3 tệp**: `AGENTS.md`, `docs/SESSION-LATEST.md`, skill chuyên trách (`rules/08`).
- **A4.** Conductor chỉ đọc thứ **script in ra**. Hợp đồng phải có lệnh in (`harness_cli.py query contract`), không đọc nguồn để suy ra (bài học lỗi #4 của plan 1445: 4 bước đọc `l1_router.py`).
- **A5.** Ngưỡng áp suất context: **xanh <25% · vàng 25–40% → đóng phiên sau wave · đỏ >40% → dừng ngay**. Vì DSH chỉ tự compaction ở **80%** (E16), ngưỡng của harness phải **thấp hơn nhiều** và do người/script cưỡng chế, không trông vào DSH.

**B. Vệ sinh Prefix (chữa `P`)**

- **B1.** Trong một phiên, **không** đổi tool set, preset, model route hay effort. Prefix được DSH giữ ổn định có chủ đích: thứ tự section cố định, tool list sắp lexicographic, skill catalog và AGENTS.md **không phát lại khi không đổi**, cập nhật system prompt được **nối vào đuôi** thay vì viết lại node 0. Đổi tool set hoặc compaction là **phá cache**.
- **B2.** Nội dung tĩnh ở **đầu**, nội dung biến động (packet) ở **cuối**. DSH cũng đặt runtime context và time context ở **đuôi** vì lý do này.
- **B3.** `compaction-basic` đặt `auto: false` cho preset worker (compaction viết lại vùng surface ⇒ mất cache từ điểm viết lại).
- **B4.** **Mọi script in < 2 KB.** Trần cứng để không bị spill là **50.000 byte** (`dsh-spill-policy`, miễn trừ `read`); nội dung vượt ngưỡng bị thay bằng preview head/tail + đường dẫn. Ghi output nặng ra đĩa, in một dòng trỏ đường dẫn.

**C. Kỷ luật ngữ cảnh (chữa `O(S²)`)**

- **C1.** Cognitive worker **0 tool bằng cấu hình**: `mode: native` + `toolFilter.allow: []` (E15). Không tin YAML — **khẳng định tập tool hiệu lực** ở Phase 01/03 (E20).
- **C2.** **Cấm read-back**: không đọc lại tệp vừa ghi. Ghi/xoá tệp đã tự ghi nhận "observed version" nên `edit` sau `write` không cần `read`; DoD chấm ở ngoài.
- **C3.** **Cấm đọc từ điển lớn**: `entities.json` = **324.493 token** (plan 1445 §4.3). Bảng tra phải sinh tự động thành digest trong prefix. `read` bị chặn ở **2.000 dòng/lần** và có trần byte/dòng ⇒ đọc tệp lớn vừa tốn vừa trả về dữ liệu **cụt**, tạo đúng tâm lý "nghi ngờ dữ liệu" đã sinh ra 15 lệnh grep trong vệt Gold.
- **C4.** Không spawn con cho việc cơ học. Mỗi con trả giá một prefix đầy đủ, **AGENTS.md nạp lại**, và thông điệp kết thúc **không có trần** (E21).
- **C5.** Citation/`entity_id` resolve **bằng xây dựng** (chỉ số mảng + resolver tất định), không để LLM chép lại chuỗi hay tự verify.
- **C6.** **Không đọc lại tệp spill.** Nội dung vượt **50.000 byte** bị thay bằng preview + đường dẫn; đọc lại tệp spill đó tính tiền như **uncached input mới**. Nếu cần lại dữ liệu, sửa script để in ít hơn, đừng đọc bù.

**D. Kỷ luật gọi cognitive (chữa Lớp A)**

- **D1.** Bulk semantic = **một bước, một batch, 0 tool, packet inline ở đuôi, JSON ra**. Không ngoại lệ.
- **D2.** Khai `maxTokens` như **chặn trên chủ động** (mặc định 256K, trần model 384K — E17) và `estimate_wave.py` cảnh báo khi `est_out` > 80% giá trị khai.
- **D3.** `reasoningEffort ∈ {off, low, high, max}` (chỉ 4 giá trị) và là **biến đo**, không phải hằng số niềm tin: ghi `reasoningTokens` mỗi wave.
- **D4.** `estimate_wave.py` in dự toán **trước**; `token_ledger.py` ghi số **thật** sau; sai số dự toán là chỉ số hạng nhất.

**E. Kỷ luật ngân sách (đo, không gate)**

- **E1.** Ledger ghi **cả** `quota_tokens` **và** `billed_usd`; nói rõ thước nào. Giá để trong **tệp cấu hình**, không hardcode.
- **E2.** Wave bulk xếp **off-peak** (ngoài 08:00–11:00 và 13:00–17:00 giờ VN, T2–T6) ⇒ **tiết kiệm 50%**. Là tham số của `article_run.py`, không phải thói quen.
- **E3.** **Làn hằng ngày** và **chiến dịch backlog** là hai ngân sách tách biệt.
- **E4.** Chỉ số ưu tiên: **độ phủ L1 bài đăng hôm nay**, rồi mới tới backlog.

**F. Cưỡng chế (thay lời hứa bằng máy)**

- **F1.** Ràng buộc nào **có thể** là hook/`guard()` thì **không** viết trong prompt. Cơ chế native đã xác minh: `ctx.tools.guard(fn)` (từ chối đơn điệu, trả lý do), waterfall `tools/pre-execute` (allow/deny/ask), `tools/post-execute` (thay/khử kết quả), `agent/pre-step` (từ chối một bước), **`agent/request` (thay cấu hình gọi LLM đã đóng băng)**, `system-prompt/assemble` (thay toàn bộ assembly), emit `tools/result`.
- **F2.** **Preflight preset guard**: từ chối chạy wave nếu phiên không ở preset/route đúng vai (chữa E2). Cài bằng `guard()`/`tools/pre-execute`, không bằng câu trong prompt.
- **F3.** **Cưỡng chế effort/model cho worker bằng `agent/request`**, không phụ thuộc `settings.yaml` (đang là `high`).
- **F4.** Giữ ADR 0008 §2.4 "thất bại phải ồn ào" nguyên vẹn.
- **F5.** Hiệu chỉnh chính sách theo `/learn`: mọi ma sát phải thành backlog item hoặc rule **trước khi đóng phiên**.

### 5.3 Bảng chọn chế độ thực thi worker (mới, từ xác minh DSH)

| Chế độ | Cách gọi | Preset? | Tinh gọn | Output | Dùng khi |
| --- | --- | --- | --- | --- | --- |
| **PTC subagent** (hiện tại) | `agent_article` trong `run_code`, Conductor ở `mode: ptc` | Con **kế thừa** preset cha | Trung bình | `res.text` gán biến ⇒ **không vào context cha** (`tool/ptc-dispatch` chỉ vào log bền) | Giữ vòng lặp người-trong-loop, cần Conductor phán đoán |
| **Headless** | `dsh --profile headless "<task>"` | **Không hỗ trợ preset**; tinh gọn bằng `--patch` hoặc `$DSH_HOME/profiles/headless/cordis.patch.yml` (`disabled: true` các row) | Có thể rất tinh gọn | stdout = **đúng** thông điệp cuối; reasoning ra stderr; exit 0/1; **không có `--json`, không có usage** | Wave 0-token conductor: một tiến trình một batch, gọi từ `article_run.py` |
| **SDK JSON-RPC** | `dsh --profile sdk`, nói JSON-RPC 2.0 qua stdin/stdout | Không preset; cấu hình qua profile | Trung bình | Có khung có cấu trúc (`session.event`, `session.status`) | Cần điều khiển hai chiều, structured |
| **sdk-minimal** | `dsh --profile sdk-minimal` | Cây Cordis **độc lập, không layer dsh-base** | **Tinh gọn nhất** (agent + llm-deepseek + pwsh bền + session JSONL; **không** fs/web/subagent/skill tool) | JSON-RPC | Kernel worker lý tưởng; cần `DEEPSEEK_API_KEY` |

**Đề xuất (câu hỏi mở #2):** đo cả hai phương án trên cùng một wave ở Phase 04 — **PTC subagent** (giữ Conductor) và **headless + overlay tinh gọn** (bỏ Conductor khỏi bulk lane) — rồi chốt bằng `quota_tokens` và độ phức tạp vận hành.

---

## 6. Bề mặt DSH thật (xác minh mã nguồn 2026-09-18)

Nguồn: `@deepseek-ai/*` **0.1.5-rc.1** (`%USERPROFILE%\.dsh\profiles\node_modules` là **junction** tới cây npx). Nhãn **[V]** đã kiểm chứng · **[U]** chưa.

### 6.1 Sự thật chịu lực

| Hạng mục | Thực tế đã xác minh | Nguồn |
| --- | --- | --- |
| Phiên bản | **0.1.5-rc.1**; hai đường dẫn là **cùng một cây nguồn** (junction) | `npx/package.json`; SHA256 khớp |
| Profile ship sẵn | **Đúng 5**: `acp`, `web`, `headless`, `sdk`, `sdk-minimal`. `tui`/`rescue`/`desktop` không tồn tại (`desktop` bị chặn cứng) | `dsh-app-boot/lib/index.js:327-355` |
| Profile tự khởi tạo | Thiếu `$DSH_HOME/profiles/<name>/package.json` + tên là template ⇒ **tự tạo**, không lỗi | `dsh-app-boot/lib/index.js:886-892` |
| `headless` | Một task một tiến trình; stdout **chỉ** thông điệp cuối; reasoning ra stderr; exit 0/1; **không preset, không `--json`, không usage**; phải khởi động **qua launcher `dsh`** | `dsh-headless/lib/index.js:26,163-167`; `README.md:12,123,126` |
| Layer patch | `--patch <file>` và `$DSH_HOME/profiles/<name>/cordis.patch.yml` được áp **sau mọi bundle layer** ⇒ đây là **cơ chế duy nhất** để có composition tinh gọn cho headless/sdk | `dsh/lib/profile-boot-*.js:305-310` |
| Row subagent — 9 khóa | `provider`(req) · `toolName` · `modelSelectionSettings` · `enableRunInBackground` · `backgroundMode` · `agentOptions` · `persona` · `toolFilter` · `maxDepth` | `dsh-tool-subagent/lib/index.js:252-270` |
| `provider` của row | Là **backend** (spawn/fork/acp/codex/claude-code), **không** phải LLM provider | `dsh-tool-subagent/README.md:83` |
| `agentOptions` — 4 khóa | `provider` · `model` · `reasoningEffort` · `maxTokens` | `dsh-tool-subagent/lib/index.js:258-263` |
| `reasoningEffort` | Chỉ **`off` · `low` · `high` · `max`** (không có `medium`/`minimal`/`none`) | `dsh-llm-deepseek/lib/index.js:26-28` |
| `maxTokens` mặc định | **256.000** (`DEFAULT_MAX_TOKENS = 256e3`); con kế thừa của cha | `dsh-llm-deepseek:1394,1998`; `dsh-subagent/lib/types/child-agent.js:79-92` |
| `maxDepth` | Trần **tuyệt đối** theo depth của con; **`0` cấm delegation hoàn toàn** (con đầu tiên đã là depth 1) | `dsh-subagent/lib/types/child-agent.js:32-41`; `README.md:53` |
| `toolFilter` | Chỉ `{allow?, deny?}`. `{allow: []}` **hợp lệ** và gỡ mọi tool **kế thừa**; `{}` ném lỗi lúc mount; tên lạ ném lỗi ở **lần delegation đầu**, không phải lúc mount | `dsh-tool-subagent:265-268,370`; `dsh-tools:2795-2804` |
| `run_code` dưới `ptc` | Được **thêm lại SAU** restriction; dưới `ptc` gọi trực tiếp `read`/`write` bị từ chối | `dsh-tools:2874,2994` |
| Kế thừa của con | Con **join preset của cha** (`composeFrom`); **không có khóa nào để tắt** | `dsh-subagent/lib/index.js:543`; `dsh-tool-subagent` schema |
| Prompt của con | Section order **cố định**, tool list lexicographic; **runtime/time context nối ở ĐUÔI** ⇒ prefix ổn định, đuôi biến động mỗi bước | `dsh-system-prompt:96,112,133`; `dsh-time-context:231` |
| AGENTS.md | Nạp lại cho **mọi** agent (kể cả con), dedup theo digest. **Gỡ được** bằng `agent-instructions.config.maxBytes <= 0` | `dsh-agent-instructions:668,1270` |
| Pruner kết quả tool | `thresholdChars 8192 / head 4096 / tail 1024` — **nhưng không đăng ký listener**; chỉ chạy **bên trong một lượt compaction** | `dsh-compaction-tool-result-pruner:11,137` |
| Compaction | Tự chạy ở **80%** cửa sổ context, giữ lại **16%**; khoá `thresholdRatio 0.8`, `retainRatio 0.16`, `auto true`; viết lại vùng surface ⇒ **mất cache** từ điểm viết lại | `dsh-compaction-basic:15,17,76,111` |
| Spill | Ngưỡng **50.000 byte** (`maxInlineBytes`), preview head/tail + đường dẫn; **miễn trừ `read`** và call lồng nhau | `dsh-spill-policy:74,104,157`; `dsh-base/cordis.patch.yml:386` |
| Kết quả tool văn bản | **Không** lưu theo tham chiếu ⇒ nằm nguyên văn, gửi lại **mỗi bước** cho tới khi spill/prune/compact | `dsh-session:1204,1269` |
| Cấu trúc bước | **Một request mỗi BƯỚC**; mọi tool call trong một assistant message chạy trong bước đó (song song ≤ **10**), rồi **một** request mới | `dsh-agent-loop:1116,1118,1226` |
| `maxParallelSubCalls` | Mặc định **10**; thuộc row `dsh-tools`, **không** thuộc row subagent; **chưa** được cấu hình ở đây | `dsh-tools:2575` |
| Cô lập con | Chỉ **thông điệp cuối** của con qua lại; transcript và tool I/O ở lại. Thông điệp cuối **không có trần** (chỉ dòng tóm tắt 120 ký tự, diagnostics 4096 byte) | `dsh-subagent:185,217,661,2475` |
| Usage — trường | `assistant/message.data.usage` = `{inputTokens, outputTokens, totalTokens, cacheReadTokens, reasoningTokens}`. DSH **đổi tên và tách rời** các rổ: DeepSeek `prompt_tokens` gồm cả cache hit, harness trừ ra nên `inputTokens = prompt_tokens − cacheRead` = **uncached**. Tên gốc `prompt_cache_hit_tokens` **không** được lưu. | `dsh-llm-deepseek:1146-1166` |
| Usage — 6 cạm bẫy | (1) `inputTokens` là **uncached**, không phải prompt size; (2) `totalTokens` **theo từng request**, không tích luỹ; (3) `reasoningTokens` là **tập con** của `outputTokens`; (4) `cacheWriteTokens` **luôn 0** với adapter DeepSeek; (5) DSH **không lưu giá/tiền** ở bất kỳ đâu ⇒ `billed_usd` phải tính ngoài; (6) `surfaceTokens = systemTokens + messageTokens` (**không** cộng `toolsTokens`), còn `pressureTokens = input + cacheRead + cacheWrite` của mẫu mới nhất (**không** gồm output) | đo thật, đối soát khớp tuyệt đối tại `seq=283` |
| Usage — GUI | Không có lệnh `/usage`, không có `dsh usage`, không có lệnh chi phí. Con số "Usage" trên GUI = `uncachedInput + cacheRead + cacheWrite + output` ⇒ **có tính cache read**; pill theo lượt lại dán nhãn uncached là "Input". Vì vậy mọi con số báo cáo phải nêu rõ thước | `dsh-client-ui-chat/lib/client.js:3942,4016` |
| Usage — quy kết con | Burn của con **không** xuất hiện trong `tokenUsage` của cha (đo: cha 158.277 uncached, ba con 158.898 + 126.250 + 125.100). Muốn đủ chi phí một wave phải duyệt `subagentCatalog` rồi cộng projcache của từng con | `session_projcache` thật |
| Budget | DSH **không có** trần token/chi phí theo phiên hay theo ngày (grep toàn bộ `.js`: chỉ có nhận diện lỗi `QUOTA` phía provider). Các giới hạn số duy nhất: `maxTokens` 256.000/request, `contextWindow` 1M, compaction 0,8×, pruner 8192 ký tự, spill 50.000 byte | `dsh-llm:132,174`; `dsh-compaction-basic:14-18` |
| Nguồn đọc usage ngoài tiến trình | **JSONL** tại `~/.dsh/sessions/<workspace-key>/<uuid>/` (**không** phải SQLite): `dsh-session-query-sqlite` được mount **trơ** (`path: ':memory:'`, `openAt: never`) | `dsh-base/cordis.patch.yml:110-113,129-133` |
| Hook bridge CC/Codex | Có package nhưng **không** composition nào mount ⇒ không dùng được mặc định; chỉ có extension point native | grep toàn bộ `.yml` |
| `dsh-token-meter` | Chỉ expose **projection trong tiến trình**; script ngoài phải tự parse JSONL | `dsh-token-meter/lib/index.js:609-615` |
| PTC trong phiên GUI hiện tại | **Không bật** nếu preset là `standard` (không mount code-runtime); `tool-presentation` mặc định `native` | `dsh-agent-presets/presets/standard`; `dsh-tools/types/ptc.js` |
| Preset mặc định | `.dsh/settings.yaml` khai **`ptc`**; base do web-app đăng ký là **`standard`**; **dù giá trị nào cũng KHÔNG phải `news-scape-conductor`** | `settings.yaml:11-12`; `dsh-web-app/cordis.patch.yml:480-484` |

### 6.2 Câu hỏi đã được trả lời (thay cho U1–U6 của rev 1)

| # | Câu hỏi | Kết luận |
| :-: | --- | --- |
| U1 | `toolFilter.allow: []` hợp lệ? | **Hợp lệ**, gỡ mọi tool kế thừa. Nhưng dưới `ptc`, `run_code` được thêm lại ⇒ phải dùng **`mode: native`** để có 0 tool (E15) |
| U2 | `reasoningEffort` có mức tắt? | **Có: `off`** (hợp lệ trong 4 giá trị) |
| U3 | `maxTokens` mặc định? | **256.000**, không phải 8K (E17) |
| U4 | Thông điệp cuối của con có vào context cha? | **Dưới `ptc`: KHÔNG** (kết quả sub-call chỉ vào `tool/ptc-dispatch` trong log bền; chỉ log + giá trị `return`/`print` là model-facing). **Ở `native`: CÓ**. ⇒ Xác nhận giả định chịu lực của kiến trúc, **với điều kiện Conductor ở `ptc`** |
| U5 | Nguồn usage | **JSONL** `~/.dsh/sessions/...`, field `assistant/message.usage`; SQLite phiên **trơ** |
| U6 | `headless` chọn được preset? | **Không.** Tinh gọn bằng `--patch`/overlay profile |
| U7 | Preset mặc định thực tế của GUI | **[U]** `settings.yaml` (`ptc`) và base web (`standard`) mâu thuẫn ⇒ Phase 00 xác nhận bằng một lệnh. Không đổi kết luận E2 |
| U8 | `--patch`/overlay headless hoạt động end-to-end? | **[U]** cần một lần chạy thật ở Phase 00 |

---

## 7. Kiến trúc đích

```text
[L0 — Cấu hình, 0 token]
  preset "news-scape-conductor"  (PTC, giữ người-trong-loop, phán đoán)
  preset "news-scape-article"    (MỚI: mode native, agent-instructions.maxBytes 0,
                                  compaction auto false, effort đo được)
  overlay headless tinh gọn      (MỚI: disabled row tool-*/skill-*/subagent/workflow/ralph)
  guard(preflight preset) · agent/request (cưỡng chế effort+maxTokens)

[Nhịp ngày, 0 token]
  morninger (capture + derive) → monocle.db
        │
        ▼
[L1 — Operator, 0 token]
  article_pack.py  Priority Sorter (Tier 1 watchlist/vĩ mô khẩn)
                   + Smart Paragraph Distillation (trần mềm ≤1.000 tok/bài)
                   → packet compact · map i→article_id · histogram · est_wave
        │
        ▼
[L2 — Cognitive, 1 BƯỚC/batch]
  agent_article · deepseek-flash · 0 tool · 1 bước · packet ở ĐUÔI prefix
                · maxTokens chặn trên · reasoningEffort đo được
                → final message: mảng Article Record gọn (Intent + Nội dung + c:[index])
        │
        ▼
[L1 — Operator, 0 token]
  article_expand.py · salvage từng item · dual-track reconcile (BOTH/LLM_ONLY/CODE_ONLY)
                    · citations-by-index CÓ kiểm `p[k] in cleaned_text` · map i→article_id
        │
        ▼
[Gate & Giao hàng]
  l1_ingest.py / agent_ingest.py → token_ledger.py --wave N → radar
  Batch 1 xong ⇒ write_user_output.py (giao sớm) ; Batch 2..N ⇒ phủ 100%
        │
        ▼
[L0 — Handoff 0 token]
  handoff.py → data/state/HANDOFF-<ts>.md ⇒ ĐÓNG PHIÊN, mở phiên mới
```

**Bất biến:** (1) LLM không đọc file, không ghi file, không tra catalog, không tự chấm DoD. (2) Code không quyết định thực thể hay tóm tắt — chỉ so khớp, tra cứu, bung chỉ số, đo. (3) Ràng buộc cưỡng chế được bằng máy thì **không** nằm trong prompt. (4) Mọi cấu hình liên quan ranh giới phải được **khẳng định ở runtime**, không tin YAML.

---

## 8. Các phase

| Phase | Tên | Phụ thuộc | Token model | Ghi file |
| :-: | --- | --- | :-: | :-: |
| 00 | **Vá P0 + Đo lường + xác minh U7/U8** | plan duyệt | không | `token_ledger.py`, `ctx_probe.py`, `estimate_wave.py`, bảng `token_ledger`, `rules/05` §4 |
| 01 | **Doctrine + preflight guard + cấu hình worker đúng** | 00 | không | `docs/TOKEN_ECONOMY.md`, `AGENTS.md` §9, `rules/08`, preset article, `guard()`, hook `agent/request` |
| 02 | **Prefix sinh tự động + Priority Pack + Distillation** | 01 | không | `build_article_prefix.py`, `article_pack.py`, archive 404+2 packet |
| 03 | **Unified single-step + expander + nghỉ hưu** | 02 | flash | `article_expand.py`, deprecate 6 hạng mục |
| 04 | **Wave 1 bước + handoff 0 token + off-peak (+ chọn chế độ thực thi)** | 03 | flash | `article_run.py`, `handoff.py`, overlay headless, radar 6 mục |
| 05 | **Migration tồn đọng + Dual-Track delivery** | 04 | flash | định tuyến lại 10.100 bài; `user_output.py` (Cấp 3) |
| 06 | **Khai phá catalog + amendment hiến pháp** | 05 | flash | `leaders.yaml`, `AGENTS.md` §6, `rules/01`, `rules/05`, ADR note |

### Phase 00 — Vá P0 & Đo lường

- **Vá P0 (làm trước tiên, không tiêu token):**
  - P0-1/E14: đổi `maxDepth: 0` → **`1`** trong `agent.cordis.yml` (2 row) + ADR 0009 §2.2 + plan 1445 §7. Chạy thử một lần delegation để chứng minh không còn `SubagentDepthError`.
  - P0-2/E15: chuyển worker sang **`mode: native` + `allow: []`** cho bulk lane; giữ `ptc` cho Conductor. **Khẳng định tập tool hiệu lực = ∅** bằng đọc `system-prompt/assemble` (`tools[]`) — không tin YAML (E20).
  - P0-3/E16: ghi nhận bằng số rằng pruner không chạy ngoài compaction; đặt ngưỡng đóng phiên theo §5.A5.
- **Sửa `rules/05` §4** (C1 cờ `--dangerously-skip-permissions`, C2 định mức bịa) và `preset.yml` (C3).
- **Xác minh U7** (preset mặc định GUI) và **U8** (`--patch` headless) — hai lệnh, không tiêu token model.
- **`token_ledger.py`** — ghi bảng `token_ledger` trong `harness.db`. Nguồn và luật kế toán **đã xác minh**, phải theo đúng:
  - **Nguồn chuẩn xác theo bước**: JSONL `~/.dsh/sessions/<workspace-key>/<uuid>/session.v3.jsonl.zstd`. Đây là **zstd nhiều frame, KHÔNG phải mỗi dòng một frame** (file thật: 165 frame / 312 dòng / 1.956.142 byte sau giải nén) ⇒ phải quét magic `28 B5 2F FD` và giải nén **từng frame**. Gọi giải nén một-frame chỉ trả về frame 0.
  - **`session_projcache/sessions/<id>.json` là checkpoint, không phải bộ đếm sống** (`writeEveryEvents: 200`, `writeIntervalMs: 5000`, flush ở `turn/end`) ⇒ chỉ dùng để đối soát chéo, không dùng cho số theo bước.
  - **6 luật kế toán bắt buộc** (mỗi luật đã kiểm chứng bằng số thật):
    1. `inputTokens` = **uncached input**, KHÔNG phải kích thước prompt. Đọc sai sẽ **hụt ~30 lần** (143.662 vs 3.692.718 prompt bị tính trong một phiên thật).
    2. Per-request: `inputTokens + cacheReadTokens + outputTokens == totalTokens`. **Không bao giờ cộng `totalTokens`** để lấy tổng phiên — nó không tích luỹ.
    3. `reasoningTokens` là **tập con của `outputTokens`** ⇒ cộng cả hai là **đếm trùng**.
    4. `cacheWriteTokens` **luôn 0** với adapter DeepSeek ⇒ không dựng dòng chi phí ghi cache.
    5. DSH **không lưu bất kỳ dữ liệu giá/tiền nào** ⇒ `billed_usd` tính ngoài, giá để trong tệp cấu hình.
    6. `contextPressure.surfaceTokens` = `systemTokens + messageTokens` (**không** cộng `toolsTokens`); `pressureTokens = inputTokens + cacheReadTokens + cacheWriteTokens` của mẫu mới nhất (**không** gồm output). Cộng cả ba trường breakdown là **vượt trần sai**.
  - **Quy kết usage của con**: con là **Session riêng**, và **burn của con KHÔNG xuất hiện** trong `tokenUsage` của cha. Số thật: cha 158.277 uncached, ba con 158.898 + 126.250 + 125.100. Ledger phải **duyệt `subagentCatalog` của cha rồi cộng projcache của từng con**; một ngân sách theo phiên mà chỉ đọc cha sẽ hụt phần lớn chi phí.
  - **Đối soát bắt buộc**: tổng ledger của một phiên phải khớp `tokenUsage.totals` trong projcache tại cùng `seq` (đã chứng minh khớp tuyệt đối ở `seq=283`).
  - `billed_usd` tính từ ba rổ rời: `uncached×giá_miss + cacheRead×giá_hit + output×giá_out`, có hệ số peak/off-peak theo `ts`.
- **Acceptance:** một wave thật có dòng ledger đủ trường; `reasoningTokens` quan sát được; **tập tool hiệu lực của worker = ∅ được in ra và lưu vào trace**; delegation `maxDepth: 1` chạy được; `rules/05` §4 không còn cờ bị ADR 0008 cấm; U7/U8 có kết luận.

### Phase 01 — Doctrine + cưỡng chế

- §5 → **`docs/TOKEN_ECONOMY.md`** + một mục mới trong `AGENTS.md` (luật: phân loại theo **lane** trước khi hành động).
- Preset `news-scape-article`: `agent-instructions.config.maxBytes: 0`, không `tool-web`/`tool-skill`/`jobs`, `compaction auto: false`, `mode: native`; mount qua junction.
- `guard()` preflight preset (F2) + hook `agent/request` cưỡng chế `reasoningEffort`/`maxTokens` (F3).
- **Acceptance:** phiên sai preset ⇒ wave bị từ chối kèm lý do; hai phiên liên tiếp có prefix byte-identical **tính đến hết phần section** (đuôi runtime/time context được phép khác); `reasoningTokens == 0` khi effort `off`.

### Phase 02 — Prefix + Pack

- `build_article_prefix.py`: sinh digest nhóm đóng từ `entities.json` + `taxonomy.json` + hash kiểm drift. `entity_id` dùng `IND_GICS*`, `type` dùng `INDUSTRY_GICS*`.
- `article_pack.py`: Priority Sorter 2 tầng; Smart Paragraph Distillation **trần mềm 1.000 token/bài**; **compact JSON bắt buộc**; in histogram + `est_wave`.
- **Archive** `data/agent_tasks/l1/` (404) + `data/agent_tasks/*.task.json` (2).
- **Acceptance:** không dòng nào > 2.000 ký tự (chặn G1); không bài nào > 1.000 token; 100/100 Tier 1 xếp đầu; hash prefix khớp catalog; thư mục packet cũ rỗng.

### Phase 03 — Single-step + Expander + Nghỉ hưu

- `agent_article`: `allow: []`, `mode: native`, `maxDepth: 1`, `maxTokens` chặn trên, effort đo được.
- `article_expand.py`: salvage từng item; dual-track reconcile; citations-by-index **có khẳng định `p[k] in cleaned_text`** (E7); resolver `IND` **exact canonical name**, sàn `resolve_rate` 85% (E6).
- Deprecate tường minh 6 hạng mục (E10).
- **Acceptance:** 1 batch 100 bài = **đúng 1 bước**; **tập tool hiệu lực = ∅ (in ra)**; DoD pass 100% với citations kiểm được; `parse_fail` < 2%; `cacheReadTokens` ≥ 95% kích thước prefix từ batch 2 (E5); 0 grep/glob trong vết con.

### Phase 04 — Wave 1 bước + Handoff + Off-peak + chọn chế độ

- `article_run.py --wave N`: radar → pack → spawn → expand → ingest → ledger trong **một** lệnh; hỗ trợ cửa sổ off-peak.
- `handoff.py` sinh `data/state/HANDOFF-<ts>.md` **0 token**; ngưỡng áp suất 25/40%.
- **Thí nghiệm chế độ thực thi** (§5.3): cùng một wave chạy bằng **PTC subagent** và bằng **headless + overlay tinh gọn**; so `quota_tokens`, số bước, độ phức tạp.
- **Acceptance:** một wave hoàn chỉnh trong **≤ 2 bước** conductor; cắt phiên giữa wave ⇒ phiên mới đọc handoff chạy tiếp, không mất bài; handoff 0 token; radar in đúng cửa sổ giá; có bảng so sánh hai chế độ.

### Phase 05 — Migration & Dual-Track delivery

- Định tuyến lại 10.100 bài tồn đọng theo **ngân sách chiến dịch riêng** (E3).
- `user_output.py`: thêm `intent_llm`, `intent_code`, `intent_source` vào `FINAL_COLUMNS` — **Cấp 3, ADR + story riêng** (E12).
- **Acceptance:** Excel đủ 3 cột; Batch 1 giao ≤ 3 phút; độ phủ L1 hôm nay 100%; backlog giảm theo ngân sách đã duyệt.

### Phase 06 — Khai phá catalog & Amendment hiến pháp

- `LLM_ONLY` → `unlisted_candidates` → `entity-curator` sinh delta; seed `leaders.yaml` cho nhóm `PER`.
- Amendment: `AGENTS.md` §6, `rules/01`, `rules/05` §2.7, ghi chú ADR 0003/0005 (E11); ADR 0009 §2.2 (`maxDepth: 1`) và §2.3 (route pro→flash) (C5, C4); §2.5 (`maxParallelSubCalls`) (C6).
- **Acceptance:** delta catalog chờ duyệt; không còn điều khoản hiến pháp nào mâu thuẫn với mô hình 1 agent; ba ADR không còn tham số không tồn tại.

---

## 9. Chỉ số & ngân sách (đo, không gate)

| Chỉ số | Mục tiêu | Đo ở đâu |
| --- | ---: | --- |
| Bước (step) / wave conductor | **≤ 2** (từ ≥ 5 ở RUNBOOK §3) | ledger `turns` |
| Bước / batch worker | **1** | ledger `turns` |
| Tool call / batch worker | **0** — và **khẳng định tập tool hiệu lực = ∅** | vết con + `system-prompt/assemble` |
| `reasoningTokens` / batch | đo, chưa đặt trần | ledger |
| Token/bài đường LLM (`full`) | ≤ 1.220 | ledger |
| Token/bài packet (`full`) | ≤ 1.000 | histogram `article_pack.py` |
| `cacheReadTokens` / batch (từ batch 2) | ≥ 95% kích thước prefix | ledger |
| `resolve_rate` theo nhóm thực thể | ≥ 85% | `article_expand.py` |
| DoD pass lần đầu | ≥ 99% item | ingest |
| `parse_fail` / wave | < 10% (dừng wave nếu vượt) | parser salvage |
| Sai số dự toán vs thực tế | ≤ 20% | `estimate_wave.py` vs ledger |
| Context phiên conductor | xanh < 25% · vàng 25–40% · đỏ > 40% (**cố ý thấp hơn ngưỡng compaction 80% của DSH**) | `ctx_probe.py` |
| Tỷ lệ chi phí off-peak | ≥ 80% tổng wave | ledger (`ts` vs cửa sổ peak) |

**Hai chốt tự động duy nhất** (bảo vệ chất lượng, không bảo vệ ví): `est_ctx_peak` vượt ngưỡng ⇒ `article_pack.py` chia nhỏ batch; `parse_fail` > 10% ⇒ dừng wave và báo.

---

## 10. Rủi ro & đối sách

| Rủi ro | Đối sách |
| --- | --- |
| Đổi `maxDepth` sang 1 mở lại đường đệ quy | `maxDepth: 1` cho phép **đúng một** tầng; cháu bị chặn. Kèm test khẳng định `SubagentDepthError` khi con thử spawn |
| `allow: []` bị gõ nhầm khóa và **bỏ qua im lặng** ⇒ con giữ toàn bộ tool | E20: khẳng định tập tool hiệu lực ở **acceptance**, không tin YAML |
| Con ở `mode: native` không tự verify citations | Chính là mục tiêu (E7: citations theo chỉ số + expander kiểm `in cleaned_text`) |
| Bỏ cổng ADR 0008 trước khi có số đo | §0.3: đo trước, gỡ sau, chỉ khi sai số ≤ 20% |
| `settings.yaml` (`reasoningEffort: high`) đè cấu hình worker | F3: cưỡng chế bằng hook `agent/request`; ledger kiểm `reasoningTokens` mỗi wave |
| Chất lượng giảm ở bài thứ 60–100 của batch | Đo `recall theo vị trí` (plan 1445 §11); hạ về 50 bài nếu giảm |
| Làn Article và làn L1 cũ chạy song song ⇒ 2 nguồn sự thật | E9 + E10: archive + deprecate **trong cùng phase**, có cảnh báo khi gọi script cũ |
| Off-peak làm trễ giao hàng Batch 1 | Off-peak chỉ áp cho **bulk/backlog**; Batch 1 ưu tiên độ trễ, ghi rõ đang chấp nhận giá peak |
| Nội dung distilled phá chuỗi con của citations | E7: khẳng định `p[k] in cleaned_text` ở expander, fail ⇒ requeue |
| Headless stdout bẩn nếu model thêm lời dẫn | Prompt ép JSON-only; parser salvage; `parse_fail` là chỉ số hạng nhất |
| DSH lên phiên bản mới đổi hành vi (`maxDepth`, PTC, pruner) | Pin version; `docs/proposals/dsh-surface-verified-*.md` ghi file:line để so lại khi nâng cấp |

---

## 11. Anti-scope

- Không dùng code/regex để **quyết định** thực thể hay tóm tắt; chỉ so khớp, tra cứu, bung chỉ số, đo.
- Không model ngoài họ flash (D6). Không model local/NER.
- Không đổi `l1-entity-output-v1`, `agent-output-v2-lean`, `check_l1_dod`, schema `monocle.db` (trừ bảng `token_ledger`).
- Không chạm `raw_html` (WORM).
- Không dựng lại cổng hỏi người dưới tên khác. Số đo để **nhìn**, không để **chặn**.
- **Không xây bundle `@news-scape/dsh-harness` (H3)** trong plan này. Ưu tiên cấu hình plugin DSH có sẵn.
- Không "continue"/multi-turn để vượt output cap.

---

## 12. Câu hỏi mở cho anh

| # | Câu hỏi | Đề xuất mặc định |
| :-: | --- | --- |
| 1 | **Ràng buộc thật**: tiền ($), quota token/ngày của gói, hay chất lượng ngữ cảnh? | Ghi **cả hai** thước vào ledger; tối ưu theo `quota_tokens` vì chặt hơn |
| 2 | Bulk lane dùng **PTC subagent** (giữ Conductor) hay **headless + overlay tinh gọn** (bỏ Conductor)? | Đo cả hai ở Phase 04 trên cùng một wave, chốt bằng `quota_tokens` + độ phức tạp vận hành |
| 3 | Cho `reasoningEffort: off` cho worker, chấp nhận rủi ro chất lượng? | Đo trên 200 bài gán tay; chốt bằng DoD recall |
| 4 | Batch 100 hay 50? | 100 mặc định, đo recall theo vị trí; hạ về 50 nếu đuôi batch giảm |
| 5 | Backlog 10.100 bài: chiến dịch riêng hay trộn vào làn ngày? | Chiến dịch riêng, ngân sách duyệt riêng (E3) |
| 6 | `IND` phát canonical name (exact) hay surface tự do (fuzzy)? | Canonical name — digest đã trong prefix, 0 token thêm |
| 7 | 2 cột Intent Excel có thật cần cho người dùng? | Nếu chưa ai dùng, hoãn để tránh Cấp 3 + ADR (E12) |
| 8 | Chấp nhận vá P0 (E14/E15/E18) như **hotfix** trước Phase 01? | Có — chúng chặn mọi wave, và sửa rất nhỏ (3 dòng YAML + 2 ADR) |

---

## 13. Nghiệm thu chung

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest tests/ -q          # giữ >= baseline passed
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token
```

Mỗi phase trả đủ **Unit + Integration + Platform**. Phase 00 có bằng chứng **số token thật + tập tool hiệu lực + delegation chạy được**, và kết quả U7/U8; Phase 03 có bằng chứng **round-trip expander + citations kiểm được**.

---

## 14. Tài liệu cần đồng bộ

| Đích | Việc |
| --- | --- |
| `AGENTS.md` | Thêm §9 "Kinh tế Token & Phân làn công việc" trỏ `docs/TOKEN_ECONOMY.md`; sửa §6A/§6B cho mô hình 1 agent (E11) |
| `docs/TOKEN_ECONOMY.md` | **MỚI** — §5 của plan này |
| `docs/proposals/dsh-surface-verified-2026-09-18.md` | **MỚI** — §6 với file:line, để so lại khi nâng cấp DSH |
| `.agents/rules/01` | Cập nhật 2-I/O cho worker 0-tool (E11) |
| `.agents/rules/05` | §4.4 bỏ `--dangerously-skip-permissions` (C1); §4 bỏ định mức bịa (C2); §2.7 cập nhật schema (E11) |
| `.agents/rules/08` | Bổ sung "cấm read-back", "cấm đọc nguồn để suy ra hợp đồng", "cấm LLM làm việc script làm được" |
| `docs/decisions/0008` | Amendment gỡ cổng + giữ "thất bại ồn ào" — **Cấp 3**, sau Phase 00 |
| `docs/decisions/0009` | §2.2 `maxDepth: 0` → **`1`** (C5); §2.5 `maxParallelSubCalls` — cấu hình thật hoặc gỡ (C6); §2.3 ghi chú route pro→flash (C4) |
| `.agents/dsh/presets/.../agent.cordis.yml` | `maxDepth: 0` → `1`; sửa comment sai về `allow`+`ptc` (C7); thêm row worker `mode: native` |
| `.agents/dsh/presets/.../preset.yml` | Mô tả đúng preset (C3) |
| `docs/decisions/0003`, `0005` | Ghi chú thứ tự ưu tiên code_first vs agent dưới mô hình 1 agent |
| `.agents/registry.yaml` | Thêm `article-processor`; `l1-entity-matcher` + `gold-financial-analyst` → `deprecated`; **bỏ `tokens_per_item` bịa**, trỏ ledger |
| `.agents/pipeline.yaml` | Stage `article_pack` · `article_analyze` · `article_expand`, rồi `l1_ingest` + `gold_ingest` |
| `.agents/skills/*` | `l1-entity-matcher` §6: sinh bảng tra tự động; `token-auditor`: bỏ định mức 450/1.470 |
| `plans/20260918-1445-.../plan.md` | Hấp thu E1–E21; sửa §7 (`maxDepth`), §10 (E5), §12 (E17), §15 (E11/E12) |
| `project/scripts/pipeline_radar.py` | In context pressure + cửa sổ giá + `resolve_rate`; bỏ hằng số 450 |
| `docs/SESSION-LATEST.md` | Ghi plan này là điểm vào của đợt cải tiến |

---

## 15. Bảng nghiệm thu đóng phiên (Harness Closure Protocol)

| Hạng mục | Kết quả |
| --- | --- |
| Phân loại prompt | **Cấp 2 — NORMAL**. Chạm Cấp 3 ở 4 điểm đã tách riêng: amendment ADR 0008, Data Contract Excel, `rules/05` §4 trái ADR, sửa `maxDepth` trong ADR 0009 |
| WIP=1 | **Không mở story mới.** US-020 giữ `in_progress`. Plan là artefact tiền-story; mỗi phase sinh story riêng khi duyệt (rule 07 §4) |
| Bounded context | 12 tệp hiến pháp/plan + `.dsh/settings.yaml` + preset + 3 trang api-docs + 4 subagent khảo sát mã DSH |
| Sản phẩm | `plans/20260918-1624-dsh-token-economy-workmethod/plan.md` |
| Bằng chứng chính | `batch_handoff.py:146` (`indent=2`); `child-agent.js:32-41` + `README.md:53` (`maxDepth 0` cấm delegation); `dsh-tools:2874,2994` (`run_code` dưới ptc); `dsh-compaction-tool-result-pruner:137` (không listener); `dsh-compaction-basic:15,111` (80%/16%); `dsh-llm-deepseek:26-28,1394` (effort, 256K); `dsh-agent-instructions:668` (gỡ AGENTS.md); `dsh-app-boot:327-355` (5 template); `dsh-headless:26,163-167`; api-docs (giá, peak/off-peak, cache 64 token, thinking mặc định) |
| Phát hiện mới ngoài 2 plan | E1, E2, E3, E5, E9, E10, E12, E13, **E14–E21**; C1–C4 hiến pháp; **C5–C8 khiếm khuyết đang sống** |
| Trace | `harness_cli.py intake` (id 23) + `trace` đã ghi (lane `normal`) |
| Friction → backlog | Đã ghi: (a) `rules/05` §4.4 còn cờ bị ADR 0008 cấm; (b) `maxDepth: 0` làm H2 bất khả thi; (c) `mode: ptc` đảo ngược ranh giới 2-I/O; (d) `settings.yaml` để `reasoningEffort: high` mặc định cho mọi con; (e) DSH không có cắt tỉa transcript ngoài compaction |
| Việc chờ anh | Duyệt plan (§0); trả lời câu hỏi mở (§12) — tối thiểu **#1, #2, #8** |
| Bước tiếp theo | Anh duyệt → **Phase 00**: vá P0 (3 dòng YAML + 2 ADR), sửa `rules/05`, dựng ledger, xác minh U7/U8 — tất cả 0 token model |
