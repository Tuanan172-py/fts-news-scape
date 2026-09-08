# Metrics Index

Định nghĩa chỉ số + cách tính. **Không** lưu giá trị runtime — giá trị nằm ở DB/logs.

## Ingestion (Vòng 1)

- [Articles Per Day](articles_per_day.md) — throughput thu thập theo nguồn
- [Dedup Rate](dedup_rate.md) — hiệu quả khử trùng lặp
- [Scraper Health](scraper_health.md) — trạng thái, error rate, latency

## Pipeline (Vòng 2 & 3)

- [Silver Backlog & Handoff Queue](silver_backlog.md) — tồn đọng Bronze→Silver và hàng đợi agent
- [DoD Pass Rate](dod_pass_rate.md) — tỷ lệ output agent qua cổng DoD

## Nội dung (Gold)

- [Sentiment Distribution](sentiment_distribution.md) — phân phối cảm xúc (nguồn: `agent_outputs`)
