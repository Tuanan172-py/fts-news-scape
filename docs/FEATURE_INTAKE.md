# FEATURE_INTAKE.md — Risk classification → Lane (news-scape)

The classification gate. Run this at step 2 of the change loop. Humans do NOT rank risk themselves — the checklist does it. Vocabulary: [GLOSSARY.md](GLOSSARY.md).

## 1. Input type (where the work lands)

| Type | Use when | Artifact & Route |
|------|----------|------------------|
| **QA Inquiry / Architecture** | Questions, architecture lookups, technical direction | Direct answer + minimal trace in `harness.db` (Tiny) |
| **Diagnostic / Exploration** | Defect investigation, root-cause analysis, system review | Diagnostic report + minimal/standard trace (Tiny/Normal) |
| **New spec** | Turn a specification into product docs and stories | product docs + stories (Normal/High-Risk) |
| **Spec slice** | Implement one behaviour or feature from a specification | 1 story packet (Normal) |
| **Change request** | Change, tune or fix source code | story packet or direct patch + trace |
| **New initiative** | Large feature area spanning several stories | proposal + stories (High-Risk) |
| **Maintenance** | Library upgrades, performance work, DB upkeep | story or decision + trace |
| **Harness improvement** | Improve the human-agent working process | update `docs/*` + ADR when a core standard changes |


## 2. Risk checklist — mark EVERY applicable flag (news-scape-specific)

| Flag | Applies when the change touches |
|------|--------------------------------|
| **DB / data model** | Operational DB schema (`C:\data\news-scape\monocle.db`, path from `project/src/core/paths.py`), `seen_articles`, Bronze/Silver tables, ORM/models. |
| **Dedup logic** | SHA-256(url+title) or fuzzy dedup — a false merge = silent data loss. |
| **Data contract** | Bronze/Silver schema, Article Lane output schemas (`l1-entity-output-v1`, `agent-output-v2-lean` in `project/schemas/`), handoff contract (`project/docs/design/07`, `08`, `00` §6.2), WORM invariants (`content_sha256`). Client/consumer-visible. |
| **Scraper config** | `project/config/domains/*.yaml`, `settings.yaml` (rate limits, selectors, feeds). |
| **Entity catalog / matching** | `entities.json`, catalog matcher guards, watchlist tiers (changes delivery routing). |
| **External API / secrets** | FireAnt bearer token, `project/config/secrets.yaml` (untracked; template `secrets.yaml.example`), any provider SDK/endpoint. |
| **Scheduler / pipeline flow** | `orchestrator.py`, `morninger.py`, `ops_daemon` (`src/ops/runtime/`), APScheduler cycles, single-writer DBWriter. |
| **Existing tested behavior** | Changing already-implemented/tested behavior. |
| **Weak proof** | Tests around the area are vague or missing. |

### Hard gates (any one → high-risk + human decision)
- Schema migration / irreversible data change (WORM violation, dropping columns, backfill).
- Touching external API tokens / secrets.
- Weakening or removing a validation/dedup guarantee.
- Changing a public data contract (Bronze/Silver, Article Lane output schemas, agent handoff envelope).
- **Adding or changing an enum value that some schema validates** — see the warning below.

> **The "additive, so nothing breaks" trap (recorded 2026-09-17, US-011 → US-015).**
> A new enum value looks additive, but when a consumer validates that enum it is a
> **data contract change** and a hard gate. Real case: adding
> `capture_status = "deleted_at_source"` in `raw_store.py` without updating
> `project/schemas/work-package-v1.schema.json:23` held every flagged article at the Silver gate;
> only the production log showed it, no test caught it.
> **Required before adding an enum value:** `grep -rn "<field_name>" project/schemas/ project/domains/`
> to find every place that constrains the value, and update them together.

## 3. Lane selection rule

```
0–1 flag        → tiny (trivial code impact) or normal
2–3 flags       → normal
4+ flags        → high-risk
Any hard gate   → high-risk (unless the human narrows scope)
```

## 4. Per-lane requirements

| Lane | What you must do |
|------|------------------|
| **Tiny** | Note intake inline → patch directly → keep docs current → run a quick check. Skip the story packet (do NOT skip intake). |
| **Normal** | Create 1 story with `python scripts/harness_cli.py doc new --type story --title "..."` (template [templates/story.md](templates/story.md)) → link OKF docs → state validation expectations → record proof in the story + TEST_MATRIX. |
| **High-risk** | Story + ask the human if direction is unclear → record an ADR with `doc new --type adr` (`decisions/NNNN-*.md`, template [templates/adr.md](templates/adr.md)). A trace note does NOT replace the ADR. |

## 5. WIP=1 at intake

Before accepting a new change in this worktree: if this worktree's story is already `in_progress`, either finish it or PARK it (`blocked`/`deferred` + reason) — see [HARNESS.md](HARNESS.md) §3. An urgent interrupt that cannot wait → park current, intake the interrupt, resume after. Never two `in_progress` on one branch; parallel work goes to its own worktree (ADR-0022).

## 6. Intake output — you must be able to state this

```
Lane: normal
Reason: touches scraper config + weak proof
Docs: project/docs/skills/cafef.md, project/docs/dev/03-adding-a-source.md
Story: docs/stories/US-NNN-<slug>.md
Validation: python -m pytest tests/scrapers/test_cafef.py
```
