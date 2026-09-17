# Plan — Tích hợp DeepSeek Harness (DSH) làm runtime điều phối News-Scape

|              |                                                                                                                                                                                                 |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ngày        | 2026-09-17                                                                                                                                                                                      |
| Trạng thái | **DRAFT — chưa implement** (chờ anh duyệt plan; H1 chỉ được chạy read-only)                                                                                                                    |
| Phân loại  | **Cấp 3 — HIGH-RISK** (chạm Harness Core / automation substrate)                                                                                                                               |
| Nền tảng    | `.agents/registry.yaml`, `.agents/pipeline.yaml`, `.agents/AGENT_NETWORK_DESIGN.md`, ADR 0006/0007/0008, plan `plans/20260917-1420-pipeline-integrity-remediation` |
| Đề xuất gốc | `docs/proposals/dsh-harness-mapping-2026-09-17.md` (đã được anh đồng ý phần lớn mapping)                                                                                              |
| Câu hỏi mở | Xem §9 — chưa chốt thì chưa code phase tương ứng                                                                                                                                               |

## 0. Cổng phê duyệt

Plan này **không tự triển khai**. Thứ tự cổng:

1. Anh duyệt plan này (và ADR 0009 dự kiến).
2. H1 (read-only trên DB vận hành): **anh đã phê duyệt quyền**, chờ duyệt plan để bắt đầu.
3. H2 trở đi (tiêu thụ token): phải qua **cổng cấp quyền ADR 0008** tại từng lần chạy.

## 1. Mục tiêu

Đưa DSH vào làm **runtime điều phối** cho mạng lưới agent đã khai báo ở `.agents`, sao cho:

- Tự động hoá `invoke_subagent` có kiểm soát (thay thao tác thủ công), đúng Option A — subagent in-process.
- Giữ nguyên **nguồn chân lý**: `registry.yaml` + `pipeline.yaml` + `harness.db`. DSH được SINH từ chúng, không thay thế.
- Cưỡng chế bằng máy các bất biến: 2-I/O, WIP=1, Gate-before-advance, Metric-after-ingest, demand-driven (Q5), human-in-the-loop + trần token (ADR 0008).
- Chạy được **toàn bộ quy trình công việc ngày 17/09** trên DB vận hành khi được duyệt.

**Không phải mục tiêu:** thay operator Python, đổi schema `monocle.db`, thay `harness.db`.

## 2. Quyết định đã chốt (từ anh, 2026-09-17)

| # | Nội dung | Hệ quả kéo theo |
|:-:|---|---|
| **D1** | **Option A** — subagent in-process (`provider: spawn`) | Ranh giới per-agent nằm ở `toolFilter` + `persona` + `agentOptions`, KHÔNG phải preset riêng |
| **D2** | Đường mặc định dùng DSH; **bỏ A0-6** (`agy.exe --dangerously-skip-permissions`) | `auto_pilot.py` KHÔNG bị xoá — giữ như **option thay thế có thể thực thi**, chỉ không còn là mặc định; mọi runner đều phải qua ADR 0008 |
| **D4** | H1–H2 wiring bằng `cordis.patch.yml`; H3–H4 đóng gói bundle local `@news-scape/dsh-harness` | H1–H2 chỉ dùng package shipped + skill; tool operator có định kiểu đến ở H3 |
| **D5** | Duyệt H1 read-only trên DB vận hành; nghiên cứu sâu để DSH thực thi toàn bộ workflow 17/09; được phép hành động trên DB vận hành trong phạm vi được duyệt | H1 có acceptance riêng (§Phase 01); H2+ vẫn cần cổng token |
| **D6** | **Chỉ dùng model trong họ DeepSeek Flash 4.1** — tức `deepseek-flash` (`DeepSeek-V41-Flash`); **cấm`deepseek-v4-pro`** vì chi phí | Mọi route agent = `deepseek-official/deepseek-flash`; các agent `pro` trong registry phải hạ tầng hoặc tạm `deferred` |

### Hệ quả D6 lên registry (bắt buộc, rule 07)

Bốn agent đang khai `model: pro` — `entity-curator`, `adversarial-dod-verifier`, `daily-brief-synthesizer`, `harness-auditor` — **không được chạy ở tầng pro**. Chọn một:

- (a) Hạ tất cả về `model: flash` và ghi chú "chất lượng kiểm chứng sau"; hoặc
- (b) Giữ `status: draft` và `deferred` tới khi có thiết kế chạy được trên flash.

Plan chọn **(b) cho Tier-3 `entity-curator`** (chạm Data Contract) và **(a) cho ba QA/brief**. Cần một dòng amendment trong `registry.yaml` + trace.

## 3. Ràng buộc bắt buộc (không thoả hiệp)

1. **ADR 0008 §2.1** — trước mọi lần gọi runner LLM: hiển thị số batch, số bài, ước lượng token, chế độ effort; mặc định HỎI; chỉ chạy thẳng khi người vận hành gõ cờ tường minh.
2. **ADR 0008 §2.3** — trần token/batch mỗi lần chạy; vượt trần dừng sạch và báo cáo phần đã làm.
3. **ADR 0008 §2.4** — thất bại phải ồn ào; không "hoàn tất 100%" vô điều kiện.
4. **Q5 demand-driven** — producer chỉ sản xuất khi consumer sắp chạy, đúng số lượng sắp tiêu thụ. DSH conductor KHÔNG được sinh packet trước.
5. **D6 model** — chỉ `deepseek-flash`.
6. **WIP=1** (AGENTS.md §1) — một story `in_progress` tại một thời điểm.
7. **2-I/O** (rule 01) — cognitive child chỉ `read`/`write`, cấm discovery tools.
8. **Không chạm `raw_html`** — WORM.
9. **Backup `monocle.db`** trước mọi thao tác ghi lần đầu.

## 4. Kiến trúc đích

```
DATA PLANE (nguồn chân lý, không đổi)
  .agents/registry.yaml · .agents/pipeline.yaml · harness.db · .agents/skills
        │  (H3: scripts/build_dsh_harness.py sinh composition từ hai manifest)
        ▼
HOST PLANE (profile web — cordis.patch.yml ở H1–H2, bundle @news-scape/dsh-harness ở H3–H4)
  H1–H2: package shipped (fs, pwsh, jobs, skills, subagent) + preset conductor
  H3–H4: + ns_radar · ns_stage · ns_gate · ns_metric · ns_pipeline_next
         + guard(WIP) · guard(gate-before-advance) · waterfall(metric)
         + agent_l1 · agent_gold · agent_* (toolFilter + persona + model flash)
        ▼
AGENT PLANE
  preset news-scape-conductor  (PTC, maxParallelSubCalls = 3)
  preset news-scape-native     (công việc code hằng ngày)
  preset news-scape-tier3      (plan-mode, chỉ ghi data/proposals)
```

## 5. Ánh xạ stage 17/09 → DSH

| # | Stage | Class | Cơ chế DSH | Cổng | Token |
|:-:|---|---|---|---|:-:|
| 1 | scrape / derive | operator | morninger chạy nền (ngoài DSH) | — | 0 |
| 2 | l1_route | operator | `pwsh` → `l1_route.py` (demand-driven, chỉ resolved) | — | 0 |
| 3 | l1_match | cognitive | `agent_l1` (Option A) | dod#l1 | flash |
| 4 | l1_ingest | operator | `pwsh` → `l1_ingest.py` | ✔ | 0 |
| 5 | triage/dedup (draft) | cognitive | `agent_triage`/`agent_dedup` | dod#triage/dedup | flash |
| 6 | gold_export | operator | `agent_export.py` | — | 0 |
| 7 | gold_analyze | cognitive | `agent_gold` | dod#gold | flash |
| 8 | gold_ingest | operator | `agent_ingest.py` | ✔ | 0 |
| 9 | deliver | operator | `write_user_output.py` | — | 0 |
| 10 | daily_brief (draft) | cognitive | `agent_brief` | dod#brief | flash |
| G | governance | cognitive | `agent_auditor` | — | flash |

## 6. Các phase

| Phase | Tên | Phụ thuộc | Token | DB write |
|:-:|---|---|:-:|:-:|
| 01 | [H1 — Read-only conductor](phase-01-h1-readonly-conductor.md) | plan duyệt | không | không |
| 02 | [H2 — L1 cognitive pilot](phase-02-h2-l1-cognitive.md) | H1 | flash | có (qua ingest) |
| 03 | [H3 — Gold + hard gate + bundle](phase-03-h3-gold-gates-bundle.md) | H2 | flash | có |
| 04 | [H4 — Governance + toàn workflow](phase-04-h4-governance-full-workflow.md) | H3 | flash | có |

## 7. Cổng cấp quyền ADR 0008 trên DSH

Runner cognitive bị chặn sau một cổng hiển thị:

```text
[ACTIVATE] l1_match · wave 3 × 25 bài · model deepseek-flash · ước lượng ~34k token
Batches: l1_batch_<ts>_01..03   Effort: low
Xác nhận chạy? (y/N)
```

- H1: chưa có runner nên chưa cần cổng.
- H2: cổng bằng `ask_user_question` + skill conductor (policy). Chưa hard-enforce được vì chưa có plugin.
- H3: cổng bằng tool `ns_activate` trong bundle (hard-enforce): trả CONFIRM_REQUIRED, chỉ spawn khi có xác nhận; ghi log.
- Luôn có trần: `max_batches` và `token_budget`; vượt thì dừng sạch.

Lưu ý môi trường: phiên DSH hiện có **approval prompts đang tắt**, nên không dùng approval seam; dùng `ask_user_question` + tool gate của bundle.

## 8. Chính sách model (D6)

| Agent | Registry hiện | Route DSH |
|---|---|---|
| l1-entity-matcher | flash | `deepseek-official/deepseek-flash` |
| gold-financial-analyst | flash | `deepseek-official/deepseek-flash` |
| materiality-triage | flash-lite | `deepseek-flash` |
| story-dedup-clusterer | flash | `deepseek-flash` |
| adversarial-dod-verifier | pro | hạ về `flash` (chất lượng kiểm chứng ở H4) |
| daily-brief-synthesizer | pro | hạ về `flash` |
| harness-auditor | pro | hạ về `flash` |
| entity-curator | pro, Tier-3 | **deferred** tới khi có thiết kế flash + ADR |

## 9. Câu hỏi mở cần chốt

1. Chốt §2 (a)/(b) cho 4 agent `pro` — plan đề xuất (b)+(a) (xem §2 Hệ quả D6).
2. H2 chạy PTC ngay hay chạy native trước rồi mới PTC? Plan đề xuất PTC, có fallback native.
3. Ngưỡng trần token mặc định mỗi lần activate (đề xuất: L1 60k, Gold 40k).
4. Có giữ `agy` song song ở H2 để đối chứng chất lượng flash hay không?
5. 163 packet L1 cũ: archive trước H2 (theo phase-02 remediation) — xác nhận thao tác.

## 10. Nghiệm thu chung

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest tests/ -q      # giữ >= 435 passed
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
```

Mỗi phase trả đủ **Unit + Integration + Platform**. H1 có thêm bằng chứng **DB không đổi** (hash trước/sau).

## 11. Không làm (anti-scope)

- Không chuyển `registry.yaml`/`pipeline.yaml`/`harness.db` sang DSH.
- Không xoá `auto_pilot.py`/`agy` — chỉ bỏ khỏi đường mặc định.
- Không dùng model ngoài họ flash 4.1.
- Không tự động hoá cognitive khi chưa có xác nhận người.
- Không chạm `raw_html`.
- Không implement khi plan chưa được duyệt.
