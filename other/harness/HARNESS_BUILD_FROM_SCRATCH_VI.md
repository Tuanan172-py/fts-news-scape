# Xây Harness Tùy Biến Từ Đầu — Guide Thiết Kế & Thực Thi Từng Bước (VI)

> Mục tiêu tài liệu: hướng dẫn **tự tay dựng một harness mới hoàn toàn** cho một
> agent/dự án mới tinh — KHÔNG kéo nguyên repo harness cũ về — mà chỉ mượn **định
> hướng nền tảng** (triết lý, mô hình, thứ tự) từ khung harness tham chiếu.
>
> Tài liệu này là bản đúc kết sau khi nghiên cứu sâu 3 tầng của khung harness
> tham chiếu: **policy docs**, **durable layer (SQLite + CLI)**, và **contract +
> decisions**. Đọc kèm `docs/HARNESS_RUNBOOK_VI.md` (cách vận hành hằng ngày).

---

## Phần 0 — Đọc tài liệu này thế nào

Tài liệu có 7 phần, đi từ **tư duy → lộ trình → thứ tự viết file → thiết kế dữ
liệu → checklist thực thi → cạm bẫy → quyết định cần ghi**.

Nếu bạn chỉ có 5 phút: đọc **Phần 1** (triết lý), **Phần 2** (lộ trình H1→H5), và
**Phần 5** (checklist). Phần 3–4 là chi tiết để thực sự bắt tay làm.

Nguyên tắc bao trùm toàn bộ guide:

> **Harness lớn dần từ friction, không dựng sẵn top-down.**
> Bắt đầu bằng phần nhỏ nhất chạy được (H1, thuần markdown, KHÔNG database), chỉ
> thêm tầng mới khi một công việc thật để lộ khoảng trống. Đừng dựng H5 khi chưa
> có một trace nào.

---

## Phần 1 — Tư duy nền tảng: Harness là gì, để làm gì

### 1.1 Định nghĩa

> **App is what users touch. The harness is what agents touch.**

Harness = **hệ điều hành cấp repo** biến *ý định con người* thành *thay đổi sản
phẩm an toàn, có bằng chứng*. Nó KHÔNG phải là code sản phẩm. Nó là lớp kỷ luật
bao quanh: phân loại việc, chọn ngữ cảnh, ghi lại điều đã xảy ra, chứng minh, và
tự cải tiến.

Một yêu cầu có thể sinh 2 loại output:
- **Product delta** — code, test, API, schema, docs sản phẩm.
- **Harness delta** — docs/template/backlog/decision làm lần sau dễ hơn.

### 1.2 Sáu nguyên tắc thiết kế (xương sống mọi quyết định)

| # | Nguyên tắc | Ý nghĩa khi dựng |
|---|------------|------------------|
| 1 | **Tách Policy ↔ Durable** | Markdown giữ *cách làm việc* (rule, vocab, template). Database giữ *điều đã xảy ra* (intake, story, trace). Đừng nhét state sống vào markdown. |
| 2 | **Grows from friction** | Không thiết kế đủ mọi thứ trước. Gặp đau → ghi lại → lặp lại nhiều → mới nâng cấp. |
| 3 | **Proof-driven** | "Chưa có bằng chứng = chưa implemented." Mọi claim phải có proof cơ học (test/lệnh verify). |
| 4 | **Request-class authority gate** | Phân loại yêu cầu TRƯỚC: read-only không được đổi state; chỉ change/build/fix mới được mutate. High-risk phải dừng hỏi người. |
| 5 | **Bounded context** | Chỉ đọc đúng ngữ cảnh phase + lane cần. Không nhồi tối đa. Có ngân sách token. |
| 6 | **Verifiable maturity** | Một cấp độ chỉ "đạt" khi kiểm chứng được trong file/DB/benchmark. Không tự khen. |

Ý phụ quan trọng: **degrade-don't-fail** — năng lực tùy chọn thiếu là *một sự
kiện được báo cáo*, không phải lỗi chặn đứng. Harness lõi vẫn chạy mượt trên máy
trắng.

### 1.3 Mục tiêu & kỳ vọng

**Mục tiêu** của một harness tốt:
1. Một agent mới, không biết dự án, đọc `AGENTS.md` là biết *phải làm gì trước*.
2. Không bao giờ có thay đổi repo mà không phân loại rủi ro.
3. Không bao giờ claim "xong" mà không có bằng chứng.
4. Mọi lần chạy để lại dấu vết (trace) cho lần sau.
5. Khi lặp đau, harness tự đề xuất sửa chính nó (giai đoạn trưởng thành).

**Kỳ vọng thực tế:** v0 của bạn sẽ **thô** và **thuần markdown**. Điều đó ĐÚNG.
Compliance 20–40% ở H1 là mục tiêu khởi đầu hợp lệ. Database đến sau.

---

## Phần 2 — Lộ trình trưởng thành H0 → H5 (bản đồ đường đi)

Đây là mô hình tiến hóa. **Mỗi cấp chỉ leo khi cấp dưới đã vận hành thật.** Mỗi
cấp *kích hoạt* thêm trách nhiệm mới.

```
H0  Bare        : prompt vào → patch ra. Không harness. (điểm xuất phát)
      │  + viết policy tĩnh
      ▼
H1  Scaffolding : rule tĩnh, template, risk lane, source-of-truth.
      │           THUẦN MARKDOWN, KHÔNG DATABASE.  ← v0 của bạn dừng ở đây trước
      │  + thêm durable layer
      ▼
H2  Durable     : SQLite + CLI ghi intake/story/decision/backlog/trace.
      │           + component taxonomy, trace spec, context rules.
      │  + đo lường
      ▼
H3  Active Obs. : chấm điểm trace, friction gom theo component,
      │           backlog dự đoán-vs-thực tế.
      │  + tự động hóa verify
      ▼
H4  Auto-Verify : story có verify_command, cổng verify trước khi close.
      │  + tự cải tiến
      ▼
H5  Self-Improve: audit entropy + propose (rule-based, có bằng chứng) +
                  đo outcome, người duyệt mọi high-risk.
```

**Diễn giải 1 câu:** *policy tĩnh (H1) → ghi điều đã xảy ra (H2) → đo nó (H3) →
chặn theo bằng chứng (H4) → để harness tự đề xuất sửa mình, người duyệt (H5).*

**Bảng file bắt buộc theo cấp:**

| Cấp | File/hạ tầng mới xuất hiện |
|-----|---------------------------|
| **H1** | `AGENTS.md`, `docs/HARNESS.md`, `docs/FEATURE_INTAKE.md`, `docs/ARCHITECTURE.md`, `docs/TEST_MATRIX.md`, `docs/GLOSSARY.md`, `docs/templates/{story,decision,validation-report}.md` |
| **H2** | CLI + `scripts/schema/001-init.sql`, `docs/HARNESS_COMPONENTS.md`, `docs/HARNESS_MATURITY.md`, `docs/TRACE_SPEC.md`, `docs/CONTEXT_RULES.md` |
| **H3** | scoring trace (`score-trace`/`score-context`), friction-by-component, backlog outcome loop |
| **H4** | `docs/TOOL_REGISTRY.md`, story `verify_command`, cổng verify khi trace |
| **H5** | `docs/HARNESS_AUDIT.md`, `docs/IMPROVEMENT_PROTOCOL.md`, `propose`, intervention |

> **Khuyến nghị mấu chốt:** Dựng **trọn H1 trước**, vận hành vài công việc thật,
> rồi mới quyết định có cần H2 (database) không. Rất nhiều dự án nhỏ sống tốt ở
> H1 thuần markdown.

---

## Phần 3 — Thứ tự VIẾT FILE (chi tiết, kèm logic/mục tiêu/kỳ vọng)

Đây là phần "viết file nào trước, file nào sau". Thứ tự KHÔNG tùy tiện — nó theo
quan hệ phụ thuộc ngữ nghĩa: *vocabulary trước → entrypoint → luật phân loại →
luật ngữ cảnh → template → (rồi mới) durable*.

### TẦNG H1 — Thuần markdown (làm 100% trước khi nghĩ tới database)

#### File 1 — `docs/GLOSSARY.md`  *(viết ĐẦU TIÊN)*
- **Logic:** Mọi file sau đều mượn từ vựng ở đây. Không có glossary, các doc sau
  sẽ định nghĩa chồng chéo, mâu thuẫn.
- **Nội dung tối thiểu:** định nghĩa *Agent, Harness, Product Contract, Story
  Packet, Feature Intake, Trace, Durable Layer, Risk Lane (tiny/normal/high-risk)*.
- **Mục tiêu:** một từ = một nghĩa duy nhất trong toàn dự án.
- **Kỳ vọng:** ngắn (1–2 trang), sẽ lớn dần khi thêm khái niệm.

#### File 2 — `AGENTS.md`  *(entrypoint — cổng vào duy nhất)*
- **Logic:** Đây là file agent đọc ĐẦU TIÊN mỗi phiên. Nó phải **chọn request
  class trước khi làm bất cứ gì**. Giữ nó NHỎ và ỔN ĐỊNH (shim), trỏ sang các doc
  chi tiết.
- **Nội dung tối thiểu:** lệnh build/run dự án; **## Harness** section với luật
  vàng: *read-only → chỉ đọc, không mutate; change → intake trước*.
- **Mục tiêu:** agent lạ đọc xong biết ngay "tôi được phép đổi repo hay không".
- **Kỳ vọng:** đây là hợp đồng authority. Đừng nhồi chi tiết vào; trỏ đi.
- **Lưu ý CC:** Claude Code không auto-load `AGENTS.md`. Nếu dùng CC, thêm dòng
  `@AGENTS.md` trong `CLAUDE.md` để import.

#### File 3 — `docs/HARNESS.md`  *(mô hình cộng tác người ↔ agent)*
- **Logic:** Giải thích vòng đời end-to-end: intent → intake → story → work loop
  → product delta → proof → harness delta. Định nghĩa **Request-Class Loops**
  (read-only vs change 8 bước) và **Done Definition**.
- **Mục tiêu:** khung tư duy chung; nơi mọi người tra "quy trình chuẩn là gì".
- **Kỳ vọng:** đây là doc "hiến pháp". Ổn định, ít sửa.

#### File 4 — `docs/FEATURE_INTAKE.md`  *(máy phân loại rủi ro)*
- **Logic:** Cổng phân loại. Định nghĩa **input types**, **risk checklist**,
  **luật chọn lane** (0–1 flag→tiny/normal; 2–3→normal; 4+→high-risk; hard gate→
  high-risk), và **yêu cầu từng lane**.
- **Mục tiêu:** con người KHÔNG cần tự xếp rủi ro — harness làm, xác định được.
- **Kỳ vọng:** kết thúc intake, agent nói được: `Lane / Reason / Docs / Story /
  Validation`.

#### File 5 — `docs/ARCHITECTURE.md`  *(luật ranh giới của SẢN PHẨM)*
- **Logic:** Đây là doc DUY NHẤT nói về *sản phẩm sẽ xây*, không phải về harness.
  Dùng **Discovery-Before-Shape** (khám phá surfaces/stack/domains/validation
  ladder trước khi định hình) và **Dependency Rule** (lớp trong không phụ thuộc
  lớp ngoài).
- **Mục tiêu:** agent biết "code mới đặt ở đâu, được phụ thuộc cái gì".
- **Kỳ vọng:** ở dự án mới, phần lớn là câu hỏi khám phá chưa có lời đáp — chấp
  nhận được. Điền dần khi có code thật.

#### File 6 — `docs/TEST_MATRIX.md`  *(từ vựng bằng chứng)*
- **Logic:** Định nghĩa status enum **planned / in_progress / implemented /
  changed / retired** và 4 tầng proof **Unit / Integration / E2E / Platform**,
  cùng luật vàng *"chưa có evidence thì chưa implemented"*.
- **Mục tiêu:** ngôn ngữ chung để nói về tiến độ + bằng chứng.
- **Kỳ vọng:** ở H1 đây là bảng markdown tay; ở H2 nó chuyển vào DB (`query
  matrix`) và file này chỉ còn giữ *vocabulary*.

#### File 7–9 — Templates  *(khuôn tái sử dụng)*
Viết 3 khuôn cốt lõi (bỏ qua khuôn nâng cao lúc đầu):
- `docs/templates/story.md` — **quan trọng nhất**. Sections: Title (US-XXX),
  Status, Lane, Product Contract, Acceptance Criteria, Design Notes, bảng
  Validation (Unit/Integration/E2E/Platform), Harness Delta, Evidence.
- `docs/templates/decision.md` — ADR: Context, Decision, Alternatives,
  Consequences (Positive/Tradeoffs), Follow-Up. Status khớp enum
  Proposed/Accepted/Superseded/Rejected.
- `docs/templates/validation-report.md` — Scope, Commands Run, bảng Results
  (mặc định "not run"), Evidence, Gaps.

**Khuôn nâng cao — để sau (chỉ khi cần lane high-risk):**
`docs/templates/spec-intake.md` (onboard cả spec lớn) và thư mục
`docs/templates/high-risk-story/{overview,design,execplan,validation}.md`.

#### File 10 — `docs/HARNESS_BACKLOG.md`  *(bồn chứa friction)*
- **Logic:** Nơi ghi "năng lực harness còn thiếu" khi đang làm mà chưa muốn đổi
  quy trình ngay. Fields: Title, Discovered While, Current Pain, Suggested
  Improvement, Risk (lane), Status.
- **Mục tiêu:** hiện thực nguyên tắc "grows from friction" ngay từ ngày đầu.
- **Kỳ vọng:** ở H2+ chuyển vào DB (`backlog` table); file này còn giữ template.

> **Chốt H1:** Sau 10 file này bạn đã có một harness CHẠY ĐƯỢC, không cần dòng
> code nào. Vận hành thật vài công việc. Ghi friction. Chỉ leo H2 khi bảng
> markdown bắt đầu đau (khó query, dễ sai, mất observability).

---

### TẦNG H2 — Thêm Durable Layer (chỉ khi markdown đã đau)

Trước khi viết code, viết 4 doc định nghĩa tầng durable:

#### File 11 — `docs/CONTEXT_RULES.md`  *(đọc đúng, đủ, biết dừng)*
- **Logic:** Ma trận **phase × lane** (Intake/Planning/Implementation/Validation/
  Trace) mỗi ô Must/Should/Skip, + **ngân sách token** (tiny ~2K, normal ~5K,
  high-risk ~10K), + **retrieval triggers**.
- **Mục tiêu:** ngăn agent nhồi context vô tội vạ; context selection đo được.

#### File 12 — `docs/TRACE_SPEC.md`  *(chuẩn bằng chứng để lại)*
- **Logic:** 3 tier **Minimal(1)/Standard(2)/Detailed(3)** map theo lane; định
  nghĩa từng field trace (`task_summary`, `outcome`, `actions_taken`,
  `files_read/changed`, `harness_friction`...).
- **Mục tiêu:** trace hữu ích cho review + benchmark + tự cải tiến sau này.

#### File 13–14 — `docs/HARNESS_COMPONENTS.md` + `docs/HARNESS_MATURITY.md`
- **Logic:** Components = **11 trách nhiệm runtime** (task spec, context, tool
  access, memory, task state, observability, failure attribution, verification,
  permissions, entropy audit, intervention). Maturity = định nghĩa H0–H5.
- **Mục tiêu:** dùng làm *lăng kính thiết kế* ("v0 của tôi đã phủ task-spec /
  context / memory / verification chưa?") và *thước đo trưởng thành*.
- **Kỳ vọng:** dùng checklist 11 trách nhiệm ngay cả ở H1 để tự soi thiết kế.

#### Rồi mới tới CODE — CLI + Schema (xem Phần 4 cho thứ tự bảng)
- `scripts/schema/001-init.sql` + một CLI mỏng thao tác DB.
- Quyết định lớn: **ngôn ngữ/engine**. Khung tham chiếu chọn **Rust prebuilt
  binary + SQLite** (xem quyết định 0004, 0005). Bạn có thể chọn khác (Python +
  SQLite, Go + embedded...) MIỄN LÀ giữ: queryable, an toàn ghi đồng thời, phân
  phối không bắt consumer cài toolchain.

---

### TẦNG H3–H5 — Nâng cao (thêm khi có đủ dữ liệu để đo)

- **H3:** `score-trace`, `score-context`, gom friction theo component, backlog
  dự-đoán-vs-thực-tế.
- **H4:** `docs/TOOL_REGISTRY.md` (outbound manifest + inbound registry + degrade
  ladder), story `verify_command`, cổng verify khi trace.
- **H5:** `docs/HARNESS_AUDIT.md` (6 drift check có trọng số → entropy score),
  `docs/IMPROVEMENT_PROTOCOL.md` (friction+intervention+audit → propose → người
  duyệt 1 key → outcome loop), bảng `intervention`.

> `HARNESS_AUDIT.md` và `IMPROVEMENT_PROTOCOL.md` là **cao cấp nhất** — máy tự sửa
> mình, vô nghĩa khi chưa có records tích lũy. Đừng viết sớm.

---

## Phần 4 — Thiết kế DURABLE LAYER: mô hình dữ liệu & thứ tự bảng

Chỉ đọc phần này khi bạn đã quyết leo H2. Đây là "viết bảng nào trước" ở tầng DB.

### 4.1 Năm bảng lõi (migration 001 — đủ để VẬN HÀNH)

| Bảng | Vai trò | Cột chính |
|------|---------|-----------|
| `schema_version` | Sổ ghi migration đã áp | `version PK`, `applied_at` |
| `intake` | Phân loại việc đến | `input_type`(CHECK enum), `summary`, `risk_lane`, `risk_flags`(JSON), `story_id`(soft) |
| `story` | Gói việc + proof (TRÁI TIM) | `id TEXT PK` (US-XXX), `status`(enum), `unit/integration/e2e/platform_proof`(INTEGER 0/1), `evidence` |
| `decision` | ADR bền vững | `id TEXT PK`, `status`(enum), `doc_path`, `predicted_impact`, `actual_outcome` |
| `trace` | Observability mỗi lần chạy | `task_summary`, `intake_id`→intake, `story_id`→story, `actions/files_*`(JSON), `outcome`(enum) |

`backlog` cũng ở 001 nhưng là vòng tự-cải-tiến — hữu ích sớm, không bắt buộc để
*vận hành*.

### 4.2 Sơ đồ quan hệ (lõi)

```
   intake ──intake_id──▶ trace ◀──story_id── story
     │(story_id soft)      │                   ▲
     │                     ▼                    │(FK từ nhiều bảng nâng cao)
     └····▶ story    intervention (FK→trace)   │
                                                │
   decision (độc lập)      backlog (độc lập ở v0)
```
Ghi nhớ: `trace` là bảng đầu tiên có **FK thật** (vào `intake` + `story`).
`intake.story_id` và `intervention.story_id` là **soft link** (TEXT, không FK).

### 4.3 Thứ tự dựng bảng (theo phụ thuộc — QUY TẮC CỨNG)

1. `schema_version` **trước hết** + bật `PRAGMA journal_mode=WAL`,
   `foreign_keys=ON`.
2. `story` — là **đích FK của nhiều bảng nhất**. Không gì tham chiếu story được
   phép có trước nó.
3. `intake` — bị `trace.intake_id` tham chiếu; dựng trước trace.
4. `decision`, `backlog` — độc lập, không FK vào ở v0.
5. `trace` — SAU `intake` + `story` (FK thật vào cả hai).
6. `intervention` — SAU `trace` (FK vào `trace.id`).
7. `tool`, `changeset_applied` — hạ tầng độc lập, lúc nào cũng được.
8. `story_dependency`, `story_hierarchy` — SAU `story` (self-join many-to-many).
9. **(nâng cao)** Chỉ mục UNIQUE trên `uid` phải có **TRƯỚC** mọi bảng tham chiếu
   `backlog(uid)` — SQLite FK cần parent index unique.

> Quy tắc một dòng: **`story` trước mọi thứ tham chiếu nó; `intake`+`story` trước
> `trace`; `trace` trước `intervention`.**

### 4.4 Bảng nâng cao (thêm dần khi trưởng thành)
`tool` (+ scan columns) → nhận biết tool · `intervention` → giám sát ·
`changeset_applied` (+ sha) → phân phối content pack idempotent ·
`story_dependency`/`story_hierarchy` → đồ thị công việc · cụm `uid` +
`proposal_evidence_link` + `backlog_outcome_observation` + `audit_evidence_
episode` + `legacy_evidence_snapshot` + `story_backlog_link` → hệ học khép kín
(chỉ đáng làm khi chạy nhiều trace và muốn *chứng minh* cải tiến có tác dụng).

### 4.5 CLI: bề mặt lệnh tối thiểu
Nhóm theo mối quan tâm: `init/migrate` · `intake` · `story add/update/verify/
complete` · `decision add` · `backlog add/close` · `trace`/`score-trace` ·
`query matrix/stories/traces/...`. Đọc-chỉ tách biệt mutate.

### 4.6 Hợp đồng process (nếu có orchestrator ngoài)
Nếu bạn muốn agent/tool bên ngoài lái CLI: áp dụng khung **discovery-before-
mutation** — lệnh đầu tiên `query contract` trả `protocol_version`, dải schema,
`database_state`, `capabilities`; consumer *verify chứ không suy từ semver*. Mỗi
lệnh in **đúng 1 JSON**; nhánh theo **exit code + `error.code`** chứ không theo
message. Mutation timeout = *kết quả không xác định* → re-query state, không giả
định rollback. Đây là ý tưởng nền tảng; format cụ thể có thể khác.

---

## Phần 5 — Checklist thực thi cho agent MỚI TINH (làm theo thứ tự)

### Giai đoạn A — Dựng H1 (một buổi, thuần markdown)
```
[ ] A1. Tạo cây thư mục:  docs/  docs/templates/  docs/stories/  docs/decisions/
[ ] A2. Viết docs/GLOSSARY.md            (từ vựng lõi)
[ ] A3. Viết AGENTS.md                    (entrypoint + ## Harness authority gate)
[ ] A4. Viết docs/HARNESS.md              (vòng đời + read-only vs change loop + Done)
[ ] A5. Viết docs/FEATURE_INTAKE.md       (input types + risk checklist + lane rule)
[ ] A6. Viết docs/ARCHITECTURE.md         (Discovery-Before-Shape + Dependency Rule)
[ ] A7. Viết docs/TEST_MATRIX.md          (status enum + proof layers + "no proof=not done")
[ ] A8. Viết 3 template: story/decision/validation-report
[ ] A9. Viết docs/HARNESS_BACKLOG.md      (bồn friction)
[ ] A10. (CC) Thêm @AGENTS.md vào CLAUDE.md
[ ] A11. TỰ SOI bằng 11-responsibility checklist (Components):
         đã phủ task-spec / context / memory / verification chưa?
```

### Giai đoạn B — Vận hành thật & thu friction (vài ngày–tuần)
```
[ ] B1. Chạy 3–5 công việc thật qua đúng quy trình intake→story→proof.
[ ] B2. Mỗi lần đau/lặp/mơ hồ → ghi 1 dòng vào HARNESS_BACKLOG.md.
[ ] B3. Cuối tuần review: markdown đã đau chưa? (khó query / dễ sai / mất dấu vết)
        → CHƯA đau: ở lại H1.  ĐÃ đau: sang C.
```

### Giai đoạn C — Leo H2 (chỉ khi B3 nói "đã đau")
```
[ ] C1. Viết CONTEXT_RULES.md + TRACE_SPEC.md
[ ] C2. Viết HARNESS_COMPONENTS.md + HARNESS_MATURITY.md
[ ] C3. Quyết định engine/ngôn ngữ CLI + ghi 1 decision record (vì sao)
[ ] C4. Viết schema 001 (5 bảng lõi) theo thứ tự Phần 4.3
[ ] C5. Dựng CLI mỏng: init/migrate/intake/story/trace/query
[ ] C6. Chuyển bảng markdown TEST_MATRIX → query matrix; docs chỉ giữ vocab
[ ] C7. Ghi decision "SQLite/Durable layer" + "prebuilt binary" nếu áp dụng
```

### Giai đoạn D — Leo H3→H5 (khi có đủ trace để đo)
```
[ ] D1. score-trace/score-context; gom friction theo component        (H3)
[ ] D2. TOOL_REGISTRY.md; story verify_command; cổng verify khi trace  (H4)
[ ] D3. HARNESS_AUDIT.md (entropy) + IMPROVEMENT_PROTOCOL.md (propose)  (H5)
```

---

## Phần 6 — Cạm bẫy & anti-pattern (học từ thiết kế tham chiếu)

| Anti-pattern | Vì sao sai | Làm đúng |
|--------------|-----------|----------|
| Dựng database ngay từ ngày 1 | H2 vô nghĩa khi chưa có công việc thật để lộ nhu cầu | H1 markdown trước, DB khi đau |
| Nhét state sống vào markdown | Bảng tay dễ sai, không query được, mất observability | State → durable layer; markdown giữ *rule* |
| Coi trace text = decision record | Trace là *evidence*, không *chứng minh* có bản ghi bền | High-risk: BẮT BUỘC cả file `decisions/NNNN.md` + row durable |
| `story update --status implemented` | Bỏ qua proof tươi | Chỉ `story complete` (chạy proof + atomic) mới sang implemented |
| Viết IMPROVEMENT_PROTOCOL/AUDIT sớm | Máy tự sửa mình khi chưa có dữ liệu = rỗng | Đợi đủ trace/records tích lũy |
| Đọc mọi doc mỗi phiên | Phá bounded-context, tốn token | Đọc theo phase×lane, có ngân sách |
| Proposal tự động apply | Harness tự viết lại policy không kiểm soát = scope creep | `propose` chỉ advisory, người duyệt 1 key |
| Suy khả năng tương thích từ semver | Version cao ≠ có capability bạn cần | `query contract`: verify protocol+schema+capabilities |
| Bootstrap/mutate khi chỉ được hỏi | Vi phạm authority gate | Read-only → chỉ đọc, tuyệt đối không đụng DB |

---

## Phần 7 — Những QUYẾT ĐỊNH cần ghi lại khi dựng (decision records)

Khi dựng harness riêng, các lựa chọn sau nên có `docs/decisions/NNNN-*.md`:

1. **Harness-first hay code-first?** (tham chiếu: quyết định 0001 chọn
   harness-first — dựng mô hình vận hành trước code).
2. **Spec là hạt giống hay kế hoạch sống?** (0002/0003: coi spec là *input lịch
   sử*, sau đó mọi việc re-enter qua intake; giữ harness stack-neutral, tái dùng
   được).
3. **Durable layer: engine gì?** (0004 chọn SQLite vì cần queryable +
   observability là tiền đề tự-cải-tiến; loại bỏ all-markdown, JSON files, DB
   server-cho-v0).
4. **Phân phối CLI thế nào?** (0005 chọn prebuilt binary + checksum để consumer
   không phải cài toolchain; binary LÀ hợp đồng phân phối).
5. **Ranh giới durable-record vs trace-evidence** (0006: quyết định phải là row
   bền + file markdown; trace không tính).
6. **Luật tự-cải-tiến** (0007: `propose` advisory, rule-based, có bằng chứng,
   người duyệt; không auto-apply, không LLM tự do).

**Cái gì là NỀN TẢNG (phải sao chép ý tưởng)** vs **cái gì là CHI TIẾT (thay
được)**:

- *Nền tảng:* tách policy↔durable · trace + friction có cấu trúc · authority
  gate · proof-driven · durable-record≠evidence · self-improve có người gác ·
  discovery-before-mutation · CAS + derived field server-side.
- *Thay được:* SQLite (có thể Postgres/KV/event-log) · Rust prebuilt (có thể
  Python/Go/container) · con số timeout/cap cụ thể · format changeset JSONL · cú
  pháp/tên lệnh · kiến trúc phân lớp cụ thể.

---

## Phụ lục — Cây thư mục đích (H2 đầy đủ, để tham chiếu)

```
<repo>/
  AGENTS.md                         # entrypoint + authority gate (shim nhỏ, ổn định)
  CLAUDE.md                         # (nếu CC) import @AGENTS.md
  harness.db                        # durable state (gitignored)  ← chỉ từ H2
  docs/
    README.md                       # bản đồ docs
    GLOSSARY.md                     # từ vựng lõi
    HARNESS.md                      # mô hình cộng tác + request-class loops
    FEATURE_INTAKE.md               # phân loại rủi ro → lane
    ARCHITECTURE.md                 # luật ranh giới SẢN PHẨM
    TEST_MATRIX.md                  # vocab bằng chứng (state sống ở DB từ H2)
    CONTEXT_RULES.md                # đọc đúng/đủ/dừng          (H2)
    TRACE_SPEC.md                   # chuẩn trace               (H2)
    HARNESS_COMPONENTS.md           # 11 trách nhiệm            (H2)
    HARNESS_MATURITY.md             # thang H0–H5               (H2)
    TOOL_REGISTRY.md                # manifest + degrade ladder (H4)
    HARNESS_AUDIT.md                # entropy score             (H5)
    IMPROVEMENT_PROTOCOL.md         # propose → outcome loop    (H5)
    HARNESS_BACKLOG.md              # bồn friction (template)
    templates/
      story.md  decision.md  validation-report.md
      spec-intake.md                # (khi onboard spec lớn)
      high-risk-story/{overview,design,execplan,validation}.md   # (lane high-risk)
    stories/                        # gói việc thật
    decisions/                      # ADR: NNNN-*.md
  scripts/
    schema/001-init.sql …           # migrations                 (H2)
    bin/<cli>                        # CLI durable layer          (H2)
    bootstrap-*.{sh,ps1}            # dựng runtime local          (H2)
```

---

_Nguồn nghiên cứu: khung harness tham chiếu — `docs/HARNESS.md`,
`FEATURE_INTAKE.md`, `CONTEXT_RULES.md`, `TRACE_SPEC.md`, `GLOSSARY.md`,
`ARCHITECTURE.md`, `HARNESS_COMPONENTS.md`, `HARNESS_MATURITY.md`,
`HARNESS_AUDIT.md`, `IMPROVEMENT_PROTOCOL.md`, `TOOL_REGISTRY.md`,
`TEST_MATRIX.md`, `contracts/harness-orchestration-v1.md`, `scripts/schema/*.sql`
(001–013), `docs/templates/*`, `docs/decisions/0001–0007`. Vận hành hằng ngày:
`docs/HARNESS_RUNBOOK_VI.md`._
