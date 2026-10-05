# US-036 — Bronze ghi nhầm gốc và khoá sổ lỗi Silver không chuẩn

- **Status:** in_progress (chờ khởi động lại morninger để mã mới có hiệu lực)
- **Lane:** normal
- **Parent / Epic:** Thu thập trọn vẹn (ADR 0013, US-033)
- **Intake date:** 2026-10-05
- **Depends On:** none

## Product Contract
Bài đã cào không bị coi là mất. Bronze luôn nằm dưới `project/data/raw_html` dù tiến trình chạy ở thư mục nào. Lần cào lỗi không ghi đè bản cào tốt. Dòng lỗi Silver cũ không ghim watermark.

## Acceptance Criteria
- [x] 2.750 tệp Bronze ở `<gốc repo>/data/raw_html` được chuyển vào `project/data/raw_html`; 1.607 tệp trùng tên khác nội dung được giữ ở `C:\data\news-scape\recovered\root_raw_html_conflicts_20261005`
- [x] 1.362 dòng `raw_missing` trong `silver_failures` đều có đủ tệp meta và HTML trên đĩa
- [x] `RawStore` neo đường dẫn tương đối vào `PROJECT_ROOT`; meta ghi `html_path` tương đối
- [x] Lần cào lỗi không ghi đè meta và HTML của bản cào tốt
- [x] Khoá `silver_failures` chuẩn hoá về dạng tương đối dùng gạch chéo xuôi; dòng cũ được gộp mỗi chu kỳ derive
- [ ] morninger khởi động lại bằng mã mới; derive xử lý 1.361 tệp; `silver_failures` về 0 dòng chặn; watermark nhảy qua 25/09
- [ ] Chạy lại toàn bộ pytest sau thay đổi `store.py` và `derive.py`

## Design Notes
Nguyên nhân: một tiến trình chạy với thư mục làm việc là gốc repo, ngày 28/09 đến 02/10, ghi Bronze và cả `silver`, `agent_tasks`, `work_packages` ra `<gốc repo>/data`. `derive` đọc theo `PROJECT_ROOT` nên báo `raw_missing`. Dòng lỗi cũ dùng khoá tương đối nên bản derive mới không xoá được và watermark ghim ở 25/09 14:53. Bài fireant 41948083 từng cào thành công, lần cào lại thất bại đã ghi đè meta bằng bản `failed` không có hash.

## Validation
| Tier | Command | Status | Evidence |
|------|---------|:------:|----------|
| Unit | `python -m pytest tests/test_raw_store.py tests/test_silver_failure_keys.py tests/test_silver_watermark_integrity.py tests/test_capture_backfill.py` | passed | 22 test đạt |
| Regression | `python -m pytest tests --ignore=tests/test_cli_entrypoints.py` | not run | lệnh bị chặn trong phiên |

## Harness Delta
OPEN-ITEMS CAP-1 mục 1 được viết lại; sao lưu DB `C:\data\news-scape\monocle.db.bak-20261005-pre-bronze-merge`.

## Trace (inline, H1)
- **Actions:** đối chiếu `silver_failures` với đĩa, gộp raw, sửa RawStore, chuẩn hoá khoá
- **Files changed:** src/crawler/raw_store.py, src/db/store.py, src/pipeline/derive.py, tests/test_raw_store.py, tests/test_silver_failure_keys.py
- **Outcome:** partial
- **Friction:** dừng morninger và chạy toàn bộ pytest đều bị từ chối trong phiên; `silver`, `agent_tasks`, `work_packages` ở gốc repo chưa xử lý.
