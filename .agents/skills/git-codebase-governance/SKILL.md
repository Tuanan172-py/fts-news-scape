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

1. **Bất biến WIP = 1**:
   Chỉ có tối đa 1 story/tác vụ ở trạng thái `in_progress` tại một thời điểm. Khi có yêu cầu khẩn cấp ngắt ngang, lưu trữ (`stash`) hoặc chuyển trạng thái tác vụ hiện tại sang `blocked` hoặc `deferred` trước khi nhận việc mới.
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

Trước khi thực hiện lệnh commit, bắt buộc hoàn thành bảng kiểm tra chất lượng:

```powershell
# 1. Kiểm tra toàn bộ cú pháp AST của các file Python đã sửa đổi:
& "C:\venvs\news-scape\Scripts\python.exe" -c "
import ast, sys
from pathlib import Path
for p in Path('.').rglob('*.py'):
    if '.venv' in p.parts or '__pycache__' in p.parts:
        continue
    try:
        ast.parse(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'Lỗi cú pháp tại {p}: {e}')
        sys.exit(1)
print('AST check passed 100%')
"

# 2. Chạy bộ kiểm thử đơn vị:
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest project/tests/ -q

# 3. Quét tệp xung đột hoặc tệp rác phát sinh:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/maintenance/clean_onedrive_conflicts.py
```

---

### SOP 4: Đóng Gói Commit Chuẩn Hóa (Conventional Commits)

1. **Cấu trúc thông điệp commit**:
   ```
   <loại>(<phạm-vi>): <mô-tả-ngắn-gọn-mệnh-lệnh-trực-diện>

   [Thân commit: giải thích lý do, tác động kiến trúc nếu cần thiết]
   ```
2. **Bảng phân loại tiền tố**:
   - `feat`: Thêm tính năng mới hoặc mở rộng nghiệp vụ.
   - `fix`: Sửa lỗi logic, sửa lỗi truy vấn hoặc dữ liệu sai lệch.
   - `refactor`: Tái cấu trúc mã nguồn, không làm đổi hành vi bên ngoài.
   - `docs`: Bổ sung hoặc cập nhật tài liệu kỹ thuật, chuẩn hóa docstrings.
   - `test`: Thêm hoặc cập nhật bộ kiểm thử đơn vị, fixture.
   - `chore`: Cập nhật cấu hình, script phụ trợ, dọn dẹp vệ sinh tệp.
3. **Quy tắc nội dung**:
   - Không sử dụng đại từ nhân xưng ("tôi", "chúng ta").
   - Sử dụng động từ hành động trực diện ("thêm", "sửa", "tối ưu", "loại bỏ").
   - Mô tả chính xác thực thể và module bị tác động.

---

### SOP 5: Đẩy Thay Đổi & Đóng Phiên Nghiệm Thu (Push & Harness Closure)

1. **Đẩy mã nguồn lên Remote**:
   ```powershell
   git push origin <ten-nhanh>
   ```
2. **Lập Bảng Nghiệm Thu Đóng Phiên (Harness Closure Protocol)**:
   Mọi phiên làm việc kết thúc bắt buộc có bảng tổng kết 5 tiêu chí:
   - Cấp độ rủi ro (Cấp 1: TINY / Cấp 2: NORMAL / Cấp 3: HIGH-RISK).
   - Mã băm Commit & Tên nhánh.
   - Trạng thái kiểm thử (Tỷ lệ pass và số lượng test).
   - Tình trạng tệp và vệ sinh môi trường.
   - Bước tiếp theo hoặc vấn đề tồn đọng.

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

## 5. Danh Mục Kiểm Tra Tra Soát Nhanh (Audit Checklist)

Bảng kiểm tra định kỳ hàng ngày dành cho quản trị viên và hệ thống kiểm toán tự động:

- [ ] Lệnh `git status` không hiển thị tệp sửa đổi ngoài ý muốn.
- [ ] Không có tệp nhị phân dữ liệu lớn (`.xlsx`, `.db`, `.zip`) nằm trong khu vực theo dõi code.
- [ ] Môi trường ảo `.venv` và thư mục `.pytest_cache` được bảo đảm nằm trong `.gitignore`.
- [ ] Nhánh làm việc đồng bộ với nhánh remote chỉ định (`up to date`).
- [ ] Toàn bộ unit tests đạt trạng thái PASS khi chạy trên môi trường chuẩn `C:\venvs\news-scape`.
- [ ] Mã nguồn tuân thủ đầy đủ quy chuẩn không sử dụng từ cấm thuộc Blacklist.
