# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-08
- **Current story:** US-101 (deliverable XLSX) · US-102 (cổng giá trị Gold) — cả hai `implemented`
- **Status:** `pytest tests/ = 373 passed` (baseline 357). 0 story `in_progress`.
- **Blocker:** **US-103 `blocked`** — cần người duyệt ADR 0004 phần D trước khi chạm dữ liệu.

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

1. **DUYỆT ADR 0004 phần D** (`docs/decisions/0004-gold-value-gate-va-du-lieu-gia-lap.md`):
   chọn D1 (hạ `dod_pass=0`, giữ `output_json` — khuyến nghị) / D2 / D3. Chưa duyệt thì
   deliverable vẫn đang chứa nội dung template.
2. Sau khi duyệt, trên **máy B**: backup `data/monocle.db` → `python scripts/verify_gold_quality.py`
   (xem báo cáo) → `--apply`.
3. Cập nhật prompt agent Gold theo `schemas/agent-instructions-v1.md` §2b rồi chạy lại backlog —
   trước khi làm việc này, mọi output kiểu cũ sẽ bị cổng mới đánh trượt (đúng chủ đích).
4. Rò rỉ T4 (orphan backlog Bronze/Silver không vào `articles`) — chưa điều tra.
