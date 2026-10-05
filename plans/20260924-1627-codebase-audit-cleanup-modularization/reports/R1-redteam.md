# R1 — Phản biện đỏ cho đợt kiểm toán A–E (news-scape)

- Ngày: 2026-09-24, khoảng 16:00–16:30. Nhánh `feature/article-lane-remove-gates` @ `45b3f0a`, còn 4 tệp chưa commit do một phiên khác đang sửa: `AGENTS.md`, `dsh-preflight-validator/SKILL.md`, `pipeline_radar.py`, `rules/09`.
- Chế độ: chỉ đọc. DB mở bằng `mode=ro`. Bản sao DB trong OneDrive mở bằng `mode=ro&immutable=1`, để không sinh `-shm`. Script tạm nằm ở `scratchpad/audit/r1/`: `r1_db*.py`, `r1_h.py`, `r1_wave.py`, `r1_groups.py`, `r1_split.py`, `r1_src.py`.
- Nhãn phán quyết: **XÁC NHẬN** · **BÁC BỎ** · **CHỈNH** (đúng một phần, hoặc đúng nhưng hệ quả hay mức độ sai).

## 0. Bối cảnh vận hành lúc kiểm (các báo cáo gốc không thấy)

1. **Một đợt Article Lane đang chạy dở.** Đợt `W09241605` được đóng gói lúc 16:06 và có repair lúc 16:09. `--finish` đang nạp: `l1_outputs` đạt 415/415 lúc 16:14. Số dòng `agent_outputs` của đợt tăng từ 34 lên 95 giữa hai truy vấn cách nhau vài phút, dòng mới nhất lúc 16:16. Không báo cáo nào nhắc tới đợt này. Báo cáo E chỉ biết W1, W2 và W365.
2. **Morninger đang chạy** (pid 15784 → 46052, khởi động 15:35), kèm tiến trình con `backfill_deferred.py` (pid 77712, 16:12). `dsh web` chạy từ 23/09 17:32.
3. **Cây làm việc chính là runtime.** Morninger, `backfill_deferred` (nạp lại từ đĩa mỗi 10 phút) và `article_run` đều chạy mã ngay trong thư mục này. Mọi `git mv`, `git rm`, `checkout` hay sửa dở trong cây này có hiệu lực tức thì với tiến trình con kế tiếp.

## 1. Bảng phán quyết

### 1.1 Đề xuất xoá hoặc archive

| Mục | Báo cáo gốc | Phán quyết | Bằng chứng | Hệ quả cho plan |
|---|---|---|---|---|
| `run_agent_hierarchy`, `l1_backlog`, `route_today_l1`, `process_l1_pipeline`, `run_validation`, `test_surface`, `inspect_catalog`, `cleanup_legacy_tasks`, `validate_e2e` | A §1a/§1c | **XÁC NHẬN** | `git grep` ngoài md/docs/plans không có người gọi nào, trừ cặp `run_validation → process_l1_pipeline` và một comment ở `entities.py:319`. Preset DSH (`agent.cordis.yml`, skill `dsh-conductor`) chỉ trỏ `article_run`, `write_user_output`, `pipeline_radar`, `build_article_prefix`. Task Scheduler không gọi tệp nào trong nhóm này | Làm được |
| `clean_yahoo_lifestyle.py` | A §1a | **XÁC NHẬN, và nặng hơn A nói** | `sqlite3.connect("data/monocle.db")` nằm ở **cấp module** (`:18`), nên chỉ cần import hoặc chạy là mở DB cũ trong OneDrive | Xoá sớm |
| `l1_route`, `agent_export`, `auto_pilot`, `run_daily.ps1`, `clean_completed_packets`, `requeue`, `verify_gold_quality`, `run_user_workflow` + `user_workflow` | A §1b | **XÁC NHẬN** | Người gọi chỉ là script chết và test nạp qua `importlib.util.spec_from_file_location` (`test_destructive_automation_guards.py:26-34`, `test_state_requeue_paths.py:25-29`). A đã liệt kê đủ các test này | Làm được. Riêng `.agents/dsh/RUNBOOK.md:190` là **false positive**: chữ "requeue item" ở đó nghĩa là chạy lại bản ghi hỏng, không phải `requeue.py` |
| `src/agent/packet.py` | A §1b + lệnh ở §6 | **CHỈNH (thứ tự nguy hiểm)** | `runner.py:11` import `packet` **ở đầu module**. `agent_ingest.py` import `AgentRunner`. Lệnh `git rm` ở A §6 xoá `packet.py` ở bước 3, trong khi import ở `runner.py` chỉ được gỡ ở bước 4 (§2) | Làm theo đúng thứ tự A thì `agent_ingest` hỏng ngay khi import, và `--finish` của đợt kế tiếp chết ở bước ingest. **Phải gỡ `export_tasks` cùng import trước, rồi mới xoá `packet.py`, trong cùng một commit** |
| `src/agent/l1_classifier.py` | A (xoá), C2.6 ("bộ đối chiếu tất định, còn hợp lệ") | **A đúng, C sai** | Đối chiếu tất định của Article Lane dùng `reg.detect` (`article_expand.py:382`). Tuy vậy `l1_router.py:8` và `l1_runner.py:9` vẫn import module này ở đầu tệp | Chỉ xoá sau khi gỡ import ở cả hai module sống. Nếu không, `l1_ingest` hỏng |
| `src/agent/archive.py` + khối archive trong hai lệnh nạp | A §2, E-07 | **XÁC NHẬN, có bằng chứng sống** | Số tệp trong `data/agent_tasks/l1` giảm từ 183 (lúc A đếm) xuống **181**, và còn 38 tệp `l1_batch_*`. Vòng dọn ở `l1_ingest.py:83-88` đã xoá 2 packet lane cũ trong lần `--finish` của W09241605 lúc 16:14. `archive.py:71` còn `mkdir(parents=True)` | Nếu chỉ chuyển `data/agent_tasks/l1` và `archive/` (A §0) mà chưa gỡ khối này, lần `--finish` kế tiếp sẽ **tạo lại** `data/agent_tasks/l1/archive/<ngày>`. Gỡ khối này, hoặc truyền `--no-archive`, trước hoặc cùng lúc với việc chuyển thư mục |
| Job `reclaim` + `Catalog.claim` | A §2, E §1.3 | **XÁC NHẬN** | `work_items` không có dòng `claimed` nào (`done 834, failed 1, held 4, pending 9337`) | Phải khởi động lại morninger. Khoá `reclaim_interval_minutes` trong settings trở thành khoá chết (C3.1 nói "không khoá chết" thì sẽ sai) |
| `tests/mocks/agent_process_packets.py`, `agent_stub.py` | A §3 | **XÁC NHẬN** | Không có import nào. Tên tệp không bắt đầu bằng `test_`, nên pytest không thu | Làm được |
| `tests/test_handoff.py` | C2.6 (xếp vào nhóm "mã lane đã ngừng") | **BÁC BỎ (C)** | Tệp này kiểm `SilverBuilder`, `WorkPackageBuilder`, `Catalog.enqueue`, `process_meta`, tức Silver đang chạy | Không được xoá |
| `./.venv` ở gốc | A §4: "(a) rỗng/hỏng, xoá" | **CHỈNH (false positive về mức an toàn)** | VS Code đang chạy jedi language server từ `…news-scape\.venv\Scripts\python.exe` (pid 74852/73072/18428/7676, từ 15/09). E §5 đã thấy điều này, A thì không | Xoá lúc VS Code còn mở sẽ gặp tệp bị khoá, xoá được một nửa, rồi OneDrive đồng bộ trạng thái dở đó. Làm theo thứ tự: đổi interpreter sang `C:\venvs\news-scape`, đóng VS Code, rồi mới xoá |
| `project/.venv` (564 MB) | A §4: "tạo trên máy khác, vô dụng" | **CHỈNH** | `pyvenv.cfg home = C:\Users\An Thanh Pham\…`, tức máy thứ hai của cùng người dùng. Hai máy (DESKTOP-RSG7M2C và FPA-AnPT) cùng đồng bộ OneDrive này, xem các tệp xung đột theo tên máy và `build_entities.py:30-31` | Xoá ở đây là **xoá luôn trên máy kia**. `run_pipeline.ps1:10` và `okf/tools/okf_check.py` + `README.md:9-12` ưu tiên venv này. Phải hỏi người dùng máy kia còn dùng không, và sửa tham chiếu trước |
| `project/src/data/` | A §4: "(a) Xoá", lệnh `Remove-Item -Recurse -Force` ở §6 | **BÁC BỎ, NGUY HIỂM** | `r1_src.py`: **767/1.083 tệp raw HTML** trong `src/data/raw_html` (cafef 533, vietstock 118, vneconomy 116) **không có bản nào** trong `project/data/raw_html` hay `C:\data\news-scape\raw_html`. DB `src/data/monocle.db` có **237 bài** không có trong DB vận hành. Thư mục bị gitignore (`.gitignore: project/src/data/`), nên git không giữ bản nào | Vi phạm bất biến "Bảo toàn raw gốc" (AGENTS §6B). Chỉ được **chuyển** ra `C:\data\news-scape\backups\src-data-20260903\`, kèm MANIFEST. Không xoá |
| DB cũ trong `project/data/` | A §4: "(d) chuyển sang backups" | **CHỈNH** | (1) `monocle.db` có **163 bài** không có trong DB vận hành (ảnh chụp tới 08/09). (2) `monocle_review.db` **không phải rác**: rule 03 `:21,:40` quy định đây là snapshot BI bắt buộc và là tệp chia sẻ qua SharePoint. `db_snapshot.py --out` mặc định ghi lại đúng đường dẫn này | Chuyển `monocle.db` và các bản backup đi thì được, nhưng không xoá. Giữ `monocle_review.db`, hoặc sửa rule 03 cùng lúc, cần người dùng quyết |
| `project/data/archive_conflicts/*.db` | A §4: "chuyển hoặc xoá" | **CHỈNH** | Chưa đối chiếu dữ liệu riêng. Đây là bản xung đột của hai máy (19/08, 25/08) | Chỉ chuyển, không xoá, cho tới khi đối chiếu xong |
| `project/daily_log.txt` | A §4: "không mã nào ghi, chắc do redirect tay" | **BÁC BỎ** | Task Scheduler `\news_cron` chạy `cmd.exe /c python scripts/run_once.py >> daily_log.txt` với cwd `project`. Task đang **Disabled**, nhưng trigger hằng ngày 16:00 vẫn đặt `NextRunTime 25/09 16:00`. Lần chạy cuối 23/09 16:11, mã lỗi `0x8007042B`. Nội dung đuôi tệp khớp log `run_once`. Không báo cáo nào nhắc tới task này (chỉ comment ở `test_cli_entrypoints.py:21`) | Thêm vào plan: xoá hẳn task `news_cron`, hoặc ghi rõ task này đã ngừng. Task gọi `python` trần. Bật lại thì đua với morninger (khoá `capture.lock` mới sẽ chặn) |
| `./data/` ở gốc | A §4 | **XÁC NHẬN** | Chỉ có đầu ra lane cũ (17/09), không mã nào đọc | Lệnh ở A §6 ghi `MANIFEST.json` bằng `Out-File -Encoding utf8` của PowerShell 5.1, tức **có BOM**. Mục mới cũng là tên thư mục, trong khi MANIFEST hiện liệt kê từng tệp. Dùng Python, hoặc `[IO.File]::WriteAllText` không BOM |
| `.agents/skills/git-codebase-governance/scripts/audit_codebase.py` | A §1c | **XÁC NHẬN** | `harness_cli.py:511-519` nạp bản ở `project/scripts/maintenance/` bằng `spec_from_file_location` | Làm được |
| `monitor_daily` + `daily_reporter`, `domain_check` | A (d) | **XÁC NHẬN là (d)** | Chỉ `run_daily.ps1:152-156` gọi | Cần người dùng quyết |

### 1.2 Khẳng định số liệu

| Mục | Báo cáo gốc | Phán quyết | Bằng chứng | Hệ quả |
|---|---|---|---|---|
| A-1: lane L1 chạy tới 15:17 | A §0 | **XÁC NHẬN phần log, BÁC BỎ phần DB** | `monocle.log:11405` cho 15:17:41 `run_l1_route`. Có hai lần shutdown (15:31 và 15:32, đúng hai tiến trình), rồi `15:35:51 started … reclaim/30min`, không còn `l1_route`. Nhưng A viết "các dòng `l1_outputs` với `l1_source='code_first'` sinh trong 23–24/09" là **sai**: dòng `code_first` mới nhất là **2026-09-17 16:47** (0 dòng từ 18/09). Chỉ `l1_tasks` nhận dòng mới: `needs_agent/pending` 1.369 và `resolved/pending` 379, `enqueued_at` tối đa 24/09 15:17:40 | Không cần dọn `l1_outputs`. Chỉ đóng băng `l1_tasks` |
| E-01: 20,3% thực thể sai dạng bị loại im lặng | E | **XÁC NHẬN số, CHỈNH mức độ** | Trên 9 tệp W1/W2/W365 đúng 1.055/5.193. Tính cả đợt mới `W09241605` là 1.564/8.350 (18,7%). 100% chuỗi sai dạng có `in_list=false`. Tuy vậy toàn bộ là thực thể **thân bài**, `in_title=0`, và thân bài không đi vào DB hay giao hàng (chính E-09). E-01 nói "một phần năm số thực thể bị dồn vào unlisted" nhưng tác động lên `l1_outputs` và xlsx chưa được đo | Tác động giao hàng hiện gần bằng 0. Mức "Cao" chỉ đứng được nếu T3.7 được làm. Muốn nói tới lớp tiêu đề thì phải đo `unlisted_candidates` riêng |
| E-02: 838 dòng provenance sai | E | **CHỈNH** | 838 là tổng `antigravity/flash`, trong đó **174 dòng có từ trước 18/09**. Riêng 10/09 còn `processing_metadata` thật với `confidence` 0,86–0,95, tức đúng là do Antigravity sinh. Chắc chắn gán sai là **664 dòng** (18/09 trở đi, toàn `confidence=0.9`). Con số còn tăng: đợt W09241605 đang thêm dòng `antigravity/flash/0.9` ngay lúc kiểm (+98) | Script sửa dữ liệu phải lọc `created_at >= '2026-09-18'`, hoặc lọc theo hình dạng v2-lean. Không `UPDATE` cả 838 dòng. Sửa mã trước, rồi mới sửa dữ liệu, để dòng sai không tiếp tục sinh |
| E-03: 3 vị từ "L1 đạt" | E, B §3.5 | **XÁC NHẬN** | `article_pack.py:181` loại `code_first`. `article_run.py coverage_of` dùng `max(dod_pass)` không lọc. `user_output.py:27` dùng `l1.dod_pass = 1` không lọc. `l1_outputs.article_id UNIQUE`. 3.069 bài chỉ có dòng `code_first` đạt | Đúng như E mô tả. B coi khác biệt ở giao hàng có thể là chủ ý (ADR 0003). Cần người dùng quyết |
| E-04: Silver ghi đè theo `article_id` | E | **XÁC NHẬN** | `work_package.py:83-86`: đường dẫn `<domain>/<ngày>/<article_id>.json`, `os.replace`. `agent_outputs UNIQUE(article_id, raw_sha256)`. Có 44 dòng lỗi `raw_sha256`, mới nhất 23/09 16:55. E ghi "1 dòng", thực tế **44** | Mức độ nên nâng lên |
| E-07a: cổng thật là 100% | E | **XÁC NHẬN cơ chế, CHỈNH lập luận** | `l1_ingest.py:96` và `agent_ingest.py:77` trả 1 khi `failed>0`. `article_run.py:543-549` dừng trước bước `verify`. Nhưng đây là **thay đổi có chủ ý** của commit `46f617f` ngày 23/09. Câu về W2 là suy luận [I]: bài vắng mặt không làm lệnh nạp trượt, chỉ bài **bị DoD loại** mới làm trượt | Đề xuất "mã 3 = lỗi mềm" đảo ngược một quyết định mới của người dùng. Phải là quyết định của người dùng, sửa AGENTS §6B cùng lúc, không tự làm |
| E-07b / D §5.5: `token_ledger` trùng dòng | E, D | **XÁC NHẬN** | W2 có 4 dòng (2,058M → 2,247M token), W365 có 3 dòng (8,36M → 9,35M). Đây là ảnh chụp cộng dồn, không phải bản sao y hệt, nên cộng các dòng lại là đếm trùng | Cách Cấp 2 an toàn nhất là để `report` chỉ lấy dòng mới nhất mỗi đợt, không xoá dòng. "Tự xoá dòng cùng đợt" (E) là ghi vào Harness Core |
| C: test ghi DB thật | C2.4 | **XÁC NHẬN** | `test_cli_entrypoints.py:56-69` chạy `backfill_deferred.py --dry-run` không có `env` và không có `--db`. `:263` gọi `ArticleStore(settings path)`, `store.py:285` chạy `init_schema` (DDL, WAL, commit) lên `C:/data/news-scape/monocle.db`. Ngoài ra không test nào khác chạm DB thật | Ghi thêm: trong lúc một đợt `--finish` đang chạy như bây giờ, test này tranh khoá ghi với đợt |
| C: tệp test khoá chưa được track | C2.2 | **LỖI THỜI** | Tệp đã được commit ở `45b3f0a` | — |
| E §5: `TESTBLOCK2` rò từ test | E | **BÁC BỎ phần nguyên nhân** | Không test hay script nào chứa chuỗi `TESTBLOCK`. Tệp tạo lúc 23/09 17:28, tức do **chạy tay** | Đề xuất "test dùng `tmp_path`" không trúng. Chỉ cần dọn tay |
| D: trace #80 vi phạm quy trình | D §5.2 | **XÁC NHẬN** | `trace.id=80`: `story_id NULL`, `intake_id NULL`. Tệp sửa gồm `AGENTS.md`, `registry.yaml`, `pipeline.yaml`, `user_output.py` và test. Bảng `decision` chỉ có 0001/0002/0006/0010 | Lập ADR hồi tố như D đề xuất |
| D: backlog có 19 mục mở | D §5.4 | **CHỈNH** | Hiện có 21 mục mở, 7 mục resolved | Số đã đổi. Sinh lại từ DB |
| A: "19 script vẫn fallback `data/monocle.db`" | A §4 | **CHỈNH (phóng đại)** | `load_settings()` luôn ghi đè `path` bằng `resolve_db_path` (`config.py:96`), nên mọi `.get("path","data/monocle.db")` là **mã chết, không bao giờ kích hoạt** (B và E nói đúng điều này). Lỗi thật chỉ nằm ở mặc định **không qua `load_settings`**: `csv_export.DB_PATH` (CLI `export_csv.py:34` không truyền đường dẫn, B-V3 **xác nhận**), `snapshot.py:14`, `clean_yahoo_lifestyle.py:18`, `audit_alias_false_positives.py:17` | Ưu tiên B S0. Không cần hoảng với 19 chỗ fallback |
| E-05: "`verify_preconditions` theo cwd" | E | **Chưa bác được, nhưng cần làm rõ** | `ArticleStore` đã neo đường dẫn tương đối theo `PROJECT_ROOT` (`store.py:278-281`). E nói đúng về `raw_html_path` trong `dod.py` và `derive`/`raw_store` mặc định `"data/raw_html"` theo cwd | Giữ đề xuất `paths.py` |

### 1.3 Mâu thuẫn giữa các báo cáo

| Chủ đề | Mâu thuẫn | Kết luận R1 |
|---|---|---|
| `l1_classifier` | A: chết. C: còn hợp lệ | A đúng, nhưng có điều kiện gỡ import (xem 1.1) |
| `test_handoff.py` | C: lane cũ. A: `handoff/*` sống | A đúng |
| `.venv` gốc | A: rỗng, xoá. E: VS Code đang dùng | E đúng về hiện trạng |
| `project/src/data` | A: (a) xoá ngay. E: việc H | Cả hai thiếu: dữ liệu Bronze độc nhất. Chỉ chuyển |
| Đếm hạ tầng | `PROJECT_ROOT` 20 (B) / 22 (E); `sqlite3.connect` 21 lời gọi trong 11 tệp (B) / 15 tệp (E); `"data/monocle.db"` 19 (A) / 12+4 (B) / 20 (E) | Grep lại cho **22** dòng `PROJECT_ROOT`, **21** dòng `sqlite3.connect`, **22** dòng chứa `"data/monocle.db"`. Plan nên dùng một lệnh đếm chung (`git grep -c`) làm baseline |
| Cấp của việc sửa `registry.yaml` | A và D: Cấp 3 (Harness Core). E §4 (jev US-028 "dọn registry"): Cấp 2 | Theo AGENTS §0, registry là Harness Core, nên **Cấp 3**. Sửa E |
| `token_ledger` | E: Cấp 3, hoặc "xoá dòng cùng đợt" ở Cấp 2. D: thêm khoá + migration 004. B S9: dời mã là Cấp 3 | Chọn "report lấy dòng mới nhất" (Cấp 2, chỉ đọc). Schema để ADR |
| Cổng `--finish` | E-07 muốn nới (mã 3). Commit `46f617f` vừa siết. A và D im lặng | Cần người dùng quyết |
| `SESSION-LATEST` "2 cặp tiến trình" | E: lỗi thời | Xác nhận: hiện chỉ còn một cặp |

## 2. Điều cả năm báo cáo bỏ sót

1. **Dữ liệu Bronze độc nhất ngoài chỗ vận hành.** Có 767 tệp raw trong `project/src/data`, và các DB cũ mang 163 + 237 bài không có trong DB vận hành. Nơi chứa đều bị gitignore và chỉ có OneDrive giữ. Bronze vận hành (`project/data/raw_html`, theo cwd) cũng nằm trong OneDrive và bị gitignore với chú thích "tái scrape được". Điều này sai: trang nguồn đổi hoặc gỡ bài thì không cào lại được. `C:\data\news-scape\raw_html` là một bản cũ ngày 08/09, tức đang có **ba kho Bronze** mà không có MANIFEST nào.
2. **OneDrive hai máy.** Xoá hay chuyển 1,7 GB trong OneDrive sẽ lan sang máy thứ hai và vào thùng rác OneDrive. `.git/` cũng nằm trong OneDrive, nên một loạt `git mv`/`git rm` lúc OneDrive đang đồng bộ có thể làm hỏng index hoặc sinh bản xung đột `-DESKTOP-*`. Nên tạm dừng đồng bộ OneDrive khi thao tác git hàng loạt.
3. **`harness.db` không có bản sao nào ngoài OneDrive.** Tệp bị gitignore (`harness.db*`) và chạy WAL. Đây là nơi duy nhất giữ story, trace, decision và token_ledger. E nêu rủi ro WAL, nhưng không ai đề xuất sao lưu trước khi dọn backlog hay story (D mục 7).
4. **Task `\news_cron`** (xem 1.1): đang Disabled nhưng còn trigger, gọi `python` trần, ghi `daily_log.txt`.
5. **Đợt W09241605 đang chạy** (§0). Mọi kế hoạch cần một bước "radar báo không có đợt dở" trước khi đụng mã nạp.
6. **`monocle_review.db` là hiện vật của rule 03**, dùng cho BI và SharePoint, không phải rác.
7. **Secrets:** `secrets.yaml` bị gitignore, không có trong lịch sử git, và grep không thấy token trong tệp được track. Git không có blob nào lớn hơn 2 MB. Mục này **đạt**, không cần hành động.
8. **Xung đột với phiên song song.** 4 tệp chưa commit, gồm `AGENTS.md`, skill preflight và `pipeline_radar.py`, đang bị phiên khác sửa. Đó đúng là các tệp mà A §5 và D mục 2 đề xuất sửa. Hai phiên cùng sửa sẽ ghi đè lên nhau.

## 3. Rủi ro vận hành khi dọn

**Làm được khi morninger đang chạy và không có đợt nào dở** (radar `status` không báo lô dở hay `--finish` đang chạy):
- Xoá mã chết chắc ở A §1a. Không có tiến trình nào nạp các tệp này.
- Sửa tài liệu và skill, sau khi phiên kia đã commit xong 4 tệp.
- Chuyển `./data` ở gốc và `project/data/agent_tasks/l1`. Điều kiện: khối archive ở `l1_ingest`/`agent_ingest` đã được gỡ, hoặc chấp nhận thư mục rỗng sinh lại.

**Phải dừng morninger trước khi làm** (vì `backfill_deferred` và job trong morninger nạp lại module từ đĩa):
- Sửa `store.py`, `catalog.py`, `config.py`, `morninger.py` (gỡ job `reclaim`), và các bước S2/S11/S12 của B (`paths`, `infra.db`, `pyproject`, `pip install -e` vào venv đang chạy).
- Mọi `git checkout`, `git stash` hay chuyển nhánh trong cây này.

**Không được làm khi một đợt đang dở (từ lúc đóng gói tới lúc `--finish` in HOÀN TẤT):**
- Gỡ `export_tasks`, xoá `packet.py`, sửa `l1_router`/`l1_runner`/`batch_handoff`/`dod.py`/`runner.py`, đổi mã thoát lệnh nạp. Những việc này làm vỡ bước ingest hoặc đổi cổng giữa đợt.
- Chuyển hoặc đổi tên `data/agent_tasks/article`, `data/agent_outputs*`, `data/work_packages`, `data/raw_html`.
- Chạy `pytest` toàn bộ: `test_cli_entrypoints` tranh khoá ghi DB.

**Phải có người và thao tác ngoài kho:**
- Đổi interpreter VS Code, rồi mới xoá `.venv` gốc.
- Hỏi về máy thứ hai trước khi xoá `project/.venv`.
- Khởi động lại `dsh web` sau khi sửa preset hay persona.
- Xoá hẳn task `news_cron`.
- Sao lưu `harness.db` và các kho Bronze trước mọi đợt dọn.

## 4. Sửa đổi bắt buộc cho plan tổng hợp

1. Rút `project/src/data` khỏi mọi lệnh `Remove-Item`. Chuyển nó ra ngoài OneDrive kèm MANIFEST.
2. Ghép "gỡ `export_tasks` + import `packet`" với "xoá `packet.py`" vào một commit. Làm tương tự với `l1_classifier` và hai import của nó.
3. Thêm bước 0 cho mọi story đụng mã: radar không báo đợt dở, và dừng morninger khi sửa `src/db`, `src/handoff`, `src/core`, `src/morninger.py`.
4. Chỉnh E-02 thành 664 dòng từ 18/09, và sửa mã trước khi sửa dữ liệu.
5. Đưa E-07 (nới cổng) vào danh sách quyết định của người dùng. Không làm như Cấp 2 tự động.
6. Thêm các mục: task `news_cron`, sao lưu `harness.db`, MANIFEST cho ba kho Bronze, trạng thái của `monocle_review.db`, tạm dừng OneDrive khi thao tác git hàng loạt, và phối hợp với phiên đang giữ 4 tệp chưa commit.
