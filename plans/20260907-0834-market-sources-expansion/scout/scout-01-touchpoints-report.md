# Scout 01 -- Touchpoint checklist: onboarding a new full-capture source (vneconomy pattern)

Scope: everything BEYOND what is already known (config/domains/<name>.yaml, capture_mixin,
vneconomy/tnck scraper, REGISTRY, docs/dev/03, docs/design/03/06/07). Facts only, file:line refs.

## (a) Create/modify checklist

| File | Action | Why |
|---|---|---|
| `config/domains/<name>.yaml` | create | (already known) |
| `src/scrapers/<name>.py` | create | (already known) |
| `src/scrapers/__init__.py` | modify (add import) | (already known) -- registers `@register` |
| `tests/test_<name>.py` | create | unit tests, `FakeHTTP` -- see (1) |
| `tests/fixtures/<name>_*.xml` / `_detail_page.html` | create | fixture bytes for test |
| `domains/<name>/schema.yaml` | create (optional but expected) | monitor field-health contract -- see (2)/(7). NOT auto-generated, NOT in docs/dev/03 |
| `domains/<name>/README.md`, `changelog.md`, `fixtures/` | create (optional, mirrors cafef/vietstock) | same monitor-doc convention |
| `docs/domains/README.md` (matrix table + counts) | modify | line 3 "23 domain", table rows 10-32, line 34 stats, line 38-41 group links |
| `docs/domains/vn-rss.md` or `api-scrapers.md` (per method) | modify | per-domain quirk section |
| `docs/skills/rss-sources.md` | modify | table row + notes (if RSS) |
| `README.md` | modify | lines 35,44,61-62,77,115,117,127-130 (counts, examples, roadmap) |
| `docs/architecture.md` | modify | line 67 example list (if illustrative) |
| `scripts/sample_articles.py` | modify (optional) | `GROUPS[...]["domains"]` lists lines 56,60,65-67,72 -- else falls into "ungrouped" bucket of `03-vn-press-rss` automatically (line 237,243) -- NOT required, cosmetic grouping only |
| `scripts/validate_capture.py` | modify (optional, dev-only) | hardcoded `sources=["cafef","vietstock"]` (line 100) + per-name special-case (line 37) -- this script is scoped to just those 2 sources; extending it is optional, not required for onboarding |
| everything else in scripts/, orchestrator, pipeline | NO CHANGE NEEDED | fully generic -- see (3)(4) |

## (b) Per-question findings

### 1. Test template (tests/test_vneconomy.py, tests/_fakes.py)
- Structure: `tests/test_vneconomy.py:1-103`. Fixtures: `feed_bytes` (reads `tests/fixtures/vneconomy_capture_feed.xml`, L21-23), `detail_html` (reads `tests/fixtures/vneconomy_detail_page.html`, L26-28), `env` (L31-37).
- `env` fixture: `monkeypatch.chdir(tmp_path)` -- isolates `RawStore` writes to `data/raw_html` under tmp (comment "co lap RawStore ghi data/raw_html vao tmp", L32-33). Builds fresh `ArticleStore`/`DedupCache` in tmp, yields dedup, closes on teardown.
- `_config(**over)` helper (L40-50) builds minimal domain-config dict (name/enabled/timeout/language/rss/detail/watchlist) -- a new source test should copy this pattern.
- Required test coverage seen: `test_registered` (REGISTRY has name to class mapping, L53-55), `test_capture_happy_path` (capture_status ok, source_domain, published_at tz suffix, language, byte-exact html vs `Path(html_path).read_text()==detail_html`, content_html/content_text non-empty, image manifest resolved_url contains CDN host, L58-79), `test_tickers_tagged` (symbols tagging via watchlist, L82-87), `test_detail_failure_keeps_summary` (detail_html=None leads to capture_status "failed", content_text falls back to summary, error message contains "detail fetch failed", `scraper.backoff=None` disables sleep, L89-98).
- `FakeHTTP` (`tests/_fakes.py:26-63`): mocks `get_json`/`get`/`get_bytes`/`get_response` (increments `detail_calls`)/`rotate_proxy`/`set_proxy_pool`. `get_response` returns `None` if `detail_html is None and detail_status<400` (simulates fetch fail) else returns `FakeResponse`. `FakeResponse` (L12-23) mimics `requests.Response` (status_code/ok/content/text/headers/encoding), accepts str or bytes as text.

### 2. Orchestrator wiring (src/orchestrator.py, src/core/config.py)
- Fully automatic glob, no hardcoded list: `list_domains()` at `src/core/config.py:84-93` does `DOMAINS_DIR.glob("*.yaml")`, sorted, filters `enabled` if `enabled_only=True` (default). `Orchestrator.run_cycle` calls `names = names or list_domains()` (`src/orchestrator.py:87`).
- `enabled:` honored twice: once by `list_domains(enabled_only=True)` default filter (`config.py:91`), and again per-name inside the cycle loop `if not cfg.get("enabled", True): ... skip` (`orchestrator.py:103-105`) -- belt-and-suspenders (matters if names passed explicitly bypassing list_domains filter, e.g. CLI `--once <name>`).
- `method:` to REGISTRY mapping: `build_scraper()` (`orchestrator.py:52-57`) -- `REGISTRY.get(cfg["name"]) or REGISTRY.get(f"_{cfg['method']}")`. Per-name class (e.g. "vneconomy") takes priority over a generic `_<method>` class (e.g. "_rss" -> generic RSSScraper). Raises `KeyError` if neither found.
- `language`/sentiment gating is NOT applied in orchestrator.py run_cycle -- classify (categories) runs unconditionally (`orchestrator.py:127-129`) but sentiment analysis is currently COMMENTED OUT entirely in the hot path (`orchestrator.py:124-126`: "Sentiment rule-based (VN lexicon) da go khoi workflow giai doan nay"). Sentiment engine still exists at `src/processor/sentiment.py` and is exercised only in `scripts/sample_articles.py:_nlp_apply` (L156-165) which gates on `a.metadata.get("language","vi")=="vi"` -- EN articles get forced neutral. So for onboarding: setting `language: en` in YAML is what future sentiment-gating (if re-enabled) or `sample_articles.py` will honor; no orchestrator change needed.
- No hardcoded domain-name list anywhere in orchestrator.py or config.py.

### 3. Downstream Bronze to Silver wiring
- `src/pipeline/run.py` (`process_meta`, L36-107): fully generic. No domain names/selector maps. Reads `meta["html_path"]`, calls `SilverBuilder().build(meta, raw_bytes)`, `fingerprint`, `classify`, `WorkPackageBuilder`, `Catalog.enqueue`. Domain enters only as data (`silver["domain"]`).
- `src/pipeline/silver_builder.py`: fully generic. `_domain_of()` (L43-54) derives domain from Bronze path segment after `raw_html/` or fallback to URL netloc -- no name list. `_detect_lang()` (L30-40) is a heuristic (VN diacritics / EN stopwords), not a domain lookup.
- `src/pipeline/derive.py` (`rederive_incremental`): fully generic, watermark-based scan of `data/raw_html/**/*.meta.json` (`iter_meta_paths`, L41-46), no domain names.
- `src/pipeline/refresh.py`: fully generic; `domains` param (L26, L70) is an optional SQL `IN (...)` filter list supplied by caller, not hardcoded.
- `scripts/rederive_from_bronze.py`: fully generic; `domain`/`date` are CLI args used as path segments (`RAW_DIR / domain`, L30-32), no hardcoded names -- docstring examples just show `cafef.vn` as an example value (L9-10).
- Conclusion: NONE of item 3 requires modification for a new source.

### 4. Scripts/subsystems enumerating domain names (grep results)
- `scripts/sample_articles.py:56,60,65-67,72` -- `GROUPS[...]["domains"]` lists (see checklist). New domain not listed auto-falls into `03-vn-press-rss` group via `ungrouped` (L235-237,243) -- cosmetic only.
- `scripts/validate_capture.py:37,100,103` -- hardcoded to cafef+vietstock only (dev audit script, not generic, not required to touch).
- `scripts/diagnose_sources.py:7,89` -- docstring example + comment only; `diagnose()` itself is generic (`list_domains()` default, `orchestrator.py`-style build_scraper).
- `scripts/domain_check.py:6,8,238` -- docstring examples only; logic generic (reads `domains/*/schema.yaml` dir listing).
- `scripts/export_csv.py:9,34` -- docstring/help text only; `--domain` filter is free-form list of source_domain values.
- `scripts/run_once.py:6` -- docstring example only.
- `src/monitor/domain_reporter.py:10` -- docstring example; logic generic, reads `domains/<domain>/schema.yaml` if present else `schema=None` and skips field-health section gracefully.
- `src/monitor/domain_validator.py:13,194` -- docstring example + comment; logic generic.
- No hardcoded domain literals found in `src/notifier/`, `src/handoff/`, `src/export/`, `src/users/`, `config/` (only settings/watchlist/entities, none domain-name-keyed).
- Net finding: zero REQUIRED script changes. All hits are either docstrings/comments or the two optional/cosmetic cases above (sample_articles GROUPS, validate_capture sources list).

### 5. Docs carrying a source matrix
- `docs/domains/README.md:3` (total count "23 domain (22 enabled + 1 disabled)"), `:8-32` (main table, 1 row per domain), `:34` (vi/en stats + filter list), `:38-41` (links to per-group docs), `:43-50` (watchlist section -- NOT domain-specific, skip).
- `docs/domains/vn-rss.md:3` (count "11 nguon (10 enabled + baodautu disabled) + vietstock/vnexpress/vneconomy"), per-domain `### <name> -- <file>.yaml` sections (e.g. L9, L20).
- `docs/domains/api-scrapers.md` -- only relevant if new source is API-method (title L1, table L8-10 lists the 4 API sources + per-domain `## <name>` sections).
- `docs/skills/rss-sources.md:29,32` -- table rows per RSS domain (skip if API-method).
- `README.md:35` (usage example), `:44` (verify_quality example), `:61-62` (dir listing comment), `:77` (skills dir comment), `:115,117` (API/RSS domain-count summary lines), `:127-130` (roadmap/phase table -- historical, likely no touch needed for routine addition).
- `docs/architecture.md:67` -- illustrative example list only, likely no touch needed.

### 6. Entities/watchlist -- registration needed?
No. `config/watchlist.yaml` (30 tickers) is a flat ticker list, no domain association -- used by `src/core/tickers.py:tag_tickers()` (generic regex+stoplist match against any text, `src/core/tickers.py:11-33`) and by API scrapers doing per-symbol fetch (cafef/fireant per docs). `config/entities/manifest.yaml` is a DEV switch for END-USER subscription filtering (`users/<name>.yaml`), unrelated to news sources. `config/entities/aliases/` holds `assets.yaml, industries.yaml, institutions.yaml, macro_geo.yaml, nations.yaml, themes.yaml, tickers.yaml` -- content/entity taxonomy for NLP tagging across ALL sources, not per-source config. Adding a new source does not require touching any of these; ticker tagging works automatically against whatever content_text/title the new scraper produces.

### 7. Quality/verification tooling -- domain name vs host argument
| Script | Arg expected | Evidence |
|---|---|---|
| `scripts/verify_quality.py` | full source_domain (host, e.g. `cafef.vn`) | `WHERE source_domain = ?` direct match, `verify_quality.py:26-32`; README usage `verify_quality.py cafef.vn` |
| `scripts/domain_check.py` (cmd_validate/report/raw_check) | config name (e.g. `cafef`), bare | `cmd_raw_check`/`cmd_report` pass name straight to `load_domain_config`/`generate_report`; BUT `cmd_validate` (`domain_check.py:152`) does `source_domain = f"{dom}.vn" if "." not in dom else dom` -- hardcodes `.vn` suffix, will break for non-`.vn` / already-dotted names unless passed as `name.tld` explicitly |
| `src/monitor/domain_reporter.py` | config name; internally same `.vn`-suffix hack (`domain_reporter.py:126,170`) | same gotcha as above |
| `scripts/diagnose_sources.py` | config name (matches `config/domains/*.yaml` stem) | `load_domain_config(name)` |
| `scripts/validate_capture.py` | config name, but hardcoded to `cafef`/`vietstock` only | see (4) |

## (c) Gotchas
- `domain_check.py:152` and `domain_reporter.py:126,170` assume source_domain == "<name>.vn" when name has no dot. A new source whose host is not `.vn` (e.g. an English/international source, or one where config `name` != host stem) will silently query the WRONG source_domain and report 0 articles / false anomalies. Must pass full dotted host explicitly as the CLI arg in that case, or the field-health/report tooling needs a fix.
- `domains/<name>/schema.yaml` (separate top-level `domains/` dir, NOT `config/domains/`) currently only exists for `cafef` and `vietstock`. It is optional (code degrades gracefully -- `domain_reporter._load_schema` returns `None`, `domain_check.cmd_list` just will not list it) but IS what unlocks field-health/anomaly reporting and `--raw-check` schema diff. This is undocumented in `docs/dev/03-adding-a-source.md`.
- `docs/dev/03-adding-a-source.md:119` only says to update docs/domains/ + matrix table -- does not enumerate `docs/skills/rss-sources.md`, `README.md` counts, or the `domains/<name>/schema.yaml` contract. Checklist there is incomplete vs what is actually cross-referenced in the repo.
- Sentiment gating by `language` is currently dead code in the hot path (commented out in orchestrator) -- only exercised in `scripts/sample_articles.py`. Do not assume live sentiment scoring happens per-cycle for a new vi-language source today.

## (d) Unresolved questions
- Should `domains/<name>/schema.yaml` (+ README/changelog/fixtures) be MANDATORY for every new source, or only for sources getting active monitoring? Only 2 of 23 domains have it today -- unclear if it is a stalled initiative or intentionally selective.
- Is the `.vn`-suffix hack in `domain_check.py`/`domain_reporter.py` a known limitation, or should it be fixed as part of this source-expansion work (esp. if new sources are non-`.vn`)?
- Confirm with maintainer whether `scripts/sample_articles.py` GROUPS and `scripts/validate_capture.py` source lists should be treated as required or genuinely optional/dev-convenience for this PR acceptance criteria.
