---
type: Python Pipeline
title: Morninger — entrypoint prod
description: Tiến trình duy nhất chạy ban ngày, 3 job APScheduler — capture 15′, re-derive Silver 30′, drift report mỗi sáng.
resource: project/src/morninger.py
tags: [pipeline, scheduler, prod, entrypoint]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: morninger
    resource: project/src/morninger.py
    title: Morninger scheduler
  - id: proclock
    resource: project/src/core/proclock.py
    title: Advisory scheduler lock
  - id: settings
    resource: project/config/settings.yaml
    title: settings.morninger
  - id: e2e-design
    resource: project/docs/design/00-end-to-end-architecture.md
    title: End-to-end architecture
sources_last_checked: 2026-09-07
---

**Prod = 1 entrypoint duy nhất: `python -m src.morninger`.** Một tiến trình, 3 job nội bộ —
không cần lên lịch riêng cho từng bước.[^e2e-design]

# 3 job

| Job | Chu kỳ | Hàm gọi | Vòng |
|---|---|---|---|
| `capture` | 15′ | [`Orchestrator.run_cycle`](ingestion_scheduler.md) | 1 |
| `re-derive` | 30′ | [`rederive_incremental`](silver_derive.md) | 2 |
| `drift report` | cron mỗi sáng (mặc định 06:00) | `pipeline.drift.list_drift` | giám sát |

Cấu hình ở [settings.yaml](../configurations/settings.md) khối `morninger`:
`capture_interval_minutes`, `rederive_interval_minutes`, `drift_hour`, `drift_minute`,
`drift_limit`.

# Checkpoint Silver

Sau mỗi lần re-derive, nếu **không còn** Bronze artifact nào chưa xử lý (backlog = 0), morninger
ghi `silver_checkpoint` vào [pipeline_state](../tables/pipeline_state.md) — nghĩa là "danh sách
tin cấp Silver đã cập nhật đầy đủ tới thời điểm này".[^morninger]

# Chống chạy trùng

Chiếm advisory lock `lock:scheduler` (value `host:pid`) khi khởi động; job `capture` refresh lock
mỗi cycle. Stale = **2400 giây (40′)** — lớn hơn chu kỳ 15′ để lock không bị cướp giữa hai
nhịp.[^proclock] Tiến trình khác không chiếm được ⇒ log ERROR và thoát, không chạy song song.

# CLI

```powershell
.venv\Scripts\python.exe -m src.morninger                  # scheduler liên tục (PROD)
.venv\Scripts\python.exe -m src.morninger --once capture   # 1 cycle capture rồi thoát
.venv\Scripts\python.exe -m src.morninger --once derive    # 1 lần re-derive tăng dần
.venv\Scripts\python.exe -m src.morninger --once drift     # 1 lần drift report
```

Trên Windows dùng Task Scheduler gọi `scripts/run_daily.ps1`.

# Việc KHÔNG thuộc morninger

Morninger chỉ lo Vòng 1 + Vòng 2. Chuỗi agent (Vòng 3) và output người dùng chạy riêng theo lô:
[Agent Handoff](agent_handoff.md) → [User Output](user_output.md).

Bảo trì chạy tay: `scripts/rederive_from_bronze.py` (full-scan sau khi bump schema/sửa parser),
`scripts/refresh_watchlist.py` (kích hoạt change-detection), `scripts/report_drift.py`.

[^morninger]: [morninger.py](project/src/morninger.py)
[^proclock]: [proclock.py](project/src/core/proclock.py)
[^settings]: [settings.yaml](project/config/settings.yaml)
[^e2e-design]: [End-to-end architecture](project/docs/design/00-end-to-end-architecture.md)
