# Kiểm toán lớp C: chất lượng mã, chuẩn docstring và sức khoẻ test

Ngày: 2026-09-24. Nhánh: `feature/article-lane-remove-gates` (working tree có thay đổi chưa commit, và có agent khác sửa tệp trong lúc kiểm toán chạy, xem C2.2).
Chế độ: chỉ đọc. Công cụ: script AST tạm trong scratchpad (`audit/static_scan.py`, `audit/test_map.py`, số liệu thô ở `audit/scan.json`, `audit/test_map.txt`, `audit/pytest_out.txt`, `audit/collect.txt`).
Chuẩn tham chiếu: `.agents/rules/06-code-and-docstring-standards.md`.

Phạm vi quét: 140 tệp Python, 25.072 dòng (`project/src` 82 tệp/14.031 dòng, `project/scripts` 57 tệp/10.108 dòng, `scripts/` gốc 1 tệp/933 dòng), 711 hàm.

---

## Tóm tắt điều hành

| Hạng mục | Kết quả |
|---|---|
| Test `project/tests` | **528 pass, 1 fail, 0 skip, 0 xfail**, 362 s (6 phút 2 giây), 550 cảnh báo DeprecationWarning (feedparser) |
| Test `tests/` gốc | **6 pass, 1 fail** (`test_query_contract`: `schema_version` 3 != 2), 3,8 s |
| Test chạm DB vận hành thật | **1** (`test_backfill_deferred_dry_run_is_safe_and_reports`), chạy `init_schema` (DDL + `PRAGMA journal_mode=WAL` + commit) lên `C:/data/news-scape/monocle.db` |
| Blacklist từ ngữ trong docstring/comment | **0** vi phạm (sạch) |
| Emoji trong docstring/comment | **0**; 146 emoji nằm trong chuỗi in CLI (thiết kế, nhưng có rủi ro mã hoá) |
| Thiếu module docstring | 2 tệp |
| Module docstring dài hơn 1 câu/12 dòng | 6 tệp |
| Hàm công khai không docstring | 95 (20 riêng `scripts/harness_cli.py`) |
| Thiếu `Args:` / `Returns:` / `Raises:` (hàm công khai > 5 dòng) | 41 / 43 / 2 |
| Comment/docstring kể lịch sử | 31 vị trí |
| `except Exception` rộng / nuốt lỗi im lặng | 102 / 20 |
| `print()` | 660 (45 trong `project/src`) |
| Đường dẫn cứng thật sự (không tính chuỗi mô tả) | 7 vị trí |
| Hàm thiếu type hint | 116/711 (16%) |
| Số ma thuật (ngoài hằng module, trừ 0/1/2/10/100) | 499 |
| Module `src` không test nào import | 6/77 |
| Script không test nào nhắc tới | 36/57 |
| Test cho mã lane đã ngừng | khoảng 50 test trong 10 tệp |
| Khoá cấu hình chết | 2 khoá domain, 1 khoá pricing, 1 comment cấu hình sai sự thật |

---

## C1. Chất lượng mã và docstring

### C1.1 Bảng xếp hạng tệp tệ nhất

Điểm = 3×thiếu module doc + 2×hàm công khai không doc + thiếu Args + thiếu Returns + thiếu Raises + 2×lịch sử + 3×nuốt lỗi + 3×đường dẫn cứng + module doc dài (đường dẫn cứng tính cả chuỗi mô tả nhắc tới OneDrive, nên `config.py` bị thổi điểm, xem C1.6).

| # | Tệp | Điểm | Dòng | Hàm công khai không doc | Thiếu Args | Thiếu Returns | Lịch sử | Nuốt lỗi | Đường dẫn cứng | print |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `project/src/db/store.py` | 44 | 798 | 9 | 13 | 9 | 2 | 0 | 0 | 0 |
| 2 | `scripts/harness_cli.py` | 44 | 933 | 20 | 0 | 0 | 0 | 0 | 1 | 4 |
| 3 | `project/scripts/build_entities.py` | 33 | 765 | 9 | 2 | 2 | 1 | 1 | 2 | 4 |
| 4 | `project/scripts/maintenance/clean_onedrive_conflicts.py` | 21 | 219 | 1 | 2 | 2 | 0 | 1 | 4 | 29 |
| 5 | `project/src/core/config.py` | 15 | 246 | 0 | 0 | 0 | 0 | 0 | 5 (1 thật) | 0 |
| 6 | `project/scripts/article_run.py` | 13 | 824 | 0 | 0 | 0 | 6 | 0 | 0 | 78 |
| 7 | `project/src/orchestrator.py` | 12 | 294 | 5 | 0 | 0 | 1 | 0 | 0 | 0 |
| 8 | `project/scripts/pipeline_radar.py` | 12 | 633 | 0 | 1 | 1 | 2 | 1 | 1 | 83 |
| 9 | `project/src/core/staging.py` | 10 | 180 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| 10 | `project/src/morninger.py` | 10 | 358 | 3 | 0 | 0 | 2 | 0 | 0 | 7 |
| 11 | `project/src/agent/runner.py` | 9 | 280 | 0 | 0 | 0 | 0 | 3 | 0 | 0 |
| 12 | `project/src/export/user_output.py` | 9 | 497 | 0 | 0 | 0 | 0 | 1 | 2 | 0 |
| 13 | `project/src/pipeline/periodic_reports.py` | 9 | 316 | 1 | 2 | 2 | 0 | 1 | 0 | 0 |
| 14 | `project/scripts/auto_pilot.py` | 9 | 246 | 0 | 1 | 1 | 2 | 0 | 1 | 32 |
| 15 | `project/src/agent/batch_handoff.py` | 8 | 231 | 0 | 2 | 2 | 2 | 0 | 0 | 0 |

Bằng chứng tiêu biểu:
- `project/src/db/store.py`: không docstring ở `init_schema` (:316), `get_by_hash` (:349), `last_version` (:360), `insert_version` (:372), `get_l1_task` (:505), `set_l1_status` (:513), `get_l1_output` (:540), `get_recent` (:607), `count` (:639); thiếu `Args:`/`Returns:` ở `changed_since` (:409), `get_agent_output` (:423), `insert_agent_output` (:453), `insert` (:548), `insert_batch` (:565), `count_by_domain` (:626), `get_state` (:647), `try_acquire_lock` (:749). Comment trong `init_schema` (:318-320) viết tiếng Việt không dấu, khác văn phong phần còn lại.
- `scripts/harness_cli.py`: 20/25 hàm công khai không docstring (`query_contract` :117, `cmd_intake` :164, `cmd_story_add` :197, `cmd_audit` :456, `cmd_propose` :553, `main` :877...). Module docstring 2 câu.

Đề xuất: ưu tiên bổ sung docstring cho `store.py` (lớp dữ liệu dùng bởi 34 tệp test, là Data Contract) và `harness_cli.py`; hai tệp này chiếm 29/95 hàm không docstring.

### C1.2 Module docstring

- Thiếu hẳn: `project/scripts/inspect_catalog.py:1`, `project/scripts/run_validation.py:1`.
- Dài hơn chuẩn "1 câu khẳng định": `project/src/agent/distill.py` (13 dòng), `project/src/agent/prefix.py` (19 dòng, có "trước đây"), `project/src/telemetry/dsh_usage.py` (22 dòng), `project/scripts/article_run.py` (15 dòng), `project/scripts/build_article_prefix.py` (16 dòng), `scripts/harness_cli.py` (2 câu).
- Docstring dòng đầu không kết thúc bằng dấu chấm: 7 hàm.

Đề xuất: thêm docstring 1 câu cho hai tệp thiếu; với 5 tệp dài, giữ câu đầu, chuyển phần giải trình thiết kế sang `docs/` hoặc plan tương ứng.

### C1.3 Blacklist và emoji

- Blacklist (`nhìn chung`, `thông thường`, `nói chung`, `về cơ bản`, `đáng chú ý`, `cần lưu ý rằng`, `chúng ta`, `tôi`, `toàn diện`, `mạnh mẽ`, `[LEGACY`, `TODO tạm thời`, `ĐÓNG BĂNG`, `L1_VERSION`) trong docstring và comment: **0 vi phạm**. Không có `TODO`/`FIXME`/`HACK` nào. Kết quả grep duy nhất nằm ở danh sách mẫu của chính `project/scripts/maintenance/audit_codebase.py:17-29`. Từ `legacy` còn xuất hiện ở tên định danh (`src/db/dedup.py:15 _LEGACY_JSON`, `scripts/maintenance/cleanup_legacy_tasks.py`) và docstring `build_entities.py:544` "chuẩn legacy".
- Emoji trong docstring/comment: **0**.
- Emoji trong chuỗi in CLI: 146 (radar 22, auto_pilot 18, article_run 17, sample_articles 16, run_agent_hierarchy 12, token_ledger 9, daily_reporter 8, build_article_prefix 7). Đây là thiết kế đầu ra (ví dụ `✅ ĐỢT <mã> HOÀN TẤT` là tín hiệu hợp đồng của `--finish`). Rủi ro còn lại: sự cố 2026-09-17 (`UnicodeEncodeError` qua pipe cp1252) sinh ra chính từ đây; `src/notifier/file_notify.py:92` có emoji mặc định `🟡` trong mã thư viện.

Đề xuất: giữ emoji ở CLI nhưng bảo đảm mọi script có emoji gọi `force_utf8_stdio()` (đã có trong `src/core/stdio.py`, nhưng `src/core/stdio.py` không có test nào, xem C2.5). Đổi `build_entities.py:544` "chuẩn legacy" thành mô tả trung tính.

### C1.4 Comment/docstring kể lịch sử (31 vị trí)

Vi phạm quy tắc "không giải trình lịch sử trong mã":
- `project/src/agent/batch_handoff.py:176` "Trước đây mã lô luôn đếm lại từ 01…", :178 "ADR 0008".
- `project/src/agent/distill.py:29` "đã bỏ", :44 "Trước đây chạm thì bỏ nguyên đoạn. Nay tách…".
- `project/src/agent/prefix.py:1` (module docstring) "trước đây".
- `project/src/pipeline/derive.py:19, 83, 158` "ADR 0007"; :121 "Trước đây mỗi tệp bị đọc/parse 3 lần".
- `project/src/morninger.py:39` "đã ngừng", :199 docstring `run_reclaim` "Trước đây".
- `project/src/orchestrator.py:145` "Sentiment rule-based … đã gỡ khỏi workflow giai đoạn này".
- `project/src/export/checkpoint.py:127` "… trước đây".
- `project/src/db/store.py:671` "ADR 0007", :717 "không còn".
- `project/scripts/article_run.py:75, 95, 307, 360, 530` ("đợt W365 in HOÀN TẤT và thoát 0"), :533 "đã ngừng".
- `project/scripts/auto_pilot.py:1` "ADR 0008", :30 "Trước đây hardcode…".
- `project/scripts/pipeline_radar.py:195` "ADR 0007", :390 "Không còn".
- `project/scripts/maintenance/backfill_deferred.py:273`, `clean_completed_packets.py:1`, `article_pack.py:178`, `article_expand.py:1`, `silver_builder.py:69`.
- `project/config/settings.yaml:24-32` nhúng nhật ký đo đạc ngày 2026-09-17 vào comment cấu hình.

Ghi chú: tham chiếu `ADR 000x` để giải thích *vì sao* bất biến tồn tại là chấp nhận được; phần cần bỏ là câu tường thuật "trước đây… nay…", mã đợt (`W365`), ngày sự cố.

Đề xuất: viết lại 31 vị trí thành câu khẳng định hiện tại ("Đọc fetch_ts một lần cho mỗi tệp."), đưa tường thuật về ADR/commit message. Có thể làm theo lô cùng C1.1.

### C1.5 Xử lý ngoại lệ

102 `except Exception` rộng; 20 khối nuốt lỗi im lặng (`pass`/`continue`), 0 `except:` trần. Các vị trí có hậu quả nghiệp vụ:

| Vị trí | Hậu quả | Mức |
|---|---|---|
| `project/src/agent/dod.py:55` (`load_thresholds`) | YAML ngưỡng DoD hỏng/sai kiểu thì lặng lẽ dùng mặc định; cổng DoD đổi ngưỡng mà không ai biết | Cao |
| `project/src/agent/runner.py:119, 194, 202` | JSON `output_json` hỏng bị bỏ qua, bài có thể bị lọc sai khỏi danh sách/thiếu thực thể | Trung bình |
| `project/src/core/staging.py:92, 119, 178` | So sánh hash / dọn tmp thất bại im lặng trong ghi nguyên tử | Trung bình |
| `project/src/export/user_output.py:131` | So sánh byte tệp giao hàng lỗi thì ghi đè (an toàn), nhưng không log | Thấp |
| `project/src/users/compile.py:330`, `src/db/snapshot.py:44`, `src/telemetry/dsh_usage.py:372`, `src/pipeline/periodic_reports.py:185` | Dọn dẹp / cache clear | Thấp |
| `project/scripts/pipeline_radar.py:18`, `sample_articles.py:12`, `diagnose_sources.py:13`, `cleanup_legacy_tasks.py:15` | Bọc `stdout.reconfigure`; trùng chức năng `src/core/stdio.force_utf8_stdio` | Thấp |

Đề xuất: (1) `dod.py:55` phải log `logger.warning` kèm tên tệp và ném lỗi khi khoá có mặt nhưng sai kiểu; (2) `runner.py` log `article_id` khi parse thất bại; (3) thay các khối `reconfigure` bằng `force_utf8_stdio()`; (4) bổ sung luật lint cấm `except Exception: pass` không có comment lý do (xem C4).

### C1.6 print thay logging

660 lời gọi `print()`. Ở `project/scripts` (611) phần lớn là đầu ra CLI hợp lệ. Ở `project/src` có 45 lời gọi trong 10 module thư viện: `monitor/daily_reporter.py` 15, `agent/manifest.py` 8, `morninger.py` 7, `handoff/contract_validator.py` 4, `export/csv_export.py` 3, `monitor/health.py` 3, `pipeline/derive.py` 3, `notifier/file_notify.py` 2, `pipeline/change_detect.py` 1, `pipeline/run.py` 1.

Đề xuất: trong `src/`, chỉ cho phép `print` trong khối `if __name__ == "__main__"` hoặc hàm `main()`; phần còn lại chuyển sang `loguru` logger (đã có `src/core/logging.py`).

### C1.7 Đường dẫn cứng

Loại chuỗi mô tả/thông báo, còn 7 vị trí thật:
- `project/scripts/build_entities.py:30-31`: `C:\Users\anpt\OneDrive - fpts.com.vn\FRA - Data` và `C:\Users\An Thanh Pham\OneDrive - fpts.com.vn\FRA - Data` (đường dẫn cá nhân, hai máy).
- `project/scripts/maintenance/route_today_l1.py:23` và `cleanup_legacy_tasks.py:22`: fallback `"C:/data/news-scape/monocle.db"` trùng `OPERATIONAL_DB_PATH`, bỏ qua `resolve_db_path()` (và bỏ qua `MONOCLE_DB_PATH`).
- `project/scripts/auto_pilot.py:31`: fallback `C:\venvs\news-scape\Scripts\python.exe`.
- `project/src/core/config.py:47` `OPERATIONAL_DB_PATH = Path("C:/data/news-scape/monocle.db")` và `project/config/settings.yaml:6` cùng giá trị (định nghĩa hai nơi).
- `project/scripts/pipeline_radar.py:42`: chuỗi hướng dẫn lệnh có `C:\venvs\...` (chấp nhận được, là văn bản cho người đọc).

Đề xuất: `build_entities.py` đọc thư mục dữ liệu từ biến môi trường (ví dụ `FRA_DATA_DIR`) với fallback tương đối; hai script bảo trì gọi `resolve_db_path()`; bỏ giá trị trùng hoặc ở `settings.yaml` hoặc ở `config.py` (xem C3).

### C1.8 Type hint và số ma thuật

- 116/711 hàm thiếu ít nhất một chú thích kiểu (tham số hoặc giá trị trả về). Nhiều nhất: `scripts/domain_check.py` 7, `sample_articles.py` 5, `build_entities.py` 5, `src/pipeline/silver_builder.py` 4, `src/export/user_output.py` 4, `src/orchestrator.py` 3, `src/pipeline/refresh.py` 3, `src/pipeline/user_workflow.py` 3.
- 499 hằng số ma thuật trong thân hàm. Nhiều nhất: `pipeline_radar.py` 32, `harness_cli.py` 30, `article_run.py` 26, `morninger.py` 23, `token_ledger.py` 17, `daily_reporter.py` 16, `http_client.py` 14. Mẫu đáng sửa: `src/morninger.py:60, 151-154, 288` lặp lại mặc định (`15`, `60`, `5`, `24`, `90`) đã có trong `settings.yaml`/`_DEFAULT_SETTINGS`, và mặc định `15` ở mã khác giá trị thật `10` trong YAML; `pipeline_radar.py:546-547` và `ctx_probe.py:63-64` lặp mặc định `0.25`/`0.40`.

Đề xuất: gom mặc định vào một chỗ (`_DEFAULT_SETTINGS`), mã chỉ đọc `cfg[...]`; bật `ruff` luật `ANN` cho `src/` trước (66 hàm).

---

## C2. Sức khoẻ test

### C2.1 Kết quả chạy

`C:\venvs\news-scape\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider -rsxX --durations=25` (cwd `project/`):

- 529 test thu thập, **528 pass, 1 fail**, 0 skip, 0 xfail/xpass, 550 cảnh báo, **362,34 s**.
- Fail: `tests/test_db_path_and_capture_lock.py::test_khoa_tu_nha_khi_chu_khoa_chet` (`assert after.acquire()` tại dòng 100).
- `tests/` gốc: 7 test, 6 pass, 1 fail `tests/test_harness_cli.py:55` `assertEqual(contract["schema_version"], 2)` nhận 3. Test cứng số phiên bản schema, lỗi thời so với `scripts/schema/`.

Đề xuất: sửa `test_harness_cli.py:55` so với hằng số phiên bản do `harness_cli` công bố thay vì số cứng; đưa `tests/` gốc vào lệnh test mặc định trong `AGENTS.md §3` (hiện chỉ ghi `project/tests`).

### C2.2 Test flaky

`test_khoa_tu_nha_khi_chu_khoa_chet` fail trong lượt chạy toàn bộ, pass 3/3 khi chạy riêng tệp. Tệp này chưa được track (`?? project/tests/test_db_path_and_capture_lock.py`) và đã bị sửa trong lúc kiểm toán chạy: bản hiện tại (dòng 100-108) thêm vòng chờ tối đa 20 s vì trình khởi chạy `python.exe` của venv trên Windows nhả khoá trễ. Test vẫn phụ thuộc thời gian thực (`time.sleep`, `Popen` giữ khoá 60 s, `holder.kill()`).

Đề xuất: đánh dấu `@pytest.mark.slow` hoặc chạy tiến trình con bằng `sys._base_executable` (trình thông dịch thật, không qua launcher) để `kill()` giải phóng khoá ngay; commit tệp test trước khi dùng làm bằng chứng.

### C2.3 Test chậm

6 test `tests/test_baodautu.py` chiếm khoảng 102 s (28% tổng thời gian): `test_date_parsed_from_detail` 25,8 s, `test_capture_happy_path` 20,4 s, `test_content_selector_avoids_js_template` 17,9 s, `test_author_parsed` 14,8 s, `test_missing_date_recorded_not_faked` 12,8 s, `test_listing_failure_isolated` 11,1 s. Dùng `FakeHTTP`, không có mạng; nghi phân tích HTML lớn lặp lại cho 30 detail mỗi lượt. Tiếp theo: `test_cli_entrypoints.py` (subprocess, 2-9 s mỗi test, tổng khoảng 35 s), `test_rss_capture.py` (3-7 s).

Đề xuất: đo `python -m cProfile` trên `test_capture_happy_path`; hạ `max_details_per_cycle` trong `_config()` của test xuống 3; dùng fixture `scope="module"` cho HTML đã parse. Mục tiêu tổng thời gian dưới 3 phút.

### C2.4 Test phụ thuộc mạng hoặc DB thật

- Mạng: không test nào gọi `requests`/`httpx`/`urlopen` trực tiếp; các scraper dùng `_fakes.FakeHTTP`. Đạt.
- **DB vận hành thật: `project/tests/test_cli_entrypoints.py:56-69` `test_backfill_deferred_dry_run_is_safe_and_reports`** chạy `scripts/maintenance/backfill_deferred.py --dry-run` qua subprocess không truyền DB. `backfill_deferred.py:263` tạo `ArticleStore(settings["database"]["path"])` = `C:/data/news-scape/monocle.db`, và `ArticleStore.__init__` (`src/db/store.py:285-286`) gọi `init_schema()` → `_migrate` + `executescript(_SCHEMA)` + `commit` + `PRAGMA journal_mode=WAL`. "Dry-run" vẫn mở kết nối ghi và lấy khoá ghi trên DB vận hành; nếu DB đang bị một đợt `--finish` giữ, test có thể chờ tới 30 s hoặc làm chậm đợt. Ghi chú trung thực: lượt chạy test của kiểm toán này đã thực thi test đó, nên đã chạy DDL idempotent lên DB thật một lần (không đổi dữ liệu nghiệp vụ).
- `test_db_path_and_capture_lock.py:27` gọi `config.load_settings()` thật (chỉ đọc cấu hình, không mở DB). Chấp nhận được.
- Node: `test_article_lane.py:560` và `test_article_lane_hardening.py:46` gọi `node`; skip khi thiếu Node. Trên máy này có Node nên không skip.

Đề xuất: truyền `--db <tmp_path>/t.db` (hoặc đặt `MONOCLE_DB_PATH` trong `env=` của subprocess) cho test dry-run; thêm `--dry-run` → `ArticleStore(..., init_schema=False)` + `_connect_ro()` trong `backfill_deferred.py`; thêm fixture autouse trong `conftest.py` đặt `MONOCLE_DB_PATH` về `tmp_path` cho mọi test để chặn cả lớp lỗi này.

### C2.5 Module `src` không có test phủ (ánh xạ import)

77 module (không tính `__init__`). Không test nào import:
- `src.core.logging`
- `src.core.stdio` (chính là lớp chặn lỗi `UnicodeEncodeError` sự cố 2026-09-17; chỉ được phủ gián tiếp qua `test_cli_entrypoints`)
- `src.crawler.http_client` (lớp HTTP thật, có retry/rate-limit; test đều thay bằng `FakeHTTP`)
- `src.monitor.domain_reporter`, `src.monitor.domain_validator` (373 dòng)
- `src.processor.extractor`, `src.processor.segment` (tách đoạn `<p>` là nền của "trích dẫn theo chỉ số đoạn", bất biến Article Lane)

Chỉ có 1 tệp test phủ các module Article Lane cốt lõi: `src.agent.distill`, `src.agent.prefix`, `src.agent.intent_resolve` (đều qua `test_article_lane.py`), `src.db.preflight`, `src.telemetry.dsh_usage` (qua `test_article_lane_hardening.py`).

Script không test nào nhắc tới (36/57), trong đó các script trên đường giao hàng/vận hành hằng ngày: `build_article_prefix.py`, `estimate_wave.py`, `ctx_probe.py`, `db_status.py`, `dbq.py` (chỉ có test cấm), `export_csv.py`, `rederive_from_bronze.py`, `run_user_workflow.py`, `validate_e2e.py`. Script lane mới có test: `article_run`, `article_pack`, `article_expand`, `token_ledger`, `pipeline_radar`, `agent_ingest`, `l1_ingest`, `write_user_output` (chỉ `--help`).

Đề xuất: ưu tiên test đơn vị cho `src.processor.segment` (hợp đồng chỉ số đoạn) và `src.core.stdio`; thêm `write_user_output.py` chạy thật trên DB tạm (hiện chỉ `--help`).

### C2.6 Test cho mã lane đã ngừng (ADR 0010)

| Tệp test | Số test | Đối tượng | Trạng thái |
|---|---|---|---|
| `test_l1_router.py` | 5 | `src.agent.l1_router` | Lane L1 (router còn được `article_expand.py` import) |
| `test_l1_runner.py` | 6 | `src.agent.l1_runner` | Còn dùng bởi `l1_ingest.py` (nạp Article Lane) và `user_workflow` |
| `test_l1_classifier.py` | 6 | `src.agent.l1_classifier` | Bộ đối chiếu tất định, còn hợp lệ |
| `test_agent_infra.py` | 15 | `src.agent.runner` (export + ingest Gold) | Phần export đã chết; phần ingest còn dùng qua `agent_ingest.py` |
| `test_pruner_and_batch.py` | 8 | `pruner`, `packet`, `batch_handoff`, `runner` | Chủ yếu đường export cũ |
| `test_batch_manifest.py` | 3 | `src.agent.manifest` | Chỉ `agent_export.py`, `l1_route.py`, `route_today_l1.py`, `run_agent_hierarchy.py` dùng: toàn lane cũ |
| `test_state_requeue_paths.py` | 3 | `scripts/maintenance/requeue.py` | AGENTS.md cấm gọi `requeue.py` |
| `test_handoff.py` | 7 | `src.handoff.*`, `pipeline.run` | Hàng đợi task cũ |
| `test_cli_entrypoints.py` | 2/11 | `l1_route.py --help`, `agent_export.py --help` trong `AUTOMATION_CLIS` (dòng 25-28) | Danh sách "automation" lỗi thời: hai script này không còn được automation gọi |
| `test_functional_and_hygiene.py::test_l1_runner_dod_registry_enforcement` | 1 | `l1_runner` | Còn hợp lệ nếu `l1_ingest` giữ |

Script lane cũ còn trong cây mã (không test hoặc chỉ test `--help`): `l1_route.py`, `agent_export.py`, `run_agent_hierarchy.py`, `process_l1_pipeline.py`, `verify_gold_quality.py`, `l1_backlog.py`, `test_surface.py`, `auto_pilot.py` (docstring "Điều phối quy trình vận hành Gold"), `maintenance/requeue.py`, `maintenance/route_today_l1.py` (docstring "cho ngày 2026-09-15", không dấu), `maintenance/cleanup_legacy_tasks.py`.

Đề xuất: (1) bỏ `l1_route.py`, `agent_export.py` khỏi `AUTOMATION_CLIS`; (2) lập danh sách xoá/di chuyển vào kho lưu trữ cho 11 script trên cùng test tương ứng (`test_batch_manifest`, `test_state_requeue_paths`, phần export của `test_agent_infra`/`test_pruner_and_batch`) theo story riêng, vì chạm mã đang chạy (`runner.py`, `batch_handoff.py` vẫn được `agent_ingest.py`/`l1_ingest.py` import); (3) thêm test "lane đã ngừng không được import từ đường Article Lane" cùng kiểu `test_no_agent_emulation.py`.

### C2.7 Fixture và helper trùng lặp

- Fixture `env` (tạo `ArticleStore` tmp + `DedupCache` + `chdir`) định nghĩa lại ở **16 tệp**; `_config` ở 13 tệp; `detail_html` 6; `_scraper` 5; `store` 4; `dedup` 4; `feed_bytes` 4; `reg` 3 (`test_entities`, `test_l1_classifier`, `test_l1_router`).
- `conftest.py` chỉ có 1 fixture autouse (`fast_tests`). Mỗi tệp test scraper còn tự `sys.path.insert` dù `conftest.py` đã làm.

Đề xuất: đưa `env`, `store`, `dedup`, `reg` lên `conftest.py` (tham số hoá bằng `request.param` khi cần khác nhau); đưa `_scraper`/`_config` chung sang `tests/_fakes.py`; xoá `sys.path.insert` lặp.

### C2.8 Cảnh báo

550 `DeprecationWarning` từ `feedparser/util.py:80,95` (`updated_parsed` → `published_parsed`) trong 7 tệp test RSS. Chỉ báo mã đọc `entry.updated*` qua ánh xạ tạm sẽ bị gỡ.

Đề xuất: đọc tường minh `entry.get("published_parsed") or entry.get("updated_parsed")` trong `src/scrapers/rss_generic.py`/`rss_capture.py`; thêm `filterwarnings = error::DeprecationWarning:src.*` để bắt sớm.

---

## C3. Tệp cấu hình

### C3.1 `project/config/settings.yaml` (40 dòng)

- Mọi khoá đều có người đọc (`database.path`, `logging.*`, `scheduler.interval_minutes`, `http.*`, `export.*`, `morninger.*` 10 khoá). Không có khoá chết, không có khoá lane cũ.
- Trùng giá trị: toàn bộ khối này được lặp trong `_DEFAULT_SETTINGS` (`src/core/config.py:47-60`) và lặp tiếp ở mặc định `.get(..., x)` trong `src/morninger.py:60, 151-154, 288`. Lệch: `capture_interval_minutes` YAML = 10, mặc định mã = 15 (hai nơi). `database.path` định nghĩa 3 nơi (YAML, `OPERATIONAL_DB_PATH`, fallback trong 2 script bảo trì).
- Comment `:24-32` là nhật ký đo đạc (vi phạm C1.4).
- `http.rate_limit: 3.0` và `timeout: 30` lặp nguyên văn ở **24/24** tệp `config/domains/*.yaml`.

Đề xuất: một nguồn mặc định (`_DEFAULT_SETTINGS`), mã chỉ đọc `cfg["key"]`; domain YAML chỉ ghi khi khác mặc định; rút comment đo đạc về `docs/operations`.

### C3.2 `project/config/token_pricing.yaml`

- `watch_thresholds.worker_turns_expected`: không mã nào đọc (chết). `currency`, `version`, `updated`: không mã nào đọc (siêu dữ liệu, chấp nhận).
- Comment `:32-34` nói sai sự thật: "Hai chốt tự động duy nhất nằm ở article_pack.py (est_ctx_peak) và article_run.py (parse_fail)". Thực tế `est_ctx_peak` chỉ được in (`article_pack.py:533, 603`), `parse_fail` không còn trong `article_run.py`. Comment này mâu thuẫn trực tiếp với bất biến "token là số ghi nhận, không phải cổng" trong `AGENTS.md §6B` và có thể khiến agent sau dựng lại cổng.
- `context_pressure_amber/red` được đọc bởi `pipeline_radar.py:545-547` và `ctx_probe.py:62-64` (hợp lệ, là mức áp suất ngữ cảnh phiên điều phối, không phải token).

Đề xuất: xoá `worker_turns_expected` hoặc cho radar đọc; sửa comment `:32-34` thành "Không có chốt tự động nào dựa trên ngưỡng ở tệp này".

### C3.3 `watchlist.yaml` và `notifications.yaml`

- 30 mã trong `watchlist.yaml` được chép nguyên văn vào rule `watchlist` của `notifications.yaml:10-40`. Hai nguồn sự thật cho cùng danh sách; chưa kể danh mục theo người dùng thật của Article Lane là `config/entities/manifest.yaml`.
- `notifications.yaml` chỉ được `FileNotifier` dùng qua `src/orchestrator.py:91` (đường capture); không thuộc giao hàng Article Lane.

Đề xuất: rule `watchlist` trong `notifications.yaml` tham chiếu `load_watchlist()` (ví dụ `tickers: "@watchlist"`), bỏ danh sách chép.

### C3.4 `config/domains/*.yaml` và `config/entities/*`

- Khoá không mã nào đọc: `cafef.yaml:8 http_method: GET`, `baodautu.yaml:35 title_selector` (comment tự ghi "đối chiếu"). Các khoá `Newstype/PageIndex/PageSize/Type` của cafef được truyền nguyên khối `api.params`, không chết.
- 16/24 domain `enabled: false` với comment "disabled 2026-08-03: focus on cafef + vietstock only", nhưng 8 domain đang bật gồm cả baodautu, fireant, thoibaotaichinhvietnam, tnck, vietnambiz, vneconomy: comment lỗi thời.
- Không tìm thấy khoá lane cũ (`materiality`, `event_type`, `impact_area`, `l1_`, `gold`) trong `config/` (lần xuất hiện `gold` duy nhất ở `cnbc.yaml:13` là từ khoá tin "vàng").

Đề xuất: xoá hai khoá chết; sửa comment `enabled: false` thành lý do trung tính không kèm ngày; cân nhắc chuyển 16 domain tắt vào `config/domains/disabled/` để giảm nhiễu.

### C3.5 `secrets.yaml`

Chỉ có `fireant_token` (không đọc giá trị). Tệp gitignored theo comment; có `secrets.yaml.example`. Đạt.

---

## C4. Đề xuất bộ kiểm tự động (chỉ đề xuất, chưa cài)

Hiện trạng: đã có `scripts/maintenance/audit_codebase.py` (AST + blacklist, gọi qua `harness_cli.py audit --codebase`) nhưng không nằm trong pytest, nên không chặn được lúc chạy `pytest tests/`. Không có `pyproject.toml`/`ruff.toml`/`pytest.ini`.

### C4.1 Test vệ sinh mã bằng AST trong pytest

Thêm `project/tests/test_code_hygiene.py` (tái dùng `BLACKLIST_PATTERNS` từ `audit_codebase.py` để không nhân đôi danh sách):

```python
"""Kiểm vệ sinh docstring và mẫu mã cấm trên src/ và scripts/."""
import ast, io, re, tokenize
from pathlib import Path
import pytest
from scripts.maintenance.audit_codebase import BLACKLIST_PATTERNS

ROOT = Path(__file__).resolve().parents[1]
FILES = [p for d in ("src", "scripts") for p in (ROOT / d).rglob("*.py")
         if "__pycache__" not in p.parts]
HISTORY = re.compile(r"\b(trước đây|trước kia|W\d{3})\b", re.I)

def _texts(tree, src):
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (d := ast.get_docstring(n)):
                yield getattr(n, "lineno", 1), d
    for t in tokenize.generate_tokens(io.StringIO(src).readline):
        if t.type == tokenize.COMMENT:
            yield t.start[0], t.string

@pytest.mark.parametrize("path", FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_hygiene(path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert ast.get_docstring(tree), "thiếu module docstring"
    bad = []
    for ln, text in _texts(tree, src):
        bad += [f"{ln}: {p.pattern}" for p in BLACKLIST_PATTERNS if p.search(text)]
        if HISTORY.search(text):
            bad.append(f"{ln}: comment kể lịch sử")
    for n in ast.walk(tree):
        if (isinstance(n, ast.ExceptHandler) and len(n.body) == 1
                and isinstance(n.body[0], ast.Pass)
                and (n.type is None or getattr(n.type, "id", "") in ("Exception", "BaseException"))):
            bad.append(f"{n.lineno}: except Exception: pass")
    assert not bad, "\n".join(bad)
```

Triển khai theo bậc: bậc 1 (module docstring + blacklist + emoji trong docstring/comment) bật ngay vì hiện đã sạch gần hết (2 tệp thiếu module docstring); bậc 2 (lịch sử, nuốt lỗi) chạy với danh sách ngoại lệ đóng băng (`ALLOWLIST` 31 + 20 vị trí hiện tại) và chỉ được giảm dần; bậc 3 (`Args/Returns` cho hàm công khai) giao cho ruff `D417`.

### C4.2 Cấu hình ruff tối thiểu (`project/ruff.toml`)

```toml
target-version = "py313"
line-length = 110
extend-exclude = ["thamkhao", "data", "domains"]

[lint]
select = [
  "E9", "F",          # lỗi cú pháp, tên chưa định nghĩa, import thừa
  "D100", "D103", "D417",  # module/hàm công khai thiếu docstring, thiếu mục Args
  "BLE001",           # except Exception rộng
  "S110",             # try-except-pass
  "T201",             # print
  "ANN001", "ANN201", # thiếu type hint tham số/trả về
  "PLR2004",          # số ma thuật trong so sánh
]
[lint.pydocstyle]
convention = "google"
[lint.per-file-ignores]
"scripts/**" = ["T201", "PLR2004"]   # CLI được in ra stdout
"tests/**"   = ["D", "ANN", "S110", "PLR2004", "T201"]
```

Chạy trước ở chế độ báo cáo (`ruff check --statistics`), lưu baseline, rồi bật `--exit-non-zero-on-fix` trong `harness_cli.py audit --codebase`.

### C4.3 Cấu hình pytest (`project/pytest.ini`)

```ini
[pytest]
testpaths = tests
markers =
    slow: test có subprocess hoặc > 5 s
filterwarnings =
    error::DeprecationWarning:src.*
```

Kèm fixture autouse trong `conftest.py` đặt `MONOCLE_DB_PATH` về `tmp_path` (chặn C2.4), và lệnh nhanh `pytest -m "not slow"` cho vòng lặp phát triển.

---

## Danh sách hành động xếp theo ưu tiên

1. **Cao**: cô lập DB trong `test_backfill_deferred_dry_run_is_safe_and_reports` và cho `--dry-run` mở DB chỉ đọc (C2.4).
2. **Cao**: `dod.py:55` không được nuốt lỗi cấu hình ngưỡng DoD (C1.5).
3. **Cao**: sửa comment sai sự thật `token_pricing.yaml:32-34` (C3.2).
4. **Trung bình**: sửa 2 test fail (`test_harness_cli.py:55` lỗi thời; lock test flaky) và bỏ `l1_route`/`agent_export` khỏi `AUTOMATION_CLIS` (C2.1, C2.2, C2.6).
5. **Trung bình**: docstring cho `store.py` và `harness_cli.py` (29 hàm) (C1.1).
6. **Trung bình**: test đơn vị cho `src.processor.segment`, `src.core.stdio`, `src.crawler.http_client` (C2.5).
7. **Thấp**: gom fixture `env` (16 bản) về `conftest.py`; tăng tốc `test_baodautu.py` (C2.3, C2.7).
8. **Thấp**: dọn 31 comment lịch sử, 7 đường dẫn cứng, khoá cấu hình chết và trùng (C1.4, C1.7, C3).
9. **Nền**: cài C4.1 + C4.2 theo bậc để chặn tái phát.
