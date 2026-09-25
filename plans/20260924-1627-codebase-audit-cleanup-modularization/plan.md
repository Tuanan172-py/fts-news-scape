# Plan — Kiểm toán toàn codebase, dọn mã chết, hợp nhất tích hợp, chuẩn module hoá

- **Trạng thái:** ĐỀ XUẤT, chờ duyệt. Chưa triển khai. Chưa mở story nào trong `harness.db`.
- **Ngày:** 2026-09-24 · **Cấp:** 2 (lập plan). Nhiều hạng mục bên trong là Cấp 3, đánh dấu **C3**.
- **Nguồn:** 5 báo cáo kiểm toán độc lập + 2 báo cáo phản biện chéo, tại `reports/`:

| Tệp | Lớp nhiệm vụ |
|---|---|
| `A-dead-code.md` | Mã chết, di sản lane L1/Gold (ADR 0010), môi trường |
| `B-modularization.md` | Import graph, logic trong `scripts/`, cấu trúc đích |
| `C-quality-tests.md` | Chuẩn rule 06, sức khoẻ test, cấu hình chết |
| `D-harness-docs.md` | Registry, skill, rule, tài liệu, `harness.db` |
| `E-integration.md` | Luồng dữ liệu đầu-cuối, hợp đồng, DSH |
| `R1-redteam.md` | Phản biện đỏ: kiểm chứng lại reachability và số liệu |
| `R2-architecture-critique.md` | Phản biện kiến trúc, phân cấp rủi ro, trình tự |

Plan này **thay mục trình tự** của `plans/20260924-research-council-execution/plan.md` (xem §5). Các task T-x.y của plan đó giữ nguyên nội dung, chỉ đổi vị trí.

---

## 1. Kết luận

1. **Xương sống Article Lane chạy đúng.** W1, W2, W365 đạt 97–100% ở cả hai lớp. Lỗi nằm ở ranh giới giữa các tầng, không nằm trong bước gọi mô hình.
2. **Có 4 rủi ro dữ liệu thật, phải xử lý trước mọi việc dọn dẹp:**
   - Test suite ghi DDL lên DB vận hành: `test_cli_entrypoints.py:56` chạy `backfill_deferred --dry-run` không truyền DB.
   - Ba định nghĩa khác nhau cho "L1 đạt". Bộ chọn bài loại `code_first`; hậu kiểm `article_run.py:670-675` và giao hàng `user_output.py:27` thì không. Đợt backlog 2.915 bài sẽ báo độ phủ bị thổi phồng.
   - `export_csv` → `csv_export.py:14` dùng `data/monocle.db` tương đối theo cwd, né cổng đường dẫn DB. `snapshot.py` và `clean_yahoo_lifestyle.py` cũng vậy; tệp sau mở DB ngay khi import.
   - Fuzzy dedup vứt vĩnh viễn khoảng 1.566 bài trước Bronze, gồm tin CBTT (R2 §5, trùng T2.1a của plan cũ).
3. **Mã chết đo được:** khoảng 4.550 LOC dọn chắc (3.900 mã + 680 test) và khoảng 2.300 LOC nữa nếu archive nhóm nghi ngờ. Có khoảng 1,7 GB nằm trong OneDrive mà không cần ở đó. R1 bác một phần danh sách xoá (§3.2): **không mục nào được xoá mà chưa qua bảng an toàn ở §3.**
4. **Module hoá: chọn phương án tối giản của R2**, không chọn 8 tầng của B (§4).
5. **Tài liệu và harness:** lõi đã khớp ADR 0010. Vùng xung quanh còn dạy lane cũ: `AGENT_RUNBOOK.md`, 4 skill, khoảng 12 tài liệu `project/docs` và `okf`. Skill `dsh-preflight-validator` còn ra lệnh `requeue --apply`, lệnh bị cấm.

## 2. Bối cảnh sống khi thực thi (R1)

- **Đợt dở.** Lúc kiểm toán, đợt `W09241605` đang ở giữa `--finish`. Mọi sprint bắt đầu bằng `pipeline_radar.py status`. Chỉ làm việc chạm mã nạp khi radar không báo đợt dở.
- **Cây làm việc là runtime.** Morninger đang chạy, kèm `backfill_deferred` nạp lại mã từ đĩa mỗi 10 phút. Sửa `src/db`, `src/handoff`, `src/core`, `morninger.py` hay chuyển nhánh git chỉ làm sau khi dừng morninger.
- **Có phiên khác đang sửa đồng thời** `AGENTS.md`, `.agents/rules/09-dsh-preflight-gate.md` (chưa track), skill `dsh-preflight-validator`, `pipeline_radar.py`. Phải commit WIP đó trước S0.
- **`.git` nằm trong OneDrive đồng bộ hai máy.** Tạm dừng đồng bộ OneDrive khi chạy `git mv`/`git rm` hàng loạt.
- **Không chạy `pytest tests/` toàn bộ** cho tới khi S0 cô lập DB xong.

## 3. Danh mục dọn dẹp đã qua phản biện

### 3.1 Dọn được (sau S0, theo đúng thứ tự)

| Nhóm | Mục | Điều kiện |
|---|---|---|
| Script lane cũ | `run_daily.ps1`, `run_agent_hierarchy`, `auto_pilot`, `l1_route`, `agent_export`, `l1_backlog`, `verify_gold_quality`, `requeue`, `clean_completed_packets`, `route_today_l1`, `cleanup_legacy_tasks`, cụm `run_user_workflow` + `src/users/user_workflow` (đường nạp thứ hai né `--finish`) | Gỡ test kèm: `test_cli_entrypoints:25,27`, `test_destructive_automation_guards`, `test_batch_manifest`, `test_state_requeue_paths:61,96`, `test_user_workflow`; gỡ `l1_route.py`/`agent_export.py` khỏi `AUTOMATION_CLIS` |
| Ký hiệu chết trong `src/agent` (~800 dòng) | `AgentRunner.export_tasks`, `L1Runner.route_and_export`/`ingest_code_first`/`drain_code_first`, 4 hàm route trong `l1_router`, 5/6 hàm `batch_handoff`, `pruner.clean_article_paragraphs`, `archive.py`, `manifest.py` | **Thứ tự bắt buộc (R1):** gỡ `import packet` ở `runner.py:11` và `import l1_classifier` ở `l1_router.py:8`, `l1_runner.py:9` **trước**, rồi mới `git rm packet.py`, `l1_classifier.py`. Sau mỗi bước chạy `python -c "import scripts.agent_ingest, scripts.l1_ingest"` bằng test, không bằng one-liner |
| Tác dụng phụ lane cũ trong `--finish` | Khối archive/xoá `l1_batch_*` ở `l1_ingest.py:73-90`, `agent_ingest.py:69-72` | Lần `--finish` 16:14 đã xoá 2 packet lane cũ (183 → 181) |
| Job morninger | `reclaim` (chạy trên tập rỗng) | Sửa `test_morninger.py:226`; gộp vào đúng một lần restart morninger |
| Test/mock chết | `tests/mocks/agent_process_packets.py`, `agent_stub.py`; bản sao lệch `.agents/skills/git-codebase-governance/scripts/audit_codebase.py` | — |
| Skill retired | `gold-financial-analyst`, `news-scape-agent-operations`, `materiality-triage` | `git rm` (R2: ADR 0010 §4 cấm để đường quay lui trong mã; tài liệu lịch sử nằm trong git) |
| Packet lane cũ | 181 tệp `project/data/agent_tasks/l1/` | Chuyển vào `project/data/archive/legacy-lane-20260923/` và bổ sung `MANIFEST.json` |

### 3.2 KHÔNG xoá (R1 bác hoặc cần người quyết)

| Mục | Lý do | Hành động đề xuất |
|---|---|---|
| `project/src/data/` | 767/1.083 tệp raw HTML không có ở kho Bronze nào khác; DB ở đó có 237 bài không có trong DB vận hành. Xoá = mất Bronze, trái bất biến "Bảo toàn raw gốc" | **H:** chuyển ra `C:\data\news-scape\recovered\src-data-<ngày>\` kèm MANIFEST SHA256; sau đó đối chiếu và nạp các bài thiếu (Cấp 3 nếu nạp vào DB) |
| `project/data/monocle.db` | 163 bài không có trong DB vận hành | **H:** như trên |
| `monocle_review.db` | Rule 03: snapshot BI, tệp chia sẻ SharePoint | Giữ |
| `.venv` gốc | VS Code đang chạy language server từ đây | **H:** trỏ VS Code sang `C:\venvs\news-scape` rồi mới xoá |
| `project/.venv` (564 MB) | Tạo trên máy thứ hai của người dùng; OneDrive đồng bộ nên xoá ở đây là xoá ở máy kia. `run_pipeline.ps1:10`, `okf/tools/okf_check.py:9,29` còn trỏ tới | **H:** người dùng xác nhận máy kia; sửa hai tệp trỏ về `C:\venvs\news-scape` trước |
| `project/daily_log.txt` | Task `\news_cron` (Disabled, còn trigger 16:00) ghi vào đây; cả 5 báo cáo bỏ sót | **H:** quyết xoá task `\news_cron` hay giữ |
| `test_handoff.py` | Kiểm Silver và work_package đang chạy; C xếp nhầm vào lane cũ | Giữ |
| `RUNBOOK.md:190` "requeue" | Nghĩa là chạy lại bản ghi hỏng, không phải `requeue.py` | Giữ |
| Nhóm (d) của A (~15 cụm công cụ chạy tay) | Người dùng có thể còn dùng | **H:** duyệt từng cụm |

### 3.3 Số liệu đã chỉnh sau phản biện

| Khẳng định gốc | Phán quyết R1 |
|---|---|
| A-1: lane L1 chạy tới 15:17 và sinh `l1_outputs` code_first mới | Log đúng. Phần DB sai: dòng code_first mới nhất là 17/09; chỉ `l1_tasks` nhận khoảng 1.748 dòng pending |
| E-01: 20,3% thực thể sai mã nhóm, mức Cao | Số đúng (18,7% tính cả đợt mới) nhưng toàn bộ là thực thể thân bài, không đi vào giao hàng. Hạ xuống Trung bình. Cần đo thêm ở tiêu đề (0 token) |
| E-02: 838 dòng provenance sai | 664 dòng sai chắc (từ 18/09), còn đang tăng theo mỗi đợt |
| E-04: 1 dòng lệch `raw_sha256` | 44 dòng |
| E-07: cổng thật 100%, sửa ở Cấp 2 | Cơ chế đúng, nhưng là chủ ý của commit `46f617f`. Nới cổng là quyết định của người dùng (ADR 0012) |
| A: 19 fallback `data/monocle.db` nguy hiểm | Phần lớn là mã chết vì `load_settings` ghi đè. Lỗi thật chỉ ở `csv_export`/`export_csv`, `snapshot.py`, `clean_yahoo_lifestyle` |
| Xác nhận không đổi | E-03, `token_ledger` trùng dòng (W2 ×4, W365 ×3), test ghi DB thật, trace #80 thiếu ADR |

## 4. Tiêu chuẩn module hoá (phương án R2)

B đề xuất 8 tầng T0–T7 và lộ trình 16 bước. R2 phản biện: quá tay cho khoảng 20K LOC còn lại sau dọn. Plan chọn phương án tối giản:

**Cấu trúc:** 3 tầng mã + 1 tầng CLI, giữ nguyên tên gói hiện có.

| Tầng | Gói | Được import |
|---|---|---|
| L0 | `src/core` (thêm `paths.py`: gốc dự án, `TASK_DIR`, `resolve_db_path` duy nhất, múi giờ VN, xử lý `today`) | stdlib, thư viện ngoài |
| L1 | `src/db` (`store.py`, `predicates.py` mới, `open_ro`/`open_rw`) | L0 |
| L2 | Gói nghiệp vụ: `scrapers`, `crawler`, `processor`, `pipeline`, `agent`, `export`, `handoff`, `monitor`, `telemetry`, `users` và gói mới **`src/article_lane/`** (select, packet, conductor, expand, verify, finish, ledger, `contracts.py`) | L0, L1, gói L2 khác |
| L3 | `scripts/*.py`: CLI mỏng, parse tham số rồi gọi một hàm trong `src` | L0–L2 |

**Luật (rule mới, số kế tiếp chưa dùng, ví dụ `10-module-boundaries.md`, vì số 09 đã bị `09-dsh-preflight-gate.md` chiếm):**
1. Không `scripts → scripts`. Không `src → scripts`.
2. `sqlite3.connect` và chuỗi `"monocle.db"` chỉ nằm trong `src/db` và `src/core/paths.py`.
3. Gốc dự án chỉ tính trong `src/core/paths.py`. Không `sys.path.insert` mới.
4. Không `subprocess` gọi script anh em; `--finish` gọi hàm Python.

**Kiểm tự động:** `project/tests/test_architecture.py` dùng `ast`, 4 luật trên, allowlist bằng hiện trạng. Test chỉ đỏ khi có vi phạm **mới**. Allowlist giảm dần theo sprint.

**Golden test:** chụp từng byte cho packet, `.ts` (sau khi chuẩn hoá đường dẫn `OUT`), đầu ra expand (bỏ `timestamp`). Radar không chụp golden được (5 lời gọi `datetime.now()`, mtime, DB sống): tách `decide(state)` thành hàm thuần, test bằng bảng trạng thái → lệnh kế tiếp.

**Không làm:** tách `store.py`, gom gói bronze/silver/apps, `pyproject.toml`, gỡ vòng `core↔db`, shim tái xuất lâu dài. Sửa 16 import của test cùng commit dời mã. Shim duy nhất là `resolve_db_path`, xoá ở sprint kế tiếp.

## 5. Trình tự hợp nhất (thay mục trình tự của plan research-council)

WIP=1 ở mức story. Song song chỉ ở mức task có tập tệp rời nhau, mỗi task một worktree.

| Sprint | Story | Task song song | Người duyệt | Xong khi |
|---|---|---|---|---|
| **Tiền đề** | — | Commit WIP của phiên khác (rule 09, radar, skill preflight, AGENTS.md); commit các thay đổi US-025…027 đang treo | **H** | `git status` chỉ còn tệp của plan này |
| **S0 Nền an toàn** | Ổn định nền kiểm toán | (a) `export_csv`, `csv_export`, `snapshot`, `clean_yahoo_lifestyle` dùng `resolve_db_path` · (b) fixture autouse `MONOCLE_DB_PATH` → `tmp_path`; `--dry-run` mở DB chỉ đọc · (c) `test_harness_cli.py:55` (schema 3), sửa comment sai `token_pricing.yaml:32-34`, sửa `dod.py:55` nuốt lỗi ngưỡng DoD · (d) `harness_cli` `DEFAULT_DB_PATH` neo tuyệt đối | Duyệt commit | `pytest` project và `tests/` gốc 100% PASS; không test nào mở `C:\data\…` |
| **S1 Chặn mất và sai dữ liệu** | Dedup + vị từ | (a) dedup truyền đúng `source_domain` (T2.1a phần Cấp 2) · (b) `src/db/predicates.py`, whitelist `l1_source='agent'` cho pack, verify, radar, handoff · (c) soạn ADR 0012, 0015 | **C3**: ADR 0012 (giao hàng bài chỉ có code_first, cổng `--finish` 90%/100%), ADR 0015 (miễn fuzzy cho CBTT) | Test "bài code_first không tính độ phủ nhưng vẫn được chọn"; test dedup cùng/khác nguồn. **Đợt backlog 2.915 bài chỉ chạy sau sprint này** |
| **S2 Xoá lane cũ** | Thực thi ADR 0010 phần mã | (a) `git rm` script + test + mock (§3.1) · (b) tách ký hiệu chết `src/agent/*` theo thứ tự R1 · (c) skill retired, sửa `dsh-preflight-validator`, `AGENT_RUNBOOK.md` | Quyết nhóm (d) và §3.2; restart morninger | `git grep` lệnh cấm chỉ còn trong test khẳng định vắng mặt; `pytest` PASS; `article_run --where` OK |
| **S3 Hợp đồng ranh giới** | Kiểm hợp đồng chỉ báo cáo + provenance | (a) `src/article_lane/contracts.py`: lược đồ bản ghi gọn `article-compact-v1`, đếm vi phạm in trong handoff (không chặn) · (b) chuẩn hoá tiền tố mã nhóm trong `IntentResolver` (đo trước/sau, 0 token) · (c) provenance đúng cho dòng mới (`dsh/deepseek-flash`, bỏ `confidence=0.9` tự đặt) · (d) `check_dod` chọn lược đồ tường minh, bỏ v1 · (e) map đợt mang `raw_sha256` | **C3**: ADR 0011 (hồi tố ngừng `materiality`/`event_type`/`impact_area`), ADR 0014 (backfill 664 dòng provenance) | Test đầu-cuối bản ghi gọn → expand → DoD; số đo mã nhóm sai trước/sau |
| **S4 Một nguồn đường dẫn** | `paths.py` + test kiến trúc | (a) `src/core/paths.py`, thay 22 `PROJECT_ROOT`, 7 `TASK_DIR`, 2 `resolve_db_path` · (b) thay trong `scripts` · (c) `tests/test_architecture.py` | — | Test chạy từ 3 cwd cho cùng đường dẫn; allowlist khớp hiện trạng |
| **S5 Module hoá tối giản** | Article Lane vào `src/article_lane` | Chụp golden trước. Dời tuần tự: select/packet → expand → conductor → verify/finish → ledger → radar `decide()` | — | Không còn cạnh `scripts→scripts`; `finish_wave()` test đơn vị được; golden không đổi. Dừng nếu một golden đổi |
| **Song song xuyên suốt** | Gắn vào story đang chạy | Tài liệu: `.agents` (4 skill, rule 01/02/07 còn "Antigravity"/`invoke_subagent`), `registry.yaml` phần mô tả I/O, `project/docs` + `okf` (~12 tệp, ~9 link chết), 31 comment kể lịch sử, docstring `store.py`/`harness_cli.py` | `registry.yaml` đổi trạng thái hoặc DAG = **C3** | Mỗi lô: số lần nhắc lệnh cấm trong tài liệu sống giảm, không có link chết mới |
| **Sau S5** | Theo plan research-council | T3.8 golden set, T3.1 few-shot (ví dụ Hòa Phát gán sai ngành), T3.5, T3.2, T2.5, ADR 0013 Harness Core (`harness.db` rời OneDrive, migration đánh số), đưa thực thể thân bài vào phân tuyến (C3), `agent_metrics` cho `article-processor`, `token_ledger` idempotent | Theo từng ADR | — |

**Việc phải tuần tự:** mọi task chạm `article_expand.py`, `article_run.py`, `article_pack.py` (S3 → S5); `pipeline_radar.py` (WIP → S1 → S5); `l1_ingest`/`agent_ingest` (S2 → S4); morninger (gộp mọi thay đổi vào một lần restart ở S2).

**Task lỗi thời trong plan research-council:** T0.1, T0.3 (đã xong), T1.1 (thay bằng xoá `run_daily.ps1`), T1.4 (xong ở `46f617f`), T2.2 phần settings/preflight (xong ở `39c9898`).

## 6. ADR cần lập

| Số | Phạm vi | Chặn sprint |
|---|---|---|
| 0011 | Hồi tố ngừng `materiality`, `event_type`, `impact_area` (trace #80 sửa AGENTS.md, registry, `user_output` mà không có intake/ADR) | S3 |
| 0012 | Ngữ nghĩa "đã phân tích"; bài chỉ có code_first có vào xlsx không (khoảng 3.069 bài bị ảnh hưởng); cổng `--finish` 90% hay 100% | S1 (phần giao hàng), đợt backlog |
| 0013 | Harness Core: `harness.db` rời OneDrive, migration đánh số, `token_ledger` trong migration | Sau S5 |
| 0014 | Provenance và backfill 664 dòng `agent_outputs` | S3 (phần backfill) |
| 0015 | Chính sách fuzzy dedup cho tin CBTT | S1 (phần miễn fuzzy) |

Đề xuất `agy-automation-council-2026-09-23.md` đang tự gọi mình là "ADR 0010" và "Intake #25", cả hai số đã dùng. Đổi số trong S0.

## 7. Quyết định cần người dùng

1. Duyệt trình tự §5 thay cho mục trình tự của plan research-council.
2. ADR 0012: bài chỉ có bản code_first có còn đi vào xlsx không.
3. ADR 0012: cổng `--finish` giữ 100% (hiện trạng từ `46f617f`) hay về 90% (AGENTS.md §6B).
4. `project/src/data/` và `project/data/monocle.db`: đồng ý chuyển ra `C:\data\news-scape\recovered\`, và có nạp lại khoảng 400 bài thiếu không.
5. `project/.venv`: máy thứ hai còn dùng không.
6. Task Scheduler `\news_cron`: xoá hay giữ.
7. Nhóm (d) của A: duyệt từng cụm (danh sách ở `reports/A-dead-code.md`).
8. Phiên đang sửa rule 09 và skill preflight: chốt và commit trước S0. Rule 09 đặt thêm một cổng "ĐỎ chặn đợt" mà chưa có intake; theo AGENTS.md, kiểm tra mới mặc định chỉ báo cáo.
