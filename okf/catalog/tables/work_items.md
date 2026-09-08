---
type: SQLite Table
title: work_items
description: Hàng đợi handoff producer↔agent — exactly-once, claim nguyên tử, 5 trạng thái vòng đời.
resource: "project/data/monocle.db (table: work_items)"
tags: [handoff, queue, agent, exactly-once]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: catalog
    resource: project/src/handoff/catalog.py
    title: Catalog — enqueue/claim/mark_done
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore schema DDL
  - id: handoff-design
    resource: project/docs/design/08-handoff-contract-catalog.md
    title: Handoff contract & catalog
sources_last_checked: 2026-09-07
---

`work_items` là **ranh giới producer ↔ consumer**: codebase (producer) enqueue việc, agent ngoài
(consumer) claim và trả kết quả. Đây là bảng duy nhất trong hệ có trạng thái *mutable* mà cả hai
phía cùng chạm tới.[^handoff-design]

**Exactly-once** đảm bảo bằng 2 cơ chế:[^catalog]

- **Idempotent enqueue** — `UNIQUE(article_id, raw_sha256)` + `INSERT OR IGNORE`. Cùng bài, cùng
  bản raw ⇒ chỉ 1 hàng; chạy lại pipeline không nhân đôi việc.
- **Claim nguyên tử** — `BEGIN IMMEDIATE` + `UPDATE ... WHERE status='pending'` ⇒ không thể hai
  worker cùng nhận một việc.

Thứ tự lấy việc mặc định là **newest-first** (`ORDER BY enqueued_at DESC, id DESC`) — tin mới
được ưu tiên xử lý trước.[^catalog]

# Vòng đời `status`

| `status` | Ý nghĩa |
|---|---|
| `pending` | đã enqueue, chưa ai nhận |
| `claimed` | agent đang xử lý |
| `done` | output qua Definition-of-Done |
| `failed` | DoD không đạt (lỗi vĩnh viễn) |
| `held` | precondition fail — không giao agent |

`held` xảy ra khi `change_state ∈ {SELECTOR_BROKEN, TEMPLATE_DRIFT}` hoặc work-package không
PASS schema `work-package-v1` (`force_held=True`).[^catalog] Không có state mồ côi: mọi hàng luôn
ở đúng 1 trong 5 giá trị trên.

# Schema

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | |
| `article_id` | TEXT NOT NULL | = `articles.url_title_hash` |
| `raw_sha256` | TEXT NOT NULL | SHA-256 bản raw Bronze (khoá provenance) |
| `domain` | TEXT | Tên miền nguồn |
| `package_path` | TEXT | Đường dẫn work-package JSON (`data/work_packages/**`) |
| `status` | TEXT NOT NULL DEFAULT pending | Xem bảng vòng đời |
| `claimed_by` | TEXT | Định danh worker đã nhận |
| `claimed_at` | TEXT | Thời điểm claim |
| `done_at` | TEXT | Thời điểm hoàn tất |
| `error` | TEXT | Lý do fail |
| `change_state` | TEXT | Trạng thái change-detection lúc enqueue |
| `enqueued_at` | TEXT | Thời điểm vào hàng đợi |

**Constraints:** `UNIQUE(article_id, raw_sha256)` ·
**Index:** `idx_work_items_status` trên `(status, enqueued_at)`

# Common Query Patterns

### Tồn đọng theo trạng thái

```sql
SELECT status, COUNT(*) AS n FROM work_items GROUP BY status ORDER BY n DESC;
```

### Việc kẹt ở `claimed` quá 6 giờ (agent chết giữa chừng)

```sql
SELECT id, article_id, claimed_by, claimed_at
FROM work_items
WHERE status = 'claimed' AND claimed_at < datetime('now', '-6 hours', 'localtime')
ORDER BY claimed_at;
```

### Domain bị held nhiều nhất (selector cần sửa)

```sql
SELECT domain, change_state, COUNT(*) AS n
FROM work_items
WHERE status = 'held'
GROUP BY domain, change_state
ORDER BY n DESC;
```

# Joins

- [articles](articles.md) / [article_versions](article_versions.md) qua `article_id`
- [agent_outputs](agent_outputs.md) qua `(article_id, raw_sha256)` hoặc `agent_outputs.work_item_id`

# Pipeline liên quan

- Sinh bởi [Silver Derive](../pipelines/silver_derive.md)
- Tiêu thụ bởi [Agent Handoff](../pipelines/agent_handoff.md)

# Metrics

- [Silver Backlog](../metrics/silver_backlog.md)

[^catalog]: [Catalog implementation](project/src/handoff/catalog.py)
[^db-store]: [ArticleStore schema DDL](project/src/db/store.py)
[^handoff-design]: [Handoff contract & catalog](project/docs/design/08-handoff-contract-catalog.md)
