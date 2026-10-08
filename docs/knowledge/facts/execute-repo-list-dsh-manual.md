---
id: FACT-execute-repo-list-dsh-manual
type: fact
title: Execute repo work, list DSH manual steps
status: active
created: 2026-09-21
updated: 2026-10-06
verified: 2026-09-21
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: .agents/dsh/DSH-VIEC-THU-CONG.md"
  - "path: project/scripts/build_article_prefix.py"
  - "operator: 2026-09-21 on plan approval, do every repo change in session and list DSH manual steps"
summary: When the operator approves a plan, the agent executes every repo change in the session without asking per item and lists DSH manual steps in a separate document.
---

# FACT-execute-repo-list-dsh-manual — Execute repo work, list DSH manual steps

## Fact

- When the operator approves a plan, the default hand-off is fixed.
- The agent executes every change the repo allows within the session.
- It then writes a list of everything the operator must do by hand in DSH.
- It does not ask again per item and does not stop midway for confirmation.
- The list lives in `.agents/dsh/DSH-VIEC-THU-CONG.md` (created 2026-09-21 with 10 items, 4 mandatory).
- Its first item is copying `project/data/prefix/ARTICLE_SYSTEM_CORE.md` into the `persona` of row `tool-subagent-article`.
- `build_article_prefix.py --check` checks file against catalog and persona against file; `--check-preset` confirms right after pasting.

## Why

- The DSH runtime is out of reach of an agent session: mounted presets, global configuration, preset choice when opening a session and persona pasting.
- Without a written list these items fall into the gap between "fixed" and "nobody did it".
- The operator runs the workload on DSH, not inside the agent session, so verification there uses simulated output.

## How to Apply

- Mark each manual item as mandatory or optional and state the consequence of skipping it.
- For an item deliberately not fixed, state the reason and a recommendation. Example: `compaction auto: false` also affects the conductor, so the operator decides.
- Record items considered and rejected, with their numbers, so they are not proposed again.
