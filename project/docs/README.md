# Tài liệu sản phẩm news-scape

Mục lục tài liệu hiện hành của `project/`. Cập nhật 2026-10-22 (US-050). Lối vào cho agent là `AGENTS.md` ở gốc kho; quyết định kiến trúc nằm ở `docs/decisions/` (mục lục `docs/INDEX.md`).

## Đọc theo đối tượng

| Bạn là | Bắt đầu ở |
|---|---|
| Mới, cần bức tranh lớn | [design/00-end-to-end-architecture.md](design/00-end-to-end-architecture.md), sơ đồ [diagrams/index.html](diagrams/index.html) |
| Dev sắp sửa code | [dev/01-codebase-guide.md](dev/01-codebase-guide.md), luật ranh giới module `.agents/rules/12-module-boundaries.md` (ADR-0027) |
| Muốn thêm nguồn tin | [dev/03-adding-a-source.md](dev/03-adding-a-source.md) |
| Vận hành hằng ngày | [operations/ops-daemon.md](operations/ops-daemon.md), runbook Article Lane `.agents/dsh/RUNBOOK-article-lane.md` |
| Xử lý sự cố | [operations/troubleshooting.md](operations/troubleshooting.md) |
| Tìm hiểu một nguồn tin | [domains/README.md](domains/README.md), [skills/](skills/) |

## design/ — Thiết kế

- [00-end-to-end-architecture.md](design/00-end-to-end-architecture.md): kiến trúc 6 lớp, Article Lane, module sau ADR-0027.
- [02-execution-flow.md](design/02-execution-flow.md): luồng thực thi capture Bronze.
- [03-source-strategy.md](design/03-source-strategy.md): chiến lược tiếp cận và xử lý nguồn.
- [05-notification-coverage.md](design/05-notification-coverage.md): phạm vi thông báo.
- [06-raw-html-capture.md](design/06-raw-html-capture.md): lưu HTML gốc (Bronze).
- [07-storage-layers-and-change-detection.md](design/07-storage-layers-and-change-detection.md): các lớp lưu trữ và phát hiện thay đổi.
- [08-handoff-contract-catalog.md](design/08-handoff-contract-catalog.md): hợp đồng work package và catalog.
- [12-bronze-to-silver-rules.md](design/12-bronze-to-silver-rules.md): quy tắc Bronze sang Silver.
- [14-entity-system-and-mapping.md](design/14-entity-system-and-mapping.md): hệ thực thể và ánh xạ watchlist.

## dev/ — Cho lập trình viên

- [01-codebase-guide.md](dev/01-codebase-guide.md): cây `src/`, CLI mỏng trong `scripts/`, test theo gói.
- [02-data-model-and-db.md](dev/02-data-model-and-db.md): mô hình dữ liệu và SQLite.
- [03-adding-a-source.md](dev/03-adding-a-source.md): thêm nguồn tin, có checklist.
- [04-testing.md](dev/04-testing.md): bố cục `tests/<gói>/`, cách chạy test.
- [05-known-issues.md](dev/05-known-issues.md): vấn đề đã biết.
- [06-raw-html-capture-guide.md](dev/06-raw-html-capture-guide.md): phát triển capture Bronze.
- [08-git-codebase-governance-guide.md](dev/08-git-codebase-governance-guide.md): git và quản trị codebase.

## operations/ — Vận hành

- [ops-daemon.md](operations/ops-daemon.md) và [ops-daemon-reference.md](operations/ops-daemon-reference.md): vận hành tự chủ L0/L1 (ADR-0012, ADR-0026).
- [publisher.md](operations/publisher.md): xuất bản lên SharePoint sandbox (ADR-0026.D1).
- [deployment.md](operations/deployment.md): cài đặt và chạy nền.
- [troubleshooting.md](operations/troubleshooting.md): triệu chứng và cách xử lý.
- [user-venv-guide.md](operations/user-venv-guide.md): chạy script bằng `C:\venvs\news-scape`.
- [runbook.md](runbook.md): quy trình capture và Silver.

## Nguồn tin và tham chiếu

- [domains/](domains/README.md): ma trận nguồn, API, RSS, HTML, sàn.
- [skills/](skills/): đặc thù từng nguồn (cafef, fireant, tnck, rss-sources).
- [reference/](reference/README.md): artifact capture có chú thích.
- [entities.md](entities.md), [rss-reference.md](rss-reference.md), [architecture.md](architecture.md) (TDR gốc Phase 1).
- [diagrams/](diagrams/README.md): sơ đồ vận hành (Mermaid, mở `index.html` offline).

## Lưu trữ

- [archive/](archive/): tài liệu của lane L1/Gold đã ngừng (ADR-0010), công cụ đã xoá ở US-049 và quy trình hai máy trên OneDrive (ADR-0024). Mỗi tệp có dòng đầu chỉ tới tài liệu thay thế.
- [others/](others/): báo cáo và ghi chép lịch sử.
