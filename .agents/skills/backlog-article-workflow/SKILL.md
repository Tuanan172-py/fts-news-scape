---
name: backlog-article-workflow
description: Bản đồ phân bổ dữ liệu và quy trình điều phối giải phóng bài viết tồn đọng (Backlog Article Workflow) trong hệ thống News-Scape, phục vụ các ca vận hành Conductor gom đợt và xử lý cuốn chiếu.
---

# Backlog Article Workflow Skill

> [!NOTE]
> **Tài liệu tham chiếu chuẩn cho Operator & Conductor:** Xem chi tiết hướng dẫn quản trị tại [Warehouse State & Backlog Observability Skill](../warehouse-backlog-observability/SKILL.md) và lệnh trinh sát hệ thống:
> ```powershell
> & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py backlog
> ```

---

## 1. Bản Đồ Tổng Thể Dữ Liệu Tồn Đọng (Backlog Map)

Tính đến ngày **16/10/2026**, toàn hệ thống có **31.704 bài viết** trong kho `articles`, trong đó **22.676 bài (71,5%)** đang chờ xử lý Gold (chưa qua LLM):

- **TIER 1 (Ưu tiên cao nhất - Watchlist & Vĩ mô khẩn) :** **11.367 bài (50,1%)**
- **TIER 2 & 3 (Hàng đợi nền - Tin thị trường chung)   :** **11.309 bài (49,9%)**

### Phân Bổ Theo Thời Gian & Tầng Dữ Liệu

```
                          TỔNG BÀI TỒN ĐỌNG (22.676 bài)
                                        │
        ┌───────────────────────────────┴───────────────────────────────┐
        ▼                                                               ▼
[Nhóm A: Có Ngày Đăng Hợp Lệ]                                   [Nhóm B: Khuyết Ngày Đăng]
       (17.306 bài)                                                    (5.370 bài)
        │                                                               │
        ├─ Đợt 1: Dữ liệu nóng gần nhất (T10/2026) : 3.340 bài          ├─ Thu thập từ cafef.vn: 4.800+ bài
        │         (15/10: 601, 14/10: 633, 13/10: 608...)               ├─ Thu thập từ khác:      500+ bài
        ├─ Đợt 2: Toàn Bộ Tháng 09/2026            : 7.451 bài          └─ Cào bù (sitemap reconcile):
        ├─ Đợt 3: Toàn Bộ Tháng 08/2026            : 4.477 bài             xử lý gom lô theo limit.
        └─ Đợt 4: Lịch Sử Cũ (< 08/2026)           : 1.971 bài
```

---

## 2. Bản Đồ Quy Trình Điều Phối Cuốn Chiếu (Rolling Wave Workflow)

```
[BƯỚC 1: XÁC ĐỊNH MỤC TIÊU & CHỌN CỜ NGÀY]
       │
       ├─ Xử lý ngày cụ thể: dùng --date YYYY-MM-DD
       └─ Xử lý gom toàn dải: dùng --limit N (mặc định ưu tiên Tier 1 trước)
       │
[BƯỚC 2: ĐÓNG GÓI ĐỢT (PACKING WAVE)]
       │
       ├─ Cú pháp: article_run.py --wave W<mã_đợt> [--date YYYY-MM-DD] [--limit N] --runner agy
       ├─ Hệ thống tự động phân tầng: Tier 1 (Watchlist + Vĩ mô khẩn) -> Tier 2 & 3
       └─ Sinh manifest wave JSON và các task packet (50 bài/lô, Compact JSON)
       │
[BƯỚC 3: KÍCH HOẠT AGY CONDUCOT PHÂN TÍCH (COGNITIVE ANALYZE)]
       │
       ├─ Cú pháp: article_run.py --wave W<mã_đợt> --runner agy --analyze --concurrency 1
       └─ Nếu có bài thiếu/chưa nhận diện: article_run.py --wave W<mã_đợt> --repair --runner agy --concurrency 1
       │
[BƯỚC 4: HOÀN TẤT NẠP CSDL SQLITE (INGEST MONOCLE.DB)]
       │
       ├─ Cú pháp: article_run.py --wave W<mã_đợt> --finish --force
       └─ Tự động: Bung schema đầy đủ -> l1_ingest -> agent_ingest -> ghi sổ cái token
       │
[BƯỚC 5: XUẤT BẢN FILE GIAO HÀNG EXCEL (DELIVERABLES)]
       │
       └─ Cú pháp: write_user_output.py --force (hoặc --date YYYY-MM-DD)
```

---

## 3. Thư Viện Lệnh Chuẩn Thực Thi (Runbook Commands)

Mọi lệnh chạy với venv `C:\venvs\news-scape\Scripts\python.exe` từ thư mục gốc hoặc chỉ định rõ đường dẫn:

### Kịch Bản A: Xử Lý Theo Ngày Cụ Thể (Khuyến Nghị Cho Dữ Liệu Tháng 10)
Cách xử lý gọn gàng nhất theo từng ngày giao dịch:

```powershell
# Ví dụ: Xử lý bài của ngày 2026-10-15 (601 bài)
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_OCT15 --date 2026-10-15 --runner agy
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_OCT15 --runner agy --analyze --concurrency 1
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_OCT15 --finish --force
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/write_user_output.py --date 2026-10-15 --force
```

### Kịch Bản B: Xử Lý Lô Lớn Gom Nhiều Ngày (500 bài / wave)

```powershell
# Bước 1: Đóng gói 500 bài tồn đọng (hệ thống tự ưu tiên Tier 1)
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BACKLOG500 --limit 500 --runner agy

# Bước 2: Chạy phân tích nhận thức & vòng vá (nếu có)
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BACKLOG500 --runner agy --analyze --concurrency 1
# Nếu phát hiện bài thiếu:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BACKLOG500 --repair --runner agy --concurrency 1

# Bước 3: Nạp CSDL & Giao hàng
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BACKLOG500 --finish --force
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/write_user_output.py --force
```

---

## 4. Cạm Bẫy Truy Vấn & Rào Cản Kỹ Thuật Cần Nhớ (Guardrails)

1. **Cạm bẫy chuỗi rỗng trong so sánh ngày SQLite:**
   - Trong SQLite, nếu cột `published_at = ''`, câu lệnh `WHERE substr(published_at,1,10) >= '2026-10-09'` có thể bị ảnh hưởng bởi collation hoặc logic null/empty.
   - **Bắt buộc:** Luôn bổ sung điều kiện `WHERE published_at IS NOT NULL AND published_at != '' AND ...`.
2. **Quy tắc Single-Turn Zero-Tool:**
   - Conductor chỉ kích hoạt LLM qua runner `agy` (Gemini Flash). Không cấp quyền tương tác file hay vòng lặp tool cho Worker con.
3. **Bảo toàn File Lock trên Windows/OneDrive:**
   - Luôn sử dụng `--force` khi hoàn tất để đảm bảo `DBWriter` và Staging ghi đè an toàn khi đối soát.
