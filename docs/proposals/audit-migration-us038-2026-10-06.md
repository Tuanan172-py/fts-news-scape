# Audit migration US-038: tách mã (Git) và dữ liệu (SharePoint)

- **Ngày:** 2026-10-06
- **Story:** US-038 (high-risk). Quyết định nền: ADR 0020 (accepted).
- **Phạm vi:** toàn bộ luồng migration từ thư mục OneDrive `FRA_DataIngestion - news-scape` sang ba nơi:
  - cây mã `C:\src\news-scraper` (Git);
  - tầng ghi `C:\data\news-scape`;
  - tầng xuất bản `FRA - Data\news` (SharePoint).
- **Cách đo:** chạy lệnh trên máy vận hành. Agent chỉ đọc cây mã mới (`git grep`). Không mở DB ngoài chế độ đọc.

## 1. Kết luận

Phần lõi của migration đã chạy được: mã, dữ liệu và DB đã tách, và chạy được từ thư mục mới. Còn **5 vấn đề P0 chặn việc mở lại vận hành** và **10 vấn đề P1 cần xử lý trước khi kho tổ chức thành nguồn chính**. P0 nặng nhất:

1. **SharePoint chưa nhận được gì.** Tiến trình đồng bộ `OneDrive.exe` không chạy, nên 12 tệp đã xuất bản mới chỉ nằm trên máy.
2. **Kênh giao hàng của chuyên viên bị đứt.** Tệp đăng ký và xlsx giao hàng nay chỉ ở ổ cục bộ của máy vận hành.

## 2. Đã đạt (số đo)

| Hạng mục | Kết quả |
|---|---|
| Cây mã | `C:\src\news-scraper`, nhánh `dev/us038` (lịch sử sạch, gốc df021e6). Chung gitdir `C:/gitdirs/news-scape.git` |
| Bản sao lưu trên kho cá nhân | `origin/import/clean-20261005`, `origin/dev/us038`, sẵn ánh xạ 1:1 sang `fpa` (plan §N1) |
| Test | 888 passed, 1 failed (`test_inherit`, có từ trước, phụ thuộc ngày) |
| Dữ liệu | 76.075 tệp, 5,63 GB chép sang `C:\data\news-scape`. Robocopy 0 lỗi. Bản gốc ở OneDrive còn nguyên (5,8 GB) |
| DB | Sao lưu `archive\pre-cutover-20261006`. `migrate_data_root --apply` đổi 25.597 dòng. Lấy mẫu: work_packages 200/200, silver_failures 3/3, periodic_reports 3/3 trỏ đúng tệp |
| Vận hành từ thư mục mới | `article_run --where`, `pipeline_radar status`, `ops_daemon once` chạy được. Mọi probe KHOẺ |
| Task Scheduler, DSH | `news-scape-ops*` trỏ `C:\src\news-scraper\project` (đang Disabled). `~/.dsh/profiles/web/cordis.patch.yml` trỏ preset mới |
| SharePoint | `FRA - Data\news` ghi được, đã pin. Ngày 2026-10-05 xuất bản đủ 12 tệp và `_manifest/20261005.json` |
| Dừng khẩn | `AGY_STOP` bật, mandate L0, ba task Disabled, không còn tiến trình của dự án. Thông báo dừng đặt ở thư mục cũ và worktree US-039 |

## 3. Vấn đề tồn đọng

### P0 — chặn mở lại vận hành

| Mã | Vấn đề | Bằng chứng | Phương án |
|---|---|---|---|
| **P0-1** | Đồng bộ OneDrive không chạy | Không có tiến trình `OneDrive.exe`, chỉ có `OneDrive.Sync.Service.exe`. Tệp trong `news\` mang thuộc tính `0x80020`, chưa phải placeholder của mây | Người vận hành mở OneDrive và chờ biểu tượng xanh. Kiểm lại bằng web `sites/FRA/Data/news`. `probe_publish` đã bắt được trường hợp này khi bật publisher |
| **P0-2** | Kênh giao hàng của chuyên viên bị đứt | Trước migration, `users\output` và `users\subscriptions` nằm trong thư viện SharePoint `FRA_DataIngestion`. Nay chúng ở `C:\data\news-scape\users_output` và `subscriptions` | (a) **Đăng ký:** cài ADR 0020 §2.4. Chuyên viên sửa ở `FRA - Data\news\users\subscriptions`. Trước mỗi lần `compile_users`, script chép về `inputs/subscriptions` (thư mục pin offline, đọc qua `NEWS_SCAPE_SUBSCRIPTIONS_DIR`). (b) **Giao hàng:** gọi `publish_users_output(day)` ngay sau `write_user_output`, không chờ lượt 01:00. (c) Báo chuyên viên đường dẫn mới |
| **P0-3** | Quyền xem trên site `FRA/Data` chưa được xét | Bản DB review chứa toàn bộ bài và phân tích. xlsx giao hàng là của từng người | Quyết định với chủ site: thư mục `news\users\` chỉ cấp cho chuyên viên liên quan, hoặc tách sang thư viện riêng. `review/` và `parquet/` cho toàn Khối đọc |
| **P0-4** | Nén Bronze quá chậm | Lượt đầu ngày 05/10 vượt giới hạn 30 phút. cafef (138 MB, khoảng 1.300 tệp) mất 12 phút, vneconomy (50 MB) mất 10 phút. Chạy tiếp mất 28 giây | Đo lại tách bạch thời gian đọc, băm và nén. Lựa chọn: `tarfile` với `preset=1` hoặc `w:gz` (nhanh hơn 5–10 lần, tệp lớn hơn khoảng 30%), song song theo nguồn, và loại thư mục `raw_html` khỏi quét thời gian thực của Defender. Mục tiêu: dưới 3 phút một ngày |
| **P0-5** | Chưa có quy trình mở lại vận hành có cổng | Daemon, morninger, watchdog đang tắt | Runbook mở lại 6 bước (mục 5), chạy sau khi P0-1 và P0-2 xong |

### P1 — trước khi kho tổ chức thành nguồn chính

| Mã | Vấn đề | Bằng chứng | Phương án |
|---|---|---|---|
| P1-1 | `harness.db` có nhiều bản, vị trí phụ thuộc cwd | `harness_cli.py:21` dùng `"harness.db"` tương đối theo cwd; `ops/config.py:134` dùng gốc kho; có bản ở OneDrive và bản ở `C:\src\news-scraper` (chép lúc 14:1x, đã lệch) | Chốt một vị trí qua `paths.harness_db()`, mặc định `<data_root>/harness/harness.db`, có env `NEWS_SCAPE_HARNESS_DB`. Gộp bản OneDrive vào (story, trace sau 14:10) bằng script hợp nhất theo khoá chính |
| P1-2 | Tài liệu và registry trỏ vị trí cũ | `registry.yaml` 26 chỗ `data/...`, `pipeline.yaml` 5 chỗ, 66 tài liệu vận hành. `DSH-WAVE-W365-HANDOFF.md`, `07-two-machine-workflow.md` còn `cd` vào OneDrive | Một PR tài liệu: registry và pipeline dùng ký hiệu `<data_root>/...`. Runbook vận hành sửa theo `article_run --where`. Tài liệu lịch sử thêm ghi chú "trước US-038". Thêm luật `doc_lint` chặn `project/data/` trong tài liệu vận hành |
| P1-3 | Đường dẫn venv viết cứng | 21 chỗ trong 8 tệp, `pipeline.yaml` có 11 | `pipeline.yaml` dùng `{python}`. `pipeline_radar.py` in `sys.executable`. `ops_install.ps1` nhận `-Venv` như hiện có |
| P1-4 | `settings.yaml` còn `database.path` cứng | `settings.yaml:6` | Xoá khoá, để `paths.db_path()` quyết định |
| P1-5 | `.gitignore` còn luật cũ | Luật `**/data/...`, `**/*-DESKTOP-*`, mục rác `**/C`, `project/data/raw_html/.gitignore` vẫn được theo dõi, luật `project/src/data/` có thể che package mới | Viết lại gọn: luật cho DB, log, venv, cache, tài liệu nhị phân. Giữ một luật chặn `project/data/` để bắt lỗi ghi sai gốc |
| P1-6 | Mã lane L1/Gold đã ngừng vẫn còn và vẫn được tham chiếu | `l1_route` được `article_expand`, `pipeline_radar`, `entities.py`, `l1_runner.py` và 7 test tham chiếu. 4 script không còn ai gọi | PR dọn: chuyển `TYPE_GROUP` và `title_of` sang module trung lập, rồi xoá script, test và skill của lane cũ. Xoá `clean_onedrive_conflicts.py` |
| P1-7 | Nhiều worktree trên một gitdir | Có thư mục OneDrive (`feature/article-lane-remove-gates`), `news-scraper` (`dev/us038`), `news-scraper-dev` (detached, thừa), `news-scape-us039`, `.kilo/granite-asphalt` (thừa) | Sau khi push `fpa`: gỡ hai worktree thừa. Nhánh US-039 đã chung tuyến sạch, mở PR riêng vào `fpa/main` |
| P1-8 | Kho tổ chức chỉ có một ngày dữ liệu | `_manifest` mới có 20261005. Bronze có từ tháng 8 | Bù lùi bằng `publish.py --date` cho từng ngày đã đóng, làm sau P0-4. Bản review chỉ xuất cho ngày gần nhất, Parquet và Bronze xuất đủ |
| P1-9 | Bản review quá nặng để xuất hằng ngày | 758 MB mỗi ngày, giữ 7 bản là 5,3 GB, tải lên 758 MB mỗi đêm | Xuất review mỗi tuần, giữ 4 bản. Chuyên viên tra hằng ngày bằng Parquet. Cần hạn mức site (ADR 0020 §6) |
| P1-10 | `test_inherit` hỏng theo ngày | `stats["copy"] == 0`, dùng ngày bài cố định với `days=3` | **Đã sửa ở nhánh `fix/us041-unblock-tests-ledger` (2026-10-08):** `cluster_job.refresh` nhận `today`, test truyền ngày cố định |

### P2 — cải tiến sau

| Mã | Vấn đề | Phương án |
|---|---|---|
| P2-1 | Chưa đóng gói chuẩn: không có `pyproject.toml`, 120 `sys.path.insert`, tên package `src` sẽ trùng trong fpa-toolkit | Đổi `src` thành `news_scape`, thêm `pyproject.toml`, entrypoint CLI. Điều kiện trước PR fpa-toolkit |
| P2-2 | Xuất bản gắn với tài khoản cá nhân qua shortcut | Mức L2 qua Graph API (`Sites.Selected`, chứng chỉ) theo plan N7 |
| P2-3 | Chưa có hợp đồng dữ liệu cho bên đọc | Viết `schemas/publish-manifest-v1.schema.json` và tài liệu cột Parquet. fpa-toolkit đọc theo `latest.json` |
| P2-4 | Ngoài bước cào, các bước ghi DB không có khoá liên tiến trình | Thêm khoá tệp cho `--finish`, `write_user_output`, migration, giống `capture.lock` |
| P2-5 | Thư mục cũ trên OneDrive vẫn giữ 5,8 GB dữ liệu và bản sao mã | N6: sau 14 ngày ổn định thì đổi tên thành ARCHIVED, ngừng đồng bộ. Archive `C:\data\news-scape\archive` đưa lên `news\backup\` |

## 4. Lộ trình đề xuất

| Đợt | Nội dung | Ai | Điều kiện xong |
|---|---|---|---|
| **Đ1 (hôm nay)** | P0-1 mở OneDrive. P0-3 quyết định quyền. Báo agent | Người | Thấy `news\` trên web SharePoint |
| **Đ2** | P0-2 (đăng ký từ SharePoint, giao hàng xuất ngay), P0-4 (nén nhanh), P1-1 (`harness.db` một chỗ), P1-4, P1-10 | Agent | pytest xanh. Xuất bản một ngày dưới 3 phút. Xuất bản 05/10 lại không đổi manifest |
| **Đ3** | P0-5 mở lại vận hành theo runbook mục 5. Bật `publish.enabled` | Người + agent | 24 giờ có đợt DONE, có xlsx trên SharePoint, có `latest.json` mới |
| **Đ4** | Push `fpa` theo ánh xạ 1:1, PR `dev/us038` → `main`. Đổi lane mã sang kho tổ chức | Người | `fpa/main` chứa US-038. Mọi nhánh mới tách từ `fpa/main` |
| **Đ5** | P1-2, P1-3, P1-5, P1-6, P1-7, P1-8, P1-9 thành các PR nhỏ trên kho tổ chức | Agent | Mỗi PR có test xanh và doc_lint xanh |
| **Đ6** | P2-1 đến P2-5 | Agent + IT | Theo từng mục |

## 5. Runbook mở lại vận hành (Đ3)

1. Kiểm OneDrive xanh và `news\_manifest\20261005.json` đã thấy trên web.
2. Chạy từ `C:\src\news-scraper\project`: `article_run.py --where`, `pipeline_radar.py status`, `ops_daemon.py once`. Không có ĐỎ mới so với 2026-10-06.
3. Đặt biến môi trường người dùng `NEWS_SCAPE_PUBLISH_DIR` thành `...\FRA - Data\news`, rồi đặt `publish.enabled: true` trong `config/ops.yaml`.
4. Gỡ cờ dừng: xoá `C:\data\news-scape\AGY_STOP` (hoặc `/unstop`), xoá `.pipeline.lock` cũ của PID 41752.
5. Bật task: `schtasks /Change /TN news-scape-ops /ENABLE`, chạy `Start-ScheduledTask news-scape-ops`, rồi bật watchdog. Task `news_cron` cũ giữ Disabled hoặc gỡ.
6. `ops_daemon.py status` báo "Daemon: sống". Đặt mandate (`/level L1`) khi muốn daemon tự mở đợt. Xoá `STOP-MIGRATION-US038.md` ở worktree US-039 khi lane đó được mở lại.

**Quay lui:** dừng task. Cài lại task từ thư mục cũ theo plan §N4. Khôi phục `monocle.db` từ `archive\pre-cutover-20261006` (DB này đã ghi đường dẫn tương đối, mã cũ vẫn đọc được tiền tố `data/` nhưng sẽ ghi Bronze vào OneDrive).

## 6. Quyết định cần người vận hành

1. Quyền đọc trên `FRA - Data\news\users\` và `review\` (P0-3).
2. Nhịp xuất bản bản review: hằng ngày giữ 7 bản, hay hằng tuần giữ 4 bản (P1-9).
3. Định dạng Bronze: `.tar.gz` nhanh, hoặc `.tar.xz` preset thấp (P0-4). Đề xuất `.tar.gz` nếu số đo xác nhận.
4. Nơi đặt `harness.db`: dưới `C:\data\news-scape\harness\` (đề xuất), hay ở gốc cây mã như hiện nay (P1-1).
