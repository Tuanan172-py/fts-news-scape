---
type: Python Pipeline
title: Web Monocle Orchestrator
description: Pipeline thu thập, phân tích cảm xúc và lưu trữ tin tức chứng khoán đa nguồn, điều phối bởi APScheduler.
resource: project/src/orchestrator.py
tags: [pipeline, ingestion, apscheduler, python]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: system-overview
    resource: project/docs/design/01-system-overview.md
    title: System Overview
    author: human:anpt
  - id: execution-flow
    resource: project/docs/design/02-execution-flow.md
    title: Execution Flow
  - id: readme
    resource: project/README.md
    title: Project README
sources_last_checked: 2026-08-03
---

Pipeline Web Monocle được điều phối bởi `src/orchestrator.py`, sử dụng thư viện `APScheduler` để tự động kích hoạt chu kỳ thu thập dữ liệu mỗi 15 phút một lần với `coalesce=True` và `max_instances=1` (không chồng lấn chu kỳ).[^execution-flow]

Quy trình diễn ra tuần tự (synchronous bằng thư viện `requests`, không dùng Scrapy hay Async) để đảm bảo tuân thủ rate limit 3 giây/domain.[^system-overview]

# Execution Flow

Mỗi chu kỳ 15 phút, orchestrator thực hiện tuần tự cho từng domain được kích hoạt:

```
1. Load domain config từ [config/domains/](../configurations/domain_sources.md)
2. Build scraper qua REGISTRY (factory pattern)
3. Scraper.run() → fetch_list() → parse_item() → dedup → enrich()
4. Classify từng article mới ([Rule-based classifier](../pipelines/sentiment_pipeline.md))
5. Sentiment analysis cho bài tiếng Việt ([VN Sentiment Engine](../pipelines/sentiment_pipeline.md))
6. Enqueue vào [DBWriter](../pipelines/db_writer.md) (single-writer thread)
7. File-based notification ([FileNotifier](../references/notifications.md))
8. CSV export nếu có bài mới
9. WAL checkpoint nếu DB > 100MB
```

# CLI Usage

```powershell
# Production: chạy liên tục theo APScheduler
python -m src.orchestrator

# Test: chạy 1 chu kỳ cho tất cả domain rồi thoát
python -m src.orchestrator --once

# Test: chạy 1 chu kỳ cho domain cụ thể
python -m src.orchestrator --once cafef fireant tnck
```

# Graceful Shutdown

Khi nhận SIGINT/SIGTERM, orchestrator gọi `shutdown()`:
1. Flush [DBWriter](../pipelines/db_writer.md) (đợi tất cả pending articles được commit)
2. WAL checkpoint
3. Đóng DedupCache

# Metrics

- **Chu kỳ chạy**: 15 phút/lần
- **Rate limit**: 3 giây/domain
- **Timeout fetch**: 30 giây
- **Retry**: 3 lần, backoff 1.5x
- **Graceful degradation**: Lỗi 1 domain không ảnh hưởng domain khác

# Configuration

Việc thêm mới một nguồn không yêu cầu sửa đổi code, chỉ cần tạo file YAML mới tại `config/domains/<name>.yaml`.[^execution-flow] Các secret và token của API ngoài (VD: FireAnt) được cấu hình tại [secrets.yaml](../configurations/secrets.md).

[^system-overview]: [System Overview](project/docs/design/01-system-overview.md)
[^execution-flow]: [Execution Flow](project/docs/design/02-execution-flow.md)
[^readme]: [Project README](project/README.md)
