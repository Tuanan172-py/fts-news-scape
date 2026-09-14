# Hướng Dẫn Vận Hành Quy Trình End-to-End (Operations Playbook)

> **Dành cho:** Người vận hành hệ thống, Chuyên viên dữ liệu (Users) và Quản trị viên (Dev/Ops).  
> **Cập nhật:** 2026-09-14 (Phiên bản H2–H5 chuẩn hóa: Lớp L1 Tinh gọn & Gold v2-lean).  
> **Mục tiêu:** Cung cấp hướng dẫn trực quan, chuẩn xác từng bước từ lúc dữ liệu thô được cào về, đi qua các lớp bóc tách thông minh (Code-First + Subagents LLM), cho đến khi xuất bản báo cáo Excel cá nhân hóa tới tay người dùng cuối.

---

## 1. Bản Đồ Tổng Thể Luồng Dữ Liệu End-to-End

```
                           [1. NGUỒN TIN BÁO CHÍ (6 Nguồn)]
               (CafeF, Vietstock, VnEconomy, Báo Đầu Tư, ĐTCK, TBTCVN)
                                        │
                                        ▼ (Scripts Automate / 15 phút)
                           [2. TẦNG BRONZE (Raw Storage)]
                     raw_html/ + .meta.json (Bất biến, SHA-256)
                                        │
                                        ▼ (Chuẩn hóa DOM & SimHash)
                           [3. TẦNG SILVER (Sạch & Cô Đọng)]
                       Tinh lọc thành các đoạn văn thuần túy (<p>)
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼ (Tất định 0 token)                          ▼ (Tin phức tạp)
         [4A. L1 CODE-FIRST]                           [4B. SUBAGENTS L1]
       Khớp mã & thực thể từ điển                     Tra soát & Bổ sung thực thể
       (Chiếm ~60% tổng lượng tin)                    (Gom lô 25 bài, Flash Model)
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        ▼
                           [5. DATABASE L1 OUTPUTS]
                       monocle.db (l1_outputs.dod_pass=1)
                                        │
               ┌────────────────────────┴────────────────────────┐
               ▼ (Không ai đăng ký)                              ▼ (Khớp Watchlist Users)
       [Trạng thái L1_ONLY]                           [6. CỔNG XUẤT TÁC VỤ GOLD]
      (Lưu trữ, tiết kiệm 45% token)                 Subscriber-Gated + 3-Pass Pruner
                                                     (<= 2.200 chars, nhúng L1 entities)
                                                                 │
                                                                 ▼ (Gom lô 5 bài)
                                                      [7. SUBAGENTS GOLD ANALYST]
                                                     Phân tích tác động, tóm tắt,
                                                     citations >= 20 chars, schema v2-lean
                                                                 │
                                                                 ▼ (Quality Ingest DoD)
                                                      [8. DATABASE GOLD OUTPUTS]
                                                     monocle.db (agent_outputs.dod_pass=1)
                                                                 │
                                                                 ▼
                                                  [9. BÀN GIAO CHO NGƯỜI DÙNG]
                                             users/output/<User>/<YYYY-MM-DD>.xlsx
```

---

## 2. Quy Chuẩn Môi Trường Thực Thi (Mục Tiêu Bất Biến)

Môi trường thực thi của dự án được cách ly hoàn toàn để chống lock file trên OneDrive/SharePoint:
- **Python Virtual Environment**: BẮT BUỘC dùng venv ngoài OneDrive tại `C:\venvs\news-scape\Scripts\python.exe`.
- **Cơ sở dữ liệu SQLite Runtime**: Nằm tại thư mục cục bộ `C:\data\news-scape\monocle.db`.
- **Thư mục chạy lệnh**: Luôn mở terminal tại thư mục `project/`.

---

## 3. Quy Trình Vận Hành 5 Bước Chuẩn Hóa

### Bước 1: Quét Dữ Liệu & Nạp L1 Code-First Tự Động (0 Token)
Chạy script để tự động nhận diện tất định ~60% lượng bài viết thông qua từ điển danh mục:
```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py --code-first
```
*Kết quả:* Các bài viết chứa mã CP tường minh (như `HPG`, `VHM`, `FPT`) được nạp thẳng vào `monocle.db` với provenance `code_first/deterministic`.

---

### Bước 2: Phát Lô Tác Vụ L1 Cho Các Bài Còn Lại (`needs_agent`)
Định tuyến các bài viết phức tạp, ẩn ý hoặc cần tra soát bổ sung thành các mini-batch 25 bài/lô:
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_route.py --review missed
```
*Kết quả:* Các gói công việc JSON được tạo ra trong `data/agent_tasks/l1/` (`l1_batch_01.task.json`, `l1_batch_02.task.json`...).

---

### Bước 3: Kích Hoạt Subagent L1 Bóc Tách Thực Thể (Theo Wave Có Kiểm Soát)
Điều phối Subagent thông qua AI coding assistant (Antigravity):
- **Nguyên tắc phân đợt (Controlled Wave)**: Chạy tối đa **2–3 batches/đợt** (50–75 bài) để tránh chạm trần rate limit.
- **Mẫu lệnh prompt cho Subagent L1**:
  > "Hãy đọc file `project/data/agent_tasks/l1/l1_batch_XX.task.json` bằng tool `view_file` DUY NHẤT 1 lần. Bóc tách thực thể theo Ontology 10 Miền. Đảm bảo exact substring cho surface và citations, tuân thủ bảng Entity ID chuẩn trong skill `l1-entity-matcher`. Ghi mảng JSON kết quả trực tiếp vào `project/data/agent_outputs_l1/l1_batch_XX.output.json`."

---

### Bước 4: Nghiệm Thu DoD L1 Ingest & Dọn Dẹp Archive
Sau khi Subagent ghi xong file output, chạy lệnh nạp dữ liệu:
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py data/agent_outputs_l1/l1_batch_XX.output.json
```
*Kết quả:*
- Kiểm định 100% tiêu chuẩn Definition-of-Done (DoD).
- Dữ liệu đạt chuẩn nạp vào bảng `l1_outputs` trong `monocle.db`.
- Task packets đã hoàn tất được tự động di dời vào `data/agent_tasks/l1/archive/YYYYMMDD/` để giữ thư mục làm việc luôn sạch sẽ.

---

### Bước 5: Đóng Gói Tác Vụ Gold & Phân Phối Deliverable Người Dùng
Khi lớp L1 đã hoàn tất, tiến hành xuất các bài viết phục vụ người dùng cuối:

1. **Xuất tác vụ Gold theo Watchlist người dùng (Subscriber-Gated)**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/agent_export.py --date today --require-l1 --subscriber-only
   ```
2. **Kích hoạt Subagent Gold (`gold_financial_analyst`)**:
   - Xử lý các lô `batch_XX.task.json` (5 bài/lô) theo chuẩn schema phẳng 7 trường `agent-output-v2-lean`.
3. **Nạp kết quả Gold & Xuất bản file Excel cho người dùng**:
   ```powershell
   # Nạp kết quả Gold vào database:
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/agent_ingest.py data/agent_outputs

   # Xuất báo cáo Excel cá nhân hóa cho từng user:
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date all
   ```
*Sản phẩm cuối cùng:* Các tệp Excel được tạo tự động tại `users/output/<user>/<YYYY-MM-DD>.xlsx` (Ví dụ: `users/output/AnPT/2026-09-14.xlsx`), phục vụ trực tiếp cho công tác phân tích đầu tư.

---

## 4. Các Bẫy Thường Gặp & Cách Khắc Phục (Troubleshooting Cheatsheet)

| Hiện tượng | Nguyên nhân gốc | Hướng xử lý ngay |
| :--- | :--- | :--- |
| **Lỗi 429 `RESOURCE_EXHAUSTED`** | Chạy quá nhiều subagents cùng một lúc vượt hạn mức TPM/RPM | Áp dụng **Controlled Wave**: Giới hạn tối đa 2-3 batches L1 hoặc 2 batches Gold mỗi đợt. |
| **Subagent chạy chậm, tốn nhiều token** | Subagent gọi tool tìm kiếm (`grep_search`, `find_by_name`) quét từ điển ngoài | Nhắc lại quy tắc **Strict 2-I/O**: Cấm gọi tool search, chỉ đọc task 1 lần và ghi output 1 lần. |
| **DoD Fail: `khong co trong danh muc`** | Subagent tự sinh Entity ID không có trong Master Catalog (như `MACRO_GEO:IRAN`) | Tra cứu bảng chuẩn trong skill `l1-entity-matcher`. Thực thể ngoài Top 8 phải để `in_list: false`, `entity_id: null`. |
| **DoD Fail: `schema_invalid: type/method`** | Output thiếu trường hoặc gán sai `type: "INDUSTRY"` chung chung | Đảm bảo `type` là 1 trong 12 Enum chuẩn (`INDUSTRY_GICS1/2/3`, `TICKER`, `MACRO_GEO`...) và có `method: "semantic"`. |
| **DoD Fail: `không phải chuỗi con của title`** | `surface` hoặc `source_span` bị sửa từ, bỏ dấu hoặc lỗi Unicode mojibake | Luôn sao chép nguyên văn (exact substring) từ tiêu đề; đảm bảo lưu file định dạng UTF-8. |
