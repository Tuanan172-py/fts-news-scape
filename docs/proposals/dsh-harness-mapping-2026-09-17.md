# Đề xuất — Khung Harness DSH cho Mạng lưới Agent News-Scape

- **Trạng thái:** DRAFT — chờ Human duyệt (Hard Gate)
- **Phân loại:** **Cấp 3 — HIGH-RISK** (chạm Harness Core / automation substrate)
- **Ngày:** 2026-09-17
- **Nguồn chân lý đã đọc:** `.agents/registry.yaml`, `.agents/pipeline.yaml`, `.agents/AGENT_NETWORK_DESIGN.md`, `.agents/AGENT_RUNBOOK.md`, `.agents/rules/07`, `docs/SESSION-LATEST.md`, `docs/OPEN-ITEMS.md`, `project/scripts/pipeline_radar.py` (chạy thật).
- **Nguồn DSH đã đọc:** `@deepseek-ai/dsh-agent-presets`, `dsh-agent-tool-presentation`, `dsh-tools`, `dsh-tool-subagent`, `dsh-subagent-spawn-in-process`, `dsh-subagent-in-process-driver`, `dsh-skill-filesystem`, `dsh-code-runtime`, profile web tại `%DSH_HOME%\profiles\web`.
- **Ràng buộc:** đề xuất này KHÔNG sửa code, KHÔNG chạm `monocle.db`, KHÔNG mở story. Mọi thay đổi chờ ADR + Human duyệt.

---

## 0. Tóm tắt điều hành

News-Scape đã hoàn tất **3 xương sống dữ liệu** (Spine 1 Registry, Spine 2 Pipeline DAG, Spine 3 Agent Metrics) nhưng còn thiếu **runtime điều phối LLM**: `OPEN-ITEMS C2` xác nhận không module nào trong repo gọi API LLM, và `A0-6` ghi nhận `agy.exe --dangerously-skip-permissions` nằm ngoài repo, không pin version, không tái lập được. Hệ quả đo được ngay bây giờ: **163 batch L1 đang chờ Subagent thủ công**, 90 bài chưa route L1, Gold 0 bài chờ.

DeepSeek Harness (DSH) cung cấp đúng lớp runtime còn thiếu đó, và cung cấp ở dạng **khai báo (cordis YAML)**, khớp với triết lý "điều phối là dữ liệu" của dự án:

- **Subagent in-process** (`@deepseek-ai/dsh-tool-subagent`) thay thế `invoke_subagent` thủ công, có kiểm soát quyền tool theo từng con.
- **Agent Presets** (`@deepseek-ai/dsh-agent-presets`) cho conductor, mỗi preset là một composition riêng.
- **PTC mode** (`@deepseek-ai/dsh-agent-tool-presentation`) cho phép conductor điều phối nhiều bước trong **một round trip**, với `maxParallelSubCalls` làm van wave chống 429.
- **Skill Filesystem** đã tự động nhận `.agents/skills` (rank 200, project root = nearest `.git`) — 16 skill của dự án đã nằm trong catalog phiên này.
- **Hook pipeline** (`tools/pre-execute`, `guard`, `tools/result`) cưỡng chế bằng máy các bất biến WIP=1, Gate-before-advance, Metric-after-ingest.

**Đề xuất:** giữ nguyên `.agents/registry.yaml` + `.agents/pipeline.yaml` + `harness.db` làm nguồn chân lý; bổ sung một **tầng DSH sinh tự động** từ hai manifest, gồm: (a) host composition cho các operator tool, (b) preset conductor PTC, (c) một subagent instance cho mỗi cognitive agent với `toolFilter` 2-I/O + `persona` + model route. Không chuyển nguồn chân lý sang DSH.

**Trạng thái đóng phiên: BLOCKED tại Hard Gate.** Cần ADR + Human duyệt trước khi viết bất kỳ dòng code nào.

---

## 1. Bối cảnh và bằng chứng

### 1.1. Ba xương sống đã có

| Spine | File / bảng | Vai trò |
|---|---|---|
| 1 | `.agents/registry.yaml` | Khai báo mọi tác nhân: class, I/O boundary, model, DoD, KPI |
| 2 | `.agents/pipeline.yaml` | DAG stage, `needs`, `gate`, `wave` |
| 3 | `harness.db.agent_metrics` | LEDGER KPI per-agent nuôi `propose` |

Taxonomy bất biến (rule 07 §1): **operator** (0 token, Python tất định) · **cognitive** (LLM qua invoke_subagent) · **conductor** (đọc pipeline.yaml, quyết stage kế).

### 1.2. Khoảng trống đang chặn vận hành

| Mã | Khoảng trống | Bằng chứng |
|---|---|---|
| G3 | Điều phối nằm trong văn xuôi SKILL, con người phải nhớ thứ tự | `AGENT_NETWORK_DESIGN §2` |
| G4 | KPI chưa được nuôi tự động sau mỗi ingest | `registry.yaml` metric_hook mới là khai báo |
| C2 | **Không có runner LLM** — hàng đợi chỉ dài thêm | `OPEN-ITEMS C2` |
| A0-6 | `agy.exe` ngoài repo, `--dangerously-skip-permissions`, không pin version | `OPEN-ITEMS A0-6` |
| — | 163 batch L1 chờ Subagent; 90 bài chưa route L1 | `pipeline_radar.py status` chạy 2026-09-17 |

Nút thắt duy nhất còn lại của đường giao hàng là **tự động hóa lớp cognitive có kiểm soát**. Mọi thứ khác (operator, DoD, subscriber-gating, morphological guards) đã chín.

### 1.3. Điểm tích hợp đã hoạt động sẵn

`@deepseek-ai/dsh-skill-filesystem` quét root theo rank; **rank 200 = `<projectRoot>/.agents/skills`**, project root là tổ tiên gần nhất chứa `.git`. Repo news-scape có `.git` ở root, nên toàn bộ `.agents/skills/<name>/SKILL.md` **đã được DSH nạp thành catalog phiên** (đúng định dạng `<name>/SKILL.md`). Đây là bằng chứng tích hợp đã chạy, không phải giả thuyết.

---

## 2. Ánh xạ taxonomy News-Scape → DSH primitive

| Khái niệm News-Scape | DSH primitive | Cơ chế cưỡng chế |
|---|---|---|
| **operator** (0 token, script Python) | Global tool do plugin `@news-scape/dsh-harness` đăng ký (bọc lời gọi script), hoặc `pwsh` cho việc ad-hoc | `ToolRuntime.register` + `output.schema` (canonical JSON) |
| **cognitive** | Một instance `@deepseek-ai/dsh-tool-subagent` (provider `spawn`) cho mỗi agent | `toolFilter: {allow:[read,write]}` + `persona` + `agentOptions.model` + `maxDepth: 0` |
| **conductor** | Session mount preset `news-scape-conductor` | Preset scope + PTC + skill + goal |
| `registry.yaml` (Spine 1) | Nguồn sinh composition (`scripts/build_dsh_harness.py`) | Generator đọc YAML → emit cordis; generator fail nếu registry sai |
| `pipeline.yaml` (Spine 2) | Tool `ns_pipeline_next` + guard `Gate-before-advance` | Logic tất định trong plugin, không phải trí nhớ LLM |
| `agent_metrics` (Spine 3) | Waterfall `tools/result` + tool `ns_metric` | Hook ghi `harness.db` sau mỗi operator ingest |
| `dod_contract` | Operator `*_ingest` hiện hữu + guard chặn stage sau | Guard đọc kết quả ingest của ngày |
| `wave {batch, concurrency}` | `maxParallelSubCalls` (PTC) + `backgroundMode` subagent | Pool scheduler của `run_code` |
| WIP=1 | `tools/pre-execute` guard đọc `harness.db` | Từ chối khi đã có story `in_progress` |
| Tier-3 / ADR / Human duyệt | `dsh-plan-mode` + `ask_user_question` | Hard gate trước mutation |
| Rule 08 Zero-Probe | `ns_radar` là tool trinh sát duy nhất; cognitive bị cấm discovery tools | `toolFilter` + skill policy |
| `tools_allowed: [view_file, write_to_file]` | `toolFilter: {allow: [read, write]}` | Tool bị lọc biến mất khỏi prompt và bị từ chối thực thi |
| Rule 06 (docstring/AST) | `ns_gate` chạy `ast.parse` + pytest | Operator tool |
| `harness_cli.py trace/audit/propose` | Operator tool `ns_harness` | Nguyên trạng |

---

## 3. Kiến trúc đề xuất — 3 tầng

```
┌─────────────────────────── DATA PLANE (nguồn chân lý — KHÔNG đổi) ───────────────────────────┐
│  .agents/registry.yaml      .agents/pipeline.yaml      harness.db (story/trace/agent_metrics) │
│  .agents/skills/*/SKILL.md                                                                     │
└───────────────┬────────────────────────────────────────────────────────────────────────────────┘
                │ scripts/build_dsh_harness.py  (operator, 0 token, sinh tự động)
                ▼
┌─────────────────────────── HOST PLANE (profile web) ─────────────────────────────────────────┐
│  package.json bundles += @news-scape/dsh-harness                                              │
│  ├─ operator tools : ns_radar, ns_stage(run operator), ns_gate, ns_metric, ns_pipeline_next   │
│  ├─ subagent rows  : agent_l1, agent_gold, agent_dedup, agent_triage, agent_curator, ...      │
│  ├─ hooks          : guard(WIP), guard(gate-before-advance), waterfall(tools/result→metric)   │
│  └─ skills         : dsh-skill + dsh-skill-filesystem (rank 200 đã bắt .agents/skills)        │
└───────────────┬────────────────────────────────────────────────────────────────────────────────┘
                │ @deepseek-ai/dsh-agent-presets
                ▼
┌─────────────────────────── AGENT PLANE (per-session) ────────────────────────────────────────┐
│  preset news-scape-conductor  (mode: ptc, maxParallelSubCalls: 3)                             │
│    └─ spawn con in-process; con kế thừa composition + toolFilter/persona/model riêng          │
│  preset news-scape-native     (mặc định cho công việc code hằng ngày)                          │
│  preset news-scape-tier3      (plan-mode bắt buộc, write chỉ vào data/proposals/)              │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

Nguyên tắc: **DSH không thay thế nguồn chân lý; DSH là lớp thực thi sinh ra từ nguồn chân lý.** Sửa registry/pipeline là sửa hành vi harness, đúng rule 07 §2.

---

## 4. Khoá học: per-child subagent chính là ranh giới 2-I/O

DSH khác với trực giác "mỗi agent một preset". Theo `dsh-agent-presets`: **agent con join composition của cha**; preset chọn theo session, không theo subagent. Ranh giới per-child nằm ở **cấu hình instance subagent**:

```yaml
- id: ns-agent-l1
  name: '@deepseek-ai/dsh-tool-subagent'
  config:
    provider: spawn
    toolName: agent_l1
    persona: >-
      Bạn là l1-entity-matcher. Chỉ đọc task packet L1 và ghi output JSON theo
      l1-entity-output-v1. Không dùng tool discovery. Không suy đoán ngoài title.
    agentOptions: { provider: deepseek-official, model: deepseek-flash }
    toolFilter: { allow: [read, write] }
    maxDepth: 0
    backgroundMode: one-shot
```

- `toolFilter.allow: [read, write]` ⇒ mọi tool global khác (grep/glob/edit/pwsh/web/skill/...) **biến mất khỏi prompt và bị từ chối thực thi**. Trùng khớp tuyệt đối `tools_allowed: [view_file, write_to_file]`.
- `persona` ⇒ prompt vai trò riêng, không lẫn conductor.
- `agentOptions.model` ⇒ đúng model route trong registry (flash/flash-lite/pro).
- `maxDepth: 0` ⇒ cognitive không được sinh sâu thêm.
- Provider `spawn` có capability `persona` + `toolFilter` + `depthLimit` (driver in-process cài đặt per-child restriction cho schema, lookup, execution và cả SDK PTC).

**Hai lựa chọn cho cognitive:**

- **Option A (khuyến nghị): subagent in-process** — conductor spawn con với `toolFilter`/`persona`/`model`. Ưu: một process, một preset, đúng mô hình DSH, ghi event vào cùng session log. Nhược: con kế thừa mode PTC của cha.
- **Option B: mỗi cognitive là một session top-level với preset riêng** — cô lập mạnh hơn, model route riêng, native mode. Nhược: nhiều process, orchestration nặng, phải launch qua CLI.

Đề xuất: **A cho toàn bộ đường giao hàng hằng ngày**; dành **B cho agent Tier-3** (entity-curator) và specialist chạy dài (harness-auditor) nơi cô lập là yêu cầu bất biến.

---

## 5. Skeleton cấu hình

### 5.1. Host composition — operator tools (`@news-scape/dsh-harness`)

Plugin đăng ký tool qua `ctx.tools.register(defineTool(...))`. Tool có `output.schema` canonical nên giá trị trả về là JSON lossless cho chương trình PTC.

```yaml
- id: ns-operators
  name: '@news-scape/dsh-harness'
  config:
    venvPython: 'C:\venvs\news-scape\Scripts\python.exe'
    projectRoot: 'C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape\project'
    stages:            # ánh xạ stage id → CLI trong pipeline.yaml
      l1_route:   { cli: 'scripts/l1_route.py --from-db --date $DATE --mini-batch 25', write: true }
      l1_ingest:  { cli: 'scripts/l1_ingest.py data/agent_outputs_l1', write: true, gate: 'dod#l1' }
      gold_export:{ cli: 'scripts/agent_export.py --date $DATE --require-l1 --subscriber-only', write: true }
      gold_ingest:{ cli: 'scripts/agent_ingest.py data/agent_outputs', write: true, gate: 'dod#gold' }
      deliver:    { cli: 'scripts/write_user_output.py --date all', write: true }
```

Sinh các tool: `ns_radar` (pipeline_radar, read-only), `ns_stage` (chạy một operator allowlist), `ns_gate` (kiểm DoD trước khi cho stage sau), `ns_metric` (ghi `agent_metrics`), `ns_pipeline_next` (đọc DAG + trạng thái DB, trả stage kế tiếp).

### 5.2. Preset conductor (PTC)

`.agents/dsh/presets/news-scape-conductor/agent.cordis.yml` — cùng khuôn với `ptc` nhưng thêm operator tool và các subagent instance. Các điểm chính:

```yaml
- id: tool-presentation
  name: '@deepseek-ai/dsh-agent-tool-presentation'
  config:
    mode: ptc
- id: tools
  name: '@deepseek-ai/dsh-tools'
  config:
    maxParallelSubCalls: 3        # van wave L1 (registry: concurrency 3)
- id: ns-operators
  name: '@news-scape/dsh-harness'
- id: ns-agent-l1
  name: '@deepseek-ai/dsh-tool-subagent'
  config: { provider: spawn, toolName: agent_l1, toolFilter: { allow: [read, write] }, maxDepth: 0, ... }
- id: ns-agent-gold
  name: '@deepseek-ai/dsh-tool-subagent'
  config: { provider: spawn, toolName: agent_gold, toolFilter: { allow: [read, write] }, maxDepth: 0, ... }
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
```

Với PTC, conductor gọi trong một chương trình:

```ts
// 1 round trip: lấy stage kế, chạy wave, ingest, ghi metric
const next = await tools.ns_pipeline_next({ date: TODAY });
const batches = next.batches;
await Promise.all(batches.slice(0, 3).map(b =>
  tools.agent_l1({ prompt: b.handoff, ... })));   // trần 3 do maxParallelSubCalls
await tools.ns_stage({ stage: 'l1_ingest', date: TODAY });      // gate dod#l1
await tools.ns_metric({ agent: 'l1-entity-matcher', ... });     // Spine 3
return { ran: batches.length, next: 'gold_export' };
```

### 5.3. Generator — registry.yaml là nguồn duy nhất

`scripts/build_dsh_harness.py` (operator, 0 token):

1. Đọc `registry.yaml` + `pipeline.yaml`.
2. Sinh `.agents/dsh/gen/host.gen.cordis.yml` (một subagent row per cognitive).
3. Sinh `.agents/dsh/gen/preset-conductor.gen.cordis.yml` (danh sách subagent tool + wave từ `pipeline.yaml`).
4. Header mọi file sinh: `# GENERATED from .agents/registry.yaml — DO NOT EDIT`.
5. Fail loud nếu registry thiếu trường bắt buộc hoặc `pipeline.yaml` tham chiếu agent không tồn tại (drift G5).

Đây là cơ chế chống drift: sửa registry → chạy generator → harness đổi theo.

### 5.4. Hook cưỡng chế

| Hook | Bất biến | Hành vi |
|---|---|---|
| `ctx.tools.guard` (agent-scoped) | WIP=1 | Từ chối `write`/`ns_stage{write:true}` khi `harness.db` có story `in_progress` khác |
| `ctx.tools.guard` | Gate-before-advance | Từ chối `gold_export` khi `l1_ingest` của ngày chưa green |
| `tools/result` waterfall | Metric-after-ingest | Sau `ns_stage` có `gate`, gọi `ns_metric` |
| `tools/pre-execute` | Tier-3 | Với preset tier3, chặn write ngoài `data/proposals/*` |

### 5.5. Vị trí file và wiring

| Thành phần | Đường dẫn đề xuất |
|---|---|
| Plugin operator | `.agents/dsh/plugin/` (local bundle `@news-scape/dsh-harness`) |
| Preset conductor | `.agents/dsh/presets/news-scape-conductor/` |
| File sinh | `.agents/dsh/gen/` |
| Wiring profile | `%DSH_HOME%\profiles\web\package.json` → thêm bundle; hoặc `cordis.patch.yml` insert |
| Preset root | thêm root trỏ `.agents/dsh/presets` qua config `dsh-agent-presets.roots` |

Lưu ý: profile hiện compose `@deepseek-ai/dsh-base` + `@deepseek-ai/dsh-web-app`; một bundle local cần được cài vào workspace của profile. Phương án nhẹ hơn là chỉ dùng `cordis.patch.yml` + preset user-root, không cần bundle.

---

## 6. Workflow pipe L1 → Gold trên DSH

```
radar (ns_radar)  ─┐
l1_route (ns_stage)│ operator
   ▼
agent_l1  ── wave 3 song song ──► 163 batch × 25 title
   ▼
l1_ingest (ns_stage, gate dod#l1) ──► ns_metric(l1-entity-matcher)
   ▼
[optional] agent_triage · agent_dedup
   ▼
gold_export (ns_stage)
   ▼
agent_gold ── wave 2 song song ──► batch × 5 bài
   ▼
gold_ingest (ns_stage, gate dod#gold) ──► ns_metric(gold-financial-analyst)
   ▼
deliver (ns_stage) ──► users/output/<user>/<date>.xlsx
   ▼
[optional] agent_brief (daily-brief-synthesizer)
```

Đối chiếu trực tiếp với `pipeline.yaml`; conductor chỉ đọc DAG + trạng thái DB, không tự bịa thứ tự.

---

## 7. Bảng ánh xạ bất biến → cơ chế cưỡng chế

| Bất biến (rule) | Enforcer trong DSH | Ghi chú |
|---|---|---|
| 2-I/O, cấm discovery tools (rule 01) | `toolFilter.allow` | Bị từ chối ở tầng execute, không chỉ prompt |
| WIP=1 (rule 04) | `guard` agent-scoped | Fail closed |
| Controlled Wave chống 429 | `maxParallelSubCalls` + `backgroundMode` | Trần cứng theo pool |
| Gate-before-advance | `guard` + `ns_pipeline_next` | Dữ liệu, không trí nhớ |
| Metric-after-ingest (rule 07 §5) | `tools/result` waterfall | Ghi `harness.db` |
| No Script Emulation (rule 05 §3) | Kiến trúc: cognitive là LLM subagent, operator là tool riêng | Ranh giới vật lý |
| Zero-Probe (rule 08) | `ns_radar` + skill policy + `toolFilter` | Một cửa trinh sát |
| Tier-3 + ADR | `plan-mode` + `ask_user_question` + guard write proposals | Hard gate |
| Token budget | `compaction-basic` + `tool-result-pruner` + `ns_metric tokens` | Đo và cắt |
| An toàn subprocess | DSH sandbox thay `--dangerously-skip-permissions` | Xử lý `A0-6` |

---

## 8. Lộ trình (khớp P1–P4 của `AGENT_NETWORK_DESIGN`)

| Giai đoạn | Nội dung DSH | Proof |
|---|---|---|
| **H1 — Đọc-only** | Mount `news-scape-native` + operator tool `ns_radar`/`ns_pipeline_next`. Chưa spawn LLM. | Conductor gợi ý đúng stage kế cho 3 ngày dữ liệu; không chạm DB |
| **H2 — Cognitive L1** | Thêm `agent_l1`, chạy wave 3 batch thật, ingest, ghi metric | 75 bài DoD pass; `agent_metrics` có dòng; so `tokens_per_item` với budget 450 |
| **H3 — Gold + gate** | Thêm `agent_gold`, guard gate-before-advance, hook metric | Gold pass; guard chứng minh chặn được export khi L1 chưa green |
| **H4 — Governance** | WIP guard, tier3 preset, harness-auditor tự động | Guard WIP bắt 2 story in_progress; proposal tự sinh |

Mỗi giai đoạn = 1 Story US-XXX + proof + trace; agent mới giữ `status: draft` tới khi đủ 5 bước rule 07 §4.

---

## 9. Rủi ro, anti-scope, câu hỏi cho Human

### Rủi ro
1. **Phụ thuộc runtime ngoài repo** — chính là bài học `A0-6`. Khắc phục: pin version DSH, ghi vào `requirements`/profile, tài liệu hoá cách cài.
2. **Trùng lặp hai hệ điều phối** — nếu vừa `agy.exe` vừa DSH chạy, sinh tranh chấp. Khuyến nghị tắt `auto_pilot.py` khi H2 xanh.
3. **Child kế thừa PTC** — cognitive con phải gọi tool qua `run_code`. Cần xác nhận chất lượng output của flash dưới PTC cho tác vụ 2-I/O; fallback là Option B.
4. **Model route** — cần chốt model id cho `pro`/`flash-lite`.
5. **24 file treo working tree** — commit trước khi thêm thay đổi harness.

### Anti-scope (không làm)
- Không chuyển `registry.yaml`/`pipeline.yaml`/`harness.db` sang DSH.
- Không viết lại operator Python thành plugin.
- Không tự động hoá Tier-3 khi chưa có ADR.
- Không xoá rule/skill hiện có.

### Câu hỏi cần Human quyết
1. Duyệt đi tiếp theo Option A (subagent in-process) hay B (session per-agent)?
2. Chấp nhận DSH là runtime chính thức (pin version) và tắt `agy.exe`?
3. Model route cho từng cognitive agent?
4. Bundle local hay chỉ `cordis.patch.yml`?
5. Giai đoạn H1 có được phép chạy read-only trên DB vận hành?

---

## 10. ADR draft (khung)

```
# ADR 0007 — Dùng DeepSeek Harness làm runtime điều phối mạng lưới agent

Status: proposed
Date: 2026-09-17
Context:  Ba spine dữ liệu đã chín nhưng thiếu runtime cognitive (C2); auto_pilot.py
          phụ thuộc agy.exe ngoài repo, skip permissions (A0-6).
Decision: Dùng DSH (agent presets + in-process subagent + PTC + hooks) làm runtime điều
          phối. registry.yaml/pipeline.yaml/harness.db giữ vai trò nguồn chân lý; harness
          được SINH từ chúng. Operator giữ nguyên script, bọc thành tool.
Consequences:
  + Tự động hoá invoke_subagent có kiểm soát 2-I/O, có sandbox.
  + Wave/gate/WIP/metric cưỡng chế bằng máy.
  + Skill dự án đã tự động nạp (rank 200).
  - Thêm phụ thuộc runtime ngoài repo; phải pin version.
  - Child kế thừa PTC của cha.
Alternatives: (a) giữ agy.exe; (b) tự viết runner LLM; (c) subagent in-process (chọn).
```

---

## 11. Phụ lục — package DSH sử dụng

| Package | Vai trò |
|---|---|
| `dsh-agent-presets` | Chọn composition theo session |
| `dsh-agent-tool-presentation` | Bật PTC mode cho conductor |
| `dsh-tools` | Registry + `maxParallelSubCalls` + hook pipeline |
| `dsh-tool-subagent` + `dsh-subagent-spawn-in-process` + `dsh-subagent-in-process-driver` | Cognitive agent |
| `dsh-tool-subagent-control` | Liệt kê/điều khiển child |
| `dsh-skill` + `dsh-skill-filesystem` + `dsh-tool-skill` | Nạp `.agents/skills` |
| `dsh-plan-mode` | Hard gate Tier-3 |
| `dsh-goal` + `dsh-tool-goal` + `dsh-command-goal` | Objective dài hạn cho conductor |
| `dsh-tool-workflow` + `dsh-workflow-worker-thread` | Fan-out có cấu trúc (tuỳ chọn) |
| `dsh-tool-ralph` | Vòng lặp đặc nhiệm (tuỳ chọn) |
| `dsh-compaction-basic` + `dsh-compaction-tool-result-pruner` | Ngân sách context |
| `dsh-tool-fs` + `dsh-tool-fs-search` | `read`/`write` cho 2-I/O |
| `dsh-tool-ask-user`, `dsh-tool-todo`, `dsh-tool-web`, `dsh-tool-present` | Hỗ trợ |

---

*Tài liệu này là đề xuất, chưa được duyệt, chưa kích hoạt bất kỳ thay đổi code nào.*