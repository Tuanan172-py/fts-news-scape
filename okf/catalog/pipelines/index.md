# Pipelines Index

Luồng xử lý, xếp theo 3 vòng của [kiến trúc end-to-end](../references/architecture.md).

## Điều phối

- [Morninger](morninger.md) — tiến trình capture + Silver thường trú, 4 job (capture 10′, re-derive 30′, drift sáng, reclaim), được `ops_daemon` giữ sống

## Vòng 1 — Capture (Bronze)

- [Capture Orchestrator](ingestion_scheduler.md) — chu kỳ scraper, dedup, capture raw byte-exact
- [DBWriter](db_writer.md) — single-writer thread ghi bảng `articles`

## Vòng 2 — Standardize (Silver)

- [Silver Derive](silver_derive.md) — Bronze → Silver → change-detection → work-package → catalog

## Vòng 3 — Article Lane

- [Article Lane](article_lane.md) — **đường xử lý duy nhất** (ADR-0010): nhận diện thực thể + nội dung trong MỘT lượt gọi cho trọn lô
- [Agent Ingest & cổng DoD](agent_handoff.md) — nửa hoàn tất: `l1_ingest.py` + `agent_ingest.py`, cổng DoD thuần code
- [User Output Workflow](user_output.md) — gate DoD, định tuyến entity, ghi `.xlsx` cho từng người dùng

Đã lưu trữ: báo cáo định kỳ NSO và engine sentiment rule-based (mã đã xoá) — xem `okf/archive/catalog/pipelines/`.
