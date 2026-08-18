---
type: Playbook
title: Hướng dẫn Triển khai (Deployment)
description: Cẩm nang triển khai hệ thống Web Monocle trên môi trường local Windows 11.
resource: project/docs/operations/deployment.md
tags: [deployment, operations, setup]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
verified:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: deployment-doc
    resource: project/docs/operations/deployment.md
    title: Deployment Guide
    author: human:anpt
  - id: readme
    resource: project/README.md
    title: Project README
sources_last_checked: 2026-08-04
---

Hướng dẫn thiết lập và chạy hệ thống thu thập tin tức Web Monocle trên môi trường local. Môi trường tham chiếu chuẩn: **Windows 11, Python 3.14** thông qua Virtual Environment (`.venv`).[^deployment-doc]

## Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| OS | Windows 11 |
| Python | 3.14 |
| Disk | ~500MB cho DB + logs (tăng ~50MB/tuần với 2 domain active) |

## Cài đặt

```powershell
# 1. Clone repo
cd "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape\project"

# 2. Tạo virtual environment
python -m venv .venv

# 3. Cài dependencies
.venv\Scripts\pip install -r requirements.txt

# 4. Cấu hình secrets (bắt buộc trước khi chạy)
cp config/secrets.yaml.example config/secrets.yaml
# → Điền FireAnt bearer token vào secrets.yaml
```

## Dependencies chính

`feedparser`, `requests`, `urllib3`, `truststore`, `trafilatura`, `beautifulsoup4`, `lxml`, `rapidfuzz`, `pyvi`, `APScheduler`, `loguru`, `pyyaml`.[^deployment-doc]

## Cấu hình bắt buộc trước khi chạy

1. **`config/secrets.yaml`**: Token FireAnt (file được gitignore để bảo mật)
2. **`config/settings.yaml`**: DB path, logging config, scheduler interval
3. **`config/watchlist.yaml`**: Danh sách 30 mã blue-chip cần theo dõi

Xem chi tiết tại:
- [settings.yaml](../configurations/settings.md)
- [secrets.yaml](../configurations/secrets.md)
- [watchlist.yaml](../configurations/watchlist.md)

## Kịch bản chạy (Execution Runbooks)

```powershell
# Kịch bản 1: Production (chạy liên tục, APScheduler 15 phút/lần)
.venv\Scripts\python.exe -m src.orchestrator

# Kịch bản 2: Test/CronJob (chạy 1 chu kỳ rồi thoát)
.venv\Scripts\python.exe -m src.orchestrator --once

# Kịch bản 3: Chạy domain cụ thể
.venv\Scripts\python.exe -m src.orchestrator --once cafef fireant tnck
```

> **Cảnh báo**: Chỉ được phép chạy MỘT tiến trình scheduler duy nhất. Việc chạy hai tiến trình song song sẽ nhân đôi lưu lượng và gây rủi ro bị chặn IP.[^deployment-doc]

## Monitoring

```powershell
# Theo dõi logs realtime
Get-Content logs/orchestrator.log -Wait

# Kiểm tra trạng thái scraper
sqlite3 data/monocle.db "SELECT scraper_name, status, last_run_ts, consecutive_failures FROM scraper_heartbeat;"

# Kiểm tra metrics gần nhất
sqlite3 data/monocle.db "SELECT ts, scraper_name, articles_fetched, articles_new, errors FROM scraper_metrics ORDER BY ts DESC LIMIT 10;"
```

[^deployment-doc]: [Deployment Guide](project/docs/operations/deployment.md)
[^readme]: [Project README](project/README.md)
