# Web Monocle 🕵️

Hệ thống thu thập tin tức chứng khoán Việt Nam đa nguồn — RSS, reverse API, HTML scraping.
Phục vụ phòng phân tích: nhiều nguồn, dedup, raw HTML bảo toàn, sentiment rule-based.

**Standalone** — single machine, SQLite duy nhất, không phụ thuộc dịch vụ ngoài.

## Kiến trúc

```
Scheduler (APScheduler, 15 phút/cycle)
   └─→ BaseScraper subclasses (per domain, config-driven)
          RSS │ REST API │ HTML  →  parse → dedup (SHA-256) → enrich
   └─→ DBWriter (single-writer thread) → SQLite WAL (data/monocle.db)
   └─→ Notify: log file + stdout
```

Chi tiết: [`docs/architecture.md`](docs/architecture.md). Yêu cầu đầy đủ: [`docs/system-prompt.md`](docs/system-prompt.md).

## Quick Start

```bash
# 1. Cài dependencies (Python 3.10+)
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt    # Windows

# 2. (Tuỳ chọn) secrets cho FireAnt — thiếu token thì scraper tự disable, không crash
copy config\secrets.yaml.example config\secrets.yaml   # rồi điền token (docs/skills/fireant.md)

# 3. Chạy liên tục (scheduler 15 phút/cycle)
python -m src.orchestrator

# Hoặc 1 cycle rồi thoát
python scripts/run_once.py            # tất cả domain
python scripts/run_once.py cafef tnck # chọn domain

# 4. Health check + quality gate
python -m src.monitor.health
python scripts/verify_quality.py cafef.vn

# 5. Tests
python -m pytest tests/ -v
```

Ops chi tiết: [`docs/runbook.md`](docs/runbook.md)

## Cấu trúc thư mục

```
web-monocle/
├── config/
│   ├── settings.yaml          # DB path, logging, scheduler, http defaults
│   ├── watchlist.yaml         # Mã cổ phiếu theo dõi
│   ├── notifications.yaml     # Rule notify (file-based)
│   ├── secrets.yaml.example   # Template secrets (secrets.yaml gitignored)
│   └── domains/               # Per-domain configs: cafef, tnck, fireant,
│                              #   vietstock, vnexpress, baodautu, vneconomy
├── src/
│   ├── orchestrator.py        # entry chính: python -m src.orchestrator [--once]
│   ├── core/                  # models, base_scraper, config, logging, retry, tickers
│   ├── crawler/               # http_client (rate limit 3s/domain, retry, UA)
│   ├── processor/             # extractor (trafilatura), classifier, sentiment, segment
│   ├── db/                    # store (SQLite WAL), writer (single-writer), dedup 2 lớp
│   ├── monitor/               # heartbeat + health check CLI
│   ├── notifier/              # file-based notify
│   └── scrapers/              # per-domain scrapers + registry (@register)
├── scripts/                   # run_once, verify_quality, enrich_deferred, watch_24h
├── tests/                     # 79 tests + fixtures thật (captured live)
├── docs/                      # architecture, runbook, skills/ per-domain
│   └── skills/                # cafef.md, tnck.md, fireant.md, rss-sources.md
├── plans/                     # implementation plans
├── thamkhao/                  # research assets (API reverse-engineering) — không xoá
├── data/                      # SQLite DB + lexicon + notifications (DB gitignored)
└── logs/                      # monocle.log rotation 50MB (gitignored)
```

## Thêm domain mới (mục tiêu ~30 phút)

1. Tạo `config/domains/<name>.yaml` (`name`, `method: rss|api|html`, `rate_limit`, endpoints/feeds/selectors)
2. Nếu `method: rss` → xong (generic RSSScraper, Phase 5). Nếu API/HTML → viết `src/scrapers/<name>.py`:

```python
from src.scrapers import register
from src.core.base_scraper import BaseScraper

@register("myndomain")
class MyDomainScraper(BaseScraper):
    def fetch_list(self) -> list[dict]: ...   # gọi API/RSS/HTML
    def parse_item(self, raw) -> Article: ... # raw → Article
    def enrich(self, article) -> None: ...    # optional: fetch trang chi tiết
```

3. Viết test (happy path + 1 edge case) trong `tests/`
4. `python scripts/run_once.py myndomain`

Không cần sửa orchestrator/core.

## Nguyên tắc dữ liệu

- **Raw HTML bảo toàn** — `content_html` giữ nguyên bản, `content_text` là bản sạch
- **Dedup bắt buộc** — SHA-256(url+title), bảng `seen_articles` cùng DB
- **Rate limit ≥3s/domain**, timeout ≤30s, retry 3 lần với backoff
- **Graceful degradation** — scraper lỗi không crash pipeline; lỗi gom vào `ScrapeResult.errors`
- **Graceful shutdown** — SIGINT/SIGTERM → DBWriter flush queue, không corrupt DB

## Nguồn tin (20 domains — Phase 2 expansion 2026-07-25)

**API (3):** cafef.vn (News.ashx, watchlist), tinnhanhchungkhoan.vn (zone), fireant.vn (bearer token — cần secrets.yaml)

**RSS Việt Nam (12):** vietstock (4 feeds), vnexpress, vneconomy (3), vietnambiz (3 — chứng khoán/tài chính/vĩ mô), dantri, vietnamnet (2, keyword filter), tuoitre, thanhnien, znews, cafebiz, vietnamplus, baodautu (disabled — dormant)

**RSS Quốc tế (5, `language: en`):** CNBC (2 feeds, filter), MarketWatch, Yahoo Finance, Federal Reserve, OilPrice

Chi tiết feed + pitfalls: [`docs/skills/rss-sources.md`](docs/skills/rss-sources.md). Bài EN: sentiment = neutral (lexicon VN không áp dụng — by design).

## Trạng thái Phase 1

| Sprint | Nội dung | Trạng thái |
|--------|----------|-----------|
| 1 | Foundation (BaseScraper, SQLite WAL, logging) + CafeF | ✅ |
| 2 | TNCK, FireAnt API scrapers | ✅ |
| 3 | Sentiment rule-based VN, fuzzy dedup, retry, monitoring, notify | ✅ |
| 4 | RSS layer: Vietstock, VnExpress, Báo Đầu tư, VnEconomy | ✅ |
| 5 | Orchestrator APScheduler + hardening | ✅ (24h test: chạy `scripts/watch_24h.py` song song orchestrator) |

Plan chi tiết: `plans/20260724-0859-scraping-expansion-phase1/plan.md`
