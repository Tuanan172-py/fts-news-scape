---
id: ADR-0029
type: adr
title: Unified documentation lifecycle
status: accepted
lane: high-risk
created: 2026-10-23
updated: 2026-10-23
lang: en
authors: [claude-opus-5-5]
approvers: [operator 2026-10-23]
story: [US-051]
supersedes: []
amends: [ADR-0021, ADR-0024]
related: [ADR-0001, ADR-0002, ADR-0012, ADR-0020, ADR-0022, ADR-0026]
evidence:
  - path:docs/knowledge/schema.yaml
  - path:scripts/knowledge.py
  - path:project/scripts/doc_lint.py
  - path:scripts/git_hooks/pre-commit
  - path:docs/knowledge/legacy.txt
  - metric:161 files under schema path globs, 111 with contract frontmatter, about 380 doc files outside any type, inventory 2026-10-22
  - metric:story status written by four code paths (frontmatter, story commands DB-only, session close string replace, doc sync), tooling map 2026-10-22
  - metric:41 live markdown files outside records still name retired lane components after US-050, scan 2026-10-23
  - metric:legacy.txt holds 39 entries, two of them stale id lines for US-038 and US-040, 2026-10-23
  - "operator: 2026-10-22 language split by reader, light contract for reference documents, one ADR plus one story in waves"
summary: "Every tracked markdown file belongs to one declared document class with one writer, one command and one mechanical check; one linter, one status writer, generated-file freshness checks, a dispatcher hook and one canonical document per topic."
summary_vi: "Mỗi tệp tài liệu thuộc đúng một lớp có người ghi, lệnh và bước kiểm riêng; một bộ lint, một luồng ghi trạng thái story, kiểm tệp sinh tự động, hook tự cài, một tài liệu gốc cho mỗi chủ đề."
---

# ADR-0029 — Unified documentation lifecycle

## Context

- ADR-0021 governs eight record types. Its schema path globs match 161 files, and 111 of them carry contract frontmatter. Both linters report 0 findings.
- About 380 documentation files sit outside every type. They include `docs/*.md` hub pages, `.agents/rules`, skills, `.agents/dsh`, `project/docs/**`, `okf/**` and the analyst plugin. Most of them are Vietnamese and operator-facing.
- Two linters overlap. `scripts/knowledge.py` checks the contract. `project/scripts/doc_lint.py` checks Vietnamese style, body links and user-interface strings for a hand-kept file list, with a 25-word sentence limit against 35 in the contract.
- Story status has four writers: frontmatter edits, `story update` and `story complete` (database only), a string replace in `session close`, and `doc sync`. Nothing detects database-to-file drift.
- Nothing checks that `docs/INDEX.md` is current. Body references such as `ADR-0021.D3` are never resolved. The pre-commit hook is copied by hand into the shared git directory, so every worktree runs whichever copy was installed last.
- The same topic is written in several places: architecture in five files, daily runbooks in more than eight, the commit standard in three, the entity system in five.
- Accepted ADR bodies were edited after the ADR-0021.D6 freeze. ADR-0012 gained a strike-through and an ADR-0026 note on 2026-10-21. ADR-0020 was edited on 2026-10-06, 2026-10-08 and 2026-10-15 without a history note.
- ADR-0024.D5 names two `harness.db` locations. The live file is the canonical worktree root, which `harness_db_path()` returns. The copy under `C:\data\news-scape` was last written on 2026-10-08.
- US-050 already moved documents about retired subjects to an archive. A scan on 2026-10-23 still finds 41 live markdown files outside records that name retired lane components.

## Decision

- D1. Every tracked markdown file MUST belong to exactly one class declared in `docs/knowledge/schema.yaml`. The classes are record, normative, reference, external, generated, ledger and archive. A file in no class is a lint finding.
- D2. Records (adr, story, proposal, plan, run, fact) and normative documents (rule, `AGENTS.md`, harness hub pages in `docs/`) MUST be English. This restates ADR-0021.D4 for those classes.
- D3. Reference documents for operators or users MAY be Vietnamese with `lang: vi` and an `audience` key. This amends ADR-0021.D4, which allowed Vietnamese only in operator runbooks.
- D4. New light types are added: `reference` (id `REF-slug`, statuses active, pointer, retired, no required sections), `ledger` and two external types. This amends ADR-0021.D2.
- D5. Skills and OKF catalog files are external types. Lint MUST NOT require or add keys to their frontmatter; it derives their id from the path and checks only their native keys, links and retired terms.
- D6. One linter remains. `scripts/knowledge.py` absorbs every rule of `project/scripts/doc_lint.py`, which is then deleted. This amends ADR-0021.D10.
- D7. New lint codes K14 to K22 are added. They cover body id references, retired terms in live documents, a stale index and a stale or growing `legacy.txt`. They also cover duplicate canonical topics, broken body links, internal codes in user-facing text, user-interface strings and unclassified files.
- D8. Codes listed in `lint.warn` report without failing during migration. The list MUST be empty when US-051 closes.
- D9. Story status has one writer, `knowledge.set_story_status`. It edits frontmatter (`status`, `updated`, `branch`, `evidence`), re-lints the file, syncs the database and rewrites the index. `story` commands and `session close` MUST call it.
- D10. No code writes story status from the database to files. `audit` reports any database row whose status differs from its file.
- D11. Generated files are checked. `doc index --check` and lint code K16 fail when `docs/INDEX.md` differs from `build_index()`. The hook runs `build_diagrams.py --check` when a diagram source is staged.
- D12. `harness_cli.py hooks install` writes a dispatcher into the common git directory. The dispatcher runs `scripts/git_hooks/pre-commit` from the committing worktree and exits 0 when that file is absent.
- D13. Each topic has one canonical document, recorded under `topics` in `schema.yaml`. Other files on the topic become pointers of at most 15 lines with a link to the canonical document.
- D14. The initial canonical documents are as follows:
  - Architecture: `project/docs/design/00-end-to-end-architecture.md`.
  - Harness process: `docs/HARNESS.md`.
  - Commit standard: `docs/GIT_COMMIT_STANDARD.md`.
  - Decisions: the ADR set.
  - Unattended operation: `project/docs/operations/ops-daemon.md`.
  - Interactive DSH operation: `.agents/dsh/RUNBOOK-article-lane.md`.
  - Entity system: `project/docs/design/14-entity-system-and-mapping.md`.
  - Naming: `docs/GLOSSARY.md`.
- D15. The post-freeze body edits to ADR-0012 and ADR-0020 are ratified as written. Their bodies MUST NOT be restored. Any further change to an accepted ADR goes through a new ADR, per ADR-0021.D6.
- D16. The only harness database is `harness.db` at the root of the canonical worktree `C:\src\news-scraper`. Temporary worktrees MUST pass `--db` with that path. This amends ADR-0024.D5.
- D17. The copy at `C:\data\news-scape\harness.db` is stale and is moved to the archive by the operator.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep the contract scope at eight record types and finish only the US-039 work packages | About 380 live documents stay unchecked; retired terms and duplicate topics keep returning, as the 41 remaining files after US-050 show |
| Full template contract for every document | Operator chose a light contract on 2026-10-22; required H2 sections do not fit design pages, skills or OKF entries |
| Translate every document to English | Operator chose the language split by reader on 2026-10-22; operator runbooks and analyst skills are read in Vietnamese |
| Keep two linters with separate scopes | Two banned-phrase lists, two sentence limits and a hand-kept file list in `doc_lint.py` drift apart |
| Restore the frozen bodies of ADR-0012 and ADR-0020 | Readers and later ADRs already cite the edited text; a restore rewrites history twice for no operational gain |

## Consequences

- Gains:
  - Every markdown file has a declared class, so drift is caught at commit time rather than in audits.
  - Story status cannot diverge between file and database without an audit finding.
  - Each worktree runs its own hook.
- Costs:
  - One migration story of about six waves.
  - Light frontmatter on roughly 120 reference files.
  - A larger `knowledge.py`.
- Risks and mitigations:
  - New codes start in warn mode, so commits between waves are not blocked.
  - External types never change skill or OKF frontmatter, so skill loaders and the OKF validator keep working.

## Rollback

- Delete the new types, codes and `topics` from `schema.yaml` and restore `project/scripts/doc_lint.py` from git.
- Revert the `set_story_status` callers.
- Reinstall the previous hook copy.
- Light frontmatter on reference files is harmless and may stay.
- The operator decides the rollback; any agent may execute it.

## Follow-up

- [ ] US-051 wave W-B: schema version 2, codes K14 to K22 in warn mode, `doc_lint.py` merged and deleted.
- [ ] US-051 wave W-C: `set_story_status`, rewired `story` and `session close` commands, `hooks install`, `doc index --check`.
- [ ] US-051 wave W-D: classify every file; migrate 12 rules and 22 plans; give ADR-0020 and US-041 frontmatter; empty `legacy.txt`.
- [ ] US-051 wave W-E: canonical topics and pointers; translate harness hub pages; fix drift in SESSION-LATEST and OPEN-ITEMS.
- [ ] US-051 wave W-F: clear the remaining retired terms; move tool-private plans and memory into the repository; empty `lint.warn`.
- [ ] Operator: archive `C:\data\news-scape\harness.db`.
