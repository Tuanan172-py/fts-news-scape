---
name: news-lakehouse-explorer
description: Kiểm toán độ tươi dữ liệu Lakehouse (_manifest/latest.json) và thực thi các câu lệnh SQL DuckDB tùy biến.
---

# Kỹ Năng Khám Phá & Kiểm Toán Hồ Dữ Liệu (News Lakehouse Explorer)

Kỹ năng này giúp chuyên viên phân tích hoặc kỹ sư dữ liệu kiểm tra tình trạng đồng bộ, đo lường độ tươi của hồ dữ liệu cục bộ và thực thi các câu lệnh truy vấn phân tích (EDA) nâng cao bằng DuckDB.

---

## 1. Khi Nào Kích Hoạt Kỹ Năng Này
- Chuyên viên hỏi về trạng thái dữ liệu: *"Dữ liệu tin tức hôm nay đã cập nhật chưa?", "Độ tươi dữ liệu Lakehouse thế nào?", "Tổng số bài viết hiện có là bao nhiêu?"*.
- Chuyên viên muốn chạy truy vấn phân tích tùy biến: *"Đếm top 10 cổ phiếu được nhắc đến nhiều nhất", "Thống kê số lượng bài theo từng nguồn báo"*.

---

## 2. Quy Trình Thực Thi (Execution Protocol)

### A. Kiểm Tra Độ Tươi & Trạng Thái Đồng Bộ (Status Check)
Chạy lệnh kiểm tra con trỏ nguyên tử `_manifest/latest.json`:
```powershell
python "%USERPROFILE%\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py" status
```
- Đọc thông tin: `latest_day`, `total_partitions`, `total_unique_articles`, `is_stale`.
- Nếu `is_stale = true` (dữ liệu cũ hơn 26 giờ): Cảnh báo người dùng kiểm tra trạng thái đồng bộ OneDrive trên khay hệ thống.

### B. Chạy Truy Vấn SQL DuckDB Tùy Biến
Chuyên viên có thể yêu cầu truy vấn bất kỳ trên bảng hợp nhất `{articles}`:
```powershell
python "%USERPROFILE%\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py" query --sql "<CÂU_SQL_AN_TOÀN>" --json
```

**Các mẫu SQL hữu ích:**
1. **Top cổ phiếu được nhắc đến nhiều nhất:**
   ```sql
   WITH unnested AS (
       SELECT unnest(symbols) as sym 
       FROM {articles} 
       WHERE len(symbols) > 0
   ) 
   SELECT sym, count(*) as count 
   FROM unnested 
   GROUP BY sym 
   ORDER BY count DESC LIMIT 10
   ```

2. **Thống kê số lượng bài theo tên miền nguồn tin:**
   ```sql
   SELECT source_domain, count(*) as total, count(CASE WHEN sentiment = 'positive' THEN 1 END) as pos_count
   FROM {articles}
   GROUP BY source_domain
   ORDER BY total DESC
   ```
