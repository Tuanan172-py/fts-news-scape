# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-11-26 12:15  
**Nhiệm vụ:** Điều tra nguyên nhân gốc và xử lý toàn diện các sự cố `OneDrive.exe` (CPU chạm đỉnh 97,4%, xoay log 1 MB/phút, 1.174 lỗi `HTTP 400 OpenUploadSession / ItemCannotFitInQuota`, 1.048 lần xóa tệp cục bộ/18h, và 301.684 tệp vượt trần 300k của OneDrive); hoàn tất bản vá codebase `US-060` + `FACT-onedrive-sync-quota-limits-per-minute-probe-churn`.

---

## 1. Kết quả Xử lý & Bằng chứng Trước/Sau

| Chỉ số | Trước xử lý (`11:11–11:23`) | Sau xử lý (`12:13`) |
|---|---|---|
| **CPU `OneDrive.exe`** | Đỉnh **97,4%** 1 nhân (`+402,6s`/12 phút; 98% ở `FileScanner`) | **0,0%** (`delta5s = 0s`, tổng `+0,1s`/2 phút) |
| **Số mục đồng bộ (`SyncEngineDatabase.db`)** | **301.684 tệp / 21.902 thư mục / 8 scopes** (vượt trần 300k) | **200.880 tệp / 19.374 thư mục / 7 scopes** (**-100.804 tệp**) |
| **Shortcut cũ `FRA_DataIngestion - news-scape`** | 100.794 tệp (6,60 GB hydrated cục bộ) | **Đã gỡ sạch** qua verb chính thức `UnmountAddedFolder` (`HTTP 204`, bảo toàn 100% trên SharePoint) |
| **Tệp `monocle_review_*.db` kẹt ở `news-data/review`** | **7 tệp (18,0 GB)** — **1.174× `HTTP 400 ItemCannotFitInQuota`** | **0 tệp kẹt**, **0 lỗi `HTTP 400` mới** (`monocle_review_20261125.db` `quick_check=ok` đã đưa về `C:\data\news-scape\snapshots\monocle_review.db`; 6 bản cũ lưu ở `C:\data\news-scape\archive\onedrive-stuck-reviews-20261126\`) |
| **Tệp rác cục bộ chưa sync trong `Desktop\backup`** | **109 tệp** (`~$*`, `~WRL*.tmp`, `Thumbs.db`) gây 108×/MB bão `SetExcludedPinStateOnFileByPath` | **Đã dọn 109/109 (0 lỗi)**; `0` hit trong `.odl` mới |
| **Bão xoay log `logs\Business1`** | **1.909 tệp / 273 MB** (đỉnh 489 MB; 24,4 MB/giờ) | **77 tệp / 4,5 MB** (0,5 MB/5 phút; đã giải phóng ~474,8 MB) |
| **Dung lượng trống ổ `C:`** | `41,04 GB` | **`47,53 GB`** (**+6,49 GB**; có thể trống thêm ~17,9 GB nếu xóa thư mục archive khi không cần) |
| **Tạo/xóa `.probe` mỗi 60 giây của `ops_daemon`** | 1.440 lần/ngày (`numLcDeleteFile = 1.048` / 1.090 phút) | Điều tiết còn tối đa **4 lần/ngày** (`write_probe_interval_minutes: 360`) |

---

## 2. Thay đổi trong Repo (`US-060`)
- [project/config/ops.yaml](file:///c:/src/news-scraper/project/config/ops.yaml): đặt `publish.include_review: false` (ngừng đồng bộ `monocle_review_*.db` 2,75 GB lên SharePoint theo ADR-0023) và `publish.write_probe_interval_minutes: 360`.
- [project/src/ops/daemon.py](file:///c:/src/news-scraper/project/src/ops/daemon.py): `publish_tick()` truyền `include_review`; `run_probes()` điều tiết `write_test` qua `_due()` (đã sửa khởi tạo lần đầu khi `last is None`).
- [project/src/ops/probes.py](file:///c:/src/news-scraper/project/src/ops/probes.py): kiểm tra `target.is_dir()` khi `write_test=False` và mở rộng phát hiện tệp xung đột OneDrive theo `-{hostname}` ngoài `-DESKTOP-`.
- [project/tests/test_publisher.py](file:///c:/src/news-scraper/project/tests/test_publisher.py) & [project/tests/test_ops_runtime.py](file:///c:/src/news-scraper/project/tests/test_ops_runtime.py): bổ sung 4 kiểm thử mới; chạy 6 test suite liên quan đạt **128/128 passed**, `ast_docstring_linter` **100%**, `scan_code_phrases` **0 lỗi**, `doc lint` **0 lỗi**.
- Đã khởi động lại `ops_daemon` (`news-scape-ops`), xác nhận `Daemon: sống`, cả `publish` và `research` probes đều `KHỎE`, các đợt tự động `W11261204` và `W11261206` chạy và giao hàng thành công.

---

## 3. Việc Thủ công Còn lại Trên Cloud / UI OneDrive (Tùy chọn tối ưu thêm)
1. **Giảm tiếp số tệp OneDrive từ `200.880` xuống `~29.000` (khuyến nghị mạnh):** Mở OneDrive Settings → **Account** → **Choose folders** → bỏ chọn **`Desktop > backup`** (171.550 tệp, 46,47 GB, 31.611 đường dẫn ≥ 240 ký tự — 100% đã lưu an toàn trên Cloud).
2. **Giải phóng quota SharePoint `sites/FRA_DataIngestion`:** Vào web SharePoint `https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion/_layouts/15/AdminRecycleBin.aspx` dọn Recycle Bin (chứa các bản `monocle_review_*.db` cũ bị prune trước đây).
3. **Thu hồi thêm ~17,9 GB ổ C (tùy chọn):** Sau khi xác nhận không cần đối chiếu các snapshot cũ, có thể xóa `C:\data\news-scape\archive\onedrive-stuck-reviews-20261126\` (bản mới nhất 25/11 đã nằm tại `C:\data\news-scape\snapshots\monocle_review.db`).
