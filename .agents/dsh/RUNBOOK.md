# RUNBOOK — Vận hành Article Lane hợp nhất (PTC, 3 mega-batch/ngày)

- **Áp dụng từ:** 2026-09-18
- **Tài liệu quy phạm:** `plans/20260918-1651-article-lane-unified/plan.md` — đọc §3 (bề mặt DSH), §6 (hợp đồng dữ liệu), §8 (kỷ luật vận hành), §16 (van xả)
- **Thay thế:** bản RUNBOOK 2026-09-17 (luồng `agent_l1`/`agent_gold` hai tầng, 5 bước/wave, trần token 60k/40k). Luồng đó đã bị Q1–Q6 bãi bỏ
- **Phạm vi:** một ngày vận hành, 3 mega-batch × 100 bài, chạy trong phiên DSH preset `news-scape-conductor`

> Q4 đã bỏ cổng xác nhận. **Gõ lệnh wave tức là đã quyết.** Không còn hỏi, không còn trần chi phí chặn việc. Chỉ còn hai chốt kỹ thuật tự động ở §5.

---

## 0. Preflight — 3 việc, 0 token, bắt buộc trước wave đầu tiên

| # | Việc | Lệnh / cách kiểm | Đạt khi |
|:-:|---|---|---|
| 1 | **Đúng preset** | Phiên phải chọn `news-scape-conductor` **trước khi gửi tin đầu tiên**. Kiểm: tool trực tiếp chỉ có `run_code`; binding SDK có `pwsh`, `read`, `write`, `agent_article` | Có `agent_article`; preset không phải `ptc`/`standard` |
| 2 | **Prefix khớp catalog** | `python scripts/article_run.py --check-prefix` | exit 0. Lệch ⇒ chạy `python scripts/build_article_prefix.py` rồi **cập nhật persona** trong preset trước khi mở đợt |
| 3 | **Permission** | `workspace-write` cho wave thật | Cần ghi packet/output/DB |

**Vì sao #1 là bắt buộc:** preset mặc định của `.dsh/settings.yaml` là `ptc`, không phải conductor. Phiên 17/09 chạy sai preset nên con được spawn bằng `subagent` generic — **không có `toolFilter`, không có persona, không có `maxDepth`**. Đó là nguyên nhân gốc của vệt 845K, không phải lỗi thiết kế. `guard()` preflight phải từ chối chạy khi sai preset.

---

## 1. Kiến trúc một ngày — 3 mega-batch chia 2 đợt

Mục tiêu §1 của plan: **toàn bộ bài trong ngày xử lý xong trong ngày, radar báo phủ 100%.** Giao hàng cho user là ưu tiên tối thượng, nên 3 mega-batch **không** chạy trong một đợt duy nhất:

| Đợt | Nội dung | Batch | Vì sao tách |
|---|---|---|---|
| **W1 — Delivery First** | Tier 1: khớp Watchlist active (`manifest.yaml`) + vĩ mô khẩn (NHNN, lãi suất, tỷ giá, GDP, CPI, thuế tự phòng vệ) | 1 × 100 (`--limit 100`) | Giao Excel cho user trong vài phút, không chờ hàng đợi nền |
| **W2 — Background** | Tier 2 & 3: VN30 ngoài watchlist, BCTC định kỳ, CBTT hành chính, thị trường chung | 2 × 100 (`--limit 200`) | Vẫn xử lý `full` 100%, chỉ xếp **thứ tự** sau. Phủ trọn kho dữ liệu |

Tổng = **3 mega-batch = 300 bài**, khớp nhịp hiện tại (~307 bài/ngày). Tier chỉ quyết **thứ tự chạy**, không quyết **độ sâu** (Q2 = 100% `full`), nên xếp thừa vào Tier 1 **không tốn thêm token** — chỉ làm W1 dài hơn.

### Cửa sổ giá — xếp lịch để tiết kiệm 50%

Peak = **08:00–11:00 và 13:00–17:00 giờ VN, Thứ 2–Thứ 6**. Mọi giờ khác là off-peak (rẻ bằng một nửa).

| Khung giờ VN | Việc nên chạy |
|---|---|
| 07:30–08:00 (off-peak) | **W1** — Tier 1, giao sớm |
| 08:00–11:00 (peak) | Chỉ W1 nếu trễ hạn. **Không** chạy bulk |
| 11:00–13:00 (off-peak) | **W2** nếu cần hai nhịp/ngày |
| 13:00–17:00 (peak) | Tránh bulk |
| sau 17:00 (off-peak) | **W2**, và chiến dịch backlog theo ngân sách riêng |

Tier 1 chấp nhận giá peak để đổi lấy độ trễ thấp — chỉ số "tỷ lệ chi phí off-peak" tính trên **bulk và backlog**, không tính trên tổng wave.

---

## 2. Quy trình một đợt — 3 bước của Conductor

### Bước 1 — Chuẩn bị (0 token model)

Trong `run_code`, gọi operator. **Cả hai tool call nằm trong MỘT assistant message ⇒ 1 bước.**

```ts
await tools.pwsh({ command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/article_run.py --today --wave W1-20260918 --batch 100 --limit 100', description: 'Chuẩn bị đợt W1' });
const prog = await tools.read({ file_path: 'project/data/agent_tasks/article/wave_W1-20260918.conductor.ts' });
return { prepared: true };
```

`article_run.py` (nửa chuẩn bị) làm, theo thứ tự:
1. Kiểm prefix hash so với catalog — lệch thì **dừng**, không mở đợt.
2. Gọi `article_pack.py --wave … --batch 100 --limit … --json`.
3. In: số bài, số bài Tier 1, số lô, dự toán quota (miss/hit/out), hash prefix, đường dẫn manifest.
4. Sinh chương trình PTC vào `project/data/agent_tasks/article/wave_<W>.conductor.ts`.

### Bước 2 — Chạy worker trong PTC (1 bước, tiêu token)

Dán **trọn** nội dung tệp `.conductor.ts` vào **MỘT** lệnh `run_code`. Không tách thành nhiều bước.

Chương trình sinh sẵn làm đúng bốn việc:

```text
readPacket(b)   đọc packet theo các cửa sổ dòng ĐÃ TÍNH SẴN (packet lớn hơn trần đọc
                nên phải phân trang; các lần đọc nằm trong cùng chương trình
                ⇒ không sinh thêm bước của mô hình, kết quả không vào ngữ cảnh)
runBatch(b)     tools.agent_article({ description, prompt: packet })
                → tools.write(data/agent_outputs_article/<batch_id>.output.json)
warm-up         BATCHES[0] chạy MỘT MÌNH trước để ghi bộ nhớ đệm cho prefix tĩnh
fan-out         các lô còn lại chạy song song theo `--concurrency` (mặc định 3)
return          CHỈ con số: { wave, batches, failed: [id…] }
```

**Bất biến của bước này:** dưới `mode: ptc`, kết quả sub-call **không** vào ngữ cảnh Conductor — chỉ vào log bền `tool/ptc-dispatch`. Nội dung packet và output của lô **không bao giờ** được vào ngữ cảnh. Đây là lý do `mode: ptc` của Conductor là bất biến R1: đổi sang `native` là output ~30.000 token mỗi batch rơi thẳng vào ngữ cảnh cha.

### Bước 3 — Hoàn tất, giao hàng, đo (0 token model)

Cùng một assistant message, gọi tuần tự:

```ts
await tools.pwsh({ command: '& "…python.exe" project/scripts/article_run.py --wave W1-20260918 --finish', description: 'Hoàn tất đợt W1' });
await tools.pwsh({ command: '& "…python.exe" project/scripts/write_user_output.py --date today', description: 'Giao Excel cho user' });
await tools.pwsh({ command: '& "…python.exe" project/scripts/token_ledger.py report --wave W1-20260918', description: 'Đọc sổ cái' });
return { done: true };
```

`--finish` chạy chuỗi: `article_expand.py` → (rc=1 ⇒ **dừng, không nạp DB**) → `l1_ingest.py data/agent_outputs_l1` → `agent_ingest.py data/agent_outputs` → `token_ledger.py append` (neo theo `created_epoch` của manifest) → `handoff.py` → `ctx_probe.py`.

**W2 lặp lại đúng ba bước với `--limit 200`.** Tổng một ngày: **6 bước Conductor** thay cho ~30 bước của luồng cũ.

---

## 3. Mẫu gọi đầy đủ trong ngày

```powershell
# ── Đợt W1 — Tier 1, giao sớm (nên chạy 07:30–08:00) ──────────────────
# Bước 1 (run_code): prepare
python scripts/article_run.py --today --wave W1 --batch 100 --limit 100
# Bước 2 (run_code): dán trọn wave_W1.conductor.ts
# Bước 3 (run_code): finish + giao hàng
python scripts/article_run.py --wave W1 --finish
python scripts/write_user_output.py --date today
python scripts/token_ledger.py report --wave W1

# ── Đợt W2 — Tier 2 & 3, 2 mega-batch (nên chạy sau 17:00) ────────────
python scripts/article_run.py --today --wave W2 --batch 100 --limit 200
# dán trọn wave_W2.conductor.ts
python scripts/article_run.py --wave W2 --finish
python scripts/write_user_output.py --date today
python scripts/token_ledger.py report --wave W2
```

**Chạy lại sau khi mất phiên:** `article_pack.py` tự loại bài đã có `l1_outputs.dod_pass = 1`, nên gọi lại `--wave W2 --resume` là an toàn — nó tự chọn nửa chuẩn bị hay nửa hoàn tất dựa trên số lô đã có output.

---

## 4. Đọc số — đo để nhìn, không để chặn

| Việc | Lệnh | Cho biết |
|---|---|---|
| Trạng thái pipeline | `python scripts/pipeline_radar.py status` | độ phủ L1 bài đăng hôm nay, hàng đợi kẹt, packet tồn |
| Sáu mục token | `python scripts/pipeline_radar.py token` | quota (hit/miss/out/reasoning) · USD theo cửa sổ giá · hit ratio · context Conductor · **sai số dự toán** · **phân rã context từng subagent (prefix hit / packet miss / output / turns)** |
| Sổ cái thô | `python scripts/token_ledger.py report --date today` | từng dòng đợt: miss/hit/out/reasoning, số bài, token/bài, sai số dự toán |
| Đối soát kế toán | `python scripts/token_ledger.py verify` | kiểm sáu luật kế toán trên log thật |
| Áp suất ngữ cảnh | `python scripts/ctx_probe.py` | `pressure / contextWindow` + khuyến nghị xanh/vàng/đỏ |

**Sáu luật kế toán phải nhớ khi đọc bất kỳ con số nào:**

1. `inputTokens` là **uncached input**, không phải kích thước prompt — đọc sai hụt ~30 lần.
2. Không bao giờ cộng `totalTokens` để lấy tổng phiên (nó theo từng request).
3. `reasoningTokens` là **tập con** của `outputTokens` — cộng cả hai là đếm trùng.
4. `cacheWriteTokens` **luôn 0** với DeepSeek.
5. DSH **không lưu giá tiền** — `billed_usd` tính ngoài từ tệp cấu hình giá.
6. `surfaceTokens = systemTokens + messageTokens`, **không** cộng `toolsTokens`.

**Quy kết chi phí của con:** con là Session riêng, burn của nó **không** nằm trong `tokenUsage` của cha. Chỉ đọc cha sẽ hụt phần lớn chi phí — ledger đã tự duyệt `subagentCatalog` và cộng projcache từng con.

**Ba chỉ số quan sát quan trọng nhất mỗi ngày:** `turns` của con **phải bằng 1** (lớn hơn ⇒ persona còn mời gọi `run_code`, xem §7) · `token/bài packet` (distillation là cần gạt chi phí số một) · `resolve_rate` theo từng nhóm, **miễn trừ `PER`** (nhóm `PER` chưa có `leaders.yaml`, mọi `PER` resolve thành `unlisted` là **đúng thiết kế**, đo bằng `per_discovery_count`).

---

## 5. Hai chốt tự động duy nhất (chỉ bảo vệ chất lượng)

| Chốt | Ngưỡng | Hành vi |
|---|---|---|
| `est_ctx_peak` | > 25% của 1M | `article_pack.py` **tự chia nhỏ batch**. Ở 100 bài/lượt, đỉnh là ~122.000 (12,2%), nên ngưỡng này chạm ở khoảng 210 bài — là lưới an toàn, không phải ràng buộc thường trực |
| `parse_fail` trong một đợt | > 10% | `article_expand.py` trả rc=1 ⇒ `--finish` **dừng trước khi nạp DB**. Xem lại persona rồi chạy lại **đúng các lô hỏng** |

**Ngưỡng áp suất ngữ cảnh Conductor** (cố ý thấp hơn nhiều so với ngưỡng compaction 80% của DSH, vì DSH **không cắt gì** trước 80%):

| Mức | Áp suất | Hành vi |
|---|---|---|
| 🟢 xanh | dưới 25% | chạy bình thường |
| 🟡 vàng | 25–40% | hoàn tất đợt đang chạy rồi **đóng phiên**, không mở đợt mới |
| 🔴 đỏ | trên 40% | dừng ngay sau batch hiện tại |

**Đóng phiên là thao tác bình thường, không phải chữa cháy.** Toàn bộ trạng thái nằm ở SQLite và file trên đĩa; `handoff.py` sinh `data/state/HANDOFF-<ts>.md` **0 token** từ DB, không nhờ LLM tóm tắt. Phiên mới: mở preset, đọc handoff, chạy `--resume`. Bộ nhớ đệm nằm ở phía nhà cung cấp nên mở phiên mới **không** mất cache prefix.

---

## 6. Van xả khi khối lượng vượt ngân sách

Q2 đã bỏ chế độ `lite`, nên cần gạt **không còn là giảm độ sâu**. Thứ tự dùng van, từ nhẹ tới nặng:

1. **Siết distillation** — hạ `--max-tokens-per-article` của `article_pack.py`. Mọi bài vẫn `full`, chỉ mang ít đoạn hơn. **Van chính, dùng trước.**
2. **Dời Tier 2–3 sang cửa sổ off-peak** hoặc sang hôm sau. Tier 1 vẫn chạy đúng hạn.
3. **Giảm `--batch`** nếu vấn đề là chất lượng chứ không phải chi phí.

Định mức tham chiếu (~1.220 token/bài, 100% `full`): 300 bài/ngày ≈ **0,10 USD off-peak** / 0,19 USD peak. Backlog 2.118 bài ≈ **0,65 USD off-peak**, chạy một lần, cũng ở chế độ `full` — không có lý do kinh tế nào để hạ chất lượng cho khoản đó.

---

## 7. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `turns` của con **> 1** | Persona đang **mời gọi** model viết chương trình: section `tools:sdk` (~600 token) kết thúc bằng `interface ToolArgsMap {}` **rỗng**, còn `tools:ptc-only` bảo *"reach every tool the SDK declares"* | `ARTICLE_SYSTEM_CORE` phải vô hiệu hoá tường minh (*"Bạn không có tool nào. Không gọi `run_code`. Không viết chương trình. Trả về một mảng JSON duy nhất trong thông điệp cuối."*) **và** nhắc lại ở **cuối packet**; rồi chạy lại đúng lô hỏng |
| Con trả lời kèm lời mở đầu/kết luận ⇒ `parse_fail` tăng | Prompt chưa đủ mạnh | `article_expand.py` salvage từng item; chỉ requeue **item** hỏng, không chạy lại cả lô |
| `SubagentDepthError` | `maxDepth` khai `0` | Phải là **`1`**. `0` cấm delegation hoàn toàn — con đầu tiên đã ở depth 1 nên `1 > 0` |
| Con gọi được tool ngoài ý muốn | `run_code` **luôn** được chèn sau lớp lọc `toolFilter`, và `restrict()` ném lỗi nếu cố đặt tên nó | Không thể đạt "0 tool". Tiêu chí đúng là **`sdkSchemas` rỗng** + **`turns == 1`**, in ra và lưu trace |
| Prefix lệch giữa hai lô | Đổi tool set / preset / model / effort trong phiên, hoặc compaction viết lại vùng surface | Không đổi gì trong phiên; `compaction-basic` để `auto: false` |
| Thinking bật lại | `.dsh/settings.yaml` khai `reasoningEffort: high` cho mọi con | Hook `agent/request` cưỡng chế; ledger kiểm `reasoningTokens` mỗi đợt |
| Nghi ngờ cấu hình không có hiệu lực | Khoá YAML gõ sai bị **bỏ qua im lặng** | Khẳng định **tập tool hiệu lực** và `sdkSchemas` ở runtime, **không tin YAML** |
| Không thấy `agent_article` trong SDK | Phiên sai preset | Xem §0 #1. Đây là nguyên nhân gốc của vệt 845K |
| `--finish` báo `chưa có đầu ra nào` | Chương trình PTC chưa chạy hoặc ghi sai `OUT` | Chạy bước 2; kiểm `data/agent_outputs_article/` |
| Output rỗng ở stdout `dsh --profile headless` | Không dùng trong phạm vi này (Q1 chốt PTC in-process) | — |

---

## 8. Bất biến vận hành

1. **Conductor bắt buộc `mode: ptc`.** Đổi sang `native` là output con rơi vào ngữ cảnh cha — sống lại đúng Lớp B.
2. **Một đợt = một mục tiêu = một phiên.** Xong đợt ⇒ handoff ⇒ đóng phiên.
3. **Một đợt = ít bước nhất có thể.** Không tách "kiểm tra trạng thái" thành bước riêng.
4. **LLM không đọc file, không ghi file, không tra catalog, không tự chấm DoD.**
5. **Code không quyết định thực thể hay tóm tắt** — chỉ so khớp, tra cứu, bung chỉ số, đo.
6. **Ràng buộc nào cưỡng chế được bằng máy thì không viết trong prompt.**
7. **Distillation chỉ được BỎ trọn một đoạn.** Cấm cắt, cấm nối, cấm sửa chữ, cấm đổi thứ tự. `p[k]` là chuỗi con nguyên văn của `cleaned_text`; kiểm bằng unit test của `article_pack.py`.
8. **Mọi script in dưới 2 KB.** Trần spill 50.000 byte; output nặng ghi ra đĩa, in một dòng trỏ đường dẫn. Không đọc lại tệp spill — đọc lại tính tiền như uncached input mới.
9. **Không chạm `raw_html`** (WORM). **Không mở lại cổng hỏi người** dưới bất kỳ tên nào.
10. **Đường cũ đóng băng nhưng gọi được** (in cảnh báo, không xoá) trong ít nhất một chu kỳ. Quay lui khi DoD pass < 95% **hoặc** `parse_fail` > 10%, kéo dài **hai đợt liên tiếp**.
