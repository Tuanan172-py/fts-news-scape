# Design 11 — End-to-End Standardization Governance (MASTER)

Cập nhật: 2026-08-14 · Trạng thái: ĐÃ TRIỂN KHAI (producer) + SPEC (agent) · **Điểm vào duy nhất** cho toàn quy trình.

Bản đồ chuẩn hoá 2 đầu: **codebase = producer raw**, **agent = consumer** (provider bất kỳ). Liên kết
docs 06–10 (không lặp lại nội dung). Phase-06.

## 1. Toàn cảnh end-to-end
```
[Scrape] cafef/vietstock (doc 06)
   → BRONZE raw .html+.meta.json  (WORM, byte-exact)
        → SILVER clean base .json           (doc 07, deterministic từ Bronze)
        → article_versions (change-log)     (doc 07: NEW/UNCHANGED/CONTENT_CHANGED/TEMPLATE_DRIFT/SELECTOR_BROKEN)
        → WORK-PACKAGE .json                 (doc 08, trỏ raw, provider-agnostic)
        → [contract_validator gate] ──PASS──► catalog work_items = pending
                                    └─FAIL──► held + log
────────────────────────── RANH GIỚI PRODUCER↔AGENT ──────────────────────────
   INPUT = work-package-v1 (doc 09)
        → [AGENT bất kỳ provider] Router→Extractor→Analyst→Verifier→Aggregator (doc 10)
        → OUTPUT = agent-output-v1  → [contract_validator] + DoD → catalog.mark_done
schema bump: bump version → rederive_from_bronze (Silver+package) → re-validate → re-enqueue  (KHÔNG re-scrape)
```

## 2. Layer ↔ Contract ↔ Owner
| Layer/Artifact | Schema | Store | Owner | Bất biến |
|----------------|--------|-------|-------|----------|
| Bronze raw | (doc 06 meta 14 keys) | `data/raw_html/**` | producer | WORM |
| Silver | `silver-v1` | `data/silver/**` | producer | re-derive |
| Version log | — (DDL) | `article_versions` | producer | append-only |
| Work-package | `work-package-v1` | `data/work_packages/**` | producer | re-derive |
| Catalog | — (DDL) | `work_items` | shared | mutable status |
| Agent output | `agent-output-v1` | (future `agent_outputs`) | agent | append |
| Lifecycle/DoD | `task-lifecycle-v1` | — | agent | spec |

## 3. Catalog status ↔ lifecycle state (không state mồ côi)
| work_items.status | lifecycle |
|-------------------|-----------|
| pending | (chưa claim) |
| claimed | STARTED / EXTRACTION_PENDING / VERIFICATION_PENDING / FAILED_RECOVERABLE |
| done | COMPLETE |
| failed | FAILED_PERMANENT |
| held | (precondition fail: broken/drift/schema-invalid) |

## 4. Hard validation gate (phase-06)
Mọi package build ra → `contract_validator(work-package-v1)`. PASS ⇒ enqueue `pending`; FAIL ⇒ `held` +
log (không bao giờ giao agent package hỏng). Cùng validator tái dùng cho agent OUTPUT (DoD, doc 10).

## 5. Versioning / migration policy
- Additive/optional only; bump `*_schema_version`; giữ ≥2 version đọc được (BACKWARD_TRANSITIVE).
- Raw = WORM source of truth ⇒ **schema bump KHÔNG cần re-scrape**: `scripts/rederive_from_bronze.py`
  regenerate Silver+packages (idempotent, offline), re-validate, re-enqueue changed.
- Change log: `schemas/CHANGELOG.md`.

## 6. Vận hành
**Driver chính (prod): `python -m src.morninger`** — scheduler 3 job: capture (15') →
`derive.rederive_incremental` (30', watermark tăng dần) → `drift.list_drift` (mỗi sáng).
1 scheduler tại 1 thời điểm (advisory lock `pipeline_state`).

| Script (bổ trợ) | Việc |
|-----------------|------|
| `rederive_from_bronze.py [domain] [date]` | **full-scan re-derive** (BẢO TRÌ: sau bump schema/sửa parser), không phải driver ngày |
| `refresh_watchlist.py [limit] [domain]` | re-fetch watch-list → kích hoạt change-detection |
| `report_drift.py` | liệt kê TEMPLATE_DRIFT/SELECTOR_BROKEN để reconcile |
| `validate_e2e.py` | smoke test toàn chuỗi OFFLINE + validate agent-output sample (PASS/FAIL) |

## 7. Bằng chứng
`validate_e2e.py` → PASS toàn chuỗi (silver→version=NEW→package schema-valid→enqueue pending→claim→
mark_done→agent-output sample valid). Tests: `test_change_detect.py`, `test_handoff.py` (20 passed).

## 8. Điểm chạm "đã thực sự hoàn thành" (tổng hợp)
- **Producer**: package PASS validator + enqueue `pending` (hoặc `held` nếu hỏng — có log).
- **Agent**: DoD (schema-valid ∧ confidence≥0.65 ∧ ≥2 citations grounded ∧ quality∈{high,medium} ∧
  audit) ⇒ `catalog.mark_done`. Không đạt ⇒ `failed`/`held`.

## Next (khi lớp agent land)
Reuse OUTPUT validator + DoD predicate làm acceptance gate; thêm bảng `agent_outputs`; adapter mỗi provider.
GOLD layer chỉ mở khi cần dataset curated riêng (hiện agent output = gold; YAGNI).
