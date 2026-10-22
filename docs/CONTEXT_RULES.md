# CONTEXT_RULES.md — Bounded Context & Token Budget Matrix (H2)

This document defines what an agent reads, per **phase** and **risk lane**, so that it reads the right files and only those, keeps the context window bounded and controls the token budget.

---

## 1. Token budgets per risk lane

| Risk lane | Estimated context budget | Maximum files read | Stop heuristic |
|:---|:---:|:---:|:---|
| **`tiny`** | $\le 2,000$ tokens | 3 – 5 files | Stop as soon as the line to patch and the test command are known. |
| **`normal`** | $\le 5,000$ tokens | 10 – 15 files | Stop when the story packet is complete and the module involved is understood. |
| **`high-risk`** | $\le 10,000$ tokens | 20 – 30 files | Stop when there is enough evidence to write the ADR and name the hard gate. |

The file ceilings match `calculate_score_context` in `scripts/harness_cli.py` (tiny 5, normal 15, high-risk 30).

> **Scope of the file ceiling (added 2026-09-17, US-014).** The ceiling counts **files that enter
> the orchestrating agent's context window directly**. Files an Explore subagent reads on its
> behalf do **not** count: they stay in the subagent's own context and come back only as a
> condensed report. Record that number separately in the trace when it matters.
>
> Reason: the budget exists to *control the context window*, and delegating exploration to a
> subagent achieves exactly that. Counting both would **penalise the behaviour the rule
> encourages** and reward reading everything inline. US-011 is the evidence: its trace was
> complete and honest but scored `score_context = 0.6` because it counted the files of two
> Explore subagents.

---

## 2. Context matrix (phase x lane)

Rule: **MUST** (read) · **SHOULD** (read if still unclear) · **SKIP** (do not read).

| Phase | Tiny lane | Normal lane | High-risk lane |
|:---|:---|:---|:---|
| **1. Intake & Classify** | **MUST:** `AGENTS.md`, `FEATURE_INTAKE.md`<br/>**SKIP:** old story packets, DB source code | **MUST:** `AGENTS.md`, `FEATURE_INTAKE.md`<br/>**SHOULD:** `HARNESS.md`<br/>**SKIP:** deep implementation details | **MUST:** `AGENTS.md`, `FEATURE_INTAKE.md`, `docs/decisions/`<br/>**SHOULD:** `project/docs/design/` |
| **2. Context & Planning** | **MUST:** the target code file<br/>**SKIP:** general architecture docs | **MUST:** related OKF docs (`project/docs/skills/`), test files, RULE-12 for where code belongs<br/>**SKIP:** unrelated modules | **MUST:** OKF + `project/docs/design/`, schema definitions, related ADRs |
| **3. Implementation** | **MUST:** the target code file<br/>**SKIP:** every policy document | **MUST:** the target module + its unit test<br/>**SKIP:** all of `docs/` | **MUST:** core models, data contracts, migrations |
| **4. Validation & Proof** | **MUST:** the related test file<br/>**SKIP:** every other document | **MUST:** the related test suite, `TEST_MATRIX.md` | **MUST:** the full unit + integration + platform test layers |
| **5. Trace & Handoff** | **MUST:** `SESSION-LATEST.md` | **MUST:** `SESSION-LATEST.md`, `docs/stories/US-NNN-<slug>.md` | **MUST:** `SESSION-LATEST.md`, ADR, story packet |

---

## 3. Retrieval stopping rules

1. **Rule of direct match:** when a search tool has located the exact defect or function to change, the agent **MUST NOT** open further reference files around it.
2. **No full-repo dumps:** never read a whole folder or paste many `.md` files into the prompt without a concrete reason. Use `docs/INDEX.md` to find governed documents.
3. **Progressive disclosure:** read the summary first; open child documents under `references/` or `scripts/` only when an execution step needs them.

---

## 4. Radar-first, zero-probe and continuous learning

The defining rule is `.agents/rules/08-context-and-zero-probe-guardrails.md` (AGENTS.md §9). In short:

1. **Zero-probe:** ad-hoc Python one-liners (`-c "import sqlite3..."`) that probe the DB or count files are forbidden. Run `python project/scripts/pipeline_radar.py status` for operating context and the next command; path, cwd and DB-write questions go to `python project/scripts/article_run.py --where`.
2. **No huge files:** never read runtime dictionaries such as `entities.json` (1.5 MB) directly. The owning skill summarises the mappings.
3. **Continuous learning:** after each run, every friction or optimisation found becomes a `FACT-*` document, a rule or a skill update, and the handoff goes into `SESSION-LATEST.md`.
