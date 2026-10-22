---
id: FACT-run-once-has-no-help-flag
type: fact
title: run_once.py has no help flag and starts a capture cycle
status: active
created: 2026-10-22
updated: 2026-10-22
verified: 2026-10-22
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - path:project/scripts/run_once.py
  - path:project/src/orchestrator.py
summary: "`python scripts/run_once.py --help` does not print help; it starts a real capture cycle, which only the capture lock stops while the daemon runs."
---

# FACT-run-once-has-no-help-flag — run_once.py has no help flag and starts a capture cycle

## Fact

- `project/scripts/run_once.py` passes its arguments to `src.orchestrator.main(["--once", ...])`, which has no argument parser, so `--help` is ignored and a scrape cycle starts against the real data root.
- On 2026-10-22 a `--help` sweep over every script hit it; the cycle exited 1 at once because `morninger` held the capture lock, so nothing was fetched.

## Why

- Run while the daemon is stopped, the same command scrapes every source and writes to `C:\data\news-scape\monocle.db`.

## How to Apply

- Never smoke-test CLIs by looping `--help` over `project/scripts`. Use `tests/repo/test_cli_entrypoints.py`, whose `AUTOMATION_CLIS` list holds only scripts with a real parser.
- Read a script's `__main__` block before running it with any flag.
