---
id: FACT-sqlite-correlated-range-index
type: fact
title: A correlated range on an indexed timestamp can pick the wrong SQLite index
status: active
created: 2026-11-19
updated: 2026-11-19
verified: 2026-11-19
lang: en
authors: [agent]
adr: []
evidence:
  - path:project/scripts/article_pack.py
  - path:project/scripts/maintenance/request_reanalysis.py
  - "metric: T4 selector over 2023-04-27..2026-11-11 took 594 s before and 9.9 s after, same 16 rows; request_reanalysis --status went from over 30 min to 2 s (2026-11-19)"
summary: In a correlated subquery that filters by id and by a timestamp range, SQLite chose the range index and scanned all newer rows per outer row; unary `+` on the non-key columns fixes the plan.
---

# FACT-sqlite-correlated-range-index — A correlated range on an indexed timestamp can pick the wrong SQLite index

## Fact

- `agent_outputs` has two indexes: `idx_agent_outputs_dod (dod_pass, created_at)` and `idx_agent_outputs_article_dod (article_id, dod_pass)`.
- For `EXISTS (SELECT 1 FROM agent_outputs g WHERE g.article_id = r.article_id AND g.dod_pass = 1 AND g.created_at >= r.requested_at)`, `EXPLAIN QUERY PLAN` showed `SEARCH g USING INDEX idx_agent_outputs_dod (dod_pass=? AND created_at>?)`.
- With that plan, each outer request row scans every passing output newer than the request, so the cost is roughly requests × outputs.
- Writing `+g.dod_pass = 1 AND +g.created_at >= r.requested_at` removes those columns from index selection, and the planner uses the article_id index.

## Why

- After US-054 opened 9,858 re-analysis requests, the T4 backlog selector in `article_pack.load_candidates` took 200–300 s at night and about 600 s in the day.
- The prepare step has a 5-minute deadline, so waves W11180700 and W11181913 failed on 2026-11-18. Two failures in a row demote the daemon from L1 to L0.
- The sensor uses the same selector, so it held the wave lock for over a minute and `/retry` was refused with "Sensor đang bận".

## How to Apply

- Run `EXPLAIN QUERY PLAN` on any correlated subquery that filters by an id and also by a range on an indexed column.
- If the plan searches the range index instead of the id index, prefix the non-key columns with unary `+`, then measure the time again.
- Queries with a literal `article_id = ?`, as in `ArticleStore._open_request_since`, did not show this problem.
