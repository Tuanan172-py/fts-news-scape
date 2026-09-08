---
okf_version: "0.2"
---
# Web Monocle Knowledge Base

Kho tri thức của hệ thống **Web Monocle** (repo `FRA_DataIngestion — news-scape`) — nền tảng thu
thập, chuẩn hoá và phân tích tin tức thị trường Việt Nam. Chuẩn **Open Knowledge Format (OKF)
v0.2**. Cập nhật gần nhất: **2026-09-07**.

## Tổng quan hệ thống

Kiến trúc **medallion 3 vòng**, standalone (1 máy, 1 SQLite, không dịch vụ ngoài):

1. **Vòng 1 — Capture (Bronze).** 7/24 domain đang bật, thu qua RSS + reverse API + HTML
   listing; mỗi bài lưu raw HTML **byte-exact (WORM)** trước mọi xử lý; dedup SHA-256.
2. **Vòng 2 — Standardize (Silver).** Bronze → clean base → change-detection 5 trạng thái →
   work-package → hàng đợi handoff. Toàn bộ **re-derivable**.
3. **Vòng 3 — Agent handoff (Gold).** Hai lớp agent NGOÀI (nhận diện thực thể + phân tích nội
   dung) làm việc qua JSON Schema và cổng Definition-of-Done. **Repo không chứa lời gọi LLM.**

Sản phẩm cuối: `users/output/<user>/<YYYY-MM-DD>.csv` — tin đã lọc theo danh mục từng người
dùng, định tuyến bằng ontology 2.152 thực thể.

## Thư mục tri thức

Toàn bộ concept nằm dưới [`catalog/`](catalog/) (nhà canonical duy nhất). Bản đồ module↔file:
[`MAPPING.md`](MAPPING.md). Lịch sử: [`log.md`](log.md).

- [Datasets](catalog/datasets/index.md) — Bronze raw store, Silver/work-package, SQLite DB, deliverable
- [Tables](catalog/tables/index.md) — 10 bảng SQLite
- [Pipelines](catalog/pipelines/index.md) — morninger, capture, silver derive, agent handoff, user output
- [Metrics](catalog/metrics/index.md) — throughput, dedup, health, backlog, DoD pass rate
- [Playbooks](catalog/playbooks/index.md) — deployment, runbook, chu kỳ agent hằng ngày
- [References](catalog/references/index.md) — kiến trúc, mã nguồn, hợp đồng agent
- [Configurations](catalog/configurations/index.md) — settings, nguồn tin, entity, đăng ký người dùng

## Bắt đầu từ đâu

| Bạn muốn | Đọc |
|---|---|
| Hiểu tổng thể | [References › Kiến trúc](catalog/references/architecture.md) |
| Sửa/thêm nguồn tin | [Configurations › Domain Sources](catalog/configurations/domain_sources.md) |
| Truy vấn dữ liệu | [Datasets › Web Monocle DB](catalog/datasets/web_monocle_db.md) + [Tables](catalog/tables/index.md) |
| Vận hành hằng ngày | [Playbooks › Runbook](catalog/playbooks/runbook.md), [Daily Agent Run](catalog/playbooks/daily_agent_run.md) |
| Làm việc với agent | [References › Agent Contracts](catalog/references/agent_contracts.md) |

## Tài liệu gốc

OKF **mô tả** hệ thống; nguồn đúng vẫn là code và `project/docs/`:

- `project/docs/design/` — 00 (bản đồ 3 vòng) → 15 (multi-agent orchestration)
- `project/docs/dev/` — codebase, data model, thêm nguồn, testing, known issues
- `project/docs/operations/` — deployment, runbook per-user, troubleshooting, DB handbook
- `project/schemas/` — 5 hợp đồng JSON Schema + hướng dẫn prompt

## Kiểm tra độ tươi

```powershell
"project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated
```

Xem [`tools/README.md`](tools/README.md).
