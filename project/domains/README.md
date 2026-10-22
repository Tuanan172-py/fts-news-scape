# Domain Mastery Framework

Framework chuyên biệt để "master" từng nguồn tin — hiểu rõ cấu trúc, phát hiện thay đổi,
log hàng ngày, dễ bảo trì khi upstream thay đổi.

---

## Cấu trúc

```
domains/
├── README.md                        # File này — tổng quan framework
├── cafef/
│   ├── README.md                    # Tài liệu mastery toàn diện về CafeF
│   ├── schema.yaml                  # Schema contract: expected fields, types, patterns
│   ├── changelog.md                 # Lịch sử mọi thay đổi của upstream
│   └── fixtures/
│       ├── samples.json             # Sample API response (dùng so sánh khi nghi ngờ)
│       └── detail_sample.html       # Sample detail page HTML
└── vietstock/
    ├── README.md                    # Tài liệu mastery toàn diện về Vietstock
    ├── schema.yaml                  # Schema contract
    ├── changelog.md                 # Lịch sử thay đổi upstream
    └── fixtures/
        └── samples.xml              # Sample RSS feed
```

## File mô tả

| File | Mục đích |
|------|----------|
| `README.md` | Tài liệu con người đọc: data flow, field mapping, pitfalls, quy trình bảo trì |
| `schema.yaml` | Contract máy đọc: field types, patterns, thresholds, watch points |
| `changelog.md` | Ghi lại mọi thay đổi của upstream ảnh hưởng đến scraper |
| `fixtures/` | Sample data capture dùng để regression test và so sánh khi nghi ngờ thay đổi |

## Công cụ đi kèm

Bộ `domain_validator` / `domain_reporter` / `domain_check.py` / `diagnose_sources.py` đã gỡ ở US-049.
Công cụ hiện hành (cwd = `project/`):

| Công cụ | Chức năng |
|---------|-----------|
| `python scripts/pipeline_radar.py status` | Trạng thái capture/wave và đúng một lệnh tiếp theo (đọc trước tiên, AGENTS.md §9) |
| `python -m src.monitor.health` | `scraper_heartbeat`: trạng thái từng scraper, lỗi liên tiếp, exit code |
| `python scripts/validate_capture.py [<domain>] [N]` | Audit capture thật: `capture_status`, sha256 khớp bytes, `images[]` |
| `python scripts/capture_reconcile.py status` | Độ lệch so với sitemap theo ngày (exit 1 khi vượt ngưỡng) |
| `python -m src.morninger --once drift` | Liệt kê bài `TEMPLATE_DRIFT` / `SELECTOR_BROKEN` |

`schema.yaml` mỗi domain còn được đọc khi phân giải host: `resolve_source_domain()` (`src/core/config.py`) lấy key `domain`.

## Quy trình làm việc

### Khi nghi ngờ upstream thay đổi

```bash
python scripts/pipeline_radar.py status          # nguồn nào thiếu tươi
python -m src.monitor.health                     # scraper nào lỗi liên tiếp
python -m src.morninger --once drift             # bài nào lệch template / hỏng selector
python scripts/validate_capture.py cafef 2       # fetch thật 2 bài, kiểm Bronze
```

### Khi xác nhận thay đổi

1. Cập nhật `domains/<domain>/schema.yaml`
2. Ghi `domains/<domain>/changelog.md`
3. Cập nhật `domains/<domain>/README.md` nếu cần
4. Sửa scraper code (`src/scrapers/`)
5. Cập nhật fixture samples (`tests/fixtures/`, `domains/<domain>/fixtures/`)
6. Chạy `validate_capture.py <domain>` để verify
7. Chạy test của scraper (`python -m pytest tests/scrapers/ -q`) để regression test

## Ngưỡng cảnh báo

Khai trong `schema.yaml` mỗi domain làm tài liệu tham chiếu; không công cụ hiện hành nào tự đọc các ngưỡng này. Mặc định:

| Ngưỡng | Giá trị | Ý nghĩa |
|--------|---------|---------|
| `article_count_drop_pct` | 50% | Số bài mới giảm >50% so với baseline |
| `field_fill_rate_drop_pct` | 20% | Fill rate field nào đó giảm >20% |
| `new_article_zero_streak` | 3 | 3 cycle liên tiếp 0 bài mới |
| `consecutive_failure_streak` | 3 | 3 cycle liên tiếp có lỗi |
