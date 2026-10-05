---
type: Reference
title: Kiến trúc Hệ thống (System Architecture)
description: Bản đồ 3 vòng medallion — capture Bronze, standardize Silver, handoff agent Gold — kèm bất biến toàn hệ.
resource: project/docs/design/00-end-to-end-architecture.md
tags: [architecture, design, medallion, overview]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: e2e
    resource: project/docs/design/00-end-to-end-architecture.md
    title: End-to-end architecture (3 vòng)
  - id: system-overview
    resource: project/docs/design/01-system-overview.md
    title: System Overview
  - id: execution-flow
    resource: project/docs/design/02-execution-flow.md
    title: Execution Flow
  - id: governance
    resource: project/docs/design/11-e2e-standardization-governance.md
    title: E2E standardization governance
sources_last_checked: 2026-09-07
stale_after: 2026-12-31
---

# Triết lý

| Nguyên tắc | Diễn giải |
|---|---|
| **Medallion** | Bronze (raw WORM) → Silver (clean base) → Gold (agent output). Mỗi tầng 1 hợp đồng. |
| **Producer ↔ Consumer** | Codebase = producer (chụp raw, chuẩn hoá, đóng gói, nghiệm thu). Agent = consumer (provider bất kỳ). Ranh giới = JSON Schema + DoD. |
| **WORM** | Raw HTML ghi 1 lần, byte-exact, không bao giờ sửa. `content_sha256` = bằng chứng bất biến. |
| **Re-derivable** | Mọi thứ dưới Bronze là hàm thuần của Bronze ⇒ sửa parser / bump schema **không cần re-scrape**. |
| **Tách hot path** | Capture (online, nhanh) tách khỏi standardize (offline). Scraper không ghi bảng downstream. |
| **Provider-agnostic** | Agent bị ràng buộc bởi hợp đồng, không khoá vendor. Repo **không chứa lời gọi LLM**. |
| **Exactly-once** | Handoff idempotent (`UNIQUE(article_id, raw_sha256)`) + claim `BEGIN IMMEDIATE`. |

# Toàn cảnh 3 vòng

```
VÒNG 1 — CAPTURE (online, 15'/cycle)
  scrapers → CaptureMixin (robots → backoff → fetch)
           → RawStore.save (.html byte-exact + .meta.json)   ← BRONZE, WORM
           → extract/classify → DBWriter → articles + CSV

VÒNG 2 — STANDARDIZE (offline, re-derivable, 30')
  meta.json → SilverBuilder ─gate silver-v1→ fingerprint (SHA/SimHash/DOM)
            → change_detect (5 state) → article_versions
            → WorkPackageBuilder ─gate work-package-v1→ Catalog.enqueue
            → work_items = pending | held

═══════════ RANH GIỚI producer ↔ agent ═══════════

VÒNG 3 — AGENT HANDOFF (Gold, 2 lớp nghiệp vụ)
  agent_export / l1_route → task packet (đã prune) → [AGENT NGOÀI]
  → agent_ingest / l1_ingest → validate schema + DoD
  → l1_outputs / agent_outputs (dod_pass)
  → run_user_workflow → users/output/<user>/<date>.csv
```

Chi tiết từng chặng: [Capture Orchestrator](../pipelines/ingestion_scheduler.md) ·
[Silver Derive](../pipelines/silver_derive.md) · [Agent Handoff](../pipelines/agent_handoff.md) ·
[User Output](../pipelines/user_output.md). Điều phối: [Morninger](../pipelines/morninger.md).

# Bản đồ artifact ↔ schema ↔ store

| Artifact | Hợp đồng | Nơi lưu | Owner | Bất biến |
|---|---|---|---|---|
| Bronze raw | meta 14 khoá | `data/raw_html/**` | producer | **WORM** |
| Silver | `silver-v1` | `data/silver/**` | producer | re-derive |
| Version log | DDL | [article_versions](../tables/article_versions.md) | producer | append-only |
| Work-package | `work-package-v1` | `data/work_packages/**` | producer | re-derive |
| Catalog | DDL | [work_items](../tables/work_items.md) | shared | status mutable |
| Task packet | packet 1.0 | `data/agent_tasks/**` | producer | ephemeral |
| Agent output | `agent-output-v1` | [agent_outputs](../tables/agent_outputs.md) | agent | append, DoD-gated |
| L1 output | `l1-entity-output-v1` | [l1_outputs](../tables/l1_outputs.md) | agent | append, DoD-gated |
| Deliverable | 15 cột CSV | `users/output/**` | producer | rewrite idempotent |

Hai khoá xuyên hệ: `article_id = url_title_hash` (định danh bài) và
`raw_sha256 = content_sha256` (provenance / change).

# Thành phần chính

| Thành phần | Module | Vai trò |
|---|---|---|
| Morninger | `src/morninger.py` | entrypoint prod, 3 job |
| Orchestrator | `src/orchestrator.py` | Vòng 1 |
| HTTPClient | `src/crawler/http_client.py` | session dùng chung, rate limit, retry, UA rotation |
| RawStore | `src/crawler/raw_store.py` | Bronze WORM |
| Scrapers | `src/scrapers/**` | 9 module + REGISTRY |
| DedupCache | `src/db/dedup.py` | dedup 2 lớp |
| SilverBuilder / change_detect | `src/pipeline/**` | Vòng 2 |
| Catalog / WorkPackage / Validator | `src/handoff/**` | ranh giới handoff |
| AgentRunner / L1Runner / DoD | `src/agent/**` | Vòng 3 (không LLM) |
| EntityRegistry | `src/agent/entities.py` | ontology + định tuyến |
| UserOutputWriter | `src/export/user_output.py` | deliverable |
| DBWriter / ArticleStore | `src/db/**` | single-writer + SQLite WAL |

# 7 bất biến toàn hệ (checklist review)

1. Raw `.html` = bytes phản hồi; `sha256(file) == content_sha256`; không bao giờ sửa.
2. Silver / package / version là hàm thuần của Bronze — **không dùng `now()`**.
3. Package **trỏ** raw (`raw_sha256`), không inline bytes.
4. Mọi package phải PASS `contract_validator` mới `pending`; else `held`.
5. Agent verify `raw_sha256` trước khi xử lý; output qua DoD mới `done`.
6. Handoff exactly-once: idempotent enqueue + atomic claim.
7. Change-detection cần ≥2 capture/URL — `refresh_watchlist` cấp nguồn.

# Tài liệu liên quan

- [Codebase Guide](codebase.md) · [Agent Contracts](agent_contracts.md)
- [Runbook](../playbooks/runbook.md) · [Daily Agent Run](../playbooks/daily_agent_run.md)

[^e2e]: [End-to-end architecture](project/docs/design/00-end-to-end-architecture.md)
[^system-overview]: [System Overview](project/docs/design/01-system-overview.md)
[^execution-flow]: [Execution Flow](project/docs/design/02-execution-flow.md)
[^governance]: [E2E governance](project/docs/design/11-e2e-standardization-governance.md)
