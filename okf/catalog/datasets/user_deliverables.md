---
type: File Dataset
title: User Deliverables
description: Một file .xlsx cho mỗi người dùng mỗi ngày dưới <DATA_ROOT>/users/output/ + bản audit CSV tập trung _master.
resource: "<DATA_ROOT>/users/output/"
tags: [gold, deliverable, xlsx, per-user]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: user-output
    resource: project/src/export/user_output.py
    title: UserOutputWriter — gate, route, ghi xlsx + _master
  - id: xlsx
    resource: project/src/export/xlsx_delivery.py
    title: DELIVERY_FIELDS — hợp đồng cột của file giao
  - id: checkpoint
    resource: project/src/export/checkpoint.py
    title: Checkpoint resume theo article_id
  - id: paths
    resource: project/src/core/paths.py
    title: users_output_dir()
sources_last_checked: 2026-10-22
---

Sản phẩm cuối của toàn hệ thống: **1 file `.xlsx` / người dùng / ngày**, chỉ chứa tin chạm tới
entity mà người đó đăng ký.[^user-output] CSV không còn là deliverable (US-101): CSV không giữ
được độ rộng cột, freeze, filter, wrap.

# Bố cục trên đĩa (ADR-0026.D6)

```
<DATA_ROOT>/users/output/<user>/<YYYY-MM-DD>.xlsx       # deliverable, duy nhất cho người dùng
<DATA_ROOT>/users/output/<user>/_checkpoint.json        # resume theo article_id
<DATA_ROOT>/users/output/_master/<YYYY-MM-DD>.csv       # audit — mọi bài gated (không lọc theo user)
<DATA_ROOT>/users/output/_master/<YYYY-MM-DD>_L1.csv    # audit — nhận diện thực thể
<DATA_ROOT>/users/output/_master/<YYYY-MM-DD>_agent.csv # audit — nội dung
```

`<DATA_ROOT>` = `MONOCLE_DATA_DIR`, mặc định `C:\data\news-scape` (`paths.users_output_dir()`).[^paths]
Cây cũ `users_output/` còn trên đĩa tới khi người vận hành chạy
`scripts/maintenance/migrate_users_output.py --apply`.

# Cột của sheet giao (`DELIVERY_FIELDS`)

`Date, Matched Entities, Intent — LLM, Intent — Code, Intent Source, Title, Sentiment,
Time Sensitivity, Gold Status, Source, Summary, Key Points, Market Implication, URL, Article ID`[^xlsx]

- `Matched Entities` = **code** các entity người dùng đăng ký mà bài chạm (nối bằng `; `).
- `Intent — LLM` / `Intent — Code` / `Intent Source` — entity mô hình nhận ra, entity từ điển
  khớp, và nhãn đối chiếu (giá trị của mô hình nằm ở nhãn `LLM_ONLY`).
- `Gold Status` = `Full` (có bản nội dung đạt DoD) hoặc `Preliminary` (`L1_ONLY`).
- Enum hiển thị tiếng Anh (`Positive`, `This Week`…); giá trị lạ giữ nguyên.
- Có thêm sheet radar chú ý dựng từ `signal_daily` khi có dữ liệu.
- Đã bỏ: `confidence`, `materiality`, `event_type`, `impact_area`.

Bản `_master/<ngày>.csv` dùng `MASTER_COLUMNS` (cột chuẩn + `l1_source`, `noise_signals`),
encoding `utf-8-sig`.[^user-output]

# Điều kiện một bài vào file

1. **Gate DoD** — bản nhận diện `l1_outputs.dod_pass = 1` và **không** phải `code_first`
   (bắt buộc); bản nội dung `agent_outputs.dod_pass = 1` là tuỳ chọn.
2. **Định tuyến** — entity `in_list` ∩ subscription của người dùng ≠ ∅, và người dùng đang BẬT
   trong manifest.
3. **Noise filter** — chỉ khớp thực thể *diện rộng* (`MACRO_GEO`, `MACRO_THEME`, `ASSET_CLASS`)
   thì alias phải xuất hiện trong tiêu đề. Có ít nhất 1 thực thể cụ thể ⇒ pass thẳng.[^user-output]

# Idempotency

- Rewrite toàn tập per (user, ngày) + dedupe theo `article_id`; không có bài mới/nâng hạng thì
  bỏ qua.
- Ghi nguyên tử rồi mới `mark_written()` vào `_checkpoint.json`; file bị khoá ⇒ ghi snapshot,
  không mark.[^checkpoint]

# Quan hệ

- Sinh bởi [User Output](../pipelines/user_output.md)
- Đầu vào định tuyến: [l1_outputs](../tables/l1_outputs.md) + [User Subscriptions](../configurations/user_subscriptions.md)

[^user-output]: [UserOutputWriter](project/src/export/user_output.py)
[^xlsx]: [xlsx_delivery.py](project/src/export/xlsx_delivery.py)
[^checkpoint]: [checkpoint.py](project/src/export/checkpoint.py)
[^paths]: [paths.py](project/src/core/paths.py)
