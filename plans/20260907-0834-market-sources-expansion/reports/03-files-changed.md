# Report 03 — Danh sách file thay đổi (để commit chọn lọc)

## ⚠️ CẢNH BÁO: working tree có HAI luồng công việc

`git status` hiện **114 file thay đổi**, nhưng **chỉ ~60 là của đợt này**.

**Nguyên nhân:** đầu phiên, OneDrive **không chạy** → mọi file trong repo là placeholder
không đọc được (`cat` trả "Permission denied", PowerShell báo *"The cloud file provider is
not running"*). `git status` lúc đó báo **clean**. Tôi khởi động OneDrive để đọc được code —
và nó **đồng bộ về một loạt thay đổi từ máy khác** (`C:\Users\anpt\...`, cùng máy đã tạo
`.venv` hỏng).

→ **ĐỪNG `git add -A`.** Sẽ commit lẫn công việc của người/máy khác.

---

## A. File CỦA ĐỢT NÀY (source expansion)

### Code
```
project/src/scrapers/rss_capture.py                    [MỚI]
project/src/scrapers/baodautu.py                       [MỚI]
project/src/scrapers/tnck.py                           [SỬA — thêm CaptureMixin]
project/src/scrapers/__init__.py                       [SỬA — +baodautu, +rss_capture]
project/src/core/config.py                             [SỬA — +resolve_source_domain()]
project/src/monitor/domain_reporter.py                 [SỬA — 2 call site, bỏ hack .vn]
project/scripts/domain_check.py                        [SỬA — 1 call site, bỏ hack .vn]
project/scripts/sample_articles.py                     [SỬA — 1 chuỗi mô tả]
project/scripts/maintenance/backfill_deferred.py       [MỚI]
project/scripts/maintenance/enrich_deferred.py         [XOÁ — Bronze-blind]
```

### Config
```
project/config/domains/vietnambiz.yaml                 [SỬA — enabled, rss_capture, 6 feed]
project/config/domains/tnck.yaml                       [SỬA — enabled, 9 zone, capture]
project/config/domains/baodautu.yaml                   [SỬA — RSS → HTML listing]
project/config/domains/thoibaotaichinhvietnam.yaml     [MỚI]
```

### Domain contracts (thư mục mới)
```
project/domains/vietnambiz/{schema.yaml,README.md,changelog.md}
project/domains/tnck/{schema.yaml,README.md,changelog.md}
project/domains/baodautu/{schema.yaml,README.md,changelog.md}
project/domains/thoibaotaichinhvietnam/{schema.yaml,README.md,changelog.md}
project/domains/vneconomy/{schema.yaml,changelog.md}        [bổ sung nợ cũ]
```

### Tests + fixtures
```
project/tests/_fakes.py                                [SỬA — +listing_html]
project/tests/test_rss_capture.py                      [MỚI — 12 case]
project/tests/test_thoibaotaichinhvietnam.py           [MỚI — 7 case]
project/tests/test_baodautu.py                         [MỚI — 14 case]
project/tests/test_backfill_deferred.py                [MỚI — 6 case]
project/tests/test_tnck.py                             [VIẾT LẠI — 13 case]
project/tests/fixtures/vietnambiz_capture_feed.xml     [MỚI]
project/tests/fixtures/vietnambiz_detail_page.html     [MỚI]
project/tests/fixtures/tbtc_capture_feed.xml           [MỚI]
project/tests/fixtures/tbtc_detail_page.html           [MỚI]
project/tests/fixtures/tnck_zone_list.json             [MỚI]
project/tests/fixtures/tnck_detail_page.html           [MỚI]
project/tests/fixtures/baodautu_listing_d2.html        [MỚI]
project/tests/fixtures/baodautu_detail_page.html       [MỚI]
```

### Docs
```
project/README.md                                      [SỬA — đếm nguồn 3→7]
project/docs/domains/README.md                         [SỬA — truth-sync ma trận]
project/docs/domains/vn-rss.md                         [SỬA]
project/docs/domains/api-scrapers.md                   [SỬA — section tnck]
project/docs/domains/html-scrapers.md                  [MỚI]
project/docs/design/03-source-strategy.md              [SỬA — tier rss_capture]
project/docs/design/06-raw-html-capture.md             [SỬA — quy trình backfill]
project/docs/design/16-periodic-report-scraper.md      [MỚI — design G2 NSO]
project/docs/dev/03-adding-a-source.md                 [SỬA — +§2b]
project/docs/dev/06-raw-html-capture-guide.md          [SỬA]
project/docs/skills/rss-sources.md                     [SỬA]
project/docs/skills/tnck.md                            [SỬA — sửa sai date/RSS]
project/docs/runbook.md                                [SỬA — +section backfill]
project/docs/others/phase1-report.md                   [SỬA — ghi chú script đã xoá]
```

### Kế hoạch
```
plans/20260907-0834-market-sources-expansion/          [MỚI — toàn bộ]
```

---

## B. File KHÔNG PHẢI của đợt này (OneDrive đồng bộ từ máy khác)

Đây là một feature khác đang làm dở — **"Zero-Waste / gold agent payload"**, batch manifest,
okf catalog, daily reporter. **Không phải tôi viết.**

```
.agents/**                                    AGENTS.md
docs/SESSION-LATEST.md                        docs/stories/US-004,US-006,US-007*.md
okf/**                                        (catalog datasets/tables/pipelines)
project/src/agent/packet.py, runner.py
project/src/agent/pruner.py, archive.py, batch_handoff.py, manifest.py   [file mới]
project/src/db/store.py                       project/src/morninger.py
project/src/orchestrator.py                   project/src/pipeline/derive.py
project/src/export/user_output.py             project/src/handoff/catalog.py
project/src/monitor/daily_reporter.py         project/scripts/monitor_daily.py
project/scripts/agent_export.py, agent_ingest.py, l1_ingest.py, l1_route.py
project/scripts/make_user_template.py, run_agent_hierarchy.py, run_daily.ps1, run_once.py
project/config/entities/users/AnPT.yaml       project/data/entities/entities.xlsx
project/reports/                              project/daily_log.txt
```

⚠️ Tôi **không đụng** vào bất kỳ file nào ở nhóm B. Nhưng vì chúng nằm chung working tree nên
`pytest` đã chạy **cùng** chúng — 310 pass là kết quả của **cả hai** luồng cộng lại.

---

## C. File sinh ra khi chạy (nên bỏ qua / kiểm tra .gitignore)

✅ **Đã kiểm tra `.gitignore` — phần lớn đã được che đúng:**

| Đường dẫn | Trạng thái |
|---|---|
| `data/raw_html/**` (Bronze) | ✅ ignored (`**/data/raw_html/`) |
| `data/silver/**` | ✅ ignored (`**/data/silver/`) |
| `data/exports/**` | ✅ ignored (`**/data/exports/`) |
| `data/monocle.db*` | ✅ ignored (`project/.gitignore:13 data/*.db`) |
| `logs/**` | ✅ ignored |
| `.venv/` | ✅ ignored (đã sửa `pyvenv.cfg`, backup `pyvenv.cfg.bak`) |

⚠️ **Hai thứ KHÔNG được che, cần anh quyết:**
```
?? project/data/reports/daily/tnck-2026-09-07.md        ← sinh ra khi chạy domain_check
?? project/data/reports/daily/vietnambiz-2026-09-07.md  ← nt
 M project/data/entities/entities.xlsx                   ← KHÔNG phải tôi sửa (nhóm B)
```
Đề xuất: thêm `**/data/reports/` vào `.gitignore` (report ngày là output chạy máy, không phải
mã nguồn). `entities.xlsx` thuộc nhóm B — đừng commit chung với đợt này.

---

## D. Gợi ý commit

```bash
# chỉ stage phần source expansion
git add project/src/scrapers/ project/src/core/config.py \
        project/src/monitor/domain_reporter.py \
        project/scripts/domain_check.py project/scripts/sample_articles.py \
        project/scripts/maintenance/backfill_deferred.py \
        project/config/domains/ project/domains/ \
        project/tests/ project/docs/ project/README.md \
        plans/20260907-0834-market-sources-expansion/
git rm --cached project/scripts/maintenance/enrich_deferred.py   # hoặc git add -u cho file đã xoá

git status   # RÀ LẠI trước khi commit — đảm bảo không lẫn nhóm B
```

**Kiểm tra `.gitignore`** cho `data/raw_html/`, `data/silver/`, `data/monocle.db*`, `logs/`
trước khi commit — README nói chúng gitignored, nhưng `git status` đang hiện
`project/data/entities/entities.xlsx` và `project/data/reports/` nên cần xác nhận lại.
