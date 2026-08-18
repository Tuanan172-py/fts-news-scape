# Scout 02 — Entities / Excel config internals

## EntityRegistry.select(doc) (project/src/agent/entities.py:94-119)
Accepted doc keys (all optional): `tickers`(alias `stocks`), `etfs`, `indices`, `exchanges`, `sectors`(FPA codes), `industries`(canonical names), `entities`(raw entity_id escape hatch).
Returns `(set[entity_id], list[(category, value)] unknown)`.
`_CATEGORY_TYPES` L42: tickers→(TICKER,SECURITY_OTHER,ETF); etfs→(ETF,SECURITY_OTHER); indices→(INDEX,); exchanges→(EXCHANGE,). industries→match fold-normalized name. sectors→`_sector_id_by_code`.
`load_registry()` L180 `@lru_cache(maxsize=1)`. `subscribers_for(entity_ids)→set[user]` L124. `resolve_subscription(name)→set[entity_id]` L121. `_load_subscriptions()` L165 globs `USERS_DIR/*.yaml`, stem=username.

## Canonical user yaml (config/entities/users/*.yaml) — compile target
```yaml
tickers:    [HPG, FPT, ...]       # optional
etfs:       [E1VFVN30]            # optional
indices:    [VNINDEX, VN30]       # optional
exchanges:  [HOSE, HNX]           # optional
industries: ["Thép", "Ngân hàng"] # optional (canonical name)
sectors:    [Chungkhoan, Thep]    # optional (FPA code)
entities:   [TICKER:HPG]          # optional (raw id)
```

## entities.xlsx source (scripts/build_entities.py) — lookup source for template dropdowns
Multi-sheet: `_Index`, `Securities`(entity_id,type,code,canonical_name,short_name,gics1-3,...), `Industries`(entity_id,level,code,name,parent,ticker_count), `Sectors_FPA`(entity_id,code,name,available_in_apd), `Indices`, `Exchanges`. AutoFilter + freeze header.
Entity counts: TICKER 1981, ETF 28, SECURITY_OTHER 11, INDEX 6, EXCHANGE 3, INDUSTRY_* 90, SECTOR_FPA 16 (total 2135). entities.json schema entity_id=`TYPE:CODE`.

## User-facing xlsx template design
Columns = select() keys: `tickers | etfs | indices | exchanges | industries | sectors | entities` (each column a vertical list, 1 entity/row). Dropdowns sourced from entities.xlsx Securities/Industries/Exchanges/Sectors sheets. Add a `meta` sheet or top rows for `user` name + `enabled`.

## Deps for xlsx (project/requirements.txt + .venv)
openpyxl 3.1.5 ✓ and pandas ✓ both present. build_entities.py already uses pandas.read_excel. Use pandas.read_excel (openpyxl backend) to parse; openpyxl for template w/ data-validation dropdowns.

## L1 "done" semantics (l1_classifier.py:38-92 / l1_router.py:94-149)
route `resolved` = code-first matched ≥1 entity; `needs_agent` = 0 matches → handoff. DoD pass = schema+grounding+consistency+category coherence+confidence≥0.60+metadata. Gate uses l1_outputs.dod_pass=1 (agent-reviewed) OR route=resolved (code-first) — DECIDE which counts as "L1 done" for output gate.

## Enabled/disabled user
GREENFIELD. Domain config has `enabled:` but users don't. Options: (a) presence of users/input/<name>/ folder = enabled; (b) `enabled: true/false` cell in xlsx meta; recommend folder-presence + optional override cell.

## Unresolved
- Per-ticker exchange not in data (only 3 generic EXCHANGE) — exchanges col is coarse.
- Does output gate require agent-reviewed L1 (dod_pass) or is code-first `resolved` sufficient? Impacts throughput.
