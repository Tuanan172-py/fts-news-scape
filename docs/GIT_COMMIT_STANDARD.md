# GIT_COMMIT_STANDARD.md — Chuẩn Mực Commit Trong Ngành & Quy Tắc Tiết Lộ Lũy Tiến

Mục đích: Tài liệu tham chiếu độc lập định nghĩa chuẩn mực commit mã nguồn (dựa trên Conventional Commits 1.0.0 và Semantic Versioning) áp dụng cho toàn bộ dự án News-Scape trong khung quản trị Harness.

> [!NOTE]
> **Nguyên tắc Tiết lộ Lũy tiến (Progressive Disclosure):**
> Tài liệu này là tệp tham chiếu tĩnh (Tầng 2). Lập trình viên và Agent không cần đọc lại tệp này trong các ca làm việc thường nhật. Tầng công cụ CLI (`harness_cli.py story complete --commit` hoặc `harness_cli.py git template`) chịu trách nhiệm tự động sinh cú pháp chuẩn với chi phí 0 token. Chỉ mở tệp này khi cần đào sâu, giải quyết tranh luận hoặc soạn thảo Release Notes.

---

## 1. Cấu Trúc Thông Điệp Commit Chuẩn (Conventional Commits 1.0.0)

Mỗi commit gồm tối đa 3 khối, cách nhau bởi một dòng trống:

```text
<type>(<scope>): <subject> (US-XXX)

[body: giải thích bối cảnh, TẠI SAO phải thay đổi, các đánh đổi kỹ thuật]

[footer: breaking changes, liên kết ADR hoặc Issue tham chiếu]
```

### A. Dòng Tiêu Đề (Header Line) — Bắt Buộc
- **Độ dài tối đa**: 72 ký tự (lý tưởng: 50–60 ký tự).
- **Quy cách**: Chữ thường toàn bộ cho `<type>` và `<scope>`. Chữ cái đầu của `<subject>` viết thường, **tuyệt đối không có dấu chấm `.` ở cuối dòng**.
- **Mã Harness**: Bắt buộc mang mã `(US-XXX)` ở cuối dòng tiêu đề đối với mọi commit thuộc Story Normal/High-Risk.

### B. Thân Commit (Body) — Tùy Chọn Nhưng Khuyến Nghị Cho Thay Đổi Lớn
- Trả lời trực tiếp câu hỏi: **TẠI SAO** (Why) lại có thay đổi này và tác động kiến trúc ra sao. Không diễn giải lại việc file nào được sửa vì `git diff` đã thể hiện điều đó.
- Xuống dòng ở độ dài khoảng 72–80 ký tự.

### C. Chân Commit (Footer) — Cho Thay Đổi Phá Vỡ Hoặc Quyết Định
- Đánh dấu thay đổi phá vỡ: `BREAKING CHANGE: <mô tả chi tiết cách di chuyển/ảnh hưởng>`
- Tham chiếu quyết định: `Refs: ADR-NNNN`

---

## 2. Ma Trận Phân Định Ranh Giới (Commit Type Taxonomy)

| Mã Loại | Tên Nghiệp Vụ | Tiêu Chuẩn Thực Tế | Ví Dụ Điển Hình |
| :--- | :--- | :--- | :--- |
| **`feat`** | Tính năng mới | Thêm một năng lực nghiệp vụ mới mà người dùng hoặc consumer có thể sử dụng được. | `feat(export): add intent columns to deliverable Excel (US-002)` |
| **`fix`** | Sửa lỗi sai lệch | Khắc phục một khiếm khuyết khiến hành vi thực tế chạy sai so với đặc tả đã cam kết. | `fix(article_pack): check content_text column existence (US-025)` |
| **`refactor`** | Tái cấu trúc | Sắp xếp lại mã nguồn nội bộ mà **không đổi hành vi bên ngoài** (không thêm tính năng, không sửa bug). | `refactor(l1_router): extract regex patterns to compile time constant (US-010)` |
| **`perf`** | Tối ưu hiệu năng | Nâng cao tốc độ thực thi, giảm tiêu thụ RAM, token LLM hoặc I/O mà giữ nguyên 100% logic. | `perf(tokenizer): use morphological compact array for tokens (US-009)` |
| **`docs`** | Tài liệu | Chỉ sửa đổi tài liệu Markdown, docstrings, quy tắc, hướng dẫn sử dụng. | `docs(governance): add ADR 0010 Article Lane unified architecture (US-027)` |
| **`test`** | Kiểm thử | Thêm mới, cập nhật hoặc sửa đổi bộ kiểm thử đơn vị, integration tests, fixtures. | `test(harness_cli): add test cases for git lifecycle and clean status (US-030)` |
| **`chore`** | Bảo trì & Hạ tầng | Cập nhật cấu hình phụ trợ, file ignore, migration CSDL nội bộ, dọn dẹp vệ sinh tệp. | `chore(hygiene): clean dangling worktree and update .gitignore` |

---

## 3. Quy Chuẩn Ngữ Văn (Grammar & Style Rules)

1. **Thể mệnh lệnh trực diện (Imperative Mood)**:
   - Viết như một mệnh lệnh hành động trực tiếp.
   - **Đúng**: `add`, `fix`, `refactor`, `remove`, `update`, `optimize`.
   - **Sai**: `added`, `fixes`, `fixing`, `refactored`, `improving`.
2. **Không dùng từ mơ hồ, sáo ngữ**:
   - Tránh: `update various files`, `fix minor bug`, `wip`, `clean code`.
   - Phải ghi rõ thực thể hoặc module bị tác động: `fix(dedup): prevent false-positive url merge on trailing slash`.
3. **Phạm vi (Scope) chuẩn của News-Scape**:
   - `core`: Module hạ tầng dùng chung (`src/core/`, staging, stdio).
   - `bronze`: Tầng cào tin và lưu trữ thô.
   - `silver`: Tầng bóc tách DOM và chuẩn hóa văn bản.
   - `gold` / `article-lane`: Tầng phân tích ngữ nghĩa LLM và trích dẫn.
   - `export` / `delivery`: Tầng phân phối dữ liệu người dùng (`.xlsx`).
   - `harness`: Khung quản trị, CLI, tracking, kiểm thử.
   - `governance`: Rules, ADRs, chính sách hệ thống.

---

## 4. Công Cụ Hỗ Trợ 0-Token Trong Harness CLI

Để sinh nhanh mẫu commit chuẩn mà không tốn token LLM, sử dụng lệnh tích hợp sẵn:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git template --type feat --scope core --story US-030 --title "integrate git lifecycle"
```

Khi nghiệm thu Story qua Harness, cờ `--commit` sẽ tự động tuân thủ 100% chuẩn mực này:
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py story complete --id US-XXX --run-verify --commit
```
