---
type: Reference
title: Kiến trúc Hệ thống (System Architecture)
description: Bản đồ 3 vòng medallion — capture Bronze, standardize Silver, Article Lane — kèm bất biến toàn hệ.
resource: project/docs/design/00-end-to-end-architecture.md
tags: [architecture, design, medallion, overview]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: e2e
    resource: project/docs/design/00-end-to-end-architecture.md
    title: End-to-end architecture (3 vòng)
  - id: execution-flow
    resource: project/docs/design/02-execution-flow.md
    title: Execution Flow
sources_last_checked: 2026-10-22
stale_after: 2026-12-31
---

# Triết lý

| Nguyên tắc | Diễn giải |
|---|---|
| **Medallion** | Bronze (raw WORM) → Silver (clean base) → Gold (agent output). Mỗi tầng 1 hợp đồng. |
| **Producer ↔ Consumer** | Codebase = producer (chụp raw, chuẩn hoá, đóng gói, nghiệm thu). Mô hình = consumer qua runner (DSH, agy, opencode, OpenRouter). Ranh giới = JSON Schema + DoD. |
| **WORM** | Raw HTML ghi 1 lần, byte-exact, không bao giờ sửa. `content_sha256` = bằng chứng bất biến. |
| **Re-derivable** | Mọi thứ dưới Bronze là hàm thuần của Bronze ⇒ sửa parser / bump schema **không cần re-scrape**. |
| **Tách hot path** | Capture (online, nhanh) tách khỏi standardize (offline). Scraper không ghi bảng downstream. |
| **Provider-agnostic** | Mô hình bị ràng buộc bởi hợp đồng, không khoá vendor. Lời gọi mô hình chỉ nằm trong `src/agent/runners/`; code không quyết định thực thể hay tóm tắt. |
| **Exactly-once** | Handoff idempotent (`UNIQUE(article_id, raw_sha256)`) + claim `BEGIN IMMEDIATE`. |

# Toàn cảnh 3 vòng

```
VÒNG 1 — CAPTURE (online, 10'/cycle dưới morninger)
  scrapers → CaptureMixin (robots → backoff → fetch)
           → RawStore.save (.html byte-exact + .meta.json)   ← BRONZE, WORM
           → extract/classify → DBWriter → articles + CSV

VÒNG 2 — STANDARDIZE (offline, re-derivable, 30')
  meta.json → SilverBuilder ─gate silver-v1→ fingerprint (SHA/SimHash/DOM)
            → change_detect (5 state) → article_versions
            → WorkPackageBuilder ─gate work-package-v1→ Catalog.enqueue
            → work_items = pending | held

═══════════ RANH GIỚI producer ↔ agent ═══════════

VÒNG 3 — ARTICLE LANE (đường duy nhất, ADR-0010)
  article_run.py → packet cả lô (chắt lọc, prefix tĩnh) → [MÔ HÌNH: DSH / agy / opencode / OpenRouter]
  → expand → l1_ingest + agent_ingest → validate schema + DoD
  → l1_outputs / agent_outputs (dod_pass)
  → write_user_output → <DATA_ROOT>/users/output/<user>/<YYYY-MM-DD>.xlsx
  → publish.py → SharePoint sandbox (ADR-0026.D1)
```

Chi tiết từng chặng: [Capture Orchestrator](../pipelines/ingestion_scheduler.md) ·
[Silver Derive](../pipelines/silver_derive.md) · [Article Lane](../pipelines/article_lane.md) ·
[User Output](../pipelines/user_output.md). Điều phối: [Morninger](../pipelines/morninger.md).

# Bản đồ artifact ↔ schema ↔ store

| Artifact | Hợp đồng | Nơi lưu | Owner | Bất biến |
|---|---|---|---|---|
| Bronze raw | meta 14 khoá | `<DATA_ROOT>/raw_html/**` | producer | **WORM** |
| Silver | `silver-v1` | `<DATA_ROOT>/silver/**` | producer | re-derive |
| Version log | DDL | [article_versions](../tables/article_versions.md) | producer | append-only |
| Work-package | `work-package-v1` | `<DATA_ROOT>/work_packages/**` | producer | re-derive |
| Catalog | DDL | [work_items](../tables/work_items.md) | shared | status mutable |
| Packet Article Lane | `{d, n, a[]}` (pack.py) | `<DATA_ROOT>/agent_tasks/article/**` | producer | ephemeral |
| Bản ghi gọn của mô hình | `article-compact-v2` | `<DATA_ROOT>/agent_outputs_article/**` | mô hình | bung bởi expand |
| Bản ghi nội dung | `agent-output-v2-lean` (đọc cả v1) | [agent_outputs](../tables/agent_outputs.md) | mô hình | append, DoD-gated |
| Bản ghi thực thể | `l1-entity-output-v1` | [l1_outputs](../tables/l1_outputs.md) | mô hình | append, DoD-gated |
| Deliverable | `.xlsx` (`DELIVERY_FIELDS`) | `<DATA_ROOT>/users/output/**` | producer | rewrite idempotent |

Hai khoá xuyên hệ: `article_id = url_title_hash` (định danh bài) và
`raw_sha256 = content_sha256` (provenance / change).

# Thành phần chính

| Thành phần | Module | Vai trò |
|---|---|---|
| Morninger | `src/morninger.py` | capture + Silver, 4 job |
| ops_daemon | `src/ops/runtime/daemon.py` | control plane không người trực (ADR-0012) |
| Orchestrator | `src/orchestrator.py` | Vòng 1 |
| HTTPClient | `src/crawler/http_client.py` | session dùng chung, rate limit, retry, UA rotation |
| RawStore | `src/crawler/raw_store.py` | Bronze WORM |
| Scrapers | `src/scrapers/**` | 8 scraper + mixin + REGISTRY |
| DedupCache | `src/db/dedup.py` | dedup 2 lớp |
| SilverBuilder / change_detect | `src/pipeline/**` | Vòng 2 |
| Catalog / WorkPackage / Validator | `src/handoff/**` | ranh giới handoff |
| Article Lane | `src/article_lane/**`, `src/ops/wave/article_run.py` | Vòng 3 |
| Runner / ingest / DoD | `src/agent/{runners,ingest,contract}/` | gọi mô hình, nghiệm thu |
| EntityRegistry | `src/agent/catalog/entities.py` | ontology + định tuyến |
| Publisher | `src/export/publisher.py` | publish một chiều lên SharePoint sandbox |
| UserOutputWriter | `src/export/user_output.py` | deliverable |
| DBWriter / ArticleStore | `src/db/**` | single-writer + SQLite WAL |

# 7 bất biến toàn hệ (checklist review)

1. Raw `.html` = bytes phản hồi; `sha256(file) == content_sha256`; không bao giờ sửa.
2. Silver / package / version là hàm thuần của Bronze — **không dùng `now()`**.
3. Package **trỏ** raw (`raw_sha256`), không inline bytes.
4. Mọi package phải PASS `contract_validator` mới `pending`; else `held`.
5. Ingest kiểm `raw_sha256` (preconditions) trước khi chấm; output qua DoD mới `done`.
6. Handoff exactly-once: idempotent enqueue + atomic claim.
7. Change-detection cần ≥2 capture/URL — `refresh_watchlist` cấp nguồn.

# Tài liệu liên quan

- [Codebase Guide](codebase.md) · [Agent Contracts](agent_contracts.md)
- [Runbook](../playbooks/runbook.md) · [Article Lane](../pipelines/article_lane.md)

[^e2e]: [End-to-end architecture](project/docs/design/00-end-to-end-architecture.md)
[^execution-flow]: [Execution Flow](project/docs/design/02-execution-flow.md)
