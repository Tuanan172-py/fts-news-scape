---
type: Reference
title: Chiến lược Nguồn tin (Source Strategy)
description: Cấu trúc phân nhóm và ưu tiên phương thức thu thập dữ liệu từ 23 domain tin tức chứng khoán.
resource: project/docs/design/03-source-strategy.md
tags: [source-strategy, architecture, rss, api]
status: stable
generated:
  by: human:anpt
  at: 2026-08-03T10:00:00Z
sources:
  - id: source-strategy
    resource: project/docs/design/03-source-strategy.md
    title: Source Strategy Document
    author: human:anpt
  - id: domain-configs
    resource: project/config/domains/
    title: Domain YAML configurations
sources_last_checked: 2026-08-04
---

Tài liệu này xác định nguyên tắc lựa chọn và xử lý các nguồn tin tức chứng khoán để phục vụ phòng phân tích. Hệ thống xử lý tổng cộng 23 domain được cấu hình thông qua framework nội bộ.[^source-strategy]

## Nguyên tắc Ưu tiên (TDR-001)

**RSS > Reverse API > HTML Scraping**

1. **RSS** được ưu tiên vì độ bao phủ rộng, thiết lập nhanh và ít bị hỏng (break) khi trang web thay đổi giao diện.
2. **API (Reverse Engineering)** chỉ được sử dụng cho các nguồn không hỗ trợ RSS theo mã chứng khoán (VD: trang của công ty môi giới).
3. **HTML tĩnh** hiếm khi được sử dụng, ngoại trừ bước bóc tách văn bản sâu (enrichment) thông qua Trafilatura.[^source-strategy]

## Phân loại Nguồn

### Nhóm A — Báo Việt Nam qua RSS (13 nguồn)

Sử dụng chung class `RSSScraper`. Cấu hình nằm trong file YAML riêng cho mỗi domain tại `config/domains/`.

| Domain | Trạng thái | Ghi chú |
|---|---|---|
| vietstock.vn | ✅ Active | |
| vnexpress.net | ⏸️ Disabled (2026-08-03) | Kinh doanh RSS |
| vneconomy.vn | ⏸️ Disabled | |
| vietnambiz.vn | ⏸️ Disabled | |
| dantri.com.vn | ⏸️ Disabled | |
| vietnamnet.vn | ⏸️ Disabled | |
| tuoitre.vn | ⏸️ Disabled | |
| thanhnien.vn | ⏸️ Disabled | |
| znews.vn | ⏸️ Disabled | |
| cafebiz.vn | ⏸️ Disabled | |
| vietnamplus.vn | ⏸️ Disabled | |
| baodautu.vn | ⏸️ Disabled | Dormant |

### Nhóm B — API Môi giới / Chuyên trang (6 nguồn)

Trả về JSON, yêu cầu code riêng vì mỗi nguồn có Schema khác nhau.

| Domain | Method | Trạng thái | Đặc điểm |
|---|---|---|---|
| cafef.vn | API | ✅ Active | Tìm theo mã Watchlist, 1 request/mã/chu kỳ |
| fireant.vn | API | ⏸️ Disabled | Cần Bearer token, tìm theo mã |
| tinnhanhchungkhoan.vn | API | ⏸️ Disabled | Lấy theo zone × page, tag ticker ở client |
| vndirect.com.vn | API | ⏸️ Disabled | Aggregator, lấy cả trang 1 lần, nội dung nhúng sẵn |
| hose (HOSE) | API | ⏸️ Disabled | Công bố thông tin sàn |
| hnx (HNX) | API | ⏸️ Disabled | Công bố thông tin sàn, lỗi cert chain |

### Nhóm C — Nguồn Tiếng Anh Quốc tế (5 nguồn)

| Domain | Method | Trạng thái |
|---|---|---|
| cnbc.com | RSS | ⏸️ Disabled |
| marketwatch.com | RSS | ⏸️ Disabled |
| finance.yahoo.com | RSS | ⏸️ Disabled |
| federalreserve.gov | RSS | ⏸️ Disabled |
| oilprice.com | RSS | ⏸️ Disabled |

## Trạng thái hiện tại (2026-08-04)

**2/23 domain đang active**: `cafef` và `vietstock`. Tất cả domain khác bị vô hiệu hóa từ 2026-08-03 để tập trung scope và giảm tải trong giai đoạn Phase 1 hardening.

Xem danh sách đầy đủ tại [Domain Sources](../configurations/domain_sources.md).

[^source-strategy]: [Source Strategy Document](project/docs/design/03-source-strategy.md)
[^domain-configs]: [Domain YAML configurations](project/config/domains/)
