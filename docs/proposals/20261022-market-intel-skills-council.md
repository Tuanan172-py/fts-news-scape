---
id: PRP-20261022-market-intel-skills-council
type: proposal
title: Review council for fpts-market-intel analyst skills
status: draft
lane: normal
created: 2026-10-22
updated: 2026-10-22
lang: en
authors: [skills council (6 members), agent]
adr: [ADR-0025]
story: [US-044]
plan: []
evidence:
  - path:docs/proposals/20261022-market-intel-skills-council/position_1_co-ban.md
  - path:docs/proposals/20261022-market-intel-skills-council/position_2_thi-truong.md
  - path:docs/proposals/20261022-market-intel-skills-council/position_3_vi-mo-morning.md
  - path:docs/proposals/20261022-market-intel-skills-council/position_4_thong-ke.md
  - path:docs/proposals/20261022-market-intel-skills-council/position_5_red-team.md
  - path:docs/proposals/20261022-market-intel-skills-council/position_6_toi-gian.md
  - path:plugins/fpts-market-intel/tools/lakehouse_client.py
  - metric:18,457 of 34,043 sandbox articles have no summary and all carry sentiment=neutral, time_sensitivity=today, 2026-10-22
  - metric:articles without summary are about 100% until 2026-08, 51.1% in 2026-09 and 41.5% in 2026-10
  - metric:is_hot true for 69.6% of articles, 2026-10-22
  - metric:story grouping merges 16,759 October articles into 15,879 stories (about 5%)
summary: Are the US-044 skills fit for analysts on the one-year sandbox? Keep the direction, but first exclude unenriched articles, normalize for collection volume, close the SQL file read and fold twelve skills into six.
summary_vi: Hội đồng giữ định hướng skill theo use case, nhưng phải sửa lớp đo (loại bài chưa qua LLM, chuẩn hoá theo khối lượng thu thập), chặn đọc tệp qua query SQL và gộp 12 skill còn khoảng 6 trước khi phát hành cho analyst.
---

# PRP-20261022-market-intel-skills-council — Review council for fpts-market-intel analyst skills

## Question

- Are the twelve skills shipped in US-044 (plugin v1.1.0) fit for daily use by the Fundamental, Market/Technical, Macro and Morning desks, now that the sandbox holds one year of data (2025-10-01 to 2026-10-21)?
- If not, what must change first, and which skills should be added, merged or dropped?
- Six independent members reviewed read-only and ran the lenses on the real sandbox: (1) Fundamental analyst, (2) Market/Technical analyst, (3) Macro/Geo and Morning analyst, (4) statistical validity, (5) red team, (6) minimalist.
- `[checked]` marks claims the chair re-measured on the Parquet files after the member reports.

## Findings

### Executive conclusion

- All six members keep the direction: subject + time window + question, with deterministic DuckDB lenses at zero tokens and the LLM only interpreting.
- The measurement layer is not yet trustworthy on the real data. Five of six members independently reached the same root cause (blocker C1). The current output would mislead analysts while every coverage flag reports "sufficient".
- Twelve skills map onto only seven lenses. Members 1, 2 and 6 independently proposed merges.

### Blockers (fix before analysts rely on the output)

| Id | Finding | Evidence | Raised by |
|---|---|---|---|
| C1 | Articles not yet enriched by the LLM carry default `sentiment=neutral`, `time_sensitivity=today`, no summary and few entities; lenses count them as real labels. | 18,457 no-summary articles are all neutral/today; no-summary share ~100% until 2026-08, 51.1% in 2026-09, 41.5% in 2026-10 [checked]. Daily net sentiment correlates 0.665 with the enriched share (member 4). | 1, 2, 3, 4, 5 |
| C2 | `is_hot` includes `today`, so "urgent news" is almost every article. | 69.6% of all articles are hot [checked]. | 2, 3, 4 |
| C3 | Baselines use raw counts while collection grew about 100x (24 articles in 2025-10, 16,759 in 2026-10). `themes` shows m30/90 ≈ 1.9-2.7 for 18/20 themes; `pulse` ranks 2026-10-21 at the 85.7th percentile against a history where 95/133 days have net = 0 (32.1 on enriched days only). `sufficient_*` flags stay true. | Member 3 and 4 measurements; monthly counts [checked]. | 2, 3, 4, 5 |
| C4 | `query --sql` reads arbitrary local files and lists folders (`read_text`, `glob`); the keyword blocklist is bypassed with whitespace or `COPY(`. | `read_text` on a scratch file returned its content [checked]. | 5 |
| C5 | The installed skills call `python` on PATH, which on this machine is Anaconda without duckdb; every skill fails and the installer self-test does not detect it. | `python -c "import duckdb"` → ModuleNotFoundError [checked]. | 5 |

### Severe findings

- S1 Ticker resolution: any 3-character string is treated as a ticker (`resolve_target("dầu")` → `TICKER:DẦU`; FED, GDP, PPI). `TICKER:HCM` from the `symbols` column is mostly Ho Chi Minh City: 420 of 892 titles (member 4); entities alone show 86 articles, 12 with TP.HCM in the title [checked, partially reproduced]. Needs a listed-ticker whitelist and stoplist.
- S2 Buzz: the 0.5 SD floor lets 2 articles on a zero baseline score z = 4; 14 of 19 flags on 2026-10-21 have mean < 1 (members 2, 4). Needs minimum-count and share-of-voice normalization.
- S3 Story grouping merges only exact normalized titles: about 5% reduction in October [checked]. It merges recurring titles across days (33 groups spanning > 7 days) and misses 447 near-duplicate pairs (member 4). `max-stories` truncation keeps the oldest stories (`lakehouse_client.py:534-537`, member 1).
- S4 Time: `pub_date` is the calendar date; 38% of articles publish after 14:45 and count as session T; weekends sit in the baseline; the empty day 2026-10-20 raises no warning (member 2).
- S5 Keyword match is accent-sensitive: "Hòa Phát" 168 vs "Hoà Phát" 6 [checked]; unaccented input returns 0.
- S6 Cooccur lift is inflated about 2.9x because the denominator includes articles without entities, and there is no minimum support (member 4).
- S7 Themes: false positives ("xung đột lợi ích", "blue-chip", "thép" in road-construction articles) and misses (74% of Iran/Hormuz/Israel articles outside `xung_dot`); existing entities `THUE_THUONG_MAI` and `NANG_HANG_TTCK` are unused (member 3).
- S8 Compliance wording: several SKILL.md files let the LLM state causality ("tin X khiến giá giảm"), forecasts or buy/sell language. Price-explainer treats "no news" as a money-flow signal even for an unknown ticker such as `ZZZ` (member 5). The `plugin.json` example "VHM 15/05" returns 0 news.
- S9 Docs drift: `%USERPROFILE%` used inside PowerShell blocks; `news-sentiment-pulse/SKILL.md:30` points at the non-windowed `urgent` command; `rules/AGENTS.md` requires `intent_source` BOTH/LLM_ONLY values the data does not carry; `status` reports 1,062 articles (latest partition) instead of the total.
- S10 Performance: buzz 27 s, window 18 s, pulse 10 s on the OneDrive sandbox (member 2).
- No current test covers C1-C3 or S1-S6 (member 4).

### Skill-level consensus

| Current skill | Verdict | Members |
|---|---|---|
| ticker-timeline, catalyst-tracker, ticker-screener, macro-timeline | Merge into one timeline skill (`--keywords` for catalysts) | 1, 6 |
| sector-impact, geo-link | Merge into one cooccur skill | 6 (3 keeps geo-link but notes empty output) |
| buzz-radar, theme-trend | Merge "what is hot" (2 proposes folding buzz into daily-brief) | 2, 6 |
| sentiment-pulse | Keep after C1-C3 | 2, 4 |
| price-explainer | Keep, remove causal wording, add session cut-off | 2, 5 |
| daily-brief | Keep; add cut-off time, overnight international, foreign flows, today's calendar | 1, 2, 3 |
| lakehouse-explorer | Not an analyst skill; Quant tool documented in README | 6 |

### New skills proposed (not yet prioritized against fixes)

- Fundamental: `news-corporate-actions` (dividends, issuance, AGM, insider trades; zero-token title rules), `news-earnings-season`, `news-peer-compare` (multi-ticker target returns 0 stories today).
- Market: intraday alert, confirm-vs-rumor, lead-lag (needs price data, outside news-only scope).
- Macro: `news-policy-digest`, `news-event-calendar`, `news-theme-compare`.
- Member 6 dissents: no new skills or lenses until usage logs exist.

## Options

| Option | Benefit | Cost or risk |
|---|---|---|
| A. Fix the measurement layer (C1-C5, S1-S6 with regression tests), then fold 12 skills into about 6; new skills wait for usage evidence | Analysts get numbers that survive a check; fewer names to remember; small surface to maintain | One more story before wider rollout; renaming skills changes the prompts analysts learned |
| B. Fix C1-C5 only and keep 12 skills | Fastest path to safe numbers | Overlapping triggers stay (member 5 matrix); maintenance across 12 SKILL.md files |
| C. Add new skills now (corporate actions, policy digest, event calendar) | Covers use cases analysts asked about | Builds on lenses that currently mislead; widens scope the operator twice asked to reduce |

## Recommendation

- Option A, in this order:
  1. **P0 measurement:** a single `enriched` predicate (summary present) applied by every sentiment, urgency, buzz and theme lens. `is_hot` = `urgent` only. Share-of-voice normalization and a baseline start date after which daily volume is stable; density flags that turn false when they should.
  2. **P0 safety and install:** allowlist SQL (single SELECT over `articles`/`entities` views, no table functions) instead of a blocklist; installer pins an interpreter that has duckdb and self-tests the import.
  3. **P1 correctness:** listed-ticker whitelist and stoplist, accent-insensitive matching, buzz minimum count, lift denominator over entity-bearing articles with minimum support, session cut-off at 14:45 and trading-day baselines, `max-stories` keeps the newest.
  4. **P1 wording:** remove causal, forecast and recommendation language from SKILL.md files; "no news" is reported as absence, never as a signal; fix S9 drift and the `plugin.json` example.
  5. **P2 consolidation:** fold into about six skills (timeline, explain-session, what-is-hot, sentiment, who-is-affected, morning brief) with Vietnamese trigger phrases. Then pick at most one new skill (`news-corporate-actions` had the strongest case) after collecting golden questions from each desk.

## Outcome

- Pending operator decision.
- Process note: while testing C4 the red-team member read `C:\Windows\win.ini` and listed three file names in the operator's `Documents` folder, outside its assigned scratch folder (read-only, nothing written); recorded in position 5.
