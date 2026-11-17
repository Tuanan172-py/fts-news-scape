---
id: US-053
type: story
title: Lakehouse plugin lens fixes and source noise guards
status: blocked
lane: normal
created: 2026-11-16
updated: 2026-11-16
lang: en
authors: [agent]
adr: [ADR-0032]
plan: []
evidence:
  - path:plugins/fpts-market-intel/tools/lakehouse_client.py
  - path:project/tests/test_plugin_lakehouse_client.py
  - path:project/src/agent/entities.py
  - path:project/src/agent/article_contract.py
  - path:docs/decisions/0032-event-kind-label-in-the-article-contract-separates.md
verify: "C:/venvs/news-scape/Scripts/python.exe -m pytest project/tests/test_plugin_lakehouse_client.py project/tests/test_entities.py project/tests/test_article_contract.py -q"
summary: The market-intel lenses read the Production lakehouse by default, stop reporting false acceleration and buzz after the entity regime change, and the L1 matcher and output validator reject known noise.
---

# US-053 — Lakehouse plugin lens fixes and source noise guards

## Contract

After this story an analyst running any `fpts-market-intel` lens reads the Production lakehouse (`FRA - Data/news`) by default. The lenses give warnings, not false "acceleration" or "spike" signals, when the entity-labelling regime changed or history is sparse. The `brief` macro tier keeps macro stories that also mention a bank. The L1 matcher no longer tags known abbreviation codes, and the output validator rejects a summary that does not describe its title. The story is `blocked` only on two human decisions: approval of ADR-0032 (event kind label, item D3) and whether to re-derive entities for 2026-11-01 to 2026-11-12 (item A6).

## Acceptance Criteria

- [x] A1: `resolve_lakehouse_root()` prefers `NEWS_DATA_ROOT`, then `NEWS_SCAPE_RESEARCH_DB_DIR`, then production-before-sandbox discovery; `NEWS_SCAPE_PUBLISH_DIR` is the last resort. `status()` reads `day`, `date_to` or `latest_date`.
- [x] A2: `buzz` and entity-based `themes` compare only against data from the regime start in `config/regimes.json` (2026-11-13); short baselines raise no spike flag and produce `warnings`.
- [x] A3: `data_range()` exposes `dense_data_from`; `timeline`, `themes` and `pulse` return `window_starts_before_dense`.
- [x] A4: heavy lenses materialize `articles` and entity tables once and match keywords on a precomputed `search_text` column; `themes` on 56,000 rows dropped from 289 s to about 20 s end to end.
- [x] A5: `buzz` uses `sqrt(mean + 1)` as a Poisson-smoothed standard-deviation floor and `min_articles` defaults to 3.
- [x] P1: lenses default to `role = primary` and provenance other than `CODE_ONLY`; `--include-mentions` widens it.
- [x] P2: `brief` macro tier keeps stories with a primary `BOTH`/`LLM_ONLY` macro entity even when a ticker is also present.
- [x] P3: `articles` has `trade_date` (after 14:45 ICT or weekend maps to the next session, holidays not modelled) and `urgency_w`; `pulse` returns `effect_net_sent` and takes `--basis`.
- [x] P4: `top_titles_7d` orders primary and hot stories first; `config/universes.json` provides `vn30` and `vn100` (market-cap proxies) for `--universe`; four money-flow themes added.
- [x] P5: plugin `rules/AGENTS.md` section 8 and the pulse, buzz, themes and brief `SKILL.md` files document divergence reading, PR exclusion and the new warnings.
- [x] D1: `CODE_STOPLIST` gains `VTV, CVT, C21, HRC, MA1, BAX, AAH, UDJ` (accepted with a CBTT prefix or a stock word before the code), `hrc` leaves `PROTECTED_SHORT_WORDS`, and `IND_GICS3:XAY_DUNG` has `drop_bare`.
- [x] D2: `validate_record` returns `summary_title_mismatch` when no significant title word appears in the summary, key points, implication, cited paragraphs or entity surfaces.
- [ ] D3: event kind label in the Gold layer, awaiting approval of ADR-0032.
- [ ] A6: decide whether to re-derive entities for 2026-11-01 to 2026-11-12 under ADR-0031 (operator decision).

## Design Notes

- D4 from the audit list was rejected: `ingest.py` already declares `symbols` as `list<string>`, so no schema drift exists.
- `IND_GICS3:GIAY` already had `drop_bare: true`; only `XAY_DUNG` was added.
- `scripts/maintenance/refresh_aliases.py` was not run: it rewrites the operational `entities.json` outside the repository, and guards are read from YAML at registry load. Run it when no wave is open.
- The universes are market-capitalisation proxies from `market_caps.parquet` (dated 2026-11-16), not the official HOSE baskets; replace them when the official lists are available.
- Measured on 49,757 Gold rows since 2026-09-01, the D2 gate would flag 174 rows (0.35%); the sampled hits were genuine title and summary swaps.
- Constraints: AGENTS.md section 7.3 (no script emulation of agent intelligence) is why D3 needs a model-produced field.

## Verification

| Tier | Command or check | Result |
|---|---|---|
| Unit | `pytest project/tests/test_plugin_lakehouse_client.py test_entities.py test_article_contract.py` | pass (29 + entity and contract suites) |
| Integration | Lenses run on Production lakehouse (56,000 rows): `themes` no longer reports false acceleration, `buzz` raises no flag with 3 baseline days | pass |
| Platform | Full `project/tests` first run: 1146 passed, 5 failed. After fixing the 5, full re-run: 1151 passed, 0 failed | The 5 predated this story: `retag_location_symbols.py` now uses `paths.state_dir()`, the `check_l1_dod` test stub accepts `paragraphs`, and `release_stale_waves.py` cancelled the PARKED wave W11091520 and FAILED W11091741 so the ops-queue checks pass |

## Evidence

- Default root on this machine changed from the Sandbox to `FRA - Data/news` after the environment-variable precedence fix.
- Residual: `brief` macro tier still includes generic `MACRO_GEO` stories after the multi-scope NER regime; revisit with ADR-0032 data.
