# VnEconomy Domain Changelog

## 2026-09-07 — Bổ sung contract còn thiếu

`domains/vneconomy/` chưa từng được tạo dù vneconomy là 1 trong 3 nguồn enabled lâu nhất.
Sau khi `resolve_source_domain()` (phase-03) lấy `domain:` từ `schema.yaml` làm nguồn sự thật,
thiếu file này nghĩa là tooling monitor phải rơi về fallback legacy `<name>.vn`
(may mắn đúng với vneconomy, nhưng không nên dựa vào may mắn).

- Thêm `schema.yaml` + `changelog.md`.
- Nội dung contract chép lại từ `config/domains/vneconomy.yaml` và
  `docs/design/06-raw-html-capture.md` (verified 2026-08-17).
- ⚠️ `last_verified: 2026-08-17` — **chưa** re-verify trong đợt 2026-09-07.
  Watch point `vne-w3` theo dõi việc này.

## 2026-08-17 — Chuyển sang scraper riêng có capture

`method: rss` → `method: vneconomy`. 8 feed. Body `#article-editor` (thẻ `<main>`).
`content:encoded` khai namespace nhưng item không chứa → detail-fetch bắt buộc.
