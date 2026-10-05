# Kế hoạch US-038: mã lên kho tổ chức, dữ liệu lên SharePoint

- **Ngày lập:** 2026-10-05
- **Story:** US-038 (high-risk, đang `blocked` chờ người)
- **Quyết định nền:** ADR 0020 (proposed). Kế thừa phương án A3 của [`../20261002-1500-sharepoint-data-plane-and-org-pr/plan.md`](../20261002-1500-sharepoint-data-plane-and-org-pr/plan.md): một máy ghi, SharePoint là kho xuất bản. Hộp trao đổi outbox/inbox cho nhiều laptop tách khỏi đợt này.
- **Đích cuối:**
  - Mã ở `C:\src\news-scraper`, clone từ `github.com/Research-FPA/news-scraper`.
  - Dữ liệu ghi ở `C:\data\news-scape`.
  - Dữ liệu dùng chung ở `FRA - Data/news/` trên SharePoint.
  - Thư mục `FRA_DataIngestion - news-scape` không còn chứa mã chạy.

## 1. Trạng thái tại thời điểm lập

| Việc | Trạng thái |
|---|---|
| Snapshot sạch `import/clean-20261005` (df021e6), 888 tệp, 8,2 MB | Xong, nằm ở kho cục bộ |
| Push snapshot lên `Research-FPA/news-scraper` (đang rỗng, private) | **Chờ người (N1)** |
| ADR 0020 cơ chế xuất bản SharePoint | **Chờ người duyệt (N3)** |
| Dữ liệu cũ chuyển vào `C:\data\news-scape\archive\20261005-cleanup\` | Xong, trừ `C:\data\news-scape\raw_html` (**N2**) |
| Cách ly test, gom đường dẫn, chuyển dữ liệu nóng, publisher | Chưa làm |

## 2. Lộ trình

Mã phụ trách: **N** = người vận hành, **A** = agent.

| Bước | Ai | Việc | Phụ thuộc | Bằng chứng xong |
|---|---|---|---|---|
| N1 | N | Push snapshot lên kho tổ chức | — | `main` trên GitHub có commit df021e6 |
| N2 | N | Chuyển `raw_html` cũ vào archive | — | `C:\data\news-scape\raw_html` không còn |
| N3 | N | Duyệt ADR 0020, trả lời 3 câu hỏi ở §6, tạo thư mục `news/` | — | ADR chuyển `accepted`, thư mục `FRA - Data\news` tồn tại và ghi được |
| A1 | A | Chuyển nhánh làm việc sang `fpa/main` | N1 | Nhánh `dev/us038` tách từ `fpa/main`, có đủ commit sau snapshot |
| A2 | A | PR-1: cách ly test | A1 | `pytest tests/` toàn bộ xanh. `monocle.db` thật không đổi `mtime` sau khi chạy |
| A3 | A | PR-2: `core/paths.py` làm nguồn đường dẫn duy nhất; packet ghi đường dẫn tương đối; script chuyển đổi đường dẫn trong DB (có `--dry-run`) | A2 | Không còn `"data/..."` tự ghép ngoài `paths.py`. Test xanh. Script chạy `--dry-run` in đúng số dòng cần đổi |
| N4 | N + A | Khung chuyển đổi: dừng daemon, clone sang `C:\src`, chuyển dữ liệu, cài lại task, sửa preset DSH | A3, không có đợt mở | `pipeline_radar.py status` và `ops_daemon.py status` xanh từ thư mục mới |
| A4 | A | PR-3: publisher mức L1 và probe sức khoẻ (ADR 0020 §2.3, §2.6) | N3, N4 | Lần xuất bản đầu có `_manifest/latest.json`, SHA256 khớp |
| N5 | N | Kiểm lần xuất bản đầu trên SharePoint, đưa archive lên `news/backup/` | A4 | Mở được tệp review DB và Parquet từ máy khác |
| N6 | N | Ngừng đồng bộ thư mục mã cũ sau 2 tuần chạy ổn | N4 + 14 ngày | Thư mục cũ gỡ khỏi OneDrive |
| N7 | N | (Sau) Xin IT cấp ứng dụng Graph cho mức L2 | N3 | App registration `Sites.Selected` trên site FRA |

PR vào fpa-toolkit (phần tiêu thụ dữ liệu) nằm ngoài kế hoạch này. Khi làm, nhớ GLB-DEC-069 (không nhắc tên trợ lý AI trong tệp được theo dõi) và `no-workspace-paths`.

---

## 3. Hướng dẫn chi tiết cho người vận hành

Mọi lệnh chạy trong PowerShell. Nếu chạy ngay trong phiên Claude Code, thêm `!` ở đầu dòng lệnh.

### N1. Push snapshot lên kho tổ chức

Điều kiện: tài khoản GitHub trên máy có quyền Write trên `Research-FPA/news-scraper`.

1. Đứng ở thư mục kho:
   ```powershell
   cd "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape"
   ```
2. Kiểm snapshot đúng là bản sạch. Lệnh in `888` và không in tên tệp dữ liệu nào:
   ```powershell
   git ls-tree -r --name-only import/clean-20261005 | Measure-Object -Line
   git ls-tree -r --name-only import/clean-20261005 | Select-String -Pattern '\.(db|xlsx|xls|csv|parquet|docx)$'
   ```
3. Push thành nhánh `main` của kho tổ chức:
   ```powershell
   git push fpa import/clean-20261005:refs/heads/main
   ```
   - Nếu hiện cửa sổ đăng nhập GitHub, đăng nhập bằng tài khoản có quyền trên tổ chức Research-FPA.
   - Lỗi `403` hoặc `Permission denied`: nhờ chủ tổ chức thêm tài khoản với vai trò Write, rồi chạy lại.
4. Kiểm trên web: mở `https://github.com/Research-FPA/news-scraper`. Có 1 commit "feat(repo): initial import of news-scape codebase (US-038)", có `AGENTS.md`, `project/`, `.agents/`.
5. Khuyến nghị, làm trên web: Settings → Branches → Add rule cho `main`, bật "Require a pull request before merging". Từ đây mọi thay đổi vào `main` đi qua PR.
6. Tuỳ chọn: cho phép agent tự push nhánh PR lên `fpa` (không push `main`). Trong Claude Code gõ `/permissions` và thêm luật cho phép `Bash(git push fpa dev/*)`. Không thêm thì sau mỗi PR agent sẽ đưa lệnh push để bạn tự chạy.
7. Báo lại cho agent: "đã push N1". Agent làm tiếp A1.

**Quay lui:** kho tổ chức đang rỗng nên không có gì để mất. Push nhầm thì xoá nhánh trên web và push lại.

### N2. Chuyển `raw_html` cũ vào archive

Thư mục này là Bronze cũ ngày 08/09, không còn mã nào đọc. Phiên agent bị chặn quyền khi chuyển nó.

1. Đóng mọi cửa sổ Explorer hoặc terminal đang mở trong `C:\data\news-scape\raw_html`.
2. Chuyển (cùng ổ đĩa nên gần như tức thì, không sao chép dữ liệu):
   ```powershell
   Move-Item C:\data\news-scape\raw_html C:\data\news-scape\archive\20261005-cleanup\legacy-c-data\raw_html
   ```
3. Kiểm: lệnh dưới in `False` rồi `True`:
   ```powershell
   Test-Path C:\data\news-scape\raw_html
   Test-Path C:\data\news-scape\archive\20261005-cleanup\legacy-c-data\raw_html
   ```
4. Lỗi "being used by another process": có tiến trình đang giữ thư mục. Khởi động lại máy rồi làm lại bước 2. Không xoá thư mục này.

Sau bước này, dòng `raw_html` trong `archive\20261005-cleanup\MANIFEST.txt` khớp với thực tế.

### N3. Duyệt ADR 0020 và chuẩn bị SharePoint

1. Đọc `docs/decisions/0020-data-plane-sharepoint-co-che-xuat-ban.md`. Nếu đồng ý, báo agent "duyệt ADR 0020". Agent đổi trạng thái sang `accepted` và ghi tên người duyệt.
2. **Kiểm quyền ghi trên `sites/FRA/Data`:**
   - Mở trình duyệt: `https://fptscomvn.sharepoint.com/sites/FRA/Data`.
   - Bấm **New → Folder**, đặt tên `news`.
   - Tạo được là tài khoản có quyền ghi. Không có nút New, hoặc báo lỗi quyền, thì nhờ chủ site cấp quyền **Edit** cho thư mục `news`.
3. **Giữ thư mục `news` luôn có sẵn trên máy vận hành:**
   - Explorer → `C:\Users\anpt\OneDrive - fpts.com.vn\FRA - Data\news`.
   - Chuột phải → **Always keep on this device**.
   - Biểu tượng chuyển thành chấm xanh đặc.
4. **Kiểm hạn mức dung lượng của site:**
   - Trên web site FRA: Settings (bánh răng) → **Site information → View all site settings → Storage Metrics**, hoặc hỏi quản trị M365.
   - Ước tính nhu cầu: dưới 1 GB mỗi tháng cho Bronze nén, cộng Parquet và bản review DB (khoảng 100–200 MB mỗi bản, giữ 7 bản).
5. **Tài khoản dịch vụ cho mức L2:** chỉ cần trả lời "có thể xin" hoặc "chưa". Thủ tục xin ở N7.
6. Gửi agent ba câu trả lời: (a) quyền ghi có/không, (b) hạn mức còn trống bao nhiêu, (c) L2 có thể xin không.

### N4. Khung chuyển đổi (khoảng 60–90 phút, làm ngoài giờ cào cao điểm)

Chỉ làm khi agent báo **A3 đã merge** vào `main` của kho tổ chức. Agent sẽ có mặt trong phiên để chạy phần chuyển đổi DB và kiểm tra.

**Chuẩn bị (trước 1 ngày):**
- Kiểm còn ≥ 15 GB trống trên ổ C (dữ liệu được sao chép trước, xoá sau):
  ```powershell
  Get-PSDrive C
  ```
- Báo người dùng nhận file xlsx rằng giao hàng ngày hôm đó có thể trễ.

**Bước 1. Dừng mở đợt mới và chờ đợt đang chạy xong**
1. Trên Telegram gõ `/pause`.
2. Chạy lệnh dưới, chờ tới khi không còn đợt nào ở trạng thái đang chạy:
   ```powershell
   cd "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape\project"
   C:\venvs\news-scape\Scripts\python.exe scripts\ops_daemon.py status
   ```
3. Còn đợt mở quá lâu thì gõ `/cancel <mã đợt>` để nhả bài.

**Bước 2. Dừng daemon, watchdog và DSH**
```powershell
schtasks /Change /TN news-scape-ops-watchdog /DISABLE
schtasks /End /TN news-scape-ops
schtasks /Change /TN news-scape-ops /DISABLE
Get-ScheduledTask news-scape-ops* | Select-Object TaskName, State
```
Kết quả mong đợi: cả hai ở trạng thái `Disabled`. Đóng cửa sổ `dsh web` nếu đang mở.

Kiểm không còn tiến trình Python nào chạy mã từ thư mục cũ:
```powershell
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*FRA_DataIngestion*' } | Select-Object ProcessId, CommandLine
```
Còn dòng nào thì dừng nó: `Stop-Process -Id <ProcessId>`.

**Bước 3. Sao lưu DB trước khi chuyển**
```powershell
Copy-Item C:\data\news-scape\monocle.db "C:\data\news-scape\archive\monocle.db.bak-$(Get-Date -Format yyyyMMdd)-pre-cutover"
```

**Bước 4. Clone mã sang thư mục mới**
```powershell
New-Item -ItemType Directory -Force C:\src | Out-Null
git clone https://github.com/Research-FPA/news-scraper.git C:\src\news-scraper
```

**Bước 5. Sao chép dữ liệu nóng sang `C:\data\news-scape`** (sao chép, chưa xoá bản cũ)
```powershell
$old = "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape"
robocopy "$old\project\data" C:\data\news-scape /E /COPY:DAT /R:1 /W:1 /XD archive archive_conflicts /NFL /NDL /LOG:C:\data\news-scape\archive\cutover-robocopy.log
robocopy "$old\users\output" C:\data\news-scape\users_output /E /R:1 /W:1 /NFL /NDL /LOG+:C:\data\news-scape\archive\cutover-robocopy.log
```
- Tên thư mục đích (`users_output` và các thư mục con) theo bố cục mà A3 chốt trong `core/paths.py`. Agent cập nhật lệnh này khi A3 merge.
- Robocopy trả mã 0–7 là thành công, từ 8 trở lên là lỗi. Xem dòng tổng kết ở cuối tệp log.
- Tệp ở trạng thái chỉ-trên-mây sẽ được tải về trong lúc chép, nên bước này có thể mất 20–40 phút.

**Bước 6. Chuyển đổi đường dẫn trong DB** (agent chạy, bạn xác nhận)
- Agent chạy script của A3 với `--dry-run` và báo số dòng sẽ đổi.
- Bạn đồng ý thì agent chạy `--apply`.

**Bước 7. Cài lại Task Scheduler từ thư mục mới**
```powershell
cd C:\src\news-scraper\project
powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Uninstall
powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Register
Get-ScheduledTask news-scape-ops* | ForEach-Object { $_.TaskName; $_.Actions.WorkingDirectory }
```
Kết quả mong đợi: cả hai task có WorkingDirectory `C:\src\news-scraper\project`.

**Bước 8. Sửa preset DSH**
1. Mở `%DSH_HOME%\profiles\web\cordis.patch.yml`.
2. Sửa dòng `path:` của mục `agent-presets` thành:
   ```yaml
   - path: 'C:\src\news-scraper\.agents\dsh\presets'
   ```
3. Chạy lại `dsh web`. Mở **phiên mới** và chọn preset `news-scape-conductor` trước khi gửi tin đầu tiên (rule 09).

**Bước 9. Kiểm tra trước khi chạy lại**
```powershell
cd C:\src\news-scraper\project
C:\venvs\news-scape\Scripts\python.exe scripts\article_run.py --where
C:\venvs\news-scape\Scripts\python.exe scripts\pipeline_radar.py status
C:\venvs\news-scape\Scripts\python.exe scripts\ops_daemon.py once
```
Kết quả mong đợi:
- `--where` in DB và thư mục dữ liệu nằm dưới `C:\data\news-scape`, không có `OneDrive`.
- Radar không báo ĐỎ mới.
- `once` đo xong, không lỗi đường dẫn.

**Bước 10. Chạy lại**
```powershell
Start-ScheduledTask news-scape-ops
schtasks /Change /TN news-scape-ops-watchdog /ENABLE
C:\venvs\news-scape\Scripts\python.exe scripts\ops_daemon.py status
```
- Dòng đầu phải là "Daemon: sống".
- Trên Telegram gõ `/resume`.

**Bước 11. Theo dõi 24 giờ**
- Có đợt DONE.
- Có xlsx giao hàng trong `C:\data\news-scape\users_output\` (hoặc trên SharePoint sau khi có A4).
- Bài mới vào `C:\data\news-scape\raw_html`.

**Quay lui** (khi bước 9 hoặc 10 đỏ mà không sửa được trong 30 phút):
1. ```powershell
   schtasks /End /TN news-scape-ops
   cd "C:\Users\anpt\OneDrive - fpts.com.vn\FRA_DataIngestion - news-scape\project"
   powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Uninstall
   powershell -ExecutionPolicy Bypass -File scripts\ops_install.ps1 -Register -Start
   ```
2. Khôi phục DB từ bản `pre-cutover` của bước 3, chỉ khi bước 6 đã chạy `--apply`.
3. Đổi lại đường dẫn preset DSH, chạy lại `dsh web`.
4. Dữ liệu cũ trong OneDrive vẫn nguyên vì bước 5 chỉ sao chép.

**Máy thứ hai** (nếu có người khác đang lấy mã qua đồng bộ SharePoint):
- Từ nay máy đó dùng `git clone https://github.com/Research-FPA/news-scraper.git`.
- Máy đó không chạy daemon và không giữ `monocle.db` riêng.

### N5. Kiểm lần xuất bản đầu tiên

Sau khi agent báo A4 đã xuất bản:
1. Trên một máy khác (hoặc trên web), mở `FRA - Data/news/_manifest/latest.json`. Kiểm ngày đúng hôm nay.
2. Mở `news/review/monocle_review_<ngày>.db` bằng DB Browser for SQLite hoặc DataGrip. Đếm bài trong bảng bài viết, so với `pipeline_radar.py status`.
3. Mở một tệp trong `news/parquet/` bằng Excel Power Query hoặc Python. Có dữ liệu ngày hôm nay.
4. Kiểm không có tệp `*.partial` hoặc `*-DESKTOP-*` dưới `news/`.
5. Đưa archive lên SharePoint: chép `C:\data\news-scape\archive\20261005-cleanup\` vào `FRA - Data\news\backup\20261005-cleanup\`. Chờ biểu tượng đồng bộ chuyển xanh, rồi báo agent. Agent đối chiếu số tệp, sau đó bạn tự quyết việc xoá bản cục bộ.

### N6. Ngừng đồng bộ thư mục mã cũ (sau 14 ngày chạy ổn)

1. Kiểm 14 ngày qua không có lệnh nào chạy từ thư mục cũ. Task Scheduler và DSH đều đã trỏ `C:\src`.
2. Trên web `https://fptscomvn.sharepoint.com/sites/FRA_DataIngestion`: đổi tên thư mục `news-scape` thành `news-scape-ARCHIVED-20261005`, hoặc hạ quyền thành chỉ đọc.
3. Trên máy: biểu tượng OneDrive → Settings → Account → **Choose folders** (hoặc **Stop sync** với thư viện `FRA_DataIngestion - news-scape`).
4. Chỉ xoá trên SharePoint khi chắc không còn ai tham chiếu. Thùng rác SharePoint giữ bản xoá 93 ngày.

### N7. Xin IT cấp ứng dụng Graph cho mức L2 (không gấp)

Gửi IT yêu cầu, chi tiết kỹ thuật ở plan 10/02 mục A.2:
- Tạo **App registration** trong Entra ID, tên `news-scape-publisher`.
- Quyền ứng dụng **`Sites.Selected`** (Microsoft Graph), admin consent.
- Cấp vai trò `write` riêng cho site `https://fptscomvn.sharepoint.com/sites/FRA` qua `POST /sites/{site-id}/permissions`.
- Xác thực bằng **chứng chỉ**, không dùng client secret. Gửi lại: tenant ID, client ID, thumbprint chứng chỉ. Chứng chỉ cài vào kho chứng chỉ của tài khoản vận hành.
- Không ghi thông tin này vào kho mã. Agent sẽ đọc từ `C:\data\news-scape\secrets\`.

---

## 4. Rủi ro và cách chặn

| Rủi ro | Chặn bằng |
|---|---|
| Hai phiên agent cùng commit lên hai lịch sử (kho cá nhân và kho tổ chức) | A1 đặt mốc: sau N1 mọi phiên làm trên nhánh tách từ `fpa/main`. Commit mới trên `feature/article-lane-remove-gates` được cherry-pick sang |
| Test ghi vào DB thật trong lúc refactor | A2 làm trước mọi PR khác |
| Chuyển thư mục khi còn đợt mở, `wave_*.json` trỏ đường dẫn cũ | N4 bước 1 chờ hết đợt. A3 đổi packet sang đường dẫn tương đối |
| Dữ liệu Bronze bị xoá nhầm khi dọn | Dọn bằng cách chuyển vào archive, có manifest. Chỉ xoá khi bản trên SharePoint đã được đối chiếu (N5) |
| OneDrive dừng đồng bộ làm xuất bản trễ | Probe ở ADR 0020 §2.6 báo Telegram. Xuất bản không chặn thu thập |
