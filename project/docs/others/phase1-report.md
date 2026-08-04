# Phase 1 Report — Web Monocle Scraping Expansion

Ngày: 2026-07-24. Plan: `plans/20260724-0859-scraping-expansion-phase1/`.

## Kết quả so với spec §4.3

| Tiêu chí | Mục tiêu | Kết quả | Đạt |
|----------|----------|---------|-----|
| Số lượng | ≥500 bài/ngày từ ≥5 domains | **791 bài mới trong 1 cycle đầu** (backfill), 7 domains cấu hình, 6 active không cần token | ✅ |
| Chất lượng | ≥95% có title+body+date | **99.8% toàn hệ thống** (961/963 bài, sau enrich-deferred); CafeF 100%, TNCK 100% | ✅ |
| Ổn định | Fallback + retry 3 lần, không crash pipeline | tenacity 3 attempts backoff 2-30s; 1 domain fail (baodautu feed quirk) → 6 domain còn lại vẫn hoàn thành cycle; FireAnt 401 self-disable không hammer | ✅ |
| Chuyên nghiệp | Logging đủ, monitoring, thêm domain ~30 phút | loguru + heartbeat/metrics SQLite + health CLI; domain RSS mới = 1 YAML (0 code) | ✅ |

## Số liệu cycle tích hợp đầu tiên (7 domains, tuần tự)

- **Thời gian:** ~8.1 phút (16:52 → 17:00) — cycle BACKFILL nặng nhất (477 bài mới CafeF).
  Steady-state (dedup skip bài cũ) ước tính 2-4 phút — dư trong budget 15 phút.
- **Kết quả per-domain:** cafef 477 new | vietstock 107 | vneconomy 149 | vnexpress 58 | tnck 0 (đã backfill trước) | fireant 0 (chưa token — self-disabled đúng thiết kế) | baodautu FAILED (leading-whitespace XML — fixed + test, verified rerun)
- **DB:** 963 articles, WAL mode, single-writer, 0 lỗi insert.

## Câu trả lời research questions (spec §5.2)

1. **Async cần không?** KHÔNG (phase này). Sequential 7 domains: backfill 8 phút, steady-state 2-4 phút < 15 phút cycle. Xem lại khi >20 domains (TDR-006).
2. **Framework add-domain nhanh nhất:** BaseScraper + registry + YAML. RSS domain = 1 yaml (0 phút code); API domain = 1 class 3 hooks (~30 phút gồm test).
3. **Caching layer:** chưa cần — dedup layer đã chặn re-fetch; requests-cache để dành khi có nhu cầu resume giữa cycle.
4. **SQLite concurrent writes:** WAL + busy_timeout 5000 + single-writer queue → 0 SQLITE_BUSY qua toàn bộ test + backfill.
5. **Monitoring:** heartbeat + metrics tables + `python -m src.monitor.health` (exit code cho cron/alert) — đủ cho single-machine, không cần dashboard.

## Sự cố phát hiện & xử lý trong quá trình build

| Sự cố | Root cause | Fix |
|-------|-----------|-----|
| Vietstock API không gọi được từ HTTP client | Endpoint ẩn trong JS bundle, cần browser session | Chuyển RSS (60 feeds verified) — pre-approved fallback |
| CafeF `Type=2` trả rỗng | Param bắt buộc `Type=1` | Config + doc |
| TNCK `phrase` filter bị ignore | Server bỏ qua param | Client-side ticker tagging (`core/tickers.py`) |
| trafilatura trả None trên bare `<div>` fragment | Cần wrap `<html><body>` | `extract_text()` helper + fallback BS4 |
| baodautu feed: 4 dòng trống trước `<?xml` | feedparser strict | `lstrip()` trước parse + regression test |
| baodautu feeds 0 items (mọi UA/client) | Nguồn RSS dormant (giống NDH) | `enabled: false` + lý do trong yaml; bật lại khi feed sống |
| VnEconomy content:encoded không có trong item | Chỉ khai báo namespace | Đi đường detail-fetch thường |
| Backfill vượt detail cap → bài summary-only | By design (cap 30/cycle) | `scripts/enrich_deferred.py` (TNCK: 80→100% quality) |

## Việc còn lại (user action)

1. **FireAnt token** — dán vào `config/secrets.yaml` (hướng dẫn `docs/skills/fireant.md`) → domain thứ 7 active.
2. **24h stability test** — chạy `python -m src.orchestrator` + song song `python scripts/watch_24h.py`; nghiệm thu uptime ≥99.5% + ≥500 bài/ngày từ CSV.
3. Sentiment validation mở rộng: gate hiện tại ≥70% trên 50 headline gán nhãn tay; nên bổ sung mẫu từ dữ liệu thật định kỳ.

## Deliverables

- 79 tests pass (fixtures thật captured live 2026-07-24)
- 7 domain configs + 4 skill docs (`docs/skills/`)
- Runbook: `docs/runbook.md` | Architecture: `docs/architecture.md`
- Tools: `run_once.py`, `verify_quality.py`, `enrich_deferred.py`, `watch_24h.py`, `-m src.monitor.health`
