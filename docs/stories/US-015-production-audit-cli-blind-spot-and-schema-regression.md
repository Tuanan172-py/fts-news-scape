# US-015 — Audit production: điểm mù CLI/subprocess, hồi quy enum schema, ngân sách cycle

- **Status:** implemented
- **Lane:** high-risk (chạm hợp đồng dữ liệu — xem §Bài học)
- **Parent / Epic:** Bronze Ingestion Pipeline
- **Intake date:** 2026-09-17 (intake #15)
- **Depends On:** US-011, US-012 — **story này sửa tiếp hồi quy của US-011**

## Product Contract

Hệ thống chạy ổn định với **biên dự phòng đo được**: mọi CLI entry point trên đường automation
được test thật qua subprocess; giá trị `capture_status` mới không chặn bài ở Silver; nhịp capture
có headroom so với thời lượng cycle đo thực tế.

## 5 lỗi còn sống, phát hiện bằng cách CHẠY THẬT

| # | Lỗi | Nguồn | Vì sao 403 test xanh vẫn không thấy |
|---|-----|-------|--------------------------------------|
| 3 | `__doc__.split("\n")[1]` → `IndexError` ngay dòng đầu (docstring 1 dòng) | có sẵn | Test import `main()` qua `importlib`, không đi qua `__main__` |
| 4 | `UnicodeEncodeError` khi in tiếng Việt lúc stdout là pipe | có sẵn | Test không chạy qua subprocess |
| 5 | `capture_interval_minutes: 5` < cycle đo thật **335s** | US-011 | Không test nào đo thời lượng cycle |
| 6 | Auto-drain `--limit 200` bị timeout 180s **mọi cycle** | US-011 | Test dùng fake HTTP, không có chi phí rate-limit thật |
| 7 | `subprocess.run(text=True)` thiếu `encoding` → `stdout=None` → `AttributeError` | US-011 | Không test nào vượt ranh giới subprocess |
| 8 | `deleted_at_source` **vi phạm enum** `work-package-v1.schema.json` → bài bị `held` ở Silver | US-011 | Không test nào validate work-package với giá trị mới |

Lỗi #3 có sức phá hoại lớn nhất: nó khiến auto-drain — tính năng chính của US-011 — **crash ngay
dòng đầu ở mọi lần gọi**, bị nuốt vào `logger.warning`, nên đã được báo cáo "hoàn thành" trong khi
chưa từng chạy nổi một lần.

## Bài học — phân loại lane của US-011 đã sai

Ở US-011 tôi tự đánh giá việc thêm giá trị `capture_status` mới là *"additive, backward-compatible,
không phải thay đổi hợp đồng dữ liệu công khai"* nên xếp lane `normal` và không lập ADR. Thực tế
`project/schemas/work-package-v1.schema.json:23` đang validate enum đó, và mọi bài bị gắn cờ đều bị
chặn ở cổng Silver. Đúng theo `FEATURE_INTAKE.md` §2, đây là cờ **Data contract** → hard gate →
lane `high-risk`. Thêm một giá trị vào enum vẫn là đổi hợp đồng nếu có consumer đang validate nó.

## Nguyên nhân gốc — điểm mù hệ thống

**52 script có khối `__main__`; 0 test nào dùng `subprocess`.** Ba lỗi (#3, #4, #7) nằm trọn trong
vùng mù này. Đã bịt bằng `project/tests/test_cli_entrypoints.py`: chạy `--help` của 9 script
automation qua subprocess với `capture_output=True` (tái hiện đúng điều kiện pipe/encoding của
morninger). Test này **bắt được lỗi #7 ngay trong vài phút đầu tồn tại**.

## Acceptance Criteria

- [x] `work-package-v1.schema.json` chấp nhận `deleted_at_source`.
- [x] `backfill_deferred.py` có `--budget-seconds`, dừng sạch giữa hai bài và vẫn in báo cáo.
- [x] `morninger` truyền `encoding="utf-8"` cho cả hai lời gọi subprocess, và phòng thủ `stdout=None`.
- [x] `capture_interval_minutes: 10` — headroom ~40% so với lượt job ~7 phút.
- [x] `deferred_backfill_limit` 200 → 60; timeout subprocess = budget + 60s.
- [x] `tests/test_cli_entrypoints.py` — 10 test, phủ 9 script automation.
- [x] Radar hiện cả số hôm nay lẫn tổng tích lũy cho metric bài bị nguồn xóa.

## Validation

| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q` | passed | **413 passed** (từ 403) |
| Integration | (trong cùng lệnh — test CLI chạy script thật qua subprocess) | passed | 10/10 |
| E2E | `backfill_deferred.py --fetch --mode all --budget-seconds 45` | passed | `fetched=14 failed=1 deleted_at_source=1 budget_stopped=1` exit 0 |
| Platform | restart `python -m src.morninger` | passed | log `capture/10min (+backfill_deferred nối tiếp), derive/30min, l1_route/15min, drift/6:0` |

**Platform tier lần đầu được trả** — đây là bằng chứng còn thiếu của US-011.

## Evidence

Auto-drain chạy trọn vẹn lần đầu tiên (11:10:59):
```
[backfill] hết ngân sách 45s — dừng sạch, phần còn lại để chu kỳ sau
backfill [all]: candidates=60 fetched=14 failed=1 deleted_at_source=1 budget_stopped=1
```
Radar xác nhận cờ đã xuống DB: `0 bài đăng hôm nay / 1 tổng tích lũy` — chứng minh luôn rằng metric
lọc theo `published_at` sẽ under-report vì bài bị xóa thường được phát hiện muộn hơn ngày đăng.

## Harness Delta

Backlog #8: `harness_cli.py intake` khai 9 giá trị `--type` trong argparse nhưng CHECK constraint
của DB chỉ nhận 6 — `qa_inquiry`/`diagnostic`/`exploration` (đều hợp lệ theo `FEATURE_INTAKE.md` §1)
luôn thất bại. Phát hiện khi ghi intake cho chính story này.

## Trace (inline)

- **Trace:** #49, `score_trace = 1.0`, `score_context = 1.0`.
- **Outcome:** completed.
