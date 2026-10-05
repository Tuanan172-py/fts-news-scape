# Web Monocle 🕵️

Hệ thống thu thập tin tức chứng khoán Việt Nam đa nguồn — RSS, reverse API, HTML scraping.
Phục vụ phòng phân tích: nhiều nguồn, dedup, raw HTML bảo toàn.

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

# 3. Chạy pipeline ban ngày liên tục (capture 15' + re-derive Silver 30' + drift sáng)
python -m src.morninger

# Hoặc 1 cycle rồi thoát
python scripts/run_once.py            # tất cả domain
python scripts/run_once.py cafef tnck # chọn domain

# Chạy thử từng nhịp riêng (không scheduler)
python -m src.morninger --once capture   # 1 cycle capture Bronze
python -m src.morninger --once derive    # 1 lần re-derive Silver tăng dần
python -m src.morninger --once drift     # 1 lần drift report

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
│   └── domains/               # 23 per-domain configs (4 enabled — xem "Nguồn tin")
├── src/
│   ├── orchestrator.py        # entry chính: python -m src.orchestrator [--once]
│   ├── morninger.py           # pipeline ban ngày: capture + re-derive Silver + drift (APScheduler)
│   ├── pipeline/              # derive.py (incremental Silver), silver_builder, change_detect, run
│   ├── core/                  # models, base_scraper, config, logging, retry, tickers
│   ├── crawler/               # http_client (rate limit 3s/domain, retry, UA)
│   ├── processor/             # extractor (trafilatura), classifier, sentiment, segment
│   ├── db/                    # store (SQLite WAL), writer (single-writer), dedup 2 lớp
│   ├── monitor/               # heartbeat + health check CLI
│   ├── notifier/              # file-based notify
│   └── scrapers/              # per-domain scrapers + registry (@register)
├── scripts/                   # run_once, verify_quality, refresh_watchlist, watch_24h
│   └── maintenance/           # backfill_deferred (Bronze-first), repair_dates, ...
├── tests/                     # 79 tests + fixtures thật (captured live)
├── docs/                      # architecture, runbook, skills/ per-domain
│   └── skills/                # cafef.md, tnck.md, fireant.md, rss-sources.md
├── plans/                     # implementation plans
├── thamkhao/                  # research assets (API reverse-engineering) — không xoá
├── data/                      # SQLite DB + lexicon + notifications (DB gitignored)
└── logs/                      # monocle.log rotation 50MB (gitignored)
```

## Thêm domain mới (mục tiêu ~30 phút)

1. Tạo `config/domains/<name>.yaml` (`name`, `method`, `rate_limit`, endpoints/feeds/selectors)
2. Nếu nguồn **có RSS** → `method: rss_capture` → **xong, 0 dòng code** (generic
   `RssCaptureScraper`, có Bronze capture). ⚠️ `content_selector` là **bắt buộc** — selector miss
   ⇒ `capture_status: partial` ⇒ `SELECTOR_BROKEN` ⇒ agent hold bài.
   Nếu API/HTML riêng → viết `src/scrapers/<name>.py`:

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

## Nguồn tin — 24 config, **8 enabled** (cập nhật 2026-09-07)

> **Enabled ≡ có Bronze capture.** Hệ thống là Bronze-first: mỗi bài phải có raw HTML byte-exact
> (`RawStore.save` trước mọi parse). `method: rss` generic **không** lưu Bronze, nên 19 domain còn
> lại **cố ý tắt** từ 2026-08-03 — bật lại cần research riêng từng trang + scraper có capture,
> không phải đổi `enabled: true`.

**Đang chạy (8):**

| Domain | Method | Ghi chú |
|---|---|---|
| cafef.vn | `api` + capture | News.ashx theo watchlist + 6 RSS chuyên mục |
| vietstock.vn | `vietstock` (RSS + capture) | 8 feeds |
| vneconomy.vn | `vneconomy` (RSS + capture) | 8 feeds, body `#article-editor` |
| **vietnambiz.vn** | **`rss_capture`** | 6 feeds, body `div.vnbcbc-body` — nguồn đầu tiên dùng class generic mới |
| **thoibaotaichinhvietnam.vn** | **`rss_capture`** | 1 feed (RSS chuyên mục của họ là ảo), chuyên mục thật từ `meta article:section` |
| **tinnhanhchungkhoan.vn** | `tnck` (zone API + capture) | 9 zone; không có RSS; `source_domain` non-www ≠ tên config `tnck` |
| **baodautu.vn** | `baodautu` (**HTML listing** + capture) | RSS hỏng vĩnh viễn → scraper HTML đầu tiên của repo; 6 chuyên mục |
| **fireant.vn** | `fireant` (API + capture **JSON**) | Bearer token; web là SPA nên Bronze là JSON; mã CK gắn sẵn. ⚠️ xem ghi chú tuân thủ |

**Đang tắt (16):** vndirect, hose, hnx, vnexpress, tuoitre, thanhnien,
znews, cafebiz, vietnamplus, dantri, vietnamnet (VN) · cnbc, marketwatch, fed, oilprice,
yahoofinance (quốc tế, `language: en`).

**Ngoài danh sách domain:** **NSO / Cục Thống kê** — báo cáo KTXH định kỳ (tháng/quý/năm).
Không phải domain: driver riêng `src/pipeline/periodic_reports.py`, dedup theo
`(report_type, period)`, Bronze gồm HTML **+ file .xlsx/.docx** đính kèm.
Chạy: `python scripts/fetch_periodic_reports.py`. Xem [`docs/design/16-periodic-report-scraper.md`](docs/design/16-periodic-report-scraper.md).

Kế hoạch mở rộng: [`plans/20260907-0834-market-sources-expansion/plan.md`](plans/20260907-0834-market-sources-expansion/plan.md)

Chi tiết feed + pitfalls: [`docs/skills/rss-sources.md`](docs/skills/rss-sources.md). Sentiment rule-based (lexicon VN) **đã gỡ khỏi workflow giai đoạn này** — sentiment "thật" do agent sinh ở lớp output; engine giữ tại `src/processor/sentiment.py` để bật lại khi cần.

## Trạng thái Phase 1

| Sprint | Nội dung | Trạng thái |
|--------|----------|-----------|
| 1 | Foundation (BaseScraper, SQLite WAL, logging) + CafeF | ✅ |
| 2 | TNCK, FireAnt API scrapers | ✅ |
| 3 | Sentiment rule-based VN, fuzzy dedup, retry, monitoring, notify | ✅ |
| 4 | RSS layer: Vietstock, VnExpress, Báo Đầu tư, VnEconomy | ✅ |
| 5 | Orchestrator APScheduler + hardening | ✅ (24h test: chạy `scripts/watch_24h.py` song song orchestrator) |

Plan chi tiết: `plans/20260724-0859-scraping-expansion-phase1/plan.md`
