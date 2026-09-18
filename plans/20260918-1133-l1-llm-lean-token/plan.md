# Plan — Tối ưu token tầng L1 theo hướng LLM-first (Lean Lane)

|  |  |
| --- | --- |
| Ngày | 2026-09-18 |
| Trạng thái | **SUPERSEDED** — thay thế bởi [plan hợp nhất 20260918-1651-article-lane-unified](../20260918-1651-article-lane-unified/plan.md). Giữ làm hồ sơ thiết kế nền (MDR, expander 0 token, catalog digest). |
| Phân loại | **Cấp 2 — NORMAL** (Thiết kế nền móng cho MDR, Expander 0-token và Catalog Digest) |
| Kế hoạch thay thế | [Plan 20260918-1445-article-lane-scale-token](../20260918-1445-article-lane-scale-token/plan.md) (Master Plan: Unified Article Processor, Mega-batch 100, Priority-Queue, Dual-Track Intent) |
| Ràng buộc chủ đạo | **Trọng tâm vẫn là LLM xử lý nội dung** — Toàn bộ các phát minh cốt lõi (MDR, Expander 0 token, Prefix Caching nhóm đóng) đã được kế thừa trọn vẹn vào Agent hợp nhất |
| Quyết định sáp nhập (2026-09-18) | Theo chỉ đạo mới: Không còn tách riêng tầng L1 và GOLD nữa; chuyển thành 1 Agent duy nhất xử lý cả tiêu đề (thực thể/intent) và nội dung theo hàng đợi Mega-batch 100 bài/batch. |

> **Định vị:** Bản kế hoạch này giữ vai trò tài liệu thiết kế nền tảng (Foundational Architecture) cho cơ chế tách rời ngữ nghĩa khỏi cơ học. Mọi luồng triển khai thực tế được điều phối qua Master Plan `20260918-1445-article-lane-scale-token`.

---

## 0. Cổng phê duyệt

Plan này **không tự triển khai**. Thứ tự cổng:

1. Anh duyệt plan này.
2. **Phase 00 (baseline instrumentation)** là read-only/đo lường — được chạy ngay sau khi duyệt.
3. **Phase 01 trở đi** đụng prompt + ghi file output: vẫn tuân thủ **ADR 0008** (hiển thị số batch, số bài, ước lượng token; trần token/batch; thất bại phải ồn ào).
4. Mọi lần activate LLM vẫn qua cổng cấp quyền theo plan DSH (H2+) — plan này không mở cổng mới.

Ngoài phạm vi: không đổi `l1-entity-output-v1.schema.json`, không đổi hàm `check_l1_dod`, không chạm `raw_html`.

---

## 1. Mục tiêu / Phi mục tiêu

**Mục tiêu**

- Giảm 4 ổ đốt token của đường L1: (1) fixed overhead mỗi agent, (2) context gửi lại mỗi lượt, (3) catalog exploration, (4) output boilerplate.
- Vẫn để **LLM đọc title và quyết định thực thể** (surface, entity_id, type, in_list) cho 100% bài `needs_agent`.
- Đưa chi phí về ≤ **350 token/bài** để 1.000 bài/ngày nằm trong trần ~350k token.
- Đo lường **token thật** thay cho hằng số ước lượng `450` trong radar.

**Phi mục tiêu (anti-scope — xem §10)**

- Không mở rộng code-first / không hạ tỷ lệ `needs_agent`.
- Không dùng model local, không luật tất định cho phần nhận diện.
- Không đổi schema/DB/DoD.

---

## 2. Hiện trạng: 4 ổ đốt token (đo trên batch 25 bài, 2026-09-17)

| # | Ổ đốt | Cơ chế | Ước lượng/batch 25 bài |
|:-:|---|---|---:|
| 1 | Fixed overhead | system prompt + tool schema + skill/schema nạp lại mỗi agent | ~12–20k |
| 2 | Context gửi lại mỗi lượt | mỗi tool call gửi lại toàn transcript (O(n²)), ~10–15 lượt | ~300–400k (chi phối) |
| 3 | Catalog exploration | đọc `entities.json` + grep khi agent tự dò từ điển | ~12–15k |
| 4 | Output boilerplate | LLM tự sinh categories/citations/metadata cho full schema | ~8k output (~320 token/bài) |

**Hệ quả:** chi phí thật cao hơn benchmark `450 token/bài` của `pipeline_radar.py` (dòng 449) **1–2 bậc độ lớn**. Đo lường sai là rủi ro gốc cần xử lý trước.

---

## 3. Nguyên tắc thiết kế

1. **Tách "quyết định ngữ nghĩa" khỏi "cơ học".**
   LLM = quyết định thực thể. Orchestrator/script tất định = nạp luật, tra cứu, đóng gói, kiểm tra.
2. **Phân biệt Retrieval vs Code-first.**
   - *Code-first (không dùng cho phần nhận diện):* script quyết định tag cuối cùng.
   - *Retrieval (được phép, cơ học):* script chỉ **thu hẹp từ điển** để LLM khỏi tự dò file; LLM vẫn là bên quyết định. Plan mặc định để **LLM tự adjudicate**; retrieval chỉ là tùy chọn tăng tốc (§CE-3).
3. **Một gói vào, một gói ra.** Không vòng lặp khám phá, không đọc lại file, không validation trong LLM.
4. **Phần tất định không đi qua LLM.** Boilerplate schema không bao giờ do model sinh.
5. **Đo trước, tối ưu sau.** Phase 00 luôn chạy trước.

---

## 4. Kiến trúc đích — Lean Lane

```text
[Orchestrator — 0 token]
  ├─ Cắt batch titles (25–50) + state tĩnh (rules + catalog digest)
  ├─ Inline thẳng batch vào user message (KHÔNG để agent gọi read)
  └─ Prefix tĩnh MARK CACHE (rules + digest) | đuôi động (batch) — byte-identical qua các batch
        │
        ▼
[L1 Lean Worker — LLM, deepseek-flash]
  toolFilter: {read?, write}         ← chỉ 1–2 tool, bỏ web/job/skill/subagent
  system: L1_SYSTEM_CORE (~700 token, inject sẵn; KHÔNG đọc SKILL.md/schema)
  output: Minimal Decision Record (chỉ surface + entity_id + type + in_list)
        │
        ▼
[expander — 0 token]
  scripts/expand_l1.py: MDR + packet → l1-entity-output-v1 đầy đủ
  (categories qua TYPE_GROUP, citations = surface, metadata, title, timestamp)
        │
        ▼
[l1_ingest.py — gate DoD, item-level retry]
```

Chế độ **warm worker** (tùy chọn Phase 04): một agent instance nhận lần lượt K batch; prefix cache giữ phần tĩnh, orchestrator **compaction** phần batch cũ sau mỗi lần ghi.

---

## 5. Đòn bẩy theo từng ổ

### A. Fixed overhead (FO)

| Mã | Đòn bẩy | Cơ chế | Tiết kiệm ước tính |
|:-:|---|---|---:|
| FO-1 | Slim agent profile | `toolFilter` chỉ `read`/`write`; bỏ tool schema ngoài phạm vi | ~12k → ~1k |
| FO-2 | Inject `L1_SYSTEM_CORE` | Luật 10 miền + anti-FP nén ~700 token, orchestrator nhúng vào prompt; bỏ đọc SKILL.md (4.7k) + schema/instructions (3.2k) | ~8k → 0.7k |
| FO-3 | Warm worker | 1 agent chạy K=4–8 batch; bỏ respawn | chia đều fixed/K |
| FO-4 | Prefix caching | Prefix tĩnh (system+digest) byte-identical; batch động đặt cuối | giảm billable input các lượt sau |
| FO-5 | Batch 25–50 | Amortize fixed còn lại; không vượt ngưỡng chất lượng | — |

### B. Context resend (CR)

| Mã | Đòn bẩy | Cơ chế | Tiết kiệm ước tính |
|:-:|---|---|---:|
| CR-1 | Inline batch vào prompt | Orchestrator đưa 25 title thẳng vào user message; bỏ tool `read` | bớt 1–2 lượt + bớt re-send packet |
| CR-2 | JSON-only / structured output | Cấm văn xuôi suy luận; chỉ phát MDR | cắt output narrative |
| CR-3 | Context compaction | Sau mỗi batch, thay (packet+output cũ) bằng stub 1 dòng trong warm session | chặn tăng context |
| CR-4 | Item-level retry | Expander/validator chấm **từng item**; chỉ requeue item lỗi, không chạy lại batch | tránh đốt lại cả batch |
| CR-5 | Bỏ validation loop trong LLM | DoD chấm ngoài; cấm read-back file | bớt 1–3 lượt |

### C. Catalog exploration (CE)

| Mã | Đòn bẩy | Cơ chế | Tiết kiệm ước tính |
|:-:|---|---|---:|
| CE-1 | Cấm discovery tools | `toolFilter` không có grep/list/glob | triệt tiêu |
| CE-2 | Catalog digest tĩnh | 8 `MACRO_GEO` + 9 `MACRO_THEME` + 7 `ASSET_CLASS` + 7 `INSTITUTION` + `INDEX`/`EXCHANGE` nén ~150 dòng (~1.2k token) trong prefix | ~12k → ~1.2k (cached) |
| CE-3a | Ticker digest (mặc định) | Alias Tier-1 (watchlist + large cap) nén; còn lại LLM tự đánh `in_list=false` | không cần grep |
| CE-3b | Retrieval shortlist (tùy chọn) | Quét literal alias trên title để tạo shortlist ứng viên; **LLM adjudicate** | giảm suy luận, KHÔNG thay LLM |

### D. Output boilerplate (OB)

| Mã | Đòn bẩy | Cơ chế | Tiết kiệm ước tính |
|:-:|---|---|---:|
| OB-1 | Minimal Decision Record | LLM phát `{"i":0,"e":[["surface","ENTITY_ID","TYPE",in_list]]}`; bỏ categories/citations/metadata/confidence/echo title | ~320 → ~80–120 token/bài |
| OB-2 | `expand_l1.py` | Sinh full `l1-entity-output-v1` tất định từ MDR + packet | 0 token |
| OB-3 | Compact JSON | Không indent, không field thừa | 10–20% output |

### Tổng hợp mục tiêu

| Chỉ số | Trước | Sau (mục tiêu) |
|---|---:|---:|
| Fixed overhead/agent | ~12–20k | ~2–3k |
| Lượt tool/batch | ~10–15 | 2–3 |
| Catalog exploration/batch | ~12–15k | ~0 (digest cached) |
| Output/bài | ~320 | ~80–120 |
| **Token/batch 25 bài** | **~300–400k** | **~10–20k** |
| **Token/bài (đường LLM)** | ~12.000–16.000 | **≤350** |

**Chiếu 1.000 bài/ngày (toàn bộ qua LLM):** ~200–350k token/ngày — nằm trong trần ~350k, thay vì vỡ trần như hiện tại. Với trần activate L1 60k (ADR 0008) cần ~4–6 lần activate/ngày.

---

## 6. Các phase

| Phase | Tên | Phụ thuộc | Token | Ghi file |
|:-:|---|---|:-:|:-:|
| 00 | Baseline instrumentation (đo token thật) | plan duyệt | 0 thay đổi hành vi | `agent_metrics`/log |
| 01 | Slim profile + rules-in-prompt + JSON-only | 00 | flash | output |
| 02 | Catalog digest + khóa discovery tools | 01 | flash | — |
| 03 | MDR + `expand_l1.py` + item retry | 02 | flash | `scripts/expand_l1.py` |
| 04 | Warm worker + prefix caching + compaction | 03 | flash | prompt/config |
| 05 | Budget guard + circuit breaker + dashboard | 04 | flash | `pipeline_radar.py` |

### Phase 00 — Baseline instrumentation
- Ghi `usage` (input/output/cached) thật của mỗi lần gọi agent vào `agent_metrics`.
- Sửa `pipeline_radar.py token`: cộng **số thật**; giữ hằng số 450 chỉ làm fallback.
- **Acceptance:** report token thật cho 1 batch 25 bài; sai số so với hằng số >50% được nêu rõ.

### Phase 01 — Slim profile + rules-in-prompt + JSON-only
- Tạo `L1_SYSTEM_CORE` (~700 token); orchestrator nhúng vào handoff.
- `toolFilter` chỉ `write` (batch inline) — hoặc `read` nếu giữ packet file.
- Ràng buộc JSON-only.
- **Acceptance:** 1 batch 25 bài, số tool call ≤3, DoD pass 100%, token giảm ≥50% so baseline.

### Phase 02 — Catalog digest + khóa discovery
- Sinh digest tĩnh từ `entities.json` (đọc 1 lần lúc build), nhúng vào prefix cache.
- Cấm mọi discovery tool.
- Chốt CE-3a vs CE-3b (§11).
- **Acceptance:** 0 grep/entities read trong runtime; catalog token ≈ digest size.

### Phase 03 — MDR + expander + item retry
- Định nghĩa MDR + `scripts/expand_l1.py` (có unit test).
- `l1_ingest.py`: chấm item-level, requeue item lỗi.
- **Acceptance:** output token giảm ≥50%; DoD pass 100%; expander round-trip == output cũ về ngữ nghĩa.

### Phase 04 — Warm worker + prefix caching + compaction
- Một agent xử lý K batch; ngắt/compaction sau mỗi lần ghi.
- **Acceptance:** K=4 batch, fixed overhead/bài giảm ≥60%; không tràn context.

### Phase 05 — Budget guard
- Trần token/batch + trần/ngày + circuit breaker; vượt trần dừng sạch, báo phần đã làm.
- **Acceptance:** mô phỏng vượt trần → dừng sạch, có log.

---

## 7. Chỉ số & ngân sách

| Chỉ số | Ngưỡng |
|---|---|
| Token/bài đường LLM | ≤ 350 |
| Token/batch 25 bài | ≤ 20k |
| Tool call/batch | ≤ 3 |
| DoD pass lần đầu | ≥ 99% item |
| Lần activate/ngày (trần 60k) | ≤ 6 cho 1.000 bài |
| Tỷ lệ bài đi đường LLM | 100% `needs_agent` (không tăng code-first) |

---

## 8. Instrumentation

- Thêm trường đo: `tokens_in`, `tokens_out`, `tokens_cached`, `tool_calls`, `batch_size`, `duration_ms` theo từng lần gọi agent.
- `pipeline_radar.py token` đọc bảng thật; cảnh báo khi lệch benchmark >50%.
- Cảnh báo khi >25% bài đi Gold (theo skill `token-auditor`) và khi packet >20 KB.

---

## 9. Rủi ro & đối sách

| Rủi ro | Đối sách |
|---|---|
| Provider không hỗ trợ prefix caching | Vẫn cắt turns; chấp nhận ~1.5–2x mục tiêu; warm worker bù |
| Warm session phình context | Compaction bắt buộc sau mỗi batch; giới hạn K |
| MDR thiếu thông tin → expander lỗi | Unit test round-trip; validator item-level; fallback full-schema mode (chỉ khi lỗi) |
| Digest thiếu alias → mất recall | CE-2 tĩnh + CE-3 shortlist; review lại sau batch |
| Structured output không được hỗ trợ | Ép "JSON only" + parser nghiêm; retry item lỗi |
| Batch lớn làm giảm chất lượng | Trần 50 bài/batch; kiểm DoD lần đầu |

---

## 10. Anti-scope

- **Không mở rộng code-first**, không hạ tỷ lệ `needs_agent`, không dùng luật thay LLM cho nhận diện.
- Không dùng model local/NER ngoài họ flash (theo D6 của plan DSH).
- Không đổi `l1-entity-output-v1`, không đổi `check_l1_dod`, không đổi schema DB.
- Không chạm `raw_html` (WORM).
- Không spawn nhiều agent song song vượt "Controlled Wave" (2–3 batch/đợt) để tránh 429.

---

## 11. Câu hỏi mở

| # | Câu hỏi | Mặc định đề xuất |
|:-:|---|---|
| 1 | Kích thước batch L1 | 25 (giữ nguyên), thử 50 ở Phase 04 |
| 2 | Ticker: CE-3a (digest) hay CE-3b (retrieval shortlist) | CE-3a trước; CE-3b nếu recall thấp |
| 3 | Trần token/batch | 20k; trần/ngày theo ADR 0008 |
| 4 | Warm worker sống bao lâu / K | K=4 batch, compaction sau mỗi batch |
| 5 | Có dùng JSON mode của provider không | Có, nếu hỗ trợ; nếu không ép JSON-only |

---

## 12. Nghiệm thu chung

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest tests/ -q      # giữ >= baseline passed
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token
```

Mỗi phase trả đủ **Unit + Integration + Platform**. Phase 00 có bằng chứng **số token thật**; Phase 03 có bằng chứng **round-trip expander**.

---

## 13. Liên hệ drift cần đồng bộ (ngoài phạm vi plan, ghi nhận)

- `news-scape-agent-operations` nói `MACRO_GEO:EU`/`DONG_NAM_A` **không có** trong DB, nhưng `entities.json` thực tế **có** (dòng 33225/33298).
- Skill nói `MACRO_THEME` "không có khóa categories", nhưng `l1_router.TYPE_GROUP` map `MACRO_THEME → macro_geo`.
- Đề xuất: lấy `entities.json` + `TYPE_GROUP` làm source-of-truth và cập nhật lại mẫu prompt trong skill (có thể gộp vào Phase 01/02).

