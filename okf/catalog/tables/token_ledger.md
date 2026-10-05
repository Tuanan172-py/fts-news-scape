---
type: SQLite Table
title: token_ledger
description: Sổ cái chi phí mỗi đợt xử lý — ba rổ token đo thật từ runtime DSH, quota, tiền, áp suất ngữ cảnh và sai số dự toán. Nằm ở harness.db, không phải monocle.db.
resource: "harness.db (table: token_ledger)"
tags: [table, harness, cost, token, cache, telemetry]
status: stable
generated:
  at: 2026-09-21T00:00:00Z
sources:
  - id: ledger
    resource: project/scripts/token_ledger.py
    title: DDL, append, report, verify, cache_shortfall
  - id: usage
    resource: project/src/telemetry/dsh_usage.py
    title: Gộp số đo phiên cha và phiên con thành một đợt
  - id: run
    resource: project/scripts/article_run.py
    title: Gọi ghi sổ ở nửa hoàn tất
  - id: radar
    resource: project/scripts/pipeline_radar.py
    title: Báo cáo token đọc từ sổ cái
sources_last_checked: 2026-09-21
---

Bảng này sống ở **`harness.db` tại gốc kho**, không ở `monocle.db`: nó đo *quá trình làm việc*
chứ không mô tả dữ liệu tin tức.[^ledger]

# Cột

| Cột | Nghĩa |
|---|---|
| `ts` | mốc ghi sổ, **ISO UTC** — không phải giờ máy |
| `wave`, `batch_id`, `agent_id` | khoá quy kết |
| `n_items`, `n_sessions` | số bài và số phiên DSH được gộp |
| `miss_tokens` | đầu vào **chưa** trúng cache (`inputTokens` của DSH) |
| `hit_tokens` | đầu vào trúng cache (`cacheReadTokens`) |
| `out_tokens` | đầu ra, **đã gồm** phần suy luận |
| `reasoning_tokens` | tập con của `out_tokens`; `NULL` khi không giải nén được JSONL |
| `quota_tokens` | tổng ba rổ — thước hạn mức, không phải tiền |
| `turns_max` | số bước lớn nhất trong các phiên; `> 1` là worker không xong trong một bước |
| `ctx_peak`, `ctx_pct` | áp suất ngữ cảnh cao nhất |
| `est_miss`, `est_out` | dự toán tương ứng, để đo sai số |
| `billed_usd` | tiền, tính ngoài từ bảng giá |
| `peak_window` | 1 nếu đợt rơi vào khung giá cao điểm |

# Ba cái bẫy khi đọc bảng

**1. Các dòng cùng một đợt là ảnh chụp TÍCH LUỸ, không phải phần tăng thêm.** Chạy `append`
lại khi các phiên con lần lượt kết thúc thì dòng sau chứa trọn dòng trước — đợt W2 có bốn
dòng. Cộng thẳng cho ra 800 bài cho một đợt 200 bài. Quy ước chung của mọi công cụ: **lấy dòng
mới nhất của mỗi `(wave, batch_id, agent_id)`** (`latest_snapshots`).[^ledger]

**2. `ts` theo UTC, người vận hành nghĩ theo giờ máy.** Lệch bảy tiếng ở Việt Nam: mọi đợt chạy
trước 07:00 giờ VN rơi vào ngày hôm trước theo UTC. Công cụ lọc theo ngày phải đổi ngày địa
phương thành khoảng UTC trước khi so.[^radar]

**3. `n_sessions` gồm cả phiên Conductor.** Phiên điều phối mang persona khác nên **không** đọc
tiền tố của worker; đếm nó như một worker làm sàn bộ nhớ đệm đòi một khoản cache không bao giờ
tồn tại.[^ledger] Xem [Metrics › Sàn bộ nhớ đệm](../metrics/cache_hit_floor.md).

# Lệnh

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py append --wave W01 --items 100
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py report --wave W01
& "C:\venvs\news-scape\Scripts\python.exe" scripts/token_ledger.py verify
```

`append` được `article_run.py --finish` gọi tự động với mốc `--since` neo vào thời điểm đóng
gói đợt; lấy mốc rộng hơn sẽ gộp nhầm phiên DSH khác đang mở song song và thổi phồng con số
token mỗi bài.[^run] `verify` đối soát sáu luật kế toán trên dữ liệu phiên thật.[^usage]
