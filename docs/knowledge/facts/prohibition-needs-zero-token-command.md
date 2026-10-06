---
id: FACT-prohibition-needs-zero-token-command
type: fact
title: A prohibition needs a zero-token command
status: active
created: 2026-09-21
updated: 2026-10-06
verified: 2026-09-21
lang: en
authors: [claude-opus-5-5]
adr: []
evidence:
  - "path: .agents/rules/08-context-and-zero-probe-guardrails.md"
  - "path: project/scripts/write_user_output.py"
summary: Forbidding agents to probe for something only works when a zero-token command answers that exact question; otherwise the rule is advice.
---

# FACT-prohibition-needs-zero-token-command — A prohibition needs a zero-token command

## Fact

- Rule 08 section 4 forbids contract archaeology by agents.
- Yet the 2026-09-21 trace spent six model steps finding that `users/output` lives at the repo root, not in `project/`.
- The steps were: reading source, grepping three files, trying a wrong path and two recursive listings.
- The fix was `scripts/write_user_output.py --where`; the normal run also prints the folder it wrote.

## Why

- The agent was not at fault. The rule said every contract has a command that prints it, but no command printed the delivery path.
- A rule that cannot be followed is not a rule.

## How to Apply

- Each time a prohibition is added to a rule or skill, check that a zero-token command answers the forbidden question.
- If no such command exists, write it before adding the prohibition.
