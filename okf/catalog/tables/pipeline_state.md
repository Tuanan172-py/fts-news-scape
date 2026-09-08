---
type: SQLite Table
title: pipeline_state
description: Key/value bền vững qua restart — watermark re-derive, checkpoint Silver, advisory lock scheduler.
resource: "project/data/monocle.db (table: pipeline_state)"
tags: [state, watermark, lock, morninger]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: get_state/set_state + try_acquire_lock/release_lock
  - id: derive
    resource: project/src/pipeline/derive.py
    title: Watermark re-derive tăng dần
  - id: proclock
    resource: project/src/core/proclock.py
    title: Advisory scheduler lock
  - id: morninger
    resource: project/src/morninger.py
    title: Morninger 3-job scheduler
sources_last_checked: 2026-09-07
---

`pipeline_state` là bảng key/value nhỏ giữ **trạng thái điều phối** sống sót qua restart. Không
chứa dữ liệu nghiệp vụ.[^db-store]

# Các khoá đang dùng

| Key | Ghi bởi | Ý nghĩa |
|---|---|---|
| `silver_watermark` | `pipeline.derive` | `fetch_ts` lớn nhất đã re-derive thành công. Lần sau **chỉ** xử lý Bronze artifact có `fetch_ts` lớn hơn (strict `>`).[^derive] |
| `silver_checkpoint` | `pipeline.derive` / `morninger` | Đánh dấu "danh sách tin cấp Silver đã cập nhật đầy đủ" — backlog = 0 khi không còn file nào vượt watermark.[^morninger] |
| `lock:scheduler` | `morninger` / `orchestrator` | Advisory lock chống chạy 2 scheduler cùng lúc. Value = `host:pid`.[^proclock] |

# Advisory lock — cơ chế

`try_acquire_lock(name, owner, stale_seconds)` chạy trong `BEGIN IMMEDIATE`; chiếm được lock
nếu **một trong các điều kiện**:[^db-store]

- chưa có ai giữ, hoặc owner chính là mình;
- owner cũ cùng host nhưng PID đã chết (`os.kill(pid, 0)` lỗi);
- bản ghi lock quá cũ (`updated_at` vượt `stale_seconds`).

`SCHEDULER_LOCK_STALE_SECONDS = 2400` (40 phút) — **phải lớn hơn** chu kỳ capture 15′ để lock
không bị cướp giữa hai nhịp; chủ sở hữu refresh lock mỗi cycle.[^proclock]

# Schema

| Column | Type | Description |
|---|---|---|
| `key` | TEXT PRIMARY KEY | Tên khoá (lock dùng tiền tố `lock:`) |
| `value` | TEXT | Giá trị (watermark ISO, hoặc `host:pid`) |
| `updated_at` | TEXT | Thời điểm ghi gần nhất (ISO 8601, giờ VN) |

# Common Query Patterns

### Xem toàn bộ trạng thái điều phối

```sql
SELECT key, substr(value, 1, 40) AS value, updated_at
FROM pipeline_state ORDER BY key;
```

### Ai đang giữ lock scheduler

```sql
SELECT value AS owner, updated_at FROM pipeline_state WHERE key = 'lock:scheduler';
```

Xoá lock mồ côi (chỉ khi chắc chắn không còn tiến trình nào chạy):

```sql
DELETE FROM pipeline_state WHERE key = 'lock:scheduler';
```

# Pipeline liên quan

- [Morninger](../pipelines/morninger.md) · [Silver Derive](../pipelines/silver_derive.md)

[^db-store]: [ArticleStore state + lock](project/src/db/store.py)
[^derive]: [derive.py](project/src/pipeline/derive.py)
[^proclock]: [proclock.py](project/src/core/proclock.py)
[^morninger]: [morninger.py](project/src/morninger.py)
