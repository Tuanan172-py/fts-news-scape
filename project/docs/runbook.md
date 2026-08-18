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
| `fireant` FAILED, log "token expired" | Bearer token hết hạn | Lấy token mới (xem `docs/skills/fireant.md`) → dán vào `config/secrets.yaml` → cycle sau tự chạy lại |
| Scraper CRITICAL liên tục | Site đổi layout/API | Xem `docs/skills/<domain>.md` pitfalls; chạy `scripts/run_once.py <domain>` xem log chi tiết |
| Nhiều bài `detail_deferred` | Backfill lần đầu vượt cap | `python scripts/enrich_deferred.py [domain]` |
| File `-wal` phình to | Process bị kill cứng | Orchestrator tự `wal_checkpoint(TRUNCATE)` cuối mỗi cycle; chạy 1 cycle là gọn lại |
| DB locked (hiếm) | AV/indexer khoá file | Loại trừ thư mục `data/` khỏi antivirus/Windows indexer |

## Thêm domain mới (~30 phút)

1. **RSS** (nhanh nhất): tạo `config/domains/<name>.yaml` với `method: rss` + danh sách feeds → XONG (generic RSSScraper tự nhận).
2. **API**: research theo quy trình spec §4.2 (DevTools → endpoint → fixture) → viết `src/scrapers/<name>.py` subclass `BaseScraper` với `@register("<name>")` (3 hooks: `fetch_list`, `parse_item`, `enrich`) → yaml + test + skill doc `docs/skills/<name>.md`.
3. Test: `pytest tests/test_<name>.py` → `python scripts/run_once.py <name>` → `python scripts/verify_quality.py <domain>`.

Không sửa orchestrator/core trong mọi trường hợp.

## Bảo trì định kỳ

- `DedupCache.cleanup(30)` — bảng seen_articles tự dọn qua orchestrator? (chưa wire — chạy tay mỗi tháng nếu cần, bảng nhỏ)
- Backup: copy `data/monocle.db` khi orchestrator dừng (hoặc dùng `sqlite3 .backup` online)
- Token FireAnt: kiểm tra khi health báo fail (thường vài ngày–vài tuần hết hạn)
