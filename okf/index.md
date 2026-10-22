---
okf_version: "0.2"
---
# Web Monocle Knowledge Base

Kho tri thức của hệ thống **Web Monocle** (repo `news-scape`, cây mã chuẩn `C:\src\news-scraper`)
— nền tảng thu thập, chuẩn hoá và phân tích tin tức thị trường Việt Nam. Chuẩn **Open Knowledge
Format (OKF) v0.2**. Cập nhật gần nhất: **2026-10-22**.

## Tổng quan hệ thống

Kiến trúc **medallion 3 vòng**, standalone (1 máy, 1 SQLite vận hành ở
`C:\data\news-scape\monocle.db`, gốc dữ liệu `MONOCLE_DATA_DIR`):

1. **Vòng 1 — Capture (Bronze).** 8/24 domain đang bật, thu qua RSS + reverse API + HTML
   listing; mỗi bài lưu raw HTML **byte-exact (WORM)** trước mọi xử lý; dedup SHA-256.
2. **Vòng 2 — Standardize (Silver).** Bronze → clean base → change-detection 5 trạng thái →
   work-package → hàng đợi `work_items`. Toàn bộ **re-derivable**.
3. **Vòng 3 — [Article Lane](catalog/pipelines/article_lane.md)**, đường xử lý **duy nhất**
   (ADR-0010): nhận diện thực thể và xử lý nội dung trong **một lượt gọi mô hình cho trọn lô**,
   qua runner DSH, agy, opencode hoặc OpenRouter; nạp DB qua cổng Definition-of-Done thuần code.
   Đường hai lớp L1/Gold cũ đã khai tử.

Vận hành không người trực: `ops_daemon` (Task Scheduler `news-scape-ops`) giữ capture sống và
mở đợt Article Lane (ADR-0012). Sản phẩm cuối: `<DATA_ROOT>/users/output/<user>/<YYYY-MM-DD>.xlsx`
— tin đã lọc theo danh mục từng người dùng, định tuyến bằng ontology thực thể; publish một chiều
lên SharePoint sandbox qua `scripts/publish.py`.

## Thư mục tri thức

Toàn bộ concept nằm dưới [`catalog/`](catalog/) (nhà canonical duy nhất). Bản đồ module↔file:
[`MAPPING.md`](MAPPING.md). Lịch sử: [`log.md`](log.md). Trang đã lưu trữ (chủ đề đã khai tử):
`archive/`.

- [Datasets](catalog/datasets/index.md) — Bronze raw store, Silver/work-package/packet, SQLite DB, deliverable
- [Tables](catalog/tables/index.md) — 12 trong 20 bảng SQLite + sổ cái token ở `harness.db`
- [Pipelines](catalog/pipelines/index.md) — morninger, capture, silver derive, **Article Lane**, ingest & cổng DoD, user output
- [Metrics](catalog/metrics/index.md) — throughput, dedup, health, backlog, DoD pass rate, **sàn bộ nhớ đệm**
- [Playbooks](catalog/playbooks/index.md) — deployment, runbook
- [References](catalog/references/index.md) — kiến trúc, mã nguồn (sau ADR-0027), hợp đồng agent, **kinh tế token**
- [Configurations](catalog/configurations/index.md) — settings, nguồn tin, entity, đăng ký người dùng, **bảng giá token**

## Bắt đầu từ đâu

| Bạn muốn | Đọc |
|---|---|
| Hiểu tổng thể | [References › Kiến trúc](catalog/references/architecture.md) |
| Sửa/thêm nguồn tin | [Configurations › Domain Sources](catalog/configurations/domain_sources.md) |
| Truy vấn dữ liệu | [Datasets › Web Monocle DB](catalog/datasets/web_monocle_db.md) + [Tables](catalog/tables/index.md) |
| Vận hành hằng ngày | [Playbooks › Runbook](catalog/playbooks/runbook.md) (radar trước) |
| Làm việc với agent | [References › Agent Contracts](catalog/references/agent_contracts.md) |
| Chạy một đợt bài đăng | [Pipelines › Article Lane](catalog/pipelines/article_lane.md) + `.agents/dsh/RUNBOOK-article-lane.md` |
| Hiểu chi phí và bộ nhớ đệm | [References › Kinh tế token](catalog/references/token_economy.md) |

## Tài liệu gốc

OKF **mô tả** hệ thống; nguồn đúng vẫn là code và `project/docs/`:

- `project/docs/design/` — thiết kế còn hiệu lực (00 bản đồ 3 vòng, 02 luồng chạy, 03, 05–08, 12, 14); bản đã khai tử ở `project/docs/archive/`
- `project/docs/dev/` — codebase, data model, thêm nguồn, testing, known issues
- `project/docs/operations/` — deployment, ops daemon, publisher, troubleshooting
- `project/schemas/` — hợp đồng JSON Schema + hướng dẫn prompt
- `docs/decisions/` — ADR (0010 Article Lane duy nhất, 0012 vận hành tự chủ, 0026 publish + thứ tự runner, 0027 ranh giới module)
- `.agents/dsh/` — vận hành Article Lane trên DSH: `RUNBOOK-article-lane.md` (gõ gì),
  `WORKFLOW-article-lane.md` (lưu đồ), `DSH-VIEC-THU-CONG.md` (việc chỉ làm được bằng tay)

## Kiểm tra độ tươi

```powershell
& "C:/venvs/news-scape/Scripts/python.exe" okf/tools/okf_check.py outdated
```

Xem [`tools/README.md`](tools/README.md).
