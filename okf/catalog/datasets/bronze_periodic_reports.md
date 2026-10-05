---
type: Dataset
title: Bronze Periodic Reports
description: Kho WORM riêng cho báo cáo định kỳ NSO — data/raw_reports/**, gồm trang HTML và file số liệu gốc .xlsx/.docx.
resource: "project/data/raw_reports/**"
tags: [bronze, worm, nso, statistics, binary]
status: stable
generated:
  at: 2026-09-08T00:00:00Z
sources:
  - id: raw-store
    resource: project/src/crawler/raw_store.py
    title: RawStore.save / RawStore.save_binary
  - id: driver
    resource: project/src/pipeline/periodic_reports.py
    title: PeriodicReportSource
  - id: design-16
    resource: project/docs/design/16-periodic-report-scraper.md
    title: Thiết kế scraper báo cáo định kỳ
sources_last_checked: 2026-09-08
---

Kho Bronze **thứ hai** của hệ thống, tách hẳn khỏi [`data/raw_html/`](bronze_raw_html.md).
Chứa báo cáo định kỳ của Cục Thống kê: trang HTML công bố **và** file số liệu gốc đính kèm.

# Bố cục

```
data/raw_reports/nso.gov.vn/<yyyymmdd>/
    <key>.html          + <key>.meta.json        <- trang cong bo
    <key>.xlsx          + <key>.binmeta.json     <- file so lieu goc
    <key>.docx          + <key>.binmeta.json
```

# Vì sao là root riêng, không nằm trong `data/raw_html/`

Đây là ràng buộc thiết kế cứng, có 3 lý do đo được:[^design-16]

1. **`derive` quét `data/raw_html/**` bằng `rglob("*.meta.json")`.** Để báo cáo ở đó thì mỗi
   attachment sinh một work_item mồ côi. Lần chạy thử trước khi tách: `derive` báo
   `432 processed, 426 ok` với 3 work_item mồ côi + 6 binary meta bị đếm nhầm `raw_missing`.
   Sau khi tách: **292/292 ok**.
2. **Hậu tố `.binmeta.json`** cho attachment — khác `.meta.json` — nên kể cả khi hai cây bị gộp
   nhầm trong tương lai, glob của derive vẫn không khớp trúng file nhị phân.
3. Báo cáo **không có định danh bài báo** (`url_title_hash`), nên không thể đi qua Silver.

# Tính chất

- **WORM** như Bronze bài báo: ghi một lần bằng `RawStore.save()` / `RawStore.save_binary()`
  **ngay sau fetch, trước mọi parse**; không bao giờ sửa file đã ghi.[^raw-store]
- `save_binary()` tự suy đuôi file từ `Content-Type` (`.pdf`, `.xlsx`, `.docx`…) và **tự thêm**
  đuôi — nên `key` truyền vào phải **đã bỏ** phần mở rộng, nếu không sẽ ra `.xlsx.xlsx`.
- Tên file gốc **phân biệt hoa/thường**; chỉ hạ chữ thường khi *so khớp*, không khi *lưu*.
- `.gitignore`: `data/raw_reports/` — không vào git. Đây là nội dung bên thứ ba, lưu nội bộ.

# Kiểm chứng toàn vẹn

```bash
python scripts/fetch_periodic_reports.py --list
python -c "import zipfile,glob; print(all(zipfile.is_zipfile(f) for f in glob.glob('data/raw_reports/**/*.xlsx', recursive=True)))"
```

# Liên quan

- Bảng [periodic_reports](../tables/periodic_reports.md) — sổ đăng ký, dedup theo kỳ
- Pipeline [Periodic Reports](../pipelines/periodic_reports.md) — ngoài chu kỳ 15 phút
- [Bronze Raw Store](bronze_raw_html.md) — kho Bronze của bài báo (tách biệt)

[^raw-store]: [RawStore.save_binary](project/src/crawler/raw_store.py)
[^design-16]: [Thiết kế scraper báo cáo định kỳ](project/docs/design/16-periodic-report-scraper.md)
