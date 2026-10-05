# US-035 — Bronze ghi nhầm gốc và khoá sổ lỗi Silver không chuẩn

- **Status:** in_progress (chờ chu kỳ derive đầu tiên của morninger chạy mã mới)
- **Lane:** normal
- **Parent / Epic:** Thu thập trọn vẹn (ADR 0013, US-033)
- **Intake date:** 2026-10-05
- **Depends On:** none

## Product Contract
Bài đã cào không bị coi là mất. Bronze và mọi sản phẩm dữ liệu luôn nằm dưới `project/data` dù tiến trình chạy ở thư mục nào. Lần cào lỗi không ghi đè bản cào tốt. Dòng lỗi Silver cũ không ghim watermark.

## Acceptance Criteria
- [x] 2.750 tệp Bronze ở `<gốc repo>/data/raw_html` chuyển vào `project/data/raw_html`; 1.607 tệp trùng tên giữ ở `C:\data\news-scape\recovered\root_raw_html_conflicts_20261005`
- [x] Cả 1.362 dòng `raw_missing` trong `silver_failures` có đủ tệp meta và HTML trên đĩa
- [x] `RawStore` neo đường dẫn tương đối vào `PROJECT_ROOT`; meta ghi `html_path` tương đối
- [x] Lần cào lỗi không ghi đè meta và HTML của bản cào tốt
- [x] Khoá `silver_failures` chuẩn hoá về dạng tương đối dùng gạch chéo xuôi; dòng cũ được gộp mỗi chu kỳ derive (1.365 dòng gộp còn 850)
- [x] `<gốc repo>/data` dọn theo phương án E: 259 tệp (`silver`, `work_packages`, `agent_tasks`, `agent_outputs*`) sang `C:\data\news-scape\recovered\root_data_20261005`; 4 CSV `exports` gộp vào `project/data/exports`; thư mục `data` ở gốc repo đã gỡ
- [x] Các điểm ghi `exports`, `notifications`, `staging`, `work_packages` neo vào `PROJECT_ROOT`, có test
- [ ] morninger chạy derive: `silver_failures` về 0 dòng chặn, watermark nhảy qua 25/09
- [ ] Chạy lại toàn bộ pytest sau thay đổi `store.py`, `derive.py` và các điểm ghi

## Design Notes
Nguyên nhân: một tiến trình chạy với thư mục làm việc là gốc repo, ngày 28/09 đến 02/10, ghi Bronze và cả `silver`, `work_packages`, `exports` ra `<gốc repo>/data`. `derive` đọc theo `PROJECT_ROOT` nên báo `raw_missing`. Dòng lỗi cũ dùng khoá tương đối nên bản derive mới không xoá được và watermark ghim ở 25/09 14:53. Bài fireant 41948083 từng cào thành công, lần cào lại thất bại đã ghi đè meta bằng bản `failed` không có hash.

Chưa neo: `batch_handoff.py`, `l1_router.py`, `packet.py`, `runner.py`, `l1_runner.py`, thuộc lane L1/Gold đã ngừng (ADR 0010).

## Validation
| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `python -m pytest tests/test_raw_store.py tests/test_silver_failure_keys.py tests/test_paths_anchored.py tests/test_silver_watermark_integrity.py tests/test_capture_backfill.py tests/test_concurrency_io.py tests/test_monitor_notify.py tests/test_morninger.py` | passed | 64 test đạt |
| Regression | `python -m pytest tests --ignore=tests/test_cli_entrypoints.py` | not run | lệnh bị chặn trong phiên |
| Platform | `pipeline_radar.py status` sau chu kỳ derive | pending | lúc 15:12 còn 849 dòng, 108 chặn watermark |

## Harness Delta
OPEN-ITEMS CAP-1 mục 1 viết lại. Sao lưu DB `C:\data\news-scape\monocle.db.bak-20261005-pre-bronze-merge`.

## Trace (inline, H1)
- **Actions:** đối chiếu `silver_failures` với đĩa, gộp raw, sửa RawStore, chuẩn hoá khoá, neo điểm ghi, dọn gốc repo
- **Files changed:** src/crawler/raw_store.py, src/db/store.py, src/pipeline/derive.py, src/export/{csv_export,silver_manifest}.py, src/orchestrator.py, src/notifier/file_notify.py, src/core/staging.py, src/handoff/work_package.py, tests/test_raw_store.py, tests/test_silver_failure_keys.py, tests/test_paths_anchored.py
- **Outcome:** partial
- **Friction:** chạy toàn bộ pytest bị từ chối trong phiên. Người vận hành tự dừng morninger và chạy lại lúc 15:05.
