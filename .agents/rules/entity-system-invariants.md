# Entity System & User Mapping Invariants

## 1. Master Catalog Invariants (`project/data/entities/entities.xlsx`)
- **Discrete Multi-sheet Architecture:** Always maintain distinct sheets:
  - `_Huong_dan`: Guide on how users pick `code` values for subscription.
  - `_Index`: Statistics and summary table across all entity types.
  - `Securities`: TICKER, ETF, SECURITY_OTHER.
  - `Industries`: GICS Level 1, 2, 3 (e.g. `QUY`, `THEP`, `NGAN_HANG`).
  - `Indices`: Market indices (`VNINDEX`, `VN30`...).
  - `Exchanges`: Trading floors (`HOSE`, `HNX`, `UPCOM`).
  - `Nations`: Geopolitics & Economic regions (`MY`, `TRUNG_QUOC`, `EU`, `NHAT_BAN`, `NGA`, `HAN_QUOC`...).
  - `Themes`: Macro themes (`LAI_SUAT`, `TY_GIA`, `LAM_PHAT`, `DAU_TU_CONG`, `FDI`, `TIN_DUNG`...).
  - `Assets`: Asset classes & Commodities (`TRAI_PHIEU`, `CO_PHIEU`, `VANG`, `DAU_THO`, `TIEN_MA_HOA`...).
  - `Institutions`: Central banks & Regulators (`NHNN`, `UBCKNN`, `BO_TAI_CHINH`, `FED`, `ECB`, `BOJ`, `WB_IMF`...).
- Every entity must have a unique `entity_id` (e.g. `TICKER:HPG`, `IND_GICS2:QUY`, `MACRO_GEO:MY`, `ASSET_CLASS:TRAI_PHIEU`).
- Code must be normalized uppercase without diacritics.

## 2. Matcher & Short-words Invariants (`project/src/agent/entities.py`)
- **No Crude Length Filtering:** Do NOT use blunt length filters `len(alias) >= 4` that skip critical financial terms like "Quỹ", "Mỹ", "Fed", "Vàng", "Dầu", "CPI", "GDP".
- **Whitelist Protected Short Words:** Short words with domain importance MUST be whitelisted in `PROTECTED_SHORT_WORDS`.
- **Word Boundary Regex:** All alias matching MUST use Word Boundary Regex `\b<alias>\b` on diacritics-folded text (`_fold()`) to eliminate false positives (e.g., "quyết định" must NOT match "quy", "mỹ thuật" must NOT match "mỹ").
- **Multi-ID Preservation:** `_alias_index` must always map an alias string to a `list[entity_id]` to preserve hierarchical industry mappings (e.g., GICS2 & GICS3 both receiving matches).

## 3. User Input & Pipeline Invariants (`project/src/users/compile.py`, `project/src/export/user_output.py`)
- **User Subscription Contract:** Users subscribe by picking `code` values from `entities.xlsx` and entering them in `users/input/<Name>/entities.xlsx`.
- **Valid Subscription Columns:** `tickers`, `etfs`, `indices`, `exchanges`, `industries`, `nations`, `themes`, `macro` (alias), `assets`, `institutions`, `entities`.
- **Graceful Validation:** Unknown codes must be isolated into `_unknown.txt` without crashing the compile pipeline.
- **Noise Filtering:** Broad macro/asset entities (`MACRO_GEO`, `MACRO_THEME`, `ASSET_CLASS`) only route to users if an alias is present in the title. The filter MUST NOT read any Gold field — the export gate is L1-only, so a not-yet-scored article would always be treated as score 0 and the relaxed gate would only half work.
- **Export Gate:** `final.csv` requires `l1_outputs.dod_pass=1` ONLY (routing needs L1 entities). `agent_outputs.dod_pass=1` is optional enrichment; when absent the Gold columns are empty strings and `gold_status=L1_ONLY`.
