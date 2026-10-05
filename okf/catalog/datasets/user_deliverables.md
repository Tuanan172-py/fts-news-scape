---
type: File Dataset
title: User Deliverables
description: CSV cuối cho từng người dùng theo ngày (users/output/**) + bản audit tập trung _master.
resource: users/output/
tags: [gold, deliverable, csv, per-user]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: user-output
    resource: project/src/export/user_output.py
    title: UserOutputWriter — gate, route, ghi CSV
  - id: checkpoint
    resource: project/src/export/checkpoint.py
    title: Checkpoint resume theo article_id
  - id: user-workflow-design
    resource: project/docs/design/13-per-user-output-workflow.md
    title: Per-user output workflow
sources_last_checked: 2026-09-07
---

Sản phẩm cuối của toàn hệ thống: **1 file CSV / người dùng / ngày**, chỉ chứa tin chạm tới
entity mà người đó đăng ký.[^user-output]

# Bố cục trên đĩa

```
users/output/<user>/<YYYY-MM-DD>.csv     # deliverable phẳng, duy nhất cho người dùng
users/output/<user>/_checkpoint.json     # resume theo article_id
users/output/_master/<YYYY-MM-DD>.csv        # audit — mọi bài gated (không lọc theo user)
users/output/_master/<YYYY-MM-DD>_L1.csv     # audit — lớp 1
users/output/_master/<YYYY-MM-DD>_agent.csv  # audit — lớp 2
```

⚠️ Đây là **bố cục phẳng hiện hành** (đổi 2026-09). Thiết kế 13 mô tả bố cục cũ
`users/output/<user>/<date>/final.csv` — code là nguồn đúng.

# Cột `final.csv` (15 cột)

`date, matched_entities, title, summary, key_points, implication, impact_area,
time_sensitivity, sentiment, event_type, url, source_domain, article_id, agent_provider,
model_used`

- Cột nghiệp vụ lên đầu, cột kỹ thuật về cuối.
- `matched_entities` = **code** các entity người dùng đăng ký mà bài chạm (nối bằng `; `).
- `summary` ← `summary.abstractive`; `key_points` ← danh sách gạch đầu dòng xuống dòng trong ô;
  `implication` ← `implication.text`; `sentiment` ← `sentiment.polarity`.
- Encoding `utf-8-sig` để Excel mở tiếng Việt không lỗi font.
- **Đã bỏ** `confidence` (2026-08-18) và `materiality_score` (chỉ còn ở bản audit `_agent.csv`).

# Điều kiện một bài vào file

1. **Gate DoD** — `l1_outputs.dod_pass = 1` (bắt buộc); `agent_outputs.dod_pass = 1` (tuỳ chọn —
   thiếu thì các cột nghiệp vụ để trống).
2. **Định tuyến** — entity `in_list` của L1 ∩ subscription của người dùng ≠ ∅, và người dùng
   đang BẬT trong manifest.
3. **Noise filter** — nếu chỉ khớp thực thể *diện rộng* (`MACRO_GEO`, `MACRO_THEME`,
   `ASSET_CLASS`) thì phải thêm một trong hai: `materiality.score ≥ 0.6`, hoặc alias entity xuất
   hiện ngay trong tiêu đề. Có ít nhất 1 thực thể cụ thể (ticker/ngành/chỉ số/sàn/định chế) ⇒
   pass thẳng.[^user-output]

# Idempotency

- `write()` **rewrite toàn tập** per (user, ngày) + dedupe theo `article_id` ⇒ chạy lại không
  nhân đôi dòng.
- Ghi nguyên tử (temp + `os.replace`), rồi mới `mark_written()` vào `_checkpoint.json` ⇒ ngắt
  giữa chừng vẫn an toàn, lần sau ghi bù.[^checkpoint]

# Chẩn đoán

Writer log sẵn 2 tín hiệu vận hành:[^user-output]
- **orphan** — số bài đạt gate nhưng không người dùng nào đăng ký.
- **backlog** — `--date today` ra 0 dòng nhưng vẫn còn bài đạt L1 ở ngày trước ⇒ gợi ý chạy
  `--days 30` hoặc `--date all`.

# Quan hệ

- Sinh bởi [User Output](../pipelines/user_output.md)
- Đầu vào định tuyến: [l1_outputs](../tables/l1_outputs.md) + [User Subscriptions](../configurations/user_subscriptions.md)

[^user-output]: [UserOutputWriter](project/src/export/user_output.py)
[^checkpoint]: [checkpoint.py](project/src/export/checkpoint.py)
[^user-workflow-design]: [Per-user output workflow](project/docs/design/13-per-user-output-workflow.md)
