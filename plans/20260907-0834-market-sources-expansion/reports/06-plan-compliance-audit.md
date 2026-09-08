# Report 06 — Biên bản rà soát: thực tế có khớp kế hoạch không?

Ngày 2026-09-07 · Chạy sau sự cố mất dữ liệu, **kiểm chứng bằng máy** chứ không dựa trí nhớ.
Script: đọc config/DB/filesystem thật rồi assert từng bất biến của kế hoạch.

**Kết quả: 96/99 PASS.** 3 mục "FAIL" là **giả** — xem §6.

---

## 1. Domain enabled + contract (A)

| Kiểm tra | Kết quả |
|---|---|
| Đúng 8 domain enabled | ✅ baodautu, cafef, fireant, thoibaotaichinhvietnam, tnck, vietnambiz, vietstock, vneconomy |
| `domains/<name>/schema.yaml` cho cả 8 | ✅ 8/8 |
| `resolve_source_domain()` khớp `domain:` trong contract | ✅ 8/8 — quan trọng nhất: `tnck` → `tinnhanhchungkhoan.vn` (trước sửa: `tnck.vn` → 0 bài) |

## 2. Bất biến config theo kế hoạch (B) — 42/42 PASS

**tnck:** 9 zone đúng bộ đã chốt `[1,4,6,11,21,26,29,33,39]` · `pages_per_cycle=1` ·
**zone 8 bị loại** (Điều tra — nội dung lệch hình sự/tiêu dùng).

**baodautu:** block `rss:` **đã xoá hẳn** · comment "bật lại khi feed có items" **đã xoá** ·
body `#content_detail_news` · date scope `span.post-time` ·
**`item_selector: article`** (KHÔNG phải `div.thumbblock` — class đó nằm trên thẻ `<a>` ảnh) ·
6 chuyên mục · **loại d80** (PR).

**TBTC:** **đúng 1 feed** (feed theo chuyên mục là ẢO) · `category_meta: article:section`.

**vietnambiz:** 6 feed · body `div.vnbcbc-body` · `method: rss_capture`.

**fireant:** enabled · `method: fireant` · có block `capture`.

**Cả 8 domain:** `rate_limit >= 3.0` ✅ · `respect_robots: true` ✅ · `proxy_rotation: false` ✅.

## 3. Bronze → Silver → handoff (C)

Mỗi domain đều có đủ **6 tầng**: `articles` / Bronze / Silver / work_package / `article_versions` / `work_items`.

| Domain | articles | bronze | silver | package | version | work_item |
|---|---|---|---|---|---|---|
| vietnambiz | 170 | 170 | 170 | 170 | 310 | 170 |
| thoibaotaichinhvietnam | 24 | 24 | 24 | 24 | 24 | 24 |
| tnck | 354 | 354 | 354 | 354 | 668 | 354 |
| baodautu | 109 | 109 | 109 | 109 | 188 | 109 |
| fireant | 357 | 358 | 322 | 322 | 322 | 322 |
| cafef | 3733 | 1405 | 1376 | 1376 | 1398 | 1364 |
| vietstock | 1272 | 815 | 787 | 787 | 827 | 797 |
| vneconomy | 1200 | 783 | 768 | 768 | 822 | 778 |

→ **Cả 8 nguồn đã tích hợp trọn vào pipeline**, work_item ở trạng thái `pending` sẵn cho agent.

**Toàn vẹn Bronze (sha256 vs `.meta.json`), mẫu 40 file/domain:**
vietnambiz 40/40 · TBTC 24/24 · tnck 40/40 · baodautu 40/40 · fireant 40/40 — **0 sai**.

> fireant `bronze 358 > silver 322`: 36 file Bronze mới kéo về sau lần `derive` cuối.
> Chạy `python -m src.morninger --once derive` là khớp. Không phải lỗi.

## 4. NSO tách biệt đúng design 16 §3 (D) — 11/11 PASS

- Bronze ở `data/raw_reports/` ✅ · **KHÔNG** ở `data/raw_html/` ✅ · **KHÔNG** tạo Silver bài báo ✅
- Attachment dùng `.binmeta.json` (6 file) ✅ · trang HTML dùng `.meta.json` (3 file) ✅
- **KHÔNG** có `config/domains/nso.yaml` ✅ · **KHÔNG** có `src/scrapers/nso.py` ✅ ·
  **KHÔNG** vào `REGISTRY` ✅
- `periodic_reports` có 3 bản ghi ✅ · **0 work_item mồ côi** ✅
- **3 file `.xlsx` là Excel hợp lệ thật** (`zipfile.is_zipfile`) ✅

## 5. Dọn dẹp + tool (E) — 13/13 PASS

- `enrich_deferred.py` (Bronze-blind) **đã xoá** ✅ · `backfill_deferred.py` có ✅ ·
  `run_periodic_reports.ps1` có ✅
- `RssCaptureScraper` **kế thừa** `RSSScraper` và **không** định nghĩa lại
  `fetch_list`/`parse_item` ✅ (chống copy-paste tái diễn)
- `SilverBuilder` có nhánh JSON generic ✅ · `RawStore.save_binary` + `.binmeta.json` ✅
- Bẫy `.vn`-suffix đã sửa ở **cả** `domain_check.py` và `domain_reporter.py` ✅
- `.gitignore`: `data/raw_html/`, `data/raw_reports/`, `data/silver/`, `data/*.db`,
  `data/reports/` ✅

## 6. Ba mục "FAIL" — đều là giả

```
FAIL  cafef:     sha256 khop  [0 ok / 0 sai / 40 dehydrated]
FAIL  vietstock: sha256 khop  [0 ok / 0 sai / 40 dehydrated]
FAIL  vneconomy: sha256 khop  [0 ok / 0 sai / 40 dehydrated]
```

`0 sai` — **không có file nào sai hash**. Chúng **không đọc được** vì OneDrive đã
dehydrate thành placeholder trên đám mây (`OSError: Invalid argument`).

- Đây là **3 domain cũ**, không thuộc phạm vi đợt này.
- 5 nguồn mới đọc được và hash khớp 100%.
- Sẽ tự hết khi OneDrive hydrate lại, hoặc khi `data/` được chuyển ra ngoài OneDrive.

## 7. Đối chiếu từng phase với kế hoạch gốc

| Phase | Kế hoạch | Thực tế | Sai lệch |
|---|---|---|---|
| 01 | class `rss_capture` + vietnambiz 6 feed | ✅ | **Có, tốt hơn:** audit phát hiện kế hoạch định copy-paste `fetch_list`/`parse_item` → đổi sang **kế thừa** `RSSScraper`, được thêm `filter.any/none` miễn phí |
| 01 | "ship không cần content_selector, dựa density fallback" | ❌ **kế hoạch SAI** | vietnambiz **không có thẻ `<article>`** → mọi bài thành `partial` → `SELECTOR_BROKEN` → agent HOLD. Đã chốt `div.vnbcbc-body` + test regression |
| 02 | 9 feed chuyên mục TBTC, "zero new Python" | ❌ **kế hoạch SAI** | Feed chuyên mục là **ẢO** — server bỏ qua path, mọi URL trả cùng feed site-wide. → 1 feed + thêm `detail.category_meta` (~20 dòng, generic). **Sai lệch có chủ ý, owner đã duyệt** |
| 03 | TNCK 9 zone + CaptureMixin + sửa `.vn` | ✅ đúng hoàn toàn | — |
| 04 | `item_selector: div.thumbblock` | ❌ **kế hoạch SAI** | Class nằm trên thẻ `<a>` ảnh → khớp **0 node**. Item thật là `<article>`; link ảnh (không text) đứng trước link tiêu đề nên `select_one()` mất sạch bài |
| 05 | "NSO bị chặn network, không xây được" | ❌ **kế hoạch SAI** | G1 re-run **12/12 PASS** — chặn ban đầu chỉ chập chờn. Owner duyệt G2 → đã build v1 |

**Bốn chỗ kế hoạch sai đều là do dữ liệu thực tế khác giả định**, phát hiện bằng verify live
trước khi code, và mỗi chỗ đều có test khoá lại để không tái diễn.

## 8. Việc còn mở (không phải sai lệch)

| # | Việc | Ghi chú |
|---|---|---|
| 1 | ToS FireAnt | robots chặn ClaudeBot/GPTBot + `ai-train=no` |
| 2 | G1 NSO từ máy deploy | từng chập chờn |
| 3 | Gắn cron NSO | `run_periodic_reports.ps1` đã sẵn |
| 4 | tnck `verify_quality` 92.1% | 28 bài ngắn **hợp lệ** (bố cáo ĐHCĐ ~116 ký tự) — đề xuất `min_body` theo domain |
| 5 | fireant derive bù 36 Bronze | `morninger --once derive` |
| 6 | 5 file `phase-XX-*.md` gốc | **không tái tạo** — đã mất, nội dung cốt lõi đã chuyển vào `plan.md` + contract từng domain |
| 7 | 3 file luồng B | `daily_reporter.py`, `monitor_daily.py`, `test_daily_reporter.py` — lấy từ máy kia |

## 9. Kết luận

**Có, quy trình khớp kế hoạch** — và ở 4 chỗ kế hoạch sai so với thực tế, việc thực hiện đã
sửa đúng theo dữ liệu verify live, có test khoá lại.

Kiểm chứng cuối: `pytest -q` → **355 passed, 0 failed**.
