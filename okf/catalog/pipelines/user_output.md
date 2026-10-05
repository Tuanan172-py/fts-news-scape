---
type: Python Pipeline
title: User Output Workflow
description: Biên dịch đăng ký người dùng, gate 2 lớp DoD, định tuyến theo entity, ghi CSV cuối theo ngày.
resource: project/src/pipeline/user_workflow.py
tags: [pipeline, per-user, deliverable, csv, idempotent]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: user-workflow
    resource: project/src/pipeline/user_workflow.py
    title: run() orchestrator + union_subscription
  - id: user-output
    resource: project/src/export/user_output.py
    title: UserOutputWriter
  - id: compile
    resource: project/src/users/compile.py
    title: Biên dịch input người dùng → yaml
  - id: checkpoint
    resource: project/src/export/checkpoint.py
    title: Checkpoint resume
  - id: user-workflow-design
    resource: project/docs/design/13-per-user-output-workflow.md
    title: Per-user output workflow
sources_last_checked: 2026-09-07
---

Chặng cuối: từ dữ liệu đã qua 2 lớp agent → **CSV cho từng người dùng theo ngày**. Idempotent,
resume theo `article_id`, không notify — chỉ `logger.info("done …")`.[^user-workflow]

# Chuỗi

```
compile  → (ingest L1) → (ingest agent) → gate + route → ghi CSV → log done
```

`run()` **không** tự scrape và **không** tự gọi agent — handoff là bất đồng bộ.

```powershell
# khi người dùng đổi danh mục
.venv\Scripts\python.exe scripts\compile_users.py --all

# mỗi chu kỳ, sau khi agent đã nộp output
.venv\Scripts\python.exe scripts\run_user_workflow.py ^
    --l1-dir data\agent_outputs_l1 --agent-dir data\agent_outputs --date today

# chỉ ghi output từ dữ liệu đã ingest sẵn
.venv\Scripts\python.exe scripts\write_user_output.py --date today
```

# Gate

```sql
articles a
JOIN      l1_outputs    l1 ON l1.article_id = a.url_title_hash AND l1.dod_pass = 1   -- BẮT BUỘC
LEFT JOIN agent_outputs ag ON ag.article_id = a.url_title_hash AND ag.dod_pass = 1   -- tuỳ chọn
```

Lọc theo ngày dùng `published_at`, fallback `fetched_at`. Hỗ trợ `--date today|YYYY-MM-DD|all`
hoặc `--days N`.[^user-output]

# Định tuyến

1. Entity của bài = `l1_outputs.entities[].entity_id` với `in_list = true`.
2. `registry.subscribers_for(eset)` ∩ tập người dùng **đang bật** (manifest).
3. Mỗi người dùng lấy `matched = eset ∩ resolve_subscription(user)`.
4. **Noise filter** — chỉ khớp thực thể diện rộng (`MACRO_GEO` / `MACRO_THEME` / `ASSET_CLASS`)
   thì cần thêm `materiality.score ≥ 0.6` hoặc alias xuất hiện trong tiêu đề.

Bài không ai đăng ký ⇒ đếm vào log `orphan`, không vào file người dùng (vẫn có ở bản `_master`).

# Tiết kiệm chi phí agent

`union_subscription(registry, enabled)` cho phép **giới hạn phạm vi export** — chỉ giao agent
những bài chạm subscription của người dùng đang bật.[^user-workflow]
⚠️ `agent_export.py` hiện **chưa** tự lọc theo union này (xem câu hỏi mở ở
[thiết kế 13](project/docs/design/13-per-user-output-workflow.md)).

# Idempotency

- DB: `l1_outputs` / `agent_outputs` UNIQUE theo `article_id` ⇒ ingest lại trả *cached*.
- File: rewrite toàn tập per (user, ngày) + dedupe `article_id` ⇒ chạy trùng vô hại.
- Checkpoint: ghi file (atomic `os.replace`) **trước**, `mark_written()` **sau** ⇒ ngắt giữa
  chừng vẫn an toàn.[^checkpoint]

# Quan hệ

- Đầu vào: [l1_outputs](../tables/l1_outputs.md), [agent_outputs](../tables/agent_outputs.md),
  [User Subscriptions](../configurations/user_subscriptions.md)
- Đầu ra: [User Deliverables](../datasets/user_deliverables.md)

[^user-workflow]: [user_workflow.py](project/src/pipeline/user_workflow.py)
[^user-output]: [UserOutputWriter](project/src/export/user_output.py)
[^compile]: [compile.py](project/src/users/compile.py)
[^checkpoint]: [checkpoint.py](project/src/export/checkpoint.py)
[^user-workflow-design]: [Per-user output workflow](project/docs/design/13-per-user-output-workflow.md)
