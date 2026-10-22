# Web Monocle 🕵️

Hệ thống thu thập và phân tích tin tức chứng khoán Việt Nam đa nguồn — RSS, reverse API, HTML scraping.
Phục vụ phòng phân tích: nhiều nguồn, dedup, raw HTML bảo toàn, mỗi người dùng nhận một tệp xlsx mỗi ngày.

**Một máy, SQLite** — DB vận hành `C:\data\news-scape\monocle.db` (ngoài kho mã, ngoài OneDrive).

## Kiến trúc

```
Capture (morninger: APScheduler, capture 10' + re-derive 30' + drift sáng)
   └─→ BaseScraper subclasses (per domain, config-driven)
          RSS │ REST API │ HTML  →  Bronze (raw HTML byte-exact) → parse → dedup (SHA-256)
   └─→ DBWriter (single-writer thread) → SQLite WAL (C:\data\news-scape\monocle.db)
   └─→ Silver (re-derive tăng dần theo watermark)
Article Lane (ADR-0010, đường xử lý duy nhất)
   └─→ article_run.py: đóng gói → runner LLM (agy, opencode, OpenRouter) → --finish: nạp DB qua cổng DoD
Giao hàng → C:\data\news-scape\users\output\<user>\<YYYY-MM-DD>.xlsx
Xuất bản → scripts/publish.py → SharePoint sandbox (một chiều)
Vận hành không người trông → ops_daemon (Task Scheduler news-scape-ops)
```

Chi tiết: [`docs/architecture.md`](docs/architecture.md).

## Quick Start

```powershell
# 1. Venv ngoài OneDrive (không tạo .venv cục bộ)
python -m venv C:\venvs\news-scape
C:\venvs\news-scape\Scripts\pip install -r requirements.txt
& "C:\venvs\news-scape\Scripts\Activate.ps1"      # mỗi terminal; mọi lệnh dưới chạy trong project/

# 2. (Tuỳ chọn) secrets cho FireAnt — thiếu token thì scraper tự disable, không crash
copy config\secrets.yaml.example config\secrets.yaml   # rồi điền token (docs/skills/fireant.md)

# 3. Chạy pipeline ban ngày liên tục (capture 10' + re-derive Silver 30' + drift sáng)
python -m src.morninger

# Hoặc 1 cycle rồi thoát
python scripts/run_once.py            # tất cả domain
python scripts/run_once.py cafef tnck # chọn domain

# Chạy thử từng nhịp riêng (không scheduler)
python -m src.morninger --once capture   # 1 cycle capture Bronze
python -m src.morninger --once derive    # 1 lần re-derive Silver tăng dần
python -m src.morninger --once drift     # 1 lần drift report

# 4. Health check + điểm chạm pipeline
python -m src.monitor.health
python scripts/pipeline_radar.py status

# 5. Tests (đọc docs/knowledge/facts/tests-must-not-write-operational-db.md trước)
python -m pytest tests/<package>/ -q
```

Vận hành:
- Lớp capture: [`docs/runbook.md`](docs/runbook.md)
- Vận hành tự chủ và đợt Article Lane: [`docs/operations/ops-daemon.md`](docs/operations/ops-daemon.md), [`docs/operations/ops-daemon-reference.md`](docs/operations/ops-daemon-reference.md)
- Xuất bản SharePoint: [`docs/operations/publisher.md`](docs/operations/publisher.md)

## Cấu trúc thư mục

```
project/
├── config/
│   ├── settings.yaml          # DB path, logging, scheduler, morninger, http defaults
│   ├── ops.yaml               # tham số ops_daemon (sensor, wave, mandate, publish)
│   ├── watchlist.yaml         # Mã cổ phiếu theo dõi
│   ├── notifications.yaml     # Rule notify (file-based)
│   ├── secrets.yaml.example   # Template secrets (secrets.yaml gitignored)
│   ├── entities/              # alias thực thể (aliases/, brand_aliases.yaml)
│   └── domains/               # 24 per-domain configs (8 enabled — xem "Nguồn tin")
├── src/
│   ├── orchestrator.py        # capture: python -m src.orchestrator [--once]
│   ├── morninger.py           # pipeline ban ngày: capture + re-derive Silver + drift (APScheduler)
│   ├── scrapers/              # per-domain scrapers + registry (@register)
│   ├── crawler/               # http_client (rate limit 3s/domain, retry, UA)
│   ├── pipeline/              # derive (incremental Silver), silver_builder, change_detect, drift, story_cluster
│   ├── processor/             # extractor (trafilatura), classifier
│   ├── article_lane/          # pack, expand, ledger, tick, handoff của Article Lane
│   ├── agent/                 # runners, contract (DoD), ingest, catalog, packet
│   ├── ops/                   # wave/, runtime/ (daemon, sensor, probes), console/ (control room, radar)
│   ├── export/                # user_output (xlsx), publisher, csv_export, silver_manifest
│   ├── core/                  # models, base_scraper, config, paths, logging, retry, tickers
│   ├── db/                    # store (SQLite WAL), writer (single-writer), dedup 2 lớp, connect, snapshot
│   ├── monitor/               # heartbeat + health check CLI
│   ├── notifier/              # file-based notify
│   └── analytics/ handoff/ lakehouse/ telemetry/ users/
├── scripts/                   # CLI mỏng: run_once, article_run, ops_daemon, publish, pipeline_radar, ...
│   └── maintenance/           # backfill_deferred (Bronze-first), migrate_users_output, refresh_aliases, ...
├── schemas/                   # hợp đồng JSON (article-compact-v2, ...)
├── assets/prefix/             # prefix cho runner LLM
├── tests/                     # tests/<package>/test_*.py, tests/repo/ (kiểm toàn kho), fixtures thật
├── docs/                      # architecture, runbook, operations/, skills/ per-domain
├── domains/                   # hồ sơ từng nguồn (README, schema, changelog)
└── thamkhao/                  # research assets (API reverse-engineering) — không xoá
```

Dữ liệu vận hành (Bronze, Silver, DB, log, đầu ra) nằm dưới `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`), không trong `project/data/`.

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

3. Viết test (happy path + 1 edge case) trong `tests/scrapers/`
4. `python scripts/run_once.py myndomain`

Không cần sửa orchestrator/core. Chi tiết: [`docs/dev/03-adding-a-source.md`](docs/dev/03-adding-a-source.md).

## Nguyên tắc dữ liệu

- **Raw HTML bảo toàn** — Bronze byte-exact, `content_text` là bản sạch
- **Dedup bắt buộc** — SHA-256(url+title), bảng `seen_articles` cùng DB
- **Rate limit ≥3s/domain**, timeout ≤30s, retry 3 lần với backoff
- **Graceful degradation** — scraper lỗi không crash pipeline; lỗi gom vào `ScrapeResult.errors`
- **Graceful shutdown** — SIGINT/SIGTERM → DBWriter flush queue, không corrupt DB

## Nguồn tin — 24 config, **8 enabled**

> **Enabled ≡ có Bronze capture.** Hệ thống là Bronze-first: mỗi bài phải có raw HTML byte-exact
> (`RawStore.save` trước mọi parse). `method: rss` generic **không** lưu Bronze, nên các domain còn
> lại **cố ý tắt** — bật lại cần research riêng từng trang + scraper có capture,
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

**NSO / Cục Thống kê** (báo cáo định kỳ) không có driver chạy; bảng `periodic_reports` trong DB giữ nguyên.

Kế hoạch mở rộng: [`plans/20260907-0834-market-sources-expansion/plan.md`](../plans/20260907-0834-market-sources-expansion/plan.md)

Chi tiết feed + pitfalls: [`docs/skills/rss-sources.md`](docs/skills/rss-sources.md). Sentiment không tính ở lớp capture; agent sinh ở lớp output.
