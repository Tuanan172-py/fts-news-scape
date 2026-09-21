---
type: Configuration
title: Token Pricing & Watch Thresholds
description: Bảng giá ba rổ token, cửa sổ giờ cao điểm và các ngưỡng cảnh báo vận hành — nguồn giá duy nhất của hệ, không hardcode trong mã.
resource: project/config/token_pricing.yaml
tags: [config, yaml, cost, token, deepseek, thresholds]
status: stable
generated:
  at: 2026-09-21T00:00:00Z
sources:
  - id: pricing
    resource: project/config/token_pricing.yaml
    title: Bảng giá và ngưỡng
  - id: usage
    resource: project/src/telemetry/dsh_usage.py
    title: load_pricing, is_peak, billed_usd
  - id: pack
    resource: project/scripts/article_pack.py
    title: Chốt tự động est_ctx_peak
sources_last_checked: 2026-09-21
---

Tệp này là **nguồn giá duy nhất**. DSH không lưu bất kỳ dữ liệu giá nào (đã xác minh mã nguồn),
nên `billed_usd` luôn được tính ngoài, từ ba rổ token rời rạc nhân đơn giá ở đây. Nhà cung cấp
đổi giá thì sửa **duy nhất** tệp này.[^pricing]

# Ba khối nội dung

| Khối | Nội dung |
|---|---|
| `models.<model>.{off_peak,peak}` | ba đơn giá: `input_cache_hit`, `input_cache_miss`, `output`, tính trên 1 triệu token |
| `peak_windows_utc` | các khung giờ cao điểm theo **UTC** và các ngày trong tuần áp dụng |
| `watch_thresholds` | ngưỡng để **nhìn**, không phải cổng chặn |

Không có dòng giá cho `cache_write` vì trường ấy **luôn bằng 0** với adapter DeepSeek.[^usage]

# Cửa sổ giá

Cao điểm 01:00–04:00 và 06:00–10:00 UTC, thứ Hai đến thứ Sáu — tức **08:00–11:00 và 13:00–17:00
giờ Việt Nam**. Ngoài các khung ấy, kể cả cuối tuần, mọi rổ rẻ **một nửa**.[^pricing]

Hệ quả vận hành: làn bulk và backlog nên chạy ngoài khung cao điểm. Đo trên đợt 300 bài,
chênh lệch là $0,233 so với $0,466 — lớn hơn mọi tối ưu prompt cộng lại.

# Ngưỡng cảnh báo

| Khoá | Ý nghĩa | Hành vi |
|---|---|---|
| `context_pressure_amber` | áp suất ngữ cảnh 25% | xong đợt hiện tại thì đóng phiên |
| `context_pressure_red` | áp suất 40% | dừng ngay sau lô hiện tại |
| `tokens_per_article_warn` | 2.500 token quota mỗi bài | soi lại distillation hoặc mốc quy kết |
| `worker_turns_expected` | 1 | worker phải xong trong đúng một bước |

Đây là **mức để nhìn**. Hai chốt tự động duy nhất nằm ở `article_pack.py` (`est_ctx_peak`) và
`article_run.py` (parse_fail).[^pack]

`tokens_per_article_warn` từng để 1.500 và vì thế báo động ở **mọi** đợt bình thường — một
cảnh báo luôn kêu thì hết là tín hiệu. Hiệu chuẩn lại ngày 2026-09-21 theo cỡ bản ghi đo thật:
~800 token đầu vào chưa cache cộng ~900 token đầu ra mỗi bài.[^pricing]

Xem thêm: [References › Kinh tế token](../references/token_economy.md).
