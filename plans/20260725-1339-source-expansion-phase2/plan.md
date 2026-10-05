# Plan: Web Monocle Phase 2 — Source Expansion

Date: 2026-07-25 | Status: Planning complete, implementation not started.

## Mission

Mở rộng 6 → 19 domains: +8 nguồn RSS VN, +5 nguồn RSS quốc tế (6 feeds), + 3 tính năng hỗ trợ nhỏ
(keyword filter, encoding hardening, language metadata), + research Layer 0/CTCK.
Nguyên tắc Phase 1 giữ nguyên: RSS domain mới = 1 YAML, zero code; KISS/YAGNI.

## Phases

| # | Phase | File | Status | Progress |
|---|-------|------|--------|----------|
| 1 | Filter + Encoding + Language features (Sprint C — LÀM TRƯỚC) | [phase-03-filter-encoding-features.md](phase-03-filter-encoding-features.md) | ✅ Done — 14 tests mới; phát hiện vietnambiz KHAI utf-16 nhưng serve utf-8 (strip encoding attr) | 100% |
| 2 | VN RSS sources ×8 (Sprint A) | [phase-01-vn-rss-sources.md](phase-01-vn-rss-sources.md) | ✅ Done — 8/8 live (brotli header fix + date-fallback parser cho vietnambiz/cafebiz/tuoitre) | 100% |
| 3 | Intl RSS sources ×5 (Sprint B) | [phase-02-intl-rss-sources.md](phase-02-intl-rss-sources.md) | ✅ Done — 5/5 live (Fed BOM OK, filter CNBC) | 100% |
| 4 | Layer 0 + CTCK research (Sprint D — song song, không chặn) | [phase-04-layer0-ctck-research.md](phase-04-layer0-ctck-research.md) | ✅ Probe done (reports/02): **GO 5/6** → đã build HNX (RSS + link_rewrites), HOSE (RSS api.hsx.vn), **VNDirect (JSON API scraper mới)**. SSC NO-GO (Oracle ADF headless-only). SSI (PDF login-wall) + BSC (PDF pipeline cần) → Phase 3 | 90% |

## Dependencies

```
Phase 3 (features: filter/encoding/language)
   ├─→ Phase 1 (VN RSS)  — vietnambiz cần utf-16 fix, dantri cần BOM strip,
   │                        vietnamnet kinh-doanh cần filter.
   │                        5 nguồn sạch (tuoitre, thanhnien, znews, cafebiz,
   │                        vietnamplus) có thể add song song Phase 3.
   └─→ Phase 2 (Intl RSS) — Fed cần BOM strip, CNBC Top News cần filter,
                             tất cả cần language: en.
Phase 4 — độc lập hoàn toàn, chạy bất kỳ lúc nào (DevTools research).
```

Execution order đề xuất: **Phase 3 → Phase 1 → Phase 2**; Phase 4 song song.

## Success Metrics (Phase 2 acceptance)

| Metric | Target |
|--------|--------|
| Domains active | ≥15 (19 configured; chấp nhận ≤4 fail/disable) |
| Volume | ≥1000 bài/ngày toàn hệ thống |
| Quality (title+body+date) | ≥95% giữ nguyên (Phase 1: 99.8%) |
| Cycle time steady-state | < 12 phút (budget 15 phút, headroom 20%) |
| Tests | 80 hiện có pass + tests mới cho filter/encoding/language |
| EN articles | có `metadata.language = "en"`, sentiment = neutral (by design) |

## Key references

- Live verification (SOURCE OF TRUTH, 2026-07-25): [reports/01-live-verification-report.md](reports/01-live-verification-report.md)
- Research: [research/researcher-01-vn-official-press-report.md](research/researcher-01-vn-official-press-report.md), [research/researcher-02-aggregator-intl-report.md](research/researcher-02-aggregator-intl-report.md)
- Phase 1 report: `docs/phase1-report.md` | Architecture: `docs/architecture.md` | RSS skill: `docs/skills/rss-sources.md`
- Lưu ý: nhiều URL trong research reports SAI (Stockbiz chết, HNX rss.html là JS page,
  dantri chung-khoan.rss không tồn tại) — chỉ dùng URL từ verification report.

## Unresolved Questions

1. VietnamBiz zones tai-chinh/vi-mo + CafeBiz zones khác: URL chưa verify — verify lúc implement, không blocker.
2. Sentiment EN: Phase 2 chấp nhận neutral; cần EN lexicon ở phase sau? (user decide)
3. IMF/TradingEconomics/Kitco: researcher-02 nói active nhưng KHÔNG trong verification report → out of scope Phase 2, cân nhắc Phase 3.
4. 19 domains sequential — nếu backfill cycle đầu > 15 phút: rollout theo batch (đã có mitigation Phase 1/2), async chưa cần (TDR-006 revisit khi >20 domains).
