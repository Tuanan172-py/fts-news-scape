# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-07
- **Current story:** Gate export L1-only + hạ tầng rút backlog L1/Gold
- **Status:** **implemented & verified** (355/355 tests passed, chạy thật trên `data/monocle.db`)
- **Blocker:** none. **CHƯA COMMIT** — theo yêu cầu người dùng.

## ⚠️ SỰ CỐ MẤT FILE — đã khôi phục

Giữa phiên, **7 file chưa từng commit** biến mất khỏi đĩa (`git log --all` không có, Recycle Bin
không có). Pipeline gãy import: `No module named 'src.agent.pruner'`.

Mất: `src/agent/{manifest,batch_handoff,archive,pruner}.py` ·
`tests/{test_pruner_and_batch,test_batch_manifest,test_agent_ingest_cli}.py`

**Khôi phục từ `__pycache__/*.cpython-314.pyc`** (khớp magic với Python 3.14.3 của venv):
- `archive.py`, `manifest.py`, `batch_handoff.py` — đối chiếu bytecode **KHỚP TUYỆT ĐỐI**
  (tên hàm, tham số, defaults, toàn bộ hằng số).
- `pruner.py` — khớp mọi thứ trừ khoảng trắng ở 1 dòng trống trong docstring (`.pyc` gốc bị ghi
  đè lúc 16:47 trước khi so xong). Không ảnh hưởng hành vi.
- 3 file test dựng lại từ `.pyc` pytest-rewritten (constants + call graph còn nguyên).

**Comment và định dạng gốc của 4 module đã mất** — comment hiện tại là viết mới.

> **Bài học:** git không cứu được vì file chưa bao giờ được commit. Rất nhiều file trong repo
> vẫn đang untracked.

## Đã làm

**Gate export & deliverable**
- Gate CỨNG = `l1_outputs.dod_pass=1`; Gold là enrichment TÙY CHỌN (`LEFT JOIN`).
- Cột **`gold_status`** (`GOLD`|`L1_ONLY`) — phân biệt "Gold chưa chạm" với "Gold đã chạy nhưng
  trường optional rỗng".
- `_GATED_SQL` chọn **bản Gold mới nhất** (`MAX(id)`) — `UNIQUE(article_id, raw_sha256)` gây
  fan-out, trước đây bản nào thắng là ngẫu nhiên (23 dòng dư trên DB thật).
- `_passes_noise_filter` **bỏ hẳn** phụ thuộc Gold; thêm `_silver_noise_signals()` ghi vào cột
  `noise_signals` của `_master/<date>.csv` — **quan sát, CHƯA gate**.
- `agent_provider`/`model_used` để **trống** thay vì bịa `"unknown"`.

**5 bug đã sửa**
1. `agent_ingest.py` — `NameError: done_aids`, crash ngay output Gold đầu tiên đạt DoD.
2. `agent_ingest.py` — nhánh `"dod_pass" not in item` cho output thô **bypass toàn bộ DoD**.
3. `runner.py` — đọc `e.get("code")` trong khi L1 schema chỉ có `entity_id` (0/399 entity có
   `code`) ⇒ chaining L1→Gold (rule 05 §2.5) chết ngầm.
4. `runner.py` — thiếu `continue` sau `mark_failed` ⇒ `wp` unbound, đứt vòng export.
5. `l1_ingest.py` — không giải nén được output gom lô (agent trả mảng là hỏng im lặng).

**Thứ tự L1 → Gold ép bằng cấu trúc**
`Catalog.claim(require_l1=)` + `AgentRunner.export_tasks(require_l1=True)` mặc định +
`agent_export.py --require-l1 / --no-require-l1`.

**Hạ tầng rút backlog (MỚI)**
- `scripts/l1_backlog.py` — kiểm kê tồn đọng T1..T4 + in sẵn chuỗi lệnh (chỉ đọc).
- `scripts/l1_route.py` — `--only {all,gold-ready,in-articles}` + `--mini-batch N`.
- `src/agent/batch_handoff.py` — `build_l1_batch_packet` / `split_l1_tasks_into_batches`
  (L1 gom 25 bài/lô vì packet chỉ mang tiêu đề). **Đã phát 17 batch cho 423 bài T1.**
- `.agents/skills/l1-entity-matcher/SKILL.md` §5 — Batch Mode + bẫy làm hỏng DoD.
- `project/docs/operations/backlog-drain-runbook.md` — runbook đầy đủ.

**Checkpoint** — giữ lại nhưng lưu `{article_id: gold_status}` + `filter_upgraded()`;
log `rows=N (new=X upgraded=Y l1_only=Z)`. Đọc ngược được định dạng list cũ.

**Thang materiality thống nhất 0–1** (bỏ `3/5` ở `entity-system-invariants.md`).

## Số liệu (DB thật)

| Nhóm | Số bài |
|---|---|
| Đã qua gate export | 424 (GOLD 384 · L1_ONLY 40) |
| T1 gold-ready — Gold xong, thiếu L1 | **423** — chạy L1 = giao ngay, **0 token Gold** |
| T2 chưa L1 chưa Gold (có trong `articles`) | 6.372 |
| T3 đã có L1, work_item pending | 40 |
| T4 mồ côi (không có trong `articles`) | l1_tasks 467 · l1_outputs xong 261 · gold xong 417 |

## Next

1. **Rút T1 trước** — 17 packet đã sẵn ở `data/agent_tasks/l1/l1_batch_XX.task.json`.
   Agent L1 xử lý → `l1_ingest.py data/agent_outputs_l1` → `write_user_output.py --date all`.
   Chi tiết: `project/docs/operations/backlog-drain-runbook.md`.
2. **Rò rỉ T4 chưa xử lý:** work-package + `l1_tasks` tồn tại với `source_url` hợp lệ nhưng
   `articles` không có dòng nào cho URL đó ⇒ Bronze/Silver tạo work-package mà **không ghi
   `articles`**. Cần truy `orchestrator`/`derive`. 678 bài đã trả tiền agent nằm ở đây — lớn hơn
   nhiều so với +40 từ việc nới gate.
