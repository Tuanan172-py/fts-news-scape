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
verify: "python -m pytest tests/<file>.py -q"
summary: One sentence stating the user-visible outcome this story delivers.
---

# {{id}} — {{title}}

<!--
Contract: docs/knowledge/README.md. WIP=1: at most one story with status in_progress.
Status vocabulary: planned, in_progress, blocked, deferred, implemented, changed, retired.
`verify` is the single command that proves the story; harness_cli story complete runs it.
-->

## Contract

<!-- What the product or harness MUST do after this story, from the user's side. 20+ words. -->

## Acceptance Criteria

- [ ] <!-- measurable criterion 1 -->
- [ ] <!-- measurable criterion 2 -->

## Design Notes

<!-- Approach, touched modules, constraints from ADRs and rules (cite ids). -->

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | <!-- pytest path --> | <!-- pass/fail, count --> |
| Integration | | |
| Platform | | |

## Evidence

<!-- Commits, metrics, wave codes. Mirror them in frontmatter `evidence`. -->
