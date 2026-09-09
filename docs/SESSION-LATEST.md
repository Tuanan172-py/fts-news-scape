# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-09
- **Current story:** US-101 (deliverable XLSX) · US-102 (cổng giá trị Gold) · US-103 (xử lý dữ liệu cũ & ADR 0003/0004) — tất cả `implemented`
- **Status:** `pytest tests/ = 378 passed`. 0 story `in_progress`.
- **Blocker:** **Không còn blocker cổng duyệt**. A1 (ADR 0003 accepted) và A2 (ADR 0004 D1 apply) đã hoàn tất. Sẵn sàng chạy §B.

## Việc đã làm phiên này

### US-101 — Deliverable người dùng cuối: CSV → XLSX đơn sắc
- `users/output/<user>/<YYYY-MM-DD>.xlsx` — **12 cột**, nhãn tiếng Việt, header đậm + kẻ mảnh,
  `freeze A2`, AutoFilter, wrap 3 cột văn bản dài, **không màu nền**.
- Bỏ khỏi deliverable: `impact_area` (100% = `market`), `event_type` (80% = `macro`),
  `agent_provider`, `model_used`.
- Sort tất định: `Độ khẩn` → `materiality.score` giảm dần → mã → tiêu đề (score vẫn ẩn cột).
- Sửa bug `matched_entities` lặp mã (22% dòng) bằng dedupe trong `_codes()`.
- Chặn formula injection: mọi ô văn bản ép `data_type="s"`.
- `_master/*.csv` **giữ nguyên** hợp đồng máy đọc (CSV, snake_case EN) — có test riêng khoá.
- `openpyxl` + `pytest` bổ sung vào `requirements.txt` (đang thiếu, cài mới là gãy).

### US-102 — Cổng giá trị Gold (backlog #3, ADR 0004 A–C)
- **Xoá `scripts/maintenance/repair_truncated_outputs.py`** — script giả lập trí tuệ agent bằng
  regex, vi phạm AGENTS.md §6.C và là nguyên nhân gốc của toàn bộ số liệu dưới.
- `check_dod` thêm 2 predicate: `value_added`, `implication_specific`.
- `tests/test_no_agent_emulation.py` khoá 3 bất biến chống tái phạm.
- `schemas/agent-instructions-v1.md` §2b + sample được sửa (sample **tự vi phạm** quy tắc).
- `scripts/verify_gold_quality.py` — kiểm định corpus (report mặc định, `--apply` mới ghi).

## Số liệu đo trên `monocle.db` thật (read-only)

| Chỉ số | Trước |
|---|---|
| `agent_outputs` · `dod_pass=1` | 1.274 · **1.274 (100%)** — cổng chưa từng từ chối ai |
| `key_points` copy y hệt `citations[].source_span` | **1.274 (100%)** |
| `implication.text` distinct | **3 câu** cho 1.274 bản ghi · boilerplate **100%** |
| `impact_area = market` | **1.274 (100%)** |
| Sẽ trượt cổng mới | **1.274 / 1.274** |

## Next Steps
1. Thực hiện chuỗi triển khai §B của `OPEN-ITEMS.md`:
   - §B1: `python scripts/rederive_from_bronze.py` (bổ sung trường `title` cho 3.910 work-package).
   - §B2: Chuỗi nạp lần đầu (`refresh_aliases`, `l1_ingest --code-first`, `heal_orphans`, `relativize_paths`, `reclaim_stale`, `run_user_workflow --date all`).
2. Giải toả hàng đợi Agent L1 (~282 bài `needs_agent`) theo §B3.
3. Rò rỉ T4 (orphan backlog Bronze/Silver không vào `articles`) — chưa điều tra.
