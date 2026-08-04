---
type: Playbook
title: Runbook — Vận hành hệ thống
description: Cẩm nang khởi chạy và kiểm tra chất lượng ứng dụng Web Monocle.
resource: project/docs/runbook.md
tags: [operations, runbook]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: readme
    resource: project/README.md
    title: Project README
  - id: deployment
    resource: project/docs/operations/deployment.md
    title: Deployment Guide
sources_last_checked: 2026-08-03
---

Hướng dẫn vận hành các tập lệnh Python của Web Monocle.

## Khởi chạy

```powershell
# Chạy liên tục với APScheduler (15 phút/chu kỳ)
.venv\Scripts\python.exe -m src.orchestrator

# Chạy 1 chu kỳ duy nhất (test)
.venv\Scripts\python.exe -m src.orchestrator --once

# Chạy 1 chu kỳ cho domain cụ thể
.venv\Scripts\python.exe -m src.orchestrator --once cafef
```

## Kiểm tra sức khỏe

```powershell
# Xem logs (Loguru, lưu 14 ngày, rotate 50MB)
# logs/orchestrator.log

# Kiểm tra trạng thái scraper
sqlite3 data/monocle.db "SELECT * FROM scraper_heartbeat ORDER BY last_run_ts DESC LIMIT 10;"

# Kiểm tra metrics chu kỳ gần nhất
sqlite3 data/monocle.db "SELECT * FROM scraper_metrics ORDER BY ts DESC LIMIT 5;"

# Đếm bài báo hôm nay
sqlite3 data/monocle.db "SELECT source_domain, COUNT(*) FROM articles WHERE date(fetched_at) = date('now', 'localtime') GROUP BY source_domain;"
```

## Cảnh báo

> **Chỉ được chạy MỘT tiến trình orchestrator duy nhất.** Chạy 2 tiến trình song song sẽ nhân đôi lưu lượng và gây rủi ro bị chặn IP.[^deployment]

## Khắc phục sự cố thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| `SQLITE_BUSY` | DB bị lock | Kiểm tra chỉ có 1 tiến trình; WAL mode đã bật chưa |
| SSL/Cert error (HNX) | Chứng chỉ không đầy đủ | `truststore` đã được cấu hình, kiểm tra Windows cert store |
| FireAnt 401 | Token hết hạn | Cập nhật Bearer token trong `config/secrets.yaml` |
| Domain không scrape được | IP bị chặn | Giảm tần suất, kiểm tra rate limit, đổi User-Agent |

[^readme]: [Project README](project/README.md)
[^deployment]: [Deployment Guide](project/docs/operations/deployment.md)
