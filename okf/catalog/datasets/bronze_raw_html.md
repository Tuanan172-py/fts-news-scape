---
type: File Dataset
title: Bronze Raw Store
description: Kho raw HTML byte-exact (WORM) + sidecar .meta.json — nguồn provenance bất biến của toàn hệ.
resource: project/data/raw_html/
tags: [bronze, worm, provenance, raw-html]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: raw-store
    resource: project/src/crawler/raw_store.py
    title: RawStore.save — atomic, byte-exact
  - id: capture-mixin
    resource: project/src/scrapers/capture_mixin.py
    title: CaptureMixin — robots → backoff → fetch → save
  - id: capture-design
    resource: project/docs/design/06-raw-html-capture.md
    title: Raw HTML capture design
  - id: capture-guide
    resource: project/docs/dev/06-raw-html-capture-guide.md
    title: Raw HTML capture guide
sources_last_checked: 2026-09-07
---

Bronze là **tầng đáy** của kiến trúc medallion: mỗi bài được lưu nguyên vẹn bytes phản hồi HTTP
trước khi bất kỳ xử lý nào chạy. Nguyên tắc **WORM** — ghi một lần, không bao giờ sửa;
`content_sha256` là bằng chứng bất biến để mọi tầng sau đối chiếu.[^capture-design]

Hệ quả thiết kế: mọi thứ dưới Bronze (Silver, work-package, version log) là **hàm thuần** của
Bronze ⇒ sửa parser hay bump schema chỉ cần re-derive, **không phải re-scrape**.

# Bố cục trên đĩa

```
data/raw_html/<domain>/<YYYYMMDD>/<url_title_hash>.html        # bytes nguyên bản
data/raw_html/<domain>/<YYYYMMDD>/<url_title_hash>.meta.json   # sidecar mô tả
```

Ghi nguyên tử: viết `<path>.tmp` rồi `os.replace()` — không bao giờ có file nửa vời.[^raw-store]
`.meta.json` **luôn** được ghi, kể cả khi fetch thất bại (để biết đã thử và hỏng ở đâu).

# Sidecar `.meta.json` — 14 khoá

| Key | Ý nghĩa |
|---|---|
| `source_url` | URL đã fetch |
| `url_title_hash` | `article_id` xuyên tầng |
| `fetch_ts` | Thời điểm fetch — cũng là **watermark** cho re-derive tăng dần |
| `render_method` | `requests` (mặc định) hoặc engine render khác |
| `html_path` | Đường dẫn file `.html` tương ứng |
| `http_status` | Mã HTTP |
| `content_sha256` | SHA-256 của bytes = `raw_sha256` toàn hệ |
| `content_length_bytes` | Kích thước bytes |
| `encoding` | Encoding phản hồi |
| `response_headers` | Header đã lọc theo whitelist |
| `images` | Danh sách ảnh quét được (chỉ đọc, không tải) |
| `capture_status` | `ok` / `partial` / `failed` |
| `missing` | Thành phần thiếu (vd `article_body`) |
| `error` | Chi tiết lỗi + `protection_mechanism` nếu bị chặn |

`capture_status = partial` (selector nội dung không khớp) sẽ dẫn tới `SELECTOR_BROKEN` ở
[change-detection](../tables/article_versions.md) ⇒ bài bị **held**, không giao agent.

# Bất biến

1. File `.html` = bytes phản hồi nguyên bản; `sha256(file) == meta.content_sha256`.
2. Không bao giờ ghi đè, không "làm sạch" tại Bronze.
3. `RawStore.save` chạy **trước** mọi parse/extract trong `enrich()`.
4. Chỉ domain có capture mới được `enabled` — xem [Source Strategy](../configurations/source_strategy.md).

# Quan hệ

- Nguồn của [Silver & Work Packages](silver_work_packages.md) qua [Silver Derive](../pipelines/silver_derive.md)
- `content_sha256` = `article_versions.content_sha256` = `work_items.raw_sha256`

[^raw-store]: [RawStore](project/src/crawler/raw_store.py)
[^capture-mixin]: [CaptureMixin](project/src/scrapers/capture_mixin.py)
[^capture-design]: [Raw HTML capture design](project/docs/design/06-raw-html-capture.md)
[^capture-guide]: [Raw HTML capture guide](project/docs/dev/06-raw-html-capture-guide.md)
