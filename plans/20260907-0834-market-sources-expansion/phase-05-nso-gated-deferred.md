# Phase 05 — NSO / Cục Thống kê: gated, deferred (NO scraper in this plan)

## Context links

- Parent plan: [plan.md](plan.md)
- Depends on: [phase-02](phase-02-tbtc-new-source.md) (TBTC is the interim KTXH proxy) · [phase-04](phase-04-baodautu-html-listing.md) (secondary proxy)
- Research: [researcher-03 §5](research/researcher-03-live-verification-report.md) (**BLOCKED**, curl-verified) · [researcher-02 §3](research/researcher-02-vietnambiz-tbtc-nso-report.md) (URL patterns from search indexing; its fetch failures are confirmed)
- Repo docs: `project/docs/design/03-source-strategy.md` · `project/docs/design/07-storage-layers-and-change-detection.md` · `project/docs/design/12-bronze-to-silver-rules.md`

## Overview

| | |
|---|---|
| Date | 2026-09-07 |
| Description | NSO (`nso.gov.vn`) is **network-unreachable** from this machine and from a second egress path. This phase writes **no scraper**. It is a gate: prove connectivity from the actual deployment host first. If it opens, NSO gets its own component design — it does **not** fit `BaseScraper.run()` and must **not** become a 24th domain YAML. If it stays shut, close it as WONTFIX-for-now and lean on TBTC + baodautu, which republish the monthly KTXH report within hours. |
| Priority | **P3** — blocked; value is high but currently unrealisable |
| Implementation status | 🟢 **G1 PASS (re-run 12/12 probe = 200)**. **G2 MỞ 2026-09-07 theo owner** → design doc: [`docs/design/16-periodic-report-scraper.md`](../../project/docs/design/16-periodic-report-scraper.md). Vẫn KHÔNG viết scraper — chờ owner duyệt phạm vi v1. |
| Review status | 🟡 Cần owner quyết G2 |

## Key insights

- **The block is at the transport layer, not HTTP.** DNS resolves (`www.nso.gov.vn` → 160.25.148.3);
  TCP **connects**, then the peer sends RST before any HTTP response, on both `:80`
  (`curl (56) Recv failure: Connection was reset`) and `:443` (`curl (35)`). `www.gso.gov.vn`
  times out after 20 s. researcher-02's WebFetch, from a **different egress**, got 4/4 `ECONNRESET`.
  → Not a bot-detection problem a better User-Agent solves. Not diagnosable from here.
- **Therefore: no scraper, no config, no selectors.** Any code written now would be written blind
  against zero successfully loaded pages. researcher-02's URL patterns come from search-engine
  indexing, not from fetches — structurally credible, content/selectors entirely unknown.
- **NSO is not a news stream.** ~1 monthly socio-economic report + quarterly + occasional CPI/IIP/FDI
  releases ≈ single-digit pages/month. The same report is mirrored across
  `/tin-tuc-thong-ke/`, `/bai-top/`, `/du-lieu-va-so-lieu-thong-ke/`, `/su-kien/` and `/en/` with
  **different URLs** → URL-based dedup is structurally wrong here; the key must be
  **(report_type, period)**. The high-value payload is the **PDF/XLSX attachments**, not the HTML
  narrative. None of this fits `fetch_list → parse_item → dedup(url,title) → enrich`.
- **A usable proxy already exists.** TBTC's top feed item on 2026-09-07 was
  *"Infographics 8 tháng giải ngân vốn đầu tư công cả nước đạt 509.557,5 tỷ đồng"* — i.e. phase-02
  already delivers the beat NSO would serve, with a working transport and clean dates.

## Requirements

**Gate G1 — connectivity (must pass before anything else)**
Run from the **deployment host**, not this workstation:
```bash
for h in www.nso.gov.vn nso.gov.vn www.gso.gov.vn; do
  echo "== $h"; getent hosts "$h" || nslookup "$h"
  curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 20 "https://$h/"  || true
  curl -sS -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 20 "http://$h/"   || true
  curl -sS --max-time 20 "https://$h/robots.txt" | head -20 || true
done
```
Also try one non-corporate path (VN residential/mobile tether) to separate an FPT egress filter
from an NSO-side WAF/geo-IP block.

- **G1 PASS** (≥1 host returns an HTTP status from ≥2 network paths) → proceed to Gate G2.
- **G1 FAIL** → close this phase as WONTFIX-for-now. Record the evidence, set a 90-day re-check
  reminder, and formally designate TBTC (primary) + baodautu (secondary) as the KTXH/đầu tư công
  coverage path. **Stop. Write no code.**

**Gate G2 — design approval (only if G1 passes)**
A `PeriodicReportScraper` design doc, reviewed and approved, covering:
1. Dedup key `(report_type, period)` — not `url_title_hash`.
2. Binary attachment capture (PDF/XLSX) as first-class Bronze artifacts.
3. Low-frequency scheduling (a few polls/month around publish windows), not the 15-min cycle.
4. Its relationship to `RawStore` / Silver / the handoff catalog.

**Explicit non-requirements**
- ❌ No `config/domains/nso.yaml`. NSO is **not** a 24th domain.
- ❌ No `src/scrapers/nso.py` in this plan.
- ❌ No headless browser / TLS-impersonation dependency added speculatively — that is a
  bot-evasion posture, and the observed failure is a TCP reset, which it would not fix anyway.

## Architecture (sketch only — for G2 review, NOT to build now)

```
NSO would NOT be a BaseScraper. Shape:

  PeriodicReportSource
    discover()   : poll 2-3 listing pages (/tin-tuc-thong-ke/, /du-lieu-va-so-lieu-thong-ke/)
                   a few times per month, around the ~day-6 publish window
    identify()   : (report_type, period) ← parsed from title/URL
                   e.g. ("monthly", 2026, 8) / ("quarterly", 2026, "Q2")
                   ⚠ same report mirrored at ≥4 URLs → dedup on this key, never on url
    capture()    : RawStore.save(html)        — reuse as-is
                 + RawStore.save_binary(pdf|xlsx)  ← NEW capability, does not exist today
    derive()     : Silver from HTML narrative; attachments stay Bronze-only until a
                   numeric-extraction component exists (out of scope)
```

Open architectural question for G2: does `RawStore` grow a binary path, or does a sibling
`AttachmentStore` own it? `RawStore._scan_images` and the `.meta.json` contract assume HTML.
`docs/design/12-bronze-to-silver-rules.md` §2 assumes `raw .html bytes → decode → cleaned_text`,
which a PDF breaks. Both are real changes to the Bronze contract and need explicit sign-off.

## Related code files

**Create: NONE in this phase.**

**Modify (documentation only, regardless of gate outcome)**
| Path | Change |
|---|---|
| `project/docs/design/03-source-strategy.md` | new §"Nguồn báo cáo định kỳ (NSO)" — why it is out of the 4 source groups, the blocked status, and the TBTC/baodautu proxy decision |
| `project/docs/domains/README.md` | a short "Không phải domain" note so NSO is not mistaken for a missing YAML |
| `project/README.md` | roadmap line: NSO deferred, gated on connectivity |

**On G2 approval only (a future plan, not this one):** `docs/design/13-periodic-report-sources.md`,
`src/crawler/raw_store.py` (binary path), a new `src/sources/periodic/` package.

## Implementation steps

### Step 1 — Run Gate G1 from the deployment host
Execute the block above. Capture raw output verbatim (exit codes, curl error numbers, timings).

### Step 2 — Run Gate G1 from one non-corporate network
Tether/VPS on a VN residential or VN cloud IP. Purpose: attribute the RST to FPT egress vs NSO-side.

### Step 3 — Record the verdict
Write the outcome into this file's Overview (`Implementation status`) and into
`docs/design/03-source-strategy.md`. Either way, this is the deliverable of the phase.

### Step 4 — If G1 FAILS: close it out properly
- Mark ⛔ WONTFIX-for-now with the evidence and the date.
- Designate TBTC as the primary KTXH/đầu tư công proxy; baodautu secondary; note the trade-off
  (journalistic summary, hours of latency, no PDF/XLSX data tables).
- Set a 90-day re-check.
- **Do not** start a headless-browser spike. A TCP reset is not a rendering problem.

### Step 5 — If G1 PASSES: scope the G2 design doc (still no scraper code)
Fetch `robots.txt`, `sitemap.xml`, one monthly-report page and one listing page. Answer
researcher-02's open questions #2–#6 (publish day, RSS/sitemap existence, CPI/IIP/FDI series URLs,
annual report pattern, actual selectors, real PDF/XLSX `<a href>` patterns) **from real fetches**.
Then write `docs/design/13-periodic-report-sources.md` and take it to review. Implementation is a
separate plan.

## Todo list

- [ ] 1. Gate G1 from the deployment host — record verbatim output
- [ ] 2. Gate G1 from a non-corporate VN network — attribute the block
- [ ] 3. Record the verdict here + in `docs/design/03-source-strategy.md`
- [ ] 4. If FAIL: close as WONTFIX-for-now, designate TBTC/baodautu proxies, set 90-day re-check
- [ ] 5. If PASS: fetch robots/sitemap/2 pages, answer researcher-02 #2–#6, draft the G2 design doc

## Success criteria

This phase succeeds by producing a **decision backed by evidence**, not by producing code.

| # | Check | Evidence |
|---|---|---|
| S1 | G1 executed from the deployment host | verbatim curl output for 3 hosts × 2 schemes, pasted into this file |
| S2 | G1 executed from a second, non-corporate network | same, with the network described |
| S3 | Verdict recorded | this file's `Implementation status` + a section in `docs/design/03-source-strategy.md` |
| S4 | **Zero speculative code** | `git diff --stat` for this phase touches only `.md` files. No `config/domains/nso.yaml`, no `src/scrapers/nso.py` |
| S5 | Proxy path is real, not hypothetical | phase-02 S8 green, and ≥1 captured TBTC article matching "giải ngân vốn đầu tư công" or "tình hình kinh tế - xã hội" is shown from the live DB |
| S6 (PASS branch only) | G2 design doc exists and is reviewed | `docs/design/13-periodic-report-sources.md`, with dedup key, attachment handling and scheduling settled |

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Someone "just adds an nso.yaml" because it looks like a missing domain | **Med** | **High** — a broken 24th domain that fails every cycle and pollutes error metrics | Explicit ❌ non-requirements above; a "Không phải domain" note in `docs/domains/README.md`; S4 |
| A headless-browser / TLS-impersonation dependency is added to "fix" the block | Med | High — heavy dep, evasion posture, and it does not address a TCP RST | Documented in Step 4; require a maintainer decision |
| Blind implementation against search-indexed URL patterns | Med | High — zero pages ever loaded; selectors would be pure invention | G2 gate demands real fetches first |
| Macro coverage gap while blocked | High | Med | TBTC (phase-02) verified to carry the beat; baodautu (phase-04) secondary. Trade-off: hours of latency, no source data tables |
| Bronze contract quietly bent to accept PDFs | Low | High | Called out as an explicit G2 architectural question; `docs/design/12` §2 assumes HTML bytes |
| G1 passes on the deploy host, so the block was purely local — wasted deferral | Med | Low | That is a *good* outcome and Step 1 costs minutes. Run G1 before anything else in this phase |

## Security considerations

- NSO is a **government** host. Probing must be minimal and polite: a handful of GETs, never a scan,
  never a retry storm. A reset is an answer — accept it.
- Do **not** attempt to evade the block (proxying around a corporate egress filter, TLS
  fingerprint impersonation, IP rotation). If FPT egress is the blocker, the correct move is an
  IT/network request, not circumvention. This needs a maintainer + IT decision, in writing.
- If G1 passes, respect `robots.txt` and any declared `Crawl-delay`; government sites often
  publish stricter terms than commercial ones. Read the site's ToS before designing the crawler.
- PDF/XLSX attachments are untrusted binaries. If they are ever captured, store bytes only —
  **never** open/parse them in-process without a sandbox and an explicit content-type check.
- Public statistical data is not personal data, but the attachment pipeline would be a new
  file-handling surface. Treat it as such at G2.

## Next steps

Final phase of this plan. On G1 PASS → G2 design doc → a **separate** implementation plan.
On G1 FAIL → 90-day re-check; TBTC/baodautu carry the macro beat in the meantime.

## Unresolved questions

1. **Is the reset FPT egress or NSO-side?** (researcher-03 §Unresolved #6, researcher-02 #1.)
   The single blocking unknown. Steps 1–2 answer it.
2. **NSO exact publish day-of-month** — ~day 6 is widely cited, never verified. Determines the
   polling window. G2.
3. **Does NSO expose RSS or `sitemap.xml`?** Unknown either way — `/robots.txt` was never reachable. G2.
4. **CPI / IIP / FDI / XNK / bán lẻ standalone series URLs** — not located. G2.
5. **Annual report URL pattern** — never searched. G2.
6. **NSO selectors and real PDF/XLSX `<a href>` patterns** — zero page loads succeeded, fully
   unknown. Hard blocker for any implementation.
7. **Does `RawStore` grow a binary path, or does a sibling `AttachmentStore` own attachments?**
   Architectural, needs sign-off at G2 — it changes the Bronze contract in `docs/design/12`.
8. **Is a journalistic proxy (TBTC/baodautu) acceptable for macro numbers**, or does the use case
   genuinely require primary-source data tables? If the latter, G1 becomes a hard project
   dependency rather than a nice-to-have. **Owner decision.**


---

## KẾT QUẢ GATE G1 — 2026-09-07 15:03 UTC: **PASS** (đảo ngược kết luận ban đầu)

### NSO nay TRUY CẬP ĐƯỢC qua HTTPS

| Probe | ~08:40 UTC (research) | **15:03 UTC (G1)** |
|---|---|---|
| `https://www.nso.gov.vn/` | `curl (35) Connection reset` | ✅ **200**, 2.07s |
| `https://nso.gov.vn/` | reset | ✅ **301** (redirect chuẩn) |
| `http://www.nso.gov.vn/` (:80) | `curl (56) reset` | ❌ vẫn **reset** |
| `https://www.gso.gov.vn/` | timeout 20s | ❌ vẫn **timeout** (host cũ, IP khác: 210.245.31.100) |

**Ổn định:** 3 request liên tiếp → 200 / 200 / 200, 1.24–1.36s.
**Kết luận:** chặn trước đó là **tạm thời/không liên tục**, không phải chặn vĩnh viễn.
Chỉ cổng **:443 mới đi được**; :80 vẫn RST. `gso.gov.vn` là host **legacy**, đã chết —
dùng `nso.gov.vn`.

⚠️ **Cảnh báo:** chỉ mới chứng minh từ **workstation này**, và cùng host này đã fail 6 giờ
trước. Trước khi commit vào NSO, cần chạy lại G1 **từ chính máy deploy** vài lần trong ngày
để loại trừ tính chập chờn.

### Dữ liệu G1 thu được (đầu vào cho G2)

- **robots.txt** (200, 824 B) — WordPress site. `User-agent: *` chỉ Disallow
  `/wp-admin/`, `/readme.html`, `/license.txt`, `/wp-admin/admin-ajax.php`, `/wp-admin/images/*`.
  → **Trang bài viết ĐƯỢC PHÉP.** Phần còn lại là blocklist các agent hút site
  (Teleport, EmailCollector, WebZIP, BlackWidow…) — ta không thuộc nhóm đó.
- **Trang đích báo cáo KTXH hàng tháng:**
  `https://www.nso.gov.vn/bao-cao-tinh-hinh-kinh-te-xa-hoi-hang-thang/` (200, 85.878 B)
- **Mẫu URL báo cáo:** `https://www.nso.gov.vn/bai-top/{YYYY}/{MM}/bao-cao-tinh-hinh-kinh-te-xa-hoi-{slug}/`
  — có cả biến thể tháng, quý (`quy-i-nam-2026`, `quy-ii-va-sau-thang-dau-nam-2026`).
- **`sitemap.xml` → 301** (chưa lần theo).

### ✅ Bằng chứng CỦNG CỐ luận điểm "dedup theo (report_type, period), KHÔNG theo URL"

Trong danh sách báo cáo có mục tháng 6/2026 nhưng slug là:
```
/bai-top/2026/06/bao-cao-tinh-hinh-kinh-te-xa-hoi-thang-nam-va-5-thang-dau-nam-2025-2/
```
→ slug ghi **2025** (sai năm) và có hậu tố **`-2`** (dấu hiệu bài bị đăng trùng rồi WordPress
tự thêm số). Slug **không suy ra được** từ (loại báo cáo, kỳ báo cáo).
Đây chính xác là lý do khoá dedup phải là **(report_type, period)**, và là lý do NSO
**không** vừa với `fetch_list → parse_item → dedup(url,title) → enrich`.

### Trạng thái: DỪNG ở G2 — cần owner quyết

Theo đúng thiết kế phase-05, **không có dòng code NSO nào được viết**:
- ❌ không có `config/domains/nso.yaml` — NSO **không phải** domain thứ 25
- ❌ không có `src/scrapers/nso.py`
- ❌ không thêm headless browser / TLS-impersonation

**Gate G2 cần owner duyệt một design doc `PeriodicReportScraper`** gồm:
1. Khoá dedup `(report_type, period)` — **không** dùng `url_title_hash`.
2. Capture attachment nhị phân (PDF/XLSX) như Bronze artifact hạng nhất.
3. Lịch chạy tần suất thấp (vài lần/tháng quanh cửa sổ công bố), **không** nhịp 15 phút.
4. Quan hệ với `RawStore` / Silver / handoff catalog.

**Khuyến nghị:** vẫn giữ TBTC (chính) + baodautu (phụ) làm nguồn proxy KTXH — cả hai đã
chạy và đã chứng minh phủ đúng beat (TBTC: *"Infographics 8 tháng giải ngân vốn đầu tư công
đạt 509.557,5 tỷ đồng"*; baodautu: *"Vốn FDI vào Việt Nam tăng mạnh, 8 tháng vượt 40 tỷ USD"*).
NSO chỉ nên xây khi cần **số liệu gốc** (bảng XLSX), không phải để lấy tin.

### Việc cần làm tiếp
- [ ] Chạy lại G1 **từ máy deploy**, nhiều lần trong ngày (loại trừ chập chờn).
- [ ] Owner quyết: có mở G2 (viết design doc `PeriodicReportScraper`) hay không.
- [ ] Nếu mở G2: khảo sát 1 trang báo cáo chi tiết để xác định vị trí + định dạng attachment.


---

## G1 RE-RUN (owner yêu cầu) — 2026-09-07 15:21–15:35 UTC: **12/12 PASS**

```
1  15:21:00Z  https=200/1.30s  http80=RST  robots=200
2  15:22:13Z  https=200/1.38s  http80=RST  robots=200
3  15:23:26Z  https=200/1.39s  http80=RST  robots=200
4  15:24:39Z  https=200/1.23s  http80=RST  robots=200
5  15:25:52Z  https=200/1.37s  http80=RST  robots=200
6  15:27:05Z  https=200/1.31s  http80=RST  robots=200
7  15:28:18Z  https=200/1.34s  http80=RST  robots=200
8  15:29:31Z  https=200/1.28s  http80=RST  robots=200
9  15:30:44Z  https=200/1.36s  http80=RST  robots=200
10 15:31:57Z  https=200/1.37s  http80=RST  robots=200
11 15:33:10Z  https=200/1.35s  http80=RST  robots=200
12 15:34:23Z  https=200/1.30s  http80=RST  robots=200
```

**HTTPS ổn định 100% — 12/12, không một lần fail** (1.23–1.39 s), trải 14 phút.
**:80 luôn RST** — bắt buộc dùng https.
⚠️ Vẫn cần chạy lại **từ máy deploy** trước khi triển khai (workstation này đã fail lúc ~08:40).

## GATE G2 — ĐÃ MỞ (owner duyệt 2026-09-07)

Design doc: **[`docs/design/16-periodic-report-scraper.md`](../../project/docs/design/16-periodic-report-scraper.md)**

### Phát hiện đổi cục diện: NSO là **WordPress có REST API công khai**
`GET /wp-json/wp/v2/posts?tags=727` — tag **727** = "Báo cáo tình hình kinh tế - xã hội",
**337 bài**. Trả JSON có `date`/`modified` ISO, `slug`, `title`, `content`, `tags`,
`gso_document_type`; hỗ trợ `after=`/`page=` → incremental sync tự nhiên.
→ Không phải scrape HTML mò như phase-05 giả định ban đầu.

**Nhịp công bố xác minh:** ngày **3** hàng tháng, ~09:00 (2026-09-03, 08-03, 07-03).

**Attachment CHỈ có trên trang HTML render**, không có trong `content.rendered` của API
(`acf: []`, `featured_media: 0`):
```
/wp-content/uploads/2026/09/01-Loi-van-T8.2026-final.docx
/wp-content/uploads/2026/09/02-Bieu-T8.2026.xlsx   ← bảng số liệu, giá trị cao nhất
```
→ kiến trúc **lai**: API để phát hiện/metadata, HTML để lấy attachment.

**robots:** `User-agent: *` chỉ chặn `/wp-admin/`, `/readme.html`, `/license.txt`.
`/wp-json/` và `/wp-content/uploads/` **được phép**.

### Trạng thái: vẫn CHƯA viết code
Design doc §8 có 5 câu hỏi cần owner chốt (phạm vi v1, có cần XLSX gốc không,
bảng riêng hay dùng `articles`, series khác, ai chạy G1 trên máy deploy).
