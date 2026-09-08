---
type: Playbook
title: Hướng dẫn Triển khai (Deployment)
description: Cài đặt và chạy hệ thống trên máy local Windows 11 — venv, cấu hình bắt buộc, chạy nền, backup.
resource: project/docs/operations/deployment.md
tags: [deployment, operations, setup, windows]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
verified:
  at: 2026-08-04T00:00:00Z
sources:
  - id: deployment-doc
    resource: project/docs/operations/deployment.md
    title: Deployment Guide
  - id: readme
    resource: project/README.md
    title: Project README — Quick Start
  - id: run-daily
    resource: project/scripts/run_daily.ps1
    title: run_daily.ps1
sources_last_checked: 2026-09-07
---

Hệ thống là **standalone**: một máy, một SQLite, không phụ thuộc dịch vụ ngoài. Môi trường tham
chiếu: **Windows 11, Python 3.10+ (đang chạy 3.14), venv `.venv`**.[^deployment-doc]

# Cài đặt

```powershell
cd "<repo>\project"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Phụ thuộc chính: `feedparser`, `requests`, `urllib3`, `truststore`, `trafilatura`,
`beautifulsoup4` + `lxml`, `rapidfuzz`, `APScheduler`, `loguru`, `pyyaml`, `openpyxl`,
`jsonschema`. (`pyvi` chỉ cần nếu bật lại engine sentiment legacy.)

# Cấu hình trước khi chạy

| File | Bắt buộc? | Ghi chú |
|---|---|---|
| [`config/settings.yaml`](../configurations/settings.md) | có sẵn | kiểm tra interval 15′, rate 3s |
| [`config/watchlist.yaml`](../configurations/watchlist.md) | có sẵn | 30 mã blue-chip |
| [`config/domains/*.yaml`](../configurations/domain_sources.md) | có sẵn | 7 domain đang bật |
| [`config/secrets.yaml`](../configurations/secrets.md) | **chỉ khi bật FireAnt** | copy từ `.example`, điền token |
| [`users/subscriptions/<name>.xlsx`](../configurations/user_subscriptions.md) | cho lớp người dùng | người dùng tự khai danh mục |

```powershell
Copy-Item config\secrets.yaml.example config\secrets.yaml
```

# Chạy

```powershell
# PROD
.venv\Scripts\python.exe -m src.morninger

# chuỗi per-user theo lô (Vòng 3)
.\scripts\run_daily.ps1 -Mode emit           # phát packet
.\scripts\run_daily.ps1 -Mode ingest -Days 30  # nạp output + ghi CSV + báo cáo
```

# Chạy nền

- **Dev** — terminal, dừng bằng Ctrl+C (SIGINT ⇒ graceful shutdown, flush DBWriter).
- **Bền hơn** — Windows Task Scheduler hoặc NSSM chạy `-m src.morninger`. Đảm bảo **1 instance**;
  không đặt đồng thời scheduler mode và cron `--once`.
- **Cron ngoài** — nếu muốn tự điều phối, dùng `--once` mỗi lần và **không** chạy scheduler mode.

Ghi chú: `scripts/run_daily.ps1` tự dò Python và **bỏ qua** `.venv` shim nếu đường dẫn chứa dấu
cách gây lỗi — kiểm tra dòng log `run_daily: Mode=…` để biết interpreter nào đang được dùng.

# Dung lượng

DB đang ~550 MB và **chưa có script prune/rotation** (câu hỏi mở trong
`docs/dev/05-known-issues.md`). Bronze `data/raw_html/**` tăng theo số bài — cần theo dõi đĩa.

# Backup

| Đối tượng | Cách | Ưu tiên |
|---|---|---|
| `data/raw_html/**` (Bronze) | copy thư mục | **cao nhất** — không tái tạo được |
| `data/monocle.db` | `wal_checkpoint(TRUNCATE)` rồi copy, hoặc `scripts/db_snapshot.py` | cao |
| `config/**` (trừ secrets), `data/entities/**` | đã ở trong git | trung bình |
| `data/silver`, `data/work_packages` | không cần — re-derive được | thấp |

# Liên quan

- [Runbook](runbook.md) · [Daily Agent Run](daily_agent_run.md) ·
  [Web Monocle DB](../datasets/web_monocle_db.md)

[^deployment-doc]: [Deployment Guide](project/docs/operations/deployment.md)
[^readme]: [Project README](project/README.md)
[^run-daily]: [run_daily.ps1](project/scripts/run_daily.ps1)
