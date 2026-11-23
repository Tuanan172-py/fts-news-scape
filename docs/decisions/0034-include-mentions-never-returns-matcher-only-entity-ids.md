---
id: ADR-0034
type: adr
title: Include mentions never returns matcher-only entity ids
status: accepted
lane: high-risk
created: 2026-11-23
updated: 2026-11-23
lang: en
authors: [agent]
approvers: ["operator AnPT 2026-11-23, news-scraper#10"]
story: [US-057]
supersedes: []
amends: [ADR-0031]
evidence:
  - "url: https://github.com/Research-FPA/news-scraper/issues/10#issuecomment-7090554250 (operator keeps ADR-0027 and commits to this amendment)"
  - "test: project/tests/test_ner_entity_db_v2.py::test_master_db_migration_candidates_log_and_user_routing"
  - "path: project/src/lakehouse/ingest.py (keep_model_entities in sanitize_article_record)"
summary: Amends ADR-0031.D4 to follow ADR-0027; include_mentions widens the ticker and brief lenses only to model-named mentioned ids, and matcher-only ids stay readable through intent_code.
summary_vi: Sửa ADR-0031.D4 theo ADR-0027; include_mentions chỉ mở rộng sang thực thể mention do mô hình nêu, thực thể chỉ bộ đối chiếu tìm thấy vẫn đọc qua intent_code.
---

# ADR-0034 — Include mentions never returns matcher-only entity ids

## Context

- ADR-0031.D4 gives `lakehouse_client.py` an opt-in `include_mentions` flag that widens the ticker and brief lenses beyond `role = 'primary'`.
- Until now that flag also returned ids that only the deterministic matcher found (provenance `CODE_ONLY`), because they sat in the `entities` column.
- ADR-0027 (fpa-toolkit, accepted 2026-11-15) keeps only model-named ids in `entities` and moves matcher-only ids to `intent_code`. Both exporters pass through `sanitize_article_record`, so the column no longer carries `CODE_ONLY` ids.
- The operator kept ADR-0027 on 2026-11-23 and asked for this amendment, so the two decisions do not contradict each other.

## Decision

1. ADR-0034.D1: `include_mentions` MUST widen the ticker and brief lenses only to ids the model named with `role = 'mentioned'`. It MUST NOT return ids whose provenance is `CODE_ONLY`.
2. ADR-0034.D2: Matcher-only ids MUST stay readable through `intent_code` and `intent_source`, as ADR-0027.D3 requires.
3. ADR-0034.D3: The rest of ADR-0031.D4 stands: exporters encode `[TYPE|ROLE|PROVENANCE]` tags, and the client never unions raw scraper `symbols` for enriched articles.

## Alternatives

| Option | Why rejected |
|---|---|
| Keep returning `CODE_ONLY` ids under `include_mentions` | Contradicts ADR-0027, which the operator kept; the gold set put `entities` precision at 15% with matcher ids and 48% without them. |
| Re-add matcher ids to `entities` for this flag only | Two meanings for one column; every reader would need the flag to interpret it. |

## Consequences

- Readers who opt into mentions get model-named mentions only, which is the precision ADR-0027 measured.
- A real company the model missed no longer appears under `include_mentions`; it remains in `intent_code`, and a reader can query that column directly.
- The production test that expected HSG under `include_mentions` now expects it only in `intent_code`.

## Rollback

Revert this ADR and the test change, and revert the ADR-0027 calls to `keep_model_entities`. The operator or the repository owner may do it.

## Follow-up

- [x] Change the expectation of `test_master_db_migration_candidates_log_and_user_routing` (US-057).
- [ ] fpa-toolkit removes the xfail on that test in the M2 sync.
