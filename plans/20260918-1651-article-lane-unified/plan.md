































































# Plan hợp nhất — Article Lane: xử lý bài đăng bằng LLM ở quy mô lớn

|                        |                                                                                                                                                                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ngày                  | 2026-09-18                                                                                                                                                                                                                              |
| Trạng thái           | **ĐÃ TRIỂN KHAI (2026-09-18).** Toàn bộ Q1–Q6 đã chốt; mã, cấu hình, kiểm định và tài liệu quản trị đã hoàn tất. Chưa chạy workload thật trên runtime — phần đó do người vận hành thực hiện |
| Vai trò               | **Tài liệu quy phạm duy nhất.** Thi hành theo đúng tài liệu này. Không cần đọc song song tài liệu nào khác                                                                                                      |
| Thay thế              | `20260918-1133-l1-llm-lean-token` · `20260918-1445-article-lane-scale-token` · `20260918-1624-dsh-token-economy-workmethod` — cả ba chuyển **SUPERSEDED**, giữ làm hồ sơ                                           |
| Hồ sơ giữ lại      | `20260918-1445-.../AUDIT-plan-set-2026-09-18.md` (22 phát hiện, lý do của mọi quyết định ở §2) · `20260918-1624-.../plan.md` §6 (bề mặt DSH kèm file:line, dùng khi nâng cấp DSH)                                 |
| Phân loại            | **Cấp 2 — NORMAL**. Chạm Cấp 3 ở hai điểm đã tách riêng: amendment ADR 0008 (§2 Q4) và amendment ADR 0009 `maxDepth` (§3.1)                                                                                       |
| Ràng buộc chủ đạo | **LLM là bộ não nhận diện và tóm tắt.** Code chỉ làm cơ học: đóng gói, tra cứu, bung chỉ số, đo lường. Không dùng code để **quyết định** thực thể hay tóm tắt                               |

> **Định vị một câu:** mỗi lượt gọi LLM nhận một packet nhiều bài và trả một mảng JSON trong **đúng một bước**; mọi thứ tất định do code làm với 0 token; và toàn bộ chi phí đo được bằng số thật trước và sau khi chạy.

---

## 1. Mục tiêu nghiệp vụ và định nghĩa "xong"

**Mục tiêu:** bao quát toàn bộ tin tức thị trường tài chính, quy mô 500–1.000 bài/ngày, với quota ổn định và dự đoán được.

**Định nghĩa xong ở cấp chương trình** — đo bằng radar, không bằng ý kiến:

> Toàn bộ bài đăng trong ngày được xử lý xong trong ngày (radar báo độ phủ 100%), với chi phí mỗi bài **đo được** và ổn định qua bảy ngày liên tiếp, và không còn hàng đợi `failed` tồn dư sau mỗi chu kỳ.

Mỗi phase phải chứng minh được nó đưa hệ thống tới gần định nghĩa này.

**Vạch xuất phát, đo ngày 2026-09-18:**

|                         |                                                                 Giá trị |
| ----------------------- | ------------------------------------------------------------------------: |
| Bài cào trong ngày   |                                                                       307 |
| Bài hoàn tất L1      |                                                        **0 (0,0%)** |
| Bài hoàn tất Gold    |                                                                         0 |
| Hàng đợi`failed`   |                                             189 work_items · 85 l1_tasks |
| Packet tồn trên đĩa | 408 file =**2.118 bài** (95 lô chứa 1.805 bài + 313 packet lẻ) |
| Tồn đọng trong DB    |                             ~6.404 bài chưa L1 · ~4.600 bài chờ Gold |

Hai con số cuối là **hai đại lượng khác nhau**, không được dùng lẫn. Con số 10.100 trong tài liệu cũ là sai do giả định mọi packet đều là lô 25 bài.

---

## 2. Nhật ký quyết định

|      #      | Quyết định                                                                                                                                                                                                                                         | Chốt                                         | Ngày |
| :----------: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | ----- |
| **Q1** | Hình thái worker:**subagent PTC in-process**. Không dùng `headless`, không dùng `sdk`/`sdk-minimal`                                                                                                                                 | ✅ Đã chốt                                 | 18/09 |
| **Q4** | Cổng phê duyệt ADR 0008:**bỏ hẳn**. Anh điều khiển bằng lệnh wave tường minh. Chỉ giữ chốt kỹ thuật tự động (§9.2)                                                                                                         | ✅ Đã chốt                                 | 18/09 |
| **Q5** | **Xuất cột Intent ra Excel — NẰM TRONG PHẠM VI**, làm ở bước 5. Deliverable phải phân biệt rõ thực thể nào do **LLM** nhận diện và thực thể nào do **code** nhận diện                                       | ✅ Đã chốt (hiệu chỉnh 18/09, xem §2.2) | 18/09 |
| **Q6** | **Hợp nhất** ba plan thành tài liệu này trước khi implement                                                                                                                                                                             | ✅ Đã chốt                                 | 18/09 |
| **Q2** | Độ sâu xử lý:**100% `full`**. Mọi bài đều được xử lý đầy đủ tiêu đề và nội dung. Không có chế độ `lite`                                                                                                         | ✅ Đã chốt                                 | 18/09 |
| **Q3** | Xếp Tier 1 theo**recall-biased**. Nguyên tắc: *nhận diện thừa còn hơn bỏ sót* — ưu tiên tăng true positive, chấp nhận đánh đổi để giảm false negative. Code-first vẫn còn điểm mù nhưng phải hạn chế tối đa | ✅ Đã chốt                                 | 18/09 |

Lý do đầy đủ của từng quyết định nằm ở `AUDIT-plan-set-2026-09-18.md`. Tài liệu này chỉ ghi kết quả và hệ quả.

### 2.1 Hai hệ quả lớn của Q2 = 100% `full`

**Hệ quả A — Subscriber-gating không còn là cơ chế kiểm soát chi phí.** ADR 0005 đặt subscriber-gating để tiết kiệm 85–91% token Gold bằng cách chỉ phân tích sâu bài có người đăng ký. Với 100% `full`, **mọi bài đều được phân tích sâu**, nên vai trò tiết kiệm chi phí của nó chấm dứt. Subscriber-gating **vẫn giữ nguyên vai trò định tuyến giao hàng** — quyết định bài nào vào Excel của user nào. Cần ghi chú vào ADR 0005 rằng lý do chi phí đã hết hiệu lực, còn lý do định tuyến thì không (§15).

**Hệ quả B — Q2 làm Q3 gần như miễn phí, hai quyết định cộng hưởng.** Khi mọi bài đều `full`, Tier chỉ còn quyết định **thứ tự chạy**, không quyết định **độ sâu**. Một bài bị recall-bias xếp nhầm vào Tier 1 chỉ tốn *sớm hơn*, không tốn *nhiều hơn*. Vì vậy nguyên tắc "nhận diện thừa còn hơn bỏ sót" của anh áp được rộng rãi mà không phải trả giá token — chi phí duy nhất là Batch 1 dài hơn, tức Tier 2 chờ lâu hơn một chút.

**Hệ quả C — Distillation trở thành đòn bẩy chi phí chính.** Trước đây phân tầng `full`/`lite` là cần gạt lớn nhất. Nay mọi bài đều mang nội dung, nên **kích thước packet mỗi bài quyết định trực tiếp tổng chi phí**. Thuật toán chắt lọc ở §6.3 chuyển từ "yêu cầu đúng đắn" thành **cần gạt chi phí số một**, và `token/bài packet` trở thành chỉ số quan trọng nhất cần theo dõi.

### 2.2 Hiệu chỉnh Q5 — cột Intent trở lại phạm vi

**Ghi nhận sai lệch.** Bản trước của tài liệu này hoãn việc xuất cột Intent ra Excel với lý do chưa xác nhận có người dùng cần. Điều đó **mâu thuẫn với chỉ đạo đã có**: deliverable cho người dùng cuối phải cho thấy thực thể nào do **LLM** nhận diện và thực thể nào do **code** nhận diện. Chỉ đạo này đã được ghi vào plan 1445 §4.4 từ trước. Hiệu chỉnh: **đưa trở lại phạm vi, làm ở bước 5.**

**Đánh giá lại lý do hoãn.** Lý do cũ là "thay đổi Data Contract nên phải lên Cấp 3". Kiểm tra thực tế `project/src/export/user_output.py`: `FINAL_COLUMNS` là một danh sách 16 cột, và đây là **thay đổi cộng thêm** — nối cột vào cuối, không sửa, không xoá, không đổi nghĩa cột nào đang có. Người tiêu thụ hiện tại không vỡ. Dữ liệu nguồn đã được `article_expand.py` đối soát sẵn ở bước 4, nên phần việc còn lại chỉ là đọc thêm ba trường và nối vào danh sách cột.

⇒ **Phân loại đúng: Cấp 2**, không phải Cấp 3. Không cần ADR riêng. Vẫn ghi vào `docs/stories` như một story bình thường theo rule 07.

**Ba cột bổ sung vào cuối `FINAL_COLUMNS`:**

| Cột              | Nội dung                                                         | Ví dụ                                                            |
| ----------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------ |
| `intent_llm`    | Thực thể do**LLM** nhận diện độc lập, kèm mã nhóm | `Hòa Phát [COM]; HRC [AST]; thuế chống bán phá giá [THM]` |
| `intent_code`   | Thực thể do**code** nhận diện tất định               | `HPG [TIC]; THEP [IND]`                                          |
| `intent_source` | Nhãn đối soát mỗi thực thể                                 | `BOTH` · `LLM_ONLY` · `CODE_ONLY`                          |

Yêu cầu cốt lõi của anh là hai cột đầu — phân biệt LLM với code. Cột thứ ba là nhãn đối soát, đã có sẵn trong DB nên xuất kèm không tốn thêm gì, và nó chính là thứ cho thấy **vùng giá trị riêng của LLM** (`LLM_ONLY`: thương hiệu con, ngành suy diễn, chủ đề vĩ mô mà code không có từ khoá cứng).

---

## 3. Bề mặt DSH — sự thật chịu lực đã xác minh

Nguồn: `%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai` phiên bản `0.1.5`. Mọi dòng dưới đây đã đọc mã nguồn, không suy đoán.

### 3.1 Bốn khiếm khuyết P0 phải vá trước mọi wave

|  #  | Sự thật                                                                                                                                                                                                                                                                                          | Bằng chứng                                                                        | Vá                                                                                                                           |
| :--: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| P0-1 | **`maxDepth: 0` cấm delegation hoàn toàn**, không phải chặn đệ quy. `childDepth = depth(parent)+1` nên con đầu tiên là 1 > 0 ⇒ `SubagentDepthError`. Preset đang khai `0` cho `agent_l1` và `agent_gold` ⇒ **hai tool này chưa bao giờ spawn được** | `dsh-subagent/lib/types/child-agent.js:32-41`; `dsh-tool-subagent/README.md:53` | Đổi thành**`maxDepth: 1`** (cho đúng một tầng, chặn cháu). Kèm amendment ADR 0009 §2.2                     |
| P0-2 | **`run_code` được chèn SAU lớp lọc `toolFilter`** và `restrict()` **ném lỗi** nếu cố đặt tên nó ⇒ con PTC luôn có `run_code`                                                                                                                                 | `dsh-tools/lib/index.js:2874`, `:2800`                                          | Bỏ tiêu chí "0 tool" (§10). Thay bằng "SDK rỗng" + "`turns == 1`"                                                     |
| P0-3 | **Không thể đặt `mode` cho con.** Schema row subagent có đúng 9 khoá, không có `mode`. Con kế thừa mode của cha                                                                                                                                                             | `dsh-tool-subagent/lib/index.js:252-270`; `dsh-tools:2668`                      | Gỡ mọi hạng mục`mode: native` cho worker. Conductor giữ `ptc` (§4 R1)                                               |
| P0-4 | **Pruner kết quả tool không đăng ký listener**, chỉ chạy bên trong một lượt compaction; mà compaction tự chạy ở **80%** cửa sổ                                                                                                                                       | `dsh-compaction-tool-result-pruner/lib/index.js`; `dsh-compaction-basic:15,111` | Không trông vào DSH để cắt transcript. Cắt bằng thiết kế (§8) và ngưỡng đóng phiên thấp hơn nhiều (§8.3) |

### 3.2 Các sự thật khác dùng trong thiết kế

| Hạng mục                       | Thực tế                                                                                                                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Cấu trúc bước                | **Một request mỗi BƯỚC**. Mọi tool call trong một assistant message chạy trong cùng bước đó (song song ≤ 10), rồi sinh **một** request mới                     |
| `agentOptions`                 | Đúng 4 khoá:`provider` · `model` · `reasoningEffort` · `maxTokens`                                                                                                           |
| `reasoningEffort`              | Chỉ 4 giá trị:`off` · `low` · `high` · `max`. **Thinking bật mặc định**; `.dsh/settings.yaml` hiện để `high` cho mọi con                                   |
| `maxTokens`                    | Mặc định adapter**256.000** (không phải 8K). Trần model 384K. Con kế thừa của cha                                                                                           |
| Kết quả sub-call dưới`ptc` | **Không** vào context cha — chỉ vào `tool/ptc-dispatch` trong log bền. Dưới `native` thì **có**                                                                  |
| Prefix                           | System prompt là**một node, không có timestamp**. Thứ tự section cố định, tool list lexicographic. Runtime/time context nối ở **đuôi**                            |
| Prefix vỡ khi                   | đổi tool set · đổi preset · đổi model/effort route · compaction viết lại vùng surface                                                                                          |
| Spill                            | Ngưỡng**50.000 byte**; vượt thì thay bằng preview + đường dẫn. **Miễn trừ `read`**                                                                               |
| Usage                            | `assistant/message.usage = {inputTokens, outputTokens, totalTokens, cacheReadTokens, reasoningTokens}`. `inputTokens` là **uncached**, không phải kích thước prompt        |
| Nguồn đọc usage               | **JSONL** `~/.dsh/sessions/<workspace-key>/<uuid>/session.v3.jsonl.zstd`. SQLite phiên được mount **trơ**                                                               |
| Quy kết con                     | Con là**Session riêng**; burn của con **không** nằm trong `tokenUsage` của cha                                                                                         |
| Budget                           | DSH**không có** trần token hay chi phí theo phiên/ngày                                                                                                                         |
| Preset mặc định               | `.dsh/settings.yaml` khai `ptc`; **không phải** `news-scape-conductor` — đây là nguyên nhân gốc khiến phiên 17/09 chạy `subagent` generic, mất sạch ranh giới |

### 3.3 Giá và cửa sổ giá `deepseek-flash`

| USD / 1M token      | Off-peak |  Peak |
| ------------------- | -------: | ----: |
| Input — cache hit  |    0,003 | 0,006 |
| Input — cache miss |     0,15 |  0,30 |
| Output              |     0,60 |  1,20 |

Peak = 01:00–04:00 và 06:00–10:00 UTC, T2–T6, tức **08:00–11:00 và 13:00–17:00 giờ VN**. Off-peak giảm 50%.

Cache tự động, prefix từ token 0, đơn vị 64 token, không phí ghi cache, **best-effort không đảm bảo**. Context 1M, max output 384K. **Không có giới hạn TPM/RPM**, chỉ concurrency 2.500. Con số "≤100.000 token/phút" trong `rules/05` §4.4 là bịa và phải gỡ.

---

## 4. Chẩn đoán gốc và ba ràng buộc của kiến trúc đã chọn

### 4.1 Công thức chi phí

Đơn vị chi phí là **bước**, không phải số bài.

```
billed_input ≈ Σ_{s=1..S} ( P + Σ_{j<s} (U_j + O_j) )  ≈  S·P + O(S²)
S = số bước · P = prefix · U = nội dung mới · O = output
```

Hai vệt audit thật chứng minh:

| Vệt |          Bài | Bước | Nội dung duy nhất |        Bị tính |          Hệ số |               Token/bài |
| ---- | ------------: | -----: | ------------------: | ---------------: | ---------------: | -----------------------: |
| L1   | 25 tiêu đề |     19 |              82.202 |         ~845.000 | **12,1×** |                  ~39.600 |
| Gold |        5 bài |     21 |             ~11.000 | 154.000–300.000 |               — | **30.800–60.000** |

Định mức khai trong `registry.yaml` là 1.470 token/bài ⇒ lệch **21–41 lần**. Cắt nội dung 50% giảm ~4% hoá đơn; cắt `S` từ 19 xuống 1 giảm ~93%. **Đòn bẩy nằm ở số bước.**

Hai lớp đốt token độc lập, và lớp thứ hai chưa ai chữa:

| Lớp                               | Ở đâu                           | Thuốc                                                                                                                 |
| ---------------------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **A — Worker**              | Mỗi lần gọi LLM xử lý bài    | 1 bước/batch · packet ở đuôi · bản ghi tối giản + expander ·`maxTokens` chặn trên · effort đo được |
| **B — Phiên điều phối** | Phiên DSH của người vận hành | **1 bước/wave** · operator-first · handoff 0 token · đóng phiên sau wave · ngưỡng context thấp       |

RUNBOOK hiện mô tả **5 bước mỗi wave**. Vì Lớp B rẻ để sửa và ảnh hưởng tới mọi việc còn lại, nó được xếp **trước** Lớp A trong §11.

### 4.2 Ba ràng buộc do Q1 (con PTC) áp lên

**R1 — Conductor bắt buộc ở `mode: ptc`.** Dưới `ptc`, kết quả sub-call không vào context cha. Nếu chuyển sang `native`, output ~30.000 token mỗi batch rơi thẳng vào context Conductor, làm sống lại đúng Lớp B. *Đổi Conductor sang `native` là phá vỡ kiến trúc.*

**R2 — Không gỡ được AGENTS.md khỏi prefix của con** (~4.069 token). Khoá `agent-instructions.maxBytes` ở cấp phiên, mà con dùng chung composition với Conductor. Nằm đầu prefix, tĩnh, byte-identical ⇒ cache hit từ lần gọi thứ hai. **Chấp nhận, không chống.**

**R3 — Con nhận ~640 token hướng dẫn về một SDK rỗng, kèm một câu lệnh mâu thuẫn.**

| Section            | Nội dung                                                                                                                              |                         Đo được |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------: |
| `tools:ptc-only` | *"`run_code` is the only tool you can call directly… **Reach every tool the SDK declares below** from inside the program."* |                           ~40 token |
| `tools:sdk`      | Hướng dẫn viết`run_code`, kết thúc bằng `interface ToolArgsMap {}` **rỗng**                                          | 1.802 ký tự ≈**600 token** |

Prompt đang **mời** model viết chương trình trong khi `tools` không có binding nào. Chi phí không đáng lo vì nằm trong prefix tĩnh (cache hit), nhưng rủi ro hành vi là thật: model thử gọi tool, thất bại, tốn thêm bước.

⇒ **Bắt buộc:** `ARTICLE_SYSTEM_CORE` phải vô hiệu hoá tường minh, đại ý *"Bạn không có tool nào. Không gọi `run_code`. Không viết chương trình. Trả lời bằng một mảng JSON duy nhất trong thông điệp cuối."* Nhắc lại ở **cuối packet** để nằm gần điểm sinh output.
⇒ **Canh bằng chỉ số `turns` của con.** Bằng 1 là đạt; lớn hơn 1 nghĩa là persona cần sửa.

---

## 5. Kiến trúc đích

```text
[L0 — Cấu hình, 0 token]
  preset news-scape-conductor : mode ptc (R1), maxDepth 1, maxParallelSubCalls cấu hình thật
  guard(preflight preset)     : từ chối chạy wave nếu phiên sai preset
  hook agent/request          : cưỡng chế reasoningEffort + maxTokens cho worker
        │
[Nhịp ngày, 0 token]  morninger (capture + derive) → monocle.db
        │
        ▼
[L1 — Operator, 0 token]  article_pack.py
  ├─ Priority Sorter recall-biased (Q3) → Tier 1 vào Batch 1 (chỉ quyết THỨ TỰ, không quyết độ sâu)
  ├─ Distillation TẤT ĐỊNH, NGUYÊN KHỐI (§6.3) → mảng p[] cho MỌI bài  ← cần gạt chi phí số 1
  ├─ Chỉ số cục bộ i=0..N-1, packet COMPACT JSON, map i→article_id giữ trên đĩa
  └─ In dự toán: est_prefix / est_miss / est_out / est_ctx_peak + histogram token/bài
        ▼
[L2 — Cognitive, ĐÚNG 1 BƯỚC/batch]  agent_article
  deepseek-flash · toolFilter allow:[] · maxDepth 1 · reasoningEffort đo được · maxTokens chặn trên
  prefix tĩnh (cache hit): ARTICLE_SYSTEM_CORE + digest nhóm đóng ~6.650 token
  đuôi động: packet
  → final message: mảng Article Record gọn
        ▼
[L1 — Operator, 0 token]  article_expand.py
  ├─ Parser salvage từng item (item hỏng → requeue riêng item đó)
  ├─ Citations by index → nguyên văn p[k], CÓ khẳng định p[k] ⊂ cleaned_text
  ├─ Resolver theo nhóm → entity_id · Dual-track reconcile → intent_source
  └─ Sinh l1-entity-output-v1 (mọi bài) + agent-output-v2-lean (bài full)
        ▼
[Gate & Giao hàng]  l1_ingest.py / agent_ingest.py → write_user_output.py
        ▼
[Đo & Bàn giao, 0 token]  token_ledger.py --wave N → radar ·  handoff.py → đóng phiên
```

**Bốn bất biến:**

1. LLM **không** đọc file, **không** ghi file, **không** tra catalog, **không** tự chấm DoD.
2. Code **không** quyết định thực thể hay tóm tắt — chỉ so khớp, tra cứu, bung chỉ số, đo.
3. Ràng buộc nào cưỡng chế được bằng máy thì **không** viết trong prompt.
4. Mọi cấu hình liên quan ranh giới phải được **khẳng định ở runtime**, không tin YAML (khoá gõ sai bị bỏ qua im lặng).

---

## 6. Hợp đồng dữ liệu

### 6.1 Article Packet — đầu vào

```json
{"d":"2026-09-18","n":100,"a":[
{"i":0,"t":"Hòa Phát báo lãi quý 3 tăng 25%, HRC hưởng lợi thuế chống bán phá giá","p":["Tập đoàn Hòa Phát công bố lợi nhuận sau thuế quý 3 đạt…","Doanh thu mảng thép cuộn cán nóng HRC tăng 32%…","Ông Trần Đình Long nhận định chính sách thuế tự vệ…"]},
{"i":1,"t":"VND: Báo cáo tình hình quản trị công ty 6 tháng đầu năm","p":["VNDirect công bố báo cáo tình hình quản trị định kỳ 6 tháng…"]}]}
```

| Trường | Nghĩa                                                                                                                 |
| -------- | ---------------------------------------------------------------------------------------------------------------------- |
| `d`    | ngày batch, một lần cho cả packet                                                                                  |
| `i`    | chỉ số cục bộ, thay`article_id` sha256 64 ký tự                                                                |
| `t`    | tiêu đề nguyên văn                                                                                                |
| `p[]`  | các đoạn đã chắt lọc,**nguyên văn, nguyên khối, giữ thứ tự gốc**. Có ở **mọi** bài (Q2) |

Không còn trường `m`: theo Q2, mọi bài đều `full`. Bài ngắn hoặc CBTT định kỳ vẫn có `p[]`, chỉ là mảng ngắn hơn — thuật toán §6.3 tự cho ra ít đoạn khi bài ít nội dung, không cần một chế độ riêng.

Bỏ khỏi packet: `code_first` hints, `domain`, `url`, `raw_sha256`, `entity_catalog_ref`, `output_contract`, `constraints`, `instructions_ref`. Mọi luật và hợp đồng đã nằm trong prefix tĩnh.

**Định dạng packet — đính chính so với bản trước của tài liệu này.**

Bản trước ghi "bắt buộc compact JSON". Khi triển khai và đo lại giới hạn thật của công cụ đọc, hoá ra quy tắc đó **suy diễn sai chiều** và sẽ gây hỏng nặng hơn lỗi nó định tránh.

Giới hạn thật của công cụ đọc trong DSH, đọc từ README của `dsh-tool-fs`:

| Tham số              |        Giá trị | Ý nghĩa                                        |
| --------------------- | ---------------: | ------------------------------------------------ |
| `readMaxLineLength` |  **2.000** | ký tự giữ lại mỗi dòng, phần dư bị cắt |
| `readMaxBytes`      | **51.200** | trần byte cho một lần gọi                    |
| `readLimit`         |  **2.000** | trần số dòng cho một lần gọi               |

Compact JSON dồn **cả packet vào một dòng duy nhất**. Đo thật trên lô 100 bài: một dòng **267.143 ký tự**, tức sẽ bị cắt còn 2.000 và mất 99,3% nội dung. Đó là hỏng nặng hơn hẳn lỗi ban đầu.

**Quy tắc đúng không phải là compact hay không, mà là: không dòng nào được vượt trần cắt dòng.** Packet mới tách nội dung thành **mảng đoạn**, nên chỉ cần ghi xuống dòng theo từng phần tử là mỗi đoạn chiếm một dòng riêng. Đo trên 4.493 đoạn thật: dài nhất **954 ký tự**, không đoạn nào chạm trần. Vì vậy:

- Ghi packet **xuống dòng theo phần tử** (`indent=1`), không dồn một dòng.
- `article_pack.py` **khẳng định** dòng dài nhất dưới ngưỡng an toàn và **ném lỗi** nếu vượt.
- Đoạn dài hơn 1.800 ký tự bị **bỏ nguyên đoạn** ở khâu chắt lọc, giữ bất biến nguyên văn.

Lỗi gốc của vệt Gold vẫn đúng như đã chẩn đoán: `cleaned_text` là **một chuỗi liền 2.173–2.537 ký tự** nằm trên một dòng. Điều đã thay đổi là cách chữa: tách thành mảng đoạn, chứ không phải đổi sang compact.

**Hệ quả vận hành:** lô 100 bài nặng ~348 KB nên vượt trần một lần đọc, phía điều phối phải **phân trang 7–8 lần đọc**. `article_pack.py` tính sẵn các cửa sổ dòng và `article_run.py` sinh sẵn chương trình lặp theo chúng. Các lần đọc này nằm trong **cùng một chương trình** nên **không sinh thêm bước nào** của mô hình, và kết quả ở lại trong chương trình chứ không vào ngữ cảnh.

### 6.2 Article Record — đầu ra

```json
[{"i":0,"e":[["Hòa Phát","COM"],["HRC","AST"],["thuế chống bán phá giá","THM"],["ông Trần Đình Long","PER"]],"s":"Hòa Phát công bố lợi nhuận quý 3 tăng 25% nhờ sản lượng HRC và giá bán cải thiện.","k":["Biên lợi nhuận HRC mở rộng sau thuế chống bán phá giá","Sản lượng nội địa tăng"],"im":"Kết quả vượt kỳ vọng hỗ trợ định giá ngắn hạn; theo dõi giá HRC quý 4.","sn":"pos","ts":"today","c":[0,2]},
{"i":1,"e":[["VND","TIC"]],"s":"VNDirect công bố báo cáo quản trị định kỳ 6 tháng, không có thay đổi nhân sự trọng yếu.","k":["Báo cáo định kỳ theo nghĩa vụ CBTT"],"im":"Không tác động tới định giá; giá trị chủ yếu là hồ sơ tuân thủ.","sn":"neu","ts":"arch","c":[0]}]
```

| Khoá          |     Bắt buộc     | Expander bù, 0 token                                                                       |
| -------------- | :----------------: | ------------------------------------------------------------------------------------------- |
| `e`          |         ✔         | `entity_id`, `type`, `in_list`, `method`, `categories`, `intent_source`         |
| `s`          |         ✔         | —                                                                                          |
| `k`, `im`  |         ✔         | —                                                                                          |
| `sn`, `ts` |         ✔         | map về enum đầy đủ                                                                     |
| `c`          | ✔ chỉ số đoạn | trích nguyên văn`p[k]` → citations ≥ 20 ký tự                                      |
| —             |                    | `article_id`, `title`, `recognized`, `processing_metadata`, `unlisted_candidates` |

**Mọi bài sinh cả `l1-entity-output-v1` và `agent-output-v2-lean`** (Q2). Đây là thay đổi vận hành đáng kể so với trước: `agent_ingest.py` nay nhận ~307 bản ghi mỗi ngày thay vì ~50, và cổng DoD Gold áp cho mọi bài. Cần kiểm lại sức chứa hàng đợi `work_items` ở bước 3.

Ước lượng: ~600–900 token vào, 220–300 token ra mỗi bài.

### 6.3 Bất biến Distillation — điều kiện sống còn của citations-by-index

Trần cơ học 2.200 ký tự cũ được thay bằng chắt lọc theo ngữ nghĩa. Việc này **âm thầm gỡ mất** bất biến của `rules/05` §2.3, mà toàn bộ cơ chế `c:[0,2]` lại đứng trên nó. Khôi phục tường minh:

> **Distillation chỉ được phép BỎ trọn vẹn một đoạn. Cấm cắt, cấm nối, cấm sửa chữ, cấm đổi thứ tự.** Mảng `p[]` là một tập con giữ nguyên thứ tự của các đoạn gốc, mỗi phần tử là **chuỗi con nguyên văn** của `cleaned_text`.

**Thuật toán tất định, có thứ tự bỏ xác định** — cần thiết để `est_ctx_peak` có cơ sở:

1. Luôn giữ `p0` (sapo).
2. Xếp hạng các đoạn còn lại: có số liệu định lượng (%, tỷ đồng, triệu USD, KQKD) > có phát ngôn lãnh đạo hoặc sự kiện pháp lý > còn lại.
3. Thêm dần **theo thứ tự gốc** cho tới khi chạm trần cứng token/bài.
4. Vượt trần ⇒ **bỏ đoạn hạng thấp nhất**, không bao giờ cắt đoạn.
5. Loại thẳng: lịch sử thành lập, giải thích thuật ngữ chung, "bài liên quan", footer toà soạn.

Kiểm bằng **unit test của `article_pack.py`**: mọi `p[k]` phải là chuỗi con của `cleaned_text` gốc. Bắt lỗi ở nơi sinh ra, không phải ở expander.

---

## 7. Nhóm thực thể và prefix

### 7.1 Ground truth catalog

`entities.json`: **1.262 entity**, 2.728 alias, 12 `type`.

**Drift phải xử lý:** `type` là `INDUSTRY_GICS1/2/3` nhưng `entity_id` mang tiền tố **`IND_GICS1/2/3:`**. Bảng tra trong SKILL.md không nói điều này, và đó là nguyên nhân gốc khiến agent trong vệt 845K phải tự dò `entities.json` — chiếm 53% toàn bộ nội dung duy nhất của vệt đó.

| `type`                   |              n | tiền tố`entity_id`  | Nhóm       |
| -------------------------- | -------------: | ----------------------- | ----------- |
| TICKER                     |          1.093 | `TICKER:`             | mở         |
| ETF · SECURITY_OTHER      |       28 · 11 | như type               | đóng (39) |
| INDEX · EXCHANGE          |         6 · 3 | như type               | đóng (9)  |
| INDUSTRY_GICS1/2/3         | 11 · 28 · 51 | **`IND_GICS*`** | đóng (90) |
| MACRO_GEO · MACRO_THEME   |         8 · 9 | như type               | đóng (17) |
| ASSET_CLASS · INSTITUTION |         7 · 7 | như type               | đóng (14) |

Ngành GICS chỉ có **1 alias = chính canonical name**, nên code không bao giờ khớp `"đường sắt"` thành `Vận tải đường bộ & đường sắt`. Đây chính là vùng LLM tạo giá trị và code không thay được.

### 7.2 Mười một mã nhóm — mỗi mã một resolver riêng

| Mã                                      | LLM phát khi thấy                                        | Resolver của code                                                                                                                                                   |
| ---------------------------------------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TIC`                                  | mã 3 ký tự in hoa                                       | exact code +`CODE_STOPLIST` + miễn trừ CBTT `^[A-Z0-9]{3}\s*:`                                                                                                 |
| `COM`                                  | tên doanh nghiệp / thương hiệu                        | alias fold + word-boundary + morphology guard +`brand_aliases.yaml`                                                                                                |
| `PER`                                  | tên người / lãnh đạo                                 | `leaders.yaml` — **chưa có**, xem §7.4                                                                                                                   |
| `FND`                                  | ETF / quỹ                                                 | digest 39 ID                                                                                                                                                         |
| `IDX` · `EXC`                       | chỉ số · sàn                                           | digest 6 · 3 ID                                                                                                                                                     |
| `IND`                                  | ngành                                                     | digest 90 ID;**LLM phát canonical name** để khớp exact-string; chọn cấp sâu nhất; `entity_id` dùng `IND_GICS*`, `type` dùng `INDUSTRY_GICS*` |
| `GEO` · `THM` · `AST` · `INS` | quốc gia · chủ đề vĩ mô · tài sản · định chế | digest 8 · 9 · 7 · 7                                                                                                                                              |

Không khớp ⇒ `in_list: false`, `entity_id: null`, vào `unlisted_candidates`. **An toàn theo hướng bỏ sót, không bịa.**

### 7.3 Prefix chứa gì

| Thành phần                                                                                   |            Token |       Vào prefix       |
| ---------------------------------------------------------------------------------------------- | ---------------: | :---------------------: |
| `ARTICLE_SYSTEM_CORE` (luật 10 miền + guard hình thái + hợp đồng + vô hiệu hoá R3) |           ~1.200 |           ✔           |
| Digest nhóm đóng 130 ID + alias                                                             |            3.750 |           ✔           |
| Digest ETF + SECURITY_OTHER (39)                                                               |              894 |           ✔           |
| Few-shot 3 ví dụ                                                                             |             ~800 |           ✔           |
| **Cộng**                                                                                | **~6.650** |                        |
| Digest TICKER Tier-1 (742 mã)                                                                 |            8.116 | ✘ — thí nghiệm §13 |
| Toàn bộ`entities.json`                                                                     |          324.493 |     ✘ tuyệt đối     |

LLM **không cần** biết mã: nó nói `"Hòa Phát"`, code biết `HPG`.

**Prefix sinh tự động** bằng `build_article_prefix.py` từ `entities.json` + `taxonomy.json`, kèm hash. Hết lớp lỗi bảng tra lệch catalog, và đổi catalog thì prefix đổi có kiểm soát.

### 7.4 Vai trò của nhóm `PER` trong giai đoạn đầu

`leaders.yaml` chưa tồn tại, seed ở bước cuối. Từ khi bật tới lúc đó, mọi `PER` resolve thành `unlisted` — **đúng thiết kế, không phải lỗi**.

⇒ `PER` ở giai đoạn đầu là **cơ chế thu thập dữ liệu cho catalog**, không phải cơ chế nhận diện. Đo bằng `per_discovery_count`, **miễn trừ khỏi `resolve_rate`**. Nếu đo gộp, chỉ số sẽ trượt sàn ở mọi wave theo đúng thiết kế của chính nó.

---

## 8. Kỷ luật vận hành

### 8.1 Bốn làn công việc

| Lane                                | Ai làm                                                                                       | Chi phí              | Dùng khi                                                 |
| ----------------------------------- | --------------------------------------------------------------------------------------------- | --------------------- | --------------------------------------------------------- |
| **L0 — Cấu hình & Script** | preset, hook,`guard()`, operator Python                                                     | **0 token**     | Việc lặp ≥2 lần, hoặc ràng buộc phải luôn đúng |
| **L1 — Operator**            | `run_code` gọi `pwsh`/`read`/`write` bên trong chương trình, chỉ `return` số | ~50–200 token/bước | Mọi thao tác cơ học                                   |
| **L2 — Cognitive**           | một lần gọi LLM cho một batch                                                             | ~1.220 token/bài     | Quyết định ngữ nghĩa                                 |
| **L3 — Human**               | anh                                                                                           | —                    | Duyệt plan/ADR, chọn ưu tiên, xử lý bất thường   |

**Quy tắc vàng:** một việc chỉ leo lên lane cao hơn khi lane thấp hơn **không thể** làm được. Đây là chiều ngược của "No Script Emulation": **cấm dùng LLM để giả lập script**.

### 8.2 Vòng đời phiên — chữa Lớp B

- **Một phiên = một mục tiêu = một wave.** Xong wave ⇒ ghi handoff ⇒ **đóng phiên**. Mở phiên mới rẻ hơn mang transcript phình, vì cache nằm ở phía nhà cung cấp chứ không gắn với session.
- **Một wave = một bước.** `article_run.py --wave N` gộp radar + pack + spawn + expand + ingest + ledger vào **một** lệnh; Conductor gọi trong **một** `run_code`. Không tách "kiểm tra trạng thái" thành bước riêng.
- **Đầu phiên nạp tối đa 3 tệp:** `AGENTS.md`, `docs/SESSION-LATEST.md`, skill chuyên trách.
- **Conductor chỉ đọc thứ script in ra.** Hợp đồng phải có lệnh in, không đọc mã nguồn để suy ra. Trong vệt 845K, agent đã tốn 4 bước đọc `l1_router.py` để suy ra `check_l1_dod`.
- **Mọi script in dưới 2 KB.** Trần spill là 50.000 byte; ghi output nặng ra đĩa, in một dòng trỏ đường dẫn.

### 8.3 Kiểm soát context

**Worker bị chặn bằng xây dựng.** Không tool nên không tích luỹ tool result; một bước nên không có history.

| Cấu hình                       | Prefix |  Packet | Output |    Đỉnh context |       % của 1M |
| -------------------------------- | -----: | ------: | -----: | ----------------: | --------------: |
| 50 bài                          |  7.000 |  42.500 | 15.000 |            64.500 |            6,5% |
| **100 bài** (mặc định) |  7.000 |  85.000 | 30.000 | **122.000** | **12,2%** |
| 200 bài                         |  7.000 | 170.000 | 60.000 |           237.000 |           23,7% |

Ở 100 bài/lượt, worker không tới gần vùng suy giảm. `article_pack.py` tính `est_ctx_peak` và **tự chia nhỏ batch** nếu vượt ngưỡng (mặc định 25% = 250K) — thực tế ngưỡng này chạm ở khoảng 210 bài, nên nó là lưới an toàn chứ không phải ràng buộc thường trực.

**Conductor giải bằng stateless-by-construction.** PTC chỉ đưa `print`/`return` vào history, nên một wave để lại dưới 100 token. Ngưỡng áp suất — **cố ý thấp hơn nhiều so với ngưỡng compaction 80% của DSH, vì DSH không cắt gì trước đó** (P0-4):

| Mức  |  Áp suất | Hành vi                                                             |
| ----- | ---------: | -------------------------------------------------------------------- |
| xanh  | dưới 25% | chạy bình thường                                                 |
| vàng |    25–40% | hoàn tất wave đang chạy rồi đóng phiên, không mở wave mới |
| đỏ  |  trên 40% | dừng ngay sau batch hiện tại                                      |

**Handoff 0 token.** Toàn bộ trạng thái nằm ở SQLite và file trên đĩa; Conductor không giữ gì mà DB không có. `handoff.py` sinh `data/state/HANDOFF-<ts>.md` từ DB, không nhờ LLM tóm tắt. Mất phiên giữa chừng chỉ mất đúng batch đang chạy, packet của nó vẫn trên đĩa.

### 8.4 Vệ sinh prefix

- Trong một phiên **không** đổi tool set, preset, model route hay effort.
- Nội dung tĩnh ở đầu, packet ở cuối.
- `compaction-basic` đặt `auto: false` cho phiên worker — compaction viết lại vùng surface là mất cache từ điểm viết lại.

### 8.5 Cưỡng chế bằng máy

| Cơ chế              | Việc                                                                                                                                                                  |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `guard()` preflight | Từ chối chạy wave nếu phiên**sai preset**. Đây là nguyên nhân gốc của vệt 845K, và phải chặn bằng máy chứ không bằng câu dặn trong prompt |
| hook`agent/request` | Cưỡng chế`reasoningEffort` và `maxTokens` cho worker, không phụ thuộc `settings.yaml` (đang để `high`)                                               |
| hook`tools/result`  | Gọi`token_ledger.py --append` sau mỗi lượt con                                                                                                                   |
| Khẳng định runtime | In**tập tool hiệu lực** và **`sdkSchemas`** của con vào trace. Khoá YAML gõ sai bị bỏ qua im lặng, nên không được tin YAML               |

---

## 9. Cơ chế đo — đo để nhìn, không để chặn

### 9.1 Ba công cụ, tất cả là operator 0 token

**`estimate_wave.py`** — dự toán trước khi chạy: `miss`, `hit`, `output`, `ctx đỉnh/lượt`, quota-equivalent, chi phí USD theo cửa sổ giá.

**`token_ledger.py`** — số thật sau khi chạy, ghi bảng `token_ledger` trong `harness.db`.

Nguồn và sáu luật kế toán, tất cả đã kiểm chứng bằng số thật — **thi hành đúng từng chữ**:

- Nguồn chuẩn theo bước là **JSONL**. File là **zstd nhiều frame, không phải mỗi dòng một frame** ⇒ phải quét magic `28 B5 2F FD` và giải nén **từng frame**; gọi giải nén một lần chỉ trả về frame 0.
- `session_projcache/sessions/<id>.json` là **checkpoint, không phải bộ đếm sống** ⇒ chỉ dùng đối soát chéo.

1. `inputTokens` là **uncached input**, không phải kích thước prompt. Đọc sai hụt khoảng 30 lần.
2. Per-request `inputTokens + cacheReadTokens + outputTokens == totalTokens`. **Không bao giờ cộng `totalTokens`** để lấy tổng phiên.
3. `reasoningTokens` là **tập con của `outputTokens`** ⇒ cộng cả hai là đếm trùng.
4. `cacheWriteTokens` **luôn 0** với adapter DeepSeek.
5. DSH **không lưu giá tiền ở đâu cả** ⇒ `billed_usd` tính ngoài, giá để trong tệp cấu hình.
6. `surfaceTokens = systemTokens + messageTokens` (**không** cộng `toolsTokens`); `pressureTokens = input + cacheRead + cacheWrite` của mẫu mới nhất (**không** gồm output).

**Quy kết usage của con:** con là Session riêng, burn của nó **không** nằm trong `tokenUsage` của cha. Ledger phải **duyệt `subagentCatalog` của cha rồi cộng projcache từng con**. Chỉ đọc cha sẽ hụt phần lớn chi phí.

**`pipeline_radar.py token`** — báo cáo sáu mục: quota (hit/miss/out/reasoning) · chi phí USD theo cửa sổ giá · hit ratio · context Conductor · sai số dự toán · **phân rã context từng subagent** (prefix hit / packet miss / output / turns).

### 9.2 Hai chốt tự động duy nhất

Bảo vệ chất lượng, **không** bảo vệ ví, **không** xin phép:

- `est_ctx_peak` vượt ngưỡng ⇒ `article_pack.py` tự chia nhỏ batch.
- `parse_fail` vượt 10% trong một wave ⇒ dừng wave và báo.

Không có `ns_activate`, không hỏi xác nhận, không chặn khi vượt số (Q4).

---

## 10. Chỉ số — tách bạch ba loại

Nhầm lẫn ba loại này là nguyên nhân khiến các tiêu chí cũ vừa mâu thuẫn vừa không kiểm được.

### 10.1 Điều kiện đóng phase — phải đạt mới đi tiếp

| Chỉ số                               | Ngưỡng                                                    |
| -------------------------------------- | ----------------------------------------------------------- |
| Bước của mỗi con (`turns`)       | **= 1**                                               |
| `sdkSchemas` của con                | **rỗng**, in ra và lưu trace                       |
| Bước của Conductor mỗi wave        | **≤ 2** (từ ≥5 hiện tại)                         |
| DoD pass lần đầu                    | **≥ 99% item**                                       |
| `parse_fail`                         | **< 2%**                                              |
| Prefix giữa hai batch liên tiếp     | **byte-identical**                                    |
| `p[k] ⊂ cleaned_text`               | **100%**, kiểm ở unit test của `article_pack.py` |
| `reasoningTokens` khi effort `off` | **= 0**                                               |
| Delegation với`maxDepth: 1`         | chạy được, không`SubagentDepthError`                 |

### 10.2 Ngưỡng ngắt mạch — chạm thì dừng máy

| Chỉ số                       | Ngưỡng                                  |
| ------------------------------ | ----------------------------------------- |
| `parse_fail` trong một wave | **> 10%** ⇒ dừng wave             |
| `est_ctx_peak`               | **> 25% của 1M** ⇒ tự chia batch |
| Áp suất context Conductor    | **> 40%** ⇒ dừng, handoff         |

### 10.3 Chỉ số quan sát — chỉ để nhìn, không chặn gì

`cacheReadTokens` so với kích thước prefix (có cảnh báo, **không** phải cổng — cache là best-effort phía nhà cung cấp) · token/bài theo độ sâu · `resolve_rate` **theo từng nhóm, miễn trừ `PER`** · `per_discovery_count` · sai số dự toán · tỷ lệ chi phí off-peak **tính trên chi phí bulk và backlog, không tính trên tổng wave** (vì Tier 1 chấp nhận giá peak để đổi lấy độ trễ thấp) · độ phủ L1 bài đăng trong ngày.

---

## 11. Các bước triển khai

Nguyên tắc thứ tự: **quyết định kiến trúc trước, thước đo sau, Lớp B trước Lớp A, việc chưa ai cần thì ra khỏi đường tới hạn.**

|       #       | Nội dung                                                                                                                                                                                                                                                                                                                                                                             | Vì sao đứng đây                                                                                                                                                             | Token |
| :------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---: |
| **0** ✅ | Vá bốn P0 (§3.1):`maxDepth` 0→1; sửa comment sai về `allow`+`ptc` trong `agent.cordis.yml`; cấu hình `maxParallelSubCalls` thật; sửa `rules/05` §4.4 còn cờ ADR 0008 đã cấm và định mức bịa. Sửa `preset.yml` mô tả sai. Amendment ADR 0009 §2.2. **Trích §6 của plan 1624 ra `docs/proposals/dsh-surface-verified-2026-09-18.md`** | Chúng chặn**mọi** wave; sửa rất nhỏ. Bản đồ DSH phải ra khỏi `plans/` trước khi ai đó dọn thư mục                                                      |   0   |
| **1** ✅ | **Lớp B trước:** `article_run.py` một lệnh cho cả wave · `handoff.py` · `ctx_probe.py` · kỷ luật vòng đời phiên (§8.2)                                                                                                                                                                                                                                    | Cắt 5 bước xuống 1 cho**mọi** việc còn lại, kể cả việc đang phát triển. Độc lập với worker                                                               |   0   |
| **2** ✅ | `token_ledger.py` + bảng `token_ledger` + radar 6 mục + `estimate_wave.py`                                                                                                                                                                                                                                                                                                    | Không đo thì mọi số sau lại là phỏng đoán. Hình thái đo đã xác định nhờ Q1                                                                                    |   0   |
| **3** ✅ | `build_article_prefix.py` + `article_pack.py` (Priority Sorter recall-biased, distillation tất định §6.3, compact JSON, histogram token/bài) + kiểm sức chứa `work_items` khi mọi bài đều qua cổng Gold + archive packet cũ **chưa xoá**                                                                                                                  | Bound xác định là tiền đề của`est_ctx_peak`; distillation nay là cần gạt chi phí số 1                                                                             |   0   |
| **4** ✅ | `agent_article` row + `ARTICLE_SYSTEM_CORE` (có phần vô hiệu hoá R3) + `article_expand.py` (salvage, citations-by-index có khẳng định, resolver theo nhóm, dual-track → `intent_source` vào DB)                                                                                                                                                                   | Lõi cognitive; giờ đã có thước đo và packet có bound                                                                                                                   | flash |
| **5** ◐ | Chạy làn ngày tới khi đạt định nghĩa xong (§1).**Giữ đường cũ đóng băng nhưng gọi được**. **Xuất 3 cột Intent ra Excel** (§2.2): nối `intent_llm`, `intent_code`, `intent_source` vào cuối `FINAL_COLUMNS` của `user_output.py`                                                                                                   | Chứng minh trên dữ liệu thật trước khi gỡ đường cũ. Cột Intent làm ở đây vì dữ liệu nguồn có từ bước 4 và cần bản ghi thật để kiểm mắt thường | flash |
| **6** ⏸ | Archive + deprecate đường cũ + chiến dịch backlog**2.118 bài** theo ngân sách riêng                                                                                                                                                                                                                                                                                   | Chỉ sau khi làn ngày chạy sạch trọn một chu kỳ                                                                                                                           | flash |
| **7** ⏸ | Khai phá catalog:`unlisted` → `entity-curator` → delta → seed `leaders.yaml`. Amendment hiến pháp còn lại                                                                                                                                                                                                                                                               | Cần dữ liệu`unlisted` tích luỹ từ bước 5–6                                                                                                                            | flash |

### 11.1 Điều kiện quay lui

Đường cũ chuyển sang **đóng băng nhưng gọi được** (in cảnh báo, **không xoá**) trong ít nhất một chu kỳ vận hành đầy đủ. Quay lui khi: DoD pass dưới 95% **hoặc** `parse_fail` trên 10%, kéo dài **hai wave liên tiếp**. Archive chỉ thực hiện ở bước 6, sau khi làn mới chạy sạch trọn một ngày.

---

## 12. Rủi ro và đối sách

| Rủi ro                                                                              | Đối sách                                                                                                                                                                            |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Con sa vào`run_code` vì prompt mời gọi (R3)                                    | Persona vô hiệu hoá tường minh + nhắc lại cuối packet; canh bằng`turns == 1`                                                                                                |
| Ai đó đổi Conductor sang`native`                                               | R1 là bất biến ghi trong tài liệu; output con sẽ rơi vào context cha                                                                                                           |
| Distillation phá chuỗi con của citations                                          | §6.3 bất biến nguyên khối + unit test ở`article_pack.py`                                                                                                                       |
| Chất lượng giảm ở bài cuối batch 100                                          | Đo recall**theo vị trí trong batch**; hạ về 50 nếu giảm; cơ chế không đổi                                                                                            |
| Prefix vỡ                                                                           | Hash prefix + kiểm byte-identical;`compaction auto: false`                                                                                                                          |
| Thinking bật lại do`settings.yaml` đè                                          | Hook`agent/request`; ledger kiểm `reasoningTokens` mỗi wave                                                                                                                      |
| Khoá YAML gõ sai bị bỏ qua im lặng                                              | Khẳng định tập tool hiệu lực ở runtime, không tin YAML                                                                                                                         |
| Hai nguồn sự thật khi làn cũ và mới chạy song song                           | §11.1 cửa sổ sống chung có điều kiện quay lui định lượng                                                                                                                   |
| Tier 1 bỏ sót bài watchlist do điểm mù code-first                              | Q3 recall-biased; theo dõi số bài watchlist rơi xuống Batch 2+. Vì Q2 = 100%`full`, bài xếp thừa vào Tier 1 **không tốn thêm token**, chỉ làm Batch 1 dài hơn |
| Khối lượng đột biến vượt ngân sách, không còn`lite` để hạ độ sâu | Ba van xả theo thứ tự ở §16.2: siết distillation → dời Tier 2–3 sang off-peak → giảm batch size                                                                             |
| `work_items` và cổng DoD Gold nay nhận mọi bài thay vì ~8–25%               | Kiểm sức chứa hàng đợi ở bước 3 trước khi bật wave đầu tiên                                                                                                             |
| Bỏ cổng xác nhận nên chạy nhầm wave lớn                                      | `--limit` tường minh, demand-driven; ledger cho thấy ngay wave nào tốn bao nhiêu                                                                                               |
| DSH nâng cấp đổi hành vi                                                        | Pin version; giữ`20260918-1624-.../plan.md` §6 có file:line để so lại                                                                                                          |

---

## 13. Ma trận thí nghiệm

| Biến                             | Mức                           | Đo                                                                                           |
| --------------------------------- | ------------------------------ | --------------------------------------------------------------------------------------------- |
| Batch size                        | 100 mặc định · 50 · 200   | DoD,`parse_fail`, **recall theo vị trí trong batch**, `est_ctx_peak`              |
| `reasoningEffort`               | `off` · `low` · `high` | `reasoningTokens` **và** DoD recall — biến đắt nhất, thinking tính giá output |
| Digest TICKER Tier-1 trong prefix | không · có (+8.116 token)   | recall nhóm`COM`, hit ratio                                                                |
| Few-shot                          | 3 · 5 ví dụ                 | DoD, token ra/bài                                                                            |
| Fan-out                           | warm-up trước · không      | hit ratio của wave                                                                           |

Mẫu chuẩn: 200 bài gán tay, đủ 11 nhóm. Chỉ số quan trọng nhất ở batch 100 là **recall có giảm ở bài thứ 60–100 không** — phép đo trực tiếp cho lo ngại suy giảm nhận thức.

---

## 14. Anti-scope

- Không dùng code hay regex để **quyết định** thực thể hay tóm tắt; chỉ so khớp, tra cứu, bung chỉ số, đo.
- Không model ngoài họ flash. Không model local, không NER.
- Không đổi `l1-entity-output-v1`, `agent-output-v2-lean`, `check_l1_dod`, schema `monocle.db` — trừ bảng `token_ledger` mới, cột `intent_source`, và ba cột Intent **nối thêm vào cuối** `FINAL_COLUMNS` (§2.2, thay đổi cộng thêm nên không phá người tiêu thụ hiện tại).
- Không chạm `raw_html` (WORM).
- **Không dựng lại cổng hỏi người dưới bất kỳ tên nào.** Số đo để nhìn, không để chặn (Q4).
- Không xây bundle `@news-scape/dsh-harness`. Ưu tiên cấu hình plugin DSH có sẵn.
- Không dùng `headless`, `sdk`, `sdk-minimal` trong phạm vi này (Q1).
- Không "continue" hay multi-turn để vượt trần output.
- **Không mở vòng audit mới khi chưa có một vòng thực thi xen giữa.**

---

## 15. Tài liệu cần đồng bộ

| Đích                                                | Việc                                                                                                                                                                                                                                                                                                                                                      |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/decisions/0009`                               | §2.2`maxDepth` 0 → **1**; §2.5 `maxParallelSubCalls` cấu hình thật hoặc gỡ; §2.3 ghi chú route pro→flash                                                                                                                                                                                                                              |
| `docs/decisions/0008`                               | Amendment**bỏ cổng xác nhận** (Q4), **giữ nguyên** §2.4 "thất bại phải ồn ào"                                                                                                                                                                                                                                                      |
| `docs/decisions/0005`                               | Ghi chú: với Q2 = 100%`full`, **lý do chi phí** của subscriber-gating hết hiệu lực (mọi bài đều phân tích sâu). **Vai trò định tuyến giao hàng giữ nguyên** — vẫn quyết định bài nào vào Excel của user nào                                                                                                  |
| `docs/proposals/dsh-surface-verified-2026-09-18.md` | **MỚI, làm ở bước 0.** Trích §6 của plan 1624 (bản đồ DSH kèm file:line) ra khỏi thư mục `plans/`. Lý do: `plans/` là nơi bị dọn dẹp định kỳ, mà bản đồ này là **tài sản kỹ thuật tĩnh** cần sống lâu hơn mọi plan — nó là thứ duy nhất cho phép đối chiếu lại khi DSH nâng phiên bản |
| `project/src/export/user_output.py`                 | Nối`intent_llm`, `intent_code`, `intent_source` vào **cuối** `FINAL_COLUMNS` (§2.2). Thay đổi cộng thêm, Cấp 2, không cần ADR                                                                                                                                                                                                     |
| `.agents/dsh/presets/.../agent.cordis.yml`          | `maxDepth` 0→1; sửa comment sai về `allow`+`ptc`; thêm row `agent_article`                                                                                                                                                                                                                                                                     |
| `.agents/dsh/presets/.../preset.yml`                | Mô tả đúng (hiện ghi "read-only, không spawn agent" nhưng file kia định nghĩa 2 subagent + PTC)                                                                                                                                                                                                                                                  |
| `.agents/rules/05`                                  | §4.4 gỡ`--dangerously-skip-permissions` (trái ADR 0008); §4 gỡ định mức 1.770/bài, "≤100.000 token/phút", trần ngày 350.000 — đều vô nguồn hoặc đã bị số đo bác bỏ                                                                                                                                                             |
| `.agents/rules/08`                                  | Bổ sung: cấm read-back tệp vừa ghi · cấm đọc mã nguồn để suy ra hợp đồng · cấm dùng LLM làm việc script làm được                                                                                                                                                                                                                   |
| `.agents/rules/01`                                  | Cập nhật 2-I/O cho mô hình worker không tool                                                                                                                                                                                                                                                                                                          |
| `.agents/registry.yaml`                             | Thêm`article-processor`; `l1-entity-matcher` và `gold-financial-analyst` → `deprecated` ở bước 6; **gỡ `tokens_per_item` bịa**, trỏ ledger                                                                                                                                                                                        |
| `.agents/pipeline.yaml`                             | Stage`article_pack` · `article_analyze` · `article_expand` → `l1_ingest` + `gold_ingest`                                                                                                                                                                                                                                                      |
| `.agents/skills/l1-entity-matcher`                  | §6 bảng tra**sinh tự động**, bổ sung tiền tố `IND_GICS*`                                                                                                                                                                                                                                                                                   |
| `.agents/skills/token-auditor`                      | Gỡ định mức 450 và 1.470 — sai 21–41 lần                                                                                                                                                                                                                                                                                                           |
| `docs/TOKEN_ECONOMY.md`                             | **MỚI** — §8 của tài liệu này                                                                                                                                                                                                                                                                                                                 |
| `project/scripts/pipeline_radar.py`                 | In context pressure, cửa sổ giá,`resolve_rate`; gỡ hằng số 450                                                                                                                                                                                                                                                                                     |
| `AGENTS.md`                                         | Thêm mục "Kinh tế Token & Phân làn công việc" trỏ`docs/TOKEN_ECONOMY.md`; sửa §6A/§6B cho mô hình một agent                                                                                                                                                                                                                                |
| `docs/SESSION-LATEST.md`                            | Ghi tài liệu này là điểm vào của đợt cải tiến                                                                                                                                                                                                                                                                                                  |

---

## 16. Ngân sách dự kiến và van xả khi quá tải

### 16.1 Chi phí ở chế độ 100% `full`

Giả định ~1.220 token/bài (850 vào + 300 ra + ~70 prefix phân bổ).

| Khối lượng                  | Quota-equivalent/ngày | USD off-peak | USD peak |
| ------------------------------ | ---------------------: | -----------: | -------: |
| 307 bài (mức hiện tại)     |               ~375.000 |        ~0,10 |    ~0,19 |
| 500 bài                       |               ~610.000 |        ~0,16 |    ~0,31 |
| 1.000 bài                     |             ~1.220.000 |        ~0,31 |    ~0,62 |
| Backlog 2.118 bài (một lần) |             ~2.580.000 |        ~0,65 |    ~1,31 |

Tiền không phải ràng buộc. Ràng buộc thật là **quota token của tài khoản** nếu có, nên ledger ghi **cả hai thước** và mọi báo cáo phải nói rõ đang dùng thước nào.

### 16.2 Van xả khi khối lượng vượt ngân sách

Vì đã bỏ chế độ `lite`, khi một ngày có đột biến khối lượng thì cần gạt **không còn là giảm độ sâu**. Thứ tự dùng van, từ nhẹ tới nặng:

1. **Siết distillation** — hạ trần token/bài trong §6.3. Mọi bài vẫn `full`, chỉ mang ít đoạn hơn. Đây là van chính và nên dùng trước.
2. **Dời Tier 2–3 sang cửa sổ off-peak** hoặc sang hôm sau. Tier 1 vẫn chạy đúng hạn.
3. **Giảm kích thước batch** nếu vấn đề là chất lượng chứ không phải chi phí.

Chế độ `lite` được **giữ trong dự trữ, không triển khai** theo Q2. Nếu về sau khối lượng tăng tới mức ba van trên không đủ, nó là phương án dự phòng đã có sẵn thiết kế trong hồ sơ audit.

**Đã cân nhắc và loại: cờ `--depth auto` cho chiến dịch backlog.** Đề xuất này nhằm dùng `lite` để dọn 2.118 bài tồn đọng cho rẻ. Nhưng số thật không ủng hộ: toàn bộ backlog ở chế độ `full` tốn **~2,58 triệu token, tức khoảng 0,65 USD off-peak, chạy một lần**. Không có lý do kinh tế nào để đánh đổi chất lượng lấy khoản đó. Thêm một nhánh mã không bao giờ dùng tới là chi phí bảo trì thuần tuý, lại tạo đúng loại đường rẽ mà các bản plan trước đã mắc: một chế độ được khai báo nhưng chưa bao giờ chạy, rồi trôi lệch khỏi nhánh chính. Backlog chạy `full` như mọi bài khác.

---

## 17. Nghiệm thu chung

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest tests/ -q
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token
```

Mỗi bước trả đủ **Unit + Integration + Platform**. Bước 0 có bằng chứng delegation chạy được và `rules/05` không còn cờ bị ADR 0008 cấm. Bước 2 có số token thật. Bước 4 có bằng chứng round-trip expander và citations kiểm được.

---

## 13. Đính chính 2026-09-21 — ràng buộc thật nằm ở đầu ra, không ở ngữ cảnh

Chỉ đạo: đóng gói 100 bài mỗi đợt, bỏ giới hạn token thực thi, một lượt điều phối cho trọn 100 bài thay vì chia lô 10 bài.

### 13.1 Số đo

| Đại lượng                      | Nguồn                                | Giá trị                           |
| ---------------------------------- | ------------------------------------- | ----------------------------------- |
| Bản ghi L1                        | 400 hàng`l1_outputs` mới nhất    | 872 ký tự ≈ 291 token, p90 370   |
| Bản ghi Gold                      | 400 hàng`agent_outputs` mới nhất | 1.946 ký tự ≈ 649 token, p90 859 |
| Bản ghi hợp nhất                | cộng hai phần trên                 | ≈ 900 token/bài, p90 ≈ 1.200     |
| Đầu vào một lượt 100 bài    | `article_pack`                      | ≈ 89K token, tức 12% cửa sổ     |
| Đầu ra cần cho 100 bài         | 100 × 900                            | ≈ 90K token                        |
| Trần đầu ra một lượt         | `maxTokens` trong preset            | 40K                                 |
| Lượt gọi thật đã chạm trần | 75 tệp nhật ký phiên DSH          | có, đúng 40.000                  |

### 13.2 Kết luận

Ngữ cảnh chưa bao giờ là ràng buộc. Trần ngữ cảnh 25% tương đương 250K token, mà một lượt trăm bài chỉ dùng 115K, nên chốt ấy chưa từng kích hoạt và không bảo vệ gì. Thứ thật sự cắt cụt kết quả là **trần token đầu ra**, và nó là giới hạn của nhà cung cấp chứ không phải chính sách của dự án — sửa cấu hình dự án không mở được nó.

Một lượt hoàn thành duy nhất chở trọn 100 bài là **không khả thi** ở cỡ bản ghi hiện tại: cần 90K trên trần 40K, tức mất trắng khoảng 56 bài cuối. Ép cho vừa thì phải cắt bản ghi xuống dưới 400 token/bài, tức bỏ hơn một nửa phần phân tích nội dung — trái với nguyên tắc LLM xử lý nội dung.

### 13.3 Thay đổi đã áp dụng

Tách **đợt** khỏi **lượt gọi**. Đợt là đơn vị người vận hành quản lý, đặt 100 bài. Lượt gọi là đơn vị nhà cung cấp áp trần, `article_pack.plan_calls` tự tính và chia đều. Một đợt 100 bài thành 4 lượt 25 bài, cả 4 chạy song song **trong cùng một lệnh `run_code`**.

Điều này giữ đúng cả ba yêu cầu: đóng gói 100 bài mỗi đợt, không còn lô 10 bài, và một bước điều phối cho trọn đợt. Chi phí phiên điều phối tỉ lệ với số bước chứ không tỉ lệ với số lượt, nên chia lượt không làm đắt thêm.

Ba hằng số sai đã sửa: dự toán đầu ra 300 → 900 token/bài; ngưỡng cảnh báo sổ cái 1.500 → 2.500 token/bài (mức bình thường đo được là 1.980); chú thích `maxTokens` trong preset.

### 13.4 Hai đường duy nhất để giảm số lượt

Nâng `maxTokens` nếu nhà cung cấp thật sự phục vụ mức cao hơn 40K — phải thử thật rồi sửa đồng thời `MAX_COMPLETION_TOKENS`. Hoặc làm bản ghi nhẹ đi, đổi lấy độ sâu phân tích. Không có đường thứ ba.

### 13.5 Lỗ hổng khung làm việc đã vá

Vệt ngày 21/09 tốn sáu bước mô hình để dò ra `users/output` nằm ở gốc kho chứ không trong `project/`: đọc `write_user_output.py`, grep `user_output.py`, grep `compile.py`, thử một đường dẫn sai, rồi hai lần liệt kê đệ quy. Đúng loại "khảo cổ hợp đồng" mà rule 08 §4 cấm.

Nguyên nhân gốc không phải agent làm sai mà là **luật không thi hành được**: rule bảo "hợp đồng nào cũng có lệnh in ra", nhưng hợp đồng này thì không có. Đã thêm `write_user_output.py --where`, và đường chạy thường cũng in thư mục đã ghi.

Bài học chung cho khung: mỗi lần cấm agent đi dò một thứ, phải đồng thời cung cấp lệnh 0 token trả lời đúng thứ đó. Cấm mà không cấp thì luật chỉ là lời khuyên.

---

## 14. Đo toàn bộ quá trình làm việc của agent — 69 phiên DSH có số đo

### 14.1 Chi phí theo số bước

Gộp 69 tệp nhật ký phiên có số đo, tính trung bình mỗi phiên:

| Số bước | Số phiên |    miss |        hit |     out | **quota/phiên** |
| ---------: | ---------: | ------: | ---------: | ------: | ---------------------: |
|          1 |         36 |  16.916 |     11.481 |   6.428 |       **34.825** |
|       2–3 |          4 |  13.569 |     26.816 |   4.182 |       **44.567** |
|       4–7 |          8 |  20.249 |    151.856 |  12.064 |      **184.169** |
|      8–15 |          5 |  19.896 |    265.574 |  12.442 |      **297.912** |
|     16–63 |         11 |  65.959 |  1.696.244 |  23.561 |    **1.785.764** |
|        64+ |          5 | 369.273 | 25.615.053 | 123.148 |   **26.107.475** |

Từ một bước lên trên sáu mươi bước, chi phí tăng **750 lần**. Phần `miss` chỉ tăng 22 lần, còn `hit` tăng 2.231 lần — nghĩa là gần như toàn bộ mức tăng là **lịch sử cũ được gửi lại**. Rẻ trên mỗi token nhưng khổng lồ về khối lượng, và hạn mức tài khoản tính theo khối lượng chứ không theo tiền.

### 14.2 Tầng nào đang đốt

Đợt ngày 18/09 lúc 18:14–18:23, đọc từ nhật ký:

| Tầng               | Phiên | Bước mỗi phiên |               Quota |
| ------------------- | -----: | -----------------: | ------------------: |
| Worker xử lý bài |     13 |                  1 |   **413.932** |
| Điều phối        |      1 |                 53 | **2.786.828** |

Phiên điều phối tốn **gấp 6,7 lần toàn bộ công việc thật cộng lại**, và 97% của nó là `hit` — tức lịch sử gửi lại qua 53 bước.

Kết luận định hướng: **tầng worker đã đạt.** Mỗi con chạy đúng một bước, `reasoning` bằng 0, và từ con thứ mười trở đi `miss` chỉ còn khoảng 180 token vì bộ nhớ đệm đã ấm. Không còn gì đáng tối ưu ở đó. Toàn bộ dư địa cải thiện nằm ở **số bước của phiên điều phối**, và đó là nơi duy nhất nên đầu tư công sức thiết kế.

### 14.3 Ba luật rút ra cho khung làm việc

1. **Đếm bước, đừng đếm bài.** Mọi quyết định thiết kế nên hỏi "việc này thêm mấy bước", không hỏi "việc này thêm mấy bài". Một đợt phải nằm trong ba bước: chuẩn bị, chạy, hoàn tất.
2. **Cấm điều gì thì phải cấp lệnh thay thế.** Xem §13.5. Luật không thi hành được thì không phải luật.
3. **Song song hoá trong một bước là miễn phí; nối tiếp qua nhiều bước thì không.** Bốn lượt gọi trong một `run_code` có chi phí điều phối bằng một lượt. Cùng bốn lượt ấy tách thành bốn bước thì phiên điều phối nhảy từ mức 35 nghìn lên mức 184 nghìn.

### 14.4 Một điểm cần bạn xác nhận

Bốn phiên worker cuối (18:18–18:19) có `miss` chỉ 146–195 token trong khi `hit` khoảng 25.8 nghìn, tức gần như toàn bộ prompt đã nằm trong bộ nhớ đệm. Với packet nội dung khác nhau thì điều này không xảy ra được. Nhiều khả năng đó là **chạy lại đúng những packet đã gửi**. Nếu đúng thì có một vòng lặp chạy lại ở đâu đó đáng tìm; nếu là chủ ý thì bỏ qua.

---

## 15. Hai lỗi thật tìm thấy khi soi đợt W1 và W2

### 15.1 Đợt W1, W2 đã chạm trần đầu ra và bị chữa cháy bằng cách chia 10

Manifest thật: `W1` 100 bài trong **một** lô, `W2` 200 bài trong **hai** lô 100. Dự toán đầu ra ghi 30.000 token cho 100 bài — theo hằng số cũ 300 token/bài, tức hụt ba lần.

Trên đĩa lại có 30 tệp `article_W*_*_cNN.output.json`, mỗi tệp đúng **10 bản ghi**. Nghĩa là phía điều phối đã không chạy nổi lô 100 bài trong một lượt và tự chia thành mười lượt mười bài. Đây chính là "chia lô 10 bài" mà người dùng nêu, và nó **không phải chính sách của dự án** mà là phản ứng với trần đầu ra.

Bản vá ở §13.3 chuẩn hoá đúng cách chữa cháy ấy: chia theo ngân sách đầu ra đo được, ra 4 lượt 25 bài thay vì 10 lượt 10 bài, và cả 4 nằm trong một bước thay vì mười lần gọi rời rạc.

### 15.2 Chương trình điều phối ghi nhầm lớp vỏ kết quả công cụ ra đĩa

Công cụ gọi agent của DSH trả về `{"kind":...,"runId":...,"output":[{"type":"text","text":"..."}]}`. Chuỗi bóc văn bản trong `conductor_program` chỉ thử `res.text` rồi `res.content`, cả hai đều không có ở tầng ngoài, nên nó rơi xuống `JSON.stringify(res)` và ghi **nguyên lớp vỏ** ra tệp.

Hậu quả đo được: `salvage_records` đọc mỗi tệp `_cNN` thành **đúng một bản ghi rác** hai trường `type` và `text`, thay vì 10 bản ghi thật. Cả lô coi như mất. Các tệp ấy thoát nạn vì không có packet và bảng ánh xạ đi kèm nên bị bỏ qua, nhưng nếu lớp vỏ xuất hiện ở tệp lô chính thì mất trắng cả lô mà vẫn báo "0 hỏng".

Đã vá hai đầu. `conductor_program` bóc `res.output[*].text` trước; `salvage_records` gọi `unwrap_tool_envelope` nên các tệp đã nằm trên đĩa cũng đọc lại được — kiểm chứng: 10 tệp `_cNN` của W1 giờ ra đúng 100 bản ghi, khớp với tệp lô đã gộp.

30 tệp `_cNN` còn lại là sản phẩm trung gian dư của W1 và W2. Chúng bị `article_expand` bỏ qua vì thiếu packet, nên vô hại; chỉ gây 30 dòng cảnh báo mỗi lần chạy `--finish`. Xoá hay giữ là quyết định của người vận hành.

---

## 16. Gỡ toàn bộ cổng chặn 2026-09-21

Chỉ đạo: xử lý dứt điểm mọi cổng làm agent bị chặn hoặc dừng, không tối ưu ở nhịp vận hành trước.

### 16.1 Bốn cổng đã gỡ

| Cổng                                                 | Nó làm gì                               | Vì sao gỡ                                                                                                                                                                                                            |
| ----------------------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `maxTokens: 40000` ở row `tool-subagent-article` | Cắt đầu ra mỗi lượt                  | Trần**do dự án tự đặt**, không phải trần nhà cung cấp. Chính nó buộc điều phối chữa cháy bằng mười lượt mười bài ở W1 và W2. Hai row `agent_l1`, `agent_gold` vốn không đặt |
| Bộ chia theo ngân sách đầu ra`plan_calls`      | Chia đợt 100 bài thành 4 lượt 25     | Lấy một trần**chưa đo** làm luật kiến trúc                                                                                                                                                              |
| Trần ngữ cảnh 25% tự chia đôi lô               | Chia lô khi ước tính vượt 250K token | Chưa bao giờ kích hoạt. Đọc trọn nội dung thì trăm bài mới chiếm 25%, vẫn không chạm                                                                                                                   |
| Trần chắt lọc 900 token/bài                       | Bỏ nội dung trước khi mô hình đọc  | Xem §16.2                                                                                                                                                                                                             |

Sau khi gỡ, `--batch` là cổng chia lô duy nhất.

### 16.2 Cổng nặng nhất: chắt lọc nội dung

Đo trên 600 bài thật:

|                                              |                                   |
| -------------------------------------------- | --------------------------------- |
| Token nội dung sau bộ lọc cơ học        | 1.542/bài (p90 2.537, p99 4.427) |
| Token thực gửi cho mô hình khi trần 900 | 838/bài                          |
| **Nội dung mô hình được đọc**  | **54%**                     |

Trần 900 được đặt để tiết kiệm token đầu vào. Chính số đo của dự án đã bác bỏ lý do ấy: đọc trọn nội dung thì một đợt trăm bài dùng 154K token đầu vào, tức 25% cửa sổ một triệu, và token đầu vào chưa cache rẻ hơn token đầu ra **năm mươi lần**. Đổi lại nó bỏ mất **46% nội dung nghiệp vụ** trước khi mô hình kịp đọc — tức code đang quyết định mô hình được đọc gì.

`DEFAULT_MAX_TOKENS_PER_ARTICLE` nay để **0**, nghĩa là không cắt. Tham số `--max-tokens-per-article` vẫn còn để dùng tay.

### 16.3 Đoạn quá dài: tách thay vì bỏ

`MAX_PARAGRAPH_CHARS = 1800` phục vụ trần cắt dòng 2.000 ký tự của công cụ đọc, nên phải giữ. Nhưng trước đây chạm trần thì **bỏ nguyên đoạn**. Đo lại trên 14.199 dòng thật: đúng một dòng vượt ngưỡng, dài nhất 2.059 ký tự — hiếm nhưng có thật, và bỏ một đoạn dài là mất đúng phần thường mang nhiều thông tin nhất.

Nay tách tại ranh giới câu. Mỗi mảnh vẫn là chuỗi con nguyên văn nên bất biến nguyên văn được giữ, mà không mất chữ nào.

### 16.4 Cơ chế thay thế: vá sau, không phòng trước

`article_run.py --wave <mã> --repair` đối chiếu số bản ghi nhận được với số bài đã gửi, tìm ra **đúng những chỉ số còn thiếu**, đóng gói lại chỉ phần ấy với chỉ số đánh lại từ 0, rồi sinh `wave_<mã>.repair.ts`. Không cần cơ sở dữ liệu vì nội dung bài đã nằm trong packet gốc, nên đường này cũng tiêu 0 token.

Kinh tế của nó: nhà cung cấp phục vụ trọn lô thì tốn **0 đồng thừa**; cắt ở bài 60 thì chạy lại 40 bài. Cách chia trước tốn 4 lượt ở **mọi** đợt, kể cả khi không cần. Chia trước chỉ thắng khi tỷ lệ cắt cụt gần 100%, mà điều đó chưa ai đo.

### 16.5 Cổng giữ nguyên

Ba cổng sau không phải để tối ưu mà để hỏng thì phải ồn, theo ADR 0008 §2.4 — điều khoản duy nhất còn hiệu lực của ADR ấy:

Prefix lệch danh mục thì dừng đợt. Tỷ lệ hỏng vượt 10% thì dừng trước khi nạp cơ sở dữ liệu. Lệnh con trả mã khác 0 thì dừng cả đợt. Cả ba đều tự động và không hỏi ai.

Bốn luật loại bản ghi Gold (thiếu tóm tắt, hàm ý dưới 40 ký tự, thiếu luận điểm, dưới hai trích dẫn) cũng giữ: đo trên 300 bài của W1 và W2, **không luật nào kích hoạt**, nên chúng không phải là cổng chặn trên thực tế.

### 16.6 Số đo trước và sau

|                                   | Trước | Sau                       |
| --------------------------------- | ------- | ------------------------- |
| Lượt gọi cho đợt 100 bài    | 4       | **1**               |
| Nội dung mô hình được đọc | 54%     | **100%**            |
| Token đầu vào mỗi đợt       | 82K     | 154K (25% cửa sổ)       |
| Cổng chia lô                    | 4       | **1** (`--batch`) |

### 16.7 Đính chính: trần thật là 256.000, và nó đã nằm sẵn trong tài liệu của dự án

Tôi từng gọi 40.000 là "trần vật lý của nhà cung cấp". Sai. Đó là giá trị **dự án tự đặt** ở `maxTokens` trong preset. Bằng chứng bác bỏ nằm ngay trong `docs/proposals/dsh-surface-verified-2026-09-18.md`, viết ngày 18/09 từ việc đọc mã nguồn DSH:

> `maxTokens` mặc định — **256.000** (`DEFAULT_MAX_TOKENS = 256e3`); con kế thừa của cha
> — `dsh-llm-deepseek:1394,1998`; `dsh-subagent/lib/types/child-agent.js:79-92`
>
> U3 · `maxTokens` mặc định? · **256.000**, không phải 8K

Cùng tài liệu, mục Budget: DSH **không có** trần token hay chi phí theo phiên hay theo ngày. Các giới hạn số duy nhất là `maxTokens` 256.000 mỗi request, `contextWindow` 1.000.000, compaction 0,8×, pruner 8.192 ký tự, spill 50.000 byte.

Nghĩa là gỡ `maxTokens` khỏi row không để nó vô hạn mà trả nó về **256.000**. Một đợt trăm bài cần khoảng 90.000 token đầu ra, còn dư gần ba lần. Bài học phương pháp: trước khi gọi một con số là ràng buộc, kiểm xem chính mình có đặt ra nó không.

---

## 17. Bộ nhớ đệm 2026-09-21 — đo lại, và xếp lại thứ tự ưu tiên

### 17.1 Cache ở hệ này là bảo hiểm, không phải cần gạt tiết kiệm

Phân rã hoá đơn thật từ sổ cái, tính bằng khung giá của chính dòng sổ cái đó:

| Đợt          | miss           | hit             | out            | Tổng   |
| -------------- | -------------- | --------------- | -------------- | ------- |
| W1 — 100 bài | $0,0487 · 43% | $0,0022 · 1,9% | $0,0634 · 55% | $0,1142 |
| W2 — 200 bài | $0,0541 · 34% | $0,0052 · 3,3% | $0,0976 · 62% | $0,1568 |

Hai cách đọc, cả hai đều đúng, và bỏ một cái là kết luận sai:

- **Cache đang cứu rất nhiều tiền.** W2 có 1,72 triệu token cache-read vì `turns_max = 2`. Không có cache, số đó bị tính giá miss: hoá đơn thành **$0,410 thay vì $0,157**, tức cache cắt **62%**.
- **Phần cache *cố ý* — tiền tố tĩnh — chỉ đáng 1,4%.** Ở 100 bài/lô, đợt 300 bài: có cache $0,23312, không cache $0,23639.

|      bài/lô | số lô | có cache | không cache |    tiết kiệm |
| ------------: | ------: | --------: | -----------: | -------------: |
|            10 |      30 |  $0,23402 |     $0,28134 |          16,8% |
|            25 |      12 |  $0,23342 |     $0,25137 |           7,1% |
|            50 |       6 |  $0,23322 |     $0,24138 |           3,4% |
| **100** |       3 |  $0,23312 |     $0,23639 | **1,4%** |
|           150 |       2 |  $0,23309 |     $0,23472 |           0,7% |

Kết luận: tiền tố tĩnh gần như vô hiệu khi mọi thứ chạy đúng thiết kế (1 bước/lô, lô to), và cứu 62% khi có lô đi hai bước hoặc phải chạy lại. Đo cache bằng câu hỏi "tiết kiệm bao nhiêu phần trăm" sẽ ra kết luận sai ở cả hai chiều.

**Thứ tự đòn bẩy thật:** đầu ra (55–62% hoá đơn) → khung giá thấp điểm (−50% mọi rổ, đợt 300 bài $0,233 so với $0,466) → số bước → tiền tố tĩnh.

### 17.2 Vì sao công thức cache phổ biến không áp được thẳng vào đây

| Giả định thường gặp                         | Ở hệ này                                                                                                                                           |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| cache-read ≈ 0,1× input                         | **0,02×** (0,003 so với 0,15)                                                                                                                 |
| phần lặp`C` lớn hơn phần mới `N`        | ngược lại:`C` ≈ 11.143, `N` ≈ 154.200 cho lô 100 bài                                                                                       |
| chi phí nằm ở lịch sử hội thoại            | worker one-shot, không có transcript                                                                                                                |
| cần đẩy phần biến động xuống cuối prompt | DSH đã thế sẵn: runtime context là**user message nối sau packet** (`dsh-agent-loop:890-906`), `dsh-time-context` không được mount |

### 17.3 Đã sửa trong kho mã

| Việc                                                                                                 | Ở đâu                                             | Vì sao                                                                                                                                                                                                                                                                                               |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--check` kiểm cả **persona trong preset ↔ tệp prefix**, thêm `--check-preset`         | `build_article_prefix.py`, `src/agent/prefix.py` | Thứ bắt buộc byte-identical lại là thứ duy nhất chưa ai kiểm. Đã đo ngày 21/09: hiện đang khớp                                                                                                                                                                                        |
| Hâm cache bằng request tí hon thay vì bắt lô đầu chạy một mình; đợt một lô không hâm | `article_run.py`                                   | Đổi được thời gian chạy đợt, không đổi tiền. Một lô thì hâm là lỗ ròng                                                                                                                                                                                                            |
| Dự toán tiền tố gồm cả phần harness (+4.800 token)                                             | `article_pack.py`, `src/agent/prefix.py`         | `est_hit` cũ hụt 4.800 token/lượt nên không đối chiếu được với `cacheRead` thật                                                                                                                                                                                                     |
| Thứ tự bài tất định (`ORDER BY published_at DESC, url_title_hash`) + băm packet              | `article_pack.py`                                  | Điều kiện để lần đóng gói lại cho ra packet giống hệt và trúng cache                                                                                                                                                                                                                    |
| Sàn`hit ≥ tiền tố × (số phiên − 1)`, cảnh báo kèm số tiền trả thừa                   | `token_ledger.py`                                  | Tỷ lệ trúng cache gộp**không** phát hiện được tiền tố trượt: nó vẫn cao khi các lượt lặp bước                                                                                                                                                                             |
| `radar token` đọc sổ cái và checkpoint phiên thật                                            | `pipeline_radar.py`                                | Bản cũ nhân số bài với định mức chết 450/1.470 rồi nhân đơn giá gõ trong mã, không biết cache tồn tại — radar và sổ cái nói hai con số khác nhau cho cùng một đợt                                                                                                     |
| Biến thể`--with-tickers` (+21.500 token, +1,5% hoá đơn đợt 300 bài)                         | `build_article_prefix.py`                          | Cache biến prefix thành**ngân sách tri thức**; biến thể ghi vào tệp mô tả nên `--check` không báo lệch oan                                                                                                                                                                     |
| `est_hit` trình bày như **sàn**, không như dự báo                                     | `estimate_wave.py`                                 | Cột lệch cũ in "+13.486%" cho một tình huống hoàn toàn lành mạnh: số thật vượt sàn là lúc cache đang gánh thay giá token mới                                                                                                                                                     |
| `--repair` phân biệt "chưa lô nào chạy" với "không thiếu bài"                             | `article_run.py`                                   | `missing_indices` coi lô chưa có tệp đầu ra là không thiếu gì, nên đợt chưa chạy lần nào vẫn nhận được câu "không cần vá"                                                                                                                                                 |
| Sàn cache đếm theo**lượt gọi worker**, không theo số phiên                             | `token_ledger.py`, `pipeline_radar.py`           | Phiên Conductor mang persona khác nên không đọc tiền tố của worker. Đếm nó vào sàn làm đợt hai lô bị đòi`11.143 × 3` trong khi chỉ hai lô đọc lại — cảnh báo kêu oan ở **mọi** đợt bình thường, và một cảnh báo luôn kêu thì hết là tín hiệu |
| Radar đổi ngày máy thành khoảng UTC trước khi tra sổ cái                                    | `pipeline_radar.py`                                | Sổ cái ghi`ts` theo UTC, radar lọc theo ngày của đồng hồ máy: lệch đúng bảy tiếng, nên mọi đợt chạy trước 07:00 giờ VN bị báo "chưa có dòng nào" cho chính ngày vừa chạy                                                                                            |

Tám bất biến mới được canh bằng kiểm định trong `tests/test_article_lane.py`.

### 17.4 Còn lại là việc tay trong DSH

Xem `.agents/dsh/DSH-VIEC-THU-CONG.md`. Mười mục, trong đó bốn mục bắt buộc: dán persona và xác nhận bằng `--check-preset`, chọn đúng preset mỗi phiên, nạp lại DSH sau khi sửa preset, và không đổi tool set/model/effort giữa đợt.

Một mục cố ý **không tự sửa**: `compaction auto: false` theo §8.4. Con dùng chung composition với cha nên tắt nén là tắt cho cả Conductor, mà worker chạy một bước thì không bao giờ chạm ngưỡng 80%. Lợi ích cache bằng không, cái mất là lưới an toàn duy nhất — khuyến nghị giữ `auto: true`.

### 17.5 Đã cân nhắc và bác bỏ

**Vá bằng cách gửi lại trọn packet gốc kèm chỉ thị ở đuôi.** Vá 8 bài trên 100 hiện tốn ~$0,0019 đầu vào; cách kia tốn ~$0,0005. Tiết kiệm $0,0014, đổi lấy rủi ro mô hình phát lại trọn 100 bản ghi — $0,054 đầu ra, đắt hơn ba mươi lần phần vừa tiết kiệm. Giữ nguyên cách vá hiện tại.
