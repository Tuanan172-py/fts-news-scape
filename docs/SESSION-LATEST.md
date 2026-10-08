# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

> **Phiên Kiến trúc & Hợp nhất 2026-10-08 (US-042 HOÀN TẤT, dev/us038 clean):**
> - **Codebase Thống nhất**: Toàn bộ codebase tập trung duy nhất tại `C:\src\news-scraper` (nhánh `dev/us038`). Đã dọn sạch 100% worktree thừa (`news-scape-us039`, `us040`, `us041`, `dev`). Đã merge trọn vẹn US-039, US-040, US-041.
> - **Cách ly SharePoint & CSDL**: Tệp review DB 758 MB đã chuyển ra `C:\data\news-scape\publish_hold`. Bộ bảo vệ `OFFICIAL_TARGET_MARKERS = frozenset({"fra - data"})` chặn cứng mọi thao tác ghi lên site chính thức.
> - **Khôi phục cào tin**: Đã cào bù 398 bài qua `capture_reconcile.py`. Task Scheduler `\news-scape-ops` đang chạy ngầm liên tục, `pipeline_radar.py` xanh (🟢 Tươi mới, Daemon sống, Mandate: L0, AGY_STOP bật - 0 token tiêu tốn).
> - **Kiến trúc CQRS Lakehouse trên SharePoint (US-042 - DONE)**:
>   - Giao thức Dropzone phân mảnh phi khóa đa Dev: `dropzone/YYYY/MM/DD/part-*.parquet`.
>   - Động cơ DuckDB tự động hợp nhất và khử trùng lặp theo `article_id` & `updated_at`: xuất `parquet/articles/...` (115ms / 1.300 bản ghi).
>   - Động cơ phân phối đa người dùng (`delivery.py`): xuất Excel 2 sheets đơn sắc bảo mật cao cho 5 chuyên viên Khối FRA.
>   - Toàn vẹn dữ liệu: Tệp kê khai `_manifest/YYYY-MM-DD.json` và con trỏ `latest.json` kiểm soát SHA-256 byte-level.
>   - Bộ kiểm thử: **33/33 tests Lakehouse PASSED**, **905/905 baseline tests PASSED** (Tổng cộng: **938/938 tests GREEN 100%**).
>   - Đã commit `a76d3db` và push lên remote tổ chức `fpa/dev/us038`.

- **Updated:** 2026-10-08 (Branch: `dev/us038` @ `a76d3db`; Git tree clean: `clean_for_closure: true`)
- **Điểm vào vận hành:** `pipeline_radar.py status` · `lakehouse_cli.py --help` · `scripts/harness_cli.py git status`
- **Sandbox đích:** `C:\Users\anpt\OneDrive - fpts.com.vn\Shortcuts\FRA_DataIngestion - news-data`

## Next Steps

1. **Vận hành Sandbox Lakehouse Thực nghiệm**:
   - Dùng lệnh `project/scripts/lakehouse_cli.py ingest` để nạp dữ liệu phân tích từ các ca chạy thật vào Sandbox `news-data`.
   - Dùng `lakehouse_cli.py consolidate --date 2026-10-08` và `lakehouse_cli.py deliver --date 2026-10-08` để tạo Parquet và phân phối báo cáo Excel cho chuyên viên.
2. **Kích hoạt Phân tích AI khi sẵn sàng**:
   - Hiện tại hệ thống đang giữ `AGY_STOP` và mức `L0` (chỉ cào tin và bóc tách cấu trúc Bronze/Silver, 0 token). Khi cần kích hoạt phân tích LLM, tắt `AGY_STOP` qua radar/cli.
