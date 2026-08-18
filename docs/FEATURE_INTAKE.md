# FEATURE_INTAKE.md — Risk classification → Lane (news-scape)

The classification gate. Run this at step 2 of the change loop. Humans do NOT rank risk themselves — the checklist does it. Vocabulary: [GLOSSARY.md](GLOSSARY.md).

## 1. Input type (where the work lands)

| Type | Use when | Artifact |
|------|----------|----------|
| New spec | Turn a project spec into harness docs | product docs + stories |
| Spec slice | Implement one behavior from a spec/phase | 1 story packet |
| Change request | Change/fix/tune existing behavior | story packet or direct patch (tiny) |
| New initiative | Large area, many stories (e.g. a whole Phase) | initiative note (free text) + stories. NO epic folders — use `Parent / Epic` field. |
| Maintenance | Dependency / perf / security / ops | story or decision |
| Harness improvement | Improve how humans+agents collaborate | update a `docs/*` or a backlog entry |

## 2. Risk checklist — mark EVERY applicable flag (news-scape-specific)

| Flag | Applies when the change touches |
|------|--------------------------------|
| **DB / data model** | `project/data/monocle.db` schema, `seen_articles`, Bronze/Silver tables, ORM/models. |
| **Dedup logic** | SHA-256(url+title) or fuzzy dedup — a false merge = silent data loss. |
| **Data contract** | Bronze/Silver/Gold schema, handoff/agent-io contract (`project/docs/design/07,08,09`), WORM invariants (`content_sha256`). Client/consumer-visible. |
| **Scraper config** | `project/config/domains/*.yaml`, `settings.yaml` (rate limits, selectors, feeds). |
| **Sentiment / classification** | VN sentiment lexicon or classifier rules (changes downstream labels). |
| **External API / secrets** | FireAnt bearer token, `config/secrets.yaml`, any provider SDK/endpoint. |
| **Scheduler / pipeline flow** | `orchestrator.py`, `morninger.py`, APScheduler cycles, single-writer DBWriter. |
| **Existing tested behavior** | Changing already-implemented/tested behavior. |
| **Weak proof** | Tests around the area are vague or missing. |

### Hard gates (any one → high-risk + human decision)
- Schema migration / irreversible data change (WORM violation, dropping columns, backfill).
- Touching external API tokens / secrets.
- Weakening or removing a validation/dedup guarantee.
- Changing a public data contract (Bronze/Silver/Gold, agent handoff envelope).

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
| **Normal** | Create/update 1 story from [templates/story.md](templates/story.md) → link OKF docs → state validation expectations → record proof in the story + TEST_MATRIX. |
| **High-risk** | Story + ask the human if direction is unclear → record an ADR (`decisions/NNNN-*.md` from [templates/decision.md](templates/decision.md)). A trace note does NOT replace the ADR. |

## 5. WIP=1 at intake

Before accepting a new change: if a story is already `in_progress`, either finish it or PARK it (`blocked`/`deferred` + reason) — see [HARNESS.md](HARNESS.md) §3. An urgent interrupt that cannot wait → park current, intake the interrupt, resume after. Never two `in_progress`.

## 6. Intake output — you must be able to state this

```
Lane: normal
Reason: touches scraper config + weak proof
Docs: project/docs/skills/cafef.md, project/docs/dev/03-adding-a-source.md
Story: docs/stories/US-0xx-....md
Validation: python -m pytest tests/test_cafef.py
```
