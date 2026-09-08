# Report 05 — Sự cố OneDrive xoá file + khôi phục, 2026-09-07

`pytest -q` = **355 passed, 0 failed** (bằng đúng con số trước sự cố). Phần việc của tôi
đã khôi phục **đầy đủ**. Nhưng có 2 file của **luồng B** vẫn mất — xem §4.

---

## 1. Chuyện gì đã xảy ra

**Bối cảnh.** Đầu phiên, OneDrive **không chạy** → mọi file trong repo là placeholder không đọc
được (`cat` trả "Permission denied"; PowerShell: *"The cloud file provider is not running"*).
`git status` lúc đó báo **clean**. Tôi khởi động OneDrive để đọc được code.

**Hậu quả.** OneDrive bắt đầu đồng bộ hai chiều với máy kia (`C:\Users\anpt\...`) và **xoá các
file mới mà snapshot bên đó không có**.

**Quy luật quan sát được — rất rõ ràng:**

| Loại thay đổi | Kết quả |
|---|---|
| **SỬA** file đã tồn tại | ✅ **giữ nguyên 100%** |
| **TẠO MỚI** file | ❌ **bị xoá** |

Ví dụ minh hoạ: `src/scrapers/tnck.py` (sửa) giữ được `CaptureMixin`; nhưng
`src/scrapers/rss_capture.py` (mới) biến mất — dù `src/scrapers/__init__.py` (sửa) vẫn import nó
→ **repo hỏng**: `ImportError: cannot import name 'baodautu'`.

Mất luôn cả 4 báo cáo trong `plans/.../reports/`, `research/`, `scout/`.

---

## 2. Chẩn đoán đã làm

| Nguồn khôi phục | Kết quả |
|---|---|
| Windows Recycle Bin | ❌ trống (0 file khớp) |
| Volume Shadow Copy (Previous Versions) | ❌ không có / không đủ quyền |
| Quét toàn bộ `C:\Users\An Thanh Pham` | ❌ không thấy bản sao nào |
| **`__pycache__/*.pyc`** | ✅ **còn** — xác nhận trạng thái cuối, kể cả `periodic_reports.cpython-314.pyc` lúc 16:21 |
| **`data/raw_html/` + `data/raw_reports/`** | ✅ **còn nguyên** — Bronze không mất byte nào |

---

## 3. Cách khôi phục (đã thực hiện sau khi owner pause sync)

### 3.1 Code + config — viết lại từ context hội thoại
`rss_capture.py`, `baodautu.py`, `periodic_reports.py`, `fetch_periodic_reports.py`,
`maintenance/backfill_deferred.py`, `config/domains/thoibaotaichinhvietnam.yaml`,
`docs/design/16-periodic-report-scraper.md`, `docs/domains/html-scrapers.md`.

### 3.2 Fixture trang detail — tái tạo TỪ BRONZE (không cần mạng)
Bronze là WORM và còn nguyên → lấy thẳng file `.html` đã capture làm fixture, **byte-exact**.
Tìm đúng bài mà test cần bằng cách khớp chuỗi đặc trưng (`#content_detail_news`, `'+content+'`,
`vnbcbc-body`, `article:section`…).

Đây là lợi ích cụ thể của kiến trúc Bronze-first: **mất code không mất dữ liệu**, và fixture
tái tạo được mà không phụ thuộc site còn sống hay không.

### 3.3 Fixture feed/list — tải lại từ mạng
Bronze chỉ lưu trang detail, không lưu trang danh sách → 4 file phải fetch lại:
`vietnambiz_capture_feed.xml`, `tbtc_capture_feed.xml`, `tnck_zone_list.json`,
`baodautu_listing_d2.html`.

### 3.4 Test — viết lại 5 file
`test_rss_capture` (12) · `test_thoibaotaichinhvietnam` (7) · `test_tnck` (13) ·
`test_baodautu` (15) · `test_periodic_reports` (23) · `test_backfill_deferred` (12).

Nhân dịp này **thêm test mới**: `test_div_thumbblock_would_match_nothing` khoá lại cái bẫy
baodautu (`div.thumbblock` khớp 0 node dù chuỗi có trong HTML).

### 3.5 Xác minh
- `pytest -q` → **355 passed, 0 failed**
- `REGISTRY` đủ 9 key; `list_domains()` đủ **8 domain enabled**
- `resolve_source_domain()` đúng cho cả 8 (`tnck` → `tinnhanhchungkhoan.vn`)
- `fetch_periodic_reports.py --list` → 3 báo cáo NSO còn trong DB, Bronze `.binmeta.json` nguyên

---

## 4. ⚠️ CÒN MẤT — thuộc luồng B, tôi KHÔNG khôi phục được

Tôi chưa bao giờ đọc nội dung các file này nên không thể viết lại:

```
src/monitor/daily_reporter.py     ← MẤT
scripts/monitor_daily.py          ← MẤT
tests/test_daily_reporter.py      ← MẤT
```

**Ảnh hưởng thực tế:** `scripts/run_daily.ps1` gọi
`& $Py 'scripts/monitor_daily.py' --days $Days --save-md` ở 3 nhánh → **pipeline daily của
luồng B sẽ lỗi** khi chạy tới bước monitor.

**Đề xuất:** lấy lại 3 file này từ **máy kia** (`C:\Users\anpt\...`) hoặc từ OneDrive web
Recycle Bin — bên đó là nguồn gốc của chúng.

(`src/agent/{pruner,archive,batch_handoff,manifest}.py`, `tests/test_pruner_and_batch.py`,
`tests/test_batch_manifest.py` đã tự quay lại sau khi pause — không cần làm gì.)

---

## 5. Bài học vận hành — cần xử lý trước khi làm tiếp

**Nguyên nhân gốc không phải OneDrive, mà là: repo dùng chung qua OneDrive giữa 2 máy, và
công việc chưa commit.** Git là thứ đáng ra phải bảo vệ điều này.

Đề xuất, theo thứ tự ưu tiên:

1. **Commit sớm và thường xuyên.** Nếu các file mới đã được `git add` + commit thì lần sync này
   không xoá được gì — khôi phục chỉ là `git checkout`.
2. **Đưa repo ra khỏi OneDrive.** Repo git + thư mục `data/` nặng không nên nằm trong thư mục
   đồng bộ. Dùng git remote để chia sẻ giữa 2 máy thay vì OneDrive.
   (Repo đã có sẵn `MONOCLE_DATA_DIR` / `MONOCLE_DB_PATH` để đẩy `data/` ra ngoài OneDrive —
   xem `src/core/config.py:load_settings`.)
3. **Nếu buộc phải giữ trong OneDrive:** chỉ mở OneDrive khi cần sync, và **commit trước** mỗi
   lần bật.

---

## 6. Trạng thái hiện tại

| Hạng mục | Trạng thái |
|---|---|
| `pytest -q` | ✅ **355 passed, 0 failed** |
| Domain enabled | ✅ **8** — cafef, vietstock, vneconomy, vietnambiz, thoibaotaichinhvietnam, tnck, baodautu, fireant |
| `domains/` contracts | ✅ 8/8 (tự quay lại sau pause) |
| Bronze `data/raw_html/` | ✅ 8 domain, không mất byte nào |
| Bronze `data/raw_reports/` | ✅ NSO 3 báo cáo + 6 attachment |
| Luồng B | ⚠️ **thiếu 3 file** (§4) |
| OneDrive sync | ⏸️ **đang pause** — đừng bật lại trước khi commit |

**Việc tiếp theo của owner:**
1. `git add` + commit ngay phần source expansion (xem `reports/03-files-changed.md` — nhưng lưu ý
   file đó cũng đã mất, danh sách rút gọn ở §6 dưới).
2. Lấy lại 3 file luồng B từ máy kia.
3. Chỉ bật lại OneDrive sync **sau khi** đã commit.

### Danh sách file cần commit (phần source expansion)

```
project/src/scrapers/{rss_capture,baodautu,tnck,fireant,__init__}.py
project/src/pipeline/{periodic_reports,silver_builder}.py
project/src/crawler/raw_store.py
project/src/core/config.py
project/src/db/store.py
project/src/monitor/domain_reporter.py
project/scripts/{fetch_periodic_reports,domain_check,sample_articles,validate_capture}.py
project/scripts/run_periodic_reports.ps1
project/scripts/maintenance/backfill_deferred.py
project/scripts/maintenance/enrich_deferred.py            ← ĐÃ XOÁ (git rm)
project/config/domains/{vietnambiz,tnck,baodautu,fireant,thoibaotaichinhvietnam}.yaml
project/domains/{vietnambiz,tnck,baodautu,thoibaotaichinhvietnam,fireant,vneconomy}/
project/tests/test_{rss_capture,thoibaotaichinhvietnam,tnck,baodautu,fireant,periodic_reports,backfill_deferred}.py
project/tests/_fakes.py
project/tests/fixtures/{vietnambiz_*,tbtc_*,tnck_zone_list.json,tnck_detail_page.html,baodautu_*}
project/docs/design/{03-source-strategy,06-raw-html-capture,16-periodic-report-scraper}.md
project/docs/domains/{README,vn-rss,api-scrapers,html-scrapers}.md
project/docs/dev/{03-adding-a-source,06-raw-html-capture-guide}.md
project/docs/skills/{rss-sources,tnck}.md
project/docs/runbook.md
project/docs/others/phase1-report.md
project/README.md
project/.gitignore
plans/20260907-0834-market-sources-expansion/
```

⚠️ **ĐỪNG `git add -A`** — sẽ commit lẫn luồng B (`okf/`, `.agents/`, `src/agent/*`,
`src/export/*`, `scripts/l1_*`, `run_daily.ps1`, `config/entities/`, `data/entities/`…).
