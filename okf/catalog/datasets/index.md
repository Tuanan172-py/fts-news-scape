# Datasets Index

Các kho dữ liệu của hệ thống, xếp theo tầng medallion (Bronze → Silver → Gold). Mọi đường dẫn nằm dưới `<DATA_ROOT>` = `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`).

- [Bronze Raw Store](bronze_raw_html.md) — `<DATA_ROOT>/raw_html/**`, raw HTML byte-exact (WORM) + `.meta.json`
- [Silver & Work Packages](silver_work_packages.md) — `silver/`, `work_packages/`, packet Article Lane `agent_tasks/article/`, bản ghi `agent_outputs*`
- [Web Monocle DB](web_monocle_db.md) — SQLite WAL `<DATA_ROOT>/monocle.db`, 20 bảng: chỉ mục + trạng thái điều phối
- [User Deliverables](user_deliverables.md) — `<DATA_ROOT>/users/output/**`, một `.xlsx` cho mỗi người dùng mỗi ngày

Đã lưu trữ: kho Bronze báo cáo định kỳ NSO (`raw_reports/`, driver đã xoá) — `okf/archive/catalog/datasets/`.
