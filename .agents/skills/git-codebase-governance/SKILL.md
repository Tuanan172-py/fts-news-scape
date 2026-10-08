---
name: git-codebase-governance
description: >-
  Quy trình chuẩn tra soát, đối chiếu và vận hành Git để quản trị codebase,
  kiểm soát kiến trúc hệ thống, bảo vệ ranh giới phân tầng và an toàn đồng bộ đa môi trường.
---

# Quy Trình Tra Soát Đối Chiếu Git & Quản Trị Kiến Trúc Codebase

Mục đích: Cung cấp quy chuẩn, runbook và công cụ kiểm định tự động để tra soát, đối chiếu và đồng bộ trạng thái Git, bảo đảm tính toàn vẹn của mã nguồn, ranh giới phân tầng kiến trúc và ngăn ngừa xung đột dữ liệu trên môi trường đồng bộ.

---

## 1. Ranh Giới Quản Trị & Bất Biến Cốt Lõi

Mọi thao tác can thiệp vào codebase và Git repository bắt buộc tuân thủ 5 bất biến:

1. **Bất biến WIP = 1 Per Worktree (ADR-0022)**:
   Mỗi Git worktree/nhánh chỉ có tối đa 1 story ở trạng thái `in_progress`. Khi có yêu cầu khẩn cấp ngắt ngang trong cùng một worktree, lưu trữ (`stash`) hoặc chuyển trạng thái tác vụ hiện tại sang `blocked` hoặc `deferred` trước khi nhận việc mới. Các worktree khác nhau hoàn toàn bình đẳng và được phép chạy song song các story độc lập.
2. **Bất biến Thẩm Định Trước Khi Commit (Pre-commit Quality Gate)**:
   Mọi commit phải vượt qua 3 cổng kiểm soát:
   - Cú pháp AST hợp lệ (`ast.parse`) trên toàn bộ tệp Python được sửa đổi.
   - Kiểm thử đơn vị đạt tỷ lệ đạt 100% (`pytest tests/`).
   - Tuân thủ quy chuẩn docstring và danh mục từ cấm theo chuẩn quy định.
3. **Bất biến Phân Tầng Kiến Trúc (Architecture Boundaries)**:
   - Tầng Crawl/Bronze: Lưu trữ thô, bất biến. Không chứa logic nghiệp vụ phân tích.
   - Tầng Tinh Chế/Silver: Chuẩn hóa dữ liệu, trích xuất cấu trúc văn bản thuần túy. Không giả lập suy luận LLM.
   - Tầng Tri Thức/Gold: Đảm nhận trích xuất thực thể, hàm ý thị trường, chấm điểm trọng yếu và trích dẫn kiểm chứng.
   - Tầng Phân Phối/Delivery: Phân tuyến dữ liệu theo danh mục người dùng, ghi nhận bàn giao độc lập.
4. **Bất biến Cô Lập Môi Trường (Hybrid Workspace Invariant)**:
   - Thư mục `.git` thực tế luôn được lưu trữ ngoài vùng đồng bộ đám mây bằng `--separate-git-dir`.
   - Virtual environment (`.venv`) và database runtime SQLite (`.db`, `.db-wal`) luôn đặt tại ổ đĩa cục bộ độc lập.
5. **Bất biến Thúc Đẩy Bản Ghi Mới Hơn (Promote-Before-Delete)**:
   Không xóa mù quáng các tệp xung đột đồng bộ (`-HOSTNAME`). Phải đối chiếu dấu thời gian và mã băm SHA-256; bản mới hơn phải được thúc đẩy thành tệp chính thức trước khi dọn dẹp bản sao thừa.

---

## 2. Ma Trận Đối Chiếu 4 Vùng Dữ Liệu Git

Trước khi thực hiện bất kỳ thay đổi nào, tiến hành đối chiếu trạng thái giữa 4 vùng:

| Vùng Dữ Liệu | Trạng Thái Cần Tra Soát | Lệnh Tra Soát | Hành Động Chuẩn Hóa |
| :--- | :--- | :--- | :--- |
| **1. Working Tree** | Tệp sửa đổi chưa stage, tệp untracked, tệp xung đột máy trạm (`-HOSTNAME`). | `git status -s` | Hoàn nguyên tệp rác (`git checkout`/`git restore`), dọn dẹp xung đột bằng script bảo trì. |
| **2. Index (Staging)** | Tệp đã stage sẵn sàng commit. | `git diff --cached --stat` | Kiểm tra phạm vi tệp, loại bỏ tệp vô tình stage nhầm (`git restore --staged <file>`). |
| **3. Local Branch** | Commit cục bộ chưa đẩy lên remote (ahead). | `git log origin/<branch>..HEAD --oneline` | Xác định các commit đang chờ đẩy, đối chiếu nội dung thay đổi. |
| **4. Remote Tracking** | Commit trên remote chưa kéo về (behind). | `git fetch origin`<br/>`git log HEAD..origin/<branch> --oneline` | Nhận diện thay đổi từ xa, chuẩn bị quy trình đồng bộ an toàn. |

---

## 3. Quy Trình Vận Hành Tiêu Chuẩn (SOP)

### SOP 1: Bắt Đầu Phiên & Đồng Bộ An Toàn (Sync Ingest)

Áp dụng khi bắt đầu phiên làm việc hoặc khi cần cập nhật trạng thái mới nhất từ remote:

```
[Fetch Remote] ──> [Kiểm Tra Trạng Thái Local] ──> [Đối Chiếu Diff] ──> [Safe Pull / Fast-Forward]
```

1. **Bước 1: Fetch metadata từ remote**:
   ```powershell
   git fetch origin
   ```
2. **Bước 2: Tra soát khác biệt giữa Local và Remote**:
   ```powershell
   # Xem danh sách commit mới trên remote
   git log HEAD..origin/main --oneline

   # Xem danh sách tệp bị tác động trên remote
   git diff --name-status HEAD..origin/main
   ```
3. **Bước 3: Xử lý tệp Untracked hoặc Sửa đổi Cục bộ gây cản trở**:
   - Nếu có tệp untracked trùng tên với tệp mới trên remote: Tạm thời di dời hoặc sao lưu bản cục bộ sang đuôi `.local.bak`.
   - Nếu có thay đổi đang dở dang: Chạy `git stash` để cất giữ vùng làm việc.
4. **Bước 4: Thực hiện Pull**:
   ```powershell
   git pull origin main
   ```
5. **Bước 5: Khôi phục thay đổi (nếu có stash)**:
   ```powershell
   git stash pop
   ```

---

### SOP 2: Phát Triển Tính Năng & Quản Lý Nhánh (Branch & WIP)

1. **Quy tắc đặt tên nhánh**:
   - Tính năng mới: `feature/<tên-tính-năng>` (VD: `feature/token-optimization`).
   - Sửa lỗi: `fix/<mã-lỗi-hoặc-mô-tả>` (VD: `fix/l1-alias-matching`).
   - Chuẩn hóa / Tái cấu trúc: `refactor/<phạm-vi>` (VD: `refactor/export-docstrings`).
2. **Tạo nhánh từ trạng thái sạch**:
   ```powershell
   git checkout main
   git pull origin main
   git checkout -b feature/<ten-nhanh>
   ```
3. **Duy trì tính độc lập**: Không trộn lẫn nhiều mục tiêu nghiệp vụ trong cùng một nhánh.

---

### SOP 3: Kiểm Chuẩn Chất Lượng Trước Khi Commit (Pre-commit Verification)

Trước khi thực hiện lệnh commit, bắt buộc kiểm tra chất lượng cơ học bằng một lệnh duy nhất:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git verify
```

Lệnh này tự động thực hiện:
- Kiểm tra toàn bộ cú pháp AST (`ast.parse`) trên tất cả các tệp Python trong repo.
- Quét và phát hiện các tệp cấm: xung đột OneDrive (`*-DESKTOP-*`, `*-FPA-*`), CSDL SQLite (`.db`, `.db-wal`), bảng tính (`.xlsx`).
- Báo cáo chi tiết danh sách lỗi (nếu có) và chặn commit nếu không đạt chuẩn.

---

### SOP 4: Đóng Gói Commit Chuẩn Hóa Theo Cấp Độ Harness

Mọi commit bắt buộc tuân thủ phân tầng 3 Tiers của Harness:

1. **Với Story Hoàn Tất (Normal Tier — US-XXX)**:
   - Sử dụng lệnh tự động nghiệm thu kèm commit:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py story complete --id US-XXX --run-verify --commit
     ```
   - Lệnh tự động chạy bộ test kiểm chứng, tự động commit các tệp đã sửa đổi với định dạng:
     `<type>(<scope>): <title> (US-XXX)`
     đồng thời tự động ghi nhận mã băm `git_commit` và nhánh `git_branch` vào CSDL `harness.db`.

2. **Với Đóng Phiên / Tác Vụ Nhỏ (Tiny Tier / Session Closure)**:
   - Sử dụng lệnh checkpoint:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git checkpoint --summary "cập nhật tài liệu và tối ưu docstrings"
     ```

3. **Với Thay Đổi Trọng Yếu (High-Risk Tier / ADR)**:
   - Commit gắn với mã quyết định:
     `docs(adr): NNNN-<tên-quyết-định>`

---

### SOP 5: Đẩy Thay Đổi & Đóng Phiên Nghiệm Thu (Push & Harness Closure)

1. **Đẩy mã nguồn lên Remote**:
   ```powershell
   git push origin <ten-nhanh>
   ```
2. **Kiểm tra trạng thái sạch trước khi đóng phiên**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git status
   ```
3. **Bảng Nghiệm Thu Đóng Phiên (Harness Closure Protocol)**:
   Mọi phản hồi kết thúc ca làm việc bắt buộc có dòng thứ 7 báo cáo trạng thái Git:
   `| Git Codebase Status | Yes / Clean | Commit <hash> trên nhánh <branch>, working tree sạch |`

---

### SOP 6: Quy Trình Phối Hợp Qua Pull Request Trên Repo Tổ Chức (Enterprise PR Workflow)

Áp dụng bắt buộc khi đóng góp mã nguồn vào kho lưu trữ chung của tổ chức (`Research-FPA/news-scraper`):

```
[Main Sạch] ──> [Tạo Nhánh feature/fix] ──> [Phát Triển & Test] ──> [Commit Chuẩn Doanh Nghiệp]
      ▲                                                                     │
      │                                                                     ▼
[Sync Cục Bộ] ◄── [Merge PR trên Web] ◄── [Review & Gate] ◄── [Push Nhánh & Mở PR]
```

1. **Bước 1: Đồng bộ nhánh `main` trước khi tạo việc mới**:
   ```powershell
   git checkout main
   git pull fpa main
   ```
2. **Bước 2: Tạo nhánh tính năng/sửa lỗi từ `main`**:
   - Tính năng mới: `git checkout -b feature/<ma-story>-<ten-ngan>` (VD: `feature/us042-duckdb-lakehouse`).
   - Sửa lỗi: `git checkout -b fix/<ma-story>-<ten-ngan>` (VD: `fix/us040-code-first-guard`).
3. **Bước 3: Thực thi kiểm định Quality Gate trước khi commit**:
   - Kiểm tra AST và vệ sinh tệp:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git verify
     ```
   - Chạy toàn bộ bộ kiểm thử đơn vị:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" -m pytest project/tests/ -q
     ```
4. **Bước 4: Đóng gói commit chuẩn danh tính tổ chức**:
   - Đảm bảo commit mang email công ty (`anpt@fpts.com.vn`).
   - Tiêu đề commit: `<type>(<scope>): <mo-ta> (US-XXX)`.
   - Cấm tuyệt đối chèn trailer `Co-Authored-By: Claude...`.
5. **Bước 5: Đẩy nhánh lên kho tổ chức**:
   ```powershell
   git push -u fpa feature/<ten-nhanh>
   ```
6. **Bước 6: Mở và xét duyệt Pull Request trên GitHub**:
   - Truy cập `https://github.com/Research-FPA/news-scraper/compare/main...<ten-nhanh>?expand=1`.
   - Kiểm tra tab **Files changed**: Xác nhận 0 file rác, 0 credentials/keys, 0 file nhị phân lớn.
   - Xét duyệt (Review) và chọn **Create a merge commit** (hoặc Squash and merge tùy chỉ đạo).
7. **Bước 7: Đồng bộ kết quả về máy trạm và dọn dẹp**:
   ```powershell
   git checkout main
   git pull fpa main
   git branch -d feature/<ten-nhanh>
   ```

---

## 4. Runbook Xử Lý Tình Huống Sự Cố (Disaster Recovery)

### Tình huống 1: Tệp Untracked Ngăn Cản Tiến Trình Pull

- **Hiện tượng**: Git báo lỗi `error: The following untracked working tree files would be overwritten by merge`.
- **Nguyên nhân**: Phía remote có tệp mới được thêm vào, trong khi máy cục bộ có tệp cùng tên nhưng chưa được Git theo dõi.
- **Biện pháp xử lý chuẩn**:
  1. Kiểm tra nội dung tệp cục bộ xem có chứa dữ liệu phân tích quan trọng hay không.
  2. Nếu tệp cục bộ là báo cáo phát sinh tự động: Di dời sang tên phụ `Move-Item <file> <file>.local.bak`.
  3. Thực hiện lại lệnh `git pull origin <branch>`.
  4. Đối chiếu nội dung giữa bản remote và bản `.local.bak`, hợp nhất nếu cần thiết, sau đó dọn dẹp bản backup.

### Tình huống 2: Xung Đột Đồng Bộ OneDrive Tạo Ra Hàng Loạt Tệp `-HOSTNAME`

- **Hiện tượng**: Thư mục xuất hiện hàng loạt tệp có đuôi `-DESKTOP-*` hoặc `-FPA-*`.
- **Biện pháp xử lý chuẩn**:
  1. Tuyệt đối không xóa mù quáng bằng lệnh regex đơn giản.
  2. Chạy công cụ bảo trì tích hợp sẵn trong dự án:
     ```powershell
     # Quét kiểm tra trước
     & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/maintenance/clean_onedrive_conflicts.py

     # Áp dụng xử lý promote và dọn dẹp an toàn
     & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/maintenance/clean_onedrive_conflicts.py --apply
     ```

### Tình huống 3: Nhánh Cục Bộ Bị Lệch Hướng (Diverged Branches)

- **Hiện tượng**: Git thông báo nhánh cục bộ và remote có các commit khác nhau (`Your branch and 'origin/main' have diverged`).
- **Biện pháp xử lý chuẩn**:
  1. Kiểm tra nhật ký commit của cả hai phía:
     ```powershell
     git log --graph --oneline --left-right HEAD...origin/main
     ```
  2. Nếu các commit cục bộ là công việc độc lập: Thực hiện rebase để giữ lịch sử phẳng:
     ```powershell
     git pull --rebase origin main
     ```
  3. Giải quyết xung đột (nếu phát sinh) trên từng commit, kiểm tra lại test suite trước khi hoàn tất rebase.

---

## 5. Quy Chuẩn Chuyển Dịch Từ Repo Cá Nhân Lên Repo Tổ Chức (Enterprise Migration Governance)

Khi chuyển dịch mã nguồn từ kho nghiên cứu cá nhân (`fts-news-scape`) sang kho chính thức của tổ chức (`Research-FPA/news-scraper`), bắt buộc tuân thủ 4 nguyên tắc định hướng:

### 1. Phân định Vai trò 2 Remote (Dual-Remote Strategy)
- **Remote Tổ chức (`fpa` hoặc `origin` mới)**:
  - URL: `https://github.com/Research-FPA/news-scraper.git`
  - Vai trò: **Single Source of Truth (Nguồn chân lý duy nhất)**.
  - Quy chuẩn: Nhánh `main` được bảo vệ, mọi thay đổi qua PR, lịch sử commit sạch, không chứa artifacts/data/credentials.
- **Remote Cá nhân (`personal` hoặc `origin` cũ)**:
  - URL: `https://github.com/Tuanan172-py/fts-news-scape.git`
  - Vai trò: **Mirror / Sandbox R&D cá nhân**.
  - Quy chuẩn: Chỉ phục vụ backup thử nghiệm độc lập; không dùng làm nguồn kéo mã chính thức cho các agent vận hành.

### 2. Bất biến Danh tính Doanh nghiệp (Enterprise Identity Invariant)
- Mọi commit trên repo tổ chức BẮT BUỘC mang thông tin định danh chính thức của nhân sự trong doanh nghiệp:
  ```powershell
  git config user.name "An Pham Thanh"
  git config user.email "anpt@fpts.com.vn"
  ```
- **Cấm Tuyệt Đối**:
  - Không sử dụng email cá nhân (`@gmail.com`) đẩy lên repo tổ chức để tránh lộ thông tin ngoài luồng.
  - Không để các agent/tool tự động chèn trailer `Co-Authored-By: Claude...` hoặc tên bot AI vào commit message.

### 3. Bất biến Cách ly Vùng Làm việc (Execution Isolation Invariant)
- Toàn bộ hoạt động code, chạy pipeline và test BẮT BUỘC thực thi tại thư mục cục bộ độc lập:
  `C:\src\news-scraper` (worktree của `C:\gitdirs\news-scape.git`).
- TUYỆT ĐỐI KHÔNG chạy runtime hay thao tác git trực tiếp trong thư mục đồng bộ OneDrive/SharePoint để triệt tiêu nguy cơ xung đột khóa tệp (`PermissionError`) và phân mảnh lịch sử git (khớp Rule 03).

### 4. Quy trình Tẩy sạch Metadata Agent trước khi Nhập kho Tổ chức
Khi phát hiện lịch sử cũ còn vướng email cá nhân hoặc trailer Co-Authored-By, sử dụng `git-filter-repo` (đã tích hợp trong venv `C:\venvs\news-scape`) để xử lý toàn diện:
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" -m git_filter_repo `
  --refs <danh-sach-nhanh> `
  --message-callback "return re.sub(br'(?m)^\s*Co-Authored-By:.*$', b'', message)" `
  --email-callback "return b'anpt@fpts.com.vn'" `
  --name-callback "return b'An Pham Thanh'" `
  --force
```

---

## 6. Danh Mục Kiểm Tra Tra Soát Nhanh (Audit Checklist)

Bảng kiểm tra định kỳ hàng ngày dành cho quản trị viên và hệ thống kiểm toán tự động:

- [ ] Lệnh `git status` không hiển thị tệp sửa đổi ngoài ý muốn.
- [ ] Không có tệp nhị phân dữ liệu lớn (`.xlsx`, `.db`, `.zip`) nằm trong khu vực theo dõi code.
- [ ] Môi trường ảo `.venv` và thư mục `.pytest_cache` được bảo đảm nằm trong `.gitignore`.
- [ ] Nhánh làm việc đồng bộ với nhánh remote chỉ định (`up to date`).
- [ ] Toàn bộ unit tests đạt trạng thái PASS khi chạy trên môi trường chuẩn `C:\venvs\news-scape`.
- [ ] Mã nguồn tuân thủ đầy đủ quy chuẩn không sử dụng từ cấm thuộc Blacklist.
- [ ] Git commit author phản ánh đúng danh tính tổ chức (`anpt@fpts.com.vn`), 0 vết Co-Authored-By AI.
