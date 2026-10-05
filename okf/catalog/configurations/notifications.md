---
type: Configuration
title: Notifications
description: 4 rule lọc tin ra log file — watchlist → symbol → finance source → market keyword; rule khớp đầu tiên thắng.
resource: project/config/notifications.yaml
tags: [config, yaml, notifications, coverage]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: notifications-config
    resource: project/config/notifications.yaml
    title: Notifications config
  - id: notifier
    resource: project/src/notifier/file_notify.py
    title: FileNotifier implementation
  - id: notification-design
    resource: project/docs/design/05-notification-coverage.md
    title: Notification Coverage Design
sources_last_checked: 2026-09-07
---

`config/notifications.yaml` định nghĩa **danh sách `rules`**; `FileNotifier` duyệt tuần tự và
**rule khớp ĐẦU TIÊN thắng**, trả về `tag` của rule đó.[^notifier]

Mục tiêu là **phủ toàn bộ thông tin thị trường** — cổ phiếu, doanh nghiệp, cơ quan quản lý, vĩ
mô, trong nước & quốc tế — chỉ loại tin lá cải thuần từ báo tổng hợp.[^notification-design]

# 4 rule hiện hành

| # | `tag` | Điều kiện | Ý đồ |
|---|---|---|---|
| 1 | `watchlist` | `tickers:` — khớp **nguyên token, phân biệt hoa/thường** 30 mã blue-chip | ưu tiên cao nhất |
| 2 | `symbol` | `has_symbol: true` | bài gắn **bất kỳ** mã CK nào, kể cả ngoài watchlist |
| 3 | `finance` | `sources:` — danh sách domain | nguồn 100% tin thị trường ⇒ ghi tất |
| 4 | `market` | `match.any:` — ~120 từ khoá | chỉ còn cafebiz (home.rss trộn lá cải) |

Rule 3 gồm: tài chính VN chuyên biệt (fireant, tinnhanhchungkhoan, vietstock, vndirect,
vneconomy, cafef, vietnambiz), sàn (hnx, api.hsx.vn), báo lớn mà ta **chỉ** subscribe chuyên mục
kinh tế (dantri, vnexpress, tuoitre, thanhnien, znews, vietnamplus, vietnamnet), và quốc tế EN
(yahoo, cnbc, fed, marketwatch, oilprice, barrons, investors, wsj).

Rule 4 phủ 6 nhóm từ khoá: chứng khoán/thị trường vốn · doanh nghiệp/vi mô · ngân hàng/tiền tệ ·
cơ quan quản lý & chính sách · vĩ mô trong nước · ngành kinh tế · hàng hoá/quốc tế.

# 4 kiểu điều kiện của 1 rule (OR trong cùng rule)

| Khoá | Cách khớp |
|---|---|
| `tickers: [MÃ…]` | regex `\b(MÃ\|…)\b` trên `title + symbols`, **case-sensitive** |
| `sources: [domain…]` | `article.source_domain` thuộc danh sách |
| `has_symbol: true` | bài có ≥1 mã CK |
| `match.any: [kw…]` | substring **lowercase** trên `title + symbols` |

`tickers` cố ý dùng khớp nguyên-token để tránh gán nhầm: `VIC` ⊄ *Vicem*, `BID` ⊄ *BIDV*,
`SSI` ⊄ *passive*.[^notifier]

# Output

Không có file `.txt` theo tier. FileNotifier ghi **1 file log/ngày**:

```
data/notifications/YYYY-MM-DD.log
```

Mỗi bài khớp = 1 dòng (kèm tag), đồng thời in ra stdout. Metadata đầy đủ đã có trong DB — log
chỉ để đọc lướt. Cuối cycle ghi thêm dòng tổng kết (`notify_cycle_summary`).

⚠️ Bản mô tả cũ nói tới cấu trúc `notifications.enabled / tiers / prefix` và file
`WATCHLIST_*.txt` — **không tồn tại** trong code lẫn config hiện tại.

⚠️ Notify là tiện ích *best-effort*: lỗi ở bước này bị bắt và bỏ qua, không làm hỏng cycle.
Lớp phân phối thật tới người dùng là [User Output](../pipelines/user_output.md).

# Liên quan

- [watchlist.yaml](watchlist.md) · [settings.yaml](settings.md)
- [Capture Orchestrator](../pipelines/ingestion_scheduler.md)

[^notifications-config]: [notifications.yaml](project/config/notifications.yaml)
[^notifier]: [FileNotifier](project/src/notifier/file_notify.py)
[^notification-design]: [Notification Coverage Design](project/docs/design/05-notification-coverage.md)
