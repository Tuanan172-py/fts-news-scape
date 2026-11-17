---
id: ADR-0032
type: adr
title: Event kind label in the article contract separates PR from valuation catalysts
status: proposed
lane: high-risk
created: 2026-11-16
updated: 2026-11-16
lang: en
authors: [agent]
approvers: []
story: [US-053]
supersedes: []
amends: []
evidence:
  - path:project/schemas/article-compact-v2.schema.json
  - path:project/src/lakehouse/ingest.py
  - path:plugins/fpts-market-intel/rules/AGENTS.md
summary: Proposes a closed event_kind field produced by article-processor, stored in the existing categories column, so lenses can drop brand PR from market-impact conclusions without script heuristics.
summary_vi: Đề xuất nhãn event_kind do article-processor sinh ra, lưu vào cột categories sẵn có, để lens loại tin PR thương hiệu khỏi kết luận tác động thị trường mà không dùng script suy đoán.
---

# ADR-0032 — Event kind label in the article contract separates PR from valuation catalysts

## Context

- The Parquet column `categories` exists in `LAKEHOUSE_ARTICLE_SCHEMA` (`ingest.py`, string) but carries no event nature; lenses cannot tell a brand PR or award story from a valuation catalyst (policy, earnings, M&A, legal).
- Measured symptom in the plugin audit of 2026-11-16: the `top_titles_7d` of the exchange-rate theme listed a bank anniversary story. Also, a sentiment weight of +1 treats a brand PR like a central-bank policy move.
- AGENTS.md section 7.3 forbids replacing agent intelligence with regex or heuristics, so the label cannot be filled by a script that reads titles.
- Changing the compact record schema changes the shared output contract and the validator that every provider passes (ADR-0017), so the change is high-risk and needs human approval before any code.

The plugin already mitigates the symptom with role and provenance filters and with reading `implication`, but it cannot reliably classify event nature without a model-produced field.

## Decision

1. The compact record MUST gain one optional key `ek` with a closed enum of six values: `MACRO_POLICY`, `EARNINGS_FINANCE`, `CORP_ACTION_MA`, `LEGAL_RISK`, `MARKET_MICROSTRUCTURE`, `PR_BRANDING`.
2. `article-processor` MUST produce `ek` in the same single turn; no extra model call and no script heuristic MAY derive it.
3. The shared validator MUST reject any value outside the enum with the code `enum:ek:<value>` and MUST accept records without `ek` so legacy waves stay valid.
4. `article_expand.py` MUST write the value into the existing `categories` column (no Parquet schema change) and the plugin MAY expose it as `event_kind`.
5. Lenses SHOULD exclude `PR_BRANDING` from market-impact conclusions only after the golden set shows at least 90% agreement with a human-labelled sample.

## Alternatives

| Option | Why rejected |
|---|---|
| Keyword or regex classifier in the plugin | Violates AGENTS.md section 7.3 and fails on paraphrase; brand PR and policy stories share vocabulary. |
| Second model pass per article | Doubles token cost for every wave and adds a second contract, against the single-turn rule of ADR-0010 and ADR-0017. |
| Keep reading `implication` only | Already in use; it is unstructured, so counts and filters cannot be computed and the weakness remains. |

## Consequences

- Gains: structured filter for PR versus catalyst; `categories` stops being empty; no Parquet schema migration.
- Costs: prompt and golden-set update for every provider, a small output-token increase per article, and a backfill decision for the 56,000 existing Gold rows (rows without `ek` stay unlabelled).
- Risk: a provider that mislabels PR as catalyst silently weakens the filter; mitigation is the 90% agreement gate before any lens relies on the label.

## Rollback

- Remove `ek` from the schema and the prompt prefix, keep the validator tolerant of the key, and stop writing `categories`; existing Parquet files stay valid because the column already existed. The operator performs the rollback.

## Follow-up

- [ ] Operator approves or rejects this ADR; no code lands before approval.
- [ ] After approval, extend `article-compact-v2.schema.json`, the validator, `article_expand.py` and the golden set in one story.
- [ ] Decide whether to backfill existing Gold rows (see the open decision on the 2026-11-01 to 2026-11-12 entity re-derivation in US-053).
