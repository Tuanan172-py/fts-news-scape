# Design 08 — Handoff Contract + Catalog (producer↔agent boundary)

Cập nhật: 2026-08-14 · Trạng thái: ĐÃ TRIỂN KHAI (producer) · Kèm: [07](07-storage-layers-and-change-detection.md), [09](09-agent-io-contract.md).

**Đây là ranh giới** để BẤT KỲ agent provider nào bắt tay xử lý từ raw. Producer sinh work-package +
đẩy vào catalog; consumer (agent) claim → done/failed. Phase-03.

## 1. Work-package = INPUT contract (schemas/work-package-v1.schema.json)
1 JSON tự mô tả / bài. **TRỎ** tới Bronze raw (không inline bytes) để agent re-verify offline.
```
{schema_version, article_id(=url_title_hash), source_url, domain, published_at,
 raw_html_path, raw_sha256,                # ★ agent verify sha256(read(raw_html_path))==raw_sha256
 cleaned_text, structure, images[], capture_status, change_state,
 provenance{fetch_ts, render_method, scraper_version, silver_schema_version}}
```
Required: schema_version, article_id, source_url, domain, raw_html_path, raw_sha256, cleaned_text,
capture_status, change_state. Ghi tại `data/work_packages/<domain>/<yyyymmdd>/<hash>.json` (atomic).
Provider-agnostic: pure JSON, không field vendor.

## 2. Catalog = `work_items` (SQLite, exactly-once)
Điều phối producer↔consumer, watermark trạng thái.
```
work_items(id, article_id, raw_sha256, domain, package_path,
           status, claimed_by, claimed_at, done_at, error, change_state, enqueued_at,
           UNIQUE(article_id, raw_sha256))
```
**Status watermark:** `pending → claimed → done | failed`; hoặc `held`.
- `enqueue` = INSERT OR IGNORE trên UNIQUE(article_id, raw_sha256) → **idempotent** (đẩy lại = no-op).
- `claim(worker_id)` = `BEGIN IMMEDIATE; UPDATE ... WHERE status='pending'` → **atomic, không double-claim**.
- `change_state ∈ {SELECTOR_BROKEN, TEMPLATE_DRIFT}` → enqueue thẳng `held` (không giao agent).
- package fail schema (validator) → `force_held=True` → `held` + log (không bao giờ giao package hỏng).

## 3. Exactly-once & incremental
- **Idempotency key** = (article_id, raw_sha256). Re-đọc cùng package không xử lý 2 lần.
- **Watermark**: `store.changed_since(iso)` → chỉ NEW/CONTENT_CHANGED thành pending; UNCHANGED bỏ qua.
- **Integrity**: agent (spec) BẮT BUỘC verify raw_sha256 trước khi xử lý (guardrail, doc 10).

## 4. Contract validator (dùng chung — DRY)
`src/handoff/contract_validator.py` (jsonschema, no exec). 1 validator, N schema (work-package-v1,
agent-output-v1, silver-v1). CLI: `python -m src.handoff.contract_validator <file.json> <schema-name>`.
Dùng ở producer gate (phase-06) NGAY khi build package: fail → held; và tái dùng cho agent output khi land.

## 5. Luồng
```
Silver + meta + article_versions.state
   → WorkPackageBuilder.build() → package.json (atomic, trỏ raw)
   → contract_validator(work-package-v1)  →PASS→ catalog.enqueue(pending)
                                           →FAIL→ catalog.enqueue(force_held) + log
consumer (agent bất kỳ):
   list_pending → claim(worker) → verify raw_sha256 → process → mark_done | mark_failed
```
Entry code: `src/pipeline/run.process_meta` (offline, idempotent). Scripts: `rederive_from_bronze.py`,
`report_drift.py`, `validate_e2e.py`.

## Versioning
Additive/optional only; bump `schema_version`; giữ đọc được bản cũ (BACKWARD_TRANSITIVE). Xem
[11](11-e2e-standardization-governance.md) + `schemas/CHANGELOG.md`.
