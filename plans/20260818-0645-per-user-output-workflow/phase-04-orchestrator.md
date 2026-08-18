# Phase 04 — Orchestrator End-to-End + Logging "done"

## Context links
- Parent: [plan.md](plan.md) · Depends: P1,P2,P3.
- Reuse: `orchestrator.run_cycle`/`pipeline.run`, `l1_route.py`, `l1_ingest.py`, `agent_export.py`, `agent_ingest.py`.

## Overview
- **Date:** 2026-08-18 · **Priority:** P1 · **Impl status:** ⬜ · **Review:** ⬜
- 1 entrypoint nối: compile users → (scrape/process) → L1 → agent → per-user output → log done. Idempotent.

## Key Insights
- Các bước đã có script riêng; orchestrator chỉ ĐIỀU PHỐI (gọi tuần tự) + truyền `enabled_users` + `date`.
- Agent-export nên GIỚI HẠN theo union subscription (tiết kiệm): chỉ enqueue article có entity ∩ (⋃ subscription user bật). Cần store hỗ trợ lọc; nếu chưa, lọc ở tầng orchestrator sau khi có l1_outputs.

## Requirements
1. CLI 1 lệnh chạy toàn trình cho user được bật.
2. Bật/tắt user: `--users A,B` hoặc mặc định tất cả folder `users/input/*` (bỏ `_*`, enabled≠FALSE).
3. `--skip-scrape` để chạy lại chỉ từ dữ liệu đã có.
4. Idempotent + resume (nhờ P3 + DB cached).
5. Log "done" mỗi user với số dòng; KHÔNG notify.

## Architecture
### Script `project/scripts/run_user_workflow.py`
```
args: --users / --all, --date today, --skip-scrape, --skip-agent, --resume
1. compile_all(users/input) → yaml; load_registry.cache_clear(); enabled = manifest∩--users
2. if not skip-scrape: run pipeline (scrape→silver→work_packages)   # reuse existing
3. L1:  l1_route.main([--review missed]) ; (nếu có agent L1 outputs) l1_ingest.main([dir])
4. Agent: agent_export.main([...]) ; agent_ingest.main([outputs_dir])   # chỉ article thiếu dod_pass
5. UserOutputWriter(enabled).write(date) → per-user CSV
6. log.info("done user=<u> date=<d> rows=<n>") cho từng user; tổng kết cuối
```
- Bước 3/4 handoff cần agent NGOÀI xử lý packet → orchestrator dừng ở "đã export packet" nếu chưa có output; hoặc chạy chế độ `--ingest-only` sau khi agent nộp. Ghi rõ 2 chế độ: `export` (phát packet) và `ingest` (nạp + xuất).
- Union-subscription filter: sau L1, tính tập entity mọi user bật; chỉ giữ work_items có giao → giảm agent cost.

## Related code files
- NEW `project/scripts/run_user_workflow.py`
- NEW (optional) `project/src/pipeline/user_workflow.py` (logic để test)
- REUSE `scripts/l1_route.py`, `l1_ingest.py`, `agent_export.py`, `agent_ingest.py`, `orchestrator.py`
- READ `project/src/core/config.py` (db path)

## Implementation Steps
1. `user_workflow.py`: `run(users, date, skip_scrape, mode)` gọi các bước; trả summary dict.
2. Manifest enabled: đọc meta xlsx / folder scan (từ P1) → danh sách user bật.
3. Union-subscription filter trước agent-export.
4. Logging "done" + bảng tổng kết (user, rows, skipped).
5. CLI wrapper.

## Todo list
- [ ] user_workflow.run() nối bước (export mode / ingest mode)
- [ ] enabled manifest resolve
- [ ] union-subscription filter cho agent-export
- [ ] logging done + summary
- [ ] CLI run_user_workflow.py

## Success Criteria
- `python scripts/run_user_workflow.py --all --date today --skip-scrape` chạy sạch, log "done" mỗi user.
- Chạy lại → không đổi output (idempotent).
- User tắt (enabled FALSE / folder `_*`) → không sinh output.

## Risk Assessment
- Handoff agent là bất đồng bộ (người/agent ngoài xử lý packet) → orchestrator không tự "chạy agent"; tách rõ export vs ingest để không treo.
- Thứ tự phụ thuộc: compile phải trước, cache_clear bắt buộc, nếu quên → subscription cũ.

## Security Considerations
- Không log nội dung bài đầy đủ; chỉ id/counts.

## Next steps → Phase 05 tests.

## Resolved (2026-08-18)
- Scrape TÁCH khỏi workflow: `--skip-scrape` MẶC ĐỊNH BẬT (giả định cron đã scrape). Vẫn giữ cờ để chạy full khi cần.
- Agent scope = CHỈ article giao union-subscription (union filter là bắt buộc, không phải tùy chọn).
- Enabled đọc từ `users/input/manifest.yaml` (vắng tên = enabled mặc định).
