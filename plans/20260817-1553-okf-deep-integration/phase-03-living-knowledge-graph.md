# GĐ3 — Living Knowledge Graph (2–6 tháng) [FAR-FUTURE]

> **CẢNH BÁO GIẢ ĐỊNH:** Phase này phụ thuộc harness đã leo H2+ (TRACE_SPEC, self-improvement H5) + GĐ2 stable. Nhiều mục là *far-future assumption*, đánh dấu rõ. KHÔNG bắt đầu tới khi GĐ2 KPI đạt. GCP seam để mở, KHÔNG build.

## Context links
- [plan.md](plan.md) · [phase-02](phase-02-semi-automation.md)
- Harness deps: H2 TRACE_SPEC, H5 self-improvement backlog (`docs/HARNESS_BACKLOG.md`).

## Overview
- **Ngày:** 2026-08-17 | **Priority:** P2 (deferred)
- **Mô tả:** OKF thành KB truy vấn được, tự cải thiện: JSON-LD export, observability, suggestion engine, codegen mở rộng, local export adapter.
- **Impl-status:** Not started | **Review-status:** Pending

## Key Insights
- GĐ2 đã có `graph.py` (networkx) + pydantic model → nền cho JSON-LD/RDF export.
- Frontmatter tối giản, không registry type trung tâm → cần chuẩn hoá nhẹ trước khi map sang RDF predicate.
- Observability phải **depend, don't build** harness TRACE_SPEC (agent_outputs.processing_metadata) — OKF chỉ thêm chiều "OKF file read/updated per trace".
- Suggestion engine tie vào `docs/HARNESS_BACKLOG.md` (friction reservoir) — human-approved, không tự-ghi OKF.

## Requirements
- R1: `okf export --jsonld` (rdflib/pyld) → truy vấn ("domain có rate_limit>5s").
- R2: Observability: log OKF file read/updated theo agent trace (ranh giới harness H2).
- R3: Suggestion engine từ friction backlog (human-approved, gắn harness H5).
- R4: Mở rộng codegen: migration schema / API docs / test fixtures từ OKF.
- R5: Local export adapter JSON/CSV; **GCP seam để mở, KHÔNG build**.

## Architecture
```
okftools/
  export.py     # jsonld (pyld/rdflib), csv, json ; abstract Exporter(seam GCP)
  observe.py    # đọc harness trace (read-only) → gắn OKF-read events ; depend TRACE_SPEC
  suggest.py    # đọc HARNESS_BACKLOG.md → đề xuất OKF update (human-approved)
  codegen.py    # OKF concept → migration SQL / API md / pytest fixture
context/
  okf.context.jsonld   # NEW: JSON-LD @context (map frontmatter→predicate)
```
- **Exporter seam:** `class Exporter(ABC)` với `LocalJSONExporter`, `LocalCSVExporter`; `GCPExporter` = stub `NotImplementedError` (seam only, YAGNI).
- **JSON-LD:** map `type`→rdf:type, `sources`→prov:wasDerivedFrom, `rate_limit`→ex:rateLimit. Query qua SPARQL (rdflib) hoặc JSON path.
- **Codegen (R4):** vd `tables/new_table.md` → `CREATE TABLE` migration; `configurations/*` → API doc; concept → pytest fixture JSON. Append-only, human-review trước merge.

## Related code files (real paths)
- `okftools/{export,observe,suggest,codegen}.py` (NEW)
- `context/okf.context.jsonld` (NEW)
- harness `docs/HARNESS_BACKLOG.md` (đọc, đề xuất) · harness TRACE_SPEC (agent_outputs table)
- `project/src/db/store.py` (đích codegen migration — human review)
- `project/schemas/*.schema.json` (nguồn/đích codegen fixtures)
- `okf/catalog/**` (nguồn tri thức)

## Implementation Steps
1. **Chuẩn hoá frontmatter:** đảm bảo type/tags/sources đủ cho map RDF; viết `context/okf.context.jsonld`.
2. **`export.py --jsonld`:** networkx→rdflib graph→JSON-LD. Thêm CSV/JSON. Định nghĩa `Exporter` ABC + GCP stub (seam).
3. **Query demo:** SPARQL/JSON "domains rate_limit>5s", "concepts sources chứa store.py".
4. **`observe.py` (R2):** nếu harness H2 sẵn → đọc trace read-only, annotate OKF-read events. Nếu chưa → skip (degrade).
5. **`suggest.py` (R3):** parse `HARNESS_BACKLOG.md` → sinh đề xuất OKF update (diff-preview), **human-approve** mới ghi (giữ permission rule).
6. **`codegen.py` (R4):** migration/API/fixtures generators, mỗi cái append-only + human-review gate.
7. **Tests + docs:** cập nhật `okf/MAPPING.md`, `okf/log.md`.

## Todo list
- [ ] Chuẩn hoá frontmatter cho RDF
- [ ] okf.context.jsonld
- [ ] export.py jsonld/csv/json + Exporter seam (+GCP stub)
- [ ] Query demo (rate_limit>5s)
- [ ] observe.py (depend harness TRACE_SPEC; degrade nếu H1)
- [ ] suggest.py (human-approved)
- [ ] codegen.py (migration/API/fixtures)
- [ ] Tests + cập nhật MAPPING/log

## Success Criteria (KPI/DoD)
- **KPI:** 90% thay đổi dùng OKF để gen config/migration; **-90% thời gian update KB**.
- **DoD:** (a) `okf export --jsonld` chạy + ≥1 query mẫu trả đúng; (b) observability không phá harness (read-only); (c) suggestion 100% human-approved trước ghi; (d) codegen output human-review; (e) GCP = stub, không dependency GCP thật.

## Risk Assessment
- **[FAR-FUTURE]** harness chưa H2 → observability/suggestion không chạy → degrade gracefully, skip, không block export/codegen.
- JSON-LD over-engineering (YAGNI) → chỉ làm khi có nhu cầu query thực; nếu không, dừng ở JSON export.
- Codegen sinh migration sai phá DB → human-review bắt buộc, không auto-apply.
- Suggestion engine tự-ghi vô kiểm soát → hard gate human-approve (permission rule plan.md).

## Security Considerations
- Export KHÔNG lộ secret (loại field nhạy cảm khỏi JSON-LD/CSV).
- Suggestion/codegen không auto-commit; mọi ghi OKF có `generated:{by,at}` truy vết.
- GCP seam stub: đảm bảo không có credential/endpoint GCP hard-code.

## Next steps
- Đánh giá lại nhu cầu GCP (nếu có) → implement `GCPExporter` sau, ngoài phạm vi hiện tại.
- Feedback loop: KPI GĐ3 → điều chỉnh charter OKF + harness H5 backlog.
