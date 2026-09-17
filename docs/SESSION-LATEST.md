# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-17 (hoàn tất thực thi Phase 01..04 của Pipeline Integrity Remediation)
- **Current story:** US-016, US-017, US-018, US-019 `implemented`. Matrix: 17 implemented, 1 blocked (US-001).
- **Test:** **435 passed** (100% green; +7 unit tests mới trong `test_state_requeue_paths.py` và `test_functional_and_hygiene.py`).
- **Pipeline:** ✅ ĐANG CHẠY — background morninger hoạt động ổn định.
  Nhịp: `capture/10min (+backfill_deferred nối tiếp), derive/30min, l1_route/15min, reclaim/30min, drift/6:0`.

## Trạng thái vận hành đã kiểm chứng & Khắc phục hoàn tất (US-016 .. US-019)

1. **Phase 01 (US-016 - Watermark Silver Integrity)**:
   - Thay công thức watermark sang `low-water mark`, chặn mất bài vĩnh viễn qua bảng `silver_failures` (ngưỡng 5 lần $\rightarrow$ dead-letter).
2. **Phase 02 (US-017 - Destructive Automation Guard)**:
   - Bỏ `-Mode full`, loại bỏ hoàn toàn hành vi xoá trắng packet L1 khi chưa xử lý (`clean_completed_packets.py` chỉ xoá packet có bằng chứng done trong DB).
   - Tên batch unique `batch_<timestamp>_<NN>` chống va chạm. Bỏ `--dangerously-skip-permissions`, bảo vệ quyền tiêu thụ token Gold (ADR 0008).
3. **Phase 03 (US-018 - State Requeue Paths)**:
   - `held` tự động chuyển sang `pending` khi re-derive hợp lệ.
   - `claimed` được tự động thu hồi bằng job scheduler `reclaim_stale` trong morninger (30 phút/lần).
   - Thêm `scripts/maintenance/requeue.py` cho `failed` và `held` (an toàn với mặc định `--dry-run`).
   - Radar hiển thị trực tiếp số lượng hàng đợi kẹt: `work_items: claimed, held, failed | l1_tasks: failed`.
4. **Phase 04 (US-019 - Functional & Hygiene)**:
   - `l1_ingest.py`: thêm `import json`, gỡ bỏ except trần khi dọn batch file hoàn tất.
   - `l1_runner.py`: truyền tường minh `self.reg` cho cả hai luồng kiểm định DoD L1.
   - `orchestrator.py`: chiếm scheduler lock khi chạy `--once` (chống cào đè song song với morninger).
   - `l1_route.py` & `morninger.py`: chuyển sang mô hình kéo theo nhu cầu (demand-driven, Q5) — job nền chỉ định tuyến DB và nạp code-first (0 token), không sinh packet thừa.
   - `user_output.py`: đẩy bộ lọc ngày xuống SQL (`substr(COALESCE(published_at, fetched_at))`) thay vì nạp toàn bộ vào RAM.
   - `store.py`: de-duplicate `article_versions` theo `(url_title_hash, content_sha256)`.
   - `harness.db`: áp dụng migration `003-intake-types.sql`, mở rộng CHECK constraint đủ 9 loại intake (đóng Backlog #8).

## Khảo sát Dung lượng Lưu trữ Retention (Q8)

- `work_packages`: 7.355 files (573.47 MB)
- `silver`: 7.355 files (572.35 MB)
- `agent_tasks/l1/archive`: 2.461 files (3.86 MB)
- `agent_tasks/l1/active`: 2.639 files (4.14 MB)
- `raw_html (Bronze - WORM)`: 14.917 files (1.534 MB - BẤT BIẾN, TUYỆT ĐỐI KHÔNG XÓA)
👉 **Nhận định**: Work packages và Silver chiếm tổng cộng ~1.14 GB với hơn 14.700 files nhỏ trên OneDrive gây chậm File System Watcher. Khuyến nghị áp dụng retention 90 ngày (hoặc nén gzip/tar theo tháng) cho các thư mục này.

## Next Steps (3 thao tác phá huỷ chờ duyệt)

1. **Xoá thư mục `project/.venv` nội bộ hỏng** (Backlog #7).
2. **Archive file output cũ ngày 14/09**: `data/agent_outputs/batch_03..11.output.json`.
3. **Dọn dẹp các task packet L1 thừa trong `data/agent_tasks/l1/`**: đưa vào `archive/` để giải phóng hàng đợi.
4. **Git Commit**: Commit toàn bộ khối công việc đã hoàn tất để tránh rủi ro mất việc trên working tree.
