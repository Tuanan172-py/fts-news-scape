# US-008 — Gate export L1-only, hạ tầng rút backlog L1/Gold, khôi phục module mất

- **Status:** implemented
- **Lane:** high-risk
- **Parent / Epic:** Per-User Output Workflow + Antigravity Multi-Agent Hierarchy
- **Intake date:** 2026-09-07
- **Depends On:** US-002 (bị supersede một phần), US-007 (mất file, xem §Sự cố)

> **Mục đích của tài liệu này:** bản đối soát đầy đủ cho các phiên sau. Ghi rõ *cái gì đổi*,
> *đổi từ đâu sang đâu*, *bằng chứng nào*, và *cái gì còn nợ*. Đọc file này trước khi sửa
> `user_output.py`, `runner.py`, `catalog.py` hoặc luồng gom lô.

Commit: `9c06234` (79 files, +3824/−1161) · Test: **355 passed**

---

## 1. Product Contract

`final.csv` giao cho user chỉ cần **L1 đạt DoD**; Gold là enrichment tùy chọn. Bài chưa có Gold
vẫn được giao với các trường Gold rỗng và `gold_status=L1_ONLY`, tự nâng cấp thành `GOLD` ở vòng
sau. Token Gold không được tiêu cho bài chưa có L1 (vì không định tuyến được cho user nào).

---

## 2. Thay đổi hợp đồng (BREAKING — đối soát kỹ)

### 2.1 Gate export

| | Trước | Sau |
|---|---|---|
| Điều kiện | `l1_outputs.dod_pass=1` **AND** `agent_outputs.dod_pass=1` | `l1_outputs.dod_pass=1` **CHỈ** |
| SQL | 2 × INNER JOIN | INNER JOIN l1 + **LEFT JOIN** gold |
| Chọn bản Gold | không `ORDER BY` → ngẫu nhiên khi fan-out | subquery `MAX(id)` → **bản mới nhất, xác định** |

`agent_outputs` UNIQUE theo `(article_id, raw_sha256)` nên 1 bài tái-capture có nhiều dòng đạt
DoD. Trên DB thật có **50 bài** như vậy → trước đây 424 bài sinh 447 dòng thô.

### 2.2 `FINAL_COLUMNS` — 16 cột

```
date, matched_entities, title, summary, key_points, implication, impact_area,
time_sensitivity, sentiment, event_type, gold_status, url, source_domain,
article_id, agent_provider, model_used
```

- **THÊM `gold_status`** ∈ `GOLD` | `L1_ONLY` (chèn sau `event_type`).
- **BỎ `materiality_score`** khỏi deliverable (mô hình CORE/DETAIL §3). Vẫn sinh + lưu đủ trong
  `agent_outputs.output_json` và cột `materiality_score` của `_master/<date>_agent.csv`.
- `agent_provider`/`model_used` khi thiếu → **chuỗi rỗng**, không còn bịa `"unknown"`.

`MASTER_COLUMNS` = `FINAL_COLUMNS` + `noise_signals` — **chỉ** `_master/<date>.csv`, không có
trong file của user.

### 2.3 Đường dẫn output (PHẲNG — nhiều doc còn ghi sai)

```
users/output/<user>/<YYYY-MM-DD>.csv          users/output/<user>/_checkpoint.json
users/output/_master/<YYYY-MM-DD>.csv         _master/<date>_L1.csv   _master/<date>_agent.csv
```

KHÔNG có thư mục lồng `<date>/`, KHÔNG có file tên `final.csv`, thư mục user KHÔNG có
`L1.csv`/`agent.csv`.

### 2.4 `_checkpoint.json`

```jsonc
// trước: { "written": { "2026-08-18": ["<aid>", ...] } }
// sau  : { "written": { "2026-08-18": { "<aid>": "GOLD" | "L1_ONLY" } } }
```

Định dạng list cũ vẫn đọc được (status rỗng). Thêm `ckpt.filter_upgraded()`.
Log đổi thành `rows=N (new=X upgraded=Y l1_only=Z)`.

**Vì sao giữ checkpoint:** nó KHÔNG quyết định nội dung output (idempotency đến từ rewrite toàn
tập + `os.replace` + dedupe `article_id`). Vai trò thật là sổ cái giao hàng — nguồn duy nhất trả
lời "bài nào mới" và "bài nào vừa được Gold bổ sung".

### 2.5 Noise filter — BỎ HẲN phụ thuộc Gold

```
trước: entity cụ thể  HOẶC  materiality.score >= 0.6  HOẶC  alias ⊂ title
sau  : entity cụ thể  HOẶC  alias ⊂ title
```

Bắt buộc, vì gate là L1-only: bài chưa có Gold luôn bị chấm score 0 nên nhánh materiality khiến
việc nới gate chỉ có tác dụng một nửa. Ràng buộc này đã ghi vào
`.agents/rules/entity-system-invariants.md`: *"The filter MUST NOT read any Gold field."*

Thêm `_silver_noise_signals()` → cột `noise_signals`
(`alias_title`, `alias_body`, `body_len`, `code_in_symbols`, `cats`) — **chỉ để quan sát, CHƯA
gate**. Gom số liệu thật trước, chọn ngưỡng sau.

### 2.6 Thứ tự L1 → Gold (ép bằng cấu trúc)

`Catalog.claim(require_l1=False)` → `AgentRunner.export_tasks(require_l1=True)` **mặc định** →
`agent_export.py --require-l1` / `--no-require-l1`.

> **Hệ quả nhịp chạy:** `run_daily.ps1` xếp `agent_export` TRƯỚC `l1_ingest`, nên bài mới trong
> ngày chưa có `l1_outputs` ⇒ không được bốc; sang vòng sau mới có packet Gold. **Không mất bài**
> (`work_items` vẫn `pending`). Muốn bắt kịp trong ngày: chạy 2 nhịp agent.

### 2.7 Thang `materiality_score` = **0–1** (thống nhất)

`agent-output-v1` quy định `minimum:0, maximum:1`. Bỏ dấu vết thang `3/5` ở
`entity-system-invariants.md`. Ghi chú cấm thang khác vào `02-financial-domain-rules.md`.

---

## 3. Mô hình CORE / DETAIL

Nguyên tắc: **tách hợp đồng LƯU TRỮ khỏi hợp đồng GIAO HÀNG.**

| Tầng | Ai làm | Trường | Vai trò |
|---|---|---|---|
| Bronze/Silver | code | `article_id, title, url, source_domain, date, cleaned_text` | CORE — luôn có |
| L1 | agent | `entities[].entity_id` + `in_list`, `categories` | **CORE — gate CỨNG** |
| Gold | agent | `summary.abstractive`, `summary.key_points`, `citations`≥2 | CORE — gate MỀM |
| Gold | agent | `implication`, `materiality`, `sentiment`, `event_type` | DETAIL |

**KHÔNG đổi `agent-output-v1`** — đổi Data Contract là HIGH-RISK hard gate (`AGENTS.md` §Cấp 3),
cần ADR + human duyệt. Ẩn/hiện cột ở tầng giao hàng là thay đổi rẻ, đảo ngược được bằng 1 dòng.

---

## 4. Bug đã sửa (5)

| # | File | Triệu chứng | Nguyên nhân |
|---|---|---|---|
| 1 | `scripts/agent_ingest.py` | `NameError: done_aids` — crash ngay output Gold **đầu tiên** đạt DoD | biến không hề khởi tạo (đối chiếu `l1_ingest.py` có) |
| 2 | `scripts/agent_ingest.py` | output thô mang key `dod_pass` **bypass toàn bộ DoD** | nhánh `... if "dod_pass" not in item else item` |
| 3 | `src/agent/runner.py` | chaining L1→Gold (rule 05 §2.5) **chết ngầm**, `l1_entities` luôn `[]` | đọc `e.get("code")`; schema L1 chỉ có `entity_id` (**0/399** entity có key `code`) |
| 4 | `src/agent/runner.py` | `wp` unbound → `NameError`, đứt cả vòng export | thiếu `continue` sau `mark_failed` |
| 5 | `scripts/l1_ingest.py` | agent trả cả lô trong 1 file → **hỏng im lặng** | không giải nén mảng JSON |

Bug 1 giải thích vì sao có **304 `work_items` kẹt `claimed`**: mỗi lần chạy ingest chỉ xử lý được
1 bài rồi chết.

---

## 5. Hạ tầng rút backlog (mới)

- **`scripts/l1_backlog.py`** (chỉ đọc) — kiểm kê T1..T4 + nhóm `claimed` kẹt, in sẵn chuỗi lệnh.
- **`scripts/l1_route.py`** — thêm `--only {all,gold-ready,in-articles}` và `--mini-batch N`.
- **`src/agent/batch_handoff.py`** — `build_l1_batch_packet` + `split_l1_tasks_into_batches`.
  L1 gom **25 bài/lô** (packet chỉ mang tiêu đề, 13,5 KB/lô) vs Gold 5–10 (mang `cleaned_text`).
- **`.agents/skills/l1-entity-matcher/SKILL.md` §5** — Batch Mode + 5 bẫy làm hỏng DoD.
- **`project/docs/operations/backlog-drain-runbook.md`** — runbook 4 bậc.

### Số liệu tồn đọng (DB thật, 2026-09-07)

| Nhóm | Bài | Ý nghĩa |
|---|---|---|
| Đã qua gate | 424 | GOLD 384 · L1_ONLY 40 |
| **T1 gold-ready** | **423** | Gold xong thiếu L1 → chạy L1 = giao ngay, **0 token Gold** |
| T2 l1-only | 6.372 | chưa L1 chưa Gold (473 đã có packet chờ) |
| T3 gold-next | 40 | đã có L1, `work_item` pending |
| T4 orphan | 467 / 261 / 417 | không có dòng trong `articles` → **vĩnh viễn** không giao được |
| `claimed` kẹt | 304 (232 chưa Gold, có trong `articles`) | `claim()` chỉ đọc `pending`, không có cơ chế đòi lại |

Nới gate chỉ thêm **+40 bài**. Nút thắt thật là **L1**, không phải Gold.
Đã phát **17 batch packet cho 423 bài T1**.

---

## 6. Sự cố mất dữ liệu (bắt buộc đọc)

Trong phiên, **file untracked biến mất khỏi đĩa nhiều đợt**, nguyên nhân chưa xác định. Không có
lệnh xoá nào được chạy. Recycle Bin trống, `git log --all` không có.

**Khôi phục được từ `__pycache__/*.cpython-314.pyc`:**

| File | Mức xác thực |
|---|---|
| `src/agent/archive.py`, `manifest.py`, `batch_handoff.py` | Đối chiếu bytecode gốc: **khớp tuyệt đối** (tên hàm, tham số, defaults, hằng số) |
| `src/agent/pruner.py` | Khớp, trừ khoảng trắng 1 dòng trống trong docstring |
| `tests/test_pruner_and_batch.py`, `test_batch_manifest.py` | Dựng lại từ `.pyc` pytest-rewritten — **tương đương hành vi, không phải nguyên bản** |
| `scripts/l1_backlog.py` | Viết lại từ đầu (mất sau khi tạo, trước khi commit) |

**Mất vĩnh viễn (markdown không có `.pyc`):**
`docs/stories/US-004-newest-first-batch-processing.md` ·
`docs/stories/US-006-task-batch-manifest-and-archive.md` ·
`docs/stories/US-007-gold-task-payload-optimization.md` ·
`project/daily_log.txt` · `project/data/reports/daily/tnck-2026-09-07.md`

> ⚠️ **Comment và định dạng gốc của 4 module là VIẾT MỚI, không phải nguyên bản.** Logic đã kiểm
> chứng bằng bytecode; văn phong chú thích thì không. Đừng coi chúng là bản gốc khi đối soát.
>
> `.pyc` **không phải backup** — chúng đã bị ghi đè sau khi khôi phục. Bằng chứng đối chiếu chỉ
> tồn tại ở kết quả chạy tại thời điểm đó, không tái lập được.

**Chưa commit có chủ đích** (vẫn nguyên trong `HEAD`, `git restore` lấy lại được):
`okf/catalog/configurations/monocle_config.md` · `users/subscriptions/AnPT_news.csv` ·
`users/subscriptions/_template_news.csv`.
Riêng `AnPT_news.csv` là **nguồn danh mục theo dõi của user** (`compile.py` đọc từ
`users/subscriptions/`) — thiếu nó thì `compile_users.py --all` không còn nguồn.

---

## 7. Validation

| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; .venv\Scripts\python.exe -m pytest tests/ -q` | **passed** | 355 passed (baseline đầu phiên 263) |
| Integration | `.venv\Scripts\python.exe scripts/write_user_output.py --date all` | **passed** | 424 dòng `_master` (GOLD 384 / L1_ONLY 40), AnPT 146 |
| Integration | `.venv\Scripts\python.exe scripts/l1_route.py --only gold-ready --all --mini-batch 25` | **passed** | 423 bài → 17 batch packet, 13,5 KB/lô |
| Integration | `.venv\Scripts\python.exe scripts/l1_backlog.py` | **passed** | in đúng T1..T4 + nhóm claimed kẹt |
| E2E | — | — | cần agent L1 thật xử lý packet |
| Platform | — | — | |

**10 test mới:** `gold_status` GOLD/L1_ONLY · `test_multiple_gold_rows_picks_latest` ·
`test_noise_filter_broad_entity_no_gold_dependency` · `test_l1_only_export_fallback_empty_gold` ·
`test_export_requires_l1_by_default` · `test_export_embeds_l1_entity_ids` ·
`test_ingest_single_output_no_nameerror` · `test_output_carrying_dod_pass_key_is_not_trusted` ·
`test_checkpoint_records_gold_status_and_upgrade` · `test_checkpoint_reads_legacy_list_format`.

---

## 8. Còn nợ (chưa sửa — ưu tiên cho phiên sau)

1. **`gated_rows()` bị làm nặng.** `_GATED_SQL` nay kéo `a.content_text` chỉ để nuôi
   `noise_signals` (thứ không gate). Hiện 1,1 MB; **sau khi rút hết backlog L1 sẽ ~11,8 MB mỗi
   lần chạy**, kể cả `--date today` (vì lấy hết rồi mới lọc ngày trong Python).
   → Bỏ `alias_body`/`body_len`, hoặc đưa sau cờ `--noise-signals` mặc định tắt.
2. **Packet gom lô không bao giờ được dọn.** `archive_completed_tasks` chỉ di chuyển
   `<article_id>.task.json`; `batch_XX.task.json` / `l1_batch_XX.task.json` nằm lại vĩnh viễn.
   Lô sau nhỏ hơn lô trước ⇒ batch cũ còn sót, agent xử lý lại bài đã xong. Có sẵn từ US-007
   cho Gold, nay nhân bản sang L1.
3. **304 `work_items` kẹt `claimed`** từ 2026-08-17, không có reclaim. 232 bài sẽ vô hình với
   hàng đợi Gold ngay cả sau khi rút xong L1.
4. **Rò rỉ T4** — Bronze/Silver tạo work-package nhưng **không ghi `articles`** (678 bài đã trả
   tiền agent). Cần truy `orchestrator`/`derive`. Lớn hơn nhiều so với +40 từ việc nới gate.
5. **25 chỗ tài liệu lệch** — nặng nhất `project/docs/design/14-entity-system-and-mapping.md:76-77`
   (ghi noise filter dùng `materiality_score >= 3`: sai cả thang lẫn logic); 11 chỗ ghi đường dẫn
   lồng (gồm `AGENTS.md:80`); 5 chỗ còn nói "gate 2 lớp";
   `design/12-agent-infrastructure.md:44` còn ghi `confidence >= 0.65` là predicate DoD.

---

## 9. Harness Delta

- Tạo story này (phiên trước không có story file — vi phạm `docs/HARNESS.md`).
- Thêm dòng US-008 vào `docs/TEST_MATRIX.md`; đồng thời ghi nhận US-003 chưa từng có dòng và
  US-004/006/007 nay mất file.
- `docs/stories/US-002` đánh dấu **superseded một phần** (hợp đồng cột đổi).
- Overwrite `docs/SESSION-LATEST.md`.

## 10. Trace

- **Outcome:** completed
- **Friction:** (a) mất file untracked nhiều đợt, nguyên nhân chưa rõ — khôi phục nhờ `.pyc`
  còn khớp magic Python 3.14.3; (b) `.pyc` bị ghi đè trong lúc đối chiếu làm mất bằng chứng của
  `pruner.py`; (c) repo có quá nhiều file untracked nên git không cứu được — đã commit `9c06234`.
