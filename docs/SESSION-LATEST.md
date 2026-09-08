# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-08
- **Current story:** Rà soát toàn bộ workflow scripts + Tối ưu hóa SQLite I/O & UTF-8 stdio
- **Status:** **implemented & verified** (357/357 pytest passed, 100% scripts verified on `data/monocle.db`)
- **Blocker:** none.

## Đã rà soát & Tối ưu hoá toàn bộ Workflow

### 1. Hạ tầng DB & Concurrency
- **Khôi phục & Đồng bộ DB**: Giải quyết triệt để conflict WAL OneDrive, khôi phục `data/monocle.db` (7.094 articles, 7.613 seen, 1.274 agent outputs, 685 L1 outputs) đạt 100% `PRAGMA integrity_check = ok`.
- **Tối ưu Composite Index**: Bổ sung `idx_agent_outputs_article_dod` và `idx_l1_outputs_article_dod` vào `_SCHEMA`. Tốc độ kiểm kê `l1_backlog.py` giảm từ >20s xuống **0.07s** (~300x).
- **Read-Only Connections**: Tách biệt `init_schema: bool = True/False` trong `ArticleStore.__init__` và cập nhật `src/monitor/health.py` dùng `_connect_ro()`.

### 2. Chuẩn hoá Windows UTF-8 Stdio
- Đã bổ sung `force_utf8_stdio()` và `argparse` vào tất cả workflow/entrypoint scripts (`refresh_watchlist.py`, `run_once.py`, `rederive_from_bronze.py`, `build_entities.py`, v.v.) triệt tiêu hoàn toàn lỗi `UnicodeEncodeError: 'charmap'` trên Windows console.

### 3. Kiểm thử toàn bộ Scripts Pipeline (100% PASS)
- **Kiểm định & Regression Suite**: `pytest tests/ -v` đạt **357/357 PASSED** (100%).
- **Harness Audit**: `health_score = 0.85`, `entropy_score = 0.15`, 0 in-progress, 0 unproven stories.
- **Monitoring & Health**: `db_status.py`, `src.monitor.health`, `report_drift.py` hoạt động chính xác.
- **Backlog & Hierarchy**: `l1_backlog.py`, `l1_route.py`, `l1_ingest.py`, `agent_export.py`, `agent_ingest.py`, `run_agent_hierarchy.py` chạy chuẩn xác theo phân cấp L1 $\rightarrow$ Gold.
- **User Delivery**: `compile_users.py`, `write_user_output.py`, `run_user_workflow.py` định tuyến đúng theo manifest.
- **Diagnostics & Snapshot**: `db_snapshot.py` (tạo `monocle_review.db`), `dbq.py`, `export_csv.py`, `export_silver.py`, `sample_articles.py`, `domain_check.py` đều chạy thông suốt.

## Số liệu Hệ thống Thực tế (Live monocle.db)

| Nhóm dữ liệu | Số lượng hiện tại | Trạng thái |
|---|---|---|
| Articles trong DB | **7.094** | 100% Integrity OK |
| Đã qua gate export (final.csv) | **424** | 384 GOLD · 40 L1_ONLY |
| T1 gold-ready (Gold xong, thiếu L1) | **423** | 17 mini-batches sẵn sàng tại `data/agent_tasks/l1/` |
| T2 chưa L1 chưa Gold | **6.247** | Sẵn sàng phân tuyến |
| T3 đã có L1, work_item pending | **40** | Sẵn sàng cho Gold Agent |
| Snapshot review độc lập | `data/monocle_review.db` | Cập nhật lúc 14:29 |

## Next Steps

1. **Rút hàng đợi T1 (423 bài)**: Subagent L1 xử lý 17 batch `data/agent_tasks/l1/l1_batch_*.task.json` $\rightarrow$ Ingest & Deliver (`python scripts/run_agent_hierarchy.py --ingest-and-deliver`). Chi tiết: `project/docs/operations/backlog-drain-runbook.md`.
2. **Kích hoạt chu trình cào mới**: `python scripts/run_once.py` hoặc `python -m src.morninger` để lấy tin tức mới nhất.
3. **Rò rỉ T4 (Orphan backlog)**: Tiếp tục điều tra nguyên nhân work-packages Bronze/Silver không ghi vào bảng `articles`.
