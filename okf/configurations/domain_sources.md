---
type: Configuration
title: Domain Sources
description: Danh sách đầy đủ 23 domain cấu hình nguồn tin — mỗi domain là 1 file YAML trong config/domains/.
resource: project/config/domains/
tags: [config, yaml, domains, sources]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: domain-configs
    resource: project/config/domains/
    title: Domain configuration directory
  - id: source-strategy
    resource: project/docs/design/03-source-strategy.md
    title: Source Strategy Document
sources_last_checked: 2026-08-04
---

Thư mục `config/domains/` chứa 23 file YAML, mỗi file định nghĩa cấu hình cho một nguồn tin. Được load bởi `src/core/config.py` và [Orchestrator](../pipelines/ingestion_scheduler.md).[^domain-configs]

# Cấu trúc 1 file domain

```yaml
name: vnexpress
enabled: false
method: rss
rate_limit: 3.0
timeout: 30
rss:
  feeds:
    - {url: "https://vnexpress.net/rss/kinh-doanh.rss", name: "VnExpress Kinh doanh"}
detail:
  extract_full: true
  max_details_per_cycle: 30
pitfalls: "chung-khoan.rss redirect 302"
```

# Danh sách đầy đủ 23 domain

## Đang Active (2)

| Domain | Method | Nhóm |
|---|---|---|
| [cafef](https://cafef.vn) | API | API Môi giới |
| [vietstock](https://vietstock.vn) | RSS | Báo VN |

## Báo Việt Nam — RSS (11, disabled)

| Domain | Trạng thái |
|---|---|
| vnexpress.net | Disabled 2026-08-03 |
| vneconomy.vn | Disabled |
| vietnambiz.vn | Disabled |
| dantri.com.vn | Disabled |
| vietnamnet.vn | Disabled |
| tuoitre.vn | Disabled |
| thanhnien.vn | Disabled |
| znews.vn | Disabled |
| cafebiz.vn | Disabled |
| vietnamplus.vn | Disabled |
| baodautu.vn | Disabled (dormant) |

## API Môi giới (5, disabled)

| Domain | Đặc điểm |
|---|---|
| fireant.vn | Cần Bearer token |
| tinnhanhchungkhoan.vn | Zone × page |
| vndirect.com.vn | Aggregator |
| hose (HOSE) | Sàn chính thống |
| hnx (HNX) | Sàn chính thống, lỗi cert chain |

## Tiếng Anh Quốc tế (5, disabled)

| Domain |
|---|
| cnbc.com |
| marketwatch.com |
| finance.yahoo.com |
| federalreserve.gov |
| oilprice.com |

# Cách thêm domain mới

Không cần sửa code, chỉ cần tạo file YAML mới trong `config/domains/`. Nếu dùng RSS: chỉ cần config. Nếu dùng API: cần implement scraper class + đăng ký qua `@register()`.

Xem thêm: [Source Strategy](source_strategy.md), [Codebase Guide](../references/codebase.md)

[^domain-configs]: [Domain configurations](project/config/domains/)
[^source-strategy]: [Source Strategy](project/docs/design/03-source-strategy.md)
