# Knowledge Contract

Binding for every agent and model (Claude, Codex, agy, opencode, OpenRouter) that writes project knowledge. Decision: [ADR-0021](../decisions/0021-agent-first-knowledge-framework.md). Machine-readable schema: [schema.yaml](schema.yaml).

## 1. Read Order

1. `docs/INDEX.md`: every governed document with id, status and one-line summary.
2. The frontmatter of a candidate document. Open its body only when the summary is relevant.
3. Never scan folders or read whole documents to find context; the index exists for that.

## 2. Write Rules

- K-R1. Create every governed document with `python scripts/harness_cli.py doc new --type <type> --title "<English title>"`. MUST NOT pick an id or number by hand.
- K-R2. Every governed document MUST start with the YAML frontmatter its template carries. Keys and enums are defined only in `schema.yaml`.
- K-R3. Language is English (`lang: en`) for every harness document. Vietnamese is allowed only inside double quotes or blockquotes (verbatim source or operator text), inside code, and in `summary_vi`. Operator runbooks MAY use `lang: vi`.
- K-R4. Keep the H2 sections of the template, in order, with the exact heading text. Add H3 subsections freely.
- K-R5. Open each section with bullets, one checkable claim per bullet. Use MUST, MUST NOT and SHOULD in the RFC 2119 sense. Number decisions (`D1`, `D2`) and rules (`R1`, `R2`) so other documents cite them as `ADR-0021.D3`.
- K-R6. Every measured claim cites evidence in frontmatter `evidence` with a prefix: `commit:`, `path:`, `metric:`, `test:`, `wave:`, `url:`, `operator:`.
- K-R7. Each invariant has exactly one defining document. AGENTS.md, skills, runbooks and other documents cite its id; they MUST NOT restate it.
- K-R8. The body of an accepted ADR is frozen. Change direction with a new ADR that lists the old id in `supersedes` or `amends`, then set the old ADR's `status` to `superseded` when fully replaced. Frontmatter stays editable.
- K-R9. Facts, pitfalls and operator preferences found in a session go to `docs/knowledge/facts/` as `FACT-*` files. Tool-private memory (`~/.claude`, `~/.codex`, `.opencode`, `.kilo`) is scratch and MUST NOT be the only copy of anything.
- K-R10. Plans live in `plans/<YYYYMMDD>-<HHMM>-<slug>/plan.md`. Plans elsewhere MUST NOT be cited.
- K-R11. Run `python scripts/harness_cli.py doc lint` before commit; the pre-commit hook runs it on staged files. Then run `doc index` to refresh `docs/INDEX.md`.

## 3. Types

| Type | Id | Location | Status values |
|---|---|---|---|
| adr | `ADR-NNNN` | `docs/decisions/NNNN-slug.md` | proposed, accepted, rejected, superseded |
| story | `US-NNN` | `docs/stories/US-NNN-slug.md` | planned, in_progress, blocked, deferred, implemented, changed, retired |
| proposal | `PRP-YYYYMMDD-slug` | `docs/proposals/YYYYMMDD-slug.md` | draft, decided, parked, rejected |
| plan | `PLN-YYYYMMDD-HHMM-slug` | `plans/YYYYMMDD-HHMM-slug/plan.md` | draft, approved, executing, done, superseded, parked |
| fact | `FACT-slug` | `docs/knowledge/facts/slug.md` | active, stale, retired |
| rule | `RULE-NN` | `.agents/rules/NN-slug.md` | active, retired |
| run | `RUN-<wave>` | `docs/runs/<wave>.md` | open, closed |
| runbook | `RB-slug` | `project/docs/operations/slug.md` | active, retired |

## 4. Lint Codes

| Code | Meaning |
|---|---|
| K00 | Governed path without frontmatter and not listed in `legacy.txt` |
| K01 | Required key missing, unknown key, or invalid YAML |
| K02 | Value outside its enum (status, lane, lang) |
| K03 | Id malformed, or file name does not match the id |
| K04 | Duplicate id |
| K05 | Required H2 section missing or out of order |
| K06 | Content floor not met (words, table rows, list items, summary length) |
| K07 | Link to an id that does not exist |
| K08 | Evidence entry without an allowed prefix |
| K09 | Vietnamese prose in a `lang: en` body |
| K10 | Style: emoji, banned filler phrase, sentence over 35 words |
| K11 | Superseded by an accepted document but status not terminal |
| K12 | Date not in `YYYY-MM-DD` |

## 5. Migration

`legacy.txt` lists files created before ADR-0021. They pass K00 until migrated. Migrating a file means adding frontmatter, translating to English and removing its line from `legacy.txt`. The list MUST only shrink.

## 6. Context Pack for Models Without File Access

Runners that call a model over an API (OpenRouter) cannot open files. They pass the model `docs/knowledge/README.md`, `docs/INDEX.md` and only the documents whose ids the task cites.
