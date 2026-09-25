# Kiểm toán D — Harness, mạng lưới agent và độ trôi tài liệu

- **Ngày:** 2026-09-24 · **Nhánh:** `feature/article-lane-remove-gates` (còn thay đổi chưa commit)
- **Phạm vi:** `.agents/**`, `docs/**`, `project/docs/**`, `okf/**`, `README.md`, `project/README.md`, `plans/`, `harness.db` (đọc `mode=ro`), `scripts/harness_cli.py`
- **Cách làm:** chỉ đọc. Grep lệnh cấm và trường đã ngừng, quét link chết bằng script (link markdown và đường dẫn trong backtick, đối chiếu cả với gốc repo và `project/`), quét mã hoá (UTF-8 hợp lệ, BOM, mẫu mojibake), truy vấn `harness.db` chỉ đọc.
- **Nhãn đối chiếu:** **[PLAN Tx.y]** = đã có trong `plans/20260924-research-council-execution/plan.md`, không cần mở việc mới, chỉ cần bổ sung phạm vi khi ghi chú. **[MỚI]** = plan chưa có.

---

## 0. Kết luận ngắn

1. **Lớp điều hành đúng, lớp xung quanh vẫn chạy theo lane cũ.** `AGENTS.md`, `registry.yaml`, `pipeline.yaml`, `RUNBOOK-article-lane.md`, skill `dsh-conductor` và `pipeline-radar` khớp ADR 0010. Nhưng `AGENT_RUNBOOK.md`, 4 skill quản trị, 4 rule, `dsh/README.md`, `okf/index.md` và phần lớn `project/docs/operations` + `design/13,15,17` vẫn dạy lane L1/Gold như đường đang chạy. Rule 08 bắt agent đọc skill chuyên trách, nên agent tuân luật vẫn có thể bị dẫn vào lane đã chết. Radar cũng từng dẫn sai theo đúng cách này (ADR 0010 §1).
2. **Plan research-council đã phủ khoảng 40% phát hiện tài liệu** (T5.2, T5.6, T3.14, T1.5, T4.3). Nó **bỏ sót** `.agents/AGENT_RUNBOOK.md`, `.agents/dsh/README.md`, 3 skill quản trị (`token-auditor`, `multi-agent-orchestrator-governance`, `dsh-preflight-validator`), rule 01/02/07, `project/docs/**` và bảng `decision`/`backlog`/`story` trong `harness.db`.
3. **harness.db:** WIP=1 đạt (0 story `in_progress`). Có 4 story treo gắn với lane đã ngừng. Bảng `decision` chỉ có 4/10 ADR. 12 mục backlog mở đã lỗi thời. `agent_metrics` không có dòng nào cho `article-processor`. Việc ngừng `materiality` (trace #80, chạm `AGENTS.md` và registry, tức Harness Core) **không có story và không có ADR**.
4. **Mã hoá:** không có tệp nào hỏng. `SESSION-LATEST.md` là UTF-8 hợp lệ, không BOM. Chuỗi `â€”` chỉ xuất hiện khi Windows PowerShell 5.1 đọc tệp UTF-8 không BOM theo code page ANSI (chi tiết ở §3).

---

## 1. `.agents/**`: mâu thuẫn với ADR 0010 và AGENTS.md

### 1.1 `.agents/AGENT_RUNBOOK.md`: lỗi thời toàn bộ, nghiêm trọng nhất [MỚI]

- Commit cuối 2026-09-17, trước Article Lane.
- `:27` stage `l1_route` **active** với lệnh `scripts/l1_route.py --from-db --date today --mini-batch 25`. Đây là lệnh AGENTS.md §6 cấm.
- `:28-34` `l1-entity-matcher`, `gold-exporter` (`agent_export.py … --subscriber-only`), `gold-financial-analyst` đều ghi **active**. Có stage `materiality_triage` (`:30`) dù agent đã retired.
- `:59` "Conductor chạy: L1 (route → match → ingest) rồi Gold (export → analyze → ingest → deliver)".
- `:80-83` mẫu ghi KPI cho `l1-entity-matcher`/`gold-financial-analyst` với định mức token 12.250/14.700. Đây là con số định mức đã bị bác (registry `:199-203`).
- `:5` và `:87-88` coi `news-scape-agent-operations` là "thư viện lệnh". Skill này đã hết hiệu lực (AGENTS.md §2).
- `AGENTS.md` không còn trỏ tới tệp này, nhưng `registry.yaml` và rule 07 vẫn dẫn gián tiếp qua `AGENT_NETWORK_DESIGN.md`.
- **Đề xuất:** thu tệp này về một trang bảng stage → lệnh sinh từ `pipeline.yaml` (scrape → article_pack → article_analyze → article_expand → deliver). Cách khác là chuyển sang `docs/archive/` và đặt redirect tới `.agents/dsh/RUNBOOK-article-lane.md`. Giữ §4 (kích hoạt agent draft) và chuyển nó vào rule 07.

### 1.2 `.agents/AGENT_NETWORK_DESIGN.md` [PLAN T5.2 — "lưu trữ"]

- `:23-24` operator mẫu là `l1_route`, `agent_export`, `pruner`; cognitive agent là `l1-entity-matcher`, `gold-financial-analyst`, gọi qua `invoke_subagent`.
- `:85-91` DAG cũ có `filter: subscriber_gated`. `:128` Materiality Triage là roadmap.
- **Đề xuất:** làm theo T5.2. Trước khi lưu trữ, chuyển 3 khái niệm còn sống (3 spine, class operator/cognitive/conductor, KPI ledger) vào phần đầu `registry.yaml` hoặc rule 07.

### 1.3 `registry.yaml`: ranh giới I/O sai với script thật [MỚI, trừ ý cuối]

| Dòng | Sai | Thật | Đề xuất |
|---|---|---|---|
| `:117`, `:349` | `delivery-writer`, `daily-brief-synthesizer` đọc `users/input/manifest.yaml` | Thư mục `users/input/` **không tồn tại**. `src/users/compile.py:16,347` đọc `users/subscriptions/manifest.yaml`, còn `pipeline_radar.py:40` đọc `project/config/entities/manifest.yaml` | Sửa theo T4.3 sau khi hợp nhất manifest. Trước mắt ghi đúng tệp mà `compile.py` đọc |
| `:46,59,72,103,117,130,187,314,349` | `data/monocle.db` | DB vận hành ở `C:\data\news-scape\monocle.db` (`settings.yaml:6`, AGENTS.md §3) | Thay bằng `$MONOCLE_DB (C:\data\news-scape\monocle.db)` |
| `:128` | `cli: article_run.py --wave <wave> --today` | AGENTS.md §3 và `pipeline.yaml` dùng `--date <ngày> --limit <n> --batch 100`. Memory ghi rằng việc ghim `--date` là bài học từ W365 | Đổi sang `--date` |
| `:135` | `article-packer` "chắt lọc đoạn tất định" | AGENTS.md §6B: "Đọc trọn nội dung (trần chắt lọc đã tắt)" | Sửa thành "mang trọn đoạn văn nguyên văn" |
| `:8`, `:35` | cognitive "gọi qua `invoke_subagent`" | DSH: `tools.agent_article` trong `run_code` | Sửa chú thích class |
| `:209` | `article-processor.skill` = `l1-entity-matcher/SKILL.md`. Skill này mô tả I/O `data/agent_tasks/l1/*.task.json` + `view_file`/`write_to_file` (`SKILL.md:11,117-120`), trái với `tools_allowed: []` | Worker không có tool nào, nhận packet trong prompt | [PLAN T3.14] viết lại §1/§5 của skill theo prefix thật |
| `:376-384` `governance_skills` | Thiếu `pipeline-radar`, `dsh-preflight-validator`, `dsh-conductor`, `find-skills`. Mô tả `token-auditor` nói "hiệu quả subscriber-gating". `news-scape-agent-operations` ghi là "runbook canonical" | Hai mục cuối đã hết hiệu lực | Cập nhật danh mục. Đánh dấu `news-scape-agent-operations` là `retired` |

### 1.4 Skill còn dạy lane cũ

| Skill | Bằng chứng | Nhãn | Đề xuất |
|---|---|---|---|
| `token-auditor` | `:3` "cảnh báo vượt hạn mức". `:27-30` "Bất biến Subscriber-Gating (ADR 0005)" và `L1_ONLY`. `:31-43` pruner 2.200 ký tự, phễu 4 tầng, L1 25 bài/lô, Gold 5 bài/lô. `:46` "van xả khi vượt ngân sách: siết trần token mỗi bài". Cả ba điều này trái với nguyên tắc "token là số ghi nhận, không phải cổng" | [MỚI] | Viết lại quanh `token_ledger.py report/verify`. Bỏ §1.2–§1.6 |
| `multi-agent-orchestrator-governance` | `:65` Subscriber-Gating. `:125-145` câu lệnh mồi "thực thi trọn vẹn chuỗi L1 (Code-First… mini-batches)". Registry vẫn neo `master-orchestrator` vào skill này (`registry.yaml:31`) | [MỚI] | Trỏ `master-orchestrator` sang `dsh-conductor`. Chuyển skill này về lưu trữ hoặc thu gọn còn phần RCA |
| `news-scape-agent-operations` | `:71` `invoke_subagent`. Sơ đồ Phase 1 có "Smart Paragraph Distillation" | [PLAN T5.2] | Đánh dấu retired (frontmatter `status: retired` + dòng redirect) |
| `gold-financial-analyst` | `:3` "chấm điểm materiality_score" | [PLAN T1.5/T5.2] | Như trên |
| `materiality-triage` | Toàn bộ tệp. Registry đã ghi retired, nhưng skill **không** có dấu retired | [PLAN T1.5] | Thêm dấu retired ở đầu tệp |
| `dod-gatekeeper` | `:15` còn nhắc `materiality` trong danh sách trường | [PLAN T1.5] | — |
| `dsh-preflight-validator` | `:3,67,117` "12 hạng mục", trong khi rule 09 `:131` và AGENTS.md §9 ghi **14**. `:46,105,139` mục D2 bắt "Conductor TỰ chạy `requeue --apply`": `requeue.py` là lệnh cấm (AGENTS.md §6). Trace #81 đã ghi nhận ma sát này. `:43` "Kiểm junction preset" trái với `dsh/README.md:30-41` (junction bị discovery bỏ qua) | [MỚI] | Bỏ D2. Đồng bộ số hạng mục với rule 09. Thay kiểm junction bằng kiểm `cordis.patch.yml` |
| `daily-brief-synthesizer` | `:80` `model: pro` | [PLAN T3.14] | — |
| `l1-entity-matcher` | Mô tả "từ tiêu đề". AGENTS.md §6A nói article-processor nhận diện "từ tiêu đề và nội dung" | [PLAN T3.14] | — |

### 1.5 Rule

| Rule | Bằng chứng | Nhãn | Đề xuất |
|---|---|---|---|
| 05 | `:33` §2.2 "Lọc Đoạn Giá Trị Cao… loại bỏ lịch sử thành lập, giải thích thuật ngữ…". Trái với nguyên tắc "đọc trọn nội dung" | [PLAN T5.2] | Viết lại theo §6B |
| 08 | `:42` bộ ba tệp gợi ý đọc skill `news-scape-agent-operations`/`gold-financial-analyst`. `:64` ví dụ cờ `l1_route.py`. `:83` ví dụ `l1_router.py` | [PLAN T5.2] | — |
| 01 | `:6` "trên nền tảng Antigravity 2.0" | [MỚI] | Đổi thành DSH (ADR 0009) |
| 02 | `:6` "Subagent Gold Analyst trên Antigravity 2.0". `:8-10` thang `materiality_score` | [PLAN T1.5 chỉ nhắc §1] | Gỡ §1 và dòng mở đầu |
| 07 | `:10` cognitive gọi qua `invoke_subagent` | [MỚI] | Sửa cùng registry `:8` |
| `entity-system-invariants` | `:42` "Export Gate: `final.csv`…" dùng tên tệp giao hàng cũ (nay là `.xlsx`) | [MỚI] | Sửa tên deliverable |

### 1.6 `.agents/dsh/**`

- `dsh/README.md:10` "Row `agent_l1`/`agent_gold` **còn trong tệp**". Thực tế `agent.cordis.yml:545` ghi đã gỡ ngày 23/09. **[MỚI]** Sửa lại câu này.
- `dsh/README.md:24` neo "ADR 0008 (cổng + trần token)". Phần trần token đã hết hiệu lực theo ADR 0010 §2.5. **[MỚI]**
- `dsh/README.md:55` "Preset + skill + **junction** ✅" mâu thuẫn với `:30-41` của chính tệp này. `DSH-VIEC-THU-CONG.md:8,64` cũng còn nói "junction preset". **[MỚI]** Thống nhất một cách wiring (patch root cấu hình).
- `dsh/README.md:52-56` bảng trạng thái H1–H4 (⏳/⏸️) là trạng thái của plan DSH 17/09. Plan đó đã bị vượt qua (xem §4). **[MỚI]** Xoá bảng này.
- `dsh/RUNBOOK.md`: tự ghi là lịch sử (README `:14`), nhưng vẫn nằm cạnh runbook hiện hành và `DSH-VIEC-THU-CONG.md:5` còn dẫn tới. `DSH-WAVE-W365-HANDOFF.md` là bàn giao của một đợt đã xong. **[MỚI]** Chuyển cả hai vào `.agents/dsh/archive/`.
- `RUNBOOK-article-lane.md:202` và ADR 0010 §3 ("Không script vận hành nào đọc bảng `l1_tasks`") lệch nhau. Theo US-025, `L1Runner` vẫn **ghi** `l1_tasks route=article_lane`. **[MỚI]** Sửa câu trong ADR 0010 §3 thành "không script nào đọc `l1_tasks` của lane cũ".
- Phần khớp: preset không còn row cũ. Worker dùng `deepseek-flash`, `reasoningEffort: "off"`, `maxDepth: 1` và không có `maxTokens` (`agent.cordis.yml:525-542`). Skill `dsh-conductor:150` cấm lệnh lane cũ đúng như AGENTS.md.

### 1.7 Đối xứng registry ↔ skill

- Mọi agent trong registry đều có tệp skill tồn tại. `article-processor` mượn skill `l1-entity-matcher` (xem §1.3).
- Có 5 skill không phải agent: `dod-gatekeeper`, `token-auditor`, `watchlist-curator`, `git-codebase-governance`, `sharepoint-git-hybrid-workspace`. Chúng có trong `governance_skills`. Ba skill `pipeline-radar`, `dsh-preflight-validator`, `find-skills` (skill ngoài, cài từ vercel-labs, trace #64) thì không có trong danh mục.
- Bốn agent draft (`story-dedup-clusterer`, `adversarial-dod-verifier`, `daily-brief-synthesizer`, `entity-curator`) và `harness-auditor` chưa có story. Rule 07 yêu cầu "1 entry + 1 skill + 1 stage + 1 story + KPI". Việc này chưa vi phạm vì chúng còn ở draft. **Đề xuất:** ghi rõ trong rule 07 rằng story chỉ bắt buộc khi agent chuyển sang active.

---

## 2. `docs/`, `project/docs/`, `okf/`, README

### 2.1 Tài liệu harness ở `docs/`

| Tệp | Vấn đề | Nhãn | Đề xuất |
|---|---|---|---|
| `TEST_MATRIX.md:36-44` | Bảng chụp dừng ở US-015, trong khi DB có tới US-027. `:39` ghi US-004/006/007 "`lost` — file story MẤT", nhưng `docs/stories/US-004…`, `US-006…`, `US-007…` **đang tồn tại** và DB ghi `implemented`. US-003 ghi `implemented` nhưng không có dòng nào trong bảng `story` | [PLAN T5.6] | Sinh bảng từ DB. Xoá dòng `lost` |
| `HARNESS_BACKLOG.md` | Bản markdown lệch với DB: #8 ghi open trong md nhưng đã resolved trong DB. #2 và #3 khác tiêu đề. Md dừng ở #8, DB có 28 mục | [PLAN T5.6] | Sinh từ DB |
| `HARNESS_MATURITY.md:16` | H3 hứa có lệnh `score-trace`, `score-context`. Hai lệnh này chỉ nằm trong `CAPABILITIES` (`harness_cli.py:33-34`), **không có subcommand**. Điểm được tính ngầm trong `trace` (`:392-413`) | [MỚI] | Sửa câu chữ, hoặc bỏ hai mục khỏi `CAPABILITIES` (gộp vào T5.1) |
| `HARNESS_AUDIT.md:9-19` | Ghi "7 drift checks". `cmd_audit` có 6 nhóm (`harness_cli.py:456-552`). Mục 5 hứa kiểm "thiếu ADR" nhưng mã chỉ kiểm intake | [MỚI] | Đồng bộ số và mô tả |
| `TOOL_REGISTRY.md` | Không có `dsh`, `token_ledger`, `pipeline_radar`, `article_run --where`. Bảng `tool` trong DB có 0 dòng | [PLAN T5.1 bỏ `tool-registry`] | Thêm 3 công cụ vận hành thật, hoặc gộp vào `.agents/registry.yaml` |
| `ARCHITECTURE.md:10` | Trỏ tới `project/docs/ARCHITECTURE.md`, trong khi tệp thật là `architecture.md` (chữ thường; chỉ chạy được trên Windows vì không phân biệt hoa thường). `:20` nhắc thư mục `harness/` không tồn tại. `:22` nhắc `project/plans/*` không tồn tại (plan nằm ở `plans/`). `:35` "Gold (deferred)". AGENTS.md `:32` có cùng lỗi chữ hoa | [MỚI] | Sửa 4 chỗ |
| `GLOSSARY.md:35` | "Gold — **deferred** by design". Không có mục Article Lane, đợt (wave), packet, conductor, `article-processor`, sổ cái token | [MỚI] | Bổ sung khoảng 8 thuật ngữ và bỏ "deferred" |
| `CONTEXT_RULES.md:44` | Tên công cụ `grep_search`, `find_by_name` là của Antigravity | [MỚI] | Viết trung tính theo nền tảng |
| `OPEN-ITEMS.md:1-6` | Tiêu đề "tuyến **L1** → giao hàng". Số đo lấy từ **bản sao** `project/data/monocle.db` ngày 07/09. A0-1…A0-4 đã được US-016…019 xử lý nhưng vẫn nằm ở mục mở. `:203-208` C2 "Không có runner LLM… `agent_stub.py` không tồn tại" đã lỗi thời (Article Lane chạy trên DSH). C1 nói về `l1_outputs` nguồn agent của lane cũ | [PLAN T5.2 "đóng OPEN-ITEMS lỗi thời"] | Chuyển A0-1…4 và C2 sang §D kèm kết quả đo. Đổi tiêu đề |
| `CODE-FIRST-LANDSCAPE.md:23-41` | Mô tả job `l1_route` 15 phút của `morninger` như đang chạy, và `materiality` | [PLAN T1.5] | Thêm dòng đầu: "Lịch sử, trước ADR 0010" |
| `SESSION-LATEST.md` | "Updated 2026-09-23", nhưng phiên 24/09 đã có trace #77–82 (council, ngừng materiality). §"Việc còn treo" không nhắc plan research-council | [MỚI] | Ghi đè khi đóng phiên 24/09 |
| `docs/stories/` | Chỉ có tệp cho US-001…015 (thiếu 005, 010). US-016…027 không có tệp story. ADR và plan thay vai này | [MỚI] | Chọn một: DB là nguồn chân lý và `stories/` chỉ còn giá trị lịch sử (ghi rõ trong `docs/HARNESS.md`), hoặc sinh tệp từ DB |
| `decisions/0003`, `0005` | Vẫn ghi `accepted`, trong khi ADR 0010 ghi "thay thế một phần 0005, 0003 chỉ còn giá trị lịch sử" | [MỚI] | Thêm dòng `Superseded-by: 0010` vào đầu 0003, 0005 và 0008 (§2.2) |

### 2.2 `project/docs/**` (plan hầu như chưa đụng tới) [MỚI]

- **Lệnh và lane cũ** (đếm số lần khớp mẫu lane cũ): `design/13-per-user-output-workflow.md` 38 lần (có `scripts/agent_run.py` không tồn tại, `:384,416,425`). `operations/daily-runbook-per-user.md` 17 lần (`:182,254`). `pipeline-runbook.html` 13 lần. `backlog-drain-runbook.md` 13 lần. `design/15-antigravity-multi-agent-orchestration.md` 12 lần. `pipeline-backlog.html` 10 lần. `end-to-end-operations-playbook.md` 8 lần. `entities.md` 8 lần. `agent-prompting-guide.md` 7 lần (`:87,177` `agent_run.py`). `framework-end-to-end.html` 7 lần. `00-end-to-end-architecture.md` 6 lần. `17-medallion-pipeline-workflows.md` 5 lần.
- **Link chết:** `project/README.md:18` → `docs/system-prompt.md` (thật ra ở `docs/others/`). `project/docs/README.md:11,56` → `decisions.md` và `:59` → `phase1-report.md` (cả hai đã chuyển vào `others/`). `design/01-system-overview.md:94` → `../decisions.md`. `dev/05-known-issues.md:48,56` → `docs/decisions.md` và `config/domains.yaml`. `runbook.md:127` và `others/phase1-report.md:40` → `scripts/enrich_deferred.py` (không tồn tại). `design/16-periodic-report-scraper.md:140-141,212` → `config/domains/nso.yaml` và `src/scrapers/nso.py` (không tồn tại; plan market-sources phase 05 để "gated/deferred").
- **Môi trường sai:** `project/README.md:24-25` hướng dẫn `python -m venv .venv`. `runbook.md:9-20` và 9 tệp khác dùng `.venv\Scripts\python.exe`. AGENTS.md §3 cấm `.venv` nội bộ.
- **Mục lục lỗi thời:** `project/docs/README.md:3` "Cập nhật 2026-07-26 (Phase 1 + 2, 23 domain, 112 test)". Không có mục nào về Article Lane.
- **Đề xuất:** thêm task T5.2b vào plan:
  - (a) Chuyển `design/13,15`, `operations/{daily-runbook-per-user, backlog-drain-runbook, agent-prompting-guide, agent-runner-prompt, end-to-end-operations-playbook, pipeline-runbook.html, pipeline-backlog.html}` và `design/framework-end-to-end.html` vào `project/docs/archive/lane-l1-gold/`.
  - (b) Sửa các link chết nêu trên.
  - (c) Viết lại Quick Start của `project/README.md` theo venv `C:\venvs\news-scape`.
  - (d) Viết lại `project/docs/README.md` thành mục lục có một dòng "Vận hành agent → `.agents/dsh/RUNBOOK-article-lane.md`".

### 2.3 `okf/**`

- `okf/index.md:22` "Đường hai lớp cũ **giữ để quay lui**". `:34` "agent handoff (quay lui)". `:26` sản phẩm là `.csv` (thật ra là `.xlsx`). ADR 0010 §4 nói không có đường quay lui tạm nào. **[MỚI]**
- `okf/catalog/pipelines/article_lane.md:43` "Agent Handoff hai lớp vẫn gọi được nhưng chỉ để quay lui". `:61,109` "chắt lọc", "Nội dung mỗi bài sau chắt lọc ~1.542 token". **[MỚI]**
- `okf/catalog/playbooks/daily_agent_run.md` (9 lần khớp), `pipelines/agent_handoff.md`, `pipelines/user_output.md`, `tables/l1_tasks.md`, `tables/l1_outputs.md`, `references/agent_contracts.md`, `tables/agent_outputs.md`, `datasets/user_deliverables.md` còn `materiality`/`l1_route`/`subscriber`. **[PLAN T5.2]** chỉ nêu playbook và `l1_tasks.md`. Cần mở rộng phạm vi sang 6 tệp còn lại.
- `okf/catalog/{pipelines,tables}/periodic_reports.md:31,70-71` dẫn tới `nso.yaml`/`nso.py` không tồn tại. **[MỚI]**
- 17 tệp okf dùng `data/monocle.db` tương đối. **[MỚI]** Thêm một dòng chuẩn "DB vận hành: `C:\data\news-scape\monocle.db`" vào `web_monocle_db.md` rồi trỏ về đó.

### 2.4 Trùng lặp nội dung (cùng một loại tri thức ở nhiều nơi)

| Loại tri thức | Số nơi đang viết | Các tệp |
|---|---|---|
| Runbook vận hành hằng ngày | **9** | `.agents/AGENT_RUNBOOK.md`, `.agents/dsh/RUNBOOK.md`, `.agents/dsh/RUNBOOK-article-lane.md`, skill `news-scape-agent-operations`, `project/docs/runbook.md`, `project/docs/operations/{daily-runbook-per-user, end-to-end-operations-playbook, backlog-drain-runbook}.md`, `okf/catalog/playbooks/{runbook, daily_agent_run}.md` |
| Kiến trúc end-to-end | **8** | `docs/ARCHITECTURE.md`, `project/docs/architecture.md`, `design/00`, `design/01`, `design/17`, `framework-end-to-end.html`, `okf/catalog/references/architecture.md`, `.agents/dsh/WORKFLOW-article-lane.md` |
| Hợp đồng đầu ra agent | **5** | `project/schemas/*.json`, `design/09-agent-io-contract.md`, `okf/catalog/references/agent_contracts.md`, skill `dod-gatekeeper`, rule 05 |
| Quyết định | **3 nơi, 2 dãy số** | `docs/decisions/0001-0010` (ADR), `project/docs/others/decisions.md` (TDR-001..006), bảng `decision` trong harness.db (4 dòng) |
| Danh sách user bật | **2 manifest** | `users/subscriptions/manifest.yaml` (chỉ `AnPT`; `compile.py` đọc tệp này, user vắng mặt được mặc định bật) và `project/config/entities/manifest.yaml` (5 user, `default: false`; radar đọc tệp này) [PLAN T4.3] |
| Bề mặt DSH | **3** | `dsh/README.md`, `DSH-VIEC-THU-CONG.md`, `docs/proposals/dsh-surface-verified-2026-09-18.md` |

---

## 3. Mã hoá: `SESSION-LATEST.md` không hỏng

- Quét toàn bộ `.md/.yaml/.yml/.html` được git theo dõi, cộng `docs/`, `plans/`, `.agents/`: **0 tệp UTF-8 không hợp lệ**. Mẫu mojibake (`â€`, `Ã¡`, `á»`) chỉ khớp ở `project/docs/operations/troubleshooting.md:28`, và đó là **ví dụ cố ý** trong mục triệu chứng.
- `docs/SESSION-LATEST.md`: `file` báo "UTF-8 text". 3 byte đầu là `23 20 53` (`# S`), **không có BOM**. Đếm chuỗi byte `â€` = 0.
- **Nguyên nhân hiển thị `â€”`:** Windows PowerShell 5.1 `Get-Content` đọc tệp không BOM theo code page ANSI (cp1252). Dấu `—` (UTF-8 `E2 80 94`) vì thế hiện thành `â€”`. Công cụ Read và `cat` của Git Bash hiển thị đúng.
- Chỉ có 2 tệp mang BOM: `docs/stories/US-002-optimize-user-output-format.md` và `project/tests/fixtures/tbtc_detail_page.html` (fixture, giữ nguyên).
- **Đề xuất:**
  - (a) Thêm vào rule 03 hoặc rule 08 một dòng: "Đọc tệp bằng PowerShell phải dùng `Get-Content -Encoding UTF8`. Không kết luận tệp hỏng từ output console."
  - (b) Không thêm BOM vào tệp. Bỏ BOM khỏi US-002 cho thống nhất.
  - (c) Tuỳ chọn: thêm kiểm "UTF-8 hợp lệ + không BOM" vào `audit --codebase`.

---

## 4. `docs/proposals/` và `plans/`

### 4.1 Trạng thái từng mục

| Mục | Trạng thái thật | Đề xuất |
|---|---|---|
| `plans/20260724-0859-scraping-expansion-phase1` | Header ghi "Not started 0%", nhưng các nguồn phase 1 đã chạy (23 domain) | Cập nhật header thành done/superseded, rồi lưu trữ |
| `plans/20260725-1339-source-expansion-phase2` | Ghi "implementation not started" | Kiểm lại, rồi đánh dấu |
| `plans/20260813-0736-raw-html-capture…` | "PLANNED — APPROVED 0/6", nhưng Bronze raw_html đã chạy (US-011, `design/06`) | Đánh dấu implemented |
| `plans/20260814-0301-raw-to-agent-standardization…` | "PLANNED — APPROVED", nhưng Silver/work-package đã chạy | Đánh dấu implemented |
| `plans/20260817-1040-vneconomy…`, `1536-harness-h1`, `0645-per-user-output` | Implemented | Lưu trữ |
| `plans/20260817-1553-okf-deep-integration` | "Planned", nhưng okf/ đã có khoảng 60 tệp | Đánh dấu implemented |
| `plans/20260907-0834-market-sources-expansion` | Không có dòng trạng thái. Phase 05 NSO bị gated và các link tới `nso.*` chết | Thêm trạng thái |
| `plans/20260917-1420-pipeline-integrity-remediation` | "Đã chốt", đã thực thi bằng US-016…019 | Đánh dấu done, rồi lưu trữ |
| `plans/20260917-1538-dsh-harness-integration` | "**DRAFT — chưa implement**". Thực tế H1 đã chạy, còn H2/H3 (agent_l1/agent_gold) **đã bị ADR 0010 bãi bỏ** | Đánh dấu SUPERSEDED bởi `20260918-1651` + ADR 0010 |
| `plans/20260918-1133`, `1445`, `1624` | Đã ghi SUPERSEDED (tốt) | Lưu trữ |
| `plans/20260918-1651-article-lane-unified` | Là thiết kế chuẩn mà AGENTS.md trỏ tới. **Không có dòng trạng thái.** `:125,299,323,351,560,585,664` còn mô tả "distillation là đòn bẩy chính" và van xả "siết distillation". Cả hai trái với nguyên tắc "đọc trọn nội dung" | Thêm header "implemented + amendment 21/09 (tắt chắt lọc) + ADR 0010". Gạch các đoạn distillation hoặc thêm chú thích trỏ về memory/RUNBOOK |
| `plans/20260924-research-council-execution` | "Chờ duyệt" | Xem §4.2 |
| `proposals/dsh-harness-mapping-2026-09-17.md` | "DRAFT — chờ Human duyệt". Đã được ADR 0009 thay. Dẫn tới `scripts/build_dsh_harness.py` và `.agents/dsh/gen/*` không tồn tại (`:71,213-217`) | Đánh dấu superseded bởi ADR 0009 |
| `proposals/dsh-surface-verified-2026-09-18.md` | Tham chiếu kỹ thuật còn sống (tự ghi "không hết hạn") | Chuyển sang `.agents/dsh/` hoặc `okf/catalog/references/`, vì đây không phải đề xuất |
| `proposals/agy-automation-council-2026-09-23.md` | Đề xuất Cấp 3 **đang treo**. `:5,133,147` gọi ADR của nó là "**ADR 0010**" và "Intake #25". **Cả hai số đã bị dùng**: ADR 0010 là ngừng lane L1/Gold, intake #25 là US-025 | **Sửa ngay:** đổi thành "ADR 0011 (dự kiến)" để tránh nhầm với ADR 0010 thật. Đánh dấu treo hoặc từ chối sau khi người dùng quyết |
| `proposals/jev-integration-council-2026-09-24.md` + thư mục con | Đề xuất Cấp 3, treo. Dẫn tới `jev_shadow_eval.py`, `jev_triage.py` chưa tồn tại (bình thường với đề xuất) | Giữ, gắn trạng thái |
| `proposals/jev-entity-linking-brainstorm-2026-09-24.md` | Brainstorm, "chưa phải đề xuất" | Giữ |
| `proposals/research-council-2026-09-24.md` | Nguồn của plan thực thi 24/09 | Khi plan được duyệt, ghi "→ plan 20260924" |

### 4.2 Đối chiếu với `plans/20260924-research-council-execution/plan.md`, tránh làm hai lần

- **Đã có trong plan và khớp phát hiện của đợt này:**
  - T5.2 (rule 05/08, OPEN-ITEMS, `AGENT_NETWORK_DESIGN`, playbook okf, `l1_tasks.md`, skill `gold-financial-analyst`/`news-scape-agent-operations`)
  - T5.6 (sinh TEST_MATRIX/BACKLOG)
  - T5.1 (`harness_cli.py:294` `or 1`, `CURRENT_SCHEMA_VERSION=2` trong khi DB đã ở v3, bỏ `tool-registry`). Đã kiểm lại: `harness_cli.py:20` = 2, DB `schema_version` = 3, `:294` đúng như mô tả.
  - T3.14 (registry/skill draft), T1.5 (materiality ở schema/rule 02/skill), T4.3 (hai manifest), T1.2 (script chết).
- **Plan bỏ sót (đề xuất thêm vào T5.2 hoặc tạo T5.7):**
  1. `.agents/AGENT_RUNBOOK.md` (§1.1)
  2. `.agents/dsh/README.md`, `RUNBOOK.md`, `DSH-WAVE-W365-HANDOFF.md`, và mâu thuẫn junction (§1.6)
  3. Skill `token-auditor`, `multi-agent-orchestrator-governance`, `dsh-preflight-validator` (§1.4), và `registry.master-orchestrator.skill`
  4. Rule 01, 02 (dòng mở đầu), 07, `entity-system-invariants` (§1.5)
  5. Sai I/O trong registry (§1.3)
  6. `project/docs/**` và `project/README.md` (§2.2)
  7. `okf/index.md`, `article_lane.md`, 6 tệp okf còn lại (§2.3)
  8. `docs/ARCHITECTURE.md`, `GLOSSARY.md`, `HARNESS_MATURITY.md`, `HARNESS_AUDIT.md`, `SESSION-LATEST.md` (§2.1)
  9. Dấu superseded cho ADR 0003/0005 (§2.1)
  10. Dọn `harness.db` (§5)
  11. Nhầm số "ADR 0010" trong đề xuất agy (§4.1)
  12. Header trạng thái của 8 plan (§4.1)
- **Rủi ro trùng việc:** T5.2 và T1.5 cùng sửa `gold-financial-analyst` và rule 02. Nên giao cho **một** agent ở làn E.

### 4.3 Đề xuất quy tắc lưu trữ (đưa vào `docs/HARNESS.md` hoặc rule 07)

1. Mọi `plan.md` và mọi proposal bắt buộc có dòng đầu `Trạng thái: draft | approved | in_progress | implemented | superseded-by <x> | rejected`. `harness_cli audit` báo tệp thiếu dòng này.
2. Plan ở trạng thái `implemented` hoặc `superseded` quá 14 ngày thì chuyển vào `plans/_archive/YYYY/` bằng `git mv`, để link còn theo được lịch sử.
3. Proposal được duyệt thì phải sinh ADR, và tệp proposal ghi `→ ADR NNNN`. Proposal bị từ chối thì chuyển vào `docs/proposals/_archive/`. Thư mục con của hội đồng (position/rebuttal/research) đi theo tệp tổng hợp.
4. **Số ADR chỉ được cấp khi lập ADR**, không được đặt trước trong proposal. Proposal dùng "ADR (dự kiến)".
5. Tài liệu tham chiếu kỹ thuật (ví dụ `dsh-surface-verified`) không để trong `proposals/`.

---

## 5. `harness.db` (đọc `mode=ro`) và `scripts/`

### 5.1 Story

- **WIP=1: đạt.** Không có story `in_progress`.
- **Story treo gắn với lane đã chết:**
  - US-021 `planned`: "H2 L1 cognitive pilot, agent_l1 subagent".
  - US-020, US-022, US-023 `deferred`: gồm "Gold + hard gate ADR 0008", "triage/dedup/brief… flash".
  - US-001 `blocked` từ 24/08: `product_contract` = `docs/contracts/gold-agent-output-v1.json`, tệp **không tồn tại**. Hợp đồng đầu ra hiện nằm ở `project/schemas/agent-output-v2-lean.schema.json`.
  - **Đề xuất:** chuyển US-021/022 sang `retired` (lý do: ADR 0010). US-001 sang `retired` (bị v2-lean thay). US-020 sang `retired` hoặc `implemented` (preset đã mount và chạy W365). US-023 để `deferred` nhưng sửa phạm vi (bỏ triage). Mỗi lệnh đổi kèm `harness_cli trace`.
- **Story thiếu trace:** US-018 (implemented, 0 trace) sẽ bị trừ điểm ở check #3. US-021/022/023 không có trace.
- **Story không có dòng DB:** US-003 (có tệp, TEST_MATRIX ghi implemented).

### 5.2 Trace và intake

- 58/82 trace không có `story_id`. Phần lớn là Cấp 1 hợp lệ.
- **Vi phạm quy trình:** trace #80 (24/09, "Ngừng materiality/event_type") sửa `AGENTS.md`, `registry.yaml`, `pipeline.yaml`, `user_output.py`. Đây là Harness Core và Data Contract đầu ra, tức Cấp 3 theo AGENTS.md §0. Nhưng trace này **không có intake, story hay ADR**. Plan research-council ghi đây là "T-00, quyết định đã chốt của người dùng", nhưng quyết định đó chưa được ghi thành ADR.
  - **Đề xuất:** lập ADR 0011 "Ngừng materiality/event_type/impact_area ở mọi tầng", kèm story US-028 hồi tố (plan đã dùng tên US-028 cho nợ registry, cần đổi số một trong hai). Registry `:20-22` nên trỏ tới ADR đó.
- Trace #77–82 (24/09) không có intake. Intake cuối là #27 (23/09).

### 5.3 Bảng `decision`

Chỉ có 4 dòng: 0001, 0002, 0006, 0010. Thiếu 0003, 0004, 0005, 0007, 0008, 0009. Trong đó ADR 0009 (D6: mọi model = flash) chính là quyết định mà AGENTS.md viện dẫn. **Đề xuất:** `harness_cli decision add` cho 6 ADR còn thiếu, ghi đúng trạng thái (0003 và 0005 `superseded`, 0008 `amended`).

### 5.4 Bảng `backlog`

- 28 mục, 19 mở. Check #4 phạt vì quá 5 mục mở. Trace #81 ghi health 0.15.
- **Đã lỗi thời do ADR 0010, đề xuất đóng kèm `outcome` "superseded by ADR 0010":**
  - #3 (prompt L1/Gold trong skill operations)
  - #4 (dọn `batch_X`)
  - #10 (L1 agent `unlisted_candidates`)
  - #11 (radar Gold eligible)
  - #12 (`agent_export` theo wave)
  - #13 (GICS `QUY` của L1 agent)
  - #14 (lệnh Gold phụ thuộc CWD)
  - #16 (`maxDepth 0` của agent_l1/gold; đã sửa thành 1)
  - #21 (radar khuyên `requeue`; US-025 đã sửa)
  - #22 (lane hợp nhất dùng `l1_outputs.dod_pass` code-first; ADR 0010 §2.4 đã xử lý)
- **Đã được xử lý, cần kiểm rồi đóng:** #15 (rule 05 §4.4 `agy --dangerously-skip-permissions`; grep `agy` trong rule 05 hiện cho 0 kết quả). #20 (preset không mount; đã mount qua patch). #18 (reasoningEffort; preset đã đặt `"off"`).
- **Còn giá trị:** #5, #7 (T5.5), #9, #17, #19, #23 (T0.3), #24 (T2.2), #28.

### 5.5 `agent_metrics` và `token_ledger`

- `agent_metrics` có 9 dòng, **tất cả cho agent đã retired** (`l1-entity-matcher`, `gold-financial-analyst`, 15–17/09). **0 dòng cho `article-processor`**. Registry `:215` khai 5 KPI cho agent này (`turns_per_batch`, `parse_fail_rate`, …) nhưng không có luồng nào ghi. Plan research-council §5.4 đã nhắc việc này, **nhưng chưa có task riêng**. **Đề xuất:** để `article_run.py --finish` ghi 1 dòng `agent_metrics` mỗi đợt (items, dod_pass của hai lớp, tokens lấy từ ledger). Ghi rõ task này trong plan (ví dụ gắn vào T3.8a).
- `token_ledger` có 8 dòng (W1, W2 ×4, W365 ×3). Các lần `append` lặp lại cho cùng một đợt tạo nhiều dòng cộng dồn (W2 có 4 dòng từ 2,05M đến 2,24M; W365 có 3 dòng). Báo cáo nào cộng thẳng các dòng sẽ đếm trùng. **Đề xuất:** khoá duy nhất `(wave, agent_id)` với upsert, hoặc để `report` chỉ lấy dòng mới nhất mỗi đợt.
- **Bảng `token_ledger` do `project/scripts/token_ledger.py:46` tự tạo**, nằm ngoài `scripts/schema/00x-*.sql`. Vì thế `schema_version` (3) không phản ánh bảng này, và `harness_cli init` trên DB mới sẽ thiếu nó. **[MỚI]** Thêm `004-token-ledger.sql` và nâng lên v4. Đây là thay đổi schema DB harness nên thuộc Cấp 3, gộp vào T5.1.

### 5.6 `scripts/harness_cli.py` và `scripts/` gốc

- Các subcommand thật: `init`, `query {contract, matrix, agent-metrics}`, `intake`, `story {add, update, complete}`, `decision add`, `backlog {add, close}`, `trace`, `metric`, `audit [--codebase]`, `propose`. AGENTS.md §5 chỉ liệt kê 5 lệnh, và cả 5 đều tồn tại.
- **Rủi ro cwd [MỚI]:** `DEFAULT_DB_PATH = "harness.db"` là đường dẫn tương đối (`harness_cli.py:21`). AGENTS.md §3 quy định "mọi lệnh `scripts/...` chạy với cwd = `project/`", còn §5 gọi `python scripts/harness_cli.py` từ gốc repo. Nếu một agent áp quy tắc §3 cho `harness_cli`, lệnh sẽ không tìm thấy tệp. Nếu dùng `init`, lệnh sẽ **tạo `project/harness.db` rỗng** mà không báo lỗi (hiện chưa xảy ra: chỉ có một `harness.db` ở gốc repo). `token_ledger.py:33-36` thì đã neo tuyệt đối. **Đề xuất:** neo `DEFAULT_DB_PATH` theo `Path(__file__).parents[1] / "harness.db"`, và ghi rõ ở AGENTS.md §5 "cwd = gốc repo".
- `scripts/bootstrap-harness.ps1` gọi `python` trần, không qua `C:\venvs\news-scape`. **[MỚI]** Đổi sang đường dẫn venv.

### 5.7 Script lane cũ còn trong mã

`project/scripts/{l1_route, agent_export, process_l1_pipeline, run_agent_hierarchy, l1_backlog}.py` và `maintenance/{requeue, route_today_l1}.py` vẫn tồn tại, trái với ADR 0010 §4 ("không có đường quay lui tạm nào nằm sẵn trong mã"). **[PLAN T1.2]**

---

## 6. Đề xuất cấu trúc tài liệu tinh gọn: một nguồn chân lý cho mỗi loại tri thức

| Loại tri thức | Nguồn chân lý duy nhất | Các nơi khác chỉ được |
|---|---|---|
| Luật cổng và phân tầng | `AGENTS.md` (shim) + `.agents/rules/*` | trỏ tới |
| Ai tồn tại, I/O, DoD, KPI | `.agents/registry.yaml` | Skill chỉ chứa kiến thức nghiệp vụ, không chép I/O |
| DAG và lệnh mỗi stage | `.agents/pipeline.yaml` | Runbook dẫn theo stage id |
| Chạy thế nào hôm nay | `.agents/dsh/RUNBOOK-article-lane.md` (+ `DSH-VIEC-THU-CONG.md` cho phần tay) | Xoá hoặc lưu trữ 8 runbook còn lại (§2.4) |
| Vì sao (kiến trúc Article Lane) | `.agents/dsh/WORKFLOW-article-lane.md` | `project/docs/design/00` giữ phần Bronze/Silver và trỏ sang tệp này cho tầng agent |
| Kiến trúc sản phẩm Bronze/Silver | `project/docs/design/*` + `project/docs/architecture.md` | `docs/ARCHITECTURE.md` giữ vai con trỏ (đã đúng vai, chỉ cần sửa link) |
| Tri thức dữ liệu bền (bảng, config, metric) | `okf/catalog/**` | Không chép schema vào `project/docs/dev/02` (thay bằng link) |
| Quyết định | `docs/decisions/NNNN-*.md` + bảng `decision` (đồng bộ) | `project/docs/others/decisions.md` (TDR) đổi tên thành `TDR-legacy.md` và trỏ về ADR |
| Hợp đồng dữ liệu agent | `project/schemas/*.schema.json` | `design/09`, `okf/references/agent_contracts.md`, `dod-gatekeeper` chỉ link và mô tả ý nghĩa |
| Trạng thái story, backlog, proof | `harness.db` | `TEST_MATRIX.md`, `HARNESS_BACKLOG.md` là **view sinh tự động** (T5.6), có dòng "đừng sửa tay" |
| Việc tồn đọng giao hàng | Bảng `backlog` trong `harness.db` (component=`delivery`) | `OPEN-ITEMS.md` rút xuống còn các mục CHẶN đang sống, hoặc sinh từ DB |
| Trạng thái phiên | `docs/SESSION-LATEST.md` (ghi đè) | — |
| Bề mặt DSH đã xác minh | `.agents/dsh/DSH-SURFACE.md` (chuyển từ proposals) | `dsh/README.md` chỉ giữ phần wiring |
| Danh sách user | Một manifest (T4.3) | Mọi tài liệu gọi `pipeline_radar.py users` |

**Thư mục lưu trữ:** `docs/archive/`, `project/docs/archive/lane-l1-gold/`, `plans/_archive/`, `docs/proposals/_archive/`, `.agents/dsh/archive/`, `.agents/skills/_retired/` (dành cho `gold-financial-analyst`, `materiality-triage`, `news-scape-agent-operations`, `multi-agent-orchestrator-governance`; phần kiến thức còn dùng thì tách ra trước).

**Kiểm tự động đề xuất cho `audit --codebase`** (chỉ báo cáo, không chặn):
- (1) Grep lệnh cấm trong `**/*.md` ngoài `archive/` và ADR.
- (2) Link chết trong tệp markdown.
- (3) Tệp plan/proposal thiếu dòng Trạng thái.
- (4) ADR có trong `docs/decisions` nhưng thiếu trong bảng `decision`.
- (5) Agent `active` mà không có dòng `agent_metrics` trong 7 ngày.
- (6) UTF-8 hợp lệ, không BOM.

---

## 7. Danh sách hành động theo ưu tiên

| # | Việc | Nhãn | Cấp |
|---|---|---|---|
| 1 | Viết lại hoặc lưu trữ `.agents/AGENT_RUNBOOK.md`. Trỏ `master-orchestrator.skill` sang `dsh-conductor` | MỚI | 2 |
| 2 | `dsh-preflight-validator`: bỏ D2 `requeue`, sửa 12 → 14, bỏ kiểm junction | MỚI | 1 |
| 3 | Sửa "ADR 0010" và "Intake #25" trong `agy-automation-council-2026-09-23.md` thành "ADR (dự kiến)" | MỚI | 1 |
| 4 | Lập ADR 0011 hồi tố cho việc ngừng materiality/event_type/impact_area, kèm story | MỚI | 3 (hồ sơ) |
| 5 | Sửa I/O registry: manifest, đường dẫn DB, `--date`, "chắt lọc", `invoke_subagent` | MỚI | 3 (registry là Harness Core) |
| 6 | Viết lại `token-auditor` và `multi-agent-orchestrator-governance`. Sửa dòng mở đầu rule 01, 02, 07 | MỚI | 2 |
| 7 | Dọn `harness.db`: retire US-001/020/021/022, đóng 10 backlog lỗi thời, `decision add` 6 ADR, thêm trace cho US-018 | MỚI | 2 |
| 8 | `okf/index.md` và `article_lane.md`: bỏ "quay lui", bỏ "chắt lọc", `.csv` → `.xlsx` | MỚI | 1 |
| 9 | `project/docs`: lưu trữ 10 tệp lane cũ, sửa 9 link chết, sửa Quick Start dùng `.venv` | MỚI | 2 |
| 10 | Header trạng thái cho 8 plan. Đánh dấu superseded cho ADR 0003/0005 | MỚI | 1 |
| 11 | `harness_cli`: neo đường dẫn DB tuyệt đối. Schema `004-token-ledger.sql`. Gộp vào T5.1 | MỚI + T5.1 | 3 |
| 12 | Ghi 1 dòng `agent_metrics` mỗi đợt từ `--finish`. Chống đếm trùng `token_ledger` | MỚI | 2 |
| 13 | T5.2, T5.6, T1.5, T3.14, T4.3 theo plan (mở rộng phạm vi như §4.2) | PLAN | 2 |
| 14 | Ghi quy tắc lưu trữ (§4.3) và luật "PowerShell đọc UTF-8" (§3) | MỚI | 2 |
