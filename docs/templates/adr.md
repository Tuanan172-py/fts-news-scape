---
id: {{id}}
type: adr
title: {{title}}
status: proposed
lane: {{lane}}
created: {{date}}
updated: {{date}}
lang: en
authors: [{{author}}]
approvers: []
story: []
supersedes: []
amends: []
evidence: []
summary: One sentence, at most 40 words, that lets an agent decide whether to open this ADR.
summary_vi: Một câu tiếng Việt cho người duyệt.
---

# {{id}} — {{title}}

<!--
Contract: docs/knowledge/README.md. Lint: python scripts/harness_cli.py doc lint.
- Keep the six H2 sections below, in this order. Do not rename them.
- Open each section with short bullets, one checkable claim per bullet; prose after.
- Every number or measured claim needs a matching `evidence` entry (commit:, path:, metric:, test:, wave:).
- The body is frozen once status is accepted. Later changes go in a new ADR that lists this id in
  `amends` or `supersedes`; only frontmatter (status, approvers, updated) may change here.
- Delete these comments before requesting approval.
-->

## Context

<!-- Forces, problem and risk that made a decision necessary. Measurements with evidence. 60+ words. -->

## Decision

<!-- The chosen option, stated directly. One numbered sub-decision per item, each citable as {{id}}.D1, D2... Use MUST / MUST NOT / SHOULD (RFC 2119). 40+ words. -->

## Alternatives

| Option | Why rejected |
|---|---|
| <!-- option A --> | <!-- concrete reason with evidence --> |
| <!-- option B --> | <!-- concrete reason with evidence --> |

## Consequences

<!-- Gains (measurable) and costs or risks accepted, with mitigation. 30+ words. -->

## Rollback

<!-- How to return the system to the state before this decision, and who may do it. 15+ words. -->

## Follow-up

- [ ] <!-- concrete action: backlog item, doc update, re-verification -->
