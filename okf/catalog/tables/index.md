# Tables Index

12 trong 20 bảng của [Web Monocle DB](../datasets/web_monocle_db.md) có trang riêng, nhóm theo tầng medallion, cộng một bảng đo quá trình làm việc ở `harness.db`. Danh sách đủ 20 bảng: [Web Monocle DB](../datasets/web_monocle_db.md).

## Bronze / ingestion

- [articles](articles.md) — bảng trung tâm, 17 cột, khoá nghiệp vụ `url_title_hash`
- [seen_articles](seen_articles.md) — cache dedup lớp 1 (SHA-256)
- [scraper_heartbeat](scraper_heartbeat.md) — trạng thái hiện thời từng scraper
- [scraper_metrics](scraper_metrics.md) — log hiệu suất mỗi chu kỳ

## Silver / change-detection

- [article_versions](article_versions.md) — nhật ký capture + 5 trạng thái change-detection

## Article Lane

- [work_items](work_items.md) — hàng đợi work-package exactly-once (5 trạng thái); Article Lane chọn bài từ đây
- [l1_outputs](l1_outputs.md) — bản ghi nhận diện thực thể đã qua DoD (nguồn định tuyến người dùng)
- [agent_outputs](agent_outputs.md) — bản ghi nội dung đã qua DoD

## Điều phối

- [pipeline_state](pipeline_state.md) — watermark, checkpoint, advisory lock scheduler

## Legacy (còn trong DDL)

- [l1_tasks](l1_tasks.md) — hàng đợi Lớp 1 của đường L1/Gold đã khai tử; nay chỉ giữ tiêu đề đối chiếu cho cổng DoD nhận diện
- [periodic_reports](periodic_reports.md) — báo cáo định kỳ NSO; driver ghi bảng đã xoá

## Đo quá trình làm việc (ở `harness.db`, **không** ở `monocle.db`)

- [token_ledger](token_ledger.md) — chi phí mỗi đợt: ba rổ token đo thật, quota, tiền, sai số dự toán
