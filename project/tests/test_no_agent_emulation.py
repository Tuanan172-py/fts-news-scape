"""Chốt chặn AGENTS.md §6.C — cấm giả lập trí tuệ Agent bằng heuristic script.

Bối cảnh (2026-09-08): `scripts/maintenance/repair_truncated_outputs.py` từng dùng regex tách
câu để tự sinh `summary`/`key_points`, gán cứng `implication` = câu template, `materiality=0.6`,
`sentiment=neutral`, `event_type=macro`, `extraction_quality="high"`, rồi `UPDATE agent_outputs`
thẳng vào DB kèm `agent_provider="gemini"` — provenance giả. Kết quả: 1.117/1.274 bản ghi Gold
là sản phẩm của regex nhưng mang nhãn LLM, và tất cả đều `dod_pass=1`.

Test này khoá 2 bất biến để lỗi đó không quay lại im lặng:
  1. Chỉ `src/db/store.py` được viết SQL chạm `agent_outputs` / `l1_outputs`.
  2. Chỉ runner (`src/agent/runner.py`, `src/agent/l1_runner.py`) được gọi `insert_*_output`,
     tức mọi bản ghi đều đi qua `check_dod` / `check_l1_dod`.

Vi phạm hợp lệ (nếu có) phải sửa danh sách miễn trừ Ở ĐÂY, kèm lý do — không sửa lén.
"""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Chỉ những file này được phép. Thêm tên vào đây là một quyết định có chủ đích, không phải
# thao tác dọn lỗi test.
SQL_WRITERS = {"src/db/store.py"}
INSERT_CALLERS = {"src/db/store.py", "src/agent/runner.py", "src/agent/l1_runner.py"}

# `dbq.py` là CLI truy vấn tuỳ ý của con người, đã có cổng `--allow-write` và chỉ chạy thủ công
# → không phải đường ghi tự động của pipeline.
EXEMPT = {"scripts/dbq.py"}

_SQL_WRITE = re.compile(
    r"(insert\s+into|update|delete\s+from)\s+(agent_outputs|l1_outputs)\b", re.I)
_INSERT_CALL = re.compile(r"\b(insert_agent_output|insert_l1_output)\s*\(")


def _sources():
    for base in ("src", "scripts"):
        for p in sorted((PROJECT_ROOT / base).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(PROJECT_ROOT).as_posix()
            if rel in EXEMPT:
                continue
            yield rel, p.read_text(encoding="utf-8")


def test_only_store_writes_agent_and_l1_outputs():
    """SQL ghi thẳng vào bảng output = đường vòng qua cổng DoD."""
    offenders = sorted(rel for rel, src in _sources()
                       if rel not in SQL_WRITERS and _SQL_WRITE.search(src))
    assert not offenders, (
        "Các file sau ghi SQL thẳng vào agent_outputs/l1_outputs, vòng qua cổng DoD "
        f"(AGENTS.md §6.C): {offenders}")


def test_only_runners_persist_agent_output():
    """Mọi bản ghi Gold/L1 phải đi qua runner để bị `check_dod` chấm."""
    offenders = sorted(rel for rel, src in _sources()
                       if rel not in INSERT_CALLERS and _INSERT_CALL.search(src))
    assert not offenders, (
        "Các file sau gọi insert_agent_output/insert_l1_output ngoài runner, nên bản ghi "
        f"không bị chấm DoD: {offenders}")


def test_emulation_script_stays_deleted():
    """Script giả lập đã xoá 2026-09-08 — không được phục hồi."""
    gone = PROJECT_ROOT / "scripts" / "maintenance" / "repair_truncated_outputs.py"
    assert not gone.exists(), (
        "repair_truncated_outputs.py đã bị xoá vì tự sinh nội dung Gold bằng regex và giả "
        "provenance. Cần sửa dữ liệu cũ thì dùng scripts/verify_gold_quality.py (report/rescore), "
        "không phục hồi script này.")
