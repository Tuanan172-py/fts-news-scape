---
type: Configuration
title: Entity Registry
description: Ontology 10 miền + từ điển alias đa miền — trái tim nhận diện và định tuyến tin của hệ thống.
resource: project/data/entities/entities.json
tags: [config, entities, ontology, alias, routing]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: entities
    resource: project/src/agent/entities.py
    title: EntityRegistry — detect / subscribers_for / resolve_subscription
  - id: entity-design
    resource: project/docs/design/14-entity-system-and-mapping.md
    title: Entity system & mapping
  - id: entities-doc
    resource: project/docs/entities.md
    title: Entities reference
  - id: aliases-tickers
    resource: project/config/entities/aliases/tickers.yaml
    title: Alias thương hiệu doanh nghiệp
sources_last_checked: 2026-09-07
---

Entity Registry là **trái tim định tuyến**: nhận diện đối tượng tài chính trong tin, rồi ánh xạ
ngược ra người dùng nào cần nhận tin đó.[^entity-design]

# Quy mô (data/entities/stats.json, schema 1.1.0)

**2.152 thực thể** — TICKER 1.983 · ETF 28 · SECURITY_OTHER 11 · INDEX 6 · EXCHANGE 3 ·
INDUSTRY_GICS1/2/3 11/28/51 · MACRO_GEO 8 · MACRO_THEME 9 · ASSET_CLASS 7 · INSTITUTION 7.
Trong 2.022 chứng khoán: 1.968 có tên, 1.917 có phân ngành GICS.

# Ontology 10 miền

| Nhóm | Prefix `type` | Sheet tra cứu | Ví dụ `code` |
|---|---|---|---|
| Cổ phiếu niêm yết | `TICKER` | Securities | `HPG`, `FPT` |
| Quỹ ETF / mở | `ETF` | Securities | `E1VFVN30` |
| Chứng khoán khác | `SECURITY_OTHER` | Securities | `FUCTVGF3` |
| Ngành GICS 3 cấp | `INDUSTRY_GICS1/2/3` | Industries | `THEP`, `NGAN_HANG` |
| Chỉ số | `INDEX` | Indices | `VNINDEX`, `VN30` |
| Sàn giao dịch | `EXCHANGE` | Exchanges | `HOSE`, `HNX` |
| Quốc gia / địa chính trị | `MACRO_GEO` | Nations | `MY`, `TRUNG_QUOC` |
| Chủ đề vĩ mô | `MACRO_THEME` | Themes | `LAI_SUAT`, `LAM_PHAT` |
| Loại tài sản | `ASSET_CLASS` | Assets | `VANG`, `DAU_THO` |
| Định chế & quản lý | `INSTITUTION` | Institutions | `NHNN`, `FED` |

Liên kết đa tầng: nhận ra `HPG` ⇒ tự động gắn ngành `THEP`.

# Bố cục file

```
project/data/entities/entities.json      # registry sinh ra (nguồn EntityRegistry đọc)
project/data/entities/entities.xlsx      # master catalog người dùng tra mã
project/data/entities/{taxonomy,stats}.json
project/config/entities/aliases/*.yaml   # 7 file alias theo miền
project/config/entities/brand_aliases.yaml
project/config/entities/manifest.yaml    # công tắc DEV bật/tắt người dùng
project/config/entities/users/<name>.yaml  # AUTO-GENERATED — xem User Subscriptions
```

Sinh lại registry: `python scripts/build_entities.py` — chạy khi dữ liệu gốc đổi.

# Chống false positive

Ba cơ chế trong `src/agent/entities.py`:[^entities]

1. **`CODE_STOPLIST`** — mã 3 ký tự trùng từ viết tắt tài chính (`GDP`, `CPI`, `FED`, `USD`,
   `CEO`, `ETF`, `IPO`…) **không** auto-match theo code.
2. **`PROTECTED_SHORT_WORDS`** — từ ngắn 2–3 ký tự nhưng quan trọng vẫn được giữ (`quy`, `my`,
   `eu`, `fed`, `vang`, `dau`, `cpi`, `gdp`, `sbv`, `bds`…), thay vì lọc bỏ mọi từ `<4` ký tự.
3. **Khớp biên từ** — alias tìm trên văn bản đã bỏ dấu bằng `\b…\b`, nên *"quyết định"* không
   thành *"quy"*, *"mỹ thuật"* không thành *"Mỹ"*.

Một alias có thể ánh xạ **nhiều** entity_id (vd *"Quỹ"* → cả `INDUSTRY_GICS2:QUY` và
`INDUSTRY_GICS3:QUY`) nên index là `dict[str, list[str]]`.

Mã CK khớp theo **CODE in hoa, nguyên token**; ngành khớp theo **CODE GICS**, không theo tên.

# API chính

| Hàm | Dùng ở |
|---|---|
| `registry.detect(title)` | code-first Lớp 1 ([l1_tasks](../tables/l1_tasks.md)) |
| `registry.get(entity_id)` | đổi id → code hiển thị |
| `registry.subscribers_for(ids)` | định tuyến tin → người dùng |
| `registry.resolve_subscription(user)` | tập entity người dùng đăng ký |
| `registry.select(doc)` | biên dịch input người dùng |

`load_registry()` có `lru_cache`; `compile_all()` gọi `cache_clear()` để subscription mới có
hiệu lực ngay.

# Liên quan

- [User Subscriptions](user_subscriptions.md) · [Agent Handoff](../pipelines/agent_handoff.md)
- [User Output Workflow](../pipelines/user_output.md) · [watchlist.yaml](watchlist.md)

[^entities]: [entities.py](project/src/agent/entities.py)
[^entity-design]: [Entity system & mapping](project/docs/design/14-entity-system-and-mapping.md)
[^entities-doc]: [Entities reference](project/docs/entities.md)
[^aliases-tickers]: [tickers.yaml](project/config/entities/aliases/tickers.yaml)
