# Harness Runbook (VI) — Cách tự thực hiện quy trình

Tài liệu tự-chạy (self-execution) cho quy trình **Harness** của Sen13. Đây là bản
đúc kết tiếng Việt của `docs/HARNESS.md`, `docs/FEATURE_INTAKE.md`,
`docs/CONTEXT_RULES.md`, `docs/TRACE_SPEC.md` và `scripts/README.md`. Khi mâu
thuẫn, các file gốc đó là nguồn chuẩn (source of truth); runbook này chỉ là lối
đi nhanh.

> **App is what users touch. The harness is what agents touch.**
> Harness KHÔNG phải code trading (DP/OG/OF). Nó là lớp vận hành bao quanh, biến
> yêu cầu thành công việc **an toàn + có bằng chứng (proof)**.

---

## 0. Nguyên tắc số một — Phân loại request TRƯỚC mọi thao tác

Mọi thứ bắt đầu ở một cổng duy nhất: **request class**. Nó quyết định *có được
thay đổi repo/DB hay không*. Quyết định dựa trên **kết quả mong muốn (outcome)**,
không phải một từ khóa.

```
Yêu cầu đến
  └─ Chỉ cần: answer / explain / review / diagnose / plan / status ?
       ├─ CÓ   → READ-ONLY
       │         Đọc AGENTS.md + đúng file cần → trả lời → DỪNG.
       │         KHÔNG bootstrap, KHÔNG init/migrate DB,
       │         KHÔNG ghi intake / story / trace / backlog.
       │
       └─ KHÔNG → CHANGE (change / build / fix / "review and apply fixes")
                 Chạy vòng mutation 8 bước ở Mục 2.
```

Ví dụ ranh giới:
- "Vì sao test này fail?" → read-only. Dù phát hiện thiếu migration → **vẫn không**
  được tạo migration (mới chỉ là chẩn đoán).
- "Sửa lại migration đó" → change. Bootstrap + intake trước khi sửa.
- "Review rồi apply fix giúp tôi" → change (vì user yêu cầu sửa repo).

---

## 1. Kiến trúc harness (2 tầng)

| Tầng | Nơi lưu | Vai trò |
|------|---------|---------|
| **Policy** | `docs/*.md` | Mô tả *cách làm việc*. Ổn định, người đọc. |
| **Durable** | `harness.db` (SQLite, gitignored) qua `scripts/bin/harness-cli.exe` | Ghi *điều đã xảy ra*: intake, story, decision, trace, backlog. |
| **Templates** | `docs/templates/*` | Khuôn story / decision / validation-report. |
| **Schema** | `scripts/schema/NNN-*.sql` | Cấu trúc DB, version-controlled. |

Policy = "how"; Durable = "what happened". `harness.db` local từng máy.

---

## 2. CHANGE loop — 8 bước

```
1. Bootstrap    .\scripts\bootstrap-harness.ps1
2. Intake       Phân loại theo docs/FEATURE_INTAKE.md (Mục 3)
                → harness-cli intake ...
3. Proof status harness-cli query matrix --active --summary
                (+ --story <id> nếu đã chọn story)
4. Context      Chỉ đọc file theo lane trong docs/CONTEXT_RULES.md (Mục 4)
5. Implement    Slice nhỏ nhất + validate trong lane
6. Self-check   Product truth / validation / architecture / next-agent có đổi?
7. Trace        harness-cli trace ... theo docs/TRACE_SPEC.md → xem score
8. Friction     Sửa tại chỗ HOẶC harness-cli backlog add
```

Xong một change request khi:
- Thay đổi hoàn tất **hoặc** blocker được ghi lại rõ.
- Docs / stories / test matrix liên quan còn đúng.
- Đã chạy validation command (nếu tồn tại).
- Đã ghi **trace**.
- Thiếu năng lực harness → đã ghi **backlog** (nếu liên quan).
- Câu trả lời cuối nói rõ *cái gì đã đổi* và *cái gì chưa làm*.

---

## 3. Intake — chọn LANE

Con người **không** cần tự xếp rủi ro. Harness làm.

### 3.1 Input type (công việc "đáp" ở đâu)

| Type | Dùng khi | Artifact |
|------|----------|----------|
| New spec | Biến spec dự án thành docs harness | Product docs, epics, decisions |
| Spec slice | Hiện thực 1 hành vi đã chọn từ spec | Story packet |
| Change request | Đổi/sửa/tinh chỉnh hành vi đã có | Story packet hoặc patch trực tiếp |
| New initiative | Vùng sản phẩm lớn, nhiều story | Initiative notes + stories |
| Maintenance | Dependency / kiến trúc / hiệu năng / bảo mật / vận hành | Story, validation report, hoặc decision |
| Harness improvement | Cải tiến cách người + agent cộng tác | Cập nhật docs hoặc `backlog add` |

### 3.2 Risk checklist — đánh dấu MỖI flag áp dụng

| Flag | Áp dụng khi động tới |
|------|----------------------|
| Auth | login, logout, session, JWT, password, refresh token |
| Authorization | roles, permissions, tenant/company scope |
| Data model | schema, migration, uniqueness, deletion, retention |
| Audit/security | audit log, privacy, dữ liệu nhạy cảm, access log |
| External systems | email, payment, cloud, provider SDK, queue, webhook |
| Public contracts | API shape, response envelope, hành vi client thấy được |
| Cross-platform | desktop/mobile/browser, native shell, deep link |
| Existing behavior | hành vi đã hiện thực / đã có test bị đổi |
| Weak proof | test quanh vùng ảnh hưởng mơ hồ hoặc thiếu |
| Multi-domain | hơn 1 product domain đổi cùng lúc |

### 3.3 Quy tắc chọn lane

```
0–1 flag          → tiny hoặc normal (tùy code impact)
2–3 flag          → normal (validation mạnh hơn)
4+ flag           → high-risk
Bất kỳ HARD GATE  → high-risk (trừ khi human thu hẹp scope)
```

**Hard gates:** Auth · Authorization · Data loss/migration · Audit/security ·
External provider behavior · Làm yếu/gỡ validation.

### 3.4 Yêu cầu theo lane

| Lane | Phải làm |
|------|----------|
| **Tiny** | Ghi intake row → patch trực tiếp → giữ docs current → chạy quick check. Bỏ qua story packet (nhưng KHÔNG bỏ intake). |
| **Normal** | Tạo/cập nhật 1 story từ `templates/story.md` → link product docs → validation expectations → ghi proof bằng `story add`/`story update`. |
| **High-risk** | Dùng `templates/high-risk-story/` (`execplan.md`, `overview.md`, `design.md`, `validation.md`) → hỏi human nếu hướng mơ hồ → ghi **decision record** (`docs/decisions/NNNN-*.md` từ `templates/decision.md` + `decision add`). Trace text KHÔNG thay được decision record. |

### 3.5 Đầu ra intake — phải nói được câu này

```
Lane: normal
Reason: touches authorization + API contract + audit
Docs: permissions, account-settings, audit-log
Story: docs/stories/epics/E02-.../US-014-...md
Validation: unit, integration, E2E
```

---

## 4. Context Rules — đọc đúng, đủ, biết dừng

Mục tiêu KHÔNG phải nhồi tối đa context, mà là đưa đúng thông tin cho **phase +
lane** hiện tại.

Phases: **Intake → Planning → Implementation → Validation → Trace**. Mỗi ô trong
`docs/CONTEXT_RULES.md` là Must / Should / Skip theo lane.

**Ngân sách token:**

| Lane | Ngân sách harness context | Hình dạng đọc |
|------|---------------------------|----------------|
| Tiny | ~2K | AGENTS.md + FEATURE_INTAKE + matrix summary + đúng file sửa |
| Normal | ~5K | Intake docs + product/story liên quan + architecture (nếu structural) + validation + trace spec cuối |
| High-risk | ~10K | Full intake + architecture + decisions + high-risk template + product/validation + trace spec + component/maturity |

**Quy tắc ngân sách:**
- Ưu tiên `rg` có mục tiêu hơn đọc cả file.
- Đọc section nhỏ nhất trả lời được câu hỏi của phase.
- Nâng context khi gặp *retrieval trigger*.
- Rõ lane + file + đường validation rồi → **ngừng** đọc lịch sử vô quan.

**Retrieval triggers (nâng context tự động), ví dụ:**
- Động schema/DB/migration → đọc `decisions/0004-sqlite-durable-layer.md` +
  `scripts/schema/`.
- Động CLI/installer → đọc `decisions/0005-prebuilt-rust-harness-cli.md` +
  `scripts/README.md`.
- Động auth / authorization / audit / data-loss / external provider → **coi như
  high-risk**, đọc `templates/high-risk-story/*` + decisions trước khi làm.
- Đổi public API / hành vi user-visible → đọc `docs/product/*` + story +
  validation trước khi sửa.
- Đổi Harness policy / hierarchy / risk rule / validation → đọc HARNESS +
  FEATURE_INTAKE + ARCHITECTURE + decisions; **dừng nếu hướng mơ hồ**.

---

## 5. Trace — bằng chứng để lại

3 tier, `harness-cli trace` tự chấm điểm:

| Lane | Tier | Nội dung tối thiểu |
|------|------|--------------------|
| Tiny | **Minimal** (1) | `task_summary` (≥10 ký tự) + `outcome` |
| Normal | **Standard** (2) | + `intake_id`, `story_id`, `agent`, `actions_taken`, `files_read`, `files_changed`, và ≥1 trong `errors`/`harness_friction` |
| High-risk | **Detailed** (3) | + `decisions_made`, `errors` (dùng `none` nếu không có), `harness_friction` (chỉ `none` sau khi đã kiểm), `duration`, `token_estimate`, `notes` |

`outcome` ∈ `completed` | `blocked` | `partial` | `failed`.

**Friction viết sao cho tốt:** nêu *cái đau cụ thể* + năng lực còn thiếu, không
nêu cảm giác mơ hồ.
- ✅ "New docs chưa nằm trong installer copy list; ghi backlog out-of-scope."
- ❌ "docs confusing".

---

## 6. Story lifecycle & verification

- Proof flags là **số** `1`/`0` (KHÔNG dùng `yes`/`no`).
- `story verify <id>` chạy `verify_command` đã cấu hình (không nhận proof flags).
- `story complete <id>` = **lối duy nhất** sang `implemented` (chạy proof tươi +
  atomic). `story update --status implemented` bị **từ chối**.
- `story verify-all` trước mọi merge / maturity claim / benchmark.
- Copy proof values: dùng `query matrix --numeric` để lấy dạng 1/0.

---

## 7. Growth rule — harness lớn lên từ friction

Khi agent bối rối / lặp thao tác thủ công / thiếu rule / thấy failure lặp:
**sửa harness ngay** hoặc ghi backlog. Backlog `--risk` dùng **lane**
(`tiny`/`normal`/`high-risk`), KHÔNG dùng `low`.

```powershell
.\scripts\bin\harness-cli.exe backlog add --title "<name>" --pain "<what was hard>" --risk tiny --predicted "<impact đo được>"
# Khi đóng:
.\scripts\bin\harness-cli.exe backlog close --id <n> --outcome "<kết quả thực đo>"
```

---

## 8. Decision records (high-risk)

Khi đổi behavior / architecture / authorization / data ownership / API shape /
validation → ghi ở **cả 2 nơi**:

1. File markdown `docs/decisions/NNNN-*.md` (từ `templates/decision.md`).
2. Durable row:

```powershell
.\scripts\bin\harness-cli.exe decision add --id 0008-auth-boundary --title "Auth Boundary" --doc docs/decisions/0008-auth-boundary.md --notes "Accepted during T4 auth work."
```

Trace `--decisions` là *evidence*, KHÔNG thay được decision log.

---

## 9. Việc agent được / phải hỏi

**Được làm trực tiếp:** story status (trừ completion) + evidence, test matrix
rows, link story→product docs, validation notes, làm rõ nhỏ, intake/trace/backlog.

**Phải hỏi human trước khi:** đổi hướng kiến trúc · gỡ validation requirement ·
đổi source-of-truth hierarchy · đổi luật phân loại rủi ro · thay feature workflow.

---

## 10. Lệnh Windows — copy-paste

```powershell
# 0. CHỈ khi là CHANGE request
.\scripts\bootstrap-harness.ps1
.\scripts\bin\harness-cli.exe --version

# 1. Intake
.\scripts\bin\harness-cli.exe intake --type <type> --summary "<text>" --lane <tiny|normal|high-risk>

# 2. Proof status
.\scripts\bin\harness-cli.exe query matrix --active --summary
.\scripts\bin\harness-cli.exe query matrix --story <id>
.\scripts\bin\harness-cli.exe query matrix --numeric        # lấy proof dạng 1/0

# 3. Story (normal+)
.\scripts\bin\harness-cli.exe story add --id US-0xx --title "<text>" --lane normal --verify "<cmd>"
.\scripts\bin\harness-cli.exe story update --id US-0xx --unit 1 --integration 1 --e2e 0 --platform 0
.\scripts\bin\harness-cli.exe story verify US-0xx
.\scripts\bin\harness-cli.exe story complete US-0xx
.\scripts\bin\harness-cli.exe story verify-all              # trước khi merge

# 4. Decision (high-risk)
.\scripts\bin\harness-cli.exe decision add --id NNNN-slug --title "<text>" --doc docs/decisions/NNNN-slug.md --notes "<...>"

# 5. Trace (cuối)
.\scripts\bin\harness-cli.exe trace --summary "<text>" --outcome completed `
  --intake <id> --story US-0xx --agent claude `
  --actions "a,b,c" --read "f1,f2" --changed "f3,f4" --friction "none"
.\scripts\bin\harness-cli.exe score-trace --id <n>          # chấm lại 1 trace cũ

# 6. Friction / backlog
.\scripts\bin\harness-cli.exe backlog add --title "<name>" --pain "<pain>" --risk tiny
.\scripts\bin\harness-cli.exe query backlog --open
.\scripts\bin\harness-cli.exe query friction

# Đọc thêm
.\scripts\bin\harness-cli.exe help
.\scripts\bin\harness-cli.exe query help
```

Lưu ý bootstrap: `bootstrap-harness.ps1` **từ chối** tạo DB rỗng nếu đây là source
checkout mà thiếu core DB (phải khôi phục core epoch đã verify); trong consumer
install thì tự `init` an toàn. Nó **pin version** CLI theo
`scripts/harness-cli-release-tag` — lệch version = bootstrap fail. Nó cũng tự
`migrate` DB cũ và từ chối schema ngoài vùng hỗ trợ.

---

## 11. Read-only inspection (không cần bootstrap)

Được phép chạy để trả lời mà **không** đổi state (dùng cho request read-only):

```powershell
.\scripts\bin\harness-cli.exe query matrix --active --summary
.\scripts\bin\harness-cli.exe query stories --json
.\scripts\bin\harness-cli.exe query backlog
.\scripts\bin\harness-cli.exe query traces
.\scripts\bin\harness-cli.exe query stats
.\scripts\bin\harness-cli.exe query sql "<một câu SELECT read-only>"
```

`query sql` chỉ nhận 1 câu read-only; CLI cưỡng chế read-only ở tầng kết nối.

---

## 12. Định nghĩa "Done"

**Read-only done:** câu trả lời có bằng chứng repo, tách rõ fact vs suy luận,
repo + harness state **không đổi**.

**Change done:** đủ các điều kiện ở Mục 2 (thay đổi/blocker, docs/story/matrix
current, validation đã chạy nếu có, **trace đã ghi**, friction đã vào backlog nếu
cần, câu trả lời cuối nói rõ đã đổi gì / chưa làm gì).

---

## Phụ lục — Ví dụ áp dụng (tình huống Sen13)

**Yêu cầu:** "Sửa OF để lọc keyspace event theo timeframe cấu hình."

```
1. Class     → CHANGE (fix).
2. Bootstrap → .\scripts\bootstrap-harness.ps1
3. Intake    → type=Change request.
   Risk flags: Existing behavior (OF đang chạy), Weak proof (không có test OF).
   → 2 flag, không hard gate → LANE = normal.
   intake --type change-request --summary "OF filter keyspace by TF" --lane normal
4. Matrix    → query matrix --active --summary  (tìm story liên quan)
5. Story     → story add --id US-0xx ... --verify "python -m compileall -q core"
6. Context   → đọc core/channel_listener.py + adjacent; skip lịch sử vô quan.
7. Implement → sửa slice nhỏ nhất, chạy compileall.
8. Trace     → Standard tier: actions/read/changed/friction.
9. Friction  → nếu thiếu test OF: backlog add --pain "OF thiếu test quanh listener".
```

---

_Nguồn chuẩn khi runbook này lỗi thời: `docs/HARNESS.md`, `docs/FEATURE_INTAKE.md`,
`docs/CONTEXT_RULES.md`, `docs/TRACE_SPEC.md`, `scripts/README.md`._
