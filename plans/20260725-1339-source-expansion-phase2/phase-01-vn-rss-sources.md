# Phase 1 (Sprint A): VN RSS Sources ×8

## Context links

- Plan overview: [plan.md](plan.md)
- Verification report (source of truth, feed URLs + item counts): [reports/01-live-verification-report.md](reports/01-live-verification-report.md)
- Features phụ thuộc: [phase-03-filter-encoding-features.md](phase-03-filter-encoding-features.md)
- Pattern chuẩn: `docs/skills/rss-sources.md`, `config/domains/vietstock.yaml` (mẫu)
- Generic scraper: `src/scrapers/rss_generic.py` (KHÔNG sửa trong phase này)

## Overview

- **Date:** 2026-07-25
- **Description:** Add 8 domain RSS VN bằng YAML thuần (zero code): vietnambiz, dantri,
  vietnamnet, tuoitre, thanhnien, znews, cafebiz, vietnamplus. 3 nguồn gated bởi Phase 3
  (encoding/filter), 5 nguồn sạch add ngay được.
- **Priority:** HIGH
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights (từ verification 2026-07-25 — TIN CÁI NÀY, không tin research reports)

- Tất cả 8 feed verified working với item count thật. Researcher-01 SAI ở nhiều chỗ:
  CafeBiz "không có RSS" (thực tế có, 61 items), dantri chung-khoan.rss (không tồn tại).
- Pitfalls per source: vietnambiz **utf-16**; dantri **BOM**; thanhnien thiếu `<?xml`
  declaration (feedparser OK, không cần fix); tuoitre XML minified 1 dòng (feedparser OK).
- VietnamNet chung-khoan.rss = **142 items** (add thẳng); kinh-doanh.rss = **1000 items**
  (chỉ add kèm keyword filter, hoặc bỏ qua nếu chung-khoan đủ coverage).
- vietnamplus dùng bản tiếng Việt `www.vietnamplus.vn` (KHÔNG dùng `en.` như researcher-01 gợi ý).

## Requirements

- 8 file YAML mới trong `config/domains/`, schema Phase 1 + field mới Phase 3.
- Rollout theo batch (không enable cả 8 cùng lúc) + đo cycle time.
- Fuzzy dedup cross-domain (Phase 1 sẵn có) xử lý tin trùng giữa báo — không cần code.
- Quality gate từng domain: `python scripts/verify_quality.py <domain>` ≥95%.

## Architecture

Không đổi. `build_scraper()` (orchestrator) resolve `method: rss` → generic `RSSScraper`.
Mỗi YAML = 1 domain. Dedup/sentiment/notify pipeline sẵn có.

## Related code files

**Create (8 YAML):**
- `config/domains/vietnambiz.yaml`
- `config/domains/dantri.yaml`
- `config/domains/vietnamnet.yaml`
- `config/domains/tuoitre.yaml`
- `config/domains/thanhnien.yaml`
- `config/domains/znews.yaml`
- `config/domains/cafebiz.yaml`
- `config/domains/vietnamplus.yaml`

**Modify:**
- `docs/skills/rss-sources.md` — thêm 8 dòng vào feed inventory + pitfalls.
- `README.md` — bảng nguồn tin.
- `tests/test_domain_configs.py` (nếu có test validate config) hoặc thêm smoke test
  load toàn bộ `config/domains/*.yaml` qua `load_domain_config`.

**Delete:** none.

## Implementation Steps

1. **Batch 1 — 5 nguồn sạch (không chờ Phase 3):**

   `config/domains/tuoitre.yaml`:
   ```yaml
   name: tuoitre
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://tuoitre.vn/rss/kinh-doanh.rss", name: "Tuổi Trẻ Kinh doanh"}
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "XML minified 1 dòng — feedparser OK. 50 items. Verified 2026-07-25."
   ```

   `config/domains/thanhnien.yaml`:
   ```yaml
   name: thanhnien
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://thanhnien.vn/rss/kinh-te.rss", name: "Thanh Niên Kinh tế"}
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "Feed thiếu <?xml declaration (bắt đầu thẳng <rss) — feedparser chấp nhận. 50 items. Verified 2026-07-25."
   ```

   `config/domains/znews.yaml`:
   ```yaml
   name: znews
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://znews.vn/rss/kinh-doanh-tai-chinh.rss", name: "Znews Kinh doanh Tài chính"}
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "50 items. Verified 2026-07-25."
   ```

   `config/domains/cafebiz.yaml`:
   ```yaml
   name: cafebiz
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://cafebiz.vn/rss/cau-chuyen-kinh-doanh.rss", name: "CafeBiz Câu chuyện KD"}
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "Researcher nói không có RSS — SAI, verified 61 items 2026-07-25. Còn zone khác chưa khám phá (step 2)."
   ```

   `config/domains/vietnamplus.yaml`:
   ```yaml
   name: vietnamplus
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://www.vietnamplus.vn/rss/kinhte.rss", name: "VietnamPlus Kinh tế"}
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "Dùng bản VN (www.), KHÔNG dùng en.vietnamplus.vn. 50 items. Verified 2026-07-25."
   ```

2. **Khám phá zone bổ sung** (curl đếm `<item>`, chỉ add nếu ≥10 items + đúng scope):
   - CafeBiz: thử `https://cafebiz.vn/rss/thi-truong.rss`, `.../vi-mo.rss`,
     `.../cafebiz-news.rss` — pattern index thường tại `https://cafebiz.vn/rss.chn`.
   - Nếu tìm được zone chứng khoán/thị trường tốt hơn → thêm vào `feeds` list cafebiz.yaml.

3. **Smoke test Batch 1:** `python scripts/run_once.py tuoitre thanhnien znews cafebiz vietnamplus`
   → check log fetched/new/errors; sau đó `python scripts/verify_quality.py <domain>` từng cái.
   Ghi cycle duration.

4. **Batch 2 — 3 nguồn cần Phase 3** (sau khi Phase 3 merge):

   `config/domains/vietnambiz.yaml`:
   ```yaml
   name: vietnambiz
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://vietnambiz.vn/chung-khoan.rss", name: "VietnamBiz Chứng khoán"}
       # step 5: verify rồi mới thêm tai-chinh / vi-mo zones
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "ENCODING UTF-16 — cần _decode_feed (Phase 3). 30 items. Verified 2026-07-25."
   ```

   `config/domains/dantri.yaml`:
   ```yaml
   name: dantri
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://dantri.com.vn/rss/kinh-doanh.rss", name: "Dân trí Kinh doanh"}
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "BOM trước <?xml — cần _decode_feed (Phase 3). KHÔNG có chung-khoan.rss. 100 items. Verified 2026-07-25."
   ```

   `config/domains/vietnamnet.yaml`:
   ```yaml
   name: vietnamnet
   enabled: true
   method: rss
   rate_limit: 3.0
   timeout: 30
   rss:
     feeds:
       - {url: "https://vietnamnet.vn/rss/chung-khoan.rss", name: "VietnamNet Chứng khoán"}
       - {url: "https://vietnamnet.vn/rss/kinh-doanh.rss", name: "VietnamNet Kinh doanh"}
   filter:
     any: ["chứng khoán", "cổ phiếu", "vn-index", "trái phiếu", "niêm yết",
           "lãi suất", "ngân hàng", "tỷ giá", "doanh nghiệp", "vàng", "hose", "hnx", "upcom"]
     drop_unmatched: true
   detail: {extract_full: true, max_details_per_cycle: 30}
   pitfalls: "chung-khoan 142 items OK; kinh-doanh 1000 items → BẮT BUỘC filter. Nếu noise vẫn cao sau 24h: bỏ feed kinh-doanh, giữ chung-khoan. Verified 2026-07-25."
   ```

   Lưu ý: filter áp per-domain (không per-feed) — chấp nhận filter chạy cả trên
   chung-khoan feed (vô hại vì tin chung-khoan match keyword). KISS, không thêm
   per-feed filter (YAGNI).

5. **VietnamBiz zone exploration:** curl `https://vietnambiz.vn/tai-chinh.rss`,
   `https://vietnambiz.vn/vi-mo.rss` (đọc index `https://vietnambiz.vn/rss.htm` nếu có)
   — verify item count + utf-16 decode OK → thêm vào feeds nếu tốt.

6. **Smoke test Batch 2:** `python scripts/run_once.py vietnambiz dantri vietnamnet`
   → verify tiếng Việt đúng dấu trong DB (`sqlite3` select title vietnambiz),
   verify vietnamnet fetched≈1142 nhưng new hợp lý (filter hoạt động).

7. **Backfill detail:** cycle đầu vượt cap 30 detail/domain → chạy
   `python scripts/enrich_deferred.py` sau backfill (pattern Phase 1).

8. **Quality gate 8 domains:** `verify_quality.py` từng domain ≥95%; tổng cycle time
   ghi vào báo cáo (guard <12 phút steady-state).

9. **Docs:** update `docs/skills/rss-sources.md` (bảng feed + pitfalls encoding/filter),
   `README.md` bảng nguồn tin (7 → 15 dòng).

## Todo list

- [ ] Batch 1: 5 YAML (tuoitre, thanhnien, znews, cafebiz, vietnamplus)
- [ ] Zone exploration CafeBiz
- [ ] Smoke + quality gate Batch 1
- [ ] Batch 2: 3 YAML (vietnambiz, dantri, vietnamnet) — sau Phase 3
- [ ] Zone exploration VietnamBiz (tai-chinh, vi-mo)
- [ ] Smoke + quality gate Batch 2 (verify utf-16 decode, filter counts)
- [ ] enrich_deferred sau backfill
- [ ] Update docs (rss-sources.md, README.md)

## Success Criteria

- 8 domain active, `run_once.py` 0 crash, feed-level isolation giữ nguyên.
- Quality ≥95%/domain (title+body+date).
- vietnambiz titles đúng dấu tiếng Việt trong DB (utf-16 decode OK).
- vietnamnet: new articles chủ yếu scope tài chính (spot-check 20 bài).
- Không tăng dup: fuzzy dedup cross-domain hoạt động (log fuzzy-dup skipped).

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Backfill cycle đầu quá dài (8 domains × cap 30 detail × 3s) | Cao | Rollout batch; enable từng batch, run_once riêng từng domain lần đầu |
| VietnamNet filter keyword list chưa chuẩn → noise/miss | Trung bình | Quan sát 24h, tune list; fallback bỏ feed kinh-doanh |
| Feed đổi format/dormant (như baodautu Phase 1) | Thấp | Feed isolation + heartbeat; disable với lý do trong yaml |
| Fuzzy dedup threshold quá aggressive khi nhiều báo đăng cùng tin | Trung bình | Spot-check fuzzy-dup log; tin cùng sự kiện khác góc nhìn vẫn giữ được vì title khác đủ xa |

## Security Considerations

- Toàn bộ nguồn public, không auth, không secrets mới.
- Rate limit 3s/domain giữ nguyên — lịch sự với server báo.

## Next steps

Phase 2 (Intl RSS). Sau cả 2: cycle-time đo tổng 19 domains (Phase 3 step 9).
