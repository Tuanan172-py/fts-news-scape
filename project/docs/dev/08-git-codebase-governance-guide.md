# Hướng Dẫn Phương Thức Vận Hành Git & Quản Trị Codebase (08-Guide)

Tài liệu này quy định phương thức làm việc chuẩn, các bước thao tác bắt buộc và cơ chế kiểm soát chất lượng tự động sau khi tích hợp quy trình quản trị Git và Codebase vào khung Harness.

---

## 1. Mục Đích & Phạm Vi Áp Dụng

1. **Khép kín khoảng trống quản trị**: Kết nối giữa tầng quản lý tác vụ logic (`harness.db`) và tầng vật mang mã nguồn thực tế (Git repository & Codebase files).
2. **Ngăn ngừa xung đột môi trường đồng bộ**: Bảo vệ repository khỏi lỗi gãy liên kết `.git`, tệp khóa Office và tệp trùng lặp sinh ra do cơ chế đồng bộ OneDrive / SharePoint.
3. **Bảo đảm chất lượng mã nguồn liên tục**: Tự động hóa kiểm định cú pháp AST (`ast.parse`), kiểm thử đơn vị (`pytest`) và quét danh mục từ cấm (Rule 06 Blacklist) trước khi mã nguồn được ghi nhận vào lịch sử phiên bản.

---

## 2. Vòng Đời Vận Hành Tiêu Chuẩn (5 Bước)

Mọi phiên làm việc của lập trình viên và AI Agent bắt buộc tuân thủ tuần tự 5 bước:

```
[BƯỚC 1: ĐỒNG BỘ AN TOÀN] ──> [BƯỚC 2: THỰC THI WIP=1] ──> [BƯỚC 3: KIỂM TOÁN CODEBASE]
                                                                        │
[BƯỚC 5: NGHIỆM THU ĐÓNG PHIÊN] <── [BƯỚC 4: COMMIT CHUẨN HÓA] <────────┘
```

### Bước 1: Khởi Tạo Phiên & Đồng Bộ An Toàn (Safe Pull)

Mục tiêu: Đưa nhánh làm việc về trạng thái mới nhất từ remote mà không làm mất mát tệp cục bộ.

1. **Kiểm tra trạng thái vùng làm việc**:
   ```powershell
   git status -s
   ```
2. **Fetch thông tin mới nhất từ remote**:
   ```powershell
   git fetch origin
   ```
3. **Đối chiếu commit và danh sách tệp thay đổi**:
   ```powershell
   git log HEAD..origin/main --oneline
   git diff --name-status HEAD..origin/main
   ```
4. **Xử lý tệp untracked nếu có nguy cơ bị ghi đè**:
   Nếu remote có tệp mới trùng tên với tệp untracked cục bộ (ví dụ: báo cáo ngày): Tạm thời đổi tên bản cục bộ sang `<tệp>.local.bak` trước khi thực hiện pull.
5. **Thực hiện cập nhật**:
   ```powershell
   git pull origin main
   ```

---

### Bước 2: Thực Thi Tác Vụ Dưới Kỷ Luật WIP = 1

1. **Nguyên tắc duy nhất**: Tại một thời điểm, chỉ có tối đa 1 Story hoặc 1 yêu cầu ở trạng thái xử lý (`in_progress`).
2. **Cách ly ngữ cảnh (Bounded Context)**: Chỉ đọc và sửa đổi các tệp nằm trong phạm vi tác vụ được giao, không nạp thừa tài liệu vượt ngân sách token.
3. **Chuyển đổi tác vụ khẩn cấp**: Nếu có yêu cầu đột xuất ngắt ngang, bắt buộc lưu trữ (`git stash`) hoặc chuyển Story hiện tại sang `blocked`/`deferred` trong Harness trước khi nhận Story mới.

---

### Bước 3: Tra Soát & Kiểm Toán Chất Lượng Trước Khi Commit

Trước khi đưa tệp vào staging hoặc commit, kích hoạt kiểm toán tự động qua 2 kênh:

#### Kênh A: Kiểm toán Tích hợp qua Harness CLI (Khuyến nghị)
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py audit --codebase
```
Lệnh này quét đồng thời 7 tiêu chí:
- Tỷ lệ hoàn thành bằng chứng kiểm thử của các Story.
- Kỷ luật WIP = 1.
- Tính đầy đủ của nhật ký Trace.
- Số lượng tồn đọng trong Friction Backlog.
- Cổng kiểm soát ADR cho các thay đổi High-Risk.
- Tính toàn vẹn của Schema CSDL SQLite.
- **Vệ sinh Codebase & Git**: Kiểm tra lỗi cú pháp AST 100% tệp Python, phát hiện tệp conflict OneDrive và quét tệp nhị phân cấm.

#### Kênh B: Chạy Trực Tiếp Script Kiểm Toán Codebase
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/maintenance/audit_codebase.py
```
Kết quả trả về danh mục chi tiết từng tệp vi phạm và cảnh báo từ cấm thuộc Rule 06.

#### Kênh C: Chạy Toàn Bộ Unit Test Suite
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest project/tests/ -q
```
Yêu cầu bắt buộc: 100% các ca kiểm thử chính thức phải đạt trạng thái PASS.

---

### Bước 4: Đóng Gói Commit Chuẩn Hóa (Conventional Commits)

1. **Chỉ stage các tệp thuộc phạm vi tác vụ**:
   ```powershell
   git add <đường-dẫn-tệp-cụ-thể>
   ```
   Tuyệt đối không dùng `git add .` một cách thiếu kiểm soát khi thư mục còn tệp untracked.
2. **Cấu trúc thông điệp commit**:
   - `feat(<module>): <mô tả ngắn gọn tính năng mới>`
   - `fix(<module>): <mô tả ngắn gọn lỗi đã sửa>`
   - `refactor(<module>): <mô tả ngắn gọn nội dung tái cấu trúc>`
   - `docs(<module>): <mô tả ngắn gọn tài liệu bổ sung hoặc cập nhật>`
   - `chore(<module>): <mô tả công việc dọn dẹp hoặc cấu hình>`
3. **Quy chuẩn văn phong**: Dùng câu mệnh lệnh trực diện, khuyết chủ ngữ, không dùng ngôi thứ nhất ("tôi", "chúng ta").

---

### Bước 5: Đẩy Mã Nguồn & Nghiệm Thu Đóng Phiên (Harness Closure)

1. **Đẩy mã nguồn lên remote repository**:
   ```powershell
   git push origin <tên-nhánh>
   ```
2. **Lập Bảng Nghiệm Thu Đóng Phiên (Harness Closure Protocol)**:
   Mọi phản hồi kết thúc phiên bắt buộc bao gồm bảng nghiệm thu 5 tiêu chí:
   - Cấp độ rủi ro: Cấp 1 (TINY) / Cấp 2 (NORMAL) / Cấp 3 (HIGH-RISK).
   - Mã băm Commit & Tên nhánh tương ứng.
   - Trạng thái kiểm thử (Pytest & AST).
   - Trạng thái vệ sinh Codebase (Kết quả từ `audit --codebase`).
   - Bước tiếp theo hoặc vấn đề tồn đọng cần bàn giao.

---

## 3. Runbook Xử Lý Sự Cố Thường Gặp (Troubleshooting)

### Sự cố 1: Phát Hiện Tệp Xung Đột Đồng Bộ OneDrive (`-HOSTNAME`)

- **Dấu hiệu**: Lệnh `audit --codebase` báo lỗi tại mục `OneDrive Conflict Files` hoặc thư mục xuất hiện tệp có đuôi `-DESKTOP-*`, `-FPA-*`.
- **Biện pháp xử lý chuẩn**:
  1. Chạy chế độ kiểm tra trước (Dry-run):
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/maintenance/clean_onedrive_conflicts.py
     ```
  2. Thực thi xử lý promote và dọn dẹp an toàn:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/maintenance/clean_onedrive_conflicts.py --apply
     ```
  Script tự động đối chiếu thời gian sửa đổi và SHA-256; bản mới hơn sẽ được thăng hạng thành tệp chính thức và bản thừa sẽ được xóa bỏ an toàn.

### Sự cố 2: Lỗi Cú Pháp AST Khi Quét Codebase

- **Dấu hiệu**: Mục `Python AST Syntax` trả về trạng thái `FAIL` kèm đường dẫn tệp và số dòng lỗi.
- **Biện pháp xử lý chuẩn**:
  1. Mở tệp được chỉ định, kiểm tra lỗi thụt đầu dòng (IndentationError), đóng ngoặc hoặc ký tự không hợp lệ.
  2. Sửa lỗi và kiểm tra lại cục bộ:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" -c "import ast; ast.parse(open('<đường-dẫn-tệp>', encoding='utf-8').read())"
     ```

### Sự cố 3: Nhánh Cục Bộ Bị Lệch Hướng So Với Remote (`diverged`)

- **Dấu hiệu**: Git thông báo `Your branch and 'origin/main' have diverged, and have X and Y different commits each`.
- **Biện pháp xử lý chuẩn**:
  1. Xem đồ thị commit để xác định nguyên nhân:
     ```powershell
     git log --graph --oneline --left-right HEAD...origin/main
     ```
  2. Sử dụng rebase để tái sắp xếp commit cục bộ lên trên commit mới của remote:
     ```powershell
     git pull --rebase origin main
     ```
  3. Xử lý xung đột mã nguồn (nếu có) trên từng commit, kiểm tra lại test suite và hoàn tất rebase.

---

## 4. Bảng Kiểm Tra Nhanh Hàng Ngày (Daily Operational Checklist)

- [ ] Đã kéo trạng thái mới nhất từ remote trước khi bắt đầu chỉnh sửa mã nguồn.
- [ ] Không có hơn 1 Story ở trạng thái `in_progress` trong `harness.db`.
- [ ] Toàn bộ tệp Python biên dịch thành công qua `ast.parse()`.
- [ ] Lệnh `python scripts/harness_cli.py audit --codebase` đạt `health_score >= 0.85` hoặc không có lỗi nghiêm trọng.
- [ ] Bộ kiểm thử `pytest project/tests/` đạt 100% PASS.
- [ ] Không commit tệp nhị phân dữ liệu lớn hoặc tệp môi trường `.venv` vào Git.
- [ ] Báo cáo nghiệm thu có Bảng Đóng Phiên đầy đủ thông tin.
