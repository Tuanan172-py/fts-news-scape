---
type: Configuration
title: Domain Sources
description: 24 file YAML cấu hình nguồn tin trong config/domains/ — 8 đang bật (Bronze-first), 16 tắt có chủ đích.
resource: project/config/domains/
tags: [config, yaml, domains, sources]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: vietnambiz-config
    resource: project/config/domains/vietnambiz.yaml
    title: Ví dụ config đầy đủ (rss_capture)
  - id: config-loader
    resource: project/src/core/config.py
    title: load_domain_config / list_domains
  - id: registry
    resource: project/src/scrapers/__init__.py
    title: Scraper REGISTRY
  - id: adding-source
    resource: project/docs/dev/03-adding-a-source.md
    title: Adding a source
sources_last_checked: 2026-09-07
---

Mỗi nguồn tin = 1 file YAML trong `config/domains/`. `list_domains()` chỉ trả về domain có
`enabled: true`; `build_scraper()` tra `method` trong [REGISTRY](../references/codebase.md).[^config-loader]

# Trạng thái (2026-09-08): 24 config, **8 enabled**

> **Enabled ≡ có Bronze capture.** Hệ thống là Bronze-first: mỗi bài phải có raw HTML byte-exact
> (`RawStore.save` trước mọi parse). `method: rss` generic **không** lưu Bronze, nên 16 domain
> còn lại **cố ý tắt** — bật lại cần research từng trang + scraper có capture, không phải đổi
> `enabled: true`.

## Đang chạy (7)

| Domain | `method` | Ghi chú |
|---|---|---|
| cafef | `api` | News.ashx theo watchlist + 6 RSS chuyên mục |
| vietstock | `vietstock` | RSS + capture, 8 feed |
| vneconomy | `vneconomy` | RSS + capture, 8 feed, body `#article-editor` |
| vietnambiz | `rss_capture` | 6 feed, body `div.vnbcbc-body` — nguồn đầu dùng class generic mới |
| thoibaotaichinhvietnam | `rss_capture` | 1 feed; chuyên mục thật lấy từ `meta article:section` |
| tnck | `tnck` | zone JSON API + capture, 9 zone; `source_domain` = `tinnhanhchungkhoan.vn` ≠ tên config |
| baodautu | `baodautu` | **HTML listing** + capture (RSS hỏng vĩnh viễn), 6 chuyên mục |

## Đang tắt (17)

- **VN, `method: rss`**: vnexpress, tuoitre, thanhnien, znews, cafebiz, vietnamplus, dantri,
  vietnamnet, hose, hnx
- **VN, `method: api`**: fireant (cần Bearer token), vndirect
- **Quốc tế (`language: en`, `method: rss`)**: cnbc, marketwatch, fed, oilprice, yahoofinance

# Cấu trúc 1 file

```yaml
name: vietnambiz
enabled: true
method: rss_capture          # rss | rss_capture | api | <tên scraper riêng>
rate_limit: 3.0
timeout: 30
language: vi
base_url: "https://vietnambiz.vn/"
rss:
  feeds:
    - {url: "https://vietnambiz.vn/chung-khoan.rss", name: "VietnamBiz Chứng khoán"}
detail:
  extract_full: true
  content_selector: "div.vnbcbc-body"   # BẮT BUỘC với rss_capture
  max_details_per_cycle: 30
capture:
  raw_dir: "data/raw_html"
  min_body_bytes: 2048
compliance:
  respect_robots: true
  proxy_rotation: false
  proxies: []
pitfalls: "ghi lại bẫy đã verify live — encoding, feed chết, selector, timezone…"
```

⚠️ Với `method: rss_capture`, **`detail.content_selector` là bắt buộc**. Selector sai ⇒
`capture_status: partial` ⇒ `SELECTOR_BROKEN` ⇒ bài bị **held**, agent không nhận. Mặc định
`article` sẽ hỏng với trang không có thẻ `<article>`.

Trường `pitfalls` là tri thức vận hành quý nhất trong mỗi file — luôn ghi kèm ngày verify live.

# Thêm domain mới

1. Tạo `config/domains/<name>.yaml`.
2. Nguồn **có RSS** → `method: rss_capture` ⇒ xong, 0 dòng code (dùng `RssCaptureScraper`).
3. API/HTML riêng → viết `src/scrapers/<name>.py` + `@register("<name>")`.
4. Viết test (happy path + 1 edge case), rồi `python scripts/run_once.py <name>`.

Không cần sửa orchestrator/core.[^adding-source]

# Liên quan

- [Source Strategy](source_strategy.md) · [Codebase Guide](../references/codebase.md)
- [Bronze Raw Store](../datasets/bronze_raw_html.md)

[^vietnambiz-config]: [vietnambiz.yaml](project/config/domains/vietnambiz.yaml)
[^config-loader]: [config.py](project/src/core/config.py)
[^registry]: [Scraper registry](project/src/scrapers/__init__.py)
[^adding-source]: [Adding a source](project/docs/dev/03-adding-a-source.md)
