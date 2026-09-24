# Plan thực thi — xử lý toàn bộ phát hiện của hội đồng nghiên cứu 2026-09-24

- **Nguồn:** `docs/proposals/research-council-2026-09-24.md`
- **Trạng thái:** chờ duyệt. Chưa agent nào được giao việc.
- **Quyết định đã chốt (người dùng, 2026-09-24):** ngừng dùng `materiality` và `event_type`, giữ đầu ra sạch. Mọi xếp hạng hay cảnh báo chỉ dùng tín hiệu sẵn có: `time_sensitivity`, tầng watchlist, kích thước cụm và số nguồn.

---

## 0. Việc đã làm trong phiên lập plan (T-00)

| Việc | Tệp | Proof |
|---|---|---|
| Gỡ `materiality`, `event_type`, `impact_area` khỏi CSV `_master` (final, agent) và khỏi khoá sắp xếp; khoá sắp chỉ còn thời gian → thực thể → tiêu đề | `project/src/export/user_output.py` | `tests/test_user_output.py` + test mới `test_retired_fields_absent_everywhere` |
| Fixture test bỏ ba trường, `time_sensitivity` lên cấp đỉnh | `project/tests/_userkit.py` | như trên |
| AGENTS.md §2, §6A: bỏ `materiality`, thêm điều khoản "đầu ra sạch" | `AGENTS.md` | đọc lại |
| `materiality-triage` → `retired`; gỡ stage `materiality_triage` | `.agents/registry.yaml`, `.agents/pipeline.yaml` | `yaml.safe_load` OK |
| Báo cáo hội đồng sửa theo quyết định | `docs/proposals/research-council-2026-09-24.md` | — |

Dữ liệu raw trong DB (`agent_outputs.output_json` cũ theo lược đồ v1) **không bị sửa**. Chỉ đường đọc và đường xuất bỏ ba trường này.

---

## 1. Mô hình thực thi cho agent

1. **WIP=1 ở mức story, song song ở mức task.** Mỗi đợt (sprint) mở đúng một story trong `harness.db`. Trong story đó, các task có **tập tệp không giao nhau** được giao cho nhiều agent chạy song song, mỗi agent một worktree (`isolation: worktree`). Phiên điều phối gộp kết quả, chạy toàn bộ test và ghi trace.
2. **Mỗi agent nhận đúng một task ID** kèm 4 thứ: tệp được phép sửa, tệp chỉ đọc, proof bắt buộc, điều kiện dừng.
3. **Proof tối thiểu cho mọi task mã:**
   - `ast.parse` trên mọi tệp `.py` đã sửa.
   - Test của module liên quan phải PASS.
   - Test mới phải chứng minh hành vi mới.
   - Phiên điều phối chạy lại toàn bộ `pytest tests/` trước khi đóng sprint.
4. **Hard gate Cấp 3.** Task có nhãn **C3** (đổi schema DB, đổi Data Contract, đổi Harness Core hoặc ADR 0009) dừng ở trạng thái `blocked`. Phải có ADR và người duyệt trước khi agent sửa mã.
5. **Nhãn H.** Task cần người thao tác hoặc quyết định (commit, xoá tệp lớn, di chuyển dữ liệu, gán nhãn, đổi định dạng giao hàng). Agent chỉ chuẩn bị, không tự làm.
6. **Cấm:**
   - Chạy đợt Article Lane thật.
   - Ghi DB vận hành `C:\data\news-scape\monocle.db`, trừ task có nhãn H đã được duyệt.
   - Thêm cổng, trần hay bộ lọc chặn mới. Kiểm tra mới mặc định là *chỉ báo cáo*.

**Làn tệp dùng để chia agent song song, tránh xung đột:**

| Làn | Phạm vi tệp |
|---|---|
| A — legacy | `project/scripts/{l1_*,agent_export,run_*,process_l1_pipeline,auto_pilot,validate_*,verify_gold_quality}.py`, `project/scripts/maintenance/`, `run_daily.ps1`, `tests/test_cli_entrypoints.py` |
| B — dữ liệu | `project/src/{core,db,crawler,scrapers,pipeline,monitor}/`, `project/scripts/maintenance/backfill_deferred.py`, `project/config/settings.yaml` |
| C — agent | `project/scripts/{article_*,build_article_prefix,agent_ingest,l1_ingest,token_ledger,handoff}.py`, `project/src/agent/`, `project/schemas/`, `.agents/dsh/` |
| D — giao hàng | `project/src/{export,users,notifier}/`, `project/scripts/{write_user_output,compile_users,pipeline_radar}.py` |
| E — harness/tài liệu | `scripts/harness_cli.py`, `docs/`, `.agents/{rules,skills,registry.yaml,pipeline.yaml}`, `okf/`, `AGENTS.md` |

---

## 2. Danh sách task

Cột: **Cấp** (1 tiny / 2 normal / C3 hard gate) · **Làn** · **Phụ thuộc** · **Proof / DoD**.

### E0 — Nền (chặn mọi việc sau)

| ID | Việc | Cấp | Làn | Phụ thuộc | Proof / DoD |
|---|---|---|---|---|---|
| T0.1 | **H.** Commit US-025…027 thành 2–3 commit theo chủ đề (script / tài liệu / ADR 0010). Commit riêng T-00 | 1 | — | — | `git status` sạch trừ dữ liệu; `pytest` PASS |
| T0.2 | `.gitignore`: `project/data/archive/`, `**/*-DESKTOP-*`, `project/src/data/` | 1 | E | — | `git status` không còn 3.350 tệp archive |
| T0.3 | **H.** Khởi động lại `morninger` bằng mã mới. Làm sau T1.1 | 1 | — | T1.1 | Radar: độ tươi cào tin 🟢; log không còn job `l1_route` |

### E1 — Dọn lane L1/Gold và fail-loud

| ID | Việc | Cấp | Làn | Phụ thuộc | Proof / DoD |
|---|---|---|---|---|---|
| T1.1 | `run_daily.ps1` hàm `Emit`: gỡ `l1_route`, `l1_ingest --code-first`, `agent_export` (dòng 96–105). Nếu script còn cần thiết thì chỉ giữ `compile_users`; nếu không thì cho nó in lệnh radar | 2 | A | — | grep 0 kết quả cho ba lệnh trong `*.ps1`; test entrypoint PASS |
| T1.2 | Chuyển script chết vào `project/scripts/_retired/` (hoặc archive ngoài repo): `l1_route`, `agent_export`, `run_agent_hierarchy`, `l1_backlog`, `process_l1_pipeline`, `run_validation`, `validate_e2e`, `run_user_workflow`, `verify_gold_quality`, `maintenance/requeue`, `maintenance/route_today_l1`, `run_pipeline.ps1`. **Trước khi chuyển:** grep import từng tệp. Giữ `check_l1_dod` (`article_expand` đang dùng). Cập nhật `test_cli_entrypoints.py`. Riêng `auto_pilot.py`: hỏi người dùng | 2 | A | T1.1 | Không còn import gãy; `pytest` PASS; radar chạy được |
| T1.3 | `src/monitor/daily_reporter.py`: gỡ khối số liệu L1/Gold (192–260); sửa cụm cấm ở :389 | 2 | B | — | Test reporter PASS; `harness_cli audit --codebase` không còn cụm cấm |
| T1.4 | `l1_ingest.py:94`, `agent_ingest.py:75`: `failed > 0` thì thoát khác 0. Gỡ bước dọn `l1_batch_*` của lane cũ (`l1_ingest.py:81-91`). Kiểm lại `article_run.py --finish` vẫn in lệnh `--only` đúng | 2 | C | — | Test mới: ingest có bản ghi hỏng → exit 1; `test_article_lane_hardening` PASS |
| T1.5 | Dọn legacy `materiality`/`event_type` còn lại:<br>• `src/agent/packet.py` (`_OUTPUT_REQUIRED_V1`)<br>• `schemas/agent-output-v1*`, `agent-instructions-v1.md`, `samples/`, `CHANGELOG.md` (thêm mục "ngừng dùng")<br>• rule `02-financial-domain-rules.md` §1<br>• skill `materiality-triage` (đánh dấu retired), `dod-gatekeeper`, `gold-financial-analyst`<br>• `docs/CODE-FIRST-LANDSCAPE.md`<br>• fixture v1 trong test ingest/DoD. **Chỉ gỡ đường nạp v1 nếu grep xác nhận không còn nguồn nào sinh v1;** nếu còn, dừng và báo | 2 | C + E | T0.1 | grep `materiality\|event_type` trong mã sống chỉ còn ở tài liệu lịch sử/ADR; `pytest` PASS |

### E2 — Tầng dữ liệu

| ID | Việc | Cấp | Làn | Phụ thuộc | Proof / DoD |
|---|---|---|---|---|---|
| T2.1a | **Vá fuzzy dedup** (`src/core/base_scraper.py:70-72`, `src/db/dedup.py`): truyền `source_domain` cùng dạng với `insert_batch` cho cả `is_similar_title` và `mark_seen`. Miễn fuzzy cho tiêu đề công bố thông tin `^[A-Z0-9]{3,4}\s*:`. Chỉ so tiêu đề **khác nguồn** | 2 | B | — | Test: cùng nguồn, hai tin CBTT khác nhau → giữ cả hai; khác nguồn, cùng tiêu đề → loại |
| T2.1b | **C3.** Fuzzy-dup không vứt: vẫn lưu Bronze và gắn `duplicate_of` + `similarity` (thêm cột hoặc bảng). Cần ADR | C3 | B | T2.1a, ADR | ADR accepted; test round-trip |
| T2.1c | **H.** Khôi phục bài đã mất: script chỉ đọc liệt kê hash có trong `seen_articles` mà không có trong `articles` (30 ngày). Người quyết định có xoá các dòng `seen` đó để lần cào sau lấy lại (nếu nguồn còn đăng) hay không | 2 + H | B | T2.1a | Báo cáo số lượng theo nguồn; lệnh xoá chỉ chạy khi đã duyệt |
| T2.2 | Đường dẫn tuyệt đối: `raw_dir`, `silver_dir`, `package_dir` suy từ `MONOCLE_DATA_DIR`. Sửa `settings.yaml:3` trỏ `C:\data`. `preflight.py` thất bại khi DB nằm trong OneDrive hoặc không tồn tại. **H:** di chuyển 2,1 GB Bronze và dọn 478 MB ở `project/src/data/` | 2 + H | B | T0.1 | Test cấu hình theo cwd khác nhau cho cùng đường dẫn; preflight test |
| T2.3 | **C3.** Bảng `capture_daily`; `backfill_deferred` ghi khối `capture`; heartbeat báo `failed` khi tỷ lệ tải chi tiết lỗi vượt ngưỡng (chỉ báo) | C3 | B | ADR | Test heartbeat; radar hiển thị |
| T2.4 | **C3.** Derive tăng dần: capture ghi chỉ mục Bronze vào DB, derive đọc phần sau watermark thay vì `rglob` | C3 | B | T2.2, ADR | Test watermark ADR 0007 vẫn PASS; đo thời gian derive |
| T2.5 | Bài sửa: bộ chọn lấy `package_path` của phiên bản mới nhất; `CONTENT_CHANGED` thì cho vào hàng chờ lại (khoá `raw_sha256`) | 2 | C | T3.5 | Test: bài có 2 phiên bản → chọn bản mới; đã phân tích bản cũ → chọn lại |
| T2.6 | Cào song song theo nguồn: mỗi nguồn một luồng, giữ nhịp chờ riêng, một luồng ghi DB | 2 | B | T2.1a | Test scraper PASS; chu kỳ đo được < 180 giây |
| T2.7 | **C3.** Nguồn có cấu trúc (CBTT HOSE/HNX/SSC, NSO). **Cần plan riêng** | C3 | B | — | Plan riêng |
| T2.8 | Gộp Silver với work_package; nén Bronze cũ hơn 30 ngày | 2 | B | T2.2 | Test tái dựng Silver từ Bronze nén |

### E3 — Tầng agent (Article Lane)

| ID | Việc | Cấp | Làn | Phụ thuộc | Proof / DoD |
|---|---|---|---|---|---|
| T3.1 | **Sửa few-shot** (`build_article_prefix.py:300,313`): thay ngành sai bằng ngành đúng của bài thép, đúng tên chuẩn trong danh mục. Sinh lại prefix. **H:** dán lại persona trong DSH, rồi khởi động lại host | 2 + H | C | — | Test: mọi `IND` trong ví dụ có trong danh mục và đúng ngữ nghĩa; hash prefix mới ghi vào handoff |
| T3.2 | **Trích dẫn tự bù** (`article_expand.py:281-288`). Phương án đề xuất: bỏ phần bù; bài có dưới 2 trích dẫn hợp lệ thì trượt nội dung và đi vào đường retry của T3.5. Sửa comment sai. **H:** duyệt phương án, vì độ phủ đợt có thể giảm | 2 + H | C | T3.5 | Test: mô hình trả 1 chỉ số → bản ghi nội dung bị loại, có lý do |
| T3.3a | Nguồn gốc: `runner.py:259-267` bỏ hằng `antigravity`/`flash`/`0.9`, ghi đúng runtime (DSH) và model thật; `MODEL_USED` (`article_expand.py:54`) đọc từ cấu hình | 2 | C | — | Test ingest: provider/model đúng |
| T3.3b | **C3.** Lưu `prefix_hash` theo dòng hoặc theo đợt (bảng wave ↔ prefix_hash) để so chất lượng giữa các phiên bản prompt | C3 | C | ADR | Test |
| T3.4 | `sentiment`/`time_sensitivity` sai định dạng: giữ giá trị mặc định nhưng **đếm và in** trong báo cáo expand và handoff (chỉ báo) | 1 | C | — | Test: 1 bản ghi sai → báo cáo đếm 1 |
| T3.5 | **Bài trượt nội dung không bị kẹt nữa:** bộ chọn bài (`article_pack.py:185-193`) nhận cả bài đã có L1 đạt nhưng chưa có `agent_outputs` đạt; giới hạn số lần thử bằng đếm lượt trượt đã có | 2 | C | T0.1 | Test: bài có L1, thiếu nội dung → được chọn; vượt số lần → không chọn, radar báo |
| T3.6 | Code chết: `categories` hai nhánh cùng `"none"` (`article_expand.py:218-222`); citation L1 chỉ lấy entity đầu | 1 | C | — | Test hiện có PASS |
| T3.7 | **C3.** Thực thể thân bài và ngành suy ra vào phân tuyến (L3): đổi `l1-entity-output` hoặc cho `user_output` đọc `article_mentions`. **ADR riêng** (đổi Data Contract) | C3 | C + D | T3.8, ADR | Eval T3.8 chứng minh recall tăng, precision không giảm |
| T3.8 | **Golden set + eval** (chia nhỏ):<br>a) `scripts/eval_sample.py` 0 token: chọn phân tầng 150–200 bài đã phân tích, xuất template gán nhãn xlsx<br>b) **H:** analyst gán nhãn (thực thể kể cả thân bài, sentiment, time_sensitivity, PASS/FAIL tóm tắt và hàm ý)<br>c) `scripts/eval_article.py`: precision/recall thực thể theo nhóm, khớp sentiment/ts, tỷ lệ PASS<br>d) `--finish` gọi eval ở chế độ chỉ báo cáo, ghi `harness_cli metric` | 2 + H | C | T0.1 | Test eval trên golden giả; số đầu tiên ghi vào `agent_metrics` |
| T3.9 | Kiểm neo tất định 0 token: số liệu và mã CP trong `s`/`k`/`im` phải có trong đoạn nguồn; in tỷ lệ theo đợt (chỉ báo) | 2 | C | — | Test: tóm tắt chứa số không có trong bài → bị đếm |
| T3.10 | `adversarial-dod-verifier`: lượt flash thứ hai trên 5% mẫu, cộng 100% bài `time_sensitivity=urgent` thuộc watchlist; ghi defect (chỉ báo). Thêm vào `conductor.ts`. Theo rule 07: story + KPI | 2 | C + E | T3.8, T3.14 | Test với stub; KPI defect_rate có dòng |
| T3.11 | Evaluator-optimizer 1 vòng: bài bị verifier gắn cờ hoặc trượt DoD được đóng gói lại kèm lý do, tối đa 1 lần | 2 | C | T3.5, T3.10 | Test packet có trường lý do; không lặp quá 1 |
| T3.12 | **C3.** Gom cụm câu chuyện: simhash LSH (+ embedding sau), bảng `story_clusters` + `story_id`; agent `story-dedup-clusterer` chỉ phân xử ca biên | C3 | B + C | T2.2, ADR | Eval độ chính xác cụm trên mẫu gán nhãn |
| T3.13 | Tự động hoá bước tay DSH: preflight so hash persona với prefix hiện hành, báo lệch; một lệnh in đường dẫn `.ts` cần chạy | 2 | C | T3.1 | Test preflight phát hiện persona cũ |
| T3.14 | US-028 — nợ registry và skill:<br>• `adversarial-dod-verifier` bỏ `pre-gold-gate`/`cost_budget`/luật 05<br>• skill `story-dedup-clusterer`, `daily-brief-synthesizer` (`model: pro` → flash, đường dẫn manifest), `l1-entity-matcher` mô tả đúng prefix thật | 2 | E | T0.1 | `yaml.safe_load`; audit không còn drift registry |

### E4 — Giao hàng

| ID | Việc | Cấp | Làn | Phụ thuộc | Proof / DoD |
|---|---|---|---|---|---|
| T4.1 | **H (định dạng giao hàng).** xlsx: thêm cột Trích dẫn (từ `citations`), dời ba cột Intent ra cuối; cùng giờ thì `urgent` lên trước | 2 + H | D | — | Cập nhật test nhãn cột; test thứ tự |
| T4.2 | **H.** Tệp theo ngày xử lý, hoặc thêm tệp "mới từ lần trước", thay cho ghi ngược vào ngày đăng | 2 + H | D | — | Test: bài xử lý muộn xuất hiện trong tệp hôm nay |
| T4.3 | Hợp nhất hai manifest user (`users/subscriptions/manifest.yaml` và `config/entities/manifest.yaml`), một ngữ nghĩa mặc định | 2 | D | — | Test `enabled_users`; `pipeline_radar users` không đổi kết quả |
| T4.4 | Radar: lệnh độ phủ theo user và entity im lặng N ngày (chỉ đọc) | 2 | D | — | Test lệnh |
| T4.5 | **H.** Nhịp đợt: Task Scheduler cho pha chuẩn bị, `--finish` và giao hàng; lịch ngoài giờ cao điểm (kiểm lại trang giá DeepSeek trước). Bước chạy DSH vẫn làm tay | 2 + H | E | T1.1, T0.3 | Runbook cập nhật; 5 ngày liên tiếp có đợt |
| T4.6 | Cảnh báo (Teams/email): mã watchlist ∧ (`urgent` ∨ cụm tăng nhanh), khử trùng theo `story_id` | 2 | D | T3.12, T4.5 | Test định tuyến cảnh báo với stub |
| T4.7 | Bản tin ngày theo user (`daily-brief-synthesizer`), mỗi ý neo `article_id` và đoạn trích | 2 | C + D | T3.12, T3.14 | Kiểm neo 100%; test grounding |
| T4.8 | **C3.** Thu phản hồi user → bảng `user_feedback` | C3 | D | ADR | Test |
| T4.9 | Hỏi đáp FTS5 + vector. **Cần plan riêng** | C3 | D | T3.7 | Plan riêng |

### E5 — Harness và tài liệu

| ID | Việc | Cấp | Làn | Phụ thuộc | Proof / DoD |
|---|---|---|---|---|---|
| T5.1 | **C3 (Harness Core).** Sửa `harness_cli.py`: bỏ `or 1` (:294), bắt buộc `--run-verify` cho normal/high-risk, `CURRENT_SCHEMA_VERSION=3`, bỏ `tool-registry` rỗng | C3 | E | ADR/duyệt | Test CLI; `query contract` khớp |
| T5.2 | Gộp tài liệu:<br>• viết lại rule 05 theo §6B; làm sạch rule 08 (:42, :64)<br>• đóng OPEN-ITEMS lỗi thời<br>• lưu trữ `AGENT_NETWORK_DESIGN.md`<br>• đánh dấu retired cho playbook okf, `okf/catalog/tables/l1_tasks.md`, skill `gold-financial-analyst` và `news-scape-agent-operations`<br>• charter cập nhật môi trường thật | 2 | E | T1.2 | `audit --codebase`: drift giảm; grep lệnh lane cũ trong `okf/` = 0 |
| T5.3 | **C3 (Harness Core).** Nới Closure/trace cho Cấp 1 TINY (sửa AGENTS.md §0) | C3 | E | duyệt | — |
| T5.4 | Pytest marker `fast` (bỏ test scraper nặng), pre-commit `ast.parse` + `pytest -m fast` | 2 | E | — | `pytest -m fast` < 60 giây |
| T5.5 | **H.** Xoá `project/.venv` (564 MB) và 12 tệp xung đột OneDrive | 1 + H | — | — | `audit --codebase` hết mục |
| T5.6 | Sinh `TEST_MATRIX.md` và `HARNESS_BACKLOG.md` từ `harness.db`; đưa chỉ số chất lượng từ T3.8 lên `audit` | 2 | E | T3.8 | Tệp sinh khớp DB |

---

## 3. Thứ tự sprint và bảng giao agent

Mỗi sprint là một story. Trong một sprint, các task cùng hàng "song song" có làn tệp khác nhau.

| Sprint | Story (đề xuất) | Song song (một agent mỗi task) | Tuần tự sau đó | Cổng người |
|---|---|---|---|---|
| **S0** | — | — | T0.1, T0.2 | Duyệt commit |
| **S1 — chặn rò và fail-loud** | "Chặn rò giá trị cấp tốc" | T1.1 (A) · T2.1a (B) · T1.4 + T3.3a + T3.4 + T3.6 (C, một agent) · T4.3 (D) · T3.14 (E) | T0.3 restart morninger | T0.3 |
| **S2 — dọn legacy** | "Dọn lane L1/Gold và trường đã ngừng" | T1.2 (A) · T1.3 (B) · T1.5 (C) · T5.2 + T5.4 (E) | — | Quyết định `auto_pilot.py` |
| **S3 — vòng chất lượng** | "Đo chất lượng Article Lane" | T3.8a + T3.8c (C) · T3.9 (C, cùng agent) · T3.1 (C, agent khác vì khác tệp) · T2.2 mã (B) · T4.1 + T4.2 (D) | T3.5 → T3.2 → T3.8d | Gán nhãn (T3.8b), dán persona (T3.1), di chuyển dữ liệu (T2.2), định dạng xlsx (T4.1/4.2) |
| **S4 — ADR Cấp 3** | Mỗi ADR một story | Soạn ADR song song: T2.1b, T2.3, T2.4, T3.3b, T3.7, T3.12, T5.1, T5.3, T4.8 | Triển khai theo ADR được duyệt | Duyệt từng ADR |
| **S5 — tầng sự kiện** | "Câu chuyện, cảnh báo, bản tin" | T3.10 · T2.6 · T4.4 | T3.11 → T4.5 → T4.6 → T4.7 | Kênh cảnh báo, lịch |
| **Sau** | Plan riêng | T2.7, T4.9, `entity-curator`, `harness-auditor`, chuỗi model flash → pro (sửa ADR 0009 D6) | — | — |

**Mẫu brief cho mỗi agent** (phiên điều phối điền):

```
Task: <ID> — <tên>
Cấp: <1|2>   Làn: <A..E>   Worktree: có
Được sửa: <danh sách tệp>
Chỉ đọc: <danh sách tệp>
Cấm: chạy đợt thật, ghi C:\data\news-scape\monocle.db, thêm cổng chặn, sửa tệp ngoài làn
Proof bắt buộc: ast.parse các tệp .py đã sửa; pytest <tệp test>; test mới cho <hành vi>
Dừng và báo nếu: cần đổi schema/Data Contract; test ngoài phạm vi gãy; grep cho thấy còn nơi dùng thứ định gỡ
Trả về: diff tóm tắt, số test PASS, rủi ro còn lại
```

---

## 4. Rủi ro của plan

| Rủi ro | Giảm thiểu |
|---|---|
| Nhiều agent sửa cùng tệp (ví dụ `article_expand.py` có trong T3.2, T3.4, T3.6) | Gộp các task cùng tệp cho một agent, hoặc chạy tuần tự |
| Gỡ script legacy làm gãy lệnh vận hành ngoài repo (Task Scheduler cũ) | T1.2 liệt kê Task Scheduler hiện có trước (chỉ đọc), rồi mới gỡ |
| T3.2 làm giảm độ phủ đợt dưới 90% | Làm T3.5 trước để bài trượt được thử lại; người duyệt phương án |
| Persona DSH lệch prefix sau T3.1 | Làm T3.13 cùng sprint hoặc ngay sau |
| Tái diễn "dựng cổng rồi gỡ" | Mọi kiểm tra mới chỉ báo cáo; muốn chặn phải có số đo từ T3.8 |

## 5. Quyết định cần người trước khi giao agent

1. Duyệt plan này và thứ tự sprint.
2. T0.1: commit nhánh hiện tại.
3. `auto_pilot.py`: giữ hay đưa vào retired.
4. T3.2: bỏ trích dẫn tự bù (độ phủ có thể giảm) hay giữ và gắn cờ.
5. T4.1/T4.2: đổi định dạng và cách đặt tên tệp giao hàng.
6. T3.8b: bố trí analyst gán nhãn.
