---
id: {{id}}
type: story
title: {{title}}
status: planned
lane: {{lane}}
created: {{date}}
updated: {{date}}
lang: en
authors: [{{author}}]
adr: []
plan: []
evidence: []
verify: "cd project && python -m pytest tests/<package>/test_<module>.py -q"
summary: One sentence stating the user-visible outcome this story delivers.
---

# {{id}} — {{title}}

<!--
Contract: docs/knowledge/README.md. WIP=1 per worktree (ADR-0022): at most one story with status
in_progress per branch, and an in_progress story MUST declare `branch:`.
Status vocabulary: planned, in_progress, blocked, deferred, implemented, changed, retired.
`verify` is the single command that proves the story; harness_cli story complete runs it.
-->

## Contract

<!-- What the product or harness MUST do after this story, from the user's side. 20+ words. -->

## Acceptance Criteria

- [ ] <!-- measurable criterion 1 -->
- [ ] <!-- measurable criterion 2 -->

## Design Notes

<!-- Approach, touched modules, constraints from ADRs and rules (cite ids). Code placement: RULE-12 (ADR-0027). -->

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | <!-- pytest path, tests/<package>/ (RULE-12.R7) --> | <!-- pass/fail, count --> |
| Integration | | |
| Platform | | |

## Evidence

<!-- Commits, metrics, wave codes. Mirror them in frontmatter `evidence`. -->
