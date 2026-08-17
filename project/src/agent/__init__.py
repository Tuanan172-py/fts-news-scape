"""
Vòng 3 — HẠ TẦNG agent (agent-agnostic, KHÔNG có LLM).

Producer chỉ cung cấp khung để BẤT KỲ agent nào (do người dùng tự điều khiển bằng
prompt riêng) cắm vào: claim việc → nhận task-packet → nộp output → validate + DoD →
lưu → mark_done. Không gọi API model nào tại đây.

- `dod`     : Definition-of-Done predicate + preconditions (thuần, machine-checkable).
- `packet`  : dựng task-packet (INPUT work-package + hợp đồng OUTPUT + ràng buộc) cho agent ngoài.
- `runner`  : AgentRunner — export_tasks (claim→packet) + ingest_output (validate→DoD→persist).

Xem docs/design/12-agent-infrastructure.md và schemas/agent-instructions-v1.md.
"""
