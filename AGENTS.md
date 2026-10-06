# AGENTS.md — Entrypoint & authority gate (news-scape)

> Read this FIRST every session. It is a small, stable shim. Detail lives in `docs/`.
> **App is what users touch. The harness is what agents touch.**

## 0. Rule number one — Classify Per-Prompt into 3 Tiers & Harness Closure

Mọi prompt/yêu cầu đều được phân loại vào **3 Cấp độ Tầm quan trọng** và BẮT BUỘC kết thúc bằng **Bảng Nghiệm thu Đóng phiên (Harness Closure Protocol)**:

```
Mọi Yêu cầu (Prompt)
  ├─ Cấp 1: TINY (Hỏi đáp, tra cứu, giải thích, patch 1-2 dòng)
  │    └─ Không chặn WIP → Trả lời/Patch → Minimal Trace vào harness.db → Harness Closure Table.
  ├─ Cấp 2: NORMAL (Tính năng mới, refactor, nghiên cứu chuyên sâu)
  │    └─ Intake → Bounded Context → WIP=1 → Story US-XXX → Proof test → Standard Trace → Closure Table.
  └─ Cấp 3: HIGH-RISK (Đổi DB Schema, sửa Data Contract, API token, Harness Core)
       └─ Intake → Dừng tại Hard Gate (status: blocked) → Lập ADR → Human Duyệt → Detailed Trace → Closure Table.
```

## 1. WIP = 1

At most **one** story `in_progress` at a time. If an urgent request interrupts, park the current story (`blocked` or `deferred`, with reason) BEFORE starting the new one. Never two `in_progress`.

## 2. OKF — where to get product context (priority order)

Read these before inventing context; do NOT create a new knowledge folder:
0. `.agents/registry.yaml` + `.agents/pipeline.yaml` — **nguồn chân lý** cho mạng lưới tác nhân (ai tồn tại, class operator/cognitive/conductor, ranh giới I/O, DoD, KPI) và DAG điều phối. **Chạy thế nào mỗi ngày:** `.agents/dsh/RUNBOOK-article-lane.md` (Article Lane trên DSH, preset `news-scape-conductor`). Thiết kế Article Lane: `plans/20260918-1651-article-lane-unified/plan.md`; quyết định ngừng lane L1/Gold: `docs/decisions/0010-ngung-lane-l1-gold-article-lane-duy-nhat.md`. Quy tắc tăng trưởng: `.agents/rules/07-agent-registry-governance.md`.

1. `.agents/skills/*` — operational & governance skills: `pipeline-radar`, `dsh-conductor` (trong `.agents/dsh/presets/news-scape-conductor/skills/`), `watchlist-curator`, `token-auditor`, `dod-gatekeeper`, `multi-agent-orchestrator-governance`, `l1-entity-matcher` (kiến thức nhận diện thực thể của `article-processor`); agent đặc nhiệm draft: `entity-curator`, `adversarial-dod-verifier`, `daily-brief-synthesizer`, `harness-auditor`. Skill `gold-financial-analyst` và `news-scape-agent-operations` mô tả lane L1/Gold đã ngừng (ADR 0010), chỉ còn giá trị tham khảo.
2. `project/docs/skills/*` — per-domain scraper knowledge (cafef, fireant, rss-sources, tnck).
3. `project/docs/{design,dev,domains,operations}/` — architecture, how-tos, source taxonomy, ops.
4. `project/docs/charter.md` + `project/docs/ARCHITECTURE.md` — goals, phases, TDRs.
5. repo `okf/` — cross-cutting operational knowledge.

## 3. Project build / run (the product lives in `project/`)

Môi trường Python được cách ly ngoài OneDrive tại `C:\venvs\news-scape`. Tuyệt đối không tạo `.venv` nội bộ.

Cây mã vận hành nằm ở `C:\src\news-scraper`, ngoài OneDrive (ADR 0020). Dữ liệu ghi nằm dưới `MONOCLE_DATA_DIR` (mặc định `C:\data\news-scape`), đường dẫn do `project/src/core/paths.py` quyết định. Dữ liệu dùng chung xuất bản một chiều lên SharePoint `FRA - Data/news/` qua `scripts/publish.py`. Thư mục `FRA_DataIngestion - news-scape` trên OneDrive là bản cũ, không chạy mã từ đó.

```powershell
# Kích hoạt môi trường (chỉ cần 1 lần / phiên terminal):
& "C:\venvs\news-scape\Scripts\Activate.ps1"

# Hoặc gọi trực tiếp Python:
# & "C:\venvs\news-scape\Scripts\python.exe" <script_path>

cd project
python -m src.morninger            # daytime pipeline (capture + re-derive Silver + drift)
python scripts/run_once.py         # one cycle
python -m pytest tests/ -v         # tests
python -m src.monitor.health       # health check

python scripts/pipeline_radar.py status                  # điểm chạm + đúng một lệnh kế tiếp
python scripts/article_run.py --where                    # đường dẫn, cwd, quyền ghi DB (0 token)
python scripts/article_run.py --wave <mã> --date <ngày> --limit <n> --batch 100   # chuẩn bị đợt
python scripts/article_run.py --wave <mã> --finish       # bung, nạp, hậu kiểm, sổ cái, bàn giao
python scripts/write_user_output.py --date today         # giao hàng

python scripts/ops_daemon.py status                      # vận hành tự chủ khi máy mở (ADR 0012): mức, đợt, breaker
python scripts/ops_daemon.py once                        # đo sensor + probe một lượt, không mở đợt
python scripts/ops_console.py                            # bảng điều khiển chữ (Ctrl+Alt+O)
python scripts/ops_daemon.py open                        # Phòng điều khiển giám sát multi-agent (ADR 0014)
```

Vận hành không giám sát do `ops_daemon` giữ (Task Scheduler `news-scape-ops`), runbook `project/docs/operations/ops-daemon.md`. Khi daemon sống ở mức ≥ L1, không mở đợt tay song song.

Mọi lệnh `scripts/...` chạy với cwd = `project/`. DB vận hành nằm ở `C:\data\news-scape\monocle.db`, ngoài kho mã. Sandbox `workspace-write` của DSH không mở rộng được ra ngoài kho, nên `--finish` và `write_user_output.py` chạy với `danger-full-access`. Chuẩn bị đợt và chạy mô hình không cần quyền này.

## 4. Harness map (read as the phase needs — bounded context)

| Doc                                                         | Purpose                                                                                        |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| [docs/GLOSSARY.md](docs/GLOSSARY.md)                         | Vocabulary (read once).                                                                        |
| [docs/HARNESS.md](docs/HARNESS.md)                           | The collaboration model + change loop + Done definition.                                       |
| [docs/FEATURE_INTAKE.md](docs/FEATURE_INTAKE.md)             | Risk classification → lane (do this before any change).                                       |
| [docs/CONTEXT_RULES.md](docs/CONTEXT_RULES.md)               | Bounded context & token budgets (Phase × Lane).                                               |
| [docs/TRACE_SPEC.md](docs/TRACE_SPEC.md)                     | 3-tier trace schema & scoring specification.                                                   |
| [docs/HARNESS_COMPONENTS.md](docs/HARNESS_COMPONENTS.md)     | 11 runtime responsibilities.                                                                   |
| [docs/HARNESS_MATURITY.md](docs/HARNESS_MATURITY.md)         | H0–H5 maturity ladder & criteria.                                                             |
| [docs/TOOL_REGISTRY.md](docs/TOOL_REGISTRY.md)               | Tool manifest & degrade ladder.                                                                |
| [docs/HARNESS_AUDIT.md](docs/HARNESS_AUDIT.md)               | Entropy scoring & 7 drift checks (bao gồm codebase hygiene).                                  |
| [docs/IMPROVEMENT_PROTOCOL.md](docs/IMPROVEMENT_PROTOCOL.md) | Closed-loop propose & outcome measurement.                                                     |
| [docs/TEST_MATRIX.md](docs/TEST_MATRIX.md)                   | Proof vocabulary & live proof table query.                                                     |
| [docs/SESSION-LATEST.md](docs/SESSION-LATEST.md)             | "Where am I, what next" — read at start, overwrite at end.                                    |
| [docs/OPEN-ITEMS.md](docs/OPEN-ITEMS.md)                     | Việc tồn đọng trên đường giao hàng: mục CHẶN, bước triển khai, quyết định treo. |

## 5. Harness CLI (Durable Layer H2-H5)

```powershell
python scripts/harness_cli.py query contract        # Check harness capabilities & schema state
python scripts/harness_cli.py query matrix          # Query live story proof matrix
python scripts/harness_cli.py audit                 # Run entropy & drift audit
python scripts/harness_cli.py audit --codebase      # Full audit: drift + Git hygiene + AST + conflicts
python scripts/harness_cli.py propose               # Generate self-improvement proposals
```

Maturity: this harness is at **H2-H5 (Durable SQLite + Active Observability + Auto-Verification + Self-Improvement Protocol)**.

## 6. Core Architecture Boundaries & Invariants (Scope Định vị Toàn Dự Án)

**Article Lane là đường xử lý duy nhất (ADR 0010, 2026-09-23).** Lane L1/Gold hai tầng (`l1_route` → `agent_l1` → `agent_export` → `agent_gold`) đã ngừng hẳn: không còn trong preset, scheduler, radar hay pipeline. Không gọi `l1_route.py`, `l1_ingest.py --code-first`, `agent_export.py` hay `requeue.py`.

**Thu thập trọn vẹn, xử lý về sau (ADR 0013, rule 10, ghim 2026-10-01).** Nguồn có bao nhiêu bài thì lấy về bấy nhiêu. Tầng cào không lọc theo độ giống, chuyên mục hay độ liên quan, và không dừng cứng ở trang 1. Mọi URL phát hiện được đều có dấu vết trong sổ phát hiện. Loại trùng, làm sạch, xếp ưu tiên là bước sau Bronze và không xoá bài. Bài trùng được giữ đủ nguồn và thời điểm vì tần suất đưa tin là tín hiệu.

### A. Ranh giới Phân công: Script (0 token) và Agent

1. **Script tất định (0 token)**:
   - **Bronze**: cào và lưu nguyên bản bất biến (`raw_html` + `.meta.json`) để kiểm toán và đối chiếu SHA256.
   - **Silver**: chuẩn hoá DOM, SimHash, tách nội dung thành các đoạn văn (`<p>`).
   - **Đóng gói đợt** (`article_run.py` → `article_pack.py`): chọn bài chưa được mô hình phân tích, xếp tầng ưu tiên, ghi packet `data/agent_tasks/article/`, sinh sẵn chương trình điều phối `wave_<mã>.conductor.ts`.
   - **Hoàn tất đợt** (`article_run.py --finish`): bung bản ghi gọn thành hai lược đồ, nạp qua cổng DoD (`l1_ingest.py`, `agent_ingest.py`, chỉ tệp của đúng đợt), hậu kiểm độ phủ, ghi sổ cái token, sinh bàn giao.
   - **Giao hàng**: phân tuyến theo watchlist, xuất `users/output/<user>/<date>.xlsx`.
2. **Agent `article-processor`** (công cụ `agent_article` trên DSH hoặc runner `agy`/`openrouter`, không tool, đúng một bước mỗi lô): xử lý **trọn một bài trong một lượt**, gồm cả hai lớp nghiệp vụ:
   - **Nhận diện thực thể** từ tiêu đề và nội dung: mã CP, doanh nghiệp, sàn, ngành, chỉ số, vĩ mô → `l1-entity-output-v1`.
   - **Phân tích nội dung**: tóm tắt, luận điểm, hàm ý thị trường, `sentiment`, `time_sensitivity`, trích dẫn theo chỉ số đoạn → `agent-output-v2-lean`.
   - **Đầu ra sạch**: không sinh `materiality`, `event_type`, `impact_area`. Ba trường này đã ngừng dùng ở mọi tầng (mô hình, DB mới, giao hàng).

### B. Bất biến của Article Lane

- **Một đợt = một lệnh `run_code`.** Phiên điều phối chạy trọn `wave_<mã>.conductor.ts` trong một bước. Chương trình đọc hết packet trước, hâm cache, chạy mọi lô song song, ghi đầu ra thẳng ra đĩa, và chỉ trả về con số.
- **`--batch` là cách chia lô duy nhất.** Không trần token hay trần ngữ cảnh nào chia lô hộ. Lô trả về thiếu bài thì `--repair` đóng gói lại đúng phần thiếu.
- **Token là số ghi nhận, không phải cổng.** Không có giới hạn hay mức cảnh báo token nào, theo bài, theo lô hay theo đợt. Sổ cái (`token_ledger`, chỉ tính phiên worker) ghi token và USD để người dùng tự đánh giá, tự ước lượng. Không dừng đợt, không giảm số bài, không chia nhỏ lô vì token.
- **Đọc trọn nội dung.** Packet mang toàn bộ đoạn văn nguyên văn của bài (trần chắt lọc đã tắt). Chỉ giữ tiêu đề và đoạn văn, bỏ link, ảnh, menu. Không dòng nào vượt trần cắt dòng của công cụ đọc.
- **Trích dẫn theo chỉ số đoạn.** Mô hình trả chỉ số, script dựng lại đoạn nguyên văn, nên trích dẫn đúng nguyên văn do cấu trúc.
- **Mọi bài đều được xử lý đầy đủ.** Xếp tầng theo watchlist (nhận rộng: mã theo dõi, ngành liên quan, vĩ mô khẩn) chỉ quyết định **thứ tự**, không quyết định độ sâu. Không còn lọc Subscriber-Gated. Một ngoại lệ có hiệu lực theo ADR 0016 (2026-10-02): bài `copy` (nội dung trùng tuyệt đối, hoặc containment từ 0,95 và cùng số liệu, cùng mã CP) không vào packet và nhận kết quả `l1_source = 'inherited'` từ bài gốc. Bản viết lại và bài cùng sự kiện vẫn được phân tích đầy đủ.
- **Đối chiếu tất định chỉ để kiểm, không để thay.** Bộ nhận diện theo danh mục (có `Capitalized Suffix Guard` và `Prefix Guard`) được dùng để đối chiếu với kết quả mô hình. Bản code-first không bao giờ được tính là "đã phân tích" (`l1_source = 'code_first'` bị loại khỏi mọi phép đếm và khỏi bộ chọn bài).
- **Cổng thật của một đợt là cổng kỹ thuật.** DB ghi được (kiểm trước khi tiêu token), nạp không lỗi, độ phủ của đợt ≥ 90% ở cả hai lớp. Chỉ khi cả ba đạt thì `--finish` mới thoát 0 và in `✅ ĐỢT <mã> HOÀN TẤT`.
- **Bảo toàn raw gốc.** `raw_html` và `meta.json` luôn giữ nguyên tại Bronze để kiểm toán.

### C. Cấm Giả lập Trí tuệ Agent bằng Script (No Script Emulation)

- **Không viết script thay agent.** Không dùng regex hay heuristic để sinh kết quả nhận diện hay phân tích.
- **Vùng độc quyền của LLM.** Ngữ nghĩa, trích xuất thực thể, tóm tắt, hàm ý và trích dẫn là việc của `article-processor`, gọi qua `tools.agent_article` trong chương trình điều phối. Provider và model nào cũng đi qua một hợp đồng đầu ra và một hàm kiểm duy nhất (ADR 0017, rule 11); provider mới phải qua bộ vàng, chuẩn đo là agy, `claude` chưa thuộc lane. ADR 0009 D6 (mọi model là `deepseek-flash`) không còn đúng.
- **Zero Hallucination User Manifest.** Khi báo cáo phân phối, chỉ tham chiếu người dùng đang bật trong `project/config/entities/manifest.yaml`. Tra bằng `pipeline_radar.py users`, không chép danh sách vào tài liệu.

## 7. Code Quality & Production Docstring Standards (Bắt Buộc Cho Mọi Agent)

Chi tiết quy chuẩn bất biến tại [`.agents/rules/06-code-and-docstring-standards.md`](.agents/rules/06-code-and-docstring-standards.md):

- **Chuẩn Google Style**: Dòng 1 câu mệnh lệnh kết thúc bằng dấu chấm; các section `Args:`, `Returns:`, `Raises:` đầy đủ kiểu và mô tả ngắn gọn. Module docstring đúng 1 câu khẳng định.
- **Triệt tiêu Blacklist**: Tuyệt đối không dùng từ nối thừa (`nhìn chung`, `thông thường`, `về cơ bản`, `cần lưu ý rằng`, `đáng chú ý`), đại từ ngôi thứ nhất (`chúng ta`, `tôi`), câu hỏi tu từ, emoji, thẻ tạm (`[LEGACY]`, `TODO tạm thời`).
- **Production Deliverable**: Docstrings và comments chỉ nói rõ nhận gì, làm gì, trả về gì và giải thích logic phức tạp không hiển nhiên. Không đưa nhật ký gỡ lỗi hoặc giải trình lịch sử vào mã nguồn.
- **Kiểm định Bắt buộc**: Mọi thay đổi code phải vượt qua kiểm tra cú pháp AST (`ast.parse`) và bảo đảm toàn bộ unit test (`pytest tests/`) luôn PASS 100%.

## 8. Zero-Probe Context & Continuous Agent Training (Bắt Buộc Cho Mọi Phiên)

Chi tiết quy chuẩn bất biến tại [`.agents/rules/08-context-and-zero-probe-guardrails.md`](.agents/rules/08-context-and-zero-probe-guardrails.md):

- **Nguyên tắc "Radar-First, Never Probe" (Zero-Probe)**: CẤM TUYỆT ĐỐI việc tự ý chạy các câu lệnh python one-liner (`-c "import sqlite3..."`) hoặc quét file ad-hoc chỉ để lấy ngữ cảnh. Mọi ca làm việc BẮT BUỘC dùng lệnh duy nhất:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py status
  ```
  Radar cung cấp đầy đủ thông tin pipeline và chỉ định chính xác 1 câu lệnh thực thi tiếp theo, theo vòng đời đợt Article Lane. Câu hỏi về đường dẫn, cwd hay quyền ghi DB thì hỏi `project/scripts/article_run.py --where`. Câu hỏi nào hai lệnh này chưa trả lời được thì báo thiếu lệnh, không đi đào mã nguồn.
- **Tách vai điều phối và kiểm toán**: luật Zero-Probe ràng buộc phiên điều phối. Phiên kiểm toán sau đợt được đọc mã và truy vấn chỉ đọc, nhưng mỗi phát hiện phải kết thúc bằng một lệnh hoặc bản vá script.
- **Progressive Bounded Context**: Không đọc các tệp từ điển khổng lồ (`entities.json` 1.5 MB) hay dump thư mục thô. Chỉ nạp tối đa 3 tệp ban đầu (`AGENTS.md`, `SESSION-LATEST.md`, Skill chuyên trách).
- **Continuous Policy Distillation (/learn)**: Mọi ma sát phát sinh (permission timeout, cờ lệnh tối ưu, thực thể mới) phải được đúc kết ngay thành Rule, cập nhật vào Skill runbook và `SESSION-LATEST.md` trước khi đóng phiên, đảm bảo các thế hệ Agent tiếp theo kế thừa trọn vẹn và không lặp lại sai sót.

## 9. Cổng Nghiệm Thu Hạ Tầng Trước Khi Vận Hành (Bắt Buộc Mọi Phiên Trên DSH)

Chi tiết quy chuẩn bất biến tại [`.agents/rules/09-dsh-preflight-gate.md`](.agents/rules/09-dsh-preflight-gate.md):

- **Không gõ lệnh đợt khi chưa qua cổng.** Mọi phiên chạy trên DSH PHẢI nghiệm thu hạ tầng trước khi vận hành, bằng 14 hạng mục trong **một** lệnh `run_code` (0 token). Cổng này trả lời dứt khoát câu hỏi *"hạ tầng đã đủ điều kiện gõ lệnh đợt chưa?"* bằng số đo, không bằng cảm nhận.
- **Không tin YAML, tin runtime.** Preset nạp **lúc mount**, không phải lúc sửa tệp. So `StartTime` của tiến trình cổng 3080 với `LastWriteTime` của `agent.cordis.yml`: tệp mới hơn tiến trình nghĩa là bản sửa **chưa có hiệu lực**, và triệu chứng duy nhất là hoá đơn sai.
- **Phân định tệp nạp lúc mount và tệp đọc live.** `agent.cordis.yml`, `preset.yml`, `~/.dsh/settings.yaml` cần restart host; `skills/**/SKILL.md`, `.agents/rules/*.md`, RUNBOOK và script Python thì không. Tra bảng ở §3 của rule trước khi kết luận.
- **Không có mục XÁM.** Mỗi hạng mục là ĐỎ hoặc XANH; "chắc là được" tính là ĐỎ, và ĐỎ chặn đợt. Không có ngoại lệ "chạy tạm rồi sửa sau".
- **Không restart host, nhưng phải mở phiên mới.** Hai việc khác nhau: restart là tắt/chạy lại `dsh web` (Conductor không tự làm được vì nó chạy bên trong tiến trình đó); mở phiên mới là thao tác người vận hành làm ở tầng UI, với preset chọn **trước** khi gửi tin đầu tiên.

## 10. Thu Thập Trọn Vẹn, Không Bỏ Sót (Bắt Buộc Cho Mọi Thay Đổi Tầng Cào)

Chi tiết quy chuẩn bất biến tại [`.agents/rules/10-thu-thap-tron-ven.md`](.agents/rules/10-thu-thap-tron-ven.md), quyết định tại [`docs/decisions/0013-thu-thap-tron-ven-xu-ly-ve-sau.md`](docs/decisions/0013-thu-thap-tron-ven-xu-ly-ve-sau.md):

- **Lấy về tất cả.** Raw có bao nhiêu tin thì lấy về bấy nhiêu. Không lọc ở tầng cào, trừ bản sao kỹ thuật cùng URL chuẩn hoá (vẫn ghi thành bí danh).
- **Không có trạng thái "đã bỏ".** Mọi URL phát hiện được đều vào sổ phát hiện trước mọi bước lọc. Trạng thái cuối chỉ là `captured`, `alias`, `gone` hoặc `dead_letter` có lý do.
- **Phân trang theo watermark, tự bù sau khi máy tắt, đối chiếu sitemap hằng ngày.** Thiếu so với kênh đối chiếu > 2% trong một ngày là ĐỎ.
- **Trùng lặp là dữ liệu.** Bài trùng có thể miễn LLM, nhưng luôn được giữ và đếm vào chỉ số tần suất, độ rộng đưa tin.

## 11. Bất Biến Đóng Phiên & Quản Trị Git Cơ Học (Bắt Buộc Cho Mọi Phiên)

- **Cấm Treo Cây Làm Việc Dồn Ứ (No Dangling Dirty Tree)**: Mọi ca làm việc có sửa đổi mã nguồn hoặc tài liệu BẮT BUỘC phải thực thi `& "C:\venvs\news-scape\Scripts\python.exe" scripts/harness_cli.py git status`. Nếu `clean_for_closure == false`, Agent KHÔNG ĐƯỢC PHÉP coi là hoàn tất phiên.
- **Quy Chuẩn Commit Cơ Học**: Bắt buộc tạo commit Conventional Commits (≤ 72 ký tự, mang mã `(US-XXX)`) bằng công cụ `harness_cli.py git template` và đẩy mã nguồn (`git push origin <branch>`) trước khi bàn giao `SESSION-LATEST.md`.

