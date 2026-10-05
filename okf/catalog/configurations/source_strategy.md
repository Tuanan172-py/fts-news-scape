---
type: Reference
title: Chiến lược Nguồn tin (Source Strategy)
description: Nguyên tắc chọn & xử lý nguồn — Bronze-first, thứ tự ưu tiên phương thức, phân nhóm 24 domain.
resource: project/docs/design/03-source-strategy.md
tags: [source-strategy, architecture, rss, api, bronze-first]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: source-strategy
    resource: project/docs/design/03-source-strategy.md
    title: Source Strategy Document
  - id: rss-sources
    resource: project/docs/skills/rss-sources.md
    title: Feed + pitfalls từng nguồn
  - id: domains-readme
    resource: project/docs/domains/README.md
    title: Domain playbooks
  - id: readme
    resource: project/README.md
    title: Project README — bảng nguồn tin
sources_last_checked: 2026-09-07
---

# Nguyên tắc số 1 — Bronze-first

Một domain chỉ được `enabled` khi scraper của nó **lưu được raw HTML byte-exact** xuống
[Bronze](../datasets/bronze_raw_html.md). Lý do: mọi tầng dưới là hàm thuần của Bronze; không có
raw thì không re-derive được, không có `raw_sha256` để agent verify, không change-detection.

Hệ quả: `method: rss` generic (`RssGenericScraper`) **không** lưu Bronze ⇒ 17 domain dùng nó bị
tắt từ 2026-08-03. Bật lại = viết/đổi sang scraper có capture, **không phải** đổi `enabled`.

# Thứ tự ưu tiên phương thức (TDR-001)

`rss_capture` **>** reverse API **>** HTML listing

1. **`rss_capture`** — có RSS thì dùng: 0 dòng code, chỉ config; đã kèm Bronze capture.
2. **Reverse API** — cho nguồn không có RSS theo mã CK hoặc RSS không đủ (cafef, tnck, fireant,
   vndirect). Mỗi nguồn schema riêng ⇒ phải viết scraper.
3. **HTML listing** — phương án cuối, chỉ khi RSS hỏng vĩnh viễn (baodautu là ca đầu tiên).
4. **Trafilatura** luôn dùng ở bước bóc `content_text` từ raw đã lưu — không phải "phương thức
   thu thập".

# Phân nhóm 24 domain

## Nhóm A — VN có capture (7, đang chạy)

| Domain | `method` | Đặc điểm |
|---|---|---|
| cafef.vn | `api` + capture | News.ashx theo watchlist + 6 RSS chuyên mục |
| vietstock.vn | `vietstock` | RSS 8 feed + capture |
| vneconomy.vn | `vneconomy` | RSS 8 feed + capture, body `#article-editor` |
| vietnambiz.vn | `rss_capture` | 6 feed; `quoc-te.rss` đã chết (0 item) |
| thoibaotaichinhvietnam.vn | `rss_capture` | 1 feed thật; RSS chuyên mục của họ là ảo |
| tinnhanhchungkhoan.vn | `tnck` | zone JSON API, 9 zone, không có RSS |
| baodautu.vn | `baodautu` | HTML listing, 6 chuyên mục |

## Nhóm B — VN chưa có capture (12, tắt)

vnexpress, tuoitre, thanhnien, znews, cafebiz, vietnamplus, dantri, vietnamnet (báo tổng hợp,
chỉ subscribe chuyên mục kinh tế) · hose, hnx (sàn — hnx từng lỗi cert chain) · fireant (cần
Bearer token) · vndirect (aggregator).

## Nhóm C — Quốc tế (5, tắt)

cnbc, marketwatch, yahoofinance, fed, oilprice — `language: en`; tiêu đề tiếng Anh nên rule lọc
theo **nguồn**, không theo từ khoá tiếng Việt.

# Ràng buộc tuân thủ

- `rate_limit ≥ 3.0` giây/domain; `timeout ≤ 30` giây; retry 3 lần.
- `compliance.respect_robots: true` — [RobotsGate](../references/codebase.md) kiểm tra
  robots.txt **trước** khi fetch trang chi tiết.
- `SourceBackoff` hạ nhịp cấp-source khi bị throttle.
- Chỉ chạy **một** tiến trình scheduler (advisory lock) — chạy 2 tiến trình nhân đôi lưu lượng,
  rủi ro bị chặn IP.

# Tri thức vận hành

Bẫy từng nguồn (feed chết, encoding sai, selector, timezone thiếu offset) ghi ở trường
`pitfalls` của mỗi YAML và ở [`docs/skills/rss-sources.md`](project/docs/skills/rss-sources.md),
`docs/domains/*.md`. Luôn kèm ngày verify live.

# Liên quan

- [Domain Sources](domain_sources.md) · [Bronze Raw Store](../datasets/bronze_raw_html.md)
- [Capture Orchestrator](../pipelines/ingestion_scheduler.md)

[^source-strategy]: [Source Strategy](project/docs/design/03-source-strategy.md)
[^rss-sources]: [RSS sources & pitfalls](project/docs/skills/rss-sources.md)
[^domains-readme]: [Domain playbooks](project/docs/domains/README.md)
[^readme]: [Project README](project/README.md)
