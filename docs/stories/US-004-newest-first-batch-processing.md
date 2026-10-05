# US-004: Newest-First Batch Task Processing (Block-by-Block 50-100 tasks)

## 1. Context & Goal
- **Problem**: Previously, `Catalog.claim()` ordered tasks by `enqueued_at ASC` (oldest first). Additionally, `l1_route.py` iterated through all historical files in ascending order without batch limiting, dumping 1,600+ tasks at once. This overwhelmed Subagents and prevented them from immediately analyzing the freshest financial news.
- **Goal**: Implement a block-by-block task processing mechanism:
  1. Priority given to newest items first (`enqueued_at DESC, id DESC`).
  2. Bounded batch size (configurable 20 - 100, default 50).
  3. L1 skips already completed articles (`status='done'`).
  4. Master orchestrator runner supports `--batch-size` and block execution.

## 2. Acceptance Criteria
- [ ] **AC-1 (Catalog Newest-First Order)**: `Catalog.claim(worker_id, order="desc")` and `Catalog.list_pending(limit, order="desc")` order by newest first (`enqueued_at DESC, id DESC`).
- [ ] **AC-2 (Agent Runner Export)**: `AgentRunner.export_tasks()` passes `order` to `Catalog.claim()`.
- [ ] **AC-3 (Agent Export CLI)**: `scripts/agent_export.py` defaults to batch size 50 and order `desc`.
- [ ] **AC-4 (L1 Route Ordering & Filter)**: `scripts/l1_route.py` scans newest files first (`reverse=True`), supports `--limit`, and skips articles with `status='done'` in `l1_tasks`.
- [ ] **AC-5 (Orchestrator Batch CLI)**: `scripts/run_agent_hierarchy.py` supports `--batch-size` and passes it to both export scripts.
- [ ] **AC-6 (Tests)**: All unit and regression tests pass (100% green).

## 3. Implementation Log
- Registered US-004 in `harness.db`.
