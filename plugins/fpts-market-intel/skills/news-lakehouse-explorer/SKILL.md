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

**Các bảng có sẵn:**
- `{articles}`: OBT Parquet nguyên gốc.
- `articles`: OBT kèm cột dẫn xuất `pub_date` (DATE), `story_key` (tiêu đề chuẩn hoá, gộp bài trùng giữa các báo), `sent_score` (1 / 0 / -1), `is_hot` (tin `urgent`/`today`).
- `article_entities`: dạng dài `article_id, entity_id, kind`, hợp nhất cột `entities` và `symbols`. `kind` gồm `TICKER`, `IND_GICS1/2/3`, `MACRO_THEME`, `MACRO_GEO`, `ASSET_CLASS`, `INSTITUTION`, `INDEX`, `EXCHANGE`. Tra mã: `lookup --text "<chuỗi>"`.

**Các mẫu SQL hữu ích:**
1. **Top cổ phiếu được nhắc đến nhiều nhất (theo thực thể, không chỉ cột `symbols`):**
   ```sql
   SELECT entity_id, count(*) AS n_articles
   FROM article_entities
   WHERE kind = 'TICKER'
   GROUP BY 1 ORDER BY n_articles DESC LIMIT 10
   ```

2. **Thống kê số lượng bài theo tên miền nguồn tin:**
   ```sql
   SELECT source_domain, count(*) as total, count(CASE WHEN sentiment = 'positive' THEN 1 END) as pos_count
   FROM {articles}
   GROUP BY source_domain
   ORDER BY total DESC
   ```

3. **Số story và số nguồn theo ngày của một mã:**
   ```sql
   SELECT a.pub_date, count(*) AS n_articles, count(DISTINCT a.story_key) AS n_stories,
          count(DISTINCT a.source_domain) AS n_sources, round(avg(a.sent_score), 3) AS net_sent
   FROM articles a JOIN article_entities e USING (article_id)
   WHERE e.entity_id = 'TICKER:HPG'
   GROUP BY 1 ORDER BY 1
   ```

**Các lệnh lens dựng sẵn** (trả JSON): `timeline`, `window`, `buzz`, `pulse`, `themes`, `cooccur`, `brief`, `lookup`, `themes-list`. Xem `python "%USERPROFILE%\.gemini\config\plugins\fpts-market-intel\tools\lakehouse_client.py" <lệnh> --help`.
