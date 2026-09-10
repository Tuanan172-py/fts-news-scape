---
name: sharepoint-git-hybrid-workspace
description: >-
  Thiết lập, di dời và vận hành dự án nằm trong thư mục đồng bộ SharePoint/OneDrive
  kết hợp Git version control an toàn, cách ly hoàn toàn .git, .venv và database runtime
  để chống hỏng repo, chống lock file và tối ưu tốc độ.
---

# SharePoint & Git Hybrid Workspace Skill

> **Mục đích:** Cung cấp quy chuẩn, runbook và bộ công cụ tự động để thiết lập hoặc di chuyển bất kỳ dự án nào nằm trên thư mục đồng bộ **SharePoint / OneDrive**, vừa đảm bảo **User/Team quản lý file trực quan trên Cloud**, vừa đảm bảo **mã nguồn được quản lý hoàn hảo bằng Git** không bị sync phá hỏng.

---

## 1. Bối cảnh & Vấn đề Cốt lõi (Root Cause)

Khi một dự án lập trình nằm trong thư mục đồng bộ hai chiều (SharePoint / OneDrive):
1. **`.git` bị phá hoại**: Git ghi dữ liệu theo cơ chế liên kết nguyên tử giữa `objects` và `refs`. OneDrive đồng bộ bất đối xứng từng file độc lập theo thời gian thực $\rightarrow$ Rất dễ gây `fatal: bad object`, mất tracking trong `.git/config`, hoặc đọng file `index.lock` / `index - Copy.lock`.
2. **`.venv` gây nghẽn mạng & gãy môi trường**: Chứa 20.000 – 50.000+ files nhỏ (`.pyc`, `.pyd`, dll). OneDrive quét liên tục gây ngốn 100% CPU/Disk, đồng thời ghi đè `pyvenv.cfg` giữa các máy khác nhau làm hỏng interpreter.
3. **Database SQLite bị lock/hỏng**: SQLite ở chế độ WAL gồm 3 file (`.db`, `.db-wal`, `.db-shm`). OneDrive sync ngắt quãng gây lỗi `database disk image is malformed`.
4. **Files On-Demand "dehydrate" mã nguồn**: Windows tự động chuyển file code thành placeholder đám mây $\rightarrow$ Python báo lỗi `OSError: [Errno 22] Invalid argument` hoặc `FileNotFoundError` khi import.

---

## 2. Mô hình Kiến trúc Phân tầng (Hybrid Architecture)

```
[MÁY CỤC BỘ / LOCAL DRIVE]                         [THƯ MỤC SHAREPOINT / ONEDRIVE]
C:\gitdirs\<repo>.git      <═════ Con trỏ ═════>   .git (chỉ là file text 34 bytes)
  • Toàn bộ commit, nhánh,                         • src/, scripts/, tests/ (Code text thuần)
    stashes, hooks an toàn                         • docs/ (Tài liệu cho người dùng)
                                                   • users/output/ (File CSV/Excel xuất bản)
C:\venvs\<repo>\                                   • data/reports/ (Báo cáo ngày)
  • Python site-packages                           • Bronze / Silver (Dữ liệu tĩnh cần review)
  • Thư viện compiled C/C++
                                                   (Loại trừ khỏi sync: .venv, *.db, *.db-wal)
C:\data\<repo>\<app>.db
  • SQLite runtime ghi liên tục
```

---

## 3. Runbook Thiết lập cho Dự án Mới (Bootstrap Runbook)

Khi bắt đầu một dự án mới hoặc kéo một repo từ GitHub về đặt trong thư mục OneDrive:

### Bước 1: Khởi tạo Git tách biệt (`--separate-git-dir`)
```powershell
param([string]$RepoName = "my-project")

# 1. Tạo thư mục chứa git database trên ổ C cục bộ
$GitDir = "C:\gitdirs\$RepoName.git"
New-Item -ItemType Directory -Path "C:\gitdirs" -Force | Out-Null

# 2. Khởi tạo Git với working tree tại thư mục hiện tại nhưng git-dir ở ổ C
git init --separate-git-dir $GitDir

# Kết quả: .git chỉ là 1 file text nhỏ chứa "gitdir: C:/gitdirs/<RepoName>.git"
```

### Bước 2: Tạo Virtual Environment ở ổ Local
```powershell
param([string]$RepoName = "my-project")

# 1. Tạo venv cục bộ
$VenvPath = "C:\venvs\$RepoName"
New-Item -ItemType Directory -Path "C:\venvs" -Force | Out-Null
python -m venv $VenvPath

# 2. Cài đặt dependencies
& "$VenvPath\Scripts\pip.exe" install --upgrade pip
if (Test-Path "requirements.txt") {
    & "$VenvPath\Scripts\pip.exe" install -r requirements.txt
}

# 3. Đảm bảo .gitignore đã chặn venv nội bộ
$IgnoreEntries = @(".venv/", "__pycache__/", "*.py[cod]", ".pytest_cache/", "*.db", "*.db-wal", "*.db-shm")
foreach ($entry in $IgnoreEntries) {
    if (-not (Select-String -Path ".gitignore" -Pattern [regex]::Escape($entry) -Quiet -ErrorAction SilentlyContinue)) {
        Add-Content -Path ".gitignore" -Value $entry
    }
}
```

### Bước 3: Ghim tệp không bị On-Demand Dehydrate
Chạy lệnh ghim thuộc tính luôn giữ file trên máy:
```powershell
attrib -U +P /s /d "*.*"
```

### Bước 4: Tách Database SQLite Runtime
Trong mã nguồn ứng dụng (`config.py`), luôn hỗ trợ đọc đường dẫn DB từ biến môi trường:
```python
import os
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "app.db"
DB_PATH = Path(os.environ.get("APP_DB_PATH", DEFAULT_DB))
```
Đặt biến môi trường User:
```powershell
[System.Environment]::SetEnvironmentVariable("APP_DB_PATH", "C:\data\$RepoName\app.db", "User")
```

---

## 4. Runbook Di dời Dự án Đang có sẵn (Migration Runbook)

Nếu dự án đã lỡ nằm trên OneDrive và đang có thư mục `.git` hoặc `.venv` thực tế:

```powershell
# 1. Dừng mọi tiến trình Python & IDE
# 2. Di dời .git sang C:\gitdirs
$RepoName = (Get-Item .).Name
$TargetGit = "C:\gitdirs\$RepoName.git"

if (Test-Path ".git" -PathType Container) {
    Write-Host "Dang di doi thu muc .git sang $TargetGit..."
    Move-Item -Path ".git" -Destination $TargetGit -Force
    # Tao con tro .git
    Set-Content -Path ".git" -Value "gitdir: $TargetGit" -Encoding ASCII
}

# 3. Xoa bo .venv noi bo trong OneDrive
if (Test-Path ".venv") {
    Write-Host "Dang xoa .venv noi bo khoi OneDrive..."
    Remove-Item -Recurse -Force ".venv"
}

# 4. Tao venv moi ngoai o C
python -m venv "C:\venvs\$RepoName"
& "C:\venvs\$RepoName\Scripts\pip.exe" install -r requirements.txt
```

---

## 5. Checklist Kiểm định Chất lượng (Audit & Verification)

Chạy script kiểm tra nhanh tính tuân thủ của Workspace:

```powershell
Write-Host "=== KIEM TRA HYBRID WORKSPACE ==="
# 1. Kiem tra .git la file chu khong phai folder
$gitItem = Get-Item ".git" -Force
if ($gitItem.PSIsContainer) {
    Write-Error "VI PHAM: .git van la thu muc thuc nam trong OneDrive!"
} else {
    Write-Host "[OK] .git la file con tro: $(Get-Content .git)" -ForegroundColor Green
}

# 2. Kiem tra khong co .venv trong OneDrive
if (Test-Path ".venv") {
    Write-Warning "CANH BAO: .venv van ton tai trong thu muc OneDrive!"
} else {
    Write-Host "[OK] Thu muc OneDrive sach se, khong bi rac .venv." -ForegroundColor Green
}

# 3. Kiem tra Git CLI
git status --short
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Git CLI hoat dong binh thuong qua con tro." -ForegroundColor Green
}
```

---

## 6. Xử lý Sự cố Thường gặp (Troubleshooting)

- **Lỗi `fatal: not a git repository: C:/gitdirs/...`**: Kiểm tra đường dẫn trong file `.git`. Dùng dấu gạch xuôi `/` thay vì dấu gạch ngược `\` (ví dụ: `gitdir: C:/gitdirs/repo.git`).
- **File bị trạng thái đồng bộ đám mây (mây xanh) không đọc được**: Chạy `attrib -U +P /s /d "*"` trên thư mục gốc.
- **VS Code không nhận venv**: Nhấn `Ctrl + Shift + P` $\rightarrow$ gõ `Python: Select Interpreter` $\rightarrow$ chọn `Enter interpreter path...` $\rightarrow$ trỏ tới `C:\venvs\<repo>\Scripts\python.exe`.

---

## 7. Phòng chống & Xử lý Xung đột Đồng bộ Tệp Tin (Conflict Resolution Runbook)

### 7.1 Nguyên nhân OneDrive Fork File Binary
OneDrive không thể merge nội dung file nhị phân (Excel `.xlsx`, SQLite `.db`, ZIP). Khi ghi đè file với tần suất cao (bulk loop), OneDrive filter driver bị quá tải và tự động tạo bản sao song song `<tên_gốc>-<TÊN_MÁY>.<ext>` (ví dụ: `2019-01-28-FPA-AnPT.xlsx`).

### 7.2 Biện pháp Ngăn ngừa Kỹ thuật
1. **Idempotent Export**: Luôn áp dụng cơ chế bỏ qua file cũ nếu không có dữ liệu mới hoặc không có bản ghi nâng cấp (`new == 0` và `upgraded == 0`).
2. **Byte-level Check (Staging)**: Kiểm tra kích thước và mã băm SHA-256 trước khi swap file tạm vào file đích.
3. **Chạy script bảo trì dọn dẹp an toàn**:
   ```powershell
   # Quét kiểm tra trước (Dry-run):
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/maintenance/clean_onedrive_conflicts.py

   # Thực thi xóa bản sao thừa:
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/maintenance/clean_onedrive_conflicts.py --apply
   ```

### 7.3 Lưu ý Tránh Lỗi Lệnh Console trên Windows
- Không chạy lệnh PowerShell lồng nhau dạng: `powershell -Command "Get-ChildItem | Where { $_.Name ... }"` (chuỗi nháy kép làm mất biến `$_`).
- Luôn ưu tiên đóng gói các tác vụ bảo trì/quét thư mục thành script Python độc lập và gọi qua `C:\venvs\<repo>\Scripts\python.exe`.

### 7.4 Bất biến Thúc đẩy File Conflict Mới hơn (Promote-Before-Delete)
Khi OneDrive fork file thành `<tên_gốc>-<TÊN_MÁY>.<ext>`, file mang tên máy thường là bản chứa các thao tác chỉnh sửa **MỚI NHẤT** của người dùng tại máy trạm đó, trong khi file gốc là bản cũ từ cloud/người khác.
- **CẤM tuyệt đối xóa mù quáng bản `<TÊN_MÁY>`**.
- Luôn kiểm tra `st_mtime` và SHA-256:
  - Nếu bản `<TÊN_MÁY>` mới hơn: **Ghi đè bản `<TÊN_MÁY>` thành file gốc chính thức** (`shutil.copy2`), sau đó mới xóa file có hậu tố.
  - Nếu giống hệt hoặc cũ hơn: Xóa bản sao thừa an toàn.
  - Script `clean_onedrive_conflicts.py` đã tự động hóa 100% quy trình này.
