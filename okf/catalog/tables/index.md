# Tables Index

10 bảng trong [Web Monocle DB](../datasets/web_monocle_db.md), nhóm theo tầng medallion.

## Bronze / ingestion

- [articles](articles.md) — bảng trung tâm, 17 cột, khoá nghiệp vụ `url_title_hash`
- [seen_articles](seen_articles.md) — cache dedup lớp 1 (SHA-256)
- [scraper_heartbeat](scraper_heartbeat.md) — trạng thái hiện thời từng scraper
- [scraper_metrics](scraper_metrics.md) — log hiệu suất mỗi chu kỳ

## Silver / change-detection

- [article_versions](article_versions.md) — nhật ký capture + 5 trạng thái change-detection

## Handoff & Gold (agent)

- [work_items](work_items.md) — hàng đợi handoff exactly-once (5 trạng thái)
- [l1_tasks](l1_tasks.md) — hàng đợi Lớp 1 nhận diện thực thể
- [l1_outputs](l1_outputs.md) — output Lớp 1 đã qua DoD (nguồn định tuyến người dùng)
- [agent_outputs](agent_outputs.md) — output Lớp 2 (Gold) đã qua DoD

## Điều phối

- [pipeline_state](pipeline_state.md) — watermark, checkpoint, advisory lock scheduler
