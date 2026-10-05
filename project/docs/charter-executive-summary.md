# Project Charter — Tóm tắt điều hành

## 1. Vấn đề

Monitor tin tức tài chính từ nhiều nguồn VN (VnExpress, Cafef, NDH,...) để:

- Phát hiện sớm thông tin ảnh hưởng đến VN30F1M
- Có context thị trường trước/trong phiên giao dịch
- Không bỏ lỡ tin quan trọng vì phải tự check nhiều trang

Hiện tại làm thủ công → mất thời gian, dễ miss.

## 2. Giải pháp

Web Monocle — hệ thống tự động:

1. **Thu thập** — RSS + content extraction → articles
2. **Xử lý** — dedup, classify, entity extract, summarize
3. **Lưu trữ** — SQLite (primary) + ClickHouse (analytics)
4. **Thông báo** — Telegram, filter theo category/keyword

## 3. Kiến trúc

1 máy (T7920/WSL), không cloud, không server mới.

```
RSS feeds → Python script (cron 15 phút) → SQLite → Hermes agent → Telegram
                                              ↓ (batch sync 1h)
                                         ClickHouse
```

## 4. Constraints chính

- **Single-machine** — không thêm server
- **No new DB** — SQLite + ClickHouse có sẵn
- **Config-driven** — thêm feed = thêm YAML
- **0 side-effect on trading** pipeline
- **Hermes-first** — cron, notification, skills đều qua Hermes

## 5. Delivery plan

| Phase                    | Nội dung                                      | Trạng thái                                                   |
| ------------------------ | ---------------------------------------------- | -------------------------------------------------------------- |
| **Phase 1 — MVP** | RSS → SQLite → Telegram                      | Code skeleton done. Cần: pip install, test thật, deploy cron |
| **Phase 2**        | ClickHouse sync, LLM summarize, entity extract | Chưa bắt đầu                                               |
| **Phase 3**        | HTML scraper, API collector, trend detection   | Chưa bắt đầu                                               |

## 6. Success criteria

- ≥ 3 nguồn RSS hoạt động ổn định
- Notification trong ≤ 30 phút từ lúc article publish
- Dedup 100% (không gửi trùng)
- False positive ≤ 5%
