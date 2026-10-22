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
  - id: health
    resource: project/src/monitor/health.py
    title: Health check CLI
  - id: radar
    resource: project/src/ops/console/radar.py
    title: pipeline_radar status / backlog / users / token
sources_last_checked: 2026-10-22
---

Mọi lệnh chạy từ `project/` với `C:\venvs\news-scape\Scripts\python.exe`. Dữ liệu dưới
`<DATA_ROOT>` = `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`).

# Radar trước, không dò tay

Câu hỏi "pipeline đang ở đâu, làm gì tiếp" trả lời bằng radar (chỉ đọc), không bằng truy vấn tay
hay chạy thử lệnh ghi (AGENTS.md §9):

```powershell
C:\venvs\news-scape\Scripts\python.exe scripts\pipeline_radar.py status     # điểm chạm + đúng một lệnh kế tiếp
C:\venvs\news-scape\Scripts\python.exe scripts\pipeline_radar.py backlog    # tồn đọng theo ngày
C:\venvs\news-scape\Scripts\python.exe scripts\pipeline_radar.py users      # người dùng + danh mục
C:\venvs\news-scape\Scripts\python.exe scripts\pipeline_radar.py token      # chi phí đợt
C:\venvs\news-scape\Scripts\python.exe scripts\article_run.py --where       # trạng thái Article Lane, chỉ đọc
C:\venvs\news-scape\Scripts\python.exe scripts\ops_daemon.py status          # trạng thái daemon từ ops.db
```

# Khởi chạy

Chuẩn: `ops_daemon` (Task Scheduler `news-scape-ops`) giữ [morninger](../pipelines/morninger.md)
sống và mở đợt [Article Lane](../pipelines/article_lane.md) — xem [Deployment](deployment.md).
Chạy tay để thử từng nhịp:

```powershell
C:\venvs\news-scape\Scripts\python.exe -m src.morninger --once capture
C:\venvs\news-scape\Scripts\python.exe -m src.morninger --once derive
C:\venvs\news-scape\Scripts\python.exe -m src.morninger --once drift
C:\venvs\news-scape\Scripts\python.exe scripts\run_once.py [domain...]      # chỉ capture
```

> ⚠️ **Chỉ MỘT tiến trình cào tại một thời điểm.** File lock `capture.lock` (cạnh DB) và advisory
> lock trong [pipeline_state](../tables/pipeline_state.md) chặn tiến trình thứ hai; chạy song
> song sẽ nhân đôi lưu lượng và có nguy cơ bị chặn IP.

# Health check

```powershell
C:\venvs\news-scape\Scripts\python.exe -m src.monitor.health     # exit 0 = OK, 1 = có vấn đề
```

Ngưỡng cảnh báo:[^health]

| Điều kiện | Mức |
|---|---|
| `consecutive_failures ≥ 3` | CRITICAL |
| `status = failed` | FAILED |
| `last_run_ts` > 30 phút | STALE |

# Truy vấn chẩn đoán (SQL chỉ đọc)

Mở DB ở chế độ chỉ đọc (`sqlite3 -readonly C:\data\news-scape\monocle.db` hoặc DB Browser
read-only), tốt nhất trên bản chụp (`src/db/snapshot.py`):

```sql
-- sản lượng hôm nay theo nguồn
SELECT source_domain, COUNT(*) FROM articles
WHERE date(fetched_at) = date('now','localtime') GROUP BY source_domain;

-- hàng đợi work_items
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
| `<DATA_ROOT>/logs/monocle.log` | Loguru, rotate 50 MB, giữ 14 ngày |
| `<DATA_ROOT>/notifications/YYYY-MM-DD.log` | 1 dòng / bài khớp rule notify |
| `<DATA_ROOT>/exports/articles-YYYY-MM-DD.csv` | export cuối mỗi cycle (ghi đè) |
| `<DATA_ROOT>/users/output/<user>/<YYYY-MM-DD>.xlsx` | deliverable |

# Sự cố thường gặp

| Vấn đề | Nguyên nhân | Xử lý |
|---|---|---|
| Morninger từ chối khởi động, log "Tiến trình cào tin khác đang chạy" | `capture.lock` đang bị tiến trình khác giữ | tìm và dừng tiến trình đó; khoá file tự nhả khi tiến trình chết |
| Log "Scheduler khác đang chạy" | advisory lock `lock:scheduler` còn của tiến trình cũ | `SELECT * FROM pipeline_state WHERE key='lock:scheduler'`; tiến trình đã chết ⇒ chờ 40′ tự stale |
| Supervisor ngừng khởi động lại morninger | vượt trần số lần restart | sửa nguyên nhân, rồi gửi `/capture restart` |
| `SQLITE_BUSY` | nhiều tiến trình ghi / DB Browser mở chế độ ghi | mở DB Browser read-only |
| Domain ra 0 bài | feed chết, selector đổi, bị chặn | xem `pitfalls` trong YAML; `scripts\validate_capture.py <domain>` |
| Nhiều bài `held` | `SELECTOR_BROKEN` / `TEMPLATE_DRIFT` | sửa `detail.content_selector` rồi `scripts\rederive_from_bronze.py <domain>` |
| `write_user_output.py --date today` ra 0 dòng | backlog ngày cũ | chạy lại với `--days 30` |
| Re-derive luôn `processed=0` | watermark đã vượt | full-scan `rederive_from_bronze.py` |
| FireAnt 401 | token hết hạn | cập nhật [secrets.yaml](../configurations/secrets.md) |
| SSL/cert (HNX) | chain không đủ | `truststore` + Windows cert store |

# Backup

Xem [Deployment › Backup](deployment.md). Bronze (`<DATA_ROOT>/raw_html/**`) là dữ liệu **không
tái tạo được**; Silver và work-package luôn re-derive lại được.

[^deployment]: [Deployment](project/docs/operations/deployment.md)
[^troubleshooting]: [Troubleshooting](project/docs/operations/troubleshooting.md)
[^health]: [health.py](project/src/monitor/health.py)
[^radar]: [radar.py](project/src/ops/console/radar.py)
