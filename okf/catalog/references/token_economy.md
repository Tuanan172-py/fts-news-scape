---
type: Reference
title: Kinh tế token và bộ nhớ đệm
description: Mô hình chi phí ba rổ token của lớp agent — đâu là tiền thật, đâu là hạn mức, bộ nhớ đệm đáng bao nhiêu, và đòn bẩy nào xếp trước.
resource: project/config/token_pricing.yaml
tags: [reference, cost, token, cache, deepseek, dsh]
status: stable
generated:
  at: 2026-09-21T00:00:00Z
sources:
  - id: pricing
    resource: project/config/token_pricing.yaml
    title: Bảng giá và cửa sổ giá — nguồn duy nhất
  - id: usage
    resource: project/src/telemetry/dsh_usage.py
    title: Đọc số đo thật từ runtime DSH, sáu luật kế toán
  - id: ledger
    resource: project/scripts/token_ledger.py
    title: Sổ cái token và sàn bộ nhớ đệm
  - id: prefix
    resource: project/src/agent/prefix.py
    title: Kích thước tiền tố tĩnh
  - id: estimate
    resource: project/scripts/estimate_wave.py
    title: Dự toán trước đợt và đối chiếu sau đợt
  - id: surface
    resource: docs/proposals/dsh-surface-verified-2026-09-18.md
    title: Bề mặt DSH đã xác minh bằng mã nguồn
  - id: plan
    resource: plans/20260918-1651-article-lane-unified/plan.md
    title: Thiết kế, số đo và mục §17 về bộ nhớ đệm
sources_last_checked: 2026-09-21
---

Mọi con số chi phí của hệ phải đến từ **số đo thật của runtime**, không từ định mức nhân tay.
Hai định mức cũ khai trong `registry.yaml` — 450 token mỗi bài tầng L1, 1.470 tầng Gold — lệch
thực tế **21 đến 41 lần** và không ai phát hiện suốt nhiều tháng, vì chưa từng có chỗ nào đối
chiếu dự toán với số đo.[^plan]

# Ba rổ token rời rạc

Nhà cung cấp tính riêng ba rổ, và chúng chênh nhau rất xa:[^pricing]

| Rổ | USD / 1M token, off-peak | So với rổ rẻ nhất |
|---|---:|---:|
| Đầu vào **trúng** bộ nhớ đệm | 0,003 | 1× |
| Đầu vào **mới** | 0,15 | **50×** |
| Đầu ra | 0,60 | **200×** |

Giờ cao điểm 01:00–04:00 và 06:00–10:00 UTC, T2–T6 (tức 08:00–11:00 và 13:00–17:00 giờ VN)
nhân đôi cả ba rổ. Mọi khung khác, kể cả cuối tuần, rẻ một nửa.[^pricing]

**`cache_write` luôn bằng 0** với adapter DeepSeek, nên không dựng dòng chi phí cho nó.[^usage]

# Hai thước đo khác nhau, không thay thế nhau

| Thước | Nghĩa | Dùng khi |
|---|---|---|
| `quota_tokens` | tổng ba rổ, **đếm cả** token trúng cache | so tải giữa các đợt |
| `billed_usd` | tiền thật, tính ngoài từ bảng giá | mọi quyết định về chi phí |

Hai thước lệch nhau rất xa vì token trúng cache rẻ hơn 50 lần. DSH **không lưu bất kỳ dữ liệu
giá nào**, nên tiền luôn tính ngoài.[^usage]

# Sáu luật kế toán

Mỗi luật đã đối soát bằng số thật, và mỗi luật từng bị đọc sai:[^usage]

1. `inputTokens` là phần **chưa cache**, không phải kích thước prompt. Đọc nhầm hụt ~30 lần.
2. `inputTokens + cacheReadTokens + outputTokens == totalTokens` **theo từng request**;
   `totalTokens` không tích luỹ nên tuyệt đối không cộng dồn.
3. `reasoningTokens` là **tập con** của `outputTokens`. Cộng cả hai là đếm trùng.
4. `cacheWriteTokens` luôn 0 với adapter DeepSeek.
5. DSH không lưu giá ở bất kỳ đâu.
6. `surfaceTokens = systemTokens + messageTokens`, **không** gồm `toolsTokens`;
   `pressureTokens` là tổng đầu vào của mẫu mới nhất, **không** gồm đầu ra.

Chi phí của agent con **không** nằm trong `tokenUsage` của phiên cha — mỗi con là một Session
riêng. Muốn biết chi phí trọn một đợt phải cộng cả phiên cha lẫn từng phiên con.[^usage]

# Bộ nhớ đệm đáng bao nhiêu — hai câu trả lời, cả hai đều đúng

Đo trên đợt W2 thật (200 bài):[^ledger]

| Rổ | Token | Chi phí | Tỷ trọng |
|---|---:|---:|---:|
| Đầu ra | 162.703 | $0,0976 | **62%** |
| Đầu vào mới | 360.365 | $0,0541 | 34% |
| Đầu vào trúng cache | 1.723.520 | $0,0052 | 3,3% |

- **Tiền tố tĩnh chỉ đáng ~1,4% hoá đơn** ở cỡ lô 100 bài. Nó không phải cần gạt tiết kiệm:
  phần lặp `C` ≈ 11.143 token còn phần mới `N` ≈ 154.200 token cho một lô trăm bài, tức tỷ lệ
  ngược hẳn với giả định thường thấy trong tài liệu về prompt caching.
- **Nhưng bỏ cache đi thì hoá đơn W2 thành $0,410 thay vì $0,157.** 1,72 triệu token tái dùng
  ấy đến từ những lượt đi hai bước; không có cache, chúng bị tính giá mới. Cache là **bảo
  hiểm** cho lượt lặp bước và lần chạy lại, không phải khoản giảm giá để thu.

**Hệ quả ngược chiều trực giác:** vì token trong prefix gần như miễn phí từ lượt thứ hai, cache
biến prefix thành **ngân sách tri thức**. Nạp trọn digest 1.093 mã chứng khoán (+21.500 token)
chỉ làm đợt 300 bài đắt thêm ~1,5%. Trần thật của prefix là cửa sổ ngữ cảnh, không phải tiền.

# Xếp hạng đòn bẩy

| Hạng | Đòn bẩy | Độ lớn |
|---:|---|---|
| 1 | **Đầu ra** — kích thước bản ghi | 55–62% hoá đơn |
| 2 | **Khung giá thấp điểm** | −50% cả ba rổ; đợt 300 bài $0,233 so với $0,466 |
| 3 | **Số bước** | mỗi bước thừa gửi lại trọn lịch sử |
| 4 | **Tiền tố tĩnh** | ~1,4% ở cỡ lô 100 bài |

Chọn giờ chạy đáng giá gấp khoảng **36 lần** toàn bộ phần tối ưu tiền tố cho cùng một đợt.

# Sàn bộ nhớ đệm — phép kiểm duy nhất bắt được tiền tố trượt

Tỷ lệ trúng cache gộp cả đợt **không** phát hiện được prefix trượt: nó vẫn cao khi các lượt lặp
bước. Phép kiểm đúng là so với sàn `tiền tố × (số lượt gọi worker − 1)`.[^ledger] Xem
[Metrics › Sàn bộ nhớ đệm](../metrics/cache_hit_floor.md).

Bốn thứ làm vỡ tiền tố: persona lệch tệp prefix · đổi tool set, model hay effort giữa đợt ·
compaction viết lại vùng surface · sai preset.[^surface]

# Sai số dự toán là chỉ số hạng nhất

`estimate_wave.py` đặt dự toán lên bàn trước khi tiêu token và nói lại sau khi tiêu xong đã
lệch bao nhiêu.[^estimate] Chỉ hai khoản là **dự báo** nên sai số mới có nghĩa: đầu vào mới và
đầu ra. Khoản tái dùng là **sàn**, vượt sàn là lành mạnh.
