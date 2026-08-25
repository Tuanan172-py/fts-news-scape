# HARNESS.md — The human ↔ agent collaboration model (news-scape, H1)

The "constitution" doc. Stable, rarely edited. Vocabulary: [GLOSSARY.md](GLOSSARY.md).
Maturity **H1**: pure markdown, no database, no CLI. The 8+1 loop below is done by hand.

## 1. Two layers

| Layer | Storage | Role |
|-------|---------|------|
| **Policy** | `docs/*.md` (this dir) | *How to work*. Stable. |
| **Durable** | *(H2+, not built)* SQLite | *What happened*. At H1 = story files + SESSION-LATEST + inline trace notes. |

A single request produces up to two outputs: a **product delta** (code/config/docs in `project/`) and a **harness delta** (a backlog/decision/doc that makes next time easier).

## 2. Request-Class Loops & Per-Prompt Lifecycle

Mọi prompt/yêu cầu đều đi qua 3 bước cốt lõi: **Classify (3 Tiers) → Execute & Proof → Harness Closure**.

```
1. Classify   Phân loại vào 1 trong 3 cấp độ: Tiny / Normal / High-Risk. Ghi nhận intake qua harness_cli.
2. Context    Đọc tài liệu theo ma trận docs/CONTEXT_RULES.md (ngân sách token tương ứng với Lane).
3. Execute    - Tiny: Trả lời hoặc patch code trực tiếp.
              - Normal: WIP=1, lập docs/stories/US-XXX.md, code và chạy unit/integ test.
              - High-Risk: Dừng tại Hard Gate, lập ADR docs/decisions/, xin phê duyệt của người dùng.
4. Proof      Chạy lệnh test cơ học và kiểm chứng.
5. Trace      Ghi nhận bản ghi trace (Minimal / Standard / Detailed) vào harness.db qua harness_cli trace.
6. Closure    BẮT BUỘC xuất Bảng Nghiệm thu Đóng phiên (Harness Closure Table).
```

## 3. WIP = 1 (Interrupt Discipline)

At most **one** story `in_progress`. On interruption:
1. Do NOT abandon the current story silently.
2. Set it `blocked` or `deferred` with a one-line reason (and `Depends On:` if applicable).
3. Create/parks the new story, finish it, then resume the old one (read its notes first).

## 4. Step 6 — Mandatory Harness Closure Protocol

Ở cuối **MỖI CÂU TRẢ LỜI / PHIÊN THỰC THI**, Agent bắt buộc xuất bảng định tuyến lưu vết:

```markdown
### 📋 Harness Closure Protocol

| File / Component | Updated? | Reason & Evidence |
|:---|:---:|:---|
| `harness.db` *(Trace & Intake)* | **Yes** | Ghi nhận Trace #ID (Lane: `Tiny/Normal/High-Risk`, Score: 1.0). |
| `docs/stories/US-XXX.md` | **Yes / No** | [Lý do cụ thể: Tạo mới / Cập nhật / Không cần (tác vụ Tiny)] |
| `docs/TEST_MATRIX.md` | **Yes / No** | [Lý do cụ thể: Chạy X tests passed / Chưa có test mới] |
| `docs/decisions/NNNN-*.md` | **Yes / No** | [Lý do cụ thể: Lập ADR do đổi kiến trúc / Không chạm Hard Gate] |
| `docs/SESSION-LATEST.md` | **Yes / No** | [Lý do cụ thể: Cập nhật trạng thái handoff / Không đổi] |
| `docs/HARNESS_BACKLOG.md` | **Yes / No** | [Lý do cụ thể: Ghi nhận ma sát / Không phát sinh ma sát] |
```

## 5. Proof Rule

Status enum + proof tiers live in [TEST_MATRIX.md](TEST_MATRIX.md). A story reaches `implemented` ONLY after a real validation command ran and is recorded in `harness.db`. Never hand-flip a proof row.

## 6. Decisions (High-Risk)

When changing architecture / a public data contract / a hard-gate area → record an ADR: a file in [decisions/](decisions/). A trace note does NOT replace an ADR.

## 7. Definition of Done

**Done criteria:**
1. Tác vụ hoàn thành đúng yêu cầu, có bằng chứng thực nghiệm rõ ràng.
2. Trace bền vững đã được nạp vào `harness.db` (`score_trace` $\ge 0.75$, `score_context` $\ge 0.8$).
3. Bảng **Harness Closure Protocol** được xuất đầy đủ ở cuối phản hồi.


## 8. Growth rule + climb-to-H2 signal

The harness grows from friction. Climb to H2 (SQLite + CLI, per `harness/HARNESS_BUILD_FROM_SCRATCH.md` Stage C) ONLY when markdown hurts: (a) can't query status across many stories; (b) the TEST_MATRIX hand table is stale/error-prone; (c) the trail is lost between sessions; (d) backlog needs predicted-vs-actual. Do not build H2 pre-emptively.

## 9. What an agent may / must ask

**May do directly:** story status/notes, TEST_MATRIX rows, linking story→OKF docs, intake, backlog, small clarifications.
**Must ask the human first:** changing architecture direction · removing a validation requirement · changing the risk rules · touching a hard-gate area (secrets, DB migration, external API tokens).
