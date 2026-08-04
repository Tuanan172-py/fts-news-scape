# Ops Runbook — Web Monocle

Cập nhật: 2026-07-24 (Phase 1).

## Khởi động / Dừng

```bash
# Scheduler liên tục (15 phút/cycle, cycle đầu chạy ngay)
.venv\Scripts\python.exe -m src.orchestrator

# 1 cycle rồi thoát (test/cron ngoài)
.venv\Scripts\python.exe scripts/run_once.py            # tất cả domain
.venv\Scripts\python.exe scripts/run_once.py cafef tnck # chọn domain

# Dừng: Ctrl+C — graceful (flush DBWriter, WAL checkpoint, rồi thoát)
```

**Tự khởi động cùng Windows:** Task Scheduler → Create Task → Trigger "At log on" →
Action: `C:\...\web-monocle\.venv\Scripts\python.exe -m src.orchestrator`,
Start in: thư mục project. (Không dùng schedule của Task Scheduler — orchestrator tự quản lý chu kỳ.)

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
