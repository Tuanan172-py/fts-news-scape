---
type: Playbook
title: Hướng dẫn Triển khai (Deployment)
description: Cài đặt và chạy hệ thống trên máy local Windows 11 — venv C:\venvs\news-scape, cấu hình bắt buộc, ops_daemon chạy nền, backup.
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
  - id: ops-install
    resource: project/scripts/ops_install.ps1
    title: Đăng ký Task Scheduler news-scape-ops + watchdog
sources_last_checked: 2026-10-22
---

Hệ thống là **standalone**: một máy, một SQLite. Môi trường tham chiếu: **Windows 11, Python
3.13, venv `C:\venvs\news-scape`** (ngoài OneDrive, không tạo `.venv` trong repo, ADR-0024). Cây
mã chuẩn `C:\src\news-scraper`. Mọi lệnh chạy từ `project/`.[^deployment-doc]

Dữ liệu vận hành nằm dưới `<DATA_ROOT>` = `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`);
mọi đường dẫn do `src/core/paths.py` quyết định. DB: `C:\data\news-scape\monocle.db`.

# Cài đặt

```powershell
python -m venv C:\venvs\news-scape
C:\venvs\news-scape\Scripts\python.exe -m pip install -r requirements.txt
```

Danh sách phụ thuộc đầy đủ: `project/requirements.txt`.

# Cấu hình trước khi chạy

| File | Bắt buộc? | Ghi chú |
|---|---|---|
| [`config/settings.yaml`](../configurations/settings.md) | có sẵn | DB `C:/data/news-scape/monocle.db`, capture 10′, re-derive 30′, rate 3s |
| [`config/watchlist.yaml`](../configurations/watchlist.md) | có sẵn | 30 mã blue-chip |
| [`config/domains/*.yaml`](../configurations/domain_sources.md) | có sẵn | 8 domain đang bật |
| [`config/secrets.yaml`](../configurations/secrets.md) | **chỉ khi bật FireAnt** | copy từ `.example`, điền `fireant_token` |
| [`<DATA_ROOT>/subscriptions/`](../configurations/user_subscriptions.md) | cho lớp người dùng | file danh mục + `manifest.yaml` |

```powershell
Copy-Item config\secrets.yaml.example config\secrets.yaml
```

# Chạy

**Chuẩn — không người trực (ADR-0012):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Register -Start
```

Đăng ký `news-scape-ops` và `news-scape-ops-watchdog`. Daemon giữ
[morninger](../pipelines/morninger.md) sống và mở đợt [Article Lane](../pipelines/article_lane.md).
Không tạo thêm task riêng cho morninger.

**Chạy tay (dev, thử nghiệm):**

```powershell
C:\venvs\news-scape\Scripts\python.exe -m src.morninger                   # capture + Silver liên tục
C:\venvs\news-scape\Scripts\python.exe -m src.orchestrator --once cafef   # 1 cycle vài domain
```

Chỉ MỘT tiến trình cào tại một thời điểm: file lock `capture.lock` từ chối tiến trình thứ hai.
Khi daemon đã cài, không khởi động thêm morninger bằng tay.

# Dung lượng

**Chưa có script prune/rotation** cho DB (câu hỏi mở trong `project/docs/dev/05-known-issues.md`).
Bronze `<DATA_ROOT>/raw_html/**` tăng theo số bài — cần theo dõi đĩa.

# Backup

| Đối tượng | Cách | Ưu tiên |
|---|---|---|
| `<DATA_ROOT>/raw_html/**` (Bronze) | copy thư mục | **cao nhất** — không tái tạo được |
| `<DATA_ROOT>/monocle.db` | copy khi không có tiến trình ghi (orchestrator tự `wal_checkpoint(TRUNCATE)` cuối mỗi cycle), hoặc bản chụp qua `src/db/snapshot.py` | cao |
| `project/config/**` (trừ secrets) | đã ở trong git | trung bình |
| `<DATA_ROOT>/silver`, `<DATA_ROOT>/work_packages` | không cần — re-derive được | thấp |

Dữ liệu dùng chung xuất bản một chiều lên SharePoint sandbox qua `scripts/publish.py`
(ADR-0026.D1).

# Liên quan

- [Runbook](runbook.md) · [Web Monocle DB](../datasets/web_monocle_db.md)

[^deployment-doc]: [Deployment Guide](project/docs/operations/deployment.md)
[^readme]: [Project README](project/README.md)
[^ops-install]: [ops_install.ps1](project/scripts/ops_install.ps1)
