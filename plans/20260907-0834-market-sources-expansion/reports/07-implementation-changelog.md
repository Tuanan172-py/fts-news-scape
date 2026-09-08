# Report 07 — Changelog implement (bản đối chiếu phiên bản)

Ngày 2026-09-07 · Phạm vi: mở rộng nguồn tin theo framework Bronze · Code root `project/`

Mục đích: **mốc so sánh cho các phiên bản về sau**. Mọi con số dưới đây lấy từ git thật,
không phải trí nhớ.

---

## 1. Hai commit của đợt này

| Commit | Tiêu đề | Files | +/- |
|---|---|---|---|
| `7bb46ba` | `feat(sources): Bronze-first expansion — 5 nguồn mới + NSO periodic reports` | 55 | **+10468 / −358** |
| `75b8b6c` | `docs(sources): khôi phục domain contract + biên bản rà soát kế hoạch` | 16 | **+731 / −0** |

Author = committer = `An Pham Thanh <anpt11172@gmail.com>` cho **cả hai**.
**Không** có trailer `Co-Authored-By` / `Claude-Session`.

Trước → sau:

| Chỉ số | Trước | Sau |
|---|---|---|
| Nguồn enabled | 3 | **8** |
| `pytest -q` | 273 passed | **355 passed, 0 failed** |
| Method có Bronze capture | `cafef`, `vietstock`, `vneconomy` | + `rss_capture`, `tnck`, `baodautu`, `fireant` |
| Driver ngoài pipeline domain | (không có) | `periodic_reports` (NSO) |

---

## 2. File MỚI (A) — 24 file code/config/docs + 8 fixture

### 2.1 Source code

| File | Dòng | Vai trò |
|---|---|---|
| `src/scrapers/rss_capture.py` | 97 | **Tài sản framework.** `RssCaptureScraper(CaptureMixin, RSSScraper)` — nguồn RSS mới từ nay = 1 file YAML, 0 dòng Python |
| `src/scrapers/baodautu.py` | 202 | HTML-listing scraper **đầu tiên** của repo |
| `src/pipeline/periodic_reports.py` | 359 | Driver báo cáo định kỳ NSO — **ngoài** vòng đời domain |
| `scripts/fetch_periodic_reports.py` | 115 | CLI cho driver trên (`--dry-run` / `--list` / `--limit`) |
| `scripts/maintenance/backfill_deferred.py` | 362 | Thay `enrich_deferred.py` đã xoá; **đọc được Bronze** (kể cả JSON) |
| `scripts/run_periodic_reports.ps1` | 41 | Wrapper cron hàng tháng |

### 2.2 Config + contract

- `config/domains/thoibaotaichinhvietnam.yaml` — nguồn mới hoàn toàn
- `domains/{baodautu,fireant,thoibaotaichinhvietnam,tnck,vietnambiz,vneconomy}/{schema.yaml,changelog.md}` — 12 file contract

### 2.3 Docs

- `docs/design/16-periodic-report-scraper.md` (210 dòng) — thiết kế NSO; §3 chốt nguyên tắc tách biệt
- `docs/domains/html-scrapers.md` (105 dòng) — chuẩn cho nhóm HTML-listing (nhóm mới)

### 2.4 Test + fixture

| Test file | Số test |
|---|---|
| `test_rss_capture.py` | 12 |
| `test_thoibaotaichinhvietnam.py` | 7 |
| `test_baodautu.py` | 15 |
| `test_periodic_reports.py` | 13 |
| `test_backfill_deferred.py` | 12 |
| `test_tnck.py` (mở rộng) | 13 |
| `test_fireant.py` (viết lại) | 11 |

Fixture mới (8): `vietnambiz_{capture_feed.xml,detail_page.html}`,
`tbtc_{capture_feed.xml,detail_page.html}`, `tnck_{zone_list.json,detail_page.html}`,
`baodautu_{listing_d2.html,detail_page.html}`.

> 4 fixture trang detail được **tái tạo byte-exact từ Bronze** sau sự cố mất file —
> bằng chứng thực tế cho giá trị của kiến trúc Bronze-first (report 05 §3.2).

---

## 3. File SỬA (M) — giao diện công khai thay đổi

| File | Thay đổi | Ảnh hưởng |
|---|---|---|
| `src/core/config.py` | **+`resolve_source_domain(name)`** — dotted → contract `domain:` → netloc `base_url` → legacy `<name>.vn` | Sửa bẫy `.vn`-suffix toàn repo. `tnck` → `tinnhanhchungkhoan.vn` (trước: `tnck.vn` → báo cáo 0 bài) |
| `src/crawler/raw_store.py` | **+`save_binary(domain,url,key,response,*,fetched_at)`**; meta ghi `.binmeta.json` | Đuôi khác `.meta.json` **có chủ đích**: `derive` rglob không quét trúng attachment |
| `src/pipeline/silver_builder.py` | **+`_html_from_json()`**, +`_JSON_HTML_FIELDS`; `build()` rẽ nhánh khi content-type là JSON | Bronze JSON (fireant) nay ra Silver được. Domain HTML không đổi hành vi |
| `src/db/store.py` | **+bảng `periodic_reports`**, `UNIQUE(source, report_type, period, revision)` | Dedup theo **kỳ báo cáo**, KHÔNG theo URL/slug (slug NSO sai năm) |
| `src/scrapers/tnck.py` | `TnckScraper(CaptureMixin, BaseScraper)`; `SOURCE_DOMAIN` non-www; zone 1 → **9** | Có Bronze thật. URL fetch vẫn giữ host `www` |
| `src/scrapers/fireant.py` | `FireAntScraper(CaptureMixin, BaseScraper)`; gọi thẳng `raw_store.save()`; đọc camelCase `postID`/`postSource`; `WEB_URL` dashboard | Bronze = JSON gốc byte-exact |
| `src/scrapers/__init__.py` | đăng ký `_rss_capture`, `baodautu` | `build_scraper()`: per-name thắng per-method |
| `src/monitor/domain_reporter.py` | dùng `resolve_source_domain` (2 chỗ) | hết báo cáo rỗng |
| `scripts/domain_check.py` | như trên | |
| `scripts/{sample_articles,validate_capture}.py` | nhận domain mới | |
| `config/domains/vietnambiz.yaml` | `method: rss_capture`, 6 feed, `content_selector: div.vnbcbc-body` | |
| `config/domains/tnck.yaml` | 9 zone `[1,4,6,11,21,26,29,33,39]`, `pages_per_cycle: 1` | zone 8 (Điều tra) bị loại — nội dung lệch hình sự/tiêu dùng |
| `config/domains/baodautu.yaml` | **xoá hẳn block `rss:`**, `item_selector: article`, `link_pattern` theo `-dNN.html`, 6 chuyên mục | loại d80 (PR) |
| `config/domains/fireant.yaml` | `enabled: true`, thêm block `capture` | |
| `.gitignore` | +`data/raw_reports/`, `data/reports/` | |
| `README.md` + 11 file docs | truth-sync (ma trận cũ ghi "22 enabled" trong khi thực tế 3) | |

## 4. File XOÁ (D)

| File | Lý do |
|---|---|
| `scripts/maintenance/enrich_deferred.py` (68 dòng) | **Bronze-blind** — fetch lại từ mạng thay vì đọc Bronze đã có. Vi phạm WORM. Thay bằng `backfill_deferred.py` |

---

## 5. Giao diện mới cần biết khi nâng cấp

```python
# src/core/config.py
resolve_source_domain(name: str) -> str

# src/crawler/raw_store.py
RawStore.save_binary(domain, url, key, response, *, fetched_at) -> dict

# src/pipeline/silver_builder.py
_html_from_json(raw_text: str) -> str | None

# src/pipeline/periodic_reports.py
parse_period(title: str) -> tuple[str, str] | None      # tu TITLE, khong tu slug
extract_attachments(html: str, page_url: str) -> list[dict]
class PeriodicReportSource:  discover / identify / run / _capture_report / _upsert

# src/scrapers/rss_capture.py
class RssCaptureScraper(CaptureMixin, RSSScraper)       # method: rss_capture
```

CLI mới:

```
python scripts/fetch_periodic_reports.py [--dry-run|--list] [--limit N]
python scripts/maintenance/backfill_deferred.py <domain> [--limit N] [--fetch] [--dry-run] [--dates-only]
pwsh scripts/run_periodic_reports.ps1
```

Khoá config mới trong `config/domains/*.yaml`:
`method: rss_capture` · `detail.category_meta` · `detail.date_scope_selector` ·
`listing.{item_selector, link_pattern, categories}`.

Storage root mới: `data/raw_reports/<host>/<yyyymmdd>/` · hậu tố meta mới `.binmeta.json`.
Bảng DB mới: `periodic_reports`.

---

## 6. Đặc thù từng nguồn đã verify (đừng "sửa" lại)

| Nguồn | Đặc thù | Nếu quên |
|---|---|---|
| vietnambiz | **không có thẻ `<article>`** → bắt buộc `div.vnbcbc-body` | 100% bài `partial` → `SELECTOR_BROKEN` → agent HOLD |
| TBTC | feed theo chuyên mục là **ẢO** (server bỏ qua path, trả cùng 1 feed site-wide) | 9 feed = 9 lần tải trùng |
| tnck | listing chỉ có API zone; `/rss.html` = 13 bytes, `/rss/*.rss` = 302 | |
| tnck | `source_domain` **non-www** nhưng URL fetch giữ `www` | lệch identity |
| baodautu | `div.thumbblock` nằm trên thẻ `<a>` ảnh → khớp **0 node**; item thật là `<article>` | mất sạch bài |
| baodautu | trang 2+ **không** có dấu `/` cuối | 404 |
| baodautu | link ảnh (không text) đứng **trước** link tiêu đề | `select_one()` lấy nhầm |
| NSO | slug **không tin được** (có bản `…-2025-2` sai năm) → parse kỳ từ **title** | dedup sai |
| NSO | tên file attachment **phân biệt hoa/thường**; `save_binary` tự thêm đuôi | `.xlsx.xlsx` |
| fireant | JSON camelCase `postID`/`postSource`; epoch có thể là số hoặc chuỗi | |

Mỗi mục trên đều có **test khoá lại**, ví dụ `test_default_article_selector_would_break`,
`test_div_thumbblock_would_match_nothing`.

---

## 7. Bốn chỗ kế hoạch sai so với dữ liệu thật

| Kế hoạch | Thực tế | Đã làm |
|---|---|---|
| vietnambiz ship không cần `content_selector` | không có `<article>` | chốt `div.vnbcbc-body` + test regression |
| TBTC 9 feed chuyên mục, "zero new Python" | feed chuyên mục ảo | 1 feed + `detail.category_meta` (~20 dòng generic) — **sai lệch có chủ ý, owner duyệt** |
| baodautu `item_selector: div.thumbblock` | khớp 0 node | `article` + duyệt mọi anchor |
| NSO "bị chặn network, không xây được" | G1 re-run **12/12 PASS** | owner mở G2 → build v1 |

Chi tiết: `reports/06-plan-compliance-audit.md` §7.

---

## 8. Trạng thái dữ liệu tại thời điểm chốt

| Domain | articles | bronze | silver | package | work_item |
|---|---|---|---|---|---|
| vietnambiz | 170 | 170 | 170 | 170 | 170 |
| thoibaotaichinhvietnam | 24 | 24 | 24 | 24 | 24 |
| tnck | 354 | 354 | 354 | 354 | 354 |
| baodautu | 109 | 109 | 109 | 109 | 109 |
| fireant | 357 | 358 | 322 | 322 | 322 |
| cafef | 3733 | 1405 | 1376 | 1376 | 1364 |
| vietstock | 1272 | 815 | 787 | 787 | 797 |
| vneconomy | 1200 | 783 | 768 | 768 | 778 |

fireant `bronze 358 > silver 322`: 36 file Bronze kéo về sau lần `derive` cuối —
chạy `python -m src.morninger --once derive` là khớp.

NSO: 3 báo cáo trong `periodic_reports`, 3 trang HTML + 6 attachment (3 `.xlsx` mở được thật)
trong `data/raw_reports/`, **0 work_item mồ côi**.

`verify_quality`: vietnambiz 100% · baodautu 99.1% · TBTC 95.8% · tnck 92.1% (28 bố cáo ĐHCĐ
~116 ký tự — **ngắn hợp lệ**, không phải lỗi).

Audit tự động `96/99 PASS`; 3 "FAIL" là giả — Bronze cũ bị OneDrive dehydrate, `0 sai hash`.

---

## 9. Cách đối chiếu ở phiên bản sau

```bash
git log --oneline 7bb46ba~1..75b8b6c            # 2 commit cua dot nay
git diff --stat 7bb46ba~1 75b8b6c -- project/   # tong thay doi
pytest -q                                       # moc: 355 passed
python -c "from src.core.config import list_domains; print(sorted(list_domains()))"  # moc: 8
```

---

## Câu hỏi còn mở

1. **ToS FireAnt** — robots chặn ClaudeBot/GPTBot + `Content-Signal: ai-train=no`. Ràng buộc cứng
   hiện hành: **không dùng dữ liệu fireant để train/fine-tune**. Nếu tài khoản không cho phép →
   `enabled: false`.
2. NSO chạy cron hay tay? `run_periodic_reports.ps1` đã sẵn nhưng chưa gắn lịch; nên chạy
   `--dry-run` từ máy deploy trước (NSO từng chập chờn).
3. `verify_quality` có nên cho `min_body` theo domain (tnck bố cáo ngắn hợp lệ)?
4. 3 file luồng B (`daily_reporter.py`, `monitor_daily.py`, `test_daily_reporter.py`) — lấy từ
   máy kia hay viết lại?
5. Đưa repo/`data/` ra khỏi OneDrive? (`MONOCLE_DATA_DIR` / `MONOCLE_DB_PATH` đã hỗ trợ sẵn.)
