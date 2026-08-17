# Schema Changelog

Chính sách: **additive/optional only**, bump `*_schema_version`, giữ ≥2 version đọc được
(BACKWARD_TRANSITIVE). Bump schema KHÔNG cần re-scrape → `scripts/rederive_from_bronze.py`.

## silver-v1 (1.0) — 2026-08-14
- Khởi tạo: article_id, source_url, domain, content_sha256, cleaned_text, built_from_raw_path (required);
  structure/images/language/built_at (optional).

## work-package-v1 (1.0) — 2026-08-14
- Khởi tạo INPUT contract. Required: schema_version, article_id, source_url, domain, raw_html_path,
  raw_sha256, cleaned_text, capture_status, change_state. Trỏ raw (không inline bytes).

## agent-output-v1 (1.0) — 2026-08-14
- Khởi tạo OUTPUT contract. CORE required: summary, implication, materiality, confidence, citations,
  processing_metadata, article_id, output_schema_version. Optional: sentiment, event_type, entities,
  extraction_quality, processing_notes.

## task-lifecycle-v1 (1.0) — 2026-08-14
- States + transitions + Definition-of-Done predicate + thresholds (spec-only).
