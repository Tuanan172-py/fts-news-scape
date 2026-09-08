---
type: Playbook
title: Runbook — Vận hành hệ thống
description: Khởi chạy, health check, truy vấn chẩn đoán và xử lý sự cố thường gặp.
resource: project/docs/runbook.md
tags: [operations, runbook, health-check, troubleshooting]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: deployment
    resource: project/docs/operations/deployment.md
    title: Deployment & vận hành
  - id: troubleshooting
    resource: project/docs/operations/troubleshooting.md
    title: Troubleshooting
  - id: db-health
    resource: project/docs/operations/db-health-queries.md
    title: DB health queries
  - id: health
    resource: project/src/monitor/health.py
    title: Health check CLI
sources_last_checked: 2026-09-07
---

# Khởi chạy

```powershell
# PROD — 1 tiến trình, 3 job (capture 15' + re-derive Silver 30' + drift sáng)
.venv\Scripts\python.exe -m src.morninger

# chạy thử từng nhịp
.venv\Scripts\python.exe -m src.morninger --once capture
.venv\Scripts\python.exe -m src.morninger --once derive
.venv\Scripts\python.exe -m src.morninger --once drift

# chỉ capture (fallback / test)
.venv\Scripts\python.exe -m src.orchestrator --once [cafef tnck]
.venv\Scripts\python.exe scripts\run_once.py [domain...]
```

> ⚠️ **Chỉ MỘT scheduler chạy tại một thời điểm.** Advisory lock trong
> [pipeline_state](../tables/pipeline_state.md) chặn tiến trình thứ hai; chạy song song sẽ nhân
> đôi lưu lượng và có nguy cơ bị chặn IP.

Chuỗi per-user (Vòng 3): xem [Daily Agent Run](daily_agent_run.md).

# Health check

```powershell
.venv\Scripts\python.exe -m src.monitor.health     # exit 0 = OK, 1 = có vấn đề
```

Ngưỡng cảnh báo:[^health]

| Điều kiện | Mức |
|---|---|
| `consecutive_failures ≥ 3` | CRITICAL |
| `status = failed` | FAILED |
| `last_run_ts` > 30 phút | STALE |

# Truy vấn chẩn đoán

```powershell
.venv\Scripts\python.exe scripts\db_status.py        # tổng quan mọi bảng + watermark
.venv\Scripts\python.exe scripts\dbq.py "<SQL>"      # truy vấn nhanh
.venv\Scripts\python.exe scripts\monitor_daily.py --date today --save-md
```

```sql
-- sản lượng hôm nay theo nguồn
SELECT source_domain, COUNT(*) FROM articles
WHERE date(fetched_at) = date('now','localtime') GROUP BY source_domain;

-- tồn đọng handoff
SELECT status, COUNT(*) FROM work_items GROUP BY status;

-- bài cần sửa selector
SELECT source_domain, state, COUNT(*) FROM article_versions
WHERE state IN ('TEMPLATE_DRIFT','SELECTOR_BROKEN')
  AND captured_at >= datetime('now','-7 days','localtime')
GROUP BY source_domain, state;

-- watermark re-derive
SELECT * FROM pipeline_state WHERE key LIKE 'silver_%';
```

# Log & artifact

| Nơi | Nội dung |
|---|---|
| `logs/monocle.log` | Loguru, rotate 50 MB, giữ 14 ngày |
| `data/notifications/YYYY-MM-DD.log` | 1 dòng / bài khớp rule notify |
| `data/exports/articles-YYYY-MM-DD.csv` | export cuối mỗi cycle (ghi đè) |
| `data/reports/daily/*.md` | báo cáo giám sát ngày |
| `users/output/<user>/<date>.csv` | deliverable |

# Sự cố thường gặp

| Vấn đề | Nguyên nhân | Xử lý |
|---|---|---|
| Không khởi động được, log "Scheduler khác đang chạy" | advisory lock còn của tiến trình cũ | kiểm tra `SELECT * FROM pipeline_state WHERE key='lock:scheduler'`; tiến trình đã chết ⇒ chờ 40′ tự stale hoặc `DELETE` khoá đó |
| `SQLITE_BUSY` | nhiều tiến trình ghi / DB Browser mở chế độ ghi | đảm bảo 1 tiến trình; mở DB Browser read-only |
| Domain ra 0 bài | feed chết, selector đổi, bị chặn | xem `pitfalls` trong YAML; `scripts/diagnose_sources.py`; `scripts/verify_quality.py <domain>` |
| Nhiều bài `held` | `SELECTOR_BROKEN` / `TEMPLATE_DRIFT` | sửa `detail.content_selector` rồi `scripts/rederive_from_bronze.py <domain>` |
| `--date today` ra 0 dòng | backlog ngày cũ | chạy lại với `--days 30` hoặc `--date all` (writer đã log gợi ý này) |
| Re-derive luôn `processed=0` | watermark đã vượt | dùng full-scan `rederive_from_bronze.py` |
| FireAnt 401 | token hết hạn | cập nhật [secrets.yaml](../configurations/secrets.md) |
| SSL/cert (HNX) | chain không đủ | `truststore` + Windows cert store |

# Backup

DB là 1 file: `PRAGMA wal_checkpoint(TRUNCATE)` (orchestrator tự làm cuối mỗi cycle) rồi copy
`data/monocle.db`, hoặc dùng `scripts/db_snapshot.py` để chụp không chặn ghi. Bronze
(`data/raw_html/**`) là dữ liệu **không tái tạo được** — ưu tiên backup cao nhất; Silver và
work-package luôn re-derive lại được.

[^deployment]: [Deployment](project/docs/operations/deployment.md)
[^troubleshooting]: [Troubleshooting](project/docs/operations/troubleshooting.md)
[^db-health]: [DB health queries](project/docs/operations/db-health-queries.md)
[^health]: [health.py](project/src/monitor/health.py)
