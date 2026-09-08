# Datasets Index

Các kho dữ liệu của hệ thống, xếp theo tầng medallion (Bronze → Silver → Gold).

- [Bronze Raw Store](bronze_raw_html.md) — `data/raw_html/**`, raw HTML byte-exact (WORM) + `.meta.json`
- [Silver & Work Packages](silver_work_packages.md) — `data/silver`, `data/work_packages`, `data/agent_tasks`, `data/agent_outputs*`
- [Web Monocle DB](web_monocle_db.md) — SQLite WAL, 10 bảng: chỉ mục + trạng thái điều phối
- [User Deliverables](user_deliverables.md) — `users/output/**`, CSV cuối cho từng người dùng
