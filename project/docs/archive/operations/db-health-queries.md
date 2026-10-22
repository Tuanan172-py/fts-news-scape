# Vận hành — Query DB kiểm tra nhanh trạng thái scrape/pipeline

Cập nhật: 2026-08-18 · Mục tiêu: kiểm tra sức khoẻ hệ thống bằng DB, không cần đọc log.
DB: `data/monocle.db` (SQLite, WAL). Đọc-only — các query dưới KHÔNG sửa dữ liệu.

---

## 0. Cách chạy (Windows)

Đảm bảo đứng ở thư mục `project/` và thiết lập biến môi trường UTF-8 (in tiếng Việt không lỗi):

```powershell
cd project
$env:PYTHONUTF8 = "1"

# Tự động trỏ python venv (nếu có) hoặc python trên hệ thống:
$py = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
```

Query thô có thể chạy bằng: **DB Browser for SQLite** (mở file `data/monocle.db`), hoặc `sqlite3` CLI, hoặc
`& $py -c "..."` (hoặc `python -c "..."`). Đơn giản nhất là dùng **1 lệnh dashboard** ở §1.

---

## 1. Dashboard 1 lệnh (khuyến nghị)

```powershell
& $py scripts/db_status.py                 # hôm nay (giờ VN)
& $py scripts/db_status.py --date 2026-08-18

# Hoặc nếu venv đã kích hoạt / python sẵn trên PATH:
python scripts/db_status.py
python scripts/db_status.py --date 2026-08-18
```

In 9 mục: heartbeat · sản lượng cycle · article hôm nay · watermark · **độ trễ capture↔derive** ·
change-detection (drift) · hàng đợi handoff · lớp L1 · lớp bóc tách. Đọc §3 để hiểu ý nghĩa.

---

## 2. Các query thô (chạy tay khi cần đào sâu)

Bảng chính: `articles`, `scraper_heartbeat`, `scraper_metrics`, `article_versions`,
`pipeline_state`, `work_items`, `l1_tasks`, `l1_outputs`, `agent_outputs`.

| # | Kiểm tra                   | SQL                                                                                                                           |
| - | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| a | Scraper còn sống?         | `select scraper_name,last_run_ts,status,consecutive_failures from scraper_heartbeat;`                                       |
| b | Sản lượng gần nhất     | `select ts,scraper_name,articles_fetched,articles_new,errors from scraper_metrics order by ts desc limit 10;`               |
| c | Thu bao nhiêu tin hôm nay | `select source_domain,count(*) n,max(fetched_at) last from articles where fetched_at>='2026-08-18' group by source_domain;` |
| d | Watermark Silver            | `select * from pipeline_state where key like 'silver_%';`                                                                   |
| e | Độ trễ capture↔derive   | `select source_domain,max(fetched_at) last_article from articles group by source_domain;` → so với watermark (d)          |
| f | Drift/selector hỏng        | `select source_domain,state,count(*) from article_versions where captured_at>='2026-08-18' group by source_domain,state;`   |
| g | Hàng đợi agent           | `select status,count(*) from work_items group by status;`                                                                   |
| h | L1 xong chưa               | `select status,count(*) from l1_tasks group by status; select dod_pass,count(*) from l1_outputs group by dod_pass;`         |
| i | Bóc tách xong chưa       | `select dod_pass,count(*) from agent_outputs group by dod_pass;`                                                            |

Ví dụ chạy 1 query nhanh (dùng dbq.py hoặc python -c):

```powershell
# Cách 1 (khuyên dùng — không cần lo escape dấu nháy):
& $py scripts/dbq.py "select scraper_name,status,last_run_ts from scraper_heartbeat"

# Cách 2 (one-liner trực tiếp):
& $py -c "import sqlite3; [print(r) for r in sqlite3.connect('data/monocle.db').execute('select scraper_name,status,last_run_ts from scraper_heartbeat')]"
```

(Mẹo: query nhiều/phức tạp → dùng `scripts/dbq.py` hoặc mở bằng **DB Browser for SQLite** cho dễ.)

---

## 3. Đọc kết quả — khoẻ vs cảnh báo

| Mục                                       | KHOẺ                                               | CẢNH BÁO → làm gì                                                                                       |
| ------------------------------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **heartbeat**                        | `status=ok`, `consecutive_failures=0`           | `failed` / cf>0 → scraper lỗi, xem `error_msg` + log                                                   |
| **metrics**                          | `errors=0`, `articles_new`>0 định kỳ         | `errors>0` liên tục hoặc `new=0` dài → nguồn/selector vấn đề                                    |
| **article hôm nay**                 | tăng dần theo domain                              | 0 tin/nhiều giờ → capture không chạy hoặc nguồn im                                                    |
| **watermark**                        | bám sát`now`                                    | tụt xa`now` → `derive` không chạy (§4)                                                              |
| **độ trễ** (`db_status` mục 5) | `đã silver`                                     | `CHỜ DERIVE` = tin đã thu nhưng chưa lên Silver → chờ tick derive hoặc force (§4)                |
| **change-detection**                 | phần lớn`NEW`/`UNCHANGED`/`CONTENT_CHANGED` | xuất hiện`SELECTOR_BROKEN`/`TEMPLATE_DRIFT` → selector hỏng, cần sửa rồi `rederive_from_bronze` |
| **work_items**                       | `pending` giảm dần khi agent chạy              | `held` nhiều → schema/selector; `failed` → xem DoD                                                    |
| **l1_outputs/agent_outputs**         | `dod_pass=1` chiếm đa số                       | nhiều`dod_pass=0` → output agent chưa đạt DoD                                                         |

---

## 4. Tình huống hay gặp: "tin mới chưa lên Silver"

**Bình thường, không phải lỗi.** `capture` (mỗi 15′) và `derive` (mỗi 30′) chạy **tách nhịp**:
tin mới vào `articles`/Bronze ngay, nhưng Silver chỉ cập nhật ở **tick derive kế tiếp** (trễ ≤30′).

Chẩn đoán: `db_status` **mục 5** báo `CHỜ DERIVE` cho domain có `last_article > watermark`.

Xử lý:

```powershell
& $py -m src.morninger --once derive        # ép derive ngay → Silver bắt kịp
```

Muốn Silver bám sát hơn: giảm `rederive_interval_minutes` trong `config/settings.yaml`.

> ⚠️ KHÔNG dùng `LastWriteTime` của file trong thư mục OneDrive để phán đoán "tin mới" — OneDrive
> sync hay chạm lại file cũ. Tín hiệu chuẩn là **`articles.fetched_at`** và **`silver_watermark`**.

---

## 5. Đếm file trên đĩa (bổ trợ, PowerShell)

```powershell
# Silver theo domain (ngày mới nhất):
foreach($d in 'cafef.vn','vietstock.vn','vneconomy.vn'){
  $days = Get-ChildItem "data\silver\$d" -Directory -EA SilentlyContinue | Sort-Object Name | Select-Object -Last 3
  "$d -> $((($days).Name) -join ', ')"
}
# Tổng work_packages chờ handoff:
(Get-ChildItem data\work_packages -Recurse -Filter *.json | Measure-Object).Count
```

---

## 6. Câu hỏi mở

- Chưa có ngưỡng cảnh báo tự động (vd heartbeat quá X phút) — hiện phải xem thủ công qua `db_status.py`.
- `db_status.py` là read-only; nếu cần export JSON cho dashboard ngoài, bổ sung cờ `--json` sau.
