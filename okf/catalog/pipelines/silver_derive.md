---
type: Python Pipeline
title: Silver Derive (Vòng 2)
description: Bronze → Silver → change-detection → work-package → catalog, tăng dần theo watermark, re-derivable.
resource: project/src/pipeline/derive.py
tags: [pipeline, silver, change-detection, handoff, re-derivable]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: derive
    resource: project/src/pipeline/derive.py
    title: rederive_incremental + watermark
  - id: run
    resource: project/src/pipeline/run.py
    title: process_meta — 1 artifact qua toàn chuỗi
  - id: silver-builder
    resource: project/src/pipeline/silver_builder.py
    title: SilverBuilder
  - id: change-detect
    resource: project/src/pipeline/change_detect.py
    title: Fingerprint + 5 trạng thái
  - id: storage-design
    resource: project/docs/design/07-storage-layers-and-change-detection.md
    title: Storage layers & change detection
sources_last_checked: 2026-09-07
---

**Vòng 2 — Standardize**: biến raw Bronze thành "clean base" và đóng gói thành việc cho agent.
Toàn bộ là **hàm thuần của Bronze** — xoá Silver rồi chạy lại cho kết quả giống hệt (không dùng
`now()`; `built_at` lấy từ `fetch_ts`).[^silver-builder]

# Chuỗi xử lý 1 artifact (`run.process_meta`)

```
meta.json + raw.html
   └─ SilverBuilder.build → silver-v1
        ├─ FAIL schema  ────────────────────────────► held
        └─ PASS
             └─ fingerprint (SHA-256 + SimHash64 + dom_path_sig)
                  └─ classify vs bản trước → article_versions (5 state)
                       └─ WorkPackageBuilder.build → work-package-v1
                            ├─ FAIL schema / drift ──► held
                            └─ PASS → Catalog.enqueue → work_items = pending
```

Hai **hard gate** (`silver-v1`, `work-package-v1`) và hai **held state**
(`SELECTOR_BROKEN`, `TEMPLATE_DRIFT`) là toàn bộ lý do một bài không tới tay agent.[^storage-design]

# Chế độ tăng dần (prod)

`rederive_incremental()` dùng watermark `silver_watermark` trong
[pipeline_state](../tables/pipeline_state.md):[^derive]

- Chọn file **strict `>` watermark** theo `fetch_ts` ⇒ chạy lúc nhàn rỗi trả `processed=0`,
  không sinh version `UNCHANGED` thừa.
- File thiếu/hỏng `fetch_ts` ⇒ **luôn** xử lý lại (retry raw_missing/corrupt).
- Watermark mới = `max(fetch_ts)` của các file xử lý **thành công**; file lỗi không đóng góp nên
  sẽ được quét lại chu kỳ sau.
- Backlog = 0 ⇔ không còn file nào vượt watermark ⇒ ghi `silver_checkpoint`.

Gọi bởi [Morninger](morninger.md) job `re-derive` mỗi 30′.

# Chế độ full-scan (bảo trì)

```powershell
.venv\Scripts\python.exe scripts\rederive_from_bronze.py [domain] [YYYYMMDD]
```

Dùng **sau khi** bump schema hoặc sửa parser — quét lại toàn bộ Bronze, bỏ qua watermark. Đây là
việc bảo trì, không phải driver hằng ngày.

# Kích hoạt change-detection

Change-detection cần ≥2 lần capture cùng URL, mà chu kỳ thường chỉ lấy bài mới. Muốn có bản
capture thứ hai:

```powershell
.venv\Scripts\python.exe scripts\refresh_watchlist.py [limit] [domain]
```

# Quan hệ

- Đọc [Bronze raw store](../datasets/bronze_raw_html.md)
- Ghi [Silver & Work Packages](../datasets/silver_work_packages.md),
  [article_versions](../tables/article_versions.md), [work_items](../tables/work_items.md)
- Tiếp nối bởi [Agent Handoff](agent_handoff.md)

# Metrics

- [Silver Backlog](../metrics/silver_backlog.md)

[^derive]: [derive.py](project/src/pipeline/derive.py)
[^run]: [run.py](project/src/pipeline/run.py)
[^silver-builder]: [SilverBuilder](project/src/pipeline/silver_builder.py)
[^change-detect]: [change_detect.py](project/src/pipeline/change_detect.py)
[^storage-design]: [Storage layers & change detection](project/docs/design/07-storage-layers-and-change-detection.md)
