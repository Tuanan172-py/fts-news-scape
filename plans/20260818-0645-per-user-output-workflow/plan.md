# Plan — Per-User Output Workflow

**Date:** 2026-08-18 · **Status:** IMPLEMENTED (P1–P5, 13 tests pass) · **Owner:** AnPT

## Goal
Input cấp cao nhất = thư mục theo user (`users/input/<name>/entities.xlsx`). Hệ thống compile →
config → chạy các layer (L1 nhận diện entity + agent bóc tách) → xuất CSV cuối cho từng user,
lọc theo entity user đăng ký, phân theo ngày. Idempotent, resume theo `article_id`. Không notify —
chỉ log "done".

## Locked decisions (input clarified)
- Layout: `users/input/<name>/` + `users/output/<name>/<YYYY-MM-DD>/` ở REPO ROOT (đã có mẫu AnPT).
- Input format: Excel `.xlsx` (1 entity/dòng, cột theo nhóm) → auto-compile → `project/config/entities/users/<name>.yaml`.
- Layers = contracts đã có: `l1-entity-output-v1` + `agent-output-v1` (KHÔNG phát minh L2 mới).
  Mỗi layer ghi file riêng; `final.csv` chỉ ghi khi CẢ HAI layer DoD-pass cho article đó.
- Checkpoint L3 theo `article_id` (tận dụng idempotency DB + checkpoint file per user).
- Không notify; log "done" khi ghi output xong.

## Reuse (không viết lại)
`EntityRegistry.select/subscribers_for` (entities.py) · `L1Runner`+`l1_route/l1_ingest` ·
`AgentRunner`+`agent_export/agent_ingest` · `store.py` (l1_outputs/agent_outputs dod_pass) ·
`csv_export.write_csv` (utf-8-sig). Deps: pandas + openpyxl đã có.

## Phases
| # | Phase | File | Status |
|---|-------|------|--------|
| P1 | Compile xlsx input → yaml config + template + enable/disable | [phase-01](phase-01-input-compile.md) | ✅ Done |
| P2 | Per-user output writer (CSV theo ngày, gate "đủ layer") | [phase-02](phase-02-user-output-writer.md) | ✅ Done |
| P3 | Checkpoint / resume theo article_id + trạng thái per-user | [phase-03-checkpoint-resume.md](phase-03-checkpoint-resume.md) | ✅ Done |
| P4 | Orchestrator end-to-end + logging done | [phase-04-orchestrator.md](phase-04-orchestrator.md) | ✅ Done |
| P5 | Tests | [phase-05-tests.md](phase-05-tests.md) | ✅ Done (13 pass) |

## Data flow
```
users/input/<name>/entities.xlsx
  └─(P1 compile_users)→ project/config/entities/users/<name>.yaml → EntityRegistry.subscriptions
scrape→silver→work_packages (existing)
  └→ L1 route+ingest (l1_outputs.dod_pass) ─┐
  └→ agent export+ingest (agent_outputs.dod_pass) ─┤
                                                    ▼ (P2 gate: both dod_pass)
              subscribers_for(entities) → per-user users/output/<name>/<date>/{L1.csv,agent.csv,final.csv}
                                                    ▲ (P3 checkpoint by article_id)
              (P4 run_user_workflow.py chains all + logs "done")
```

## Cross-cutting decisions (CHỐT với user 2026-08-18)
1. **Gate "L1 done"** = BẮT BUỘC `l1_outputs.dod_pass=1` (agent-reviewed). Output cuối = `l1_outputs.dod_pass=1 AND agent_outputs.dod_pass=1`. (code-first `resolved` KHÔNG đủ để vào final.csv).
2. **Agent extraction scope** = CHỈ article có entity giao với union subscription của user đang bật (tiết kiệm agent).
3. **Date partition** = `published_at` (fallback `fetched_at`; null → `unknown-date`).
4. **Enable/disable** = file trung tâm `users/input/manifest.yaml` (liệt kê user bật/tắt). KHÔNG dùng ô xlsx.
5. **Scrape** = TÁCH khỏi workflow: `run_user_workflow.py` mặc định `--skip-scrape` (giả định cron/pipeline đã scrape).
