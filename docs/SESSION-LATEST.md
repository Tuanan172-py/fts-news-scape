# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-07
- **Current story:** Rà soát gate export & tách tầng CORE/DETAIL (nối tiếp US-007)
- **Status:** **implemented & verified** (324/324 tests passed, chạy thật trên `data/monocle.db`)
- **Blocker:** none
- **Accomplished:**
  - **Gate export = L1-only** (đã có trong working tree, nay hoàn thiện + tài liệu hoá): `l1_outputs.dod_pass=1` là gate CỨNG; `agent_outputs.dod_pass=1` là enrichment TÙY CHỌN → trường Gold để trống. Thêm cột **`gold_status`** (`GOLD`|`L1_ONLY`) để không nhầm "Gold chưa chạm" với "Gold đã chạy nhưng trường optional rỗng".
  - `_GATED_SQL` chọn **bản Gold mới nhất** (`MAX(id)`) — trước đây `UNIQUE(article_id, raw_sha256)` gây fan-out, bản nào thắng là ngẫu nhiên (23 dòng dư trên DB thật).
  - `_passes_noise_filter` **bỏ hẳn phụ thuộc Gold** (`materiality.score`) — chỉ còn entity cụ thể HOẶC alias ⊂ title. Thêm `_silver_noise_signals()` (alias_title/alias_body/body_len/code_in_symbols/cats) ghi vào cột `noise_signals` của `_master/<date>.csv` — **quan sát, CHƯA gate**.
  - **4 bug chặn đường (đều từ US-007 chưa commit):** `agent_ingest.py` `NameError: done_aids` (crash ngay output Gold đầu tiên pass DoD) · nhánh `"dod_pass" not in item` bypass toàn bộ DoD · `runner.py` đọc `e.get("code")` trong khi L1 schema chỉ có `entity_id` (0/399 entity có `code` → chaining L1→Gold rule 05 §2.5 chết ngầm) · thiếu `continue` sau `mark_failed` → `wp` unbound.
  - **Thứ tự L1 → Gold ép bằng cấu trúc:** `Catalog.claim(require_l1=)` + `AgentRunner.export_tasks(require_l1=True)` mặc định + `agent_export.py --require-l1/--no-require-l1`.
  - **Khôi phục backlog:** `l1_route.py --only gold-ready` → đã phát packet L1 cho **423 bài đã có Gold nhưng thiếu L1** (Gold đã trả tiền mà không giao được).
  - **Checkpoint:** giữ lại nhưng lưu `{article_id: gold_status}` + `filter_upgraded()`; log `rows=N (new=X upgraded=Y l1_only=Z)`. Đọc ngược được định dạng list cũ.
  - Thống nhất **thang materiality 0–1** (bỏ `3/5` ở `entity-system-invariants.md`); `agent_provider`/`model_used` để **trống** thay vì bịa `"unknown"`.
  - Đồng bộ 8 chỗ docs/rules còn ghi gate cũ "đủ 2 lớp".
- **Số liệu thật sau thay đổi:** gate population 424 (articles ⨝ L1 pass) — GOLD 384 · L1_ONLY 40 (+40 so với gate cũ). AnPT: 146 dòng (138 GOLD / 8 L1_ONLY).
- **Files changed this session:** `project/src/export/user_output.py`, `project/src/export/checkpoint.py`, `project/src/agent/runner.py`, `project/src/handoff/catalog.py`, `project/scripts/agent_ingest.py`, `project/scripts/agent_export.py`, `project/scripts/l1_route.py`, `project/scripts/write_user_output.py`, `project/src/pipeline/user_workflow.py`, `project/tests/{_userkit,test_user_output,test_user_checkpoint,test_agent_infra,test_pruner_and_batch}.py`, `project/tests/test_agent_ingest_cli.py` (mới), `project/docs/design/13-per-user-output-workflow.md`, `project/docs/operations/{daily-runbook-per-user,monocle-db-handbook}.md`, `.agents/rules/{02-financial-domain-rules,05-gold-agent-and-payload-invariants,entity-system-invariants}.md`, `docs/stories/US-002-*.md`.

## Next — rò rỉ dữ liệu CHƯA xử lý (ngoài phạm vi phiên này)

`l1_outputs`/`agent_outputs` chứa `article_id` **không tồn tại trong bảng `articles`**:
**261 bài đã xong L1** và **417 bài đã xong Gold** → vĩnh viễn không vào được `final.csv`
(gate join `articles ⨝ l1_outputs`). Cả 3 đều có `work_items` + `l1_tasks` + file work-package
với `source_url` hợp lệ, nhưng `articles` không có dòng nào cho URL đó.

⇒ Bronze/Silver tạo work-package nhưng **không ghi `articles`** — cần truy `orchestrator`/`derive`.
Đây là rò rỉ LỚN NHẤT còn lại (678 bài đã trả tiền agent), lớn hơn cả +40 từ việc nới gate.
Đếm nhanh: `.venv\Scripts\python.exe scripts/db_status.py` hoặc §3.8 trong `monocle-db-handbook.md`.
