# Scraping System Research Report: Ops, Sentiment, RSS Feeds
**Date**: 2026-07-24 | **Target**: Vietnamese stock-news scraper (Python 3.10+, SQLite, 15-min polling, single Windows+WSL)

---

## 1. Scheduling: APScheduler vs Windows Task Scheduler vs WSL Cron

### Findings
- **APScheduler 3.x**: Native coalescing (`coalesce=True`) + misfire grace time (`misfire_grace_time`) prevent duplicate job execution during catch-up. Singleton constraint is **natively supported** via locking mechanism in persistent job stores.
- **Windows Task Scheduler**: No built-in coalescing; multiple queued task instances may execute. Requires external singleton mutex logic.
- **WSL cron**: Lightweight; WSL can run systemd-compatible cron, but no built-in singleton constraint. Requires wrapper script with flock/lockfile.

### Recommendation
**APScheduler 3.11+** with in-memory job store + SQLite persistent backing (optional for crash recovery). Configure: `trigger=CronTrigger(minute='*/15'), coalesce=True, misfire_grace_time=300` (5 min grace window). Ensures single cycle isolation, prevents stale executions after restart.

### Citation
- [APScheduler User Guide - Coalescing & Misfires](https://apscheduler.readthedocs.io/en/3.x/userguide.html)
- [GitHub Discussion: Preventing Multiple Workers](https://github.com/agronholm/apscheduler/discussions/592)

---

## 2. SQLite Concurrency & WAL Mode

### Findings
- **WAL mode**: Enables concurrent readers + single writer (not multiple writers). One writer holds lock at any moment; writers serialize automatically.
- **check_same_thread=False** in sqlite3: Allows multi-thread access but **does NOT guarantee safety**. Writes must be serialized by application logic.
- **Python sqlite3 best practices**:
  - Use **connection-per-thread** (not shared connection). Each thread instantiates its own `sqlite3.connect()`.
  - Enable `WAL` mode: `conn.execute('PRAGMA journal_mode=WAL')`
  - Set `busy_timeout`: `conn.execute('PRAGMA busy_timeout=5000')` (5s retry on locked).
  - Use `check_same_thread=False` **only** if each thread holds its own connection.
  - Batch inserts in transactions: `BEGIN IMMEDIATE; INSERT...; COMMIT` for 3-5 threads.
  - WAL checkpointing: SQLite auto-checkpoints; manual `PRAGMA wal_checkpoint(RESTART)` for cleanup.

### Single-Writer Pattern (Recommended)
For 3-5 scraper threads: Use thread pool + **single writing thread** via `Queue`. Scrapers parse → Queue message → dedicated DB writer thread processes batch inserts. Eliminates lock contention.

### Citation
- [SQLite Forum: WAL & Threading](https://sqlite.org/forum/info/461653af585fb599)
- [Concurrent Writing Python Guide](https://www.pythontutorials.net/blog/concurrent-writing-with-sqlite3/)
- [SQLite Official Docs: WAL](https://sqlite.org/wal.html)

---

## 3. Monitoring & Health-Check (No External Infra)

### Lightweight Professional Setup

**Structured Logging**:
- Use **loguru** (not stdlib): auto-rotating files, JSON export, single-line import.
  ```python
  from loguru import logger
  logger.add("scraper.log", rotation="500 MB", format="{time} {level} {message}")
  ```

**Heartbeat Table** (SQLite):
```sql
CREATE TABLE IF NOT EXISTS scraper_heartbeat (
  scraper_name TEXT PRIMARY KEY,
  last_run_ts INTEGER,  -- unix timestamp
  status TEXT,          -- 'running', 'success', 'failed'
  error_msg TEXT,
  cycle_count INTEGER
);
```

**Health Check Query**:
```python
def check_scraper_health(scraper_name, max_gap_minutes=30):
  row = db.execute(
    "SELECT last_run_ts FROM scraper_heartbeat WHERE scraper_name=?",
    (scraper_name,)
  ).fetchone()
  if not row: return False  # Never ran
  gap = (time.time() - row[0]) / 60
  return gap <= max_gap_minutes
```

**Alerting** (N consecutive failures):
- Log to file + check on startup: if heartbeat gap > 30 min → log ERROR + optionally send email via SMTP.
- No Grafana/Prometheus needed. Simple CLI: `SELECT * FROM scraper_heartbeat WHERE status='failed' ORDER BY last_run_ts DESC LIMIT 5`

**Metrics Table** (Optional):
```sql
CREATE TABLE IF NOT EXISTS scraper_metrics (
  ts INTEGER,
  scraper_name TEXT,
  articles_fetched INTEGER,
  parse_time_ms INTEGER
);
```

### Citation
- [Loguru Documentation](https://loguru.readthedocs.io/)
- Best practice: Structured logging for single-machine ops avoids syslog complexity.

---

## 4. Vietnamese Sentiment Analysis (Rule-Based, Financial News)

### Available Lexicons

1. **VnEmoLex**: 12,795 Vietnamese words annotated for 8 emotions (joy, sadness, anger, fear, trust, disgust, surprise, anticipation). Built from NRC EmoLex + Viet Wordnet.
   - Source: [Zenodo - VnEmoLex](https://zenodo.org/records/801610)
   - **Use case**: Emotion-intensity scoring; less ideal for binary pos/neg/neutral finance.

2. **VietSentiWordNet (VSWN)**: 3-level sentiment (positive/negative/neutral). Semi-supervised framework; extended in 2025-2026.
   - Paper: "Expanding Vietnamese SentiWordNet..." (2025, arxiv:2501.08758)
   - **Use case**: Better for binary financial sentiment classification.

3. **VietSentiLex**: Polarity-focused dictionary. Lightweight alternative.
   - Paper: [ACL Anthology - VietSentiLex](https://aclanthology.org/Y18-1081.pdf)

### Word Segmentation & Negation

- **underthesea**: Python package for Vietnamese NLP. Includes word segmentation, POS tagging, but **sentiment lexicon built-in is limited**. Use for segmentation, pair with external lexicon.
- **pyvi**: Alternative segmentation tool; lighter-weight.

**Negation Handling** (Financial context):
- Simple rule: if previous token in `['không', 'chưa', 'không phải']`, flip sentiment polarity.
  ```python
  def apply_negation(tokens, sentiments):
    negation_words = {'không', 'chưa', 'không_phải'}
    for i, token in enumerate(tokens):
      if token in negation_words and i+1 < len(sentiments):
        sentiments[i+1] *= -1  # Flip next token polarity
  ```

### Financial Tone Adaptation

VietSentiWordNet default: equal weight for all domains. For finance:
1. Download VSWN lexicon.
2. Augment with domain words: `tăng/increase → +1.0`, `giảm/decrease → -1.0`, `lỗ/loss → -0.8`, `lãi/profit → +0.8`.
3. Aggregate sentence score: `mean(word_scores)` → round to pos/neg/neutral.

### Recommended Stack
- **Segmentation**: `underthesea.ner()` or `pyvi.word_tokenize()`
- **Lexicon**: VietSentiWordNet (polarity) + domain augmentation
- **Negation**: Simple regex on preceding tokens
- **Classification**: Threshold-based: score > 0.2 → positive, < -0.2 → negative, else neutral.

### Citation
- [VnEmoLex - Zenodo](https://zenodo.org/records/801610)
- [VietSentiWordNet Expansion 2025](https://arxiv.org/pdf/2501.08758)
- [VietSentiLex Paper](https://aclanthology.org/Y18-1081.pdf)
- [ACM Study on Sentiment Analysis](https://dl.acm.org/doi/full/10.1145/3589131)

---

## 5. Vietnamese Finance RSS Feeds (2026 Status)

### Working RSS Feeds Verified

| Source | Feed URL | Status | Notes |
|--------|----------|--------|-------|
| VnExpress | https://e.vnexpress.net/rss | ✅ Active | General + business section |
| Vietstock | https://vietstock.vn/rss | ✅ Active | Stocks, real estate, finance |
| Báo Đầu tư | https://baodautu.vn/rssMain.html | ✅ Active | Investment, FDI, banking |
| VnEconomy | https://vneconomy.vn/rss.html | ✅ Active | Economy, securities, investment |
| CafeF | https://cafef.vn/ | ⚠️ Check | No direct RSS URL found; web scraping needed |
| NDH (ndh.vn) | Not found | ❌ Inactive/Offline | No RSS discovered |
| TinnhanhChungkhoan | https://tinnhanhchungkhoan.vn/ | ⚠️ Check | Likely scrape-only; verify RSS |

### Recommended Primary Feeds
1. **Vietstock** - Most reliable for stock/finance
2. **VnExpress** - Broad coverage + English variant
3. **Báo Đầu tư** - Investment-focused
4. **VnEconomy** - Economics + securities

### Note
NDH (ndh.vn) appears dormant; deprioritize in initial phase. CafeF & TinnhanhChungkhoan may require fallback to DOM scraping if RSS discontinued.

### Citation
- [VnExpress RSS](https://e.vnexpress.net/rss)
- [Vietstock RSS](https://vietstock.vn/rss)
- [Báo Đầu tư RSS](https://baodautu.vn/rssMain.html)
- [VnEconomy RSS](https://vneconomy.vn/rss.html)

---

## Summary Recommendations

1. **Scheduling**: APScheduler 3.11+ with coalesce=True, misfire_grace_time=300. Native singleton isolation.
2. **SQLite**: WAL mode + connection-per-thread + busy_timeout=5000. For 3-5 scrapers, consider single-writer pattern (Queue-based batching).
3. **Monitoring**: Loguru + heartbeat table in SQLite. Simple health checks on startup; log failures for email alerts.
4. **Sentiment**: VietSentiWordNet lexicon + underthesea word segmentation + negation rules. Threshold-based classification (pos/neg/neutral).
5. **RSS Feeds**: Primary 4 feeds (Vietstock, VnExpress, Báo Đầu tư, VnEconomy). Plan DOM fallback for CafeF/TinnhanhChungkhoan.

---

## Unresolved Questions
- Does CafeF still maintain RSS in 2026, or has it migrated to API-only? Recommend test fetch on setup.
- Performance baseline: how many articles/min can single SQLite handle on Windows with 3 concurrent scrapers? Benchmark WAL checkpoint strategy.
- Negation handling: should domain-specific negation rules (e.g., "không tăng" = "not increase" ≠ "tăng") override generic lexicon? Needs financial corpus validation.
