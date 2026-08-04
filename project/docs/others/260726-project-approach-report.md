# Báo cáo tổng hợp dự án Web Monocle — Cách tiếp cận, triển khai & đường hướng

Ngày: 2026-07-26. Phạm vi: từ khởi đầu dự án → hết Phase 2 + đợt kiểm định nguồn 26/07.
Nguồn: `docs/charter.md`, `docs/decisions.md`, `docs/phase1-report.md`, `plans/2026072*/`, live-verify 26/07.

---

## 1. Bối cảnh & Goal

**Web Monocle** = hệ thống thu thập tin tức chứng khoán/tài chính VN đa nguồn (RSS, reverse API, HTML), phục vụ **phòng phân tích** — vai trò infrastructure phụ trợ, chạy song song, không đụng luồng giao dịch chính (gốc: giám sát tin liên quan VN30F1M).

**Goal cốt lõi (P0/P1, từ charter):**

| ID | Goal | Trạng thái |
|----|------|-----------|
| G-1 | Thu thập tự động, không can thiệp thủ công | ✅ orchestrator 15ph/cycle |
| G-2 | Full content — không chỉ title/summary | ✅ 97.6% quality (nguồn full-content) |
| G-3 | Dedup chính xác (URL hash + fuzzy title) | ✅ 2 lớp |
| G-4 | Notify kịp thời ≤30 phút | ✅ file-notify cùng cycle |
| G-5 | Phân loại category | ✅ rule-based |
| G-6 | Lưu trữ tra cứu được | ✅ SQLite WAL |

**Goal mở rộng đã vượt kế hoạch:** G-7 entity/ticker tagging (client-side), G-10 multi-domain, G-11 API reverse (CafeF/TNCK/FireAnt/VNDirect) — làm sớm hơn dự kiến Phase 2/3 của charter.

**Success criteria đạt:** coverage ≥3 nguồn → **22**; dedup 100% URL-hash; quality 99.8% (Phase 1) / 97.6% (Phase 2). Chưa nghiệm thu: uptime ≥99% (24h test pending).

## 2. Nguyên tắc thiết kế (đường hướng xuyên suốt)

1. **KISS + progressive enhancement** — bắt đầu RSS + SQLite; chỉ thêm phức tạp khi có bằng chứng cần (vd: async trả lời KHÔNG cần khi 7 domain, xem lại khi >20).
2. **Config-driven** — thêm nguồn RSS = 1 file YAML, 0 code; API domain = 1 class 3 hooks (~30 phút gồm test). Không sửa orchestrator/core.
3. **Graceful degradation** — feed chết → log + skip; enrich fail → fallback summary; token hết hạn → self-disable, không hammer. Không bao giờ crash pipeline.
4. **Raw HTML bảo toàn** — `content_html` giữ nguyên bản gốc phục vụ audit/tái xử lý; `content_text` là bản sạch.
5. **Idempotent + observable** — chạy lại không nhân đôi (dedup); heartbeat/metrics SQLite + health CLI exit-code cho cron.
6. **Standalone, single-machine** — SQLite duy nhất, không server/database/cloud mới. (Charter gốc dự kiến Hermes/WSL/ClickHouse/Telegram — thực tế Phase 1 chuyển hướng: standalone Windows, APScheduler thay Hermes cron, file-notify thay Telegram; ClickHouse sync chưa cần.)

## 3. Kiến trúc & thiết kế

```
Scheduler (APScheduler 15ph, coalesce + max_instances=1 = singleton cycle)
  └─→ BaseScraper subclasses (per-domain, config-driven)
        RSS │ REST API │ HTML → fetch_list → parse_item → dedup 2 lớp → enrich
  └─→ classify (rule) + sentiment (lexicon VN; EN=neutral by design)
  └─→ DBWriter (single-writer thread queue) → SQLite WAL (data/monocle.db)
  └─→ Notify: file + stdout │ Heartbeat + health CLI
```

**Pattern chính:**
- **Template method** (`BaseScraper.run()`): subclass chỉ viết `fetch_list/parse_item/enrich`; luồng chuẩn + gom lỗi vào `ScrapeResult.errors`.
- **Registry + factory** (`@register`): per-name class > generic method class (`_rss`); fallback method per config.
- **Single-writer** cho SQLite: WAL + busy_timeout + queue → 0 SQLITE_BUSY qua toàn bộ test/backfill. WAL checkpoint TRUNCATE cuối cycle (giữ file -wal nhỏ trên Windows).
- **Dedup 2 lớp** (TDR-003): SHA-256(url+title) + fuzzy rapidfuzz token_set_ratio ≥90, window 48h.
- **Generic extractor** (TDR-002): trafilatura thay vì selector per-domain — 85-90% đủ cho monitoring; selector riêng chỉ khi domain quan trọng kém chất lượng.

**Quyết định kỹ thuật then chốt (TDR):** RSS làm primary source (TDR-001, setup 5ph/feed, maintenance thấp); HTML scraping chỉ là fallback; API reverse cho nguồn giá trị cao.

## 4. Cách triển khai — phân kỳ thực tế

### Phase 1 (2026-07-24) — Foundation, 5 sprint trong 1 ngày
1. Foundation (BaseScraper, SQLite WAL, logging loguru) + CafeF API
2. TNCK + FireAnt API scrapers
3. Quality layer: sentiment rule-based VN, fuzzy dedup, retry (tenacity 3 lần backoff 2-30s), monitoring, notify
4. RSS layer: Vietstock, VnExpress, Báo Đầu tư, VnEconomy
5. Orchestrator APScheduler + hardening (graceful shutdown, signal handling)

Kết quả: 7 domains, 963 bài, 99.8% quality, 79 tests (fixtures capture live), cycle backfill 8.1ph / steady-state 2-4ph.

### Phase 2 (2026-07-25) — Source expansion ×3
16 nguồn mới → **22 configs (21 active)**: VN RSS ×8, quốc tế ×5 (`language: en`), Layer 0 sở GD ×2 (HNX/HOSE), VNDirect API. 2224 bài, 97.6%, 108 tests.

Tính năng cứng hoá đi kèm: keyword filter per-domain, encoding hardening (`_decode_feed`), date-fallback parser 3 format phi chuẩn, link_rewrites, truststore (HNX cert), bỏ brotli trap.

### Kiểm định nguồn (2026-07-26) — audit toàn bộ 23 domains
Công cụ mới: `scripts/diagnose_sources.py` (fetch+parse+enrich per-domain) + `scripts/sample_articles.py` (xuất bài thật để review nội dung). Phát hiện & fix 5 lỗi:

| Lỗi | Fix |
|-----|-----|
| FireAnt detail `/post/{id}` → 404 im lặng, bài chỉ còn teaser | Đúng là `/posts/{id}` số nhiều; + guard non-200 |
| Yahoo RSS summary rỗng + `extract_full: false` → bài chỉ có title | Bật extract_full (consent-wall là giả định sai — trafilatura trích được) |
| vietnamnet feed chung-khoan dormant từ 2025-01 (trả bài cũ 1.5 năm) | Gỡ feed chết, giữ kinh-doanh + filter |
| Title bọc `<span>` (hose) | `_clean_title`: strip tag HTML |
| Title double-encoded entity (`&aacute;` thanhnien, `&#225;` vietnambiz) | + `html.unescape` (title dùng cho dedup-hash/ticker/sentiment nên phải sạch) |

Trạng thái sau audit: **22/22 nguồn active OK, 112 tests pass, 0 lỗi tồn đọng.**

## 5. Phương pháp làm việc (điều làm nên tốc độ + chất lượng)

- **Live-verify trước khi code** — nhiều nguồn từ research bị loại/điều chỉnh khi xác minh thật (Vietstock API ẩn trong JS → chuyển RSS; Stockbiz/dantri-chungkhoan SAI; SSC NO-GO Oracle ADF). Bài học: **tin docs cũ sẽ code sai**.
- **Fixture thật** — test capture từ response live, không mock tay → bắt được quirk encoding/date thật.
- **Plan → implement → report** mỗi phase (`plans/<YYMMDD-HHMM>-<slug>/` gồm phase files, research, reports) + docs song song (skills per-domain, runbook, TDR) — không nợ documentation.
- **Quality gate**: tests pass + `verify_quality.py` + code review scoped delta trước khi chốt phase.
- **Xử lý sự cố trong ngày**: mọi sự cố live đều root-cause + fix + regression test ngay (bảng sự cố trong cả 2 phase report).

## 6. Nhiệm vụ phía trước

**Vận hành (user action, chặn nghiệm thu):**
1. 24h stability test: `python -m src.orchestrator` + `scripts/watch_24h.py` → uptime ≥99.5%.

**Phase 3 candidates (đã research):**
- BSC PDF pipeline (GO — PDF tự do, ID tăng dần, cần pypdf); SSI title-only monitor.
- Relevance noise: filter cafebiz/marketwatch; bật full-content CNBC/MarketWatch (đang summary-only by-design).

**Đường hướng nâng cấp news-intelligence (nếu chốt mục tiêu này — đánh giá 26/07):**
- Tier 1: entity resolution (tên công ty/lãnh đạo → mã), event clustering chéo nguồn (1 sự kiện = 1 cụm + N nguồn + first-seen), event taxonomy, materiality ranking.
- Tier 2: source-health alert (feed về 0 → báo), làn ưu tiên CBTT sơ cấp, FTS5 search + timeline theo mã, coverage audit (đo recall).
- Tier 3: sentiment mức-mã + EN, versioning bài, dashboard KPI (recall/dedup-rate/latency/tỷ lệ gắn mã).

## 7. Đánh giá tổng thể

- **Điểm mạnh:** kiến trúc config-driven mở rộng đúng như thiết kế (thêm nguồn RSS = 1 YAML, thực chứng 16 nguồn/1 ngày); degradation + hardening thực chiến (7+ quirk encoding/cert/date xử lý xong); auditability (raw HTML + fixtures + TDR + reports đầy đủ).
- **Điểm cần củng cố:** ổn định chưa chứng minh bằng chạy dài (24h pending); feed chết âm thầm chỉ phát hiện thủ công (cần alert); dedup fuzzy chưa gom cụm chéo nguồn thành sự kiện; sentiment/ticker tagging còn thô so với nhu cầu desk phân tích.
- **Vị trí hiện tại:** nền tảng **news-awareness vững** (ingest → dedup → notify), sẵn sàng xây tầng intelligence (resolve → cluster → rank → deliver) lên trên mà không phải làm lại.

---

## Unresolved questions

1. Mục tiêu chốt: news-intelligence thuần hay tiến tới platform có giá/cơ bản? → quyết Tier roadmap.
2. Universe coverage: toàn thị trường hay watchlist? → quyết mức đầu tư entity resolution.
3. Kênh tiêu thụ cho analyst: UI web / digest / search CLI? → quyết thiết kế delivery.
4. Chấp nhận dependency mới (FTS5, NER model, LLM) hay giữ rule-based thuần?
5. Compliance/licensing nguồn scrape ở cấp công ty chứng khoán — cần rà pháp lý.
