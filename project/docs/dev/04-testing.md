# Dev — Kiểm thử

Cập nhật: 2026-10-22 · 97 file `test_*.py` (~840 hàm `test_`, chưa tính parametrize) dưới `project/tests/`.
Bố cục theo RULE-12.R7 ([`.agents/rules/12-module-boundaries.md`](../../../.agents/rules/12-module-boundaries.md)).

## 1. Nguyên tắc

- **Không mạng thật** trong unit test — dùng `FakeHTTP` / `FakeResponse` (`tests/_fakes.py`) bơm bytes/JSON cố định.
- **Không mock giả để pass build** — test phải phản ánh hành vi thật của code.
- **Fixture thật** cho feed/trang khó: `tests/fixtures/*` (vd `dantri_bom.rss`, `vietnambiz_utf16.rss`, `*_detail_page.html`)
  capture từ nguồn sống để khoá regression. Golden của Article Lane: `tests/fixtures/golden/`.
- **Không đụng dữ liệu vận hành.** `tests/conftest.py`, trước khi import module test nào:
  - đặt `MONOCLE_DATA_DIR` và `MONOCLE_DB_PATH` vào một thư mục tạm (`news-scape-test-*`), bỏ `MONOCLE_ALLOW_SYNCED_DB`
    và `NEWS_SCAPE_SUBSCRIPTIONS_DIR`; script con gọi qua subprocess thừa kế các biến này;
  - chép `tests/fixtures/entities_min.json` vào `<tmp>/entities/entities.json` cho `load_registry()`;
  - bọc `sqlite3.connect`: mở DB dưới `C:\data\news-scape` hoặc `harness.db` của kho thì test thất bại ngay.
- DB test dùng `tmp_path` hoặc thư mục tạm trên; không bao giờ `C:\data\news-scape\monocle.db`.

## 2. Bố cục

```
project/tests/
├── conftest.py          # cô lập dữ liệu + sys.path (project root và thư mục tests)
├── _fakes.py            # FakeHTTP, FakeResponse dùng chung
├── _userkit.py          # helper dựng người dùng/subscription cho test
├── fixtures/            # feed, trang chi tiết, JSON API, entities_min.json, golden/
└── <package>/test_*.py  # soi gương src/<package>/
```

| Thư mục | Số file | Phủ |
|---|---|---|
| `agent/` | 15 | runners (agy, opencode, openrouter), conformance, DoD, entities/matcher, l1_classifier, l1_router, l1_runner, pruner, ingest CLI |
| `article_lane/` | 7 | contract, lane, pack thin, tick, code-first guard, ledger, `test_lane_golden.py` |
| `core/` | 9 | base_scraper, paths, capture registry, DB path + capture lock, tickers, user manifest, migrate_users_output, backfill_deferred |
| `crawler/` | 3 | raw_store, robots, backoff |
| `db/` | 2 | store, dedup |
| `export/` | 6 | user_output, checkpoint, publisher, signal_build, đường dẫn neo, I/O song song |
| `handoff/` | 2 | handoff, đường dẫn state |
| `lakehouse/` | 6 | storage, manifest, dedup, concurrency, perf, adversarial |
| `monitor/` | 1 | heartbeat/metrics, notify |
| `ops/` | 11 | ops core/runtime/manual/present/supervision/trace, restart lock, pipeline_spec, wave thin-demote, hardening |
| `orchestrator/` | 1 | functional + hygiene |
| `pipeline/` | 9 | change_detect, story_cluster, inherit, morninger, capture reconcile/backfill, silver watermark |
| `processor/` | 1 | classifier, extractor |
| `repo/` | 8 | `test_architecture.py` (RULE-12), `test_cli_entrypoints.py`, `test_doc_lint.py`, `test_diagrams.py`, lakehouse CLI, plugin, no-agent-emulation |
| `scrapers/` | 15 | từng scraper (cafef, tnck, fireant, vietstock, vneconomy, baodautu, vndirect, thoibaotaichinhvietnam, rss_*), orchestrator, looks_complete |
| `users/` | 1 | compile_users |

Đếm lại: `Get-ChildItem project/tests -Recurse -Filter test_*.py | Measure-Object`.

## 3. Chạy

Venv chuẩn `C:\venvs\news-scape` (ADR-0024), cwd = `project/`:

```powershell
cd project
C:\venvs\news-scape\Scripts\python.exe -m pytest tests/ -q                                  # tất cả
C:\venvs\news-scape\Scripts\python.exe -m pytest tests/ -q --ignore=tests/repo/test_cli_entrypoints.py   # agent chạy bản này (§3.1)
C:\venvs\news-scape\Scripts\python.exe -m pytest tests/scrapers/test_fireant.py -v          # 1 file
C:\venvs\news-scape\Scripts\python.exe -m pytest tests/ -k "dedup" -q                       # theo keyword
C:\venvs\news-scape\Scripts\python.exe -m pytest tests/repo/test_architecture.py -q         # ranh giới module (RULE-12)
C:\venvs\news-scape\Scripts\python.exe -m pytest tests/article_lane/test_lane_golden.py -q  # packet/conductor/expand không đổi
```

### 3.1 `tests/repo/test_cli_entrypoints.py`

File này chạy `--help` của mọi CLI và một lượt `scripts/maintenance/backfill_deferred.py --mode all --limit 3 --dry-run`
qua subprocess, không truyền DB. Subprocess thừa kế `MONOCLE_DB_PATH` tạm từ `conftest.py`, nên theo code hiện tại
lượt dry-run mở DB trong thư mục tạm. FACT [`tests-must-not-write-operational-db`](../../../docs/knowledge/facts/tests-must-not-write-operational-db.md)
(verified 2026-10-06) vẫn yêu cầu agent bỏ file này khi chạy cả bộ; giữ `--ignore` cho tới khi FACT được xác minh lại.

## 4. Mẫu FakeHTTP

```python
class FakeHTTP:
    def __init__(self, xml): self.xml = xml
    def get_bytes(self, url, **kw): return self.xml.encode("utf-8")
    def get(self, url, **kw): return "<html>…</html>"
```
API scraper dùng `FakeResponse`/`FakeHTTP` trả `.json()` + `.status_code` để test self-disable
(vd FireAnt `list_status=401` → assert `scraper.disabled` và không gọi tiếp watchlist còn lại).

## 5. Thêm test

- Test mới vào `tests/<package>/` khớp package trong `src/`; kiểm tra toàn kho vào `tests/repo/` (RULE-12.R7).
- Khi thêm nguồn, tối thiểu: happy path (1 item → 1 Article đúng field), thiếu field → None, lỗi HTTP → errors
  không rỗng nhưng không crash, date parsing đúng giờ VN, raw Bronze byte-exact. Có auth: token thiếu/hết hạn → disabled.
  Encoding lạ: thêm fixture thật vào `tests/fixtures/`.
- Script mới: khai trong `SCRIPT_INVENTORY` (`tests/repo/test_architecture.py`), nếu không test kiến trúc thất bại.

## 6. Câu hỏi mở

- Chưa có fixture cố định cho hose (JSON-feed qua feedparser, nguồn đang tắt). Xem [05-known-issues.md](05-known-issues.md).
