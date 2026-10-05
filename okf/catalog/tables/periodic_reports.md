---
type: SQLite Table
title: periodic_reports
description: Sổ đăng ký báo cáo định kỳ của cơ quan thống kê (NSO) — dedup theo (report_type, period), KHÔNG theo URL.
resource: "project/data/monocle.db (table: periodic_reports)"
tags: [nso, periodic, bronze, statistics, out-of-cycle]
status: stable
generated:
  at: 2026-09-08T00:00:00Z
sources:
  - id: driver
    resource: project/src/pipeline/periodic_reports.py
    title: PeriodicReportSource — discover / identify / capture / upsert
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: design-16
    resource: project/docs/design/16-periodic-report-scraper.md
    title: Thiết kế scraper báo cáo định kỳ
sources_last_checked: 2026-09-08
---

`periodic_reports` là bảng **duy nhất** nằm ngoài vòng đời bài báo. Nó ghi các báo cáo định kỳ
do Cục Thống kê (`nso.gov.vn`) công bố — ví dụ "Báo cáo tình hình kinh tế – xã hội tháng 8/2026" —
cùng các file số liệu gốc `.xlsx`/`.docx` đính kèm.[^design-16]

**Vì sao không dùng `articles`.** Một báo cáo không phải một bài báo: nó có **kỳ** (period), có
**bản hiệu đính** (revision), và mang file nhị phân. Định danh nghiệp vụ là
`(source, report_type, period)` chứ không phải URL — NSO đăng lại cùng một kỳ ở nhiều slug, và
**slug không đáng tin** (đã gặp bản `…-2025-2` mang sai năm). Vì vậy kỳ được parse từ **title**,
không bao giờ từ slug.[^driver]

# Dedup và hiệu đính

- `UNIQUE(source, report_type, period, revision)` — mỗi kỳ chỉ một hàng cho mỗi bản.
- `modified_at` đổi ⇒ NSO đã hiệu đính ⇒ `revision` tăng, **giữ nguyên bản cũ**. Lịch sử số liệu
  công bố là dữ liệu, không phải rác.
- Chạy lại driver nhiều lần là **idempotent**: không sinh hàng mới nếu `modified_at` không đổi.

# Schema

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `source` | TEXT NOT NULL | `nso` |
| `report_type` | TEXT NOT NULL | `monthly` \| `quarterly` \| `annual` |
| `period` | TEXT NOT NULL | `2026-08` \| `2026-Q2` \| `2026` — parse từ **title** |
| `title` | TEXT NOT NULL | Tiêu đề gốc |
| `source_url` | TEXT NOT NULL | URL trang báo cáo |
| `remote_id` | TEXT | WordPress post id |
| `published_at` | TEXT | ISO +07:00 |
| `modified_at` | TEXT | ISO +07:00 — đổi = bản hiệu đính |
| `html_path` | TEXT | Bronze HTML trong `data/raw_reports/**` |
| `attachments_json` | TEXT | `[{url, path, sha256, bytes, content_type}]` |
| `capture_status` | TEXT | trạng thái capture |
| `revision` | INTEGER DEFAULT 1 | tăng khi `modified_at` đổi |
| `created_at` / `updated_at` | TEXT | |

**Constraints:** `UNIQUE(source, report_type, period, revision)` ·
**Index:** `idx_periodic_period` trên `(source, report_type, period)`

# Tách biệt khỏi pipeline bài báo

Ràng buộc thiết kế, **không được phá**:[^design-16]

- Bronze ở root riêng `data/raw_reports/` — `derive` không quét tới, nên không sinh Silver/
  work-package/work_item mồ côi.
- Attachment nhị phân dùng hậu tố meta `.binmeta.json`, **khác** `.meta.json` của trang HTML, để
  `rglob("*.meta.json")` của derive không khớp trúng.
- NSO **không** là domain thứ 25: không có `config/domains/nso.yaml`, không có
  `src/scrapers/nso.py`, không vào `REGISTRY`.

# Common Query Patterns

### Các kỳ đã thu, mới nhất trước

```sql
SELECT report_type, period, revision, published_at, title
FROM periodic_reports
WHERE source = 'nso'
ORDER BY period DESC, revision DESC;
```

### Kỳ có bản hiệu đính (revision > 1)

```sql
SELECT period, COUNT(*) AS revisions
FROM periodic_reports
WHERE source = 'nso'
GROUP BY report_type, period
HAVING revisions > 1;
```

### Kỳ tháng bị thiếu trong 12 tháng gần nhất

```sql
SELECT period FROM periodic_reports
WHERE source='nso' AND report_type='monthly'
ORDER BY period DESC LIMIT 12;
-- doi chieu bang tay voi lich cong bo (~ngay 3 hang thang)
```

# Joins

Không join với `articles`. Đây là nhánh dữ liệu độc lập — liên kết duy nhất tới phần còn lại của
hệ là **ngữ nghĩa** (số liệu KTXH được các domain tin tức trích dẫn lại).

# Pipeline liên quan

- Sinh bởi [Periodic Reports](../pipelines/periodic_reports.md) — **ngoài** chu kỳ 15 phút

# Dataset liên quan

- [Bronze Periodic Reports](../datasets/bronze_periodic_reports.md) — `data/raw_reports/**`

[^driver]: [PeriodicReportSource](project/src/pipeline/periodic_reports.py)
[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^design-16]: [Thiết kế scraper báo cáo định kỳ](project/docs/design/16-periodic-report-scraper.md)
