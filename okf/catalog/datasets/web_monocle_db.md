---
type: SQLite Database
title: Web Monocle DB
description: SQLite vận hành ở <DATA_ROOT>/monocle.db — 20 bảng phủ ingestion, sổ phát hiện URL, change-detection, Article Lane, bảng phái sinh và trạng thái điều phối.
resource: "<DATA_ROOT>/monocle.db"
tags: [database, sqlite, news-scape, wal]
status: stable
generated:
  at: 2026-09-07T00:00:00Z
sources:
  - id: db-store
    resource: project/src/db/store.py
    title: ArticleStore — schema DDL + pragmas
  - id: config
    resource: project/src/core/config.py
    title: resolve_db_path
  - id: writer
    resource: project/src/db/writer.py
    title: DBWriter single-writer
  - id: data-model
    resource: project/docs/dev/02-data-model-and-db.md
    title: Data Model & DB Design
sources_last_checked: 2026-10-22
---

`monocle.db` là **cơ sở dữ liệu vận hành** của hệ thống, nằm ở `<DATA_ROOT>/monocle.db`
(mặc định `C:\data\news-scape\monocle.db`). Không bao giờ dùng đường dẫn tương đối kiểu
`data/monocle.db` hay bản trong `project/data/`. Thứ tự giải đường dẫn (`resolve_db_path`):
`MONOCLE_DB_PATH` → `MONOCLE_DATA_DIR` → `database.path` trong `settings.yaml` → `monocle.db`
dưới `paths.data_root()`; đường dẫn trong OneDrive hoặc trong kho mã bị từ chối.[^config]

Mọi connection ghi bật `journal_mode=WAL`, `busy_timeout=30000`, `synchronous=NORMAL`; đọc chỉ
đọc mở bằng URI `mode=ro`.[^db-store] Ngoài nội bộ `src/db`, mã mở kết nối qua
`src/db/connect.py` (`open_ro`, `open_rw`, ADR-0027).

Ghi hàng loạt đi qua [DBWriter](../pipelines/db_writer.md) theo mẫu **single-writer**; các thao tác
trạng thái (claim work_item, upsert lock) dùng `BEGIN IMMEDIATE` riêng.[^writer]

Đây là *chỉ mục và trạng thái* của hệ, **không phải** nguồn provenance: bằng chứng bất biến nằm
ở [Bronze raw store](bronze_raw_html.md) trên đĩa.

# 20 bảng trong `store._SCHEMA`

| Tầng | Bảng | Mục đích |
|---|---|---|
| Bronze | [articles](../tables/articles.md) | bài đã capture + chuẩn hoá |
| Bronze | [seen_articles](../tables/seen_articles.md) | cache dedup SHA-256 |
| Bronze | `discovered_urls` · `url_aliases` | sổ phát hiện URL ghi trước mọi bước lọc (ADR 0013) |
| Bronze | `capture_coverage` | độ phủ thu thập so với kênh đối chiếu |
| Bronze | [scraper_heartbeat](../tables/scraper_heartbeat.md) | trạng thái hiện thời từng scraper |
| Bronze | [scraper_metrics](../tables/scraper_metrics.md) | log hiệu suất mỗi chu kỳ |
| Silver | [article_versions](../tables/article_versions.md) | nhật ký capture + change-detection |
| Silver | `silver_failures` | sổ lỗi derive; watermark không vượt hàng `dead_letter=0` (ADR 0007) |
| Handoff | [work_items](../tables/work_items.md) | hàng đợi work-package exactly-once |
| Article Lane | [l1_outputs](../tables/l1_outputs.md) | bản ghi nhận diện thực thể đã qua DoD |
| Article Lane | [agent_outputs](../tables/agent_outputs.md) | bản ghi nội dung đã qua DoD |
| Legacy | [l1_tasks](../tables/l1_tasks.md) | hàng đợi Lớp 1 cũ; nay chỉ giữ tiêu đề đối chiếu cho cổng DoD |
| Legacy | [periodic_reports](../tables/periodic_reports.md) | báo cáo định kỳ NSO; driver đã xoá |
| Phái sinh | `story_clusters` · `cluster_members` | cụm câu chuyện (ADR 0016), dựng lại được |
| Phái sinh | `signal_daily` · `entity_links` · `source_profile` | tín hiệu insight (ADR 0016), dựng lại bằng `signal_build.py` |
| Điều phối | [pipeline_state](../tables/pipeline_state.md) | watermark, checkpoint, advisory lock |

Không có bảng `schema_version`. DDL dùng `CREATE TABLE IF NOT EXISTS` nên không tự nâng cấp DB
cũ; cột thêm sau đi qua `ArticleStore._MIGRATIONS` (hiện có `l1_outputs.l1_source`).

Sổ cái chi phí [token_ledger](../tables/token_ledger.md) nằm ở `harness.db`, không ở đây; sự kiện
vận hành nằm ở `ops.db` (`src/ops/store.py`).

# Cấu hình

| Thuộc tính | Giá trị | Nguồn |
|---|---|---|
| Đường dẫn | `C:/data/news-scape/monocle.db` | [settings.yaml](../configurations/settings.md) `database.path`, `resolve_db_path` |
| Journal mode | WAL | `store._connect()` |
| Busy timeout | 30000 ms | `store._connect()` |
| Synchronous | NORMAL | `store._connect()` |
| `check_same_thread` | False | APScheduler chạy job ở worker thread khác |

Bản chụp point-in-time không chặn ghi: `src/db/snapshot.py` (`create_db_snapshot`).

# Vận hành

Trạng thái pipeline đọc bằng radar, không bằng truy vấn tay:

```powershell
C:\venvs\news-scape\Scripts\python.exe scripts\pipeline_radar.py status
C:\venvs\news-scape\Scripts\python.exe scripts\article_run.py --where
```

Truy vấn SQL tự do: mở chỉ đọc (`sqlite3 -readonly C:\data\news-scape\monocle.db`), tốt nhất trên
bản chụp. Xem thêm: [Runbook](../playbooks/runbook.md), [Deployment](../playbooks/deployment.md).

[^db-store]: [ArticleStore](project/src/db/store.py)
[^writer]: [DBWriter](project/src/db/writer.py)
[^config]: [config.py](project/src/core/config.py)
[^data-model]: [Data Model & DB Design](project/docs/dev/02-data-model-and-db.md)
