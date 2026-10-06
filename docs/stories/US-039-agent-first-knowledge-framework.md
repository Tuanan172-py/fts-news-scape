---
id: US-039
type: story
title: Agent-first knowledge framework
status: in_progress
branch: feature/us039-knowledge-framework
lane: high-risk
created: 2026-10-06
updated: 2026-10-06
lang: en
authors: [claude-opus-5-5]
adr: [ADR-0021]
plan: []
evidence: [path:docs/knowledge/schema.yaml, path:scripts/knowledge.py, test:tests/test_knowledge.py]
verify: "python -m pytest tests/test_knowledge.py tests/test_harness_cli.py -q"
summary: Every agent writes ADRs, stories, proposals, plans and facts through one English frontmatter contract with an id allocator and a blocking lint, and thin historical ADRs are rebuilt from commit evidence.
---

# US-039 — Agent-first knowledge framework

## Contract

After this story, any agent (Claude, Codex, agy, opencode, an OpenRouter model) that creates or edits a governed knowledge document gets the same structure, language and id discipline. A document that breaks the contract cannot be committed. Historical ADRs carry reconstructed context, alternatives and rollback with commit evidence.

## Acceptance Criteria

- [x] `docs/knowledge/schema.yaml` defines eight types; `harness_cli.py doc new|lint|index|sync` exist and are tested.
- [x] `doc new` never reuses an id present on disk, on any git branch or in `harness.db`.
- [x] The pre-commit hook rejects a staged governed document that fails `doc lint`.
- [x] ADR-0001 to ADR-0019 pass `doc lint` with `original` and `reconstructed` recorded, ADR-0015 exists as rejected. ADR-0020 waits for US-038, which owns it.
- [ ] `docs/knowledge/legacy.txt` is empty or every remaining entry has a phase owner in ADR-0021 follow-up.
- [x] Twenty Claude memory files exist as `FACT-*` documents.
- [ ] Tool-private plans are moved into `plans/`, and `SESSION-LATEST.md` is split by lane (G5 remainder).
- [ ] Stories, proposals and rules are migrated (G4, G2 rules), and drift items are fixed (G6).

## Design Notes

- Contract and validator follow the ADR-0017 pattern: one schema, one validator, one gate for every model.
- `project/scripts/doc_lint.py` keeps its Vietnamese rules for legacy files and skips any file whose frontmatter declares `type`; those files belong to `scripts/knowledge.py`.
- Work happens in worktree `C:/src/news-scape-us039`, branch `feature/us039-knowledge-framework` from `dev/us038`, because another session edits `doc_lint.py` and ADR-0020 on `dev/us038`.
- WIP is per worktree (ADR-0022): US-038 runs in parallel on `dev/us038` in another worktree.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `python -m pytest tests/test_knowledge.py -q` | 15 passed |
| Integration | `python scripts/harness_cli.py doc lint` on the repository | 0 findings, 20 ADRs and 20 facts governed |
| Platform | pre-commit hook rejects a broken staged ADR | rejected `0099-broken.md` with K01, K02, K05 |

## Evidence

- Commits 6004c47 to the ADR-0010 batch on `feature/us039-knowledge-framework`.
- Audit reports of 2026-10-06 (ADR quality, harness rules, stories and memory) summarized in ADR-0021 Context.
