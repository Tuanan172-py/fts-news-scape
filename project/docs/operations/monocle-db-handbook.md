# Sổ tay vận hành `monocle.db` — cho dev monitor hàng ngày

Cập nhật: 2026-08-19 · DB: `data/monocle.db` (SQLite, WAL). Đọc-only trừ mục §7.
Anh em (ngắn hơn): [db-health-queries.md](db-health-queries.md) · dashboard: `scripts/db_status.py`.

---

## 0. Ba cách chạy query
 
```powershell
cd project
$env:PYTHONUTF8 = "1"

# Tự động trỏ python venv (nếu có) hoặc python trên hệ thống:
$py = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
```
1. **Ad-hoc 1 câu (khuyên dùng)** — `scripts/dbq.py`, MẶC ĐỊNH read-only (không thể lỡ tay sửa):
   ```powershell
   & $py scripts/dbq.py "select status,count(*) n from work_items group by status"
   # Hoặc: python scripts/dbq.py "select status,count(*) n from work_items group by status"
   ```
2. **Dashboard tổng** — `scripts/db_status.py` (9 mục sức khoẻ).
3. **GUI** — mở `data/monocle.db` bằng **DB Browser for SQLite** (tốt cho query phức tạp/nhiều cột).

> 💡 Có thể kích hoạt venv trước: `.\.venv\Scripts\Activate.ps1` rồi dùng trực tiếp lệnh `python`.

---

## 1. Bản đồ bảng + khoá liên kết

**Khoá vàng:** `articles.url_title_hash` == `article_id` trong MỌI bảng handoff
(`l1_tasks`, `l1_outputs`, `work_items`, `agent_outputs`).

| Bảng | Vai trò | Cột chính |
|------|---------|-----------|
| `articles` | Bài đã scrape (Silver-facing) | `url_title_hash`(=article_id), title, source_domain, published_at, fetched_at, symbols, sentiment |
| `scraper_heartbeat` | Nhịp tim scraper | scraper_name, last_run_ts, status, consecutive_failures, cycle_count |
| `scraper_metrics` | Sản lượng mỗi cycle | ts, scraper_name, articles_fetched, articles_new, errors, duration_ms |
| `article_versions` | Change-detection (Bronze→Silver) | url_title_hash, captured_at, state, capture_status |
| `pipeline_state` | Watermark/checkpoint/lock (key-value) | key, value, updated_at |
| `work_items` | Hàng đợi bóc tách (exactly-once) | article_id, status, change_state, package_path, claimed_by |
| `agent_outputs` | Output lớp bóc tách + DoD | article_id, dod_pass, dod_reasons, output_json, created_at |
| `l1_tasks` | Trạng thái L1 code-first + agent | article_id, route, status, code_first_json |
| `l1_outputs` | Output L1 + DoD | article_id, recognized, dod_pass, dod_reasons, output_json |

Trạng thái quan trọng:
- `article_versions.state` ∈ `NEW / UNCHANGED / CONTENT_CHANGED / TEMPLATE_DRIFT / SELECTOR_BROKEN`.
- `work_items.status` ∈ `pending / claimed / done / failed / held`.
- `l1_tasks.route` ∈ `resolved / needs_agent`; `.status` ∈ `pending / done / failed`.

---

## 2. Nhịp monitor buổi sáng (checklist 60 giây)

```powershell
& $py scripts/db_status.py                       # tổng quan 9 mục
```
Nhìn nhanh 4 điều: **(1)** heartbeat `status=ok`, `cf=0`; **(2)** article hôm nay tăng; **(3)** mục 5
không kẹt `CHỜ DERIVE` lâu; **(4)** không có `SELECTOR_BROKEN/TEMPLATE_DRIFT`. Bất thường → nhảy §5.

---

## 3. Cookbook theo tình huống (copy-paste vào `dbq.py "..."`)

### 3.1 Sức khoẻ scraper
```sql
-- scraper còn chạy? lỗi liên tiếp?
select scraper_name,last_run_ts,status,consecutive_failures,cycle_count from scraper_heartbeat order by scraper_name;
-- 10 cycle gần nhất: thu / mới / lỗi
select substr(ts,1,19) ts,scraper_name,articles_fetched,articles_new,errors from scraper_metrics order by ts desc limit 10;
-- domain nào lâu rồi không có tin MỚI (new=0 nhiều cycle)
select scraper_name,max(ts) last, sum(articles_new) new_24h from scraper_metrics where ts>=datetime('now','-1 day') group by scraper_name;
```

### 3.2 Độ phủ / sản lượng
```sql
-- bài thu hôm nay theo domain
select source_domain,count(*) n,substr(max(fetched_at),1,19) last from articles where fetched_at>=date('now') group by source_domain order by n desc;
-- tổng bài theo domain (toàn thời gian)
select source_domain,count(*) n,substr(max(fetched_at),1,19) newest from articles group by source_domain order by n desc;
-- bài mới nhất bất kỳ
select substr(fetched_at,1,19) fetched,source_domain,title from articles order by fetched_at desc limit 10;
```

### 3.3 Bronze→Silver: watermark & độ trễ
```sql
-- watermark + lock scheduler
select key,substr(value,1,25) value,substr(updated_at,1,19) updated from pipeline_state;
-- domain nào có bài mới hơn watermark (=> đang CHỜ DERIVE)
select a.source_domain, substr(max(a.fetched_at),1,19) last_article,
       (select value from pipeline_state where key='silver_watermark') watermark
from articles a group by a.source_domain;
```

### 3.4 Change-detection / drift (selector hỏng)
```sql
-- phân bố state hôm nay theo domain
select source_domain,state,count(*) n from article_versions where captured_at>=date('now') group by source_domain,state order by source_domain;
-- CẢNH BÁO: selector hỏng / template đổi (cần sửa selector)
select source_domain,state,count(*) n from article_versions where state in ('SELECTOR_BROKEN','TEMPLATE_DRIFT') group by source_domain,state;
```

### 3.5 Hàng đợi bóc tách (work_items)
```sql
select status,count(*) n from work_items group by status order by n desc;
-- việc 'held' (bị chặn precondition) + lý do
select domain,change_state,count(*) n from work_items where status='held' group by domain,change_state;
-- việc 'claimed' lâu chưa xong (nghi kẹt worker)
select article_id,claimed_by,substr(claimed_at,1,19) claimed_at from work_items where status='claimed' order by claimed_at limit 20;
```

### 3.6 Lớp L1 (nhận diện entity)
```sql
select route,status,count(*) n from l1_tasks group by route,status;
select dod_pass,count(*) n from l1_outputs group by dod_pass;
-- lý do trượt DoD (sửa trúng điểm)
select article_id,substr(dod_reasons,1,120) reasons from l1_outputs where dod_pass=0 limit 20;
```

### 3.7 Lớp bóc tách (agent)
```sql
select dod_pass,count(*) n from agent_outputs group by dod_pass;
select article_id,substr(dod_reasons,1,120) reasons from agent_outputs where dod_pass=0 limit 20;
```

### 3.8 Sẵn sàng ra output cho user? (gate tối thiểu L1)
```sql
-- số bài đạt gate export, tách theo đã/chưa có Gold (cột gold_status trong <date>.xlsx)
select case when ag.article_id is null then 'L1_ONLY' else 'GOLD' end gold_status, count(*) n
from articles a
join l1_outputs l1 on l1.article_id=a.url_title_hash and l1.dod_pass=1
left join (select distinct article_id from agent_outputs where dod_pass=1) ag
       on ag.article_id=a.url_title_hash
group by 1;
```
> Lưu ý: `l1_outputs`/`agent_outputs` có thể chứa `article_id` KHÔNG tồn tại trong `articles`
> (work_item đã tạo nhưng bài chưa/không được ghi vào `articles`). Những bài đó không bao giờ
> vào được `<date>.xlsx`. Đếm rò rỉ:
```sql
select count(*) from l1_outputs l1 where l1.dod_pass=1
  and not exists (select 1 from articles a where a.url_title_hash=l1.article_id);
```

### 3.9 Truy 1 bài cụ thể (debug)
```sql
-- theo tiêu đề (LIKE)
select url_title_hash,source_domain,substr(published_at,1,19) pub,title from articles where title like '%Hòa Phát%' limit 10;
-- toàn cảnh 1 article_id qua các lớp
select 'l1' layer, status, dod_pass from l1_outputs where article_id='<ID>'
union all select 'agent', '', dod_pass from agent_outputs where article_id='<ID>'
union all select 'work_item', status, null from work_items where article_id='<ID>';
```
*(l1_outputs không có cột `status`; thay bằng `recognized` nếu cần — ví dụ minh hoạ cách gộp.)*

### 3.10 Cửa sổ thời gian (N giờ gần nhất)
```sql
select source_domain,count(*) n from articles where fetched_at>=datetime('now','-3 hours') group by source_domain;
```

---

## 4. Đọc kết quả — KHOẺ vs CẢNH BÁO

| Tín hiệu | KHOẺ | CẢNH BÁO → §5 |
|----------|------|----------------|
| heartbeat | `ok`, cf=0 | `failed`/cf>0 |
| metrics | errors=0, new>0 định kỳ | errors>0 kéo dài / new=0 nhiều giờ |
| watermark | bám `now` | tụt xa `now` |
| versions | NEW/UNCHANGED/CONTENT_CHANGED | `SELECTOR_BROKEN`/`TEMPLATE_DRIFT` |
| work_items | pending giảm khi agent chạy | `held`/`failed` nhiều, `claimed` kẹt |
| l1/agent dod_pass | phần lớn =1 | nhiều =0 (xem dod_reasons) |

---

## 5. Sự cố thường gặp → chẩn đoán → xử lý

| Triệu chứng | Query chẩn đoán | Xử lý |
|-------------|-----------------|-------|
| **Silver chưa có tin mới** | §3.3 (bài mới > watermark) | `python -m src.morninger --once derive`; hoặc giảm `rederive_interval_minutes` |
| **Scraper 1 domain đỏ** | §3.1 (status/cf) + xem `error_msg` | kiểm tra nguồn/selector; xem log `logs/` |
| **articles_new=0 kéo dài** | §3.1 (new_24h) | nguồn im thật, hay selector list hỏng → §3.4 |
| **SELECTOR_BROKEN/TEMPLATE_DRIFT** | §3.4 | sửa selector domain rồi `python scripts/rederive_from_bronze.py <domain>` |
| **work_items held nhiều** | §3.5 | thường do change_state; sửa capture rồi rederive |
| **agent/L1 dod_pass=0 nhiều** | §3.6/§3.7 (dod_reasons) | sửa output theo reason (xem agent-prompting-guide §6) |
| **<date>.xlsx rỗng dù có tin** | §3.8 (gated=0) | thiếu 1 lớp → chạy L1/agent ingest cho đủ |
| **DB locked / busy** | (lỗi khi ghi) | có tiến trình đang ghi (morninger); đọc thì mở `mode=ro` (dbq.py mặc định) |

---

## 6. Backup TRƯỚC mọi thao tác ghi (bắt buộc)

```powershell
# Backup nhất quán kể cả khi morninger đang chạy (dùng sqlite backup API):
& $py -c "import sqlite3; s=sqlite3.connect('data/monocle.db'); d=sqlite3.connect('data/monocle.backup.db'); s.backup(d); d.close(); s.close(); print('backup OK -> data/monocle.backup.db')"
```
Hoặc đơn giản: dừng morninger → `Copy-Item data\monocle.db data\monocle.backup.db` (kèm `.db-wal` nếu có).

---

## 7. Thao tác GHI hiếm gặp (cẩn trọng — backup §6 trước)

Chạy qua `dbq.py ... --allow-write`. Chỉ làm khi hiểu hệ quả.

```sql
-- (a) Requeue việc failed để agent xử lý lại:
update work_items set status='pending', error=null where status='failed';
-- (b) Gỡ kẹt việc 'claimed' quá lâu (worker chết):
update work_items set status='pending', claimed_by=null, claimed_at=null where status='claimed';
-- (c) Xoá dữ liệu STUB để chạy LLM thật (đã nói ở runbook no-LLM):
delete from l1_outputs; delete from agent_outputs; delete from l1_tasks;
-- (d) Ép derive xử lý lại toàn bộ Bronze: reset watermark
delete from pipeline_state where key in ('silver_watermark','silver_checkpoint');
```
> Sau (c)/(d) nhớ chạy lại chuỗi tương ứng (l1_route/agent_export… hoặc `--once derive`).

---

## 8. Bảo trì định kỳ

```powershell
# Kích thước & toàn vẹn (pragma → dùng one-liner, không qua dbq.py)
& $py -c "import sqlite3; print('integrity:', sqlite3.connect('data/monocle.db').execute('pragma integrity_check').fetchone()[0])"
Get-Item data\monocle.db | Select-Object Length
# Gộp WAL vào file chính (giảm .db-wal phình to) — làm khi morninger DỪNG:
& $py -c "import sqlite3;c=sqlite3.connect('data/monocle.db');c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close();print('wal truncated')"
# VACUUM (nén file) — chỉ khi morninger DỪNG, và đã backup:
& $py -c "import sqlite3;sqlite3.connect('data/monocle.db').execute('VACUUM');print('vacuumed')"
```

---

## 9. Gotchas (bẫy hay dính)

- **OneDrive**: `LastWriteTime` của file trong thư mục OneDrive KHÔNG đáng tin (sync chạm lại file cũ).
  Phán đoán "tin mới" bằng `articles.fetched_at` / `silver_watermark`, KHÔNG bằng ngày file.
- **Timezone**: log in giờ hệ thống (có thể UTC) nhưng DB đóng dấu **giờ VN (+07)**. So sánh theo giá trị
  chuỗi ISO trong DB cho nhất quán.
- **File WAL**: sẽ thấy `monocle.db-wal`, `monocle.db-shm` — bình thường. Backup phải gồm cả `.db-wal`
  (hoặc dùng sqlite backup API §6).
- **Đang chạy morninger**: nó GIỮ `lock:scheduler` (xem `pipeline_state`). Đọc song song vô tư (mode=ro);
  tránh VACUUM/checkpoint/ghi khi nó đang chạy.

---

## 10. Tra cứu nhanh (một dòng)

```powershell
& $py scripts/db_status.py                                           # tổng quan
& $py scripts/dbq.py "select status,count(*) from work_items group by status"
& $py scripts/dbq.py "select scraper_name,status,consecutive_failures from scraper_heartbeat"
& $py scripts/dbq.py "select key,substr(value,1,25),updated_at from pipeline_state"
& $py scripts/dbq.py "select dod_pass,count(*) from agent_outputs group by dod_pass"
```

## 11. Câu hỏi mở
- Chưa có cảnh báo tự động (heartbeat quá hạn, drift>0) — hiện xem thủ công.
- `dbq.py` chặn ghi theo từ khoá đầu câu; câu lệnh ghi lồng (CTE) hiếm gặp cần tự cẩn trọng.
