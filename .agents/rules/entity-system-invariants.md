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
- **Morphological & Compound Boundary Guard (`_blocked_by_morphology`):**
  - For single-word geopolitical/macro aliases (e.g., `MY` for Nước Mỹ, `NGA` for Nước Nga), regex boundary `\b<alias>\b` is insufficient in Vietnamese because proper noun compounds (e.g. *"Mỹ Thuận"*, *"Mỹ Tho"*, *"Á Mỹ"*, *"Mỹ Phước"*) or person names (*"Bà Trần Kim Nga"*, *"Nga Rose"*) are separated by spaces.
  - **Capitalized Suffix Guard**: If `MY` is followed by a capitalized token (e.g., `Thuận`, `Tho`, `Đình`, `Thủy`, `Hào`...), match is blocked unless the following token is an international whitelist term (e.g., `Trump`, `Biden`, `Fed`, `Wall`, `Street`, `Trung Quốc`).
  - **Brand/Person Prefix Guard**: If preceded by Vietnamese brand prefixes (`Á`, `Phú`, `Phù`, `Nam`, `Bắc`) or person honorifics (`Bà`, `Ông`, `Thị`, `Văn`, `Cô`, `Chị`), match is blocked.
  - **Case-Sensitive Raw String Check**: Morphological checks MUST run on the raw text (`raw`), NOT on `_fold()` text, to prevent accent-stripping collisions (e.g., folding *"Mỹ Lâm"* to `"my lam"` would mistakenly collide with and block legitimate news like *"Mỹ làm dịu..."*).
- **Positional Disclosure Exemption Rule (`_DISCLOSURE_PREFIX_RE`):**
  - Financial disclosures (CBTT) commonly format titles as `CODE: Title` (e.g. `VND: Báo cáo tình hình quản trị...`).
  - Codes in `CODE_STOPLIST` (such as `VND`) that represent both currencies/common acronyms and legitimate tickers MUST receive an exemption when appearing at string start index 0 followed by a colon (`^([A-Z0-9]{3})\s*:`). This eliminates false negatives while preventing false positives in body/mid-title currency references (`500 tỷ VND`).
- **Domain Banking Conflict Guards (e.g. `TICKER:PGD`):**
  - Ticker codes identical to ubiquitous banking abbreviations (e.g. `PGD` for Phòng Giao Dịch) MUST be guarded against banking contexts (e.g. `thành lập PGD`, `đổi tên PGD`, `Chi nhánh/PGD`, `PGD <Tên riêng>`, or presence of bank disclosure headers `MBB:`, `TCB:`, `VCB:`...).
- **Ecosystem & Subsidiary Brand Aliasing (`tickers.yaml`):**
  - Major conglomerates drive material revenues through key subsidiaries and consumer brands not present in legal parent exchange names (`Bách Hóa Xanh` $\rightarrow$ `MWG`, `WinCommerce` $\rightarrow$ `MSN`, `FE Credit` $\rightarrow$ `VPB`, `VinFast` $\rightarrow$ `VIC`).
  - These brand aliases MUST be mapped to parent tickers in `config/entities/aliases/tickers.yaml` and merged via `refresh_aliases.py`.
- **Multi-ID Preservation:** `_alias_index` must always map an alias string to a `list[entity_id]` to preserve hierarchical industry mappings (e.g., GICS2 & GICS3 both receiving matches).

## 3. User Input & Pipeline Invariants (`project/src/users/compile.py`, `project/src/export/user_output.py`)
- **User Subscription Contract:** Users subscribe by picking `code` values from `entities.xlsx` and entering them in `users/input/<Name>/entities.xlsx`.
- **Valid Subscription Columns:** `tickers`, `etfs`, `indices`, `exchanges`, `industries`, `nations`, `themes`, `macro` (alias), `assets`, `institutions`, `entities`.
- **Graceful Validation:** Unknown codes must be isolated into `_unknown.txt` without crashing the compile pipeline.
- **Noise Filtering:** Broad macro/asset entities (`MACRO_GEO`, `MACRO_THEME`, `ASSET_CLASS`) only route to users if an alias is present in the title. The filter MUST NOT read any Gold field — the export gate is L1-only, so a not-yet-scored article would always be treated as score 0 and the relaxed gate would only half work.
- **Export Gate:** `final.csv` requires `l1_outputs.dod_pass=1` ONLY (routing needs L1 entities). `agent_outputs.dod_pass=1` is optional enrichment; when absent the Gold columns are empty strings and `gold_status=L1_ONLY`.
