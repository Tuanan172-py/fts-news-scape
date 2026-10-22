---
type: Python Pipeline
title: Morninger — tiến trình capture + Silver
description: Tiến trình thường trú với 4 job APScheduler — capture (10′), re-derive Silver (30′), drift report mỗi sáng, reclaim — được ops_daemon giữ sống.
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
    title: capture.lock + advisory scheduler lock
  - id: settings
    resource: project/config/settings.yaml
    title: settings.morninger
  - id: supervisor
    resource: project/src/ops/runtime/supervisor.py
    title: Supervisor giữ morninger sống
sources_last_checked: 2026-10-22
---

**Capture + Silver = 1 tiến trình thường trú: `python -m src.morninger`.** Một tiến trình, bốn
job APScheduler nội bộ — không cần lên lịch riêng cho từng bước.[^morninger]

# 4 job

| Job | Chu kỳ (`settings.yaml`) | Việc | Vòng |
|---|---|---|---|
| `capture` | `capture_interval_minutes` (hiện 10′) | [`Orchestrator.run_cycle`](ingestion_scheduler.md), nối tiếp đối chiếu sitemap + bù URL thiếu (ADR 0013) và `backfill_deferred` có trần thời gian | 1 |
| `derive` | `rederive_interval_minutes` (30′) | [`rederive_incremental`](silver_derive.md), rồi gom cụm câu chuyện + tín hiệu (ADR 0016) | 2 |
| `drift` | cron `drift_hour:drift_minute` (06:00) | `pipeline.drift.list_drift` | giám sát |
| `reclaim` | `reclaim_interval_minutes` (mặc định 30′) | trả work-package bị treo về hàng đợi | 2 |

Cấu hình ở [settings.yaml](../configurations/settings.md) khối `morninger`.[^settings]

# Checkpoint Silver

Sau mỗi lần re-derive, nếu **không còn** Bronze artifact nào chưa xử lý (backlog = 0), morninger
ghi `silver_checkpoint` vào [pipeline_state](../tables/pipeline_state.md).[^morninger]

# Chống chạy trùng

Hai lớp khoá:[^proclock]

1. **File lock `capture.lock`** cạnh DB vận hành (`SingleInstanceLock`), dùng chung cho mọi
   tiến trình cào (`morninger`, `run_once.py`, `orchestrator`). Không có trạng thái stale: hệ
   điều hành nhả khoá khi tiến trình chết.
2. **Advisory lock `lock:scheduler`** trong `pipeline_state` (value `host:pid`, stale 2400 giây).

Không chiếm được khoá ⇒ log ERROR và thoát, không cào song song.

# Ai giữ morninger sống

Vận hành không người trực: `ops_daemon` (Task Scheduler `news-scape-ops` +
`news-scape-ops-watchdog`, ADR-0012) chạy `Supervisor` khởi động lại `python -m src.morninger`
khi tiến trình chết, có backoff và trần số lần; vượt trần thì báo đỏ và dừng thử. Lệnh
`/capture restart` (Telegram hoặc console) xoá trạng thái bỏ cuộc.[^supervisor]

# CLI (chạy từ `project/`)

```powershell
C:\venvs\news-scape\Scripts\python.exe -m src.morninger                  # scheduler liên tục
C:\venvs\news-scape\Scripts\python.exe -m src.morninger --once capture   # 1 cycle capture rồi thoát
C:\venvs\news-scape\Scripts\python.exe -m src.morninger --once derive    # 1 lần re-derive tăng dần
C:\venvs\news-scape\Scripts\python.exe -m src.morninger --once drift     # 1 lần drift report
```

# Việc KHÔNG thuộc morninger

Morninger chỉ lo Vòng 1 + Vòng 2. Phân tích bài chạy theo đợt qua
[Article Lane](article_lane.md) (do `ops_daemon` mở đợt hoặc chạy tay), rồi
[User Output](user_output.md).

Bảo trì chạy tay: `scripts/rederive_from_bronze.py` (full-scan sau khi bump schema/sửa parser),
`scripts/refresh_watchlist.py` (kích hoạt change-detection).

[^morninger]: [morninger.py](project/src/morninger.py)
[^proclock]: [proclock.py](project/src/core/proclock.py)
[^settings]: [settings.yaml](project/config/settings.yaml)
[^supervisor]: [supervisor.py](project/src/ops/runtime/supervisor.py)
