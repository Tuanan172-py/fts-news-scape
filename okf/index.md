---
okf_version: "0.2"
---
# Web Monocle Knowledge Base

Kho tri thức của hệ thống **Web Monocle** (repo `FRA_DataIngestion — news-scape`) — nền tảng thu
thập, chuẩn hoá và phân tích tin tức thị trường Việt Nam. Chuẩn **Open Knowledge Format (OKF)
v0.2**. Cập nhật gần nhất: **2026-09-21**.

## Tổng quan hệ thống

Kiến trúc **medallion 3 vòng**, standalone (1 máy, 1 SQLite, không dịch vụ ngoài):

1. **Vòng 1 — Capture (Bronze).** 8/24 domain đang bật, thu qua RSS + reverse API + HTML
   listing; mỗi bài lưu raw HTML **byte-exact (WORM)** trước mọi xử lý; dedup SHA-256.
2. **Vòng 2 — Standardize (Silver).** Bronze → clean base → change-detection 5 trạng thái →
   work-package → hàng đợi handoff. Toàn bộ **re-derivable**.
3. **Vòng 3 — Agent handoff (Gold).** Agent NGOÀI làm việc qua JSON Schema và cổng
   Definition-of-Done. **Repo không chứa lời gọi LLM.** Từ 2026-09-18, đường mặc định là
   [Article Lane](catalog/pipelines/article_lane.md): nhận diện thực thể và xử lý nội dung gộp
   vào **một lượt gọi cho trọn lô**, chạy trên harness DSH, với tiền tố tĩnh ~11.143 token
   trúng bộ nhớ đệm và sổ cái đo chi phí thật từng đợt. Đường hai lớp cũ giữ để quay lui.

Sản phẩm cuối: `users/output/<user>/<YYYY-MM-DD>.csv` — tin đã lọc theo danh mục từng người
dùng, định tuyến bằng ontology 2.152 thực thể.

## Thư mục tri thức

Toàn bộ concept nằm dưới [`catalog/`](catalog/) (nhà canonical duy nhất). Bản đồ module↔file:
[`MAPPING.md`](MAPPING.md). Lịch sử: [`log.md`](log.md).

- [Datasets](catalog/datasets/index.md) — Bronze raw store, Bronze báo cáo định kỳ, Silver/work-package, SQLite DB, deliverable
- [Tables](catalog/tables/index.md) — 11 bảng SQLite + sổ cái token ở `harness.db`
- [Pipelines](catalog/pipelines/index.md) — morninger, capture, silver derive, **Article Lane**, agent handoff (quay lui), user output, báo cáo định kỳ NSO
- [Metrics](catalog/metrics/index.md) — throughput, dedup, health, backlog, DoD pass rate, **sàn bộ nhớ đệm**
- [Playbooks](catalog/playbooks/index.md) — deployment, runbook, chu kỳ agent hằng ngày
- [References](catalog/references/index.md) — kiến trúc, mã nguồn, hợp đồng agent, **kinh tế token**
- [Configurations](catalog/configurations/index.md) — settings, nguồn tin, entity, đăng ký người dùng, **bảng giá token**

## Bắt đầu từ đâu

| Bạn muốn | Đọc |
|---|---|
| Hiểu tổng thể | [References › Kiến trúc](catalog/references/architecture.md) |
| Sửa/thêm nguồn tin | [Configurations › Domain Sources](catalog/configurations/domain_sources.md) |
| Truy vấn dữ liệu | [Datasets › Web Monocle DB](catalog/datasets/web_monocle_db.md) + [Tables](catalog/tables/index.md) |
| Vận hành hằng ngày | [Playbooks › Runbook](catalog/playbooks/runbook.md), [Daily Agent Run](catalog/playbooks/daily_agent_run.md) |
| Làm việc với agent | [References › Agent Contracts](catalog/references/agent_contracts.md) |
| Chạy một đợt bài đăng | [Pipelines › Article Lane](catalog/pipelines/article_lane.md) + `.agents/dsh/RUNBOOK-article-lane.md` |
| Hiểu chi phí và bộ nhớ đệm | [References › Kinh tế token](catalog/references/token_economy.md) |

## Tài liệu gốc

OKF **mô tả** hệ thống; nguồn đúng vẫn là code và `project/docs/`:

- `project/docs/design/` — 00 (bản đồ 3 vòng) → 15 (multi-agent orchestration)
- `project/docs/dev/` — codebase, data model, thêm nguồn, testing, known issues
- `project/docs/operations/` — deployment, runbook per-user, troubleshooting, DB handbook
- `project/schemas/` — 5 hợp đồng JSON Schema + hướng dẫn prompt
- `.agents/dsh/` — vận hành Article Lane trên DSH: `RUNBOOK-article-lane.md` (gõ gì),
  `WORKFLOW-article-lane.md` (sáu lưu đồ), `DSH-VIEC-THU-CONG.md` (việc chỉ làm được bằng tay)
- `docs/proposals/dsh-surface-verified-2026-09-18.md` — bề mặt DSH xác minh bằng mã nguồn

## Kiểm tra độ tươi

```powershell
"project/.venv/Scripts/python.exe" okf/tools/okf_check.py outdated
```

Xem [`tools/README.md`](tools/README.md).
