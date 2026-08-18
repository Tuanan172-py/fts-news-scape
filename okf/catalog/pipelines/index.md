# Pipelines Index

Danh sách các data pipeline và luồng xử lý chính.

- [Orchestrator](ingestion_scheduler.md) — Pipeline chính, điều phối thu thập & xử lý (APScheduler 15 phút)
- [DBWriter](db_writer.md) — Single-writer background thread ghi SQLite
- [Sentiment Pipeline](sentiment_pipeline.md) — Phân tích cảm xúc tiếng Việt rule-based
