---
type: Pipeline
title: Periodic Reports (NSO)
description: Driver thu báo cáo định kỳ Cục Thống kê — offline, opt-in, tần suất thấp, NGOÀI chu kỳ 15 phút của orchestrator.
resource: "project/src/pipeline/periodic_reports.py"
tags: [nso, periodic, bronze, out-of-cycle, opt-in]
status: stable
generated:
  at: 2026-09-08T00:00:00Z
sources:
  - id: driver
    resource: project/src/pipeline/periodic_reports.py
    title: PeriodicReportSource
  - id: cli
    resource: project/scripts/fetch_periodic_reports.py
    title: CLI thu báo cáo định kỳ
  - id: design-16
    resource: project/docs/design/16-periodic-report-scraper.md
    title: Thiết kế scraper báo cáo định kỳ
sources_last_checked: 2026-09-08
---

Nhánh xử lý **thứ tư**, song song với 3 vòng medallion chứ không nằm trong chúng. Thu báo cáo
kinh tế – xã hội định kỳ do Cục Thống kê (`nso.gov.vn`) công bố, kèm file số liệu gốc.

> ⚠️ **KHÔNG chạy trong cycle 15 phút của [Morninger](morninger.md).** NSO công bố ~ngày 3 hàng
> tháng; chạy liên tục là lãng phí và bất lịch sự với một cơ quan nhà nước.

# Vì sao không phải một domain

NSO **không** là domain thứ 25. Không có `config/domains/nso.yaml`, không có `src/scrapers/nso.py`,
không đăng ký vào `REGISTRY`. Lý do: đơn vị dữ liệu là **kỳ báo cáo**, không phải bài báo — nó
không có `url_title_hash`, không đi qua Silver, không sinh work-package.[^design-16]

# Luồng

```
discover()      WordPress REST API: /wp-json/wp/v2/posts?tags=727   (tag KTXH, 337 post)
   |
identify()      parse (report_type, period) tu TITLE  -- KHONG tu slug
   |
_existing()     tra periodic_reports theo (source, report_type, period)
   |            modified_at doi -> revision + 1 ; khong doi -> bo qua (idempotent)
   |
_capture_report()
   |-- RawStore.save()         trang HTML  -> .html + .meta.json
   |-- extract_attachments()   quet link .xlsx/.docx/.pdf tren trang
   |-- RawStore.save_binary()  tung file    -> .xlsx + .binmeta.json
   |
_upsert()       ghi periodic_reports
```

# Chạy

```bash
python scripts/fetch_periodic_reports.py                # 20 bai moi nhat
python scripts/fetch_periodic_reports.py --dry-run      # chi liet ke, khong ghi
python scripts/fetch_periodic_reports.py --list         # xem da co gi trong DB
pwsh scripts/run_periodic_reports.ps1                   # wrapper cho cron
```

Lịch khuyến nghị: cron ngày 2–6 hàng tháng, 2 lần/ngày (08:00 & 14:00 giờ VN), cộng 1 lần/tuần
để bắt báo cáo quý/năm.[^cli]

# Bẫy đã gặp (đừng lặp lại)

| Bẫy | Hậu quả | Cách đúng |
|---|---|---|
| Parse kỳ từ **slug** | sai năm (đã gặp `…-2025-2`) ⇒ dedup sai kỳ | parse từ `title` |
| `key` còn giữ phần mở rộng | file ra `.xlsx.xlsx` | `_safe_key()` bỏ đuôi, `save_binary` tự thêm lại |
| Hạ chữ thường cả đường dẫn khi trích attachment | mất phân biệt hoa/thường của tên file | chỉ hạ chữ thường khi **so khớp** |
| Để Bronze trong `data/raw_html/` | work_item mồ côi, `derive` báo `raw_missing` | root riêng `data/raw_reports/` + `.binmeta.json` |

# Cổng triển khai

Kết luận research ban đầu ("NSO bị chặn network, TCP RST") **đã bị đảo ngược**: gate G1 chạy lại
2026-09-07 đạt **12/12 PASS** — lần chặn đầu chỉ là chập chờn. Trước khi gắn cron, chạy
`--dry-run` **từ máy deploy** để xác nhận đường mạng ở đó.

# Liên quan

- Bảng [periodic_reports](../tables/periodic_reports.md)
- Dataset [Bronze Periodic Reports](../datasets/bronze_periodic_reports.md)
- Playbook [Runbook](../playbooks/runbook.md) — mục "Báo cáo định kỳ NSO"

[^driver]: [PeriodicReportSource](project/src/pipeline/periodic_reports.py)
[^cli]: [CLI thu báo cáo định kỳ](project/scripts/fetch_periodic_reports.py)
[^design-16]: [Thiết kế scraper báo cáo định kỳ](project/docs/design/16-periodic-report-scraper.md)
