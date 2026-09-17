# US-012 — Content Recovery Engine (retry có trạng thái, ngưỡng bỏ cuộc, khôi phục lỗi tạm thời)

- **Status:** implemented
- **Lane:** normal
- **Parent / Epic:** Bronze Ingestion Pipeline
- **Intake date:** 2026-09-17 (intake #12)
- **Depends On:** US-011 — **story này sửa lỗi hồi quy do US-011 gây ra**

## Product Contract

Mọi bài chưa lấy được nội dung đầy đủ đều được thử lại **có giới hạn và có ghi sổ**. Bài đã xác
nhận mất vĩnh viễn (nguồn xóa 404/410) hoặc đã thử đủ ngưỡng bị loại khỏi hàng đợi, không còn bị
fetch lại vô hạn.

## Lỗi hồi quy được sửa

US-011 thêm bộ lọc loại bài `source_deleted` khỏi `_DEFERRED_WHERE`, nhưng **không có gì ghi cờ đó
xuống DB trên đường backfill**. `backfill_deferred.py:244-246` khi gặp thất bại chỉ `stats["failed"] += 1`
rồi `continue` — không chạm DB. Nguyên nhân gốc: `_INSERT_SQL` của ArticleStore là `INSERT OR IGNORE`
(`project/src/db/store.py:78-81`) nên row đã tồn tại không bao giờ tự cập nhật; bắt buộc `UPDATE` tường
minh. Hệ quả nếu không vá: sau khi restart morninger, mỗi bài đã bị xóa vĩnh viễn sẽ bị fetch lại mỗi
5 phút — khoảng 288 request rác/ngày/bài, không bao giờ dừng.

## Acceptance Criteria

- [x] `_record_attempt()` ghi `capture_retry.{attempts,last_at,last_status}` vào `metadata_json` ở
      **mọi** nhánh thất bại (HTTP lỗi, thiếu file, bóc ra rỗng).
- [x] 404/410 → `source_deleted: true`; đủ `max_attempts` → `capture_giveup: true`.
- [x] `_EXCLUDE_DEAD` dùng chung, loại cả hai cờ khỏi `_DEFERRED_WHERE` và `_FAILED_WHERE`.
- [x] `--mode {deferred,failed,all}` (mặc định `deferred` — giữ nguyên runbook + test cũ);
      morninger gọi `--mode all`.
- [x] `--max-attempts` (5) và `--retry-window-hours` (morninger truyền 24; CLI mặc định 0 = không
      giới hạn, giữ nguyên backfill thủ công hàng loạt).
- [x] `SourceBackoff.before_fetch/observe` bao quanh mọi fetch của đường backfill.
- [x] `--dry-run` không ghi sổ retry.
- [x] Early-exit khi không có row → không dựng `HTTPClient`/`RobotsGate` thừa.
- [x] Artifact của **trang lỗi** không được dùng làm nội dung bài (phát sinh từ test, xem dưới).

## Design Notes

**Lỗi thứ hai do test phát hiện.** Test `test_transient_failure_gives_up_after_max_attempts` ban đầu
đỏ vì lý do bất ngờ: `RawStore.save()` vẫn ghi body khi HTTP lỗi (`raw_store.py`, chú thích *"partial
body vẫn lưu để inspect"*), nên một trang 500 cũng sinh file `.html`. Lượt backfill kế tiếp thấy file
đó qua `_find_bronze()`, bóc chữ trong **trang lỗi** ra làm `content_text` của bài rồi đánh dấu
`backfilled_from_bronze` — nội dung bài bị thay bằng nội dung trang lỗi. Đây là hành vi có sẵn từ
trước, nhưng trước US-011 backfill chỉ chạy tay hiếm khi nên ít lộ; chạy 5 phút/lần thì nó thành một
đường làm hỏng dữ liệu. Vá bằng cách cho `_find_bronze()` soi sidecar `.meta.json` và chỉ chấp nhận
artifact có `capture_status` là `ok`/`partial`; thiếu sidecar thì vẫn chấp nhận (artifact cũ/đặt tay).

**Về `SourceBackoff` — ghi chú trung thực:** lớp này chỉ phản ứng với 429/503, trần 16s, state thuần
in-memory nên **chỉ bảo vệ trong phạm vi một lần chạy**. Cơ chế chặn thật xuyên các lần chạy là
attempt cap; backoff chỉ là lớp lịch sự với nguồn. Nhịp cơ bản 3s/domain vốn đã có sẵn từ `HTTPClient`.

## Validation

| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q` | passed | 403 passed (từ 395, +8 test) |
| Integration | (cùng lệnh — backfill chạy thật qua fake HTTP + Bronze thật trên đĩa) | passed | xem Evidence |
| E2E | — | — | không gọi mạng thật trong phiên |
| Platform | — | — | chờ restart morninger (xem US-011 §Ops) |

## Evidence

```
403 passed, 550 warnings in 120.96s (0:02:00)
```

Test then chốt chứng minh vòng lặp vô hạn đã bị chặn:
- `test_retry_404_marks_source_deleted_and_stops_requerying` — `fake.calls == 1` sau **hai** lượt
  chạy: lượt hai không chạm mạng nữa vì row đã bị loại khỏi hàng đợi.
- `test_transient_failure_gives_up_after_max_attempts` — `fake.calls == 3` với `max_attempts=3`, dù
  gọi `main()` 6 lần.
- `test_find_bronze_rejects_error_page_artifact` — artifact `deleted_at_source`/`failed` bị từ chối.

## Harness Delta

Không phát sinh backlog mới. Ma sát đã ghi trong trace #46 (lỗi artifact trang lỗi).

## Trace (inline)

- **Trace:** #46, `score_trace = 1.0`, `score_context = 1.0`.
- **Outcome:** completed.
