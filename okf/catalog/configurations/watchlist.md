---
type: Configuration
title: Watchlist
description: 30 mã blue-chip dùng để query API theo mã và gắn tag ticker — KHÔNG phải bộ lọc thu thập.
resource: project/config/watchlist.yaml
tags: [config, yaml, tickers, watchlist]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: watchlist
    resource: project/config/watchlist.yaml
    title: Watchlist YAML
  - id: tickers
    resource: project/src/core/tickers.py
    title: Ticker tagging
  - id: cafef
    resource: project/src/scrapers/cafef.py
    title: CafeF — query theo từng mã watchlist
sources_last_checked: 2026-09-07
---

`config/watchlist.yaml` liệt kê 30 mã blue-chip dưới khoá `tickers`.[^watchlist]

# Danh sách (30 mã)

```
HPG VNM VIC VHM VCB BID CTG TCB MBB VPB
ACB STB SHB HDB FPT SSI VND HCM VCI MWG
MSN GAS PLX POW GVR SAB VJC VRE BCM DGC
```

# Ba công dụng

1. **Query API theo mã** — [CafeF](../references/codebase.md) gọi News.ashx 1 request/mã/chu
   kỳ.[^cafef]
2. **Gắn tag ticker** — `src/core/tickers.py` khớp mã 3 ký tự in hoa trong tiêu đề/nội dung, đổ
   vào `articles.symbols`.[^tickers]
3. **Rule notify ưu tiên cao nhất** — tag `watchlist` trong [notifications.yaml](notifications.md)
   (danh sách được lặp lại trong file đó).

⚠️ Watchlist **không** phải bộ lọc thu thập: hệ thống vẫn thu mọi tin của nguồn đã bật, kể cả
tin không có mã nào. Việc lọc "tin nào tới người dùng nào" do
[Entity Registry](entity_registry.md) + [User Subscriptions](user_subscriptions.md) đảm nhiệm ở
tầng Gold, phạm vi rộng hơn watchlist rất nhiều (2.152 thực thể).

Cập nhật danh sách: `python scripts/refresh_watchlist.py` cũng dùng file này để chọn URL re-fetch
kích hoạt change-detection.

# Liên quan

- [settings.yaml](settings.md) · [notifications.yaml](notifications.md) · [Domain Sources](domain_sources.md)
- [Entity Registry](entity_registry.md)

[^watchlist]: [watchlist.yaml](project/config/watchlist.yaml)
[^tickers]: [tickers.py](project/src/core/tickers.py)
[^cafef]: [CafeF scraper](project/src/scrapers/cafef.py)
