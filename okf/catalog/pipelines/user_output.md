---
type: Python Pipeline
title: User Output Workflow
description: Gate DoD, định tuyến theo entity, ghi một file .xlsx cho mỗi người dùng mỗi ngày — chặng cuối của Article Lane, trước bước publish.
resource: project/src/export/user_output.py
tags: [pipeline, per-user, deliverable, xlsx, idempotent]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: user-output
    resource: project/src/export/user_output.py
    title: UserOutputWriter — gate, route, noise filter, ghi xlsx
  - id: xlsx
    resource: project/src/export/xlsx_delivery.py
    title: write_delivery_xlsx
  - id: contract
    resource: project/src/agent/contract/article_contract.py
    title: analyzed_l1_sql — điều kiện "bài đã được mô hình phân tích"
  - id: compile
    resource: project/src/users/compile.py
    title: Biên dịch input người dùng → yaml
  - id: checkpoint
    resource: project/src/export/checkpoint.py
    title: Checkpoint resume
  - id: wave-flow
    resource: project/src/ops/wave/wave_flow.py
    title: Bước ghi deliverable của đợt
sources_last_checked: 2026-10-22
---

Chặng cuối: từ bản ghi đã qua cổng DoD → **một file `.xlsx` cho từng người dùng theo ngày**.
Idempotent, resume theo `article_id`.[^user-output] Trong vận hành tự động, workflow của đợt
gọi `write_user_output.py --date <ngày>` sau khi nạp DB.[^wave-flow] Bước publish lên SharePoint
sandbox là việc riêng của `scripts/publish.py` (ADR-0026.D1).

# Chuỗi

```
article_run.py --finish → l1_outputs / agent_outputs → write_user_output.py → <DATA_ROOT>/users/output/<user>/<YYYY-MM-DD>.xlsx
```

```powershell
# khi người dùng đổi danh mục
C:\venvs\news-scape\Scripts\python.exe scripts\compile_users.py --all

# ghi deliverable từ dữ liệu đã nạp (chạy từ project/)
C:\venvs\news-scape\Scripts\python.exe scripts\write_user_output.py --date today
C:\venvs\news-scape\Scripts\python.exe scripts\write_user_output.py --where     # chỉ in đường dẫn, không ghi
```

Cờ khác: `--days N`, `--users a,b`, `--force` (ghi đè kể cả khi không có bài mới).

# Gate

```sql
articles a
JOIN      l1_outputs    l1 ON l1.article_id = a.url_title_hash
                          AND l1.dod_pass = 1 AND <không phải code_first>   -- BẮT BUỘC
LEFT JOIN agent_outputs ag ON ag.article_id = a.url_title_hash AND ag.dod_pass = 1  -- bản mới nhất
```

Chỉ bài **đã được mô hình phân tích** mới vào deliverable; hàng `code_first` bị loại (ADR-0010
D4, `analyzed_l1_sql`).[^contract] Thiếu bản nội dung thì dòng vẫn ra với `gold_status = L1_ONLY`.
Lọc theo ngày dùng `published_at`, fallback `fetched_at`.[^user-output]

# Định tuyến

1. Entity của bài = `l1_outputs.entities[].entity_id` với `in_list = true`.
2. `registry.subscribers_for(eset)` ∩ tập người dùng **đang bật** (manifest).
3. Mỗi người dùng lấy `matched = eset ∩ resolve_subscription(user)`.
4. **Noise filter** — nếu chỉ khớp thực thể diện rộng (`MACRO_GEO` / `MACRO_THEME` /
   `ASSET_CLASS`) thì alias của thực thể phải xuất hiện trong tiêu đề (so khớp dạng bỏ dấu).

Bài không ai đăng ký ⇒ log `orphan`, không vào file người dùng (vẫn có ở bản `_master`).

# Idempotency

- DB: `l1_outputs` / `agent_outputs` UNIQUE theo bài ⇒ ingest lại trả *cached*.
- File: rewrite toàn tập per (user, ngày) + dedupe `article_id`; không có bài mới hay bài nâng
  hạng `L1_ONLY → GOLD` thì **bỏ qua** ghi.
- File đang bị khoá (Excel mở) ⇒ ghi ra snapshot cạnh đó, **không** mark checkpoint.
- Checkpoint: ghi file **trước**, `mark_written()` **sau**.[^checkpoint]

# Quan hệ

- Đầu vào: [l1_outputs](../tables/l1_outputs.md), [agent_outputs](../tables/agent_outputs.md),
  [User Subscriptions](../configurations/user_subscriptions.md)
- Đầu ra: [User Deliverables](../datasets/user_deliverables.md)

[^user-output]: [UserOutputWriter](project/src/export/user_output.py)
[^xlsx]: [xlsx_delivery.py](project/src/export/xlsx_delivery.py)
[^contract]: [article_contract.py](project/src/agent/contract/article_contract.py)
[^compile]: [compile.py](project/src/users/compile.py)
[^checkpoint]: [checkpoint.py](project/src/export/checkpoint.py)
[^wave-flow]: [wave_flow.py](project/src/ops/wave/wave_flow.py)
