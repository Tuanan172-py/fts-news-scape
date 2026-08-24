# TEST_MATRIX.md — Evidence Vocabulary + Live Proof Table (H2-H5)

Golden rule: **"No proof = not implemented."** A claim without a mechanical result is a plan, not a fact.

> [!TIP]
> **H2-H5 Queryable Matrix:**
> Bắt đầu từ cấp độ H2, bảng trạng thái sống được lưu bền vững trong `harness.db` và có thể truy vấn thời gian thực bằng lệnh:
> ```powershell
> python scripts/harness_cli.py query matrix
> ```

## Status enum

| Status | Meaning |
|--------|---------|
| `planned` | Story exists, not started. |
| `in_progress` | Being worked (WIP=1 — only one at a time). |
| `implemented` | Reached ONLY via a real validation command that ran + is recorded. Never hand-flipped. |
| `changed` | Previously implemented, since modified (needs re-proof). |
| `retired` | Removed / superseded. |
| `blocked` | Halted on an external dependency / Hard Gate / ADR requirement. |
| `deferred` | Intentionally postponed with explicit reason. |

## Proof tiers

| Tier | For news-scape means |
|------|----------------------|
| **Unit** | Pure-function tests (parsers, dedup hash, sentiment rules) — `pytest tests/`. |
| **Integration** | Scraper → parse → dedup → store against captured fixtures. |
| **E2E** | A full cycle (`scripts/run_once.py <domain>`) or `verify_quality.py`. |
| **Platform** | Runtime/ops (scheduler, WAL, graceful shutdown, health check). |

A tier is `1` (passed, evidence recorded), `0` (not passed/not run), or `—` (N/A for this story).

## Live Proof Table (Snapshot H2)

| Story | Parent/Epic | Status | Unit | Integ | E2E | Platform | Evidence |
|-------|-------------|--------|:----:|:-----:|:---:|:--------:|----------|
| [US-001](stories/US-001-gold-agent-output-contract.md) | Phase 3 — Gold / agent-extract | `planned` | 0 | — | — | — | Hard gate (blocked on contract decision + ADR) |
| [US-002](stories/US-002-optimize-user-output-format.md) | Per-User Output Workflow | `implemented` | 1 | 1 | — | — | Pytest 13/13 passed + real run 60 rows generated |

> Rule reminder: Stories reach `implemented` ONLY after validation commands run and results are recorded. Never hand-flip.

