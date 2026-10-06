---
id: FACT-adr-0004-d4-applied-to-operational-db
type: fact
title: ADR-0004 D4 flag applied to the operational DB
status: active
created: 2026-10-06
updated: 2026-10-06
verified: 2026-10-06
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0004]
evidence:
  - commit:3b6003b
  - commit:31d539d
  - commit:4738f66
  - commit:39c9898
  - path:project/scripts/verify_gold_quality.py
  - path:C:/data/news-scape/archive/20261005-cleanup/db-backups/monocle_backup_260909_pre_a2.db
  - path:C:/data/news-scape/archive/20261005-cleanup/db-backups/monocle_backup_pre_adr0007_260917.db
  - metric:pre-A2 backup, agent_outputs 1,274 rows, 1,274 dod_pass=1, dod_reasons all empty
  - metric:C:/data/news-scape/monocle.db read-only 2026-10-06, 1,092 original ids kept, all dod_pass=0, output_json identical to the backup
  - metric:C:/data/news-scape/monocle.db read-only 2026-10-06, 182 original ids replaced 2026-09-10 by gold-financial-analyst reruns
summary: The verify_gold_quality.py --apply step of ADR-0004 D4 ran on 2026-09-09 and its dod_pass=0 flags persist in C:/data/news-scape/monocle.db; OPEN-ITEMS item A3 was stale.
---

# FACT-adr-0004-d4-applied-to-operational-db — ADR-0004 D4 flag applied to the operational DB

## Fact

- `verify_gold_quality.py --apply` only runs `UPDATE agent_outputs SET dod_pass=0, dod_reasons=<new gate failures>` per failing row; it deletes nothing and adds no column.
- It ran on 2026-09-09 on the operator machine, after the backup `monocle_backup_260909_pre_a2.db` (13:24) and before commit 3b6003b.
- The pre-A2 backup holds 1,274 `agent_outputs` rows, all `dod_pass=1`, all `dod_reasons` empty.
- Today's operational DB keeps 1,092 of those ids, all `dod_pass=0`, `output_json` unchanged, `dod_reasons` holding `value_added` and `implication_specific` failures.
- The other 182 ids were overwritten on 2026-09-10 by `gold-financial-analyst` reruns through `INSERT OR REPLACE`.
- The `l1_outputs.l1_source` column that OPEN-ITEMS item A3 warned about is absent in the pre-A2 backup and present by 2026-09-17.
- OPEN-ITEMS item A2 is correct. Item A3 came from the dev machine (commit 31d539d) and described a copy.

## Why

- The project ran on two machines from 2026-09-08 (commit 4738f66). The dev machine held a DB copy that never received the flag.
- `project/docs/operations/pipeline-backlog.html` measured that dev copy and reported `dod_pass=1`, which looks like a contradiction.
- An agent trusting A3 or that page could rerun `--apply` or "restore" flags on the wrong file.

## How to Apply

- Treat ADR-0004 D4 as applied on the DB lineage now at `C:/data/news-scape/monocle.db`.
- MUST NOT rerun `verify_gold_quality.py --apply` to fix a doc mismatch. Check the operational DB read-only first.
- When a doc reports DB state, it MUST name the DB file it measured, because dev copies and backups differ.
