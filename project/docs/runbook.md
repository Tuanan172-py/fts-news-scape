# Ops Runbook — Web Monocle

Cập nhật: 2026-07-24 (Phase 1).

## Khởi động / Dừng

```bash
# Pipeline ban ngày liên tục (capture 15' + re-derive Silver 30' + drift mỗi sáng)
.venv\Scripts\python.exe -m src.morninger

# Scheduler chỉ capture (15 phút/cycle) — nếu không cần downstream tự động
.venv\Scripts\python.exe -m src.orchestrator

# 1 cycle rồi thoát (test/cron ngoài)
.venv\Scripts\python.exe scripts/run_once.py            # tất cả domain
.venv\Scripts\python.exe scripts/run_once.py cafef tnck # chọn domain

# Chạy thử từng nhịp morninger riêng
.venv\Scripts\python.exe -m src.morninger --once derive  # re-derive Silver tăng dần (watermark)
.venv\Scripts\python.exe -m src.morninger --once drift   # drift report

# Dừng: Ctrl+C — graceful (flush DBWriter, WAL checkpoint, rồi thoát)
```

**Morninger** chạy 3 nhịp trong 1 tiến trình: capture Bronze (15') → re-derive Silver
tăng dần bằng watermark `pipeline_state` (30') → drift report mỗi sáng. Checkpoint
"Silver đầy đủ" = watermark đuổi kịp Bronze mới nhất (backlog=0), ghi `silver_checkpoint`.
Tại mỗi checkpoint, tự xuất manifest Silver hôm nay ra `data/exports/silver-YYYYMMDD-today.csv`
(danh sách tin cấp Silver: id/domain/url/state/work_status). Xuất tay: `python scripts/export_silver.py`.
Xem `python -m src.morninger --once derive` để đọc trạng thái watermark/checkpoint.

**Tự khởi động cùng Windows:** Task Scheduler → Create Task → Trigger "At log on" →
Action: `C:\...\web-monocle\.venv\Scripts\python.exe -m src.morninger`,
Start in: thư mục project. (Không dùng schedule của Task Scheduler — morninger tự quản lý 3 nhịp.)
**Chỉ tạo 1 task** — chạy 2 scheduler cùng lúc sẽ bị advisory lock (`pipeline_state`) từ chối
(orchestrator/morninger thứ hai log lỗi và thoát) để tránh double-scrape.

## Health check

```bash
.venv\Scripts\python.exe -m src.monitor.health
# SCRAPER   STATE     LAST RUN   FAILS  CYCLES  ARTICLES/24H  ERROR
# Exit 0 = OK hết; exit 1 = có STALE (>30ph) / FAILED / CRITICAL (≥3 fail liên tiếp)

.venv\Scripts\python.exe scripts/verify_quality.py [domain]   # gate ≥95% title+body+date
```

- Notify log: `data/notifications/YYYY-MM-DD.log` (mỗi article match rule + summary cycle)
- App log: `logs/monocle.log` (rotation 50MB, giữ 14 ngày)

## Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
|-------------|-------------|-------|
| `fireant` FAILED, log "token expired" | Bearer token hết hạn | Lấy token mới (xem `docs/skills/fireant.md`) → dán vào `config/secrets.yaml` → cycle sau tự chạy lại. Scraper tự disable trong cycle để không hammer API |
| Scraper CRITICAL liên tục | Site đổi layout/API | Xem `docs/skills/<domain>.md` pitfalls; chạy `scripts/run_once.py <domain>` xem log chi tiết |
| Nhiều bài `detail_deferred` | Backfill lần đầu vượt cap | **Bronze-first, 3 bước:** `python scripts/refresh_watchlist.py 500 <host>` → `python -m src.morninger --once derive` → `python scripts/maintenance/backfill_deferred.py <host> --limit 600` |
| File `-wal` phình to | Process bị kill cứng | Orchestrator tự `wal_checkpoint(TRUNCATE)` cuối mỗi cycle; chạy 1 cycle là gọn lại |
| DB locked (hiếm) | AV/indexer khoá file | Loại trừ thư mục `data/` khỏi antivirus/Windows indexer |

## Báo cáo định kỳ NSO (Cục Thống kê)

**KHÔNG nằm trong cycle 15 phút.** Driver riêng, tần suất thấp — NSO công bố
~**ngày 3 hàng tháng, ~09:00** (verified 2026-09-07).

```bash
python scripts/fetch_periodic_reports.py --dry-run      # chỉ discover + parse kỳ
python scripts/fetch_periodic_reports.py                # 20 bài mới nhất
python scripts/fetch_periodic_reports.py --after 2026-09-01   # sync tăng dần
python scripts/fetch_periodic_reports.py --list         # xem đã có gì trong DB
```

Lịch khuyến nghị (chưa gắn cron):
```
0 8,14 2-6 * *   --after <YYYY-MM-01>     # bắt báo cáo tháng
0 9   * * 1      --per-page 10            # bắt báo cáo quý/năm
```

- **Idempotent**: chạy lại → `skipped_unchanged`, không fetch lại.
- `modified` đổi = **bản hiệu đính** → tạo `revision` mới, **giữ** bản cũ.
- Không parse được kỳ → **held + error**, exit code **1** (cron báo động được).
  KHÔNG bao giờ đoán bừa kỳ báo cáo.
- Bronze: `data/raw_html/nso.gov.vn/<yyyymmdd>/<type>-<period>-r<rev>.html`
  **+ file đính kèm** `__<tên>.xlsx` / `.docx` (bảng số liệu là payload giá trị nhất).
- Chỉ đi HTTPS — cổng `:80` của NSO luôn bị RST.
- ⚠️ Kết nối NSO **từng chập chờn** (reset TCP sáng 2026-09-07, sau đó 12/12 probe OK).
  Fail 1 lần không mất dữ liệu vì tần suất thấp + idempotent.

Chi tiết: [`docs/design/16-periodic-report-scraper.md`](design/16-periodic-report-scraper.md)

## Backfill bài `detail_deferred` (Bronze-first)

Cycle đầu của nguồn mới sinh hàng trăm bài trong khi `max_details_per_cycle` chỉ ~30-40 →
phần dư chỉ có `summary` làm body và bị dedup chặn, **không tự khỏi**.

```bash
# 1. Kéo Bronze cho backlog (bỏ qua dedup, tôn trọng robots + rate limit 3s)
python scripts/refresh_watchlist.py 500 <host>        # vd: vietnambiz.vn

# 2. Bronze → Silver
python -m src.morninger --once derive

# 3. Cập nhật cột DB TỪ FILE BRONZE (thuần, không chạm mạng)
python scripts/maintenance/backfill_deferred.py <host> --limit 600

# kiểm chứng
python scripts/verify_quality.py <host>               # kỳ vọng >= 95%
```

- `backfill_deferred.py` **không bao giờ** ghi `content_text` nếu bài chưa có Bronze artifact.
  Thiếu Bronze → đếm vào `no_bronze` và bỏ qua (trừ khi thêm `--fetch`, khi đó nó ghi Bronze trước).
- `--dry-run` để xem trước, không ghi gì.
- ⚠️ `scripts/enrich_deferred.py` **đã bị XOÁ 2026-09-07**: nó ghi `content_text` mà **không**
  tạo Bronze artifact → vi phạm Bronze-first. Đừng thêm lại (có test canh:
  `tests/test_backfill_deferred.py::test_enrich_deferred_is_gone`).

## Thêm domain mới (~30 phút)

1. **RSS** (nhanh nhất): tạo `config/domains/<name>.yaml` với `method: rss` + danh sách feeds → XONG (generic RSSScraper tự nhận).
2. **API**: research theo quy trình spec §4.2 (DevTools → endpoint → fixture) → viết `src/scrapers/<name>.py` subclass `BaseScraper` với `@register("<name>")` (3 hooks: `fetch_list`, `parse_item`, `enrich`) → yaml + test + skill doc `docs/skills/<name>.md`.
3. Test: `pytest tests/test_<name>.py` → `python scripts/run_once.py <name>` → `python scripts/verify_quality.py <domain>`.

Không sửa orchestrator/core trong mọi trường hợp.

## Bảo trì định kỳ

- `DedupCache.cleanup(30)` — bảng seen_articles tự dọn qua orchestrator? (chưa wire — chạy tay mỗi tháng nếu cần, bảng nhỏ)
- Backup: copy `data/monocle.db` khi orchestrator dừng (hoặc dùng `sqlite3 .backup` online)
- Token FireAnt: kiểm tra khi health báo fail (thường vài ngày–vài tuần hết hạn)
