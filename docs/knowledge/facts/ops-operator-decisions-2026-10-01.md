---
id: FACT-ops-operator-decisions-2026-10-01
type: fact
title: Operator decisions for ops_daemon on 2026-10-01
status: active
created: 2026-10-01
updated: 2026-10-06
verified: 2026-10-01
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0012]
evidence:
  - "path: docs/proposals/20261001-ops-council.md"
  - "operator: 2026-10-01 decisions D1' and D8 to D13 after the ops council"
summary: The operator chose Telegram, full article text to every provider, running only while the machine is on, no per-wave approval, and per-user delivery separate from waves.
---

# FACT-ops-operator-decisions-2026-10-01 — Operator decisions for ops_daemon on 2026-10-01

## Fact

Decisions of 2026-10-01 after the council in `docs/proposals/20261001-ops-council.md` section 9:

- Telegram (BotFather) is the main channel.
- Full cleaned article text (packet with `i/t/p` only) goes to every provider. Articles are public, with no copyright issue.
- Internal data (logs, watchlist, secrets) MUST NOT travel in the payload.
- Not 24/7: the system runs only while the machine is on and pauses when it closes. No auto-logon, no sleep blocking, and healthchecks MUST NOT turn red while the machine sleeps.
- Machine on and conditions met (100 articles, age, time window): the agent runs the whole workflow with no per-wave approval button, matching the ADR 0008 amendment.
- The DB is the single source of truth. Delivery (which articles, how many, how often) is per-user configuration, separate from the wave workflow.
- D12 (keep old versions, redeliver with versions) and D13 (a clean wave has quality criteria) are agreed.

## Why

- The operator wants an end-to-end framework that runs itself. People steer through standing orders and pause, not by pressing approve.

## How to Apply

- MUST NOT propose a per-wave approval gate or a 24/7 requirement again.
- Sleep in the middle of a wave is a normal case, so recovery (Job Object, reconcile) is mandatory.
- See FACT-ops-daemon-scheduler-pitfalls and FACT-tokens-recorded-not-gated.
