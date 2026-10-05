---
type: Metric
title: Sàn bộ nhớ đệm
description: Phép kiểm duy nhất phát hiện được tiền tố tĩnh trượt bộ nhớ đệm — so token trúng cache thật với sàn tiền tố × (số lượt gọi worker − 1).
tags: [metric, cache, cost, token, prefix]
status: stable
generated:
  at: 2026-09-21T00:00:00Z
sources:
  - id: ledger
    resource: project/scripts/token_ledger.py
    title: cache_shortfall, worker_calls
  - id: prefix
    resource: project/src/agent/prefix.py
    title: cached_prefix_tokens, compare_persona
  - id: radar
    resource: project/scripts/pipeline_radar.py
    title: Mục 3 của báo cáo token
  - id: pricing
    resource: project/config/token_pricing.yaml
    title: Chênh lệch giá hai rổ đầu vào
sources_last_checked: 2026-09-21
---

# Định nghĩa

```
sàn      = tiền_tố_tĩnh × (số_lượt_gọi_worker − 1)
hụt      = max(0, sàn − cacheReadTokens đo được)
trả thừa = hụt × (giá_cache_miss − giá_cache_hit)
```

`tiền_tố_tĩnh` = persona sinh từ catalog (~6.343 token) **cộng** phần harness luôn nối thêm
(~4.800: AGENTS.md, section tool/SDK, harness identity) ≈ **11.143 token**.[^prefix]

# Vì sao cần chỉ số này

Tỷ lệ trúng cache gộp cả đợt **không** phát hiện được tiền tố trượt. Nó vẫn cao khi các lượt
lặp bước — một lượt đi hai bước sẽ đọc lại trọn prompt ở giá cache và đẩy tỷ lệ lên trên 80%
ngay cả lúc tiền tố trượt sạch. Đợt W2 có tỷ lệ 82,7% trong khi vấn đề nằm ở chỗ khác.[^ledger]

Tiền tố trượt là **lỗi không có triệu chứng**: kết quả nghiệp vụ vẫn đúng, chỉ có phần lẽ ra
rẻ nhất bị tính giá đắt hơn **50 lần**.[^pricing] Không có phép kiểm này thì không gì báo.

# Đếm theo lượt gọi, không theo số phiên

Một đợt hai lô có **bốn** phiên DSH: phiên Conductor, lượt hâm bộ nhớ đệm, và hai lô. Phiên
Conductor mang persona khác và bộ tool khác nên nó không đọc tiền tố của worker. Lấy số phiên
làm sàn là đòi `11.143 × 3` trong khi chỉ hai lô đọc lại — cảnh báo kêu oan ở **mọi** đợt bình
thường, và một cảnh báo luôn kêu thì hết là tín hiệu.[^ledger]

Số lượt gọi worker đọc từ mô tả đợt: số lô cộng một nếu đợt có hâm cache. Không có mô tả thì
suy thô từ số phiên và báo cáo nói rõ đang dùng cơ sở nào.[^ledger]

# Đọc kết quả

| Kết quả | Nghĩa | Làm gì |
|---|---|---|
| `ĐẠT` | vượt sàn | bình thường; vượt nhiều là lúc cache gánh thay giá token mới |
| `HỤT` | dưới sàn | kiểm theo thứ tự bên dưới |

Thứ tự kiểm khi hụt:[^radar]

1. `build_article_prefix.py --check` — persona trong preset có còn khớp tệp prefix **từng
   byte** không. Đây là nguyên nhân số một.
2. Trong đợt có đổi tool set, model hay `reasoningEffort` không — cả ba đều đổi system prompt.
3. Phiên nào chạm ngưỡng nén 80% — compaction viết lại vùng surface là mất cache từ điểm ấy.

# Nơi hiển thị

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py append --wave W01 --items 100
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --wave W01
```

Sổ cái in dòng kiểm ngay sau khi ghi; radar in mục 3 kèm số tiền trả thừa quy đổi.[^radar]
