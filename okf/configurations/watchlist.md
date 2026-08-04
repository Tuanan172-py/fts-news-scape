---
type: Configuration
title: Watchlist
description: Danh sách 30 mã chứng khoán blue-chip được theo dõi — dùng để lọc tin tức và tag symbols.
resource: project/config/watchlist.yaml
tags: [config, yaml, tickers, watchlist]
status: stable
generated:
  by: human:anpt
  at: 2026-08-04T00:00:00Z
sources:
  - id: watchlist
    resource: project/config/watchlist.yaml
    title: Watchlist YAML
sources_last_checked: 2026-08-04
---

File `config/watchlist.yaml` định nghĩa danh sách 30 mã chứng khoán blue-chip (VN30) được hệ thống theo dõi.[^watchlist]

# Mục đích

1. **Lọc tin tức**: Chỉ thu thập và phân tích bài báo có đề cập đến mã trong watchlist
2. **Tag symbols**: Scraper API (cafef, fireant) tìm kiếm theo từng mã trong watchlist
3. **Notification trigger**: FileNotifier gửi thông báo khi có bài mới khớp watchlist

# Cấu trúc

```yaml
tickers:
  - ACB
  - BID
  - BVH
  - CTG
  - FPT
  - GAS
  - HPG
  - MBB
  - MSN
  - MWG
  - PLX
  - PNJ
  - POW
  - SAB
  - SSI
  - STB
  - TCB
  - VCB
  - VHM
  - VIC
  - VJC
  - VNM
  - VPB
  - VRE
  - ... (30 mã)
```

# Liên quan

- [settings.yaml](settings.md) — Cấu hình toàn cục
- [notifications.yaml](notifications.md) — Cấu hình thông báo (triggered by watchlist match)
- [Domain Sources](domain_sources.md) — Domain API scraper dùng watchlist để query

[^watchlist]: [Watchlist config](project/config/watchlist.yaml)
