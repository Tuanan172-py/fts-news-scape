# Phase 4 (Sprint D): Layer 0 + CTCK Research (DevTools Reverse)

## Context links

- Plan overview: [plan.md](plan.md)
- Verification report: [reports/01-live-verification-report.md](reports/01-live-verification-report.md) (section "Cần research sâu riêng")
- Research: [research/researcher-01-vn-official-press-report.md](research/researcher-01-vn-official-press-report.md) (Layer 0 + CTCK tables — feasibility ước tính, CHƯA verify)
- Pattern tham chiếu: Phase 1 CafeF reverse (`thamkhao/`, `docs/skills/cafef.md`, `src/scrapers/cafef.py`)
- Skill: chrome-devtools (browser automation cho network capture)

## Overview

- **Date:** 2026-07-25
- **Description:** Research sprint riêng biệt (KHÔNG chặn Phase 1-3): DevTools reverse
  các nguồn Layer 0 (HOSE/HNX/SSC/CBTT disclosure) + CTCK research PDF lists
  (SSI/VNDirect/BSC). Deliverable = findings report + 1-2 scrapers NẾU khả thi
  (pattern API scraper Phase 1). Timebox, không cam kết scraper.
- **Priority:** MEDIUM (giá trị cao — disclosure là tin gốc, nhưng effort không chắc chắn)
- **Implementation status:** Not started
- **Review status:** Not reviewed

## Key Insights

- Verification 2026-07-25: HNX `hnx.vn/vi-vn/rss.html` là **JS page, không phải feed**
  (researcher-01 nói "RSS confirmed" — SAI). Có thể có feed/API ẩn sau JS → cần DevTools.
- Researcher-01 feasibility Layer 0: HOSE no public RSS; SSC portal SPA
  (`ssc.gov.vn/webcenter/portal/cbtt`) có thể có anti-bot/session — chưa verify.
- CTCK: SSI có `/api/research/` hint; VNDirect PDF public một phần; BSC daily outlook
  public không login. Tất cả CHƯA verify live.
- Phase 1 precedent: Vietstock internal API cần browser session → fail, đổi RSS.
  Bài học: verify session requirement SỚM trước khi viết scraper.
- Disclosure (CBTT) là Layer 0 — tin gốc trước khi báo chí đăng lại → giá trị alpha
  cao nhất cho phòng phân tích.

## Requirements

1. Findings report per target: endpoint thật, auth/session requirement, rate limit
   observed, response format, feasibility verdict (GO / NO-GO / NEEDS-BROWSER).
2. Nếu ≥1 target GO (plain HTTP + JSON/HTML parse được): implement 1-2 scrapers
   theo pattern Phase 1 (BaseScraper subclass + @register + yaml + tests + skill doc).
3. Timebox: 1-2 ngày research; scraper chỉ khi GO rõ ràng. NO-GO cũng là deliverable.
4. Tôn trọng ToS: chỉ public endpoints, không bypass login, rate limit ≥3s.

## Architecture

Nếu GO: giống API scrapers Phase 1 (cafef/tnck):

```
src/scrapers/<name>.py  (@register("<name>"), 3 hooks: fetch_list/parse_item/enrich)
config/domains/<name>.yaml  (method: api, endpoints, rate_limit)
```

PDF sources (CTCK): Article với `url` = PDF link, `content_text` = title/mô tả từ
list page, `metadata.report_type` — KHÔNG parse PDF nội dung ở Phase 2 (YAGNI;
phòng phân tích tự mở PDF).

## Related code files

**Create (research phase):**
- `plans/20260725-1339-source-expansion-phase2/reports/04-layer0-ctck-findings.md` — findings.
- `thamkhao/layer0/` — captured requests/responses (HAR/JSON) per target. (`thamkhao/` = không xoá.)

**Create (chỉ nếu GO, per scraper):**
- `src/scrapers/<name>.py` (vd `hnx.py`, `ssi_research.py`)
- `config/domains/<name>.yaml`
- `tests/test_<name>.py` + fixture captured live
- `docs/skills/<name>.md`

**Modify:** `README.md` nếu domain mới active.

**Delete:** none.

## Implementation Steps

1. **Setup capture:** dùng chrome-devtools skill / Chrome DevTools thủ công —
   Network tab, filter XHR/Fetch, Preserve log.

2. **HNX (`hnx.vn`):** mở trang tin CBTT/thông báo → capture XHR. Tìm:
   - Feed ẩn sau `vi-vn/rss.html` (JS page render link RSS thật?)
   - API JSON pagination (pattern ASP.NET thường: POST với ViewState hoặc REST ẩn)
   - Test replay bằng `curl`/requests KHÔNG cookie → xác định session requirement.

3. **HOSE (`hsx.vn`):** trang công bố thông tin → capture API list announcements.
   HSX từng có REST JSON pagination (`/Modules/.../get...`) — verify tồn tại + replay.

4. **SSC/CBTT (`ssc.gov.vn/webcenter/portal/cbtt`):** Oracle WebCenter SPA —
   capture, khả năng cao NEEDS-BROWSER/anti-bot. Verdict nhanh, không sa lầy.

5. **SSI (`ssi.com.vn`):** trang research/báo cáo public → capture `/api/research/`
   hint từ researcher-01. Xác định: list endpoint JSON? PDF URL pattern? login wall
   ở đâu (list vs download)?

6. **VNDirect (`vndirect.com.vn`):** trang research/DSMART public reports →
   list endpoint + PDF URLs không login.

7. **BSC (`bsc.com.vn`):** daily market outlook page — khả năng HTML parse tĩnh
   (researcher-01: public không login). Verify + capture HTML structure.

8. **Viết findings report** (`reports/04-layer0-ctck-findings.md`): bảng verdict
   6 targets (GO/NO-GO/NEEDS-BROWSER), endpoint + evidence, đề xuất scraper nào build.

9. **Nếu GO — build 1-2 scrapers** (ưu tiên: HNX/HOSE disclosure > CTCK research):
   - Class theo pattern `src/scrapers/tnck.py` (API JSON) hoặc HTML parse BS4.
   - `enrich()`: disclosure thường không cần detail fetch (title+link+date đủ);
     CTCK: metadata `report_type`, `broker`.
   - `language: vi`, tests với fixture captured, `run_once.py <name>` verify,
     `docs/skills/<name>.md` (endpoint, params, pitfalls).

10. **24hmoney/Cophieu68** (optional, chỉ khi còn timebox): quick network capture,
    ghi findings — KHÔNG build scraper Phase 2.

## Todo list

- [ ] Capture HNX network → verdict
- [ ] Capture HOSE network → verdict
- [ ] Capture SSC/CBTT → verdict (nhanh, không sa lầy)
- [ ] Capture SSI research → verdict
- [ ] Capture VNDirect research → verdict
- [ ] Capture BSC outlook → verdict
- [ ] Findings report `reports/04-layer0-ctck-findings.md`
- [ ] (Nếu GO) Scraper #1 + yaml + tests + skill doc
- [ ] (Nếu GO) Scraper #2 + yaml + tests + skill doc
- [ ] (Optional) 24hmoney/Cophieu68 quick findings

## Success Criteria

- Findings report đầy đủ 6 targets với verdict + evidence (request/response captured
  trong `thamkhao/layer0/`).
- Nếu GO: scraper chạy `run_once.py` sạch, tests pass, quality gate ≥95%,
  không vi phạm rate limit/ToS.
- NO-GO có lý do cụ thể (session/anti-bot/login) — đủ để không phải research lại.

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Endpoint cần browser session (như Vietstock Phase 1) | Cao | Verify replay không-cookie NGAY sau capture, trước khi viết code |
| Gov site anti-bot / IP block | Trung bình | Rate limit ≥3s, UA browser, dừng ngay nếu 403; không retry hammer |
| Sa lầy timebox (SPA phức tạp) | Trung bình | Verdict-first: mỗi target ≤2h research; NO-GO là kết quả hợp lệ |
| Endpoint không ổn định (đổi theo release) | Trung bình | Skill doc ghi cách re-capture; heartbeat phát hiện fetched=0 |

## Security Considerations

- KHÔNG bypass login/paywall; chỉ public endpoints (ToS risk — researcher-01 đã cảnh báo Selenium+login wall).
- Không lưu cookie/session vào repo; captured HAR sanitize header nhạy cảm trước khi commit `thamkhao/`.
- Gov sites: rate limit bảo thủ, max_details thấp.

## Next steps

Findings → quyết định Phase 3 (project-level) scope: disclosure scrapers chính thức,
PDF content parse, EN sentiment lexicon.
