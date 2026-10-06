---
id: ADR-0021
type: adr
title: Agent-first knowledge framework, model-agnostic
status: accepted
lane: high-risk
created: 2026-10-06
updated: 2026-10-06
lang: en
authors: [claude-opus-5-5]
approvers: [operator 2026-10-06]
story: [US-039]
amends: [ADR-0001, ADR-0002]
evidence:
  - path:docs/templates/adr.md
  - path:project/scripts/doc_lint.py
  - path:scripts/schema/001-init.sql
  - metric:4 of 19 ADRs follow the template (0016-0019), audit 2026-10-06
  - metric:38 stories in harness.db, 19 story files, audit 2026-10-06
  - metric:20 Claude-only memory files outside the repo, audit 2026-10-06
  - operator:Q1-Q4 answered 2026-10-06 (English, one-time normalization, docs/knowledge/facts, harness.db derived)
summary: One frontmatter contract, one language (English), one id allocator and one lint gate for every knowledge document, so any model writes ADRs, stories, plans and facts the same way.
summary_vi: Một hợp đồng tài liệu, một ngôn ngữ (tiếng Anh), một bộ cấp mã và một cổng lint cho mọi agent viết ADR, story, plan và fact.
---

# ADR-0021 — Agent-first knowledge framework, model-agnostic

## Context

- The operator works with Claude Code, Codex, agy, opencode and OpenRouter models. Templates and rules exist, yet agent-written documents are fragmented, mix languages and are often thin.
- Only 4 of 19 ADRs followed the decision template (0016 to 0019). ADR-0001 has 21 lines and ADR-0002 has 23 lines; both lack alternatives and rollback.
- Seven ADRs were partly replaced by later ADRs while their status line still says accepted: 0003, 0004, 0005, 0006, 0009, 0010, 0011.
- The template forbade editing accepted ADRs, yet 0008, 0012 and 0017 were edited in place. Number 0015 was reserved in a plan and never written.
- `harness.db` holds 38 stories but only 19 have files. US-036 names four different scopes and US-035 names two. Four stories were `in_progress` at once against WIP=1.
- None of the 10 proposals follows the proposal template, and three proposals ended without a verdict. Plans live in four places, two of them private to one tool.
- No language policy exists. The story template was English, four other templates Vietnamese, and the technical-writing skill demands "Global English".
- `AGENTS.md` is the only entrypoint. Nine of twelve rules carry an agy-only `trigger` block. Twenty Claude memory files hold safety facts other agents cannot read, such as "pytest writes to the real DB".
- `doc_lint.py` runs only inside pytest, checks ADRs from 0015 on and a few runbooks, and was red at audit time.

The root cause is that templates are prose suggestions. No machine-readable field, no id allocator and no blocking check exists, so each model fills them by habit. The harness already solved the same problem for model output in ADR-0017: one schema, one validator, one gate for every provider. This ADR applies that pattern to knowledge documents.

## Decision

- D1. Markdown files with YAML frontmatter in the repository are the single source of truth for project knowledge. The `harness.db` tables `story` and `decision` are derived by `harness_cli.py doc sync`; `trace`, `intake` and `agent_metrics` stay runtime data.
- D2. Eight governed types exist: adr, story, proposal, plan, fact, rule, run, runbook. Ids, paths, statuses, required keys, required sections and content floors are defined only in `docs/knowledge/schema.yaml`.
- D3. Every governed document MUST carry the frontmatter of its template, including a one-sentence `summary`. Agents read `docs/INDEX.md` and frontmatter first and open bodies only when needed.
- D4. English is the language of every harness document (`lang: en`). Vietnamese is allowed in quotes, blockquotes, code and `summary_vi`. Operator runbooks MAY use Vietnamese. Delivered user output is out of scope.
- D5. Bodies are written for agents: fixed H2 sections in fixed order, bullets first, RFC 2119 keywords, numbered decisions and rules citable as `ADR-NNNN.Dn`. Each invariant has exactly one defining document; others cite it.
- D6. The body of an accepted ADR is frozen; frontmatter stays editable. Changes go in a new ADR via `supersedes` or `amends`. A one-time exception under US-039 normalizes ADR-0001 to ADR-0020: decision meaning is kept, while missing context, alternatives, rollback and evidence are reconstructed from commits, plans and proposals. Each normalized file records `original` and `reconstructed`.
- D7. Ids are allocated only by `harness_cli.py doc new`, which scans the working tree, every git branch and `harness.db`.
- D8. Project memory lives in `docs/knowledge/facts/` as `FACT-*` files. Tool-private memory is scratch. Plans live only in `plans/`.
- D9. `AGENTS.md` stays the canonical entrypoint. One-line redirect files (`CLAUDE.md`, `GEMINI.md`) point every tool to it.
- D10. `harness_cli.py doc lint` is the gate. It runs in the pre-commit hook on staged files, in pytest and in `harness_cli.py audit`. Files created before this ADR are listed in `docs/knowledge/legacy.txt`, which only shrinks.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep prose templates and remind agents to follow them | Tried since 2026-08-18; 15 of 19 ADRs drifted. Without a gate each model falls back to its own habit. |
| Add more rules to `AGENTS.md` | `AGENTS.md` already restates rules from `.agents/rules/`, and the copies drifted (H1 versus H5, closure emoji, ADR commit format). More text adds drift, not compliance. |
| Make `harness.db` the source of truth | The database is gitignored and exists on one machine. An agent on another checkout sees nothing; files are visible to every tool. |
| Keep Vietnamese for all documents | Lower migration cost, but more tokens per idea on most tokenizers and no standard meaning for normative keywords. Rejected by the operator at Q1. |
| Bilingual documents | Doubles length and the two halves drift apart, which is the mixing this ADR ends. |
| Rewrite thin ADRs from model memory | Fabricates history. Every reconstructed part MUST cite a commit, plan, proposal or measurement. |

## Consequences

Gains:

- One document contract for every model; schema drift is blocked at commit time whichever model wrote the file.
- Agents load the index and frontmatter first, which keeps context small, in line with the zero-probe rule.
- Id collisions such as the two ADR-0018 drafts or the US-035 and US-036 reuse become impossible through the allocator.
- Safety facts currently locked in Claude memory become shared project memory.

Costs accepted:

- Migration effort: about 19 ADRs, 19 stories, 10 proposals, 22 plans, 12 rules and 20 memories. Phased in the follow-up list and tracked by `legacy.txt`.
- The operator reads harness documents in English; `summary_vi` keeps a Vietnamese line for approval.
- Stricter lint slows document commits; `doc new` scaffolds the structure to compensate.

## Rollback

- Each phase is a separate commit on `feature/us039-knowledge-framework`; `git revert` restores the previous state per phase.
- Original texts of normalized documents stay in git history; each normalized file records `original: commit:<hash>`.
- Enforcement is disabled by removing the `doc lint --staged` step from `scripts/git_hooks/pre-commit`.
- Only the operator may order a full rollback.

## Follow-up

- [x] G1 Contract: `schema.yaml`, English templates, `scripts/knowledge.py`, `harness_cli.py doc new|lint|index|sync`, pre-commit step, tests.
- [ ] G2 Entrypoints: slim `AGENTS.md`, add `CLAUDE.md` and `GEMINI.md` redirects, frontmatter for the twelve rules, generate `docs/INDEX.md`.
- [ ] G3 ADRs: normalize ADR-0001 to ADR-0020 with commit evidence; add ADR-0015 as rejected (absorbed by ADR-0013); fold TDR-001 to TDR-006 in as superseded records.
- [ ] G4 Stories and proposals: resolve the US-035 and US-036 collisions, write files for database-only stories, move wave checkpoints to type run, give orphan proposals a verdict.
- [ ] G5 Memory and handoff: migrate the twenty Claude memories to `FACT-*`, move tool-private plans into `plans/`, split `SESSION-LATEST.md` by lane.
- [ ] G6 Drift cleanup: harness maturity H1 versus H5, closure-table emoji, ADR commit format, stale `monocle.db` paths, Gold rule 05 still always-on.
