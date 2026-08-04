---
okf_version: "0.2"
---
# Web Monocle Knowledge Base

Kho tri thức của hệ thống **Web Monocle** — nền tảng thu thập và phân tích tin tức chứng khoán Việt Nam đa nguồn. Được thiết lập theo chuẩn **Open Knowledge Format (OKF) v0.2**.

## Tổng quan Hệ thống

Web Monocle thu thập tin tức từ 23 domain qua RSS, API reverse-engineer, và HTML scraping. Dữ liệu được pipeline xử lý qua các bước: fetch → parse → dedup (SHA-256) → classify → sentiment analysis (VN NLP) → SQLite WAL.

## Thư mục Tri thức

- [Datasets](datasets/index.md) — Cơ sở dữ liệu và data stores
- [Tables](tables/index.md) — Schema các bảng dữ liệu
- [Pipelines](pipelines/index.md) — Data pipelines và luồng xử lý
- [Metrics](metrics/index.md) — Chỉ số kinh doanh và kỹ thuật
- [Playbooks](playbooks/index.md) — Runbook vận hành và triển khai
- [References](references/index.md) — Tài liệu tham khảo kiến trúc
- [Configurations](configurations/index.md) — Cấu hình hệ thống

## Tài liệu gốc

Toàn bộ documentation gốc của dự án nằm tại [`project/docs/`](../project/docs/):
- `design/` — Tài liệu thiết kế hệ thống
- `dev/` — Hướng dẫn phát triển
- `operations/` — Hướng dẫn vận hành
