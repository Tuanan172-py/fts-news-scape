# Phase 04 — Quality Layer: Sentiment, Fuzzy Dedup, Retry, Monitoring, Notify

## Context Links
- Parent plan: [plan.md](plan.md)
- Depends on: [phase-01-foundation-refactor.md](phase-01-foundation-refactor.md) only (parallelizable with Phase 3)
- Spec: `docs/system-prompt.md` §9 (sentiment rule-based), §4.3 (stability/quality metrics), §13 Sprint 3
- Scout audit: GAP #4 (retry), #5 (sentiment MISSING), #6 (monitoring), #7 (notify); TDR-003 layer-2 fuzzy dedup broken (`is_similar_title()` always False)
- Research: [research/researcher-02-ops-sentiment-report.md](research/researcher-02-ops-sentiment-report.md) §3 (heartbeat), §4 (VSWN + underthesea + negation)

## Overview
- **Date:** 2026-07-24
- **Description:** Rule-based Vietnamese sentiment engine (lexicon + negation + finance terms), fix broken layer-2 fuzzy dedup, formalize retry/fallback via tenacity, SQLite heartbeat/metrics monitoring with health-check CLI, file/stdout notify module.
- **Priority:** Critical (sentiment is spec-required Phase 1 blocker per audit)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights
- Sentiment: NO LLM (spec hard constraint). Stack: word segmentation (`underthesea.word_tokenize`, fallback `pyvi` if underthesea install fails on Windows) → VietSentiWordNet polarity lexicon → finance-term overlay (domain words override generic: `tăng trần +1.0`, `giảm sàn -1.0`, `lãi +0.8`, `lỗ -0.8`, `phá sản -1.0`, `cổ tức +0.6`, `thoái vốn -0.3`, `kỷ lục +0.7`, `xử phạt -0.6`, `truy thu -0.6`, `khởi tố -0.9`, `vượt kế hoạch +0.8`, `đi lùi -0.5`...) → negation flip on `không|chưa|không_phải|giảm bớt` preceding token → mean score → thresholds `>0.2 pos / <-0.2 neg / else neutral`.
- Title weighted 2× vs body (financial headlines carry the signal); body sampled first 100 tokens for speed.
- Fuzzy dedup broken because JSON cache stored only hashes — Phase 1 already added `title_norm` column to `seen_articles`; fix = query recent titles (48h window) + `rapidfuzz.fuzz.token_set_ratio ≥ 90`, cross-domain only (same-domain handled by hash layer). rapidfuzz chosen over difflib: C-speed, handles word order (VN news reprints shuffle clauses).
- Retry currently split: urllib3 Retry in HTTPClient (transport-level) — keep; add tenacity at scraper-operation level (whole fetch_list attempt, 3 tries, exp backoff 2–30s) + method fallback chain from domain YAML (`method` → `fallback`, e.g. vietstock api→rss).
- Monitoring = SQLite tables (no external infra): `scraper_heartbeat` + `scraper_metrics` per research-02 §3; health CLI reads them.
- Notify Phase 1 = file/stdout ONLY (spec §11): match rules from `config/notifications.yaml`, append to daily log; Telegram explicitly out of scope.

## Requirements
1. `SentimentEngine.analyze(title, text) -> (label, score)`; fills `articles.sentiment` + `sentiment_score` in pipeline.
2. Lexicon files under `data/lexicon/` (VSWN subset TSV + `finance_terms.tsv` hand-curated ~150 entries); loading cached at startup.
3. Validation set: 50 hand-labeled real headlines (pull from DB after Phase 2/3) → accuracy target ≥70% Phase 1 (rule-based ceiling; document).
4. Fuzzy dedup: `is_similar_title()` actually works; unit-tested with real reprint pairs (e.g. same story on Vietstock ch.733 vs TNCK).
5. Retry: any scraper transient failure → 3 attempts exp backoff; primary method exhausted → fallback method if configured; final failure → heartbeat `failed` + notify, cycle continues (graceful degradation).
6. Heartbeat updated per scraper per cycle; metrics row per scraper per cycle (articles_fetched, new, errors, duration_ms).
7. `python -m src.monitor.health` prints per-scraper status table; exit code 1 if any scraper stale >30 min or 3 consecutive fails.
8. Notify module: rule match (keyword any-list from notifications.yaml) → line in `data/notifications/YYYY-MM-DD.log` + stdout; summary line per cycle.

## Architecture
```
src/processor/sentiment.py      # SentimentEngine
src/db/dedup.py                 # + is_similar_title() fixed (rapidfuzz)
src/core/retry.py               # tenacity policies + run_with_fallback(scraper)
src/monitor/__init__.py
src/monitor/heartbeat.py        # record_start/record_result(scraper, status, err, metrics)
src/monitor/health.py           # CLI health check
src/notifier/__init__.py
src/notifier/file_notify.py     # FileNotifier.notify(articles), rules from notifications.yaml
data/lexicon/vswn_polarity.tsv  # word<TAB>score
data/lexicon/finance_terms.tsv  # phrase<TAB>score (overrides vswn)
```
**Sentiment core:**
```python
class SentimentEngine:
    NEGATIONS = {"không", "chưa", "không_phải", "chẳng"}
    def __init__(self, lexicon_dir="data/lexicon"): ...  # dict phrase→score, finance overrides generic
    def score_tokens(self, tokens: list[str]) -> float:
        scores = []
        for i, tok in enumerate(tokens):
            s = self.lex.get(tok.lower())
            if s is None: continue
            if i > 0 and tokens[i-1].lower() in self.NEGATIONS: s = -s
            scores.append(s)
        return sum(scores) / len(scores) if scores else 0.0
    def analyze(self, title, text) -> tuple[str, float]:
        score = 0.67 * self.score_tokens(seg(title)) + 0.33 * self.score_tokens(seg(text)[:100])
        return ("positive" if score > 0.2 else "negative" if score < -0.2 else "neutral", round(score, 3))
```
Multi-word finance phrases: match on segmented compound tokens (underthesea joins by `_`, e.g. `tăng_trần`) + bigram scan fallback.
**DDL (added to store.init_schema):** `scraper_heartbeat(scraper_name PK, last_run_ts, status, error_msg, consecutive_failures, cycle_count)`; `scraper_metrics(ts, scraper_name, articles_fetched, articles_new, errors, duration_ms)`.
**Retry wrapper:**
```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30),
       retry=retry_if_exception_type(TransientError), reraise=True)
def _attempt(scraper): return scraper.run()
def run_with_fallback(scraper, fallback_scraper=None):  # fallback built from yaml `fallback` method
```

## Related Code Files
**Create:** `src/processor/sentiment.py`, `src/core/retry.py`, `src/monitor/heartbeat.py`, `src/monitor/health.py`, `src/notifier/file_notify.py`, `data/lexicon/vswn_polarity.tsv`, `data/lexicon/finance_terms.tsv`, `scripts/fetch_lexicon.py` (download/convert VSWN if not bundled), `tests/test_sentiment.py`, `tests/test_fuzzy_dedup.py`, `tests/test_heartbeat.py`, `tests/test_notify.py`, `data/labeled/sentiment_validation.csv` (50 rows)
**Modify:** `src/db/dedup.py` (fix `is_similar_title` + rapidfuzz), `src/db/store.py` (heartbeat/metrics DDL), `src/processor/pipeline.py` (sentiment step after classify, before enqueue), `config/notifications.yaml` (file-based rules only, drop telegram), `requirements.txt` (+underthesea OR pyvi, rapidfuzz), `src/core/base_scraper.py` (raise `TransientError` vs `PermanentError` distinction from fetch layer)
**Delete:** none

## Implementation Steps
1. Lexicon acquisition: `scripts/fetch_lexicon.py` — download VietSentiWordNet source (verify license; if download unstable → curate top ~2000 polarity words into bundled TSV, cite source in file header). Hand-write `finance_terms.tsv` (~150 phrases) using headlines in `thamkhao/present/docs_vietstock/Discovered Channels.md` as vocabulary source.
2. Try `pip install underthesea` on Windows; if build pain → `pyvi` (`ViTokenizer.tokenize`). Wrap behind `src/processor/segment.py::seg(text)` so engine is tokenizer-agnostic.
3. Implement `SentimentEngine` per pseudocode; phrase matching on `_`-joined compounds + bigram fallback.
4. Build validation CSV: 50 headlines from live DB, hand-label pos/neg/neutral. `tests/test_sentiment.py`: unit cases (`"lãi kỷ lục"`→pos, `"không tăng"`→not-pos flip, `"bị xử phạt và truy thu thuế"`→neg, empty text→neutral) + accuracy assert ≥0.70 on validation CSV.
5. Wire into `pipeline.py`: `article.sentiment, article.sentiment_score = engine.analyze(...)` — engine instantiated once, injected.
6. Fix fuzzy dedup: `DedupCache.is_similar_title(title, source_domain)` → SELECT title_norm, source_domain FROM seen_articles WHERE seen_at > now-48h AND source_domain != ? → `rapidfuzz.fuzz.token_set_ratio(norm(title), t) >= 90` → duplicate. Called in BaseScraper.run() after hash check. Config flag `dedup.fuzzy_enabled` + threshold in settings.yaml. Tests with 3 real reprint pairs + 2 near-miss non-dupes.
7. `src/core/retry.py`: define `TransientError` (timeouts, 429, 5xx, ConnectionError) vs `PermanentError` (401/403/404, parse schema break); tenacity policy; `run_with_fallback()` consults domain yaml `fallback` (e.g. vietstock: api→rss builds RSSScraper for that domain — actual fallback pairs configured in Phase 5/6).
8. `src/monitor/heartbeat.py`: `record_start(name)`, `record_result(name, status, error_msg, metrics)` — writes via DBWriter queue (single-writer preserved); increments `consecutive_failures` or resets.
9. `src/monitor/health.py`: `python -m src.monitor.health` → table: scraper | last_run | status | consec_fails | articles_24h; rules: stale>30min→STALE, consec_fails>=3→CRITICAL; exit 1 on any non-OK.
10. `src/notifier/file_notify.py`: load notifications.yaml rules (`match.any` keywords over title+symbols); matched → formatted line to `data/notifications/YYYY-MM-DD.log` + stdout; plus per-cycle summary (`[cycle] cafef: 12 new, vietstock: FAILED (...)`). Health CRITICAL states also routed here.
11. Update `config/notifications.yaml`: watchlist-keyword rule + `match: true → file` default; remove telegram IDs.
12. Full test pass + live cycle: force one scraper failure (bad endpoint) → verify retry×3, heartbeat `failed`, notify line, other scrapers unaffected.

## Todo List
- [ ] fetch_lexicon.py + vswn_polarity.tsv + finance_terms.tsv (~150)
- [ ] segment.py tokenizer wrapper (underthesea/pyvi decision)
- [ ] SentimentEngine + negation + phrase matching
- [ ] 50-row validation set, accuracy ≥70%
- [ ] Pipeline wiring (sentiment fields persisted)
- [ ] Fuzzy dedup fix (rapidfuzz, 48h window, cross-domain) + tests
- [ ] retry.py: Transient/Permanent + tenacity + fallback runner
- [ ] heartbeat.py + DDL + wiring in scraper run path
- [ ] health.py CLI (exit codes)
- [ ] file_notify.py + notifications.yaml rewrite
- [ ] Failure-injection live test

## Success Criteria
- Every new article gets sentiment label + score; ≥70% accuracy on validation set.
- Known reprint pair deduped cross-domain; non-dupes not falsely merged (0 false-positive on test set).
- Injected scraper failure: 3 retries logged, heartbeat=failed, notify line written, cycle completes for other scrapers.
- `python -m src.monitor.health` correct statuses + exit codes.
- No Telegram/Hermes path in notify.

## Risk Assessment
- **Rule-based sentiment ceiling:** finance sarcasm/context missed — accepted per spec ("làm tốt nhất có thể với rule engine"); document known-miss examples for Phase 2 LLM upgrade.
- **underthesea Windows install (torch deps):** pyvi fallback pre-planned via segment.py seam.
- **Fuzzy false positives** (e.g. daily "Phân tích kỹ thuật phiên chiều DD/MM" series titles differ only by date): normalize strips dates? No — dates distinguish them; token_set_ratio on date-differing titles scores <90; add these exact series titles to non-dupe test set to prove.
- **VSWN availability/license:** fallback = self-curated lexicon; flag in plan.md unresolved Q6.

## Security Considerations
- Lexicon/validation files are data-only; no code execution from TSV (parse strictly, ignore malformed lines).
- Notify log may aggregate market-sensitive digests — stays local file, no network egress.
- Health CLI read-only DB access.

## Next Steps
Phase 5 RSS layer (uses retry/monitor/notify plumbing from this phase).
