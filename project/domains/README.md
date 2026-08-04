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

| Công cụ | Vị trí | Chức năng |
|---------|--------|-----------|
| `domain_validator` | `src/monitor/domain_validator.py` | Validate field-level, detect anomaly vs baseline |
| `domain_reporter` | `src/monitor/domain_reporter.py` | Sinh báo cáo hằng ngày |
| `domain_check` | `scripts/domain_check.py` | CLI tool: validate, report, raw-check |

## Quy trình làm việc

### Hằng ngày

```bash
# Kiểm tra nhanh tất cả domain
python scripts/domain_check.py

# Tạo báo cáo chi tiết
python scripts/domain_check.py --report
```

Report được lưu vào `data/reports/daily/{domain}-{date}.md`.

### Khi nghi ngờ upstream thay đổi

```bash
# Kiểm tra raw response (không cần cycle)
python scripts/domain_check.py cafef --raw-check

# Validate articles hiện có trong DB
python scripts/domain_check.py vietstock

# Chạy diagnostic chuyên sâu
python scripts/diagnose_sources.py cafef
```

### Khi xác nhận thay đổi

1. Cập nhật `domains/<domain>/schema.yaml`
2. Ghi `domains/<domain>/changelog.md`
3. Cập nhật `domains/<domain>/README.md` nếu cần
4. Sửa scraper code (`src/scrapers/`)
5. Cập nhật fixture samples
6. Chạy `domain_check` để verify
7. Chạy test suite để regression test

## Ngưỡng cảnh báo

Định nghĩa trong `schema.yaml` mỗi domain. Mặc định:

| Ngưỡng | Giá trị | Ý nghĩa |
|--------|---------|---------|
| `article_count_drop_pct` | 50% | Số bài mới giảm >50% so với baseline |
| `field_fill_rate_drop_pct` | 20% | Fill rate field nào đó giảm >20% |
| `new_article_zero_streak` | 3 | 3 cycle liên tiếp 0 bài mới |
| `consecutive_failure_streak` | 3 | 3 cycle liên tiếp có lỗi |
