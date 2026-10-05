# Domains — Sàn chính thống (Layer 0): HOSE, HNX

Cập nhật: 2026-07-26 · Verify 2026-07-25 (probe report `plans/.../reports/02-layer0-ctck-probe.md`).

"Layer 0" = nguồn công bố thông tin **chính thống** từ sở giao dịch — độ tin cậy cao nhất, tín
hiệu đáng theo dõi (công bố niêm yết, cảnh báo, đình chỉ…). Cả hai đi qua `RSSScraper` nhưng
trang chi tiết là SPA nên cấu hình đặc thù.

## hose — `config/domains/hose.yaml`

- **Method:** `rss` (nhưng feed thực là **JSON-feed** qua `api.hsx.vn`).
- **Feeds (2):**
  - `https://api.hsx.vn/n/api/v1/News/NewsByCateFeed/21` — Tổ chức niêm yết
  - `https://api.hsx.vn/n/api/v1/News/NewsByCateFeed/22` — Thành viên
- **Detail:** `extract_full: false`, `max_details_per_cycle: 0` → **summary-only**.
- **Quirk:**
  - Trang hsx.vn là **React SPA** → không parse được detail → **title công bố = signal chính**.
  - BOM utf-8 → `_decode_feed` (utf-8-sig). ~10 items/feed.
  - ⚠️ `method: rss` + URL JSON: đã verify feedparser xử được nhưng **chưa có test cố định**
    (xem [../dev/05-known-issues.md](../dev/05-known-issues.md) §3.1).

## hnx — `config/domains/hnx.yaml`

- **Method:** `rss`.
- **Feed:** `https://www.hnx.vn/vi-vn/1/vi_vn/thong-tin-cong-bo-tu-so.rss` — Công bố từ Sở.
- **Detail:** `extract_full: true`, `max_details_per_cycle: 15`.
- **link_rewrites:**
  - `:7978` → `""` — item link kèm **port nội bộ** rò rỉ từ backend, phải gỡ.
  - `^http://` → `https://`.
- **Quirk:**
  - BOM utf-8. ~50 items. Follow redirect 302.
  - `rss.html` là JS page — **không dùng**; chỉ dùng đúng URL `.rss` ở trên.
  - hnx.vn serve TLS chain thiếu intermediate → HTTP client dùng **truststore** (OS cert store)
    thay certifi (`http_client.py:15-21`).

## Vì sao summary-only cho hose

Nội dung công bố nằm ở file đính kèm/PDF hoặc render động; title + tóm tắt trong feed đã đủ để
làm tín hiệu ("Công ty X công bố...", "Cổ phiếu Y vào diện cảnh báo"). Bóc detail SPA không đáng
công + dễ vỡ. hnx thì detail HTML tĩnh hơn nên vẫn `extract_full: true` (cap 15).

## Ghi chú

- Cả hai `language: vi` → có chấm sentiment VN.
- Đây là kết quả timebox nghiên cứu Layer 0 (Phase 2 phase-04). CTCK (công ty chứng khoán) khác
  phần lớn không có feed công khai ổn định → chưa đưa vào (xem probe report).
