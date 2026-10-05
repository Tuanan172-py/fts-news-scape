# US-011 — Bronze Capture Cadence & Deferred/Deleted-Article Loss Prevention

- **Status:** implemented
- **Lane:** normal
- **Parent / Epic:** Bronze Ingestion Pipeline
- **Intake date:** 2026-09-17
- **Depends On:** none

## Product Contract

Chu kỳ Bronze phải phát hiện và lưu nguyên bản tin mới đủ nhanh, có lưới an toàn tự động, để
đặc điểm tin VN — một số bài bị nguồn gỡ rất sớm sau khi đăng — không gây mất vĩnh viễn nội dung
đầy đủ. Silver→L1 (nhánh code-first, 0 token) phải được định tuyến tự động, không phụ thuộc con
người chạy tay hay quota Gold (Gold vẫn là bottleneck quota riêng, ngoài phạm vi story này).

## Acceptance Criteria

- [x] `capture_interval_minutes` giảm 15→5 phút (`project/config/settings.yaml`).
- [x] `backfill_deferred.py` tự động chạy nối tiếp ngay sau mỗi capture cycle
      (`Morninger.run_capture` → `run_backfill_deferred`), không cần vận hành viên chạy tay.
- [x] HTTP 404/410 khi fetch trang chi tiết được gắn `capture_status=deleted_at_source` +
      `article.metadata.source_deleted=True`, khác với lỗi tạm thời (`failed`).
- [x] `backfill_deferred.py` loại các bài `source_deleted=True` khỏi `_DEFERRED_WHERE` — không
      retry vô ích một URL đã xác nhận biến mất.
- [x] `pipeline_radar.py status` hiển thị số bài bị nguồn xóa trước khi lấy được nội dung.
- [x] Job `l1_route` (code-first, `--from-db --date today --mini-batch 25`, 0 token LLM) chạy
      tự động theo lịch riêng (`l1_route_interval_minutes`, mặc định 15p) trong
      `morninger.build_scheduler`, tách biệt hoàn toàn AutoPilot/Gold quota.
- [x] `build_scheduler()` tương thích ngược: tham số `l1_route_fn` mặc định `None` → không đăng
      ký job nếu không truyền (không phá lời gọi cũ 4 tham số).
- [x] Toàn bộ unit test PASS (không có regression).

## Design Notes

Phạm vi nhỏ nhất thực sự cần — không đổi kiến trúc Bronze/Silver/Gold, chỉ vá 3 lỗ hổng cụ thể
tìm thấy khi audit (`project/src/orchestrator.py` + `project/src/morninger.py` +
`project/src/scrapers/rss_generic.py` + `project/src/scrapers/capture_mixin.py`):

1. **`max_details_per_cycle`** (mặc định 30–40, per-domain) khiến bài vượt cap bị
   `detail_deferred=True` và CHỈ được bù lại qua `scripts/maintenance/backfill_deferred.py` chạy
   TAY (runbook thủ công) — cửa sổ rủi ro giữa lúc bị hoãn và lúc con người chạy backfill là nơi
   nguồn tin VN có thể đã xóa bài. → Nối job bù (`run_backfill_deferred`) NGAY sau mỗi capture
   cycle thay vì chờ người vận hành.
2. **Không phân biệt 404/410 với lỗi tạm thời** ở `raw_store.py`/`capture_mixin.py` — không đo
   được tần suất "đăng rồi xóa", và backfill có thể lãng phí request retry một URL đã biến mất
   vĩnh viễn. → Thêm nhánh `deleted_at_source`.
3. **`l1_route.py`** (định tuyến L1 code-first, 0 token cho nhánh `resolved`) không có lịch tự
   động — chỉ chạy khi con người thấy cảnh báo `pipeline_radar` rồi gõ lệnh. → Thêm job
   scheduler riêng, độc lập hoàn toàn với AutoPilot/Gold (đã bị bottleneck quota theo thiết kế).

**Không làm gì thêm ngoài phạm vi**: KHÔNG di chuyển các domain `method: rss` (không có Bronze
raw-capture) sang `rss_capture` — xác minh mọi domain đang `enabled: true` hiện tại đã dùng
scraper có `CaptureMixin` rồi (cafef, vietstock, vietnambiz, tnck, fireant, baodautu, vneconomy,
thoibaotaichinhvietnam); nhóm domain còn lại đều `enabled: false` từ 2026-08-03. Migrate sang
capture-enabled là việc riêng, cần xác minh selector CSS từng site, chỉ cần làm TRƯỚC KHI ai đó
bật lại domain trong nhóm đó.

## Validation

| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `cd project; C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q` | passed | 395 passed, 0 failed (chỉ có `feedparser` DeprecationWarning, không liên quan) |
| Integration | (nằm trong cùng lệnh trên — `test_cafef_capture.py`, `test_backfill_deferred.py` chạy qua scraper/backfill thật với fixture HTTP) | passed | Xem file test bên dưới |
| E2E | — | — | Không chạy `run_once.py` sống (không muốn gọi mạng thật trong phiên audit) |
| Platform | — | — | Chưa restart `morninger` process thật để quan sát job `l1_route` bắn theo lịch |

> "No proof = not implemented." Cả 2 tier trên đã chạy thật và ghi nhận evidence.

## Harness Delta

- Backlog #6: ngân sách context Normal-lane (≤15 file) quá chật cho tác vụ audit/redesign toàn
  pipeline — trace này chỉ đạt `score_context=0.6` dù trace đầy đủ và trung thực.
- Backlog #7: `project/.venv` nội bộ hỏng (trỏ Python 3.14 hồ sơ Windows cũ) — trái với
  AGENTS.md §3 (cấm tạo `.venv` nội bộ, chỉ dùng `C:\venvs\news-scape`).

## Evidence

```
cd project
C:/venvs/news-scape/Scripts/python.exe -m pytest tests/ -q
...
395 passed, 550 warnings in 135.10s (0:02:15)
```

Targeted trước đó (subset, trong lúc phát triển):
```
C:/venvs/news-scape/Scripts/python.exe -m pytest tests/test_raw_store.py tests/test_morninger.py \
  tests/test_cafef_capture.py tests/test_backfill_deferred.py tests/test_cafef.py -q
45 passed in 18.40s
```

## Trace (inline, H1)

- **Actions:** Khảo sát kiến trúc Bronze/Silver/L1/Gold qua 2 Explore subagent song song → xác
  định 3 lỗ hổng cụ thể → xác nhận `morninger.py` là scheduler production thật (không phải
  `orchestrator.start_scheduler`, bị khóa bởi Fix F lock) → xác nhận 8 domain đang bật đều đã có
  Bronze raw-capture → hỏi người dùng 2 quyết định (khoảng capture, nhịp drain deferred) → sửa
  6 file sản phẩm + 4 file test → chạy pytest toàn bộ 395/395 → ghi nhận vào harness (`intake`,
  `story`, `trace`, `backlog`).
- **Files read:** xem `harness.db` trace #45 (`files_read`) — 23 file (Bronze/Silver/L1 core +
  config domain + docs harness).
- **Files changed:** `project/config/settings.yaml`, `project/src/crawler/raw_store.py`,
  `project/src/scrapers/capture_mixin.py`, `project/scripts/maintenance/backfill_deferred.py`,
  `project/src/morninger.py`, `project/scripts/pipeline_radar.py`, `project/tests/test_raw_store.py`,
  `project/tests/test_cafef_capture.py`, `project/tests/test_backfill_deferred.py`,
  `project/tests/test_morninger.py`, `docs/stories/US-011-...md`, `docs/TEST_MATRIX.md`,
  `docs/SESSION-LATEST.md`.
- **Outcome:** completed
- **Friction:** Ngân sách context Normal-lane quá chật cho audit toàn pipeline (backlog #6);
  `project/.venv` nội bộ hỏng, phải dùng `C:\venvs\news-scape` (backlog #7).
