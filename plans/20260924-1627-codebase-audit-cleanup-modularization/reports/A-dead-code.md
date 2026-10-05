# Kiểm toán A — Mã chết và di sản lane L1/Gold (news-scape)

- Ngày: 2026-09-24 · Nhánh: `feature/article-lane-remove-gates` · Phiên: kiểm toán, CHỈ ĐỌC
- Căn cứ: ADR 0010, AGENTS.md §6
- Phương pháp:
  1. Dựng đồ thị import bằng AST cho `project/src`, `project/scripts` và `project/tests` (script `scratchpad/audit/graph.py`). Đồ thị có tính cả lời gọi subprocess dạng chuỗi `"xxx.py"` và `SCRIPTS / "xxx.py"`.
  2. Tính tập tệp tới được từ các gốc vận hành: `src/morninger.py`, `src/orchestrator.py`, `scripts/article_run.py`, `scripts/pipeline_radar.py`, `scripts/write_user_output.py`, `scripts/run_once.py`, `src/monitor/health.py`. Kết quả: 78 tệp tới được.
  3. Grep tên tệp và tên ký hiệu trên mọi tệp được git theo dõi (.py/.ps1/.yaml/.ts/.json/.md), bỏ `project/data/` và `archive`. Tham chiếu được chia thành các nhóm code, test, cfg, orch (`.agents/dsh`, `registry.yaml`, `pipeline.yaml`) và doc.
  4. Đối chiếu log vận hành `project/logs/monocle.log` và dấu thời gian tệp, chỉ đọc.
- Tệp số liệu thô: `scratchpad/audit/refs.json` (tham chiếu theo từng tệp), `edges.json` (đồ thị import), `reach.json` (tập tới được).

Phân loại:
- **(a) CHẾT CHẮC**: không mã, test hay cấu hình nào tham chiếu. Chỉ còn tài liệu nhắc tới, hoặc không còn gì.
- **(b) CHẾT, CÒN TEST/TÀI LIỆU**: phải gỡ test và cấu hình kèm theo, nếu không test vỡ.
- **(c) SỐNG MỘT PHẦN**: tệp nằm trên đường Article Lane nhưng mang theo phần của lane cũ. Cần tách phần sống ra.
- **(d) NGHI NGỜ**: công cụ vận hành thủ công hoặc để dành. Cần người xác nhận.

---

## 0. Phát hiện khẩn: lane L1 vẫn chạy thật tới 15:17 hôm nay

Bằng chứng từ `project/logs/monocle.log`:
- `11381: 2026-09-24 15:02:40 | __main__:run_l1_route:208 | [morninger] l1_route: 📦 Đã đóng gói 2 mini-batch L1 ...`
- `11405: 2026-09-24 15:17:41 ... run_l1_route ...`. Có 104 dòng `l1` trong ngày 24/09. Lần cuối ghi `code-first -> DB l1_tasks` lúc `2026-09-24 09:05:10`.
- Sau đó `15:32:39 Morninger shutdown`, rồi `15:35:51 Morninger started: capture/10min, derive/30min, reclaim/30min, drift/6:0`, tức tiến trình mới không còn job `l1_route`.

Hệ quả: tiến trình `morninger` khởi động trước ADR 0010 đã chạy `l1_route` và `l1_ingest --code-first` thêm khoảng 30 giờ sau quyết định, đúng rủi ro ADR 0010 §3 đã nêu. Tồn dư còn lại:
- 183 packet mới trong `project/data/agent_tasks/l1/`: 24 tệp từ 23/09 17:xx và 159 tệp ngày 24/09 từ 09:xx tới 15:17.
- Các dòng `l1_tasks` và `l1_outputs` với `l1_source='code_first'` sinh trong hai ngày 23–24/09. Các dòng này đã bị bộ chọn bài loại (`scripts/article_pack.py:181 ANALYZED_L1`), nên không làm hỏng Article Lane.

**Hành động:** chuyển `project/data/agent_tasks/l1/` sang `project/data/archive/legacy-lane-20260923/agent_tasks/l1-late-20260924/`, bổ sung mục vào `MANIFEST.json` (lệnh ở §6). Ghi vào `docs/SESSION-LATEST.md` rằng morninger đã khởi động lại lúc 15:35 ngày 24/09. Không cần sửa DB.

---

## 1. `project/scripts/` và `project/scripts/maintenance/`

Tập tới được từ các gốc gồm: `article_run`, `article_pack`, `article_expand`, `build_article_prefix`, `ctx_probe`, `handoff`, `l1_ingest`, `agent_ingest`, `token_ledger`, `pipeline_radar`, `run_once`, `write_user_output` và `maintenance/backfill_deferred`. Nguồn: `article_run.py:88,412,519,537,561,571,575` và `morninger.py:155`. Radar còn khuyến nghị `validate_capture.py` (`pipeline_radar.py:296`), nên tệp này cũng sống.

### 1a. CHẾT CHẮC

| Tệp | LOC | Bằng chứng reachability | Hành động | Tham chiếu phải sửa kèm | Rủi ro |
|---|---|---|---|---|---|
| `scripts/run_agent_hierarchy.py` | 328 | Không mã hay test nào import. Tệp này gọi `l1_route.py` (`:81`) và `agent_export.py` (`:102`), cả hai bị ADR 0010 cấm. Chỉ tài liệu nhắc tới (US-003/004/007/009, `okf/catalog/playbooks/daily_agent_run.md`). | Chuyển vào archive | Không có (test không phụ thuộc) | Thấp |
| `scripts/l1_backlog.py` | 172 | 0 tham chiếu từ mã hay test. Tệp in lệnh `l1_route.py` (`:127,133`) và `agent_export.py` (`:137`). Chỉ doc nhắc: `docs/OPEN-ITEMS.md`, `project/docs/operations/backlog-drain-runbook.md`. | Chuyển vào archive | Sửa `project/docs/operations/backlog-drain-runbook.md` và `docs/OPEN-ITEMS.md` | Thấp |
| `scripts/maintenance/route_today_l1.py` | 75 | Script dùng một lần, docstring ghi "cho ngày 2026-09-15". Không ai import. Chỉ `plans/20260924-research-council-execution/plan.md` nhắc tới. | Xoá (git giữ lịch sử) | Không | Thấp |
| `scripts/process_l1_pipeline.py` | 27 | Chỉ `run_validation.py:10` import. `run_validation.py` thì không ai gọi. | Xoá cả cụm | Bỏ comment ở `src/agent/entities.py:319` | Thấp |
| `scripts/run_validation.py` | 41 | 0 tham chiếu, trừ `plans/20260924-...` | Xoá | Không | Thấp |
| `scripts/test_surface.py` | 71 | 0 tham chiếu, kể cả tài liệu. Tên dễ nhầm với test pytest. | Xoá | Không | Thấp |
| `scripts/inspect_catalog.py` | 11 | 0 tham chiếu. Chỉ in số entity, không có docstring. | Xoá | Không | Thấp |
| `scripts/maintenance/cleanup_legacy_tasks.py` | 53 | 0 tham chiếu. Dọn `data/agent_tasks` của lane cũ. | Xoá | Không | Thấp |
| `scripts/maintenance/clean_yahoo_lifestyle.py` | 37 | 0 tham chiếu. Dòng `:18` có `sqlite3.connect("data/monocle.db")` cứng, trỏ vào **bản sao DB cũ trong OneDrive** chứ không phải `C:\data\news-scape\monocle.db`. | Xoá. Nếu còn cần thì viết lại qua `resolve_db_path` | Không | Trung bình: chạy nhầm sẽ ghi vào DB cũ |

### 1b. CHẾT NHƯNG CÒN TEST HOẶC TÀI LIỆU

| Tệp | LOC | Bằng chứng reachability | Hành động | Tham chiếu phải sửa kèm | Rủi ro |
|---|---|---|---|---|---|
| `scripts/l1_route.py` | 205 | Bị AGENTS.md §6 cấm. Người gọi: `run_agent_hierarchy.py:81`, `run_daily.ps1:96`, và một comment trong `run_pipeline.ps1`. Test: `tests/test_cli_entrypoints.py:25`. Registry: `.agents/registry.yaml:56-57` (l1-router, `status: retired`). | Chuyển vào archive | Bỏ dòng `:25` khỏi `AUTOMATION_CLIS` trong `test_cli_entrypoints.py`. Ghi `entrypoint: archived` cho mục `l1-router` ở `registry.yaml:56`. Xoá comment ở `run_pipeline.ps1:22-23`. | Thấp |
| `scripts/agent_export.py` | 101 | Bị cấm. Người gọi: `auto_pilot.py:149`, `run_agent_hierarchy.py:102`, `run_daily.ps1:103,105`. Test: `test_cli_entrypoints.py:27`. Registry `:85-86` (gold-exporter, retired). | Chuyển vào archive | Bỏ `test_cli_entrypoints.py:27`. Sửa `registry.yaml:85`. | Thấp |
| `scripts/run_daily.ps1` | 168 | Người dùng đã xác nhận `Get-ScheduledTask` không đăng ký tệp này. Tệp gọi `l1_route` (`:96`), `agent_export` (`:103,105`), `compile_users` (`:95`), `clean_completed_packets` (`:129`) và `monitor_daily` (`:152-156`). Test chỉ nhắc trong comment (`test_cli_entrypoints.py:21`). | Chuyển vào archive | Sửa comment ở `test_cli_entrypoints.py:21`, `auto_pilot.py:30` và `clean_completed_packets.py:3`. Sửa doc: `okf/catalog/pipelines/morninger.md`, `okf/catalog/playbooks/daily_agent_run.md`, `okf/MAPPING.md`. | Thấp |
| `scripts/auto_pilot.py` | 246 | Docstring ghi "Điều phối quy trình vận hành Gold". Tệp gọi `agent_export.py` (`:149`). Chỉ test dùng tới: `tests/test_destructive_automation_guards.py:31-34`, cùng các test `:139,145,156,162`. | Chuyển vào archive | Gỡ 4 test auto_pilot trong `test_destructive_automation_guards.py:139-173` và khối `_SPEC_AP` ở `:31-34`. Sửa doc ADR 0008 và 0009 (chỉ là ghi chú lịch sử). | Thấp |
| `scripts/maintenance/clean_completed_packets.py` | 112 | Chỉ `run_daily.ps1:129` gọi. Test: `test_destructive_automation_guards.py:25-29`, cùng 5 test `:66-122`. Tệp dọn packet `data/agent_tasks` của lane cũ; Article Lane có vòng đời packet riêng. | Chuyển vào archive | Gỡ 5 test đó. Nếu gỡ cả `test_batch_ids_unique_across_runs` (`:124`, dùng `split_tasks_into_batches`) thì cả tệp test (173 dòng) được xoá. | Thấp |
| `scripts/maintenance/requeue.py` + `Catalog.requeue` (`src/handoff/catalog.py:85-119`) | 80 + 35 | Bị AGENTS.md §6 cấm. Test: `tests/test_state_requeue_paths.py:25-27` và `:96-136`. **Skill đang hoạt động vẫn ra lệnh chạy nó**: `.agents/skills/dsh-preflight-validator/SKILL.md:46` ("Chạy `requeue.py --apply`") và `:139` ("D2 ──► Conductor TỰ chạy requeue --apply"). | Chuyển vào archive và gỡ phương thức | Gỡ `test_requeue_cli_dry_run_vs_apply`. **Sửa `dsh-preflight-validator/SKILL.md:46,105,139`** (bỏ hạng mục D2, hoặc thay bằng `article_run.py --repair`). Sửa `.agents/dsh/RUNBOOK.md:190`. | **Cao**: skill đang dẫn Conductor sang lệnh cấm |
| `scripts/verify_gold_quality.py` + `ArticleStore.set_agent_dod` (`store.py:435-451`) | 146 + 17 | 0 người gọi. `set_agent_dod` chỉ có tệp này dùng. Test chỉ nhắc tên trong thông báo lỗi (`test_no_agent_emulation.py:71`). | Chuyển vào archive và gỡ phương thức | Sửa chuỗi ở `test_no_agent_emulation.py:71`. Sửa doc ADR 0004 và `project/docs/operations/user-venv-guide.md`. | Thấp |
| `scripts/run_user_workflow.py` + `src/pipeline/user_workflow.py` | 40 + 114 | Chỉ nhau gọi nhau. `user_workflow.py:96-102` nạp qua `L1Runner` và `AgentRunner` ngoài Article Lane, đi vòng qua cổng `--finish`. Hai tệp này đã bị `write_user_output.py` thay thế. Test: `tests/test_user_workflow.py` (39 dòng). | Chuyển vào archive | Xoá `tests/test_user_workflow.py`. Sửa `.agents/rules/01-subagent-guardrails.md`, `okf/catalog/pipelines/user_output.md` và `project/docs/design/13-per-user-output-workflow.md`. | Trung bình: một đường nạp thứ hai, lách cổng `--finish` |
| `src/agent/manifest.py` | 188 | Người gọi: `agent_export.py`, `l1_route.py`, `route_today_l1.py`, `run_agent_hierarchy.py` (đều chết). Test: `tests/test_batch_manifest.py:7,13,18`. | Xoá | Tách `test_archive_task_packet` (`:50`) ra, hoặc xoá cùng archive (§2c). Xoá `test_format_short_time` và `test_create_and_load_batch_manifest`. | Thấp |
| `src/agent/packet.py` | 135 | Chỉ `runner.py:11` import, và chỉ `export_tasks` dùng (`build_task_packet`, `write_packet`). Hàm `build_gold_input` không có người gọi nào ngoài test. `write_packet` trong `article_pack` là hàm khác cùng tên. | Xoá, sau khi gỡ `export_tasks` | `tests/test_pruner_and_batch.py:14`: gỡ `test_lean_task_packet_size` (`:79`) và `test_dod_pass_with_pruned_packet` (`:163`) | Thấp |
| `src/agent/l1_classifier.py` | 111 | `classify_title` chỉ phục vụ nhánh code-first của `L1Runner` (`l1_runner.py:9`) và `process_l1_pipeline.py`. `classify_article` chỉ phục vụ `route_article`. `title_of` không có người gọi sống: `silver_builder.py:142` chỉ nhắc trong comment. Phép đối chiếu tất định sống của Article Lane dùng thẳng `reg.detect` (`article_expand.py:382`). | Xoá, sau khi gỡ code-first | `tests/test_l1_classifier.py`: xoá (69 dòng). `tests/test_dynamic_entities.py:16`: 3 test dùng `classify_title`, đổi sang `registry.detect(title)`. `tests/test_silver_title.py:19,69`: đổi assert sang `wp["title"]`. | Trung bình: phải viết lại assert |
| `.agents/skills/gold-financial-analyst/`, `.agents/skills/news-scape-agent-operations/` | 101 + 136 | Registry ghi `retired`. AGENTS.md §2 nói "chỉ còn giá trị tham khảo". Người nhắc tới: `AGENTS.md`, `.agents/rules/08-...md`, `.agents/AGENT_RUNBOOK.md`, `.agents/AGENT_NETWORK_DESIGN.md`, `dod-gatekeeper/SKILL.md`. | Chuyển sang `.agents/skills/_retired/` | Sửa AGENTS.md §2, `rules/08`, `dod-gatekeeper/SKILL.md` | Thấp |
| `.agents/skills/materiality-triage/` | 68 | Registry `:288-290` ghi `retired`. AGENTS.md §6 cấm sinh `materiality`. Chỉ đề xuất và ADR 0006 nhắc tới. | Chuyển sang `_retired/` | Sửa `.agents/AGENT_RUNBOOK.md` | Thấp |

### 1c. NGHI NGỜ: công cụ thủ công, cần người xác nhận

| Tệp | LOC | Bằng chứng | Đề xuất |
|---|---|---|---|
| `scripts/monitor_daily.py` + `src/monitor/daily_reporter.py` | 47 + 493 | Người gọi duy nhất là `run_daily.ps1:152-156`, tệp đã chết. Test: `test_cli_entrypoints.py:31` và `test_daily_reporter.py` (179). | Hỏi người dùng còn đọc báo cáo ngày không. Nếu không thì archive cả cụm (719 LOC tính cả test). Nếu có thì giữ và thêm lệnh vào radar. |
| `scripts/domain_check.py` + `src/monitor/domain_reporter.py` + `src/monitor/domain_validator.py` | 256 + 316 + 373 | Không test nào. Chỉ `plans/20260907-...` nhắc tới. Có cấu hình ghi chú `config/domains/thoibaotaichinhvietnam.yaml:1`. | Công cụ khi thêm nguồn mới. Giữ. Nếu không dùng nữa thì archive (945 LOC). |
| `scripts/validate_e2e.py` | 144 | Không ai gọi. Tệp dùng `Catalog.claim/counts/mark_done`, tức mô hình claim của lane cũ. | Archive. Giữ tệp này thì phải giữ luôn `Catalog.claim` (§2c). |
| `scripts/sample_articles.py` + `src/processor/sentiment.py` + `segment.py` | 399 + 107 + 35 | `orchestrator.py:147` ghi "Engine giữ ở sentiment.py để bật lại khi cần". Sentiment hiện do mô hình sinh. Test: `test_sentiment.py` (65). | Người quyết định. Để dành có chủ đích thì giữ. |
| `scripts/run_pipeline.ps1` | 25 | Người dùng mới kiểm Task Scheduler cho `run_daily.ps1`, chưa kiểm tệp này. Dòng `:10` ưu tiên `project/.venv` (xem §4). | Chạy `Get-ScheduledTask \| ? { $_.Actions.Arguments -match 'run_pipeline' }`. Không có task nào gọi thì archive. |
| `scripts/fetch_periodic_reports.py` + `run_periodic_reports.ps1` + `src/pipeline/periodic_reports.py` | 93 + 48 + 316 | Luồng NSO chạy tay theo tháng. Có test (`test_periodic_reports.py`, `test_cli_entrypoints.py:32`). | Giữ, vì đây là nguồn dữ liệu, không thuộc lane L1/Gold. |
| `scripts/compile_users.py`, `make_user_template.py`, `build_entities.py`, `maintenance/refresh_aliases.py` | 39/114/765/79 | Công cụ quản trị danh mục. YAML sinh ra ghi "Chạy lại: python scripts/compile_users.py" (`config/entities/users/*.yaml:2`). `refresh_aliases` được `_context_guards.yaml:20` nhắc. | Giữ |
| `scripts/estimate_wave.py`, `db_status.py`, `dbq.py`, `db_snapshot.py` (+ `src/db/snapshot.py`), `diagnose_sources.py`, `verify_quality.py`, `report_drift.py`, `rederive_from_bronze.py`, `refresh_watchlist.py`, `export_csv.py`, `export_silver.py`, `watch_24h.py` | — | Công cụ vận hành thủ công. Runbook và `rules/03` còn nhắc. | Giữ. Cân nhắc gom 12 tệp vào `scripts/tools/` để tách khỏi đường vận hành. |
| `scripts/maintenance/heal_orphans.py`, `relativize_paths.py`, `repair_dates.py` | 101/56/50 | Migration dùng một lần. Chỉ `OPEN-ITEMS.md` và `README.md` nhắc tới. | Archive sau khi người dùng xác nhận đã chạy xong |
| `scripts/maintenance/audit_alias_false_positives.py`, `clean_onedrive_conflicts.py` | 109/219 | Chạy tay. Skill `sharepoint-git-hybrid-workspace` nhắc `clean_onedrive_conflicts`. | Giữ |
| `.agents/skills/git-codebase-governance/scripts/audit_codebase.py` | 286 | **Bản sao đã lệch** của `project/scripts/maintenance/audit_codebase.py`, hiện đang sống qua `scripts/harness_cli.py:511`. `diff` chỉ khác comment và type hint. | Xoá bản trong skill, trỏ SKILL.md sang bản `project/scripts/maintenance/` |
| `scripts/bootstrap-harness.ps1` (gốc) | 30 | Chỉ doc nhắc tới | Giữ (dùng khi dựng lại harness) |

Các mục SỐNG, giữ nguyên: `article_*`, `build_article_prefix`, `ctx_probe`, `handoff`, `token_ledger`, `pipeline_radar`, `run_once`, `write_user_output`, `validate_capture`, `maintenance/backfill_deferred`, `maintenance/audit_codebase`, `scripts/harness_cli.py`, `tests/test_harness_cli.py`.

---

## 2. `project/src/` sống một phần: cần tách

| Ký hiệu | Dòng chết | Bằng chứng | Hành động | Test phải sửa kèm | Rủi ro |
|---|---|---|---|---|---|
| `src/agent/runner.py` `AgentRunner.export_tasks` (`:63-218`) | 156 | Người gọi duy nhất là `agent_export.py`. `ingest_output` (`:221-280`) còn sống qua `agent_ingest.py`. | Gỡ `export_tasks` và import `packet` (`:11`) | `tests/test_agent_infra.py:122,223,237` (3 test export): xoá. `:182,194` đang dùng `export_tasks` làm fixture cho ingest: đổi sang `Catalog.enqueue` + tự ghi work-package. `tests/test_pruner_and_batch.py:245,308-351`: xoá. | Trung bình: phải viết lại fixture ingest |
| `src/agent/l1_runner.py` `route_and_export` (`:42-71`), `ingest_code_first` (`:74-142`), `drain_code_first` (`:144-184`) | 140 | `route_and_export` chỉ có `l1_route.py` và `route_today_l1.py` gọi. `drain_code_first` chỉ có `l1_ingest.py --code-first` gọi, nhánh bị AGENTS.md §6 cấm. `ingest_output` và `_register_article_lane_task` còn sống. | Gỡ 3 phương thức và import `classify_title`, `build_code_first_output`, `build_l1_task_packet`, `route_article`, `write_l1_packet` (`:9-13`) | `tests/test_l1_runner.py:49-60`: xoá 2 test route. Giữ 4 test ingest. | Thấp |
| `src/agent/l1_router.py` `route_article`, `build_l1_task_packet`, `write_l1_packet`, `build_code_first_output` | ~112 | Chỉ l1_runner (phần chết) và `process_l1_pipeline.py` gọi. Còn sống: `check_l1_dod` (`:172`), `TYPE_GROUP` (`article_expand.py:32`), `CODE_FIRST_PROVIDER`. | Gỡ 4 hàm. Đổi tên module thành `l1_dod.py`, hoặc giữ tên để diff nhỏ. | `tests/test_l1_router.py:38-53`: xoá 2 test route. `tests/mocks/agent_process_packets.py` (xem §3). | Thấp |
| `src/agent/batch_handoff.py` | ~170/231 | Chỉ `unpack_batch_output` (`:204-231`) sống, qua hai tệp ingest. `build_batch_packet`, `build_l1_batch_packet`, `write_batch_packet`, `split_*` chỉ có script chết gọi. | Giữ `unpack_batch_output`, gỡ phần còn lại | `tests/test_pruner_and_batch.py:113` (`test_batch_handoff_and_unpack`): giữ phần unpack. `:216`: xoá. `test_destructive_automation_guards.py:19,124`: xoá. | Thấp |
| `src/agent/pruner.py` `clean_article_paragraphs` (`:76-153`) | 78 | Chỉ `packet.py` gọi. `is_boilerplate_paragraph` còn sống qua `distill.py`. | Gỡ `clean_article_paragraphs` | `test_pruner_and_batch.py:58,281`: xoá. Giữ `:36`. | Thấp |
| `src/agent/archive.py` + khối archive trong `l1_ingest.py:73-90` và `agent_ingest.py:69-72` | 94 + ~25 | `article_run.py:537-543` gọi hai lệnh nạp mà không truyền `--task-dir` và không có `--no-archive`. Vì thế archive quét `data/agent_tasks/l1/<aid>.task.json` và `data/agent_tasks/<aid>.task.json`, là thư mục của lane cũ. Packet Article Lane nằm ở `data/agent_tasks/article/`, nên thao tác này không có tác dụng. Riêng vòng dọn `l1_batch_*.task.json` (`l1_ingest.py:79-88`) **xoá packet của lane cũ** mỗi lần `--finish`. | Gỡ khối archive, gỡ vòng dọn l1_batch và gỡ `archive.py` | `tests/test_batch_manifest.py:50` (`test_archive_task_packet`): xoá. Kiểm lại `test_article_lane_hardening.py` (đang import `l1_ingest`, `agent_ingest`). | Trung bình: đổi hành vi `--finish` (bỏ tác dụng phụ). Chạy `pytest tests/test_article_lane*.py`. |
| `scripts/l1_ingest.py` nhánh `--code-first` (`:31-33`, `:44-49`), `--limit`, `--dry-run` | ~12 | Nhánh bị AGENTS.md §6 cấm. Thêm nữa, `--task-dir` mặc định `data/agent_tasks/l1` là thư mục lane cũ. | Gỡ cờ và nhánh. Đổi `target` sang `nargs="+"`. | `test_cli_entrypoints.py:26` (vẫn chạy `--help`, không vỡ) | Thấp |
| `src/morninger.py` job `reclaim` (`:93-99`, `run_reclaim :199-218`, `:278`, `:292-298`) + `Catalog.reclaim_stale/claim/list_pending/count_by_status` | ~30 + ~130 | Trạng thái `claimed` chỉ sinh ra từ `Catalog.claim`, và `claim` chỉ có `AgentRunner.export_tasks` (chết) và `validate_e2e.py` (nghi ngờ) gọi. Article Lane chỉ JOIN `work_items` (`article_pack.py:201`), không claim. Job reclaim vẫn chạy mỗi 30 phút (log `15:35:51 ... reclaim/30min`) mà không có gì để nhả. | Gỡ job reclaim khỏi morninger. Gỡ `claim`, `reclaim_stale`, `list_pending` và `count_by_status` sau khi quyết định số phận `validate_e2e.py`. | `tests/test_morninger.py:223-226`: đổi tập job thành `{"capture","derive","drift"}`. `tests/test_state_requeue_paths.py:61` (`test_reclaim_stale...`): xoá. | Trung bình: đổi hành vi scheduler, phải khởi động lại morninger |
| `.agents/registry.yaml` mục `l1-router` (`:51-64`), `gold-exporter` (`:80-95`), `l1-entity-matcher`, `gold-financial-analyst`, `materiality-triage` | — | `status: retired`, nhưng `entrypoint` và `cli` vẫn trỏ tệp sẽ bị archive | Đổi `entrypoint` thành đường dẫn archive, hoặc bỏ `cli` | Kiểm `harness_cli.py audit` sau khi sửa | Thấp, nhưng là Harness Core, nên thuộc cấp HIGH-RISK theo AGENTS.md §0 |

Các module SỐNG hoàn toàn: `dod.py` (qua `AgentRunner.ingest_output`), `distill.py`, `prefix.py`, `intent_resolve.py`, `entities.py`, `handoff/contract_validator.py`, `handoff/work_package.py`, `telemetry/dsh_usage.py`, cùng toàn bộ `core/`, `crawler/`, `db/`, `export/`, `scrapers/`, `users/` và `pipeline/{run,derive,drift,silver_builder,change_detect,refresh}`. Các phương thức `l1_*` trong `store.py` vẫn sống qua `L1Runner.ingest_output`.

---

## 3. `project/tests/`

| Tệp | LOC | Bằng chứng | Phân loại | Hành động |
|---|---|---|---|---|
| `tests/mocks/agent_process_packets.py` | 349 | Không test hay mã nào import. Grep chỉ ra doc: `docs/decisions/0003`, `docs/stories/US-003`, `project/docs/operations/*`. Tệp import `dod`, `entities` và `l1_router` của lane cũ. | (a) | Xoá. Sửa `project/docs/operations/agent-prompting-guide.md` và `daily-runbook-per-user.md`. |
| `tests/mocks/agent_stub.py` | 147 | Như trên | (a) | Xoá |
| `tests/test_l1_classifier.py` | 69 | Đi theo `l1_classifier.py` | (b) | Xoá cùng module |
| `tests/test_user_workflow.py` | 39 | Đi theo `user_workflow.py` | (b) | Xoá |
| `tests/test_destructive_automation_guards.py` | 173 | Chỉ kiểm `auto_pilot`, `clean_completed_packets` và `split_tasks_into_batches` (đều chết) | (b) | Xoá cả tệp |
| `tests/test_batch_manifest.py` | 65 | `manifest` và `archive` (chết) | (b) | Xoá cả tệp |
| `tests/test_state_requeue_paths.py` | 136 | Test `:41` (held→pending qua `Catalog.enqueue`) còn giá trị. Test `:61` và `:96` thuộc lane cũ. | (c) | Giữ `:41`, xoá `:61` và `:96`. Đổi tên tệp thành `test_catalog_enqueue.py`. |
| `tests/test_pruner_and_batch.py` | 351 | Giữ `:36` (boilerplate) và phần unpack của `:113`. Còn lại thuộc lane cũ. | (c) | Còn khoảng 60 dòng. Đổi tên thành `test_unpack_and_boilerplate.py`. |
| `tests/test_agent_infra.py` | 248 | Các test DoD và ingest (`:58-111,155-219`) sống. Export (`:122,223,237`) thì chết. | (c) | Xoá 3 test. Viết lại fixture `:182,194`. |
| `tests/test_l1_runner.py`, `tests/test_l1_router.py` | 88/76 | Phần ingest và DoD sống, phần route chết | (c) | Xoá 2+2 test |
| `tests/test_dynamic_entities.py`, `tests/test_silver_title.py`, `tests/test_functional_and_hygiene.py:91` | — | Dùng `classify_title` và `title_of` làm lớp bọc. `L1Runner.ingest_output` còn sống. | (c) | Đổi sang `registry.detect` và `wp["title"]`. `test_functional_and_hygiene` giữ nguyên. |
| `tests/test_cli_entrypoints.py:25,27` | — | Liệt kê `l1_route.py` và `agent_export.py` như "script automation" | (c) | Bỏ 2 dòng. Sửa comment `:21`. |
| `project/tests/__pycache__/*-DESKTOP-RSG7M2C.cpython-313-pytest-9.1.1.pyc` | 10 tệp | Bản xung đột OneDrive của bytecode | (a) | Xoá (đã có trong gitignore) |

---

## 4. Tệp ngoài mã: môi trường, xung đột OneDrive, rác

| Mục | Kích thước | Bằng chứng | Phân loại | Hành động |
|---|---|---|---|---|
| `./.venv` | 15 MB | `pyvenv.cfg`: anaconda 3.13.5. `Lib/site-packages` chỉ có 2 mục, tức venv rỗng hoặc hỏng. AGENTS.md §3 cấm `.venv` nội bộ. | (a) | Xoá |
| `./project/.venv` | **564 MB** | `pyvenv.cfg` ghi `home = C:\Users\An Thanh Pham\...pythoncore-3.14-64`, tức tạo trên máy khác, vô dụng trên máy này. Có thêm `pyvenv.cfg.bak`. **Hai script vẫn ưu tiên nó**: `run_pipeline.ps1:10` (`Join-Path $proj ".venv\Scripts\python.exe"`) và `okf/tools/okf_check.py:9,29`. `run_daily.ps1:72-74` phải viết mã riêng để né nó. | (a) + sửa tham chiếu | Xoá. Sửa `run_pipeline.ps1:10` và `okf_check.py:9,29` sang `C:\venvs\news-scape\Scripts\python.exe`. |
| `__pycache__` (19 thư mục ngoài venv; khoảng 150 MB nếu tính cả venv) | — | Đã có trong gitignore | (a) | `Get-ChildItem -Recurse -Directory -Filter __pycache__ -Exclude .venv \| Remove-Item -Recurse` |
| `project/logs/monocle-DESKTOP-RSG7M2C-2.log`, `monocle-FPA-AnPT-2.log`, `daily_log.txt` (27/08), `morninger_sched_test.log` | ~1.5 MB | Bản xung đột theo tên máy và log cũ | (a) | Xoá |
| `project/daily_log.txt` | 73 KB | Ghi lần cuối 23/09 16:42. Không mã nào ghi tên tệp này (grep chỉ ra doc). Nhiều khả năng do redirect `>` bằng tay. `project/.gitignore:40` đã bỏ qua. | (d) | Xoá sau khi người dùng xác nhận không có lối tắt nào ghi vào |
| `project/data/monocle.db` (187 MB, ngày 21/09) + `monocle_backup_260909_pre_a2.db` (187) + `monocle_backup_before_gold_clean.db` (187) + `monocle_backup_premerge.db` (86) + `monocle_review.db` (185) | **~832 MB** | DB vận hành là `C:/data/news-scape/monocle.db` (`config/settings.yaml:6`). Các bản trong OneDrive là bản cũ. **19 script vẫn fallback `"data/monocle.db"`**, ví dụ `write_user_output.py:40`, `l1_ingest.py:40`, `agent_ingest.py:39`, `run_once.py:22`. Tệp `-shm` được chạm lúc 24/09 15:09, nên có tiến trình vừa mở bản cũ này. | (d) | Chuyển sang `C:\data\news-scape\backups\`. Thay mọi fallback `.get("path","data/monocle.db")` bằng `src.db.preflight.resolve_db_path()`. Lệnh kiểm: `git grep -n '"data/monocle.db"' -- '*.py'` |
| `project/src/data/` (monocle.db 66 MB, `raw_html/`, `silver/`, `exports/`) | ~66 MB+ | Sinh do chạy với cwd = `src/`. Đã có trong gitignore (`project/src/data/`). `-shm` cũng được chạm lúc 24/09 15:09. | (a) | Xoá |
| `project/data/archive_conflicts/monocle-DESKTOP-RSG7M2C.db`, `monocle-FPA-AnPT.db` | 194 MB | Bản xung đột DB | (a) | Chuyển ra ngoài OneDrive hoặc xoá |
| `./data/` ở gốc repo (`agent_outputs`, `agent_outputs_l1`, `agent_tasks`, `silver`, `work_packages`) | 19 MB, 257 tệp | Đầu ra lane cũ ngày 17/09 do chạy script với cwd = gốc repo. Không mã nào đọc. | (a) | Chuyển vào `project/data/archive/legacy-lane-20260923/root-data-20260917/`, ghi MANIFEST |
| `project/data/agent_tasks/l1/` (183 tệp mới, xem §0) + `project/data/agent_tasks/archive/` | 6.1 MB | Tồn dư lane cũ | (a) | Chuyển vào archive, ghi MANIFEST |
| `project/data/agent_outputs_l1/` (8 tệp) | 716 KB | Đều là `article_W*`, tức đầu ra Article Lane. Vẫn sống. | Giữ | — |
| `./desktop.ini` | 95 B | Do OneDrive sinh. Đã có trong gitignore. | (d) | Bỏ qua (OneDrive sẽ tái tạo) |
| `other/harness/*.md` (4 tệp) | ~83 KB | `scripts/harness_cli.py:4` và `scripts/schema/001-init.sql:2` trỏ tới làm tài liệu tham chiếu | Giữ | — |
| `other/meeting-minutes/*.docx`, `project/thamkhao/present/**` (gồm 2 CSV trùng nhau `all_articles_by_ticker_20260212_163152.csv` và bản `... 1.csv`) | — | Chỉ `plans/2026072x` nhắc tới (tài liệu nghiên cứu nguồn) | (d) | Giữ. Xoá bản CSV trùng `... 1.csv`. |
| `logs/tasks-list/**` ở gốc (có .docx được git theo dõi) | — | Gitignore có `logs/`, nhưng các tệp này đã được theo dõi từ trước | (d) | Người xác nhận. Chuyển sang `docs/`, hoặc `git rm --cached` |

---

## 5. Tài liệu còn chỉ dẫn lane đã ngừng (phải sửa cùng đợt dọn)

Mức ưu tiên từ cao xuống thấp. Tài liệu này là tài liệu tác nhân đọc, nên chỉ dẫn sai ở đây thì tác nhân làm sai theo.

1. `.agents/skills/dsh-preflight-validator/SKILL.md:46,105,139,219`. Tệp ra lệnh `requeue --apply`. Dòng `:219` còn đòi `l1_ingest.py` và `agent_ingest.py` có mặt, điều này đúng nhưng cần ghi rõ vai "cổng DoD".
2. `okf/catalog/playbooks/daily_agent_run.md`: 17 lần nhắc `l1_route`, `agent_export`, `run_daily`, `requeue`, `code-first`.
3. `docs/CODE-FIRST-LANDSCAPE.md`: 24 lần. Cần gắn đầu tệp ghi "lịch sử, ADR 0010", hoặc chuyển vào `docs/archive/`.
4. `.agents/AGENT_RUNBOOK.md`, `.agents/AGENT_NETWORK_DESIGN.md` (`status: active` cho các mục lane cũ), `okf/catalog/pipelines/agent_handoff.md`, `project/docs/operations/backlog-drain-runbook.md`, `agent-prompting-guide.md`.
5. AGENTS.md §2: bỏ `gold-financial-analyst` và `news-scape-agent-operations` khỏi danh sách skill vận hành sau khi chuyển chúng vào `_retired/`.

---

## 6. Lệnh đề xuất (người vận hành chạy; phiên này KHÔNG chạy)

Chuyển dữ liệu lane cũ vào archive theo mẫu `MANIFEST.json` (`{reason, restore, items[]}`):

```powershell
# cwd = project/
$arc = "data/archive/legacy-lane-20260923"
$moved = @()
foreach ($src in @("data/agent_tasks/l1", "data/agent_tasks/archive")) {
  if (Test-Path $src) {
    $dst = Join-Path $arc ("late-20260924/" + ($src -replace '^data/',''))
    New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
    Move-Item $src $dst; $moved += ($src -replace '^data/','')
  }
}
# data/ ở gốc repo
Move-Item "../data" (Join-Path $arc "root-data-20260917"); $moved += "../data"
$m = Get-Content "$arc/MANIFEST.json" -Raw | ConvertFrom-Json
$m.items = @($m.items) + $moved
$m | ConvertTo-Json -Depth 5 | Out-File "$arc/MANIFEST.json" -Encoding utf8
```

Chuyển mã chết (git mv, để hoàn tác được):

```powershell
# cwd = project/
New-Item -ItemType Directory -Force scripts/_retired | Out-Null
git mv scripts/l1_route.py scripts/agent_export.py scripts/auto_pilot.py scripts/run_daily.ps1 `
       scripts/run_agent_hierarchy.py scripts/l1_backlog.py scripts/verify_gold_quality.py `
       scripts/run_user_workflow.py scripts/maintenance/requeue.py `
       scripts/maintenance/clean_completed_packets.py scripts/_retired/
git rm scripts/process_l1_pipeline.py scripts/run_validation.py scripts/test_surface.py `
       scripts/inspect_catalog.py scripts/maintenance/route_today_l1.py `
       scripts/maintenance/cleanup_legacy_tasks.py scripts/maintenance/clean_yahoo_lifestyle.py `
       src/agent/manifest.py src/agent/packet.py src/pipeline/user_workflow.py `
       tests/mocks/agent_process_packets.py tests/mocks/agent_stub.py `
       tests/test_user_workflow.py tests/test_destructive_automation_guards.py tests/test_batch_manifest.py
```

Chọn `scripts/_retired/` thay vì `data/archive/`, vì `data/archive/` bị gitignore và không nằm trong git. Nếu muốn mã ra khỏi cây làm việc hoàn toàn thì dùng `git rm`, git vẫn giữ lịch sử để quay lui theo ADR 0010 §4. `scripts/_retired/` phải được loại khỏi `harness_cli.py audit --codebase` và khỏi `test_no_agent_emulation`.

Dọn môi trường:

```powershell
Remove-Item -Recurse -Force "./.venv", "./project/.venv", "./project/src/data"
Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Remove-Item project/logs/*-DESKTOP-*.log, project/logs/*-FPA-*.log
```

Kiểm chứng sau mỗi bước:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest tests/ -q          # cwd = project/
& "C:\venvs\news-scape\Scripts\python.exe" ../scripts/harness_cli.py audit --codebase
git grep -nE "l1_route|agent_export|requeue\.py|auto_pilot|run_daily\.ps1|export_tasks|drain_code_first" -- '*.py' '*.ps1' '*.yaml' '*.ts'
```

Kỳ vọng sau khi dọn: lệnh `git grep` cuối chỉ còn trả về các test khẳng định chuỗi đã vắng mặt (`test_article_lane_hardening.py:299-300`, `test_morninger.py:246`) và dòng cảnh báo ở `pipeline_radar.py:332`.

Thứ tự thực hiện đề xuất, mỗi bước một commit, chạy pytest xanh xong mới sang bước sau:
1. §0 và §4: dữ liệu và môi trường. Không đụng mã.
2. §1a và §3(a): xoá tệp chết chắc.
3. §1b: script, test và skill.
4. §2: tách phần sống một phần. Chạy `pytest tests/test_article_lane*.py` và `test_agent_ingest_cli.py`, sau đó chạy thử `article_run.py --finish` trên một đợt nhỏ.
5. §5 và `registry.yaml`: đây là Harness Core, cấp HIGH-RISK, cần ADR phụ hoặc amendment ADR 0010 và người duyệt.

---

## 7. Ước lượng LOC giảm được

| Nhóm | Mã nguồn | Test | Ghi chú |
|---|---|---|---|
| (a) CHẾT CHẮC | 815 (scripts) + 496 (tests/mocks) = **1.311** | — | Không cần sửa gì kèm |
| (b) CHẾT + TEST/TÀI LIỆU | **~1.776**: l1_route 205, agent_export 101, auto_pilot 246, run_daily 168, requeue 80 + 35, clean_completed_packets 112, verify_gold_quality 146 + 17, run_user_workflow và user_workflow 154, manifest 188, packet 135, clean_article_paragraphs 78, l1_classifier 111 | **~566**: test_destructive 173, test_batch_manifest 65, test_user_workflow 39, test_l1_classifier 69, khoảng 220 dòng từ test_pruner_and_batch và test_state_requeue | Cùng 305 dòng skill retired |
| (c) TÁCH PHẦN CHẾT | **~800**: export_tasks 156, l1_runner 140, l1_router 112, batch_handoff 170, archive.py 94 + khối ingest 37, reclaim và Catalog khoảng 90 | **~110** | Phải viết lại fixture ở test_agent_infra |
| **Tổng chắc chắn (a+b+c)** | **~3.900 LOC mã** | **~680 LOC test** | Khoảng **4.550 LOC**, tương đương 19% của 23.970 LOC trong `project/src` + `project/tests` + các script liên quan |
| (d) nếu người dùng đồng ý archive thêm | ~2.300 (domain_check và monitor 945, monitor_daily và daily_reporter 540, validate_e2e 144, sample_articles, sentiment và segment 541, 3 migration 207) | ~244 | Không tính vào tổng |
| Dung lượng ngoài mã, rời OneDrive | project/.venv 564 MB, DB cũ 832 MB, archive_conflicts 194 MB, src/data khoảng 66 MB, .venv 15 MB, data/ gốc 19 MB, pycache | — | **Khoảng 1,7 GB** không còn đồng bộ qua OneDrive |
