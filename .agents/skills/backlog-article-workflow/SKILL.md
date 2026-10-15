---
name: backlog-article-workflow
description: Bản đồ phân bổ dữ liệu và quy trình điều phối giải phóng bài viết tồn đọng (Backlog Article Workflow) trong hệ thống News-Scape, phục vụ các ca vận hành Conductor gom đợt và xử lý cuốn chiếu.
---

# Backlog Article Workflow Skill

> **Mục đích:** Cung cấp bản đồ phân bổ chi tiết của **15.924 bài đăng tồn đọng** trước ngày 09/10/2026 trong kho CSDL `monocle.db`, kèm chiến lược phân kỳ xử lý cuốn chiếu (Rolling Waves), cú pháp chuẩn xác khi chạy AGY Conductor và các cạm bẫy truy vấn SQLite cần phòng tránh.

---

## 1. Bản Đồ Tổng Thể Dữ Liệu Tồn Đọng (Backlog Map)

Tính đến ngày **09/10/2026**, toàn hệ thống có **16.197 bài** trong bảng `work_items` mang trạng thái `status = 'pending'`. Trong đó:
- **Hôm nay (2026-10-09):** ~273 bài (tiến trình vận hành hằng ngày).
- **Tồn đọng trước hôm nay (< 2026-10-09):** **15.924 bài**.

### Phân Bổ Theo Thời Gian & Tầng Dữ Liệu

```
                      TỔNG BÀI TỒN ĐỌNG TRƯỚC 09/10 (15.924 bài)
                                     │
      ┌──────────────────────────────┴──────────────────────────────┐
      ▼                                                             ▼
[Nhóm A: Có Ngày Đăng Hợp Lệ]                                 [Nhóm B: Khuyết Ngày Đăng]
     (12.565 bài)                                                  (2.785 bài)
      │                                                             │
      ├─ Đợt 1: Tuần Gần Nhất (06/10 → 08/10) :   739 bài           ├─ Thu thập từ cafef.vn: 2.404 bài
      ├─ Đợt 2: Đầu Tháng 10 (01/10 → 05/10)  : 1.609 bài           ├─ Thu thập từ tinnhanh:   355 bài
      ├─ Đợt 3: Toàn Bộ Tháng 09/2026         : 7.425 bài           ├─ Thu thập từ khác:        26 bài
      ├─ Đợt 4: Tháng 08/2026                 : 2.223 bài           └─ Cào bù (fetched_at 10/2026):
      └─ Đợt 5: Lịch Sử Cũ (05/2017 → 07/2026):   569 bài              xử lý gom lô theo limit.
```

---

## 2. Chi Tiết Phân Bổ Từng Giai Đoạn

### Giai Đoạn 1: Tuần Gần Nhất Tháng 10/2026 (739 bài) — *Ưu tiên số 1*
Dữ liệu nóng, độ tươi cao, sát phiên giao dịch hiện tại:
- **2026-10-08:** **123 bài**
- **2026-10-07:** **143 bài**
- **2026-10-06:** **473 bài**

### Giai Đoạn 2: Đầu Tháng 10/2026 (1.609 bài) — *Ưu tiên số 2*
- **2026-10-05:** **323 bài**
- **2026-10-04:** **107 bài** (Cuối tuần)
- **2026-10-03:** **38 bài**
- **2026-10-02:** **490 bài**
- **2026-10-01:** **651 bài**

### Giai Đoạn 3: Toàn Bộ Tháng 09/2026 (7.425 bài) — *Ưu tiên số 3*
- **Cuối tháng (25/09 → 30/09):** 1.984 bài *(30/09: 599, 29/09: 575, 28/09: 443...)*
- **Giữa tháng (14/09 → 24/09):** 2.417 bài *(16/09: 476, 17/09: 449, 14/09: 368...)*
- **Đầu tháng (01/09 → 13/09):** 3.024 bài *(10/09: 443, 07/09: 429, 09/09: 413...)*

### Giai Đoạn 4: Tháng 08/2026 & Dữ Liệu Lịch Sử (2.792 bài)
- **Tháng 08/2026:** 2.223 bài
- **Từ 05/2017 đến 07/2026:** 569 bài

### Giai Đoạn 5: Nhóm Khuyết Ngày Đăng (2.785 bài)
Các bài viết được cào bù (sitemap reconcile) không bóc tách được `published_at` từ HTML nguồn (nhưng có `fetched_at` trong tháng 10/2026). Khi chạy `article_run.py` không kèm `--date`, hệ thống sẽ tự động quét các bài này theo thứ tự ưu tiên Tiers.

---

## 3. Bản Đồ Quy Trình Điều Phối Cuốn Chiếu (Rolling Wave Workflow)

```
[BƯỚC 1: XÁC ĐỊNH MỤC TIÊU & CHỌN CỜ NGÀY]
       │
       ├─ Xử lý ngày cụ thể: dùng --date YYYY-MM-DD
       └─ Xử lý gom toàn dải: dùng --limit N kèm file loại trừ ngày hiện tại
       │
[BƯỚC 2: TẠO FILE LOẠI TRỪ NGÀY HIỆN TẠI (NẾU CHẠY KHÔNG CÓ --date)]
       │
       ├─ BẮT BUỘC: a.published_at IS NOT NULL AND a.published_at != '' AND a.published_at >= '2026-10-09'
       └─ CẤM: substr(published_at,1,10) >= '2026-10-09' đơn thuần (sẽ nuốt cả chuỗi rỗng '')
       │
[BƯỚC 3: ĐÓNG GÓI ĐỢT (PACKING WAVE)]
       │
       ├─ Cú pháp: article_run.py --wave W<mã_đợt> [--date YYYY-MM-DD] [--limit N] --runner agy
       ├─ Hệ thống tự động phân tầng: Tier 1 (Watchlist + Vĩ mô khẩn) -> Tier 2 & 3
       └─ Sinh manifest wave JSON và các task packet (50 bài/lô, Compact JSON)
       │
[BƯỚC 4: KÍCH HOẠT AGY CONDUCOT PHÂN TÍCH (COGNITIVE ANALYZE)]
       │
       ├─ Cú pháp: article_run.py --wave W<mã_đợt> --runner agy --analyze --concurrency 1
       └─ Nếu có bài thiếu/chưa nhận diện: article_run.py --wave W<mã_đợt> --repair --runner agy --concurrency 1
       │
[BƯỚC 5: HOÀN TẤT NẠP CSDL SQLITE (INGEST MONOCLE.DB)]
       │
       ├─ Cú pháp: article_run.py --wave W<mã_đợt> --finish --force
       └─ Tự động: Bung schema đầy đủ -> l1_ingest -> agent_ingest -> ghi sổ cái token
       │
[BƯỚC 6: XUẤT BẢN FILE GIAO HÀNG EXCEL (DELIVERABLES)]
       │
       └─ Cú pháp: write_user_output.py --force (hoặc --date YYYY-MM-DD)
```

---

## 4. Thư Viện Lệnh Chuẩn Thực Thi (Runbook Commands)

Mọi lệnh chạy với venv `C:\venvs\news-scape\Scripts\python.exe` từ thư mục gốc hoặc chỉ định rõ đường dẫn:

### Kịch Bản A: Xử Lý Theo Ngày Cụ Thể (Khuyến Nghị Cao Nhất)
Đây là cách an toàn và gọn gàng nhất, không cần file loại trừ:

```powershell
# Ví dụ: Xử lý 123 bài của ngày 2026-10-08
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W1009_OCT08 --date 2026-10-08 --limit 200 --runner agy
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W1009_OCT08 --runner agy --analyze --concurrency 1
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W1009_OCT08 --finish --force
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/write_user_output.py --date 2026-10-08 --force
```

### Kịch Bản B: Xử Lý Lô Lớn Gom Nhiều Ngày (500 bài)

**Bước 1: Tạo file loại trừ chuẩn (Chỉ loại trừ bài hôm nay 09/10/2026):**
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" -c "import sqlite3, pathlib; conn = sqlite3.connect('file:C:/data/news-scape/monocle.db?mode=ro', uri=True); ids = [r[0] for r in conn.execute(\"SELECT url_title_hash FROM articles WHERE published_at IS NOT NULL AND published_at != '' AND substr(published_at,1,10) >= '2026-10-09'\").fetchall()]; p = pathlib.Path('C:/data/news-scape/agent_tasks/article/exclude_current.txt'); p.write_text('\n'.join(ids), encoding='utf-8'); print('Excluded:', len(ids))"
```

**Bước 2: Đóng gói 500 bài tồn đọng:**
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W<mã_đợt> --limit 500 --exclude-file C:/data/news-scape/agent_tasks/article/exclude_current.txt --runner agy
```

**Bước 3: Chạy phân tích nhận thức & vòng vá (nếu có):**
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W<mã_đợt> --runner agy --analyze --concurrency 1
# Nếu phát hiện bài thiếu:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W<mã_đợt> --repair --runner agy --concurrency 1
```

**Bước 4: Nạp CSDL & Giao hàng:**
```powershell
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W<mã_đợt> --finish --force
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/write_user_output.py --force
```

---

## 5. Cạm Bẫy Truy Vấn & Rào Cản Kỹ Thuật Cần Nhớ (Guardrails)

1. **Cạm bẫy chuỗi rỗng trong so sánh ngày SQLite:**
   - Trong SQLite, nếu cột `published_at = ''`, câu lệnh `WHERE substr(published_at,1,10) >= '2026-10-09'` có thể bị ảnh hưởng bởi collation hoặc logic null/empty.
   - **Bắt buộc**: Luôn bổ sung điều kiện `WHERE published_at IS NOT NULL AND published_at != '' AND ...`.
2. **Quy tắc Single-Turn Zero-Tool:**
   - Conductor chỉ kích hoạt LLM qua runner `agy` (Gemini Flash). Không cấp quyền tương tác file hay vòng lặp tool cho Worker con.
3. **Bảo toàn File Lock trên Windows/OneDrive:**
   - Luôn sử dụng `--force` khi hoàn tất để đảm bảo `DBWriter` và Staging ghi đè an toàn khi đối soát.
