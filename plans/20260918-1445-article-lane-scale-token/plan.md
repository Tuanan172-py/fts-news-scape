# Plan — Article Lane: xử lý bài đăng bằng LLM ở quy mô lớn, có cơ chế đo và kiểm soát context

|                              |                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ngày                        | 2026-09-18 (rev 3 — Unified Article Processor, Smart Paragraph Distillation, Priority-Queue 100 bài/batch giao sớm cho user, Dual-Track Intent 2 cột) |
| Trạng thái                 | **DRAFT — chờ duyệt** (chưa sửa code/runtime/preset)                                                                                                                                                                                                                                                                                                                                                      |
| Phân loại                  | **Cấp 2 — NORMAL** cho operator + prompt + expander + user_output. **Cấp 3** cho: (a) amendment ADR 0008 bỏ cổng xác nhận, (b) row preset DSH mới, (c) trường `mentions` mới                                                                                                                                                                                                                              |
| Nền tảng                   | ADR 0009 (DSH runtime, D1–D6) · audit vệt L1 845K + Gold 154–300K (§1) · nghiên cứu DeepSeek + DSH đã xác minh (§14) · thảo luận phản biện kiến trúc (2026-09-18)                                                                                                                                                                                                                                                                                                         |
| Thay thế                    | Plan `20260918-1133-l1-llm-lean-token` (Lean Lane L1) — bị plan này bao trùm và sáp nhập toàn bộ                                                                                                                                                                                                                                                                                                                                    |
| Ràng buộc chủ đạo       | **LLM là bộ não nhận diện và tóm tắt.** Code chỉ làm cơ học: đóng gói, tra cứu, mở rộng schema, **đo lường**. Không dùng code thay LLM để nhận diện                                                                                                                                                                                                                           |
| Chỉ đạo & Thống nhất mới (2026-09-18) | ① Bỏ cổng người xác nhận — anh quản theo batch/wave · ② **100 bài/lượt (Mega-batch)** · ③ Cơ chế chống suy giảm nhận thức khi context phình + handoff 0 token · ④ Cơ chế **đo** token burn trong khung harness (đo, **không** phải gate chặn) · ⑤ Nhóm thực thể bám `project/data/entities/` thật · ⑥ Chưa cần KPI/ngân sách mục tiêu · ⑦ **Hợp nhất hoàn toàn L1 & Gold thành 1 Agent duy nhất (`agent_article`)** xử lý trọn vẹn cả tiêu đề (thực thể/intent) lẫn nội dung · ⑧ **Bỏ cắt tỉa cứng $\le 2.200$ ký tự**, thay bằng **Smart Paragraph Distillation** (giữ Sapo, số liệu tài chính %, phát ngôn lãnh đạo; bỏ rác) + citations bằng index `c: [0, 2]` · ⑨ **Hàng đợi Mega-Batch phân tầng ưu tiên (Priority-Queue)**: Code-first đóng gói bài ưu tiên (Watchlist active `manifest.yaml`, vĩ mô khẩn) vào Batch 1 giao ngay cho user; các bài còn lại vẫn xử lý full nhưng xếp hàng đợi sau để phủ 100% database · ⑩ **Nhận diện Intent Độc lập & 2 Cột Output**: Code và LLM nhận diện độc lập, lớp mapping đối soát `BOTH`/`LLM_ONLY`/`CODE_ONLY`; output Excel người dùng có 2 cột riêng biệt `intent_llm` và `intent_code`. |

> **Định vị một câu:** mỗi lượt gọi LLM nhận **một packet 100 bài** (được phân tầng ưu tiên) và trả **một mảng JSON** hợp nhất cả Intent và Nội dung, không đọc file, không ghi file, không tra catalog, không tự chấm DoD — và toàn bộ chi phí của lượt đó **đo được bằng số thật** trước khi chạy và sau khi chạy.

---

## 1. Audit hai vệt thật — L1 845K (25 tiêu đề) và Gold 154–300K (5 bài)

### 1.1 Tái dựng bằng số

Vệt anh đưa: **19 lượt model**, kết thúc ở **845.000 token**. Mô hình tái dựng (đo file thật trong repo, quy đổi 3 ký tự/token tiếng Việt) cho **~990K** — sai số 17%, đủ để kết luận cơ chế.

| Lượt                                               |        Nội dung mới nạp | Input gửi đi (cả history) |           Output | Context sau lượt |
| ---------------------------------------------------- | -------------------------: | ---------------------------: | ---------------: | -----------------: |
| T1 đọc SKILL.md + packet                           |                      7.803 |                       17.924 |              120 |             18.044 |
| T2 9× grep`entities.json`                         |                        520 |                       18.564 |              260 |             18.824 |
| T3–T5 đọc 5 lát`entities.json`                 |                     28.601 |                      106.006 |              400 |             47.826 |
| T6–T9 glob + schema + instructions + sample         |                      3.404 |                      198.364 |              310 |             51.540 |
| T10–T12 grep + đọc`l1_router.py` 4 lần         |                      5.760 |                      165.670 |              340 |             57.640 |
| T13–T14 grep GICS + 4 lát`entities.json`         |                     14.471 |                      131.474 |              310 |             72.421 |
| **T15 đọc lại packet + GHI output 23,5 KB** |                      3.600 |                       76.021 |  **7.950** |             83.971 |
| T16 lỗi`limit > 2000`                             |                        120 |                       84.091 |              200 |             84.291 |
| **T17 đọc lại chính file vừa ghi**        |                      7.800 |                       92.091 |              120 |             92.211 |
| T18 send_message                                     |                          0 |                       92.211 |              260 |             92.471 |
| **TỔNG**                                      | **82.202 duy nhất** |            **982.427** | **10.270** |                 — |

**Hệ số lãng phí = 12,1×.** 82K nội dung duy nhất, ~990K bị tính tiền.

### 1.2 Phân bố 82K nội dung *duy nhất*

| Khoản                                                                          |  Token |     % | Có phải "việc" không                         |
| ------------------------------------------------------------------------------- | -----: | ----: | ------------------------------------------------ |
| `entities.json` (9 lát cắt) + 11 grep                                       | 43.593 | 53,0% | **Không** — rule 08 cấm đọc file này |
| Prefix cố định (dsh-system-prompt + AGENTS.md + skill-catalog + tool schema) | 10.121 | 12,3% | Một phần                                       |
| Output JSON ghi ra (**output token**)                                     |  7.800 |  9,5% | **Có**, nhưng ~70% là boilerplate       |
| Output JSON đọc lại để tự kiểm                                           |  7.800 |  9,5% | **Không**                                 |
| Packet 25 bài (đọc**2 lần**)                                          |  7.200 |  8,8% | **Có** một nửa (3.600)                  |
| `l1_router.py` đọc 4 lần (dò `check_l1_dod`, `TYPE_GROUP`)            |  5.760 |  7,0% | **Không**                                 |
| SKILL.md                                                                        |  4.203 |  5,1% | Một phần                                       |
| schema + instructions + sample                                                  |  3.204 |  3,9% | **Không**                                 |

**Việc thật = 3.600 token vào (25 tiêu đề) + ~2.400 token ra (phần quyết định ngữ nghĩa).** Trên 845K bị tính tiền, hiệu suất = **0,7%**.

### 1.3 Mười một lỗi hệ thống rút ra

| # | Lỗi                                                                                                                                           | Bằng chứng trong vệt                                                                                                                |                  Chi phí | Xử lý                                                                    |
| :-: | ---------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------: | -------------------------------------------------------------------------- |
| 1 | **Ranh giới 2-I/O không được cưỡng chế** — con dùng Grep, Glob dù registry khai `tools_allowed: [view_file, write_to_file]` | 11 Grep + 4 Glob                                                                                                                       |       mở cửa cho lỗi#2 | `toolFilter` thật sự có hiệu lực; worker **không tool nào** |
| 2 | **Đọc `entities.json` — file rule 08 cấm tuyệt đối**                                                                            | 9 lát cắt + 11 grep                                                                                                                  |          **43.593** | Catalog nhóm đóng nằm sẵn trong prefix (§4.3)                        |
| 3 | **Bảng tra trong SKILL.md không đủ dùng** — thiếu tiền tố `IND_GICS*` nên agent buộc phải tự dò                          | agent tự ghi:*"industry entity IDs use prefix IND_GICS1:, not INDUSTRY_GICS1"*                                                      | nguyên nhân gốc của#2 | Prefix**sinh tự động từ `entities.json`**, không gõ tay      |
| 4 | **Hợp đồng DoD rải rác và mâu thuẫn** → agent đọc mã nguồn để suy ra luật                                                | đọc`l1_router.py` 4 lần; tự ghi nhận 2 mâu thuẫn (`UNKNOWN` enum; `recognized=false` categories)                          |                     8.964 | LLM**không chấm DoD**; expander + ingest chấm                     |
| 5 | **Agent tự kiểm tra file vừa ghi**                                                                                                    | T17 đọc lại 23,5 KB                                                                                                                 |            7.800 + resend | Cấm read-back; validator ở ngoài                                        |
| 6 | **Output JSON đi qua tool-call argument** = loại token đắt nhất                                                                     | Write 23,5 KB                                                                                                                          |              7.950 output | Trả JSON trong**final message**, không qua tool                    |
| 7 | **Đọc packet 2 lần**                                                                                                                  | T1 và T15                                                                                                                             |                     3.600 | Packet inline trong prompt, không đọc                                   |
| 8 | **Boilerplate chiếm ~70% output**                                                                                                       | 25 × (`categories` 8 khóa + `processing_metadata` + echo `title` + `article_id` 64 ký tự + `citations` lặp `surface`) |             ~5.400 output | Bản ghi gọn (§3.2), expander bù                                        |
| 9 | **19 lượt → resend O(n²)**                                                                                                           | mỗi Think/Code là một lượt                                                                                                        |                     ~900K | **Một lượt duy nhất**                                            |
| 10 | **Một lượt cháy vì lỗi công cụ** (`limit > 2000`)                                                                              | T16                                                                                                                                    |                     8.400 | Không dùng tool ⇒ không có lớp lỗi này                             |
| 11 | **`reasoningEffort: high` bật mặc định** — 11 khối Think tính giá output, chưa ai đo                                         | `settings.yaml` [V §14]                                                                                                             |               chưa biết | `reasoningEffort: off` + đo `reasoningTokens` riêng                  |

### 1.4 Chiếu cùng công việc sang Article Lane

|                            | Vệt 845K (25 tiêu đề) | Article Lane (100 bài,`lite`) | Article Lane (100 bài,`full`) |
| -------------------------- | ------------------------: | -------------------------------: | -------------------------------: |
| Số lượt model           |                        19 |                      **1** |                      **1** |
| Prefix                     |  10.121 × 19 lần resend |                     ~7.000 (hit) |                     ~7.000 (hit) |
| Input mới (miss)          |                    72.081 |                           ~4.500 |                          ~85.000 |
| Output                     |                    10.270 |                           ~3.500 |                          ~30.000 |
| **Quota-equivalent** |        **~990.000** |                **~15.000** |               **~122.000** |
| Token / bài               |                   ~39.600 |                             ~150 |                           ~1.220 |

### 1.5 Vệt Gold thứ hai — 5 bài, 154K–300K token: bệnh khác, cùng một chẩn đoán

Anh đưa vệt Gold hôm qua: **5 bài**, `Usage` báo **154.000 token**, thực tế trung bình các lần chạy **200.000–300.000**. Đây là số **không cần mô hình hóa** — DSH tự báo cáo:

| | Giá trị | Nguồn |
|---|---:|---|
| Token/bài theo UI báo (154K/5) | **30.800** | báo cáo trực tiếp |
| Token/bài theo trung bình thực tế (200–300K/5) | **40.000–60.000** | anh cung cấp |
| `cost_budget.tokens_per_item` của `gold-financial-analyst` trong `registry.yaml` | 1.470 | `.agents/registry.yaml:156` |
| **Lệch so với định mức khai báo** | **21–41 lần** | |

Đếm lượt trong vệt: **21 lượt model cho 5 bài** — tệ hơn L1 (19 lượt cho 25 bài) tính theo lượt/bài. Trong đó **15/21 lượt (71%) là Grep xác minh từng citation một** — mỗi citation một lượt Grep riêng.

**Chuỗi nhân quả, xác minh bằng file thật:**

1. `write_batch_packet` ghi packet bằng `json.dumps(..., indent=2)` — đo trực tiếp trên `data/agent_tasks/archive/20260917/batch_20260917T165007_8fb1_02.task.json`: file pretty-printed, và vì `cleaned_text` là một chuỗi JSON không xuống dòng thật, **mỗi bài trở thành đúng 1 dòng dài 2.173–2.537 ký tự** (~724–845 token/dòng).
2. Dòng đó **vượt trần 2.000 ký tự/dòng của tool Read trong DSH** — đúng như agent tự ghi nhận trong Think: *"The cleaned_text is truncated in the read output at 2000 chars per line"*.
3. Agent không còn tin nội dung mình vừa đọc, nên **không trả kết quả rồi dừng** mà tự đặt ra một vòng kiểm chứng: Grep riêng từng citation (đếm được đúng 15 lệnh Grep = 5 bài × 3 citation/bài — khớp 100% với dữ liệu output thật).
4. Vì cả 3 citation của một bài **luôn nằm trên cùng một dòng `cleaned_text`** (xác minh trực tiếp: đúng cho cả 5/5 bài), mỗi lệnh Grep ở chế độ mặc định trả về **nguyên dòng khớp**, tức là **trả lại gần như toàn bộ nội dung bài đó** (~730–845 token) — không phải một đoạn ngắn 20 ký tự như citation cần kiểm.
5. 15 lượt đó cộng dồn vào lịch sử của mọi lượt sau (đặc tính API multi-turn stateless), nên phần trả lời "Có" 15 lần (~90 token hữu ích) kéo theo hàng trăm nghìn token nội dung bị gửi lại nhiều lần.

Mô hình tích lũy tương tự §1.1 cho ra quota-equivalent 500K–620K tùy giả định — **cao hơn số DSH báo cáo 3–4 lần**, nghĩa là DSH đã có sẵn một lớp giảm tải nào đó (rất có thể là retention/pruning riêng cho kết quả `grep`/`bash` mà nghiên cứu ở §14 có nhắc tới nhưng chưa xác minh chi tiết). Điểm quan trọng: **dù có lớp giảm tải đó, chi phí thật vẫn lệch 21–41 lần** — nghĩa là nguyên nhân gốc không nằm ở cơ chế cache mà nằm ở **cấu trúc lượt gọi**, đúng kết luận đã rút ra từ L1.

**Việc thật của Gold trên 5 bài:** đọc skill (1.652 tok) + đọc packet (6.138 tok, trong đó chỉ 3.727 tok là `cleaned_text` — 61%, còn lại là khung JSON) + viết output (3.211 tok). Cộng **~11.000 token cho việc thật**, so với 154.000–300.000 bị tính — hiệu suất dưới **7%**, còn tệ hơn cả L1 (0,7%) nếu tính trên phần việc, nhưng vì tổng nhỏ hơn nên tỷ lệ phần trăm hiệu suất cao hơn một chút.

| # | Lỗi | Bằng chứng | Xử lý (đã có sẵn trong plan, hoặc bổ sung mới) |
|:-:|---|---|---|
| G1 | **Packet ghi pretty-printed (`indent=2`)** khiến 1 bài = 1 dòng dài, vượt trần đọc của tool | 5/5 dòng `cleaned_text` > 2.000 ký tự, đo trực tiếp | **Mới, bổ sung §3.1/§7**: `article_pack.py` ghi packet dạng **compact JSON** (không indent) — không dòng nào có thể dài bất thường vì đoạn văn đã được tách mảng `p[]` theo từng phần tử, không dồn vào một chuỗi khổng lồ |
| G2 | **Agent tự vòng kiểm chứng citation bằng 15 lượt Grep riêng lẻ** — việc mà một script làm trong 0 token | 15 Grep, khớp đúng 3×5 | **Đã có trong §3.2**: `c` là **chỉ số đoạn**, không phải chuỗi. Expander lấy nguyên văn đoạn theo chỉ số ⇒ citation luôn đúng **bằng xây dựng**, LLM không bao giờ cần verify |
| G3 | **Worker có quyền dùng Grep** dù registry Gold cũng khai `tools_allowed: [view_file, write_to_file]` — cùng lỗi cưỡng chế như L1 (#1 ở §1.3) | 15 Grep xuất hiện dù registry cấm | **Đã có trong §2/§7**: `toolFilter: { allow: [] }` — worker vật lý không có Grep để gọi |
| G4 | **Grep mặc định trả nguyên dòng khớp** khi dòng đó chính là toàn bộ nội dung bài → verify 20 ký tự tốn 730+ token | tính trực tiếp từ độ dài dòng | Hệ quả của G1+G2; hết khi cả hai được xử lý |
| G5 | **21 lượt cho 5 bài** = không thể scale; đúng vấn đề anh nêu "1 lượt nhiều bài hơn, tốn ít token hơn" | đếm trực tiếp | **Đã có trong §2**: 1 lượt/batch, không phụ thuộc số bài trong batch |

**So sánh chiếu sang Article Lane (100 bài `full`, §1.4):** 1 lượt, ~1.220 token/bài — so với Gold hiện tại 30.800–60.000 token/bài là **giảm 25–50 lần**, và khác biệt so với so sánh L1 ở chỗ: phần lớn mức giảm ở đây đến từ việc **triệt tiêu một lớp lỗi mới** (self-verification loop) chứ không chỉ từ gộp lượt.

---

## 2. Kiến trúc đích — Unified Article Processor & Priority-Queue Mega-Batch

```text
[Toàn bộ bài cào trong ngày (100% Raw/Silver)]
   │
   ▼
[Code-First Priority Sorter & Dual-Track Matcher — 0 token]
   ├─ Quét tiêu đề/Sapo: Nhận diện mã CP/Alias theo catalog tĩnh -> lưu {code_entities}
   ├─ Phân tầng hàng đợi ưu tiên:
   │   ├─ TIER 1 (Ưu tiên Cao nhất): Khớp Watchlist active (manifest.yaml) + Vĩ mô khẩn
   │   │   └──> Đóng gói vào BATCH 1 (100 bài đầu tiên)
   │   └─ TIER 2 & 3 (Hàng đợi Nền): VN30, BCTC, tin CBTT hành chính, thị trường chung
   │       └──> Xếp hàng đợi cho BATCH 2..N (100 bài/batch), vẫn xử lý full toàn bộ
   ▼
[article_pack.py — operator, 0 token]
   ├─ Smart Semantic Paragraph Distillation: Bỏ trần 2.200 ký tự; chọn Sapo (p0) + 
   │   đoạn số liệu định lượng (%, tỷ đồng, KQKD) + đoạn trích dẫn lãnh đạo/pháp lý
   ├─ Chỉ số cục bộ i=0..99 (KHÔNG gửi sha256 64 ký tự), các đoạn đánh số [p0..pk]
   ├─ Xuất packet compact JSON + map i->article_id trên đĩa
   └─ In dự toán: est_prefix / est_miss / est_out / est_ctx_peak
   ▼
[agent_article — DSH subagent, deepseek-flash, KHÔNG tool, MỘT lượt, thinking OFF]
   prefix tĩnh (cache hit ~85%): ARTICLE_SYSTEM_CORE + catalog nhóm đóng 130 ID ~7K
   đuôi động: packet 100 bài (được phân tầng ưu tiên)
   final message: mảng JSON Article Record gọn (gồm cả Intent/Entities và Nội dung)
   ▼
[article_expand.py — operator, 0 token]
   ├─ Parser salvage từng item (item hỏng -> requeue item đó)
   ├─ Dual-Track Reconciliation: So khớp {llm_entities} vs {code_entities}
   │   └──> Gán nhãn: BOTH / LLM_ONLY / CODE_ONLY
   ├─ Citations by Index: c: [0, 2] -> lấy nguyên văn đoạn p0, p2 -> DoD 100% exact substring
   ├─ Map i -> article_id · surface+nhóm -> entity_id
   └─ Sinh l1-entity-output-v1 + agent-output-v2-lean chuẩn
   ▼
[Ingest & Giao hàng Phân tầng]
   ├─ BATCH 1 XONG: Kích hoạt ngay [write_user_output.py] -> Giao Excel 2 cột Intent cho User
   └─ BATCH 2..N XONG: Nạp SQLite [monocle.db], hoàn tất 100% độ phủ kho dữ liệu
   ▼
[token_ledger.py — operator, 0 token]
   Ghi nhận số đo thật: hit/miss/out/reasoning/ctx -> bảng token_ledger -> pipeline_radar
```

**Bất biến kiến trúc thống nhất:** 
1. Không còn phân biệt L1 vs GOLD; chỉ một Agent duy nhất xử lý trọn vẹn từ tiêu đề đến nội dung.
2. LLM không đọc file, không ghi file, không tra catalog, không tự chấm DoD. Nhận 1 packet 100 bài và trả 1 mảng JSON trong 1 lượt duy nhất.
3. Code-first đảm bảo: Bài ưu tiên của User được phục vụ ngay ở Batch 1; các bài còn lại vẫn được phân tích full 100% trong các batch nối tiếp.

---

## 3. Hợp đồng dữ liệu

### 3.1 Article Packet (input) — Smart Semantic Paragraph Distillation

Bỏ trần cắt tỉa cơ học `$\le 2.200$` ký tự cũ. Thay bằng **Smart Semantic Paragraph Distillation** chắt lọc các đoạn văn bản giá trị cao:
- `p0`: Bắt buộc giữ đoạn Sapo mở đầu (chứa 70% nội dung sự kiện).
- `p1..pk`: Giữ các đoạn chứa số liệu định lượng (%, tỷ đồng, triệu USD, KQKD) và phát ngôn lãnh đạo / sự kiện pháp lý.
- Loại bỏ hoàn toàn: Lịch sử thành lập công ty, giải thích thuật ngữ chung, liên kết xem thêm và footer tòa soạn.

```json
{"d":"2026-09-18","n":100,"a":[
 {"i":0,"t":"Hòa Phát báo lãi quý 3 tăng 25%, HRC hưởng lợi thuế chống bán phá giá",
  "p":["Sapo: Tập đoàn Hòa Phát công bố LNST quý 3 đạt...",
       "Doanh thu mảng thép cuộn cán nóng HRC tăng 32%, biên lợi nhuận mở rộng...",
       "Ông Trần Đình Long nhận định chính sách thuế tự vệ tạo dư địa tăng trưởng..."]},
 {"i":1,"t":"VND: Báo cáo tình hình quản trị công ty 6 tháng đầu năm",
  "p":["VNDirect công bố báo cáo quản trị định kỳ 6 tháng..."]}]}
```

Bỏ khỏi packet: `code_first` hints, `domain`, `url`, `raw_sha256`, `entity_catalog_ref`, `output_contract`, `constraints`, `instructions_ref`. Mọi luật và hợp đồng đã nằm trong prefix tĩnh.

`full` ~ 600–900 token miss/bài (nhờ lọc đoạn thông minh).

**Bắt buộc ghi packet dạng compact JSON (`json.dumps(..., separators=(',',':'))`), không `indent`.** Ngăn ngừa việc một dòng vượt quá trần 2.000 ký tự của parser, bảo vệ bất biến zero-tool.

### 3.2 Article Record (output) — Unified Compact Schema & Citations-by-Index

```json
[{"i":0,
  "e":[["Hòa Phát","COM"],["HRC","AST"],["thuế chống bán phá giá","THM"],["ông Trần Đình Long","PER"]],
  "s":"Hòa Phát công bố lợi nhuận quý 3 tăng 25% nhờ sản lượng HRC và giá bán cải thiện.",
  "k":["Biên lợi nhuận HRC mở rộng sau thuế chống bán phá giá","Sản lượng nội địa tăng"],
  "im":"Kết quả vượt kỳ vọng hỗ trợ định giá ngắn hạn; theo dõi giá HRC quý 4.",
  "sn":"pos","ts":"today","c":[0,2]},
 {"i":1,"e":[["VND","TIC"]],"s":"CBTT quản trị định kỳ.","sn":"neu","ts":"arch","c":[0]}]
```

| Khóa | LLM trả | Expander bù (0 token) |
|---|---|---|
| `e` | Mảng `[surface nguyên văn, MÃ NHÓM]` (LLM Intent độc lập) | `entity_id`, `type`, `in_list`, `method`, `categories`, đối soát với Code Intent |
| `s`, `k`, `im` | Tóm tắt / Key notes / Hàm ý phân tích | — |
| `sn`, `ts` | `pos/neg/neu` · `urg/today/week/month/arch` | Map về enum đầy đủ |
| `c` | **Chỉ số mảng đoạn `[0, 2]`** làm chứng cứ | Trích nguyên văn đoạn `p0`, `p2` thành citations $\ge 20$ ký tự $\rightarrow$ DoD 100% pass |
| — | — | `article_id`, `title`, `processing_metadata`, `intent_source` (`BOTH`/`LLM_ONLY`/`CODE_ONLY`) |

`full` ~ 220–300 token out/bài · `lite` ~ 30–40.

---

## 4. Nhóm thực thể — bám nền tảng `project/data/entities/`

### 4.1 Ground truth đã đo (2026-09-18)

`entities.json`: **1.262 entity**, 2.728 alias, 12 `type`. **Drift đã gây tốn token trong vệt 845K:** `type` là `INDUSTRY_GICS1/2/3` nhưng `entity_id` mang tiền tố **`IND_GICS1/2/3:`** — hai thứ khác nhau, và bảng tra trong SKILL.md không nói.

| `type`                   |              n | tiền tố`entity_id`          | Nhóm đóng? |
| -------------------------- | -------------: | ------------------------------- | ------------- |
| TICKER                     |          1.093 | `TICKER:`                     | mở           |
| ETF · SECURITY_OTHER      |       28 · 11 | `ETF:` · `SECURITY_OTHER:` | đóng (39)   |
| INDEX · EXCHANGE          |         6 · 3 | `INDEX:` · `EXCHANGE:`     | đóng (9)    |
| INDUSTRY_GICS1/2/3         | 11 · 28 · 51 | **`IND_GICS1/2/3:`**    | đóng (90)   |
| MACRO_GEO · MACRO_THEME   |         8 · 9 | như type                       | đóng (17)   |
| ASSET_CLASS · INSTITUTION |         7 · 7 | như type                       | đóng (14)   |

Ngành GICS chỉ có **1 alias = chính canonical_name**, nên code-first không bao giờ khớp `"đường sắt"` thành `Vận tải đường bộ & đường sắt`. Đây chính là chỗ LLM tạo giá trị và code không thay được.

### 4.2 Mười một mã nhóm LLM phát ra — mỗi mã một thuật toán resolver riêng

Ý tưởng của anh (mã CP / tên doanh nghiệp / tên lãnh đạo / nhóm tài sản / themes) được tách thành các mã mà **code có cách giải khác nhau** — đó là lý do tách, không phải để cho đẹp:

| Mã                                   | LLM nói khi thấy                                                        | Resolver của code                                                                                                                          | Nguồn                                        |
| ------------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| `TIC`                               | mã 3 ký tự in hoa (`HPG`, `VND:`)                                  | exact code +`CODE_STOPLIST` + miễn trừ CBTT `^[A-Z0-9]{3}\s*:`                                                                        | `entities.py`                               |
| `COM`                               | tên doanh nghiệp / thương hiệu (`Hòa Phát`, `Bách Hóa Xanh`) | alias fold + word-boundary + morphology guard +`brand_aliases.yaml`                                                                       | `entities.py`, `config/entities/aliases/` |
| `PER`                               | tên người / lãnh đạo (`ông Trần Đình Long`)                   | `leaders.yaml` (**chưa có** — seed từ `unlisted`, Phase 06)                                                                   | mới                                          |
| `FND`                               | ETF / quỹ                                                                | digest 39 ID                                                                                                                                | catalog                                       |
| `IDX` / `EXC`                     | chỉ số / sàn                                                           | digest 6 / 3 ID                                                                                                                             | catalog                                       |
| `IND`                               | ngành (`thép`, `đường sắt`, `bán lẻ`)                       | digest 90 ID, chọn**cấp sâu nhất** khớp; sinh `entity_id` bằng tiền tố `IND_GICS*` còn `type` bằng `INDUSTRY_GICS*` | catalog +`taxonomy.json.gics_tree`          |
| `GEO` / `THM` / `AST` / `INS` | quốc gia / chủ đề vĩ mô / tài sản / định chế                   | digest 8 / 9 / 7 / 7                                                                                                                        | catalog                                       |

Không khớp thì `in_list: false`, `entity_id: null`, vào `unlisted_candidates`. **An toàn theo hướng bỏ sót, không bịa.**

### 4.3 Prefix chứa gì — đã cân đo

| Thành phần                                                                                   |            Token |                    Vào prefix?                    |
| ---------------------------------------------------------------------------------------------- | ---------------: | :------------------------------------------------: |
| `ARTICLE_SYSTEM_CORE` (luật 10 miền nén + guard hình thái + hợp đồng Article Record) |           ~1.200 |                        có                        |
| Digest**nhóm đóng** 130 ID + alias (GEO/THM/AST/INS/IDX/EXC/GICS 1-2-3)               |  **3.750** |                        có                        |
| Digest ETF + SECURITY_OTHER (39)                                                               |              894 |                        có                        |
| Few-shot 3 ví dụ                                                                             |             ~800 |                        có                        |
| **Cộng payload prefix**                                                                 | **~6.650** |                                                    |
| Digest TICKER Tier-1`code + name` (742 mã)                                                  |            8.116 | không (mặc định) —**thí nghiệm** §11 |
| Digest TICKER Tier-1+2                                                                         |           11.878 |                       không                       |
| Toàn bộ`entities.json`                                                                     |          324.493 |                không, tuyệt đối                |

Lý do không nhét ticker: LLM **không cần** biết mã — nó nói `"Hòa Phát"`, code biết `HPG`. Digest ticker chỉ đáng nếu thí nghiệm cho thấy recall `COM` tăng.

**Prefix sinh tự động** bằng `build_article_prefix.py` từ `entities.json` + `taxonomy.json` + rules, kèm hash. Hết lớp lỗi #3 (bảng tra lệch catalog), và đổi catalog thì prefix đổi theo có kiểm soát.

### 4.4 Cơ chế Nhận diện Intent Độc lập & Lớp Đối soát Hai Đầu (Dual-Track Intent Reconciliation)

Nhằm đảm bảo tính khách quan của AI, tránh việc LLM bị thiên kiến (Confirmation Bias) khi nhận gợi ý từ Code, và mang lại tính minh bạch giải trình (Explainability) tối đa cho người dùng cuối:

1. **Nhận diện độc lập ban đầu (Parallel Independent Detection)**:
   - **Track Code-First (0 token)**: `entities.py` quét tiêu đề/sapo qua regex mã CP (`TIC`), alias từ điển (`brand_aliases.yaml`), và bộ lọc hình thái. Kết quả lưu vào `{code_entities}`.
   - **Track LLM Semantic (Zero-tool)**: LLM đọc văn bản tự nhiên, nhận diện đối tượng theo 11 mã nhóm ngữ nghĩa (`TIC`, `COM`, `IND`, `THM`, `GEO`, `PER`...) hoàn toàn độc lập, không nhận bất kỳ hint nào từ Code. Kết quả trả về trong trường `e` của Article Record: `{llm_entities}`.

2. **Lớp Mapping & Đối soát Chéo (Reconciliation Layer — 0 token)**:
   Script `article_expand.py` chạy so khớp đối chiếu giữa 2 tập danh sách:
   - **`BOTH` (Đồng thuận cao)**: Cả Code và LLM cùng nhận diện được thực thể (ví dụ: Code thấy `HPG`, LLM thấy `"Hòa Phát"`). Độ tin cậy đạt mức cao nhất.
   - **`LLM_ONLY` (Vùng giá trị cốt lõi của AI)**: LLM phát hiện thực thể/chủ đề dựa trên ngữ nghĩa sâu (tên thương hiệu con, ngành nghề suy diễn, chủ đề vĩ mô) mà Code không có từ khóa cứng. Tự động đưa vào `unlisted_candidates` để cấp nguyên liệu cho `entity-curator` mở rộng Catalog.
   - **`CODE_ONLY` (Khớp từ khóa)**: Code khớp từ khóa/ticker xuất hiện lướt qua nhưng LLM không đánh giá là đối tượng trọng tâm của bài.

3. **Cấu trúc Bảng Báo cáo Giao hàng Người dùng Cuối (Excel Deliverable)**:
   Trong file `users/output/<user>/<date>.xlsx`, phân tách rõ 2 cột độc lập:
   - **Cột `intent_llm`**: Thực thể do LLM nhận diện độc lập kèm phân nhóm (VD: `Hòa Phát [COM]; HRC [AST]; Thuế tự vệ [THM]`).
   - **Cột `intent_code`**: Thực thể do Code nhận diện tất định (VD: `HPG [TIC]; THEP [IND]`).
   - **Cột `intent_source`**: Trạng thái đối soát (`BOTH`, `LLM_ONLY`, `CODE_ONLY`).

---

## 5. Kiểm soát context & cơ chế handoff

Nỗi lo của anh — nhận thức suy giảm khi context chiếm 50–60% của 1M — tách làm hai vế vì hai vế có lời giải khác hẳn nhau.

### 5.1 Worker: context bị chặn **bằng xây dựng**, không phải bằng kỷ luật

Worker chỉ có prefix + packet + output. Không tool nên không có tool result tích lũy; một lượt nên không có history.

| Cấu hình                            | Prefix |  Packet | Output | **Đỉnh context** |       % của 1M |
| ------------------------------------- | -----: | ------: | -----: | -----------------------: | --------------: |
| 100 bài`lite`                      |  7.000 |   4.500 |  3.500 |         **15.000** |            1,5% |
| 100 bài`full`                      |  7.000 |  85.000 | 30.000 |        **122.000** | **12,2%** |
| 200 bài`full` (nếu sau này cần) |  7.000 | 170.000 | 60.000 |                  237.000 |           23,7% |

Kết luận: **ở 100 bài/lượt, worker không bao giờ tới gần vùng suy giảm.** `article_pack.py` tính `est_ctx_peak` trước khi phát packet và **tự chia nhỏ batch** nếu vượt ngưỡng cấu hình (mặc định 25% = 250K) — chốt an toàn tự động của operator, không phải hỏi người.

### 5.2 Conductor: rủi ro thật, giải bằng *stateless-by-construction*

**Lớp 1 — không cho phình.** PTC: chỉ `print`/`return` vào history [V §14]. Chương trình `run_code` ghi kết quả con thẳng ra đĩa và chỉ `return {ok, n, failed}`. Một wave 100 bài để lại **dưới 100 token** trong context conductor.

**Lớp 2 — đo áp suất.** DSH ghi sẵn `contextPressure {surfaceTokens, contextWindow, pressureTokens}` trong `session_projcache` [V §14]. Operator `ctx_probe.py` đọc, `pipeline_radar.py status` in một dòng:

```
Context phiên: 184.320 / 1.048.576 (17,6%)  xanh  | wave đã chạy: 6 | ước còn: ~40 wave
```

**Lớp 3 — ngưỡng và handoff tự động.** Đặt **dưới** vùng anh lo (50–60%) để còn biên:

| Mức  |  Áp suất | Hành vi của Conductor                                                                |
| ----- | ---------: | -------------------------------------------------------------------------------------- |
| xanh  | dưới 25% | chạy bình thường                                                                   |
| vàng |    25–40% | hoàn tất wave đang chạy rồi**dừng và sinh handoff**; không mở wave mới |
| đỏ  |  trên 40% | dừng ngay sau batch hiện tại, sinh handoff                                          |

### 5.3 Handoff gần như miễn phí — vì trạng thái không nằm trong đầu LLM

Toàn bộ trạng thái pipeline đã nằm ở SQLite (`l1_tasks`, `work_items`, `l1_outputs`, `agent_outputs`) và file trên đĩa. Conductor **không giữ trạng thái nào** mà DB không có. Nên handoff không cần LLM tóm tắt gì.

`handoff.py` (operator, **0 token**) sinh `data/state/HANDOFF-<ts>.md`:

```
WAVE ĐANG DỞ   : wave_07 · 3/5 batch xong · batch 04,05 chưa chạy
ĐÃ INGEST      : L1 412 bài · Gold 138 bài (hôm nay)
HÀNG ĐỢI       : l1_tasks pending=1.349 failed=85 · work_items pending=7.454
PACKET TRÊN ĐĨA: data/agent_tasks/article/wave_07_b04.json, _b05.json
LỆNH TIẾP THEO : python scripts/article_run.py --wave 07 --resume
PREFIX HASH    : a7f3… (khớp preset hiện tại: OK)
```

Phiên mới: mở preset, chạy radar, đọc handoff, chạy tiếp. **Chi phí handoff ~ 0 token, không mất việc.** Sang phiên mới trở thành thao tác bình thường và rẻ, không phải phương án chữa cháy.

### 5.4 Mỗi wave là một điểm cắt an toàn

`article_expand` + `ingest` chạy ngay sau mỗi batch và ghi DB, nên **không có công việc nào sống trong context**. Mất phiên giữa chừng chỉ mất đúng batch đang chạy, và packet của nó vẫn nằm trên đĩa để chạy lại.

---

## 6. Cơ chế đo token burn trong khung harness (đo, không phải gate)

Ba công cụ, tất cả là **operator 0 token**, tất cả chỉ **báo cáo**.

### 6.1 `estimate_wave.py` — dự toán TRƯỚC khi chạy

```
WAVE 07 — 5 batch × 100 bài (320 full / 180 lite)
                        miss      hit(prefix)   output    ctx đỉnh/lượt
  batch 01 (100 full)   85.000    7.000         30.000    122.000  (11,6%)
  ...
  CỘNG WAVE            312.000    35.000       108.000
  Quota-equivalent: 455.000 token
  Chi phí: 0,112 USD (thấp điểm) / 0,224 USD (cao điểm)
```

### 6.2 `token_ledger.py` — số THẬT sau khi chạy

Nguồn đã xác minh [V §14]:

- `~/.dsh/storages/session_projcache/sessions/<id>.json` cho `tokenUsage.totals {uncachedInputTokens, outputTokens, cacheReadTokens, cacheWriteTokens}` + `contextPressure` + `contextBreakdown`
- `~/.dsh/sessions/<cwd>/<session>/session.v3.jsonl.zstd` cho từng event `assistant/message.usage {inputTokens, cacheReadTokens, outputTokens, reasoningTokens}` (nén nhiều frame zstd, tách theo magic `28 B5 2F FD`)

Ghi bảng mới `token_ledger` trong `harness.db`:

| cột                                                                                                                  | nguồn                                                                 |
| --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `ts`, `session_id`, `agent_id`, `batch_id`, `n_items`, `depth_mix`                                        | conductor + packet                                                     |
| `miss_tokens` (từ `inputTokens`), `hit_tokens` (từ `cacheReadTokens`), `out_tokens`, `reasoning_tokens` | DSH event                                                              |
| `turns` — số lượt của con                                                                                      | đếm event                                                            |
| `ctx_peak`, `ctx_pct`                                                                                             | `contextPressure`                                                    |
| `est_miss`, `est_out`                                                                                             | từ`estimate_wave.py`, để đo **độ chính xác dự toán** |

### 6.3 `pipeline_radar.py token` — báo cáo sáu mục

```
1. QUOTA (mọi token)      : 455.000  (hit 35.000 · miss 312.000 · out 108.000 · reasoning 0)
2. CHI PHÍ                : 0,112 USD thấp điểm  |  0,224 USD cao điểm
3. HIỆU QUẢ CACHE         : hit ratio 10,1%   (prefix 7.000 × 5 lượt)
4. CONTEXT CONDUCTOR      : 184.320 / 1.048.576 (17,6%) xanh
5. SAI SỐ DỰ TOÁN         : +3,2%
6. PHÂN RÃ CONTEXT SUBAGENT (batch 01):
     prefix (hit) 7.000 | packet (miss) 85.000 | output 30.000 | turns 1
```

Mục 6 trả lời trực tiếp *"subagents chứa context như thế nào"*: mỗi lượt con một dòng, thấy rõ bao nhiêu là prefix tái dùng, bao nhiêu là nội dung bài, bao nhiêu là sinh ra.

### 6.4 Không có gate

Không có `ns_activate`, không hỏi xác nhận, không chặn khi vượt số. `estimate_wave.py` in ra rồi chạy tiếp. Chỉ hai chốt **tự động** giữ hệ thống không tự làm hỏng mình, không liên quan tới phê duyệt:

- `est_ctx_peak` vượt ngưỡng (mặc định 25% của 1M) thì `article_pack.py` chia nhỏ batch. Bảo vệ **chất lượng**, không phải bảo vệ ví.
- `parse_fail` vượt 10% trong một wave thì dừng wave và báo. Chống đốt tiếp khi prompt đã hỏng.

### 6.5 Đặt hàng DSH (row/hook cần thêm)

| Hạng mục                               | Cơ chế DSH                                                                          | Trạng thái                                                                      |
| ---------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Ghi ledger sau mỗi lượt con           | hook native`tools/result` trên `agent_article` gọi `token_ledger.py --append` | khả thi [V §14]                                                                 |
| Đọc áp suất context                  | `ctx.tokenMeter` / projcache                                                        | có sẵn [V]                                                                      |
| Không để compaction làm trôi prefix | row`compaction-basic` đặt `auto: false` trong preset worker                     | cấu hình                                                                        |
| Tắt thinking                            | `agentOptions.reasoningEffort: off`                                                 | cấu hình                                                                        |
| Trần output đúng batch                | `agentOptions.maxTokens` = N × out/item × 1,3 (100 `full` thành 40.000)        | **bắt buộc** — mặc định chỉ 8K, batch 100 sẽ bị cắt cụt im lặng |

---

## 7. Row subagent DSH & chương trình một wave

```yaml
- id: tool-subagent-article
  name: '@deepseek-ai/dsh-tool-subagent'
  config:
    provider: spawn
    toolName: agent_article
    persona: >-
      <ARTICLE_SYSTEM_CORE v1 — sinh bởi build_article_prefix.py, KHÔNG gõ tay>
    agentOptions:
      provider: deepseek-official
      model: deepseek-flash
      reasoningEffort: off       # settings.yaml đang để 'high' cho mọi child
      maxTokens: 40000           # 100 bài full; thiếu dòng này thì mặc định 8K cắt cụt
    toolFilter: { allow: [] }    # không tool; Phase 00 thử, fallback deny toàn bộ
    maxDepth: 0
    backgroundMode: one-shot
```

Preset worker riêng (khuyến nghị, tách khỏi conductor): bỏ row `agent-instructions` (AGENTS.md ~4.069 token vô ích với worker), `compaction-basic` đặt `auto: false`, `dsh-persona.includeRuntimeContext: false`. Mount bằng junction như preset conductor hiện có.

```ts
const pack = JSON.parse((await tools.pwsh({command: PY+' scripts/article_pack.py --lane bulk --batch 100 --limit 500'})).stdout.text);
await runOne(pack.batches[0]);                                   // warm-up ghi cache
await Promise.all(pack.batches.slice(1).map(runOne));            // fan-out
async function runOne(b) {
  const packet = await tools.read({file_path: b.path});          // vào chương trình, không vào context
  const res = await tools.agent_article({description:'article '+b.id, prompt: packet.text});
  await tools.write({file_path:'data/agent_outputs_article/'+b.id+'.json', content: res.text});
  return b.id;                                                   // KHÔNG return nội dung
}
await tools.pwsh({command: PY+' scripts/article_expand.py data/agent_outputs_article'});
await tools.pwsh({command: PY+' scripts/l1_ingest.py data/agent_outputs_l1'});
await tools.pwsh({command: PY+' scripts/agent_ingest.py data/agent_outputs'});
await tools.pwsh({command: PY+' scripts/token_ledger.py --wave '+pack.wave});
return {batches: pack.batches.length};
```

---

## 8. Quản trị wave & Hàng đợi Mega-Batch phân tầng ưu tiên

ADR 0008 §2.1 yêu cầu người xác nhận trước mọi lần tiêu token. Anh chỉ đạo bỏ cổng hỏi người, thay bằng **quản trị wave có ý thức** kết hợp **hàng đợi Mega-batch 100 bài/batch phân tầng ưu tiên (Priority-Queue)**.

### 8.1 Thuật toán Hàng đợi Phân tầng (Priority-Queue Engine)
Tầng Code-First chấm điểm ưu tiên (0 token) trước khi đóng gói các gói 100 bài:
1. **TIER 1 — Delivery First (Batch 1, 100 bài)**:
   - Bài khớp Ticker/Alias nằm trong Watchlist active (`manifest.yaml`, e.g., user `AnPT`).
   - Bài chứa biến động vĩ mô khẩn (NHNN, lãi suất, tỷ giá, GDP, CPI, thuế tự vệ).
   - **Quy trình**: Đóng gói ngay vào **Batch 1** $\rightarrow$ LLM chạy $\rightarrow$ Expander đối soát $\rightarrow$ **Kích hoạt ngay `write_user_output.py` để xuất bản file Excel giao cho người dùng trước trong 2–3 phút**.
2. **TIER 2 & 3 — Background Queue (Batch 2..N, 100 bài/batch)**:
   - Cổ phiếu VN30 ngoài watchlist, báo cáo tài chính quý/năm, công bố thông tin hành chính, tin cổ đông nhỏ, tin thị trường chung.
   - **Quy trình**: Vẫn xử lý **FULL toàn bộ cả bài** (không bỏ sót bài nào, không để bài nào ở trạng thái L1-only mãi mãi), nhưng xếp hàng đợi phía sau để chạy các batch nối tiếp, hoàn tất nạp SQLite để làm giàu kho dữ liệu phân tích với **độ phủ 100%**.

### 8.2 Amendment ADR 0008 đề xuất

| Điều khoản 0008 | Thay bằng |
| --- | --- |
| §2.1 hỏi xác nhận trước mỗi lần tiêu token | Người vận hành điều khiển bằng **lệnh wave tường minh** (`article_run.py --wave N`). Chạy tức là đã quyết. |
| §2.3 trần token mỗi lần chạy, dừng sạch | Chỉ còn **chốt kỹ thuật**: `est_ctx_peak` (chất lượng) và `parse_fail` (prompt hỏng). Không có trần chi phí chặn việc. |
| §2.4 thất bại phải ồn ào | **Giữ nguyên** — vẫn bắt buộc |
| §2.2 bỏ `--dangerously-skip-permissions` | Không còn liên quan (không dùng `agy`) |

---

## 9. Các phase triển khai

| Phase | Tên | Ra cái gì |
| :---: | --- | --- |
| 00 | **Cơ chế đo** — `token_ledger.py`, `ctx_probe.py`, `estimate_wave.py`, bảng `token_ledger`, radar 6 mục | Số thật thay hằng số 450/1.470; xác minh `allow: []` và `reasoningTokens == 0` |
| 01 | **Prefix sinh tự động** — `build_article_prefix.py` + digest nhóm đóng 130 ID + hash kiểm drift | Prefix ~6.650 token, byte-identical, khớp catalog |
| 02 | **Priority Pack & Smart Paragraph Distillation** — `article_pack.py` (Tier 1 ưu tiên, bỏ trần 2.200 ký tự, mảng `p[]`) | Packet compact 100 bài theo thứ tự ưu tiên; Sapo + số liệu định lượng |
| 03 | **Unified Single-shot Article Processor** — `agent_article` (100 bài, 1 lượt) + `article_expand.py` | Trả cả Intent và Content; citations index `c: [0, 2]`; DoD 100% pass |
| 04 | **Delivery First & Dual-Track Output** — Giao Excel Batch 1 cho User (2 cột Intent) + nạp Batch 2..N | `user_output.py` có 2 cột `intent_llm` và `intent_code`; độ phủ 100% |
| 05 | **Context governance & Handoff 0-token** — `handoff.py`, ngưỡng áp suất 25/40% | Handoff 0 token khi đổi phiên; không mất việc dở dang |
| 06 | **Vòng khai phá catalog** — unlisted từ `LLM_ONLY` qua `entity-curator` thành delta và `leaders.yaml` | Catalog lớn dần từ phát hiện ngữ nghĩa của LLM |

---

## 10. Nghiệm thu từng phase

- **00:** `token_ledger` có dòng thật đủ `hit/miss/out/reasoning/ctx`; radar in 6 mục; `reasoningTokens == 0` khi `reasoningEffort: off`; số lượt của con bằng 1; `article_pack.py` xuất packet compact và test kiểm tra không dòng nào vượt 2.000 ký tự (chặn tái diễn G1).
- **01:** hash prefix khớp `entities.json`; digest đủ 130 ID nhóm đóng kèm tiền tố `IND_GICS*` đúng.
- **02:** `article_pack.py` xếp đúng 100 bài Tier 1 (Watchlist + Vĩ mô khẩn) lên đầu; mảng `p[]` chắt lọc đúng Sapo và số liệu, không dòng nào quá 2.000 ký tự.
- **03:** 1 batch 100 bài full: **1 lượt duy nhất**, citations index `c: [0, 2]` bung ra exact substring đạt DoD 100%, parse_fail dưới 2%, hit ratio batch thứ 2 trở đi từ 80%.
- **04:** file Excel `users/output/<user>/<date>.xlsx` hiển thị đầy đủ 2 cột `intent_llm` và `intent_code` kèm `intent_source`; Batch 1 giao hàng trong vòng 3 phút; các batch sau phủ 100% bài cào.
- **05:** cắt phiên giữa wave, phiên mới đọc handoff chạy tiếp, không mất bài, 0 token cho handoff.
- **06:** các thực thể `LLM_ONLY` sinh ra unlisted candidates được `entity-curator` tổng hợp thành delta catalog để duyệt.

Mỗi phase trả **Unit + Integration + Platform** theo AGENTS.md.

---

## 11. Ma trận thí nghiệm

| Biến                             | Mức                                         | Đo                                                                       |
| --------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------- |
| Batch size                        | 100 (mặc định) · 50 · 200               | DoD, parse_fail, recall**theo vị trí bài trong batch**, ctx_peak |
| Digest TICKER Tier-1 trong prefix | không (mặc định) / có (thêm 8.116 tok) | recall nhóm`COM`, hit ratio                                            |
| Few-shot                          | 3 / 5 ví dụ                                | DoD, out/bài                                                             |
| Fan-out                           | warm-up trước / không                     | hit ratio wave                                                            |
| Độ sâu                         | 100% full / auto                             | coverage, quota/ngày                                                     |

Mẫu chuẩn: 200 bài gán tay, đủ 11 nhóm. Chỉ số quan trọng nhất ở batch 100: **recall có giảm ở bài thứ 60–100 không** — phép đo trực tiếp cho nỗi lo suy giảm nhận thức.

---

## 12. Rủi ro & đối sách

| Rủi ro                                                     | Đối sách                                                                                                      |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Quên`maxTokens` nên mặc định 8K cắt cụt batch 100  | row worker luôn khai;`estimate_wave.py` cảnh báo khi `est_out` vượt 80% `maxTokens`                   |
| Chất lượng giảm ở bài cuối batch 100                 | đo recall theo vị trí (§11); nếu giảm thì hạ về 50 — cơ chế không đổi                             |
| Prefix vỡ (đổi tool set / preset / effort / compaction)  | hash prefix + radar mục 3 hit ratio;`compaction auto: false`                                                  |
| Thinking bật lại do`settings.yaml` đè                 | kiểm`reasoningTokens == 0` mỗi wave trong ledger                                                             |
| `toolFilter.allow: []` không hợp lệ                    | fallback`deny` toàn bộ; đo `turns == 1` để xác nhận                                                   |
| Không có JSON mode qua DSH                                | persona ép JSON-only + parser salvage + theo dõi`parse_fail`                                                 |
| Context conductor phình ngoài dự kiến                   | 3 lớp §5.2; handoff 0 token                                                                                    |
| Resolver khớp sai alias ngắn                              | tái dùng guard hình thái`entities.py`; không khớp thì unlisted (bỏ sót an toàn hơn bịa)            |
| Bỏ cổng xác nhận nên chạy nhầm wave lớn             | `article_pack.py` demand-driven theo `--limit` tường minh; ledger cho thấy ngay wave nào tốn bao nhiêu |
| Contract L1 chỉ nhận`surface` là chuỗi con của title | expander tách title-entities (vào L1) và body-mentions (sidecar, ADR ở Phase 06)                             |
| Packet ghi pretty-printed làm một đoạn vượt trần dòng của tool đọc (G1, §1.5) | `article_pack.py` ghi compact JSON bắt buộc (§3.1); Phase 00 có test kiểm tra không dòng nào > 2.000 ký tự |
| LLM tự mở vòng verify citation nếu vẫn còn tool để gọi (G2, §1.5) | `toolFilter: { allow: [] }` triệt tiêu vật lý; citations-by-index (§3.2) khiến verify trở thành vô nghĩa vì LLM không tự tay chép chuỗi |

---

## 13. Anti-scope

- Không dùng code/regex để **quyết định** thực thể hay tóm tắt. Code chỉ so khớp thứ LLM đã nêu.
- Không model ngoài `deepseek-flash` (D6). Không model local/NER.
- Không đổi `l1-entity-output-v1`, `agent-output-v2-lean`, `check_l1_dod`, DB schema (trừ bảng `token_ledger` mới và `mentions` chờ ADR).
- Không chạm `raw_html` (WORM).
- Không dựng lại cổng hỏi người dưới tên khác. Mọi số đo là để **nhìn**, không để **chặn**.
- Không "continue"/multi-turn để vượt output cap.

---

## 14. Nghiên cứu đã xác minh (2026-09-18)

Nguồn: `api-docs.deepseek.com` và bản cài DSH `%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai\*` (0.1.5-rc.2) + session log thật. **[V]** đã kiểm chứng · **[U]** chưa.

### DeepSeek

| Mục                            | Kết luận                                                                                                     |    |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------- | :-: |
| Cache                           | tự động,**prefix từ token 0**, đơn vị 64 token, best-effort, hết hạn vài giờ đến vài ngày | [V] |
| Usage                           | `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` / `reasoning_tokens`                              | [V] |
| Giá`deepseek-flash` (USD/1M) | hit 0,006/0,003 · miss 0,30/0,15 · out 1,20/0,60 (peak/off-peak) — khớp bảng anh đưa                    | [V] |
| Giờ peak                       | 01–04h và 06–10h UTC, T2–T6, tức**08–11h và 13–17h giờ VN**                                     | [V] |
| Context / output                | context**1M**; max output **384K**; **mặc định chỉ 8K** khi không thinking              | [V] |
| Thinking                        | bật mặc định;`reasoning_effort` low/high/max; **tắt được**                                     | [V] |
| Rate limit                      | **không TPM/RPM**, chỉ concurrency (flash 2.500)                                                       | [V] |
| JSON mode                       | có ở API nhưng**DSH không gửi `response_format`**                                                 | [V] |
| Batch API giảm 50%             | không có tài liệu chính thức                                                                             | [U] |

### DSH

| Mục                                                  | Kết luận                                                                                                                              |    |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | :-: |
| Usage per call                                        | `assistant/message.usage {inputTokens=miss, cacheReadTokens=hit, outputTokens, reasoningTokens}` trong `session.v3.jsonl.zstd`      | [V] |
| Tổng + áp suất                                     | `session_projcache/sessions/<id>.json`: `tokenUsage.totals`, `contextPressure`, `contextBreakdown`                              | [V] |
| Số thật phiên Conductor 18/09                      | cacheRead**2.081.536** · uncached **72.855** (hit 96,6%)                                                                   | [V] |
| System prompt                                         | **1 node, không timestamp**; thứ tự: harness identity, persona prefix, section, `tools:sdk`, suffix (`{{cwd}}` cố định) | [V] |
| Prefix chỉ vỡ khi                                   | đổi tool set / preset / model-effort route / compaction                                                                               | [V] |
| `settings.yaml` hiện tại                          | `reasoningEffort: high`, preset `ptc`, model `deepseek-flash`                                                                     | [V] |
| `agentOptions`                                      | chỉ`provider`, `model`, `reasoningEffort`, `maxTokens`. Không temperature / response_format / prefill                         | [V] |
| PTC                                                   | chỉ`print`/`return` vào context; prompt inline **không giới hạn byte**; spill 50 KB cho output ra context                | [V] |
| Hook                                                  | `tools/pre-execute`, `guard()`, `tools/result`; đọc được `ctx.tokenMeter`                                                  | [V] |
| `allow: []` hợp lệ? · tách AGENTS.md per-child? | chưa xác minh, để Phase 00                                                                                                          | [U] |

---

## 15. Tài liệu cần đồng bộ

- **Amendment ADR 0008** (§8) — bỏ cổng xác nhận, giữ "thất bại ồn ào".
- `token-auditor/SKILL.md`: định mức 450/1.470 và trần 350k/ngày **sai 1–2 bậc** — thay bằng cơ chế ledger §6.
- `l1-entity-matcher/SKILL.md` §6: bảng tra thiếu tiền tố `IND_GICS*`, nguyên nhân gốc của 43.593 token lãng phí — chuyển thành **sinh tự động**, không gõ tay.
- `rules/08`: bổ sung "cấm read-back file vừa ghi" và "cấm đọc mã nguồn để suy ra hợp đồng".
- `registry.yaml`: thêm `article-processor`; `l1-entity-matcher` và `gold-financial-analyst` chuyển deprecated sau Phase 03.
- `pipeline.yaml`: stage `article_pack`, `article_analyze`, `article_expand`, rồi `l1_ingest` + `gold_ingest`.
- Drift `MACRO_THEME` map về `TYPE_GROUP.macro_geo`, và `INDUSTRY_GICS*` so với `IND_GICS*`: lấy `entities.json` + `TYPE_GROUP` làm nguồn chân lý khi sinh prefix.
- `src/export/user_output.py`: Mở rộng `FINAL_COLUMNS` bổ sung 2 cột riêng biệt `intent_llm` và `intent_code`, kèm `intent_source` (`BOTH`, `LLM_ONLY`, `CODE_ONLY`) phục vụ giao hàng Excel.
