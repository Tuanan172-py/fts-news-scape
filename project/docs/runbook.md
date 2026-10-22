# Ops Runbook — Web Monocle (lớp capture)

Cập nhật: 2026-10-22. Phạm vi: capture Bronze → Silver. Đợt Article Lane, giao hàng và vận hành không người trông:
[operations/ops-daemon.md](operations/ops-daemon.md). Xuất bản SharePoint: [operations/publisher.md](operations/publisher.md).

Mọi lệnh chạy với thư mục hiện tại là `project/`, sau `& "C:\venvs\news-scape\Scripts\Activate.ps1"`.
Dữ liệu ghi nằm dưới `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`).

## Khởi động / Dừng

```powershell
# Pipeline ban ngày liên tục (capture 10' + re-derive Silver 30' + drift mỗi sáng)
python -m src.morninger

# Scheduler chỉ capture (15 phút/cycle) — nếu không cần downstream tự động
python -m src.orchestrator

# 1 cycle rồi thoát (test/cron ngoài)
python scripts/run_once.py            # tất cả domain
python scripts/run_once.py cafef tnck # chọn domain

# Chạy thử từng nhịp morninger riêng
python -m src.morninger --once capture  # 1 cycle capture Bronze
python -m src.morninger --once derive   # re-derive Silver tăng dần (watermark)
python -m src.morninger --once drift    # drift report

# Dừng: Ctrl+C — graceful (flush DBWriter, WAL checkpoint, rồi thoát)
```

**Morninger** chạy 3 nhịp trong 1 tiến trình: capture Bronze (`capture_interval_minutes`, 10') kèm bù
`backfill_deferred` → re-derive Silver tăng dần bằng watermark `pipeline_state` (30') → drift report mỗi sáng
(`drift_hour`, 06:00). Checkpoint "Silver đầy đủ" = watermark đuổi kịp Bronze mới nhất (backlog=0), ghi
`silver_checkpoint`. Tại mỗi checkpoint, tự xuất manifest Silver hôm nay ra
`C:\data\news-scape\exports\silver-YYYYMMDD-today.csv` (danh sách tin cấp Silver).

**Chạy nền:** `ops_daemon` (Task Scheduler `news-scape-ops`) tự giữ `morninger` sống; đầu ra ở
`C:\data\news-scape\ops_logs\capture.log`. Không tạo task riêng cho `morninger`. Chạy 2 scheduler cùng lúc
bị khoá `capture.lock` / `pipeline_state` từ chối để tránh double-scrape.

## Health check

```powershell
python -m src.monitor.health
# SCRAPER   STATE     LAST RUN   FAILS  CYCLES  ARTICLES/24H  ERROR
# Exit 0 = OK hết; exit 1 = có STALE (>30ph) / FAILED / CRITICAL (≥3 fail liên tiếp)

python scripts/pipeline_radar.py status      # điểm chạm của pipeline + đúng một lệnh kế tiếp
python scripts/validate_capture.py [domain] [n]   # audit Bronze capture: chạy n bài (mặc định 2) vào DB tạm
```

- Notify log: `C:\data\news-scape\notifications\YYYY-MM-DD.log` (mỗi article match rule + summary cycle)
- App log: `C:\data\news-scape\logs\monocle.log` (rotation 50MB, giữ 14 ngày)

## Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Xử lý |
| --- | --- | --- |
| `fireant` FAILED, log "token expired" | Bearer token hết hạn | Lấy token mới (xem `docs/skills/fireant.md`) → dán vào `config/secrets.yaml` → cycle sau tự chạy lại. Scraper tự disable trong cycle để không hammer API |
| Scraper CRITICAL liên tục | Site đổi layout/API | Xem `docs/skills/<domain>.md` pitfalls; chạy `scripts/run_once.py <domain>` xem log chi tiết |
| Nhiều bài `detail_deferred` | Backfill lần đầu vượt cap | **Bronze-first, 3 bước:** `python scripts/refresh_watchlist.py 500 <host>` → `python -m src.morninger --once derive` → `python scripts/maintenance/backfill_deferred.py <host> --limit 600` |
| File `-wal` phình to | Process bị kill cứng | Orchestrator tự `wal_checkpoint(TRUNCATE)` cuối mỗi cycle; chạy 1 cycle là gọn lại |
| DB locked (hiếm) | AV/indexer khoá file | Loại trừ thư mục `C:\data\news-scape` khỏi antivirus/Windows indexer |

Sự cố khác của lớp capture: [operations/troubleshooting.md](operations/troubleshooting.md).

## Backfill bài `detail_deferred` (Bronze-first)

`morninger` nối `backfill_deferred.py --mode all` ngay sau mỗi chu kỳ capture, nên bài `detail_deferred` và
bài lỗi tạm thời (timeout/5xx) được bù liên tục. Quy trình thủ công dưới đây chỉ dùng cho **backlog lớn khi
onboard nguồn mới** (hàng trăm bài, vượt xa ngân sách 90s/chu kỳ của job tự động).

Tham số job tự động nằm ở `config/settings.yaml` khối `morninger`:
`deferred_backfill_limit` (60) · `deferred_budget_seconds` (90) · `deferred_max_attempts` (5) ·
`deferred_retry_window_hours` (24).

Bài thử đủ `max_attempts` lần được gắn `capture_giveup`; bài trả 404/410 được gắn `source_deleted`. Cả hai bị
loại khỏi hàng đợi để không fetch lại vô hạn — muốn ép thử lại phải xoá cờ tương ứng trong `metadata_json`.

Cycle đầu của nguồn mới sinh hàng trăm bài trong khi `max_details_per_cycle` chỉ ~30-40 → phần dư chỉ có
`summary` làm body và bị dedup chặn, **không tự khỏi** trong một chu kỳ.

```powershell
# 1. Kéo Bronze cho backlog (bỏ qua dedup, tôn trọng robots + rate limit 3s)
python scripts/refresh_watchlist.py 500 <host>        # vd: vietnambiz.vn

# 2. Bronze → Silver
python -m src.morninger --once derive

# 3. Cập nhật cột DB TỪ FILE BRONZE (thuần, không chạm mạng)
python scripts/maintenance/backfill_deferred.py <host> --limit 600
```

- `backfill_deferred.py` **không bao giờ** ghi `content_text` nếu bài chưa có Bronze artifact.
  Thiếu Bronze → đếm vào `no_bronze` và bỏ qua (trừ khi thêm `--fetch`, khi đó nó ghi Bronze trước).
- `--dry-run` để xem trước, không ghi gì.
- Không thêm script ghi `content_text` mà không tạo Bronze artifact (vi phạm Bronze-first; test canh:
  `tests/core/test_backfill_deferred.py::test_enrich_deferred_is_gone`).

## Thêm domain mới (~30 phút)

1. **RSS** (nhanh nhất): tạo `config/domains/<name>.yaml` với `method: rss_capture` + danh sách feeds + `content_selector` → XONG (generic `RssCaptureScraper` có Bronze capture).
2. **API/HTML riêng**: research theo quy trình spec §4.2 (DevTools → endpoint → fixture) → viết `src/scrapers/<name>.py` subclass `BaseScraper` với `@register("<name>")` (3 hooks: `fetch_list`, `parse_item`, `enrich`) → yaml + test + skill doc `docs/skills/<name>.md`.
3. Test: `python -m pytest tests/scrapers/test_<name>.py` → `python scripts/run_once.py <name>` → `python scripts/validate_capture.py <name>`.

Chi tiết: [dev/03-adding-a-source.md](dev/03-adding-a-source.md). Không sửa orchestrator/core trong mọi trường hợp.

## Bảo trì định kỳ

- `DedupCache.cleanup(30)` chạy mỗi lần khởi tạo orchestrator (bảng `seen_articles`, xoá mục >30 ngày).
- Backup: copy `C:\data\news-scape\monocle.db` khi không có tiến trình ghi (hoặc dùng sqlite backup API online).
- Token FireAnt: kiểm tra khi health báo fail (thường vài ngày–vài tuần hết hạn).
