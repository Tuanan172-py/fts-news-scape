# Pipelines Index

Luồng xử lý, xếp theo 3 vòng của [kiến trúc end-to-end](../references/architecture.md).

## Điều phối

- [Morninger](morninger.md) — **entrypoint prod**, 1 tiến trình / 3 job (capture 15′, re-derive 30′, drift sáng)

## Vòng 1 — Capture (Bronze)

- [Capture Orchestrator](ingestion_scheduler.md) — chu kỳ scraper, dedup, capture raw byte-exact
- [DBWriter](db_writer.md) — single-writer thread ghi bảng `articles`

## Vòng 2 — Standardize (Silver)

- [Silver Derive](silver_derive.md) — Bronze → Silver → change-detection → work-package → catalog

## Vòng 3 — Agent handoff (Gold)

- [Agent Handoff](agent_handoff.md) — 2 lớp agent, export/ingest packet, cổng DoD
- [User Output Workflow](user_output.md) — gate 2 lớp, định tuyến entity, ghi CSV người dùng

## Legacy

- [Sentiment Pipeline](sentiment_pipeline.md) — ⚠️ *deprecated*: sentiment rule-based đã gỡ khỏi
  workflow; chỉ bước classify còn chạy
