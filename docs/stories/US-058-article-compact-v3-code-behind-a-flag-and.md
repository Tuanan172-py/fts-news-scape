---
id: US-058
type: story
title: Article-compact-v3 code behind a flag and agy cost sample
status: planned
lane: high-risk
created: 2026-11-23
updated: 2026-11-23
lang: en
authors: [agent]
adr: [ADR-0033]
plan: [PLN-20261123-1510-production-upgrade-to-article-compact-v3-and-sync]
evidence: []
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_impact_contract.py project/tests/test_impact_labels.py project/tests/test_plugin_lakehouse_client.py project/tests/test_article_contract_v3_flag.py -q"
summary: Production code can run article-compact-v3 behind a flag that stays off, writes the x and provenance columns under obt/3, and has a measured agy cost.
---

# US-058 — Article-compact-v3 code behind a flag and agy cost sample

## Contract

The operator can switch the article pass between `v2` and `v3` with one config flag, default `v2`. With the flag off, output is unchanged except four new NULL-able columns at the end of the schema. With it on, records carry `x` and the contract, rubric and prompt stamps. A cost report on `agy` supports the M3 decision.

## Acceptance Criteria

- [ ] `article.contract: v2 | v3` in `config/ops.yaml`, default `v2`, read in one place.
- [ ] No runner hardcodes the v2 prefix path; `check_prefix` covers both variants.
- [ ] `x`, `contract_version`, `rubric_version`, `prompt_hash` are last in `LAKEHOUSE_ARTICLE_SCHEMA`; `OBT_SCHEMA` is `obt/3`.
- [ ] Flag off: a replayed v2 batch gives the same rows except the new columns.
- [ ] P7 report on about 400 articles, tokens primary, time as reference.

## Design Notes

Plan PLN-20261123-1510, phases P5 and P7. Decisions D2, D4, D5, D7. The branch joins `import/clean-20261127` and reaches `dev/us038` only at M3, by merge.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `verify` command above | |
| Integration | full suite once before R2 | |
| Platform | P7 cost report | |

## Evidence

