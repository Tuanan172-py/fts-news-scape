# Research C — Nền tảng news-scape hiện tại và các điểm tích hợp Jev

|  |  |
| --- | --- |
| Vai | Researcher C (kiểm toán, chỉ đọc mã) |
| Ngày | 2026-09-24 |
| Nhãn | **[S]** có nguồn (URL hoặc tệp:dòng) · **[V]** kiểm chứng tại máy (đọc tệp/gói đã cài) · **[I]** suy luận |
| Phạm vi | Bản đồ điểm quyết định có kiểu, ràng buộc runtime DSH/agy, governance, số liệu chi phí/khối lượng |

---

## 0. Sự thật Jev tối thiểu cần để đối chiếu nền tảng

Researcher A phụ trách Jev. Mục này chỉ giữ những gì ảnh hưởng trực tiếp tới cách cắm vào nền tảng.

| # | Sự thật | Nhãn |
| --- | --- | --- |
| J1 | Một endpoint `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <key>`, thân gồm `model` (`jev-latest`), `state` (string/object/array), `questions` (map câu hỏi có tên). Trả `answers` + `usage` | [S] https://docs.typesafe.ai/api.md |
| J2 | Ba loại câu hỏi: **Choice** (≤ 255 lựa chọn, trả phân phối xác suất + confidence), **Score** (2–10 mức mô tả bằng lời), **Noul** (có/không, trả xác suất). Không sinh chuỗi | [S] https://docs.typesafe.ai/api.md · https://docs.typesafe.ai/concepts/system-one |
| J3 | Ngữ cảnh 64k token/request; **32k cho `state` + câu hỏi dài nhất** | [S] https://docs.typesafe.ai/models.md |
| J4 | Giá **$0,042 / 1M token vào, đầu ra miễn phí** | [S] https://docs.typesafe.ai/models.md · https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/ |
| J5 | Rate limit 250.000 token/s, 1.200 request/phút, "điều chỉnh động" trong giai đoạn early access | [S] https://docs.typesafe.ai/models.md |
| J6 | Ngôn ngữ: tiếng Anh là chính; ngôn ngữ khác "xử lý được nhưng không tốt bằng". **Tiếng Việt chưa được nêu tên** | [S] https://docs.typesafe.ai/models.md |
| J7 | Không có batch endpoint, không nêu chính sách lưu dữ liệu; lỗi 401/422/429/529 | [S] https://docs.typesafe.ai/api.md |
| J8 | Có SDK Python và JavaScript; alias `jev-latest`/`jev-preview` đều trỏ `jev-1.13.0` → phải ghim phiên bản | [S] https://docs.typesafe.ai/models.md |
| J9 | Giao thức **không** phải OpenAI-compatible chat/completions | [I] từ J1–J2 |

---

## 1. Bản đồ điểm quyết định có kiểu (typed/classificatory decisions)

Khối lượng tham chiếu: đợt W365 ngày 21/09 = **365 bài/ngày** [S `.agents/dsh/DSH-WAVE-W365-HANDOFF.md`]; 23/09 có **345 bài chờ** [S `docs/SESSION-LATEST.md`]; backlog **2.915 bài** ngày 10–17/09 (≈ 365 bài/ngày) [S ADR 0010 §1]. Dưới đây lấy **~350 bài/ngày** làm khối lượng phân tích [I].

Chi phí hiện tại: worker ~**2.850 token quota/bài**, cache hit ~9% [S `skills/dsh-conductor/SKILL.md`, RUNBOOK §2]. Quy ra tiền theo `token_pricing.yaml` (off-peak: miss $0,15, hit $0,003, out $0,60 / 1M): giả định ~1.900 in / ~900 out mỗi bài (trăm bài ~90k output, RUNBOOK §1.1) → **≈ $0,0008/bài, ≈ $0,28/ngày off-peak, ≈ $0,56/ngày peak** cho **toàn bộ** tác vụ hợp nhất (nhận diện + tóm tắt + hàm ý + sentiment + trích dẫn) [I, tính từ số [S]]. Số thật nằm ở `token_ledger` (harness.db), không truy vấn trong phiên này.

| # | Điểm quyết định | Hiện ai làm | Khối lượng/ngày | Chi phí hiện tại | Vị trí mã | Dạng Jev phù hợp | Nhãn |
|---|---|---|---|---|---|---|---|
| D1 | **Xếp tầng ưu tiên** (tier 1 watchlist/ngành/vĩ mô khẩn vs tier 2 background) | Script: `reg.detect(title)` giao watchlist, so GICS, regex `_MACRO_URGENT_RE` | ~350 (mọi bài chờ) | 0 token | `project/scripts/article_pack.py:85-90, 104-159, 439` | Noul "liên quan tới danh mục theo dõi?" hoặc Choice ngành | [V] |
| D2 | **Bộ chọn bài** (bài nào chưa phân tích) | Script SQL, loại `code_first` | mọi bài | 0 | `article_pack.py:162-205` (`ANALYZED_L1`) | Không — tất định, có đáp án đúng duy nhất | [V] |
| D3 | **Materiality** (mức trọng yếu) | **KHÔNG làm.** Lược đồ lean không có trường `m`; `_sort_key` chỉ đọc `materiality.score` lồng → luôn 0 | 0 | 0 | `project/src/export/user_output.py:287-297`; dossier agy §D | **Score** 3–5 mức — ứng viên số 1 | [V] |
| D4 | **Sentiment** (`sn`) | LLM `deepseek-flash` trong `article-processor`; script ánh xạ qua `SENTIMENT_MAP` | ~350 | nằm trong gói ~$0,0008/bài | `project/scripts/article_expand.py:301` | Choice {tích cực, trung tính, tiêu cực} + xác suất | [V] |
| D5 | **Time sensitivity** (`ts`) | LLM, ánh xạ `TIME_MAP` | ~350 | như trên | `article_expand.py:302` | Choice/Score | [V] |
| D6 | **Nhóm thực thể** (`e[1]` ∈ 11 mã TIC/COM/PER/…) | LLM trích + gán nhóm; script tra định danh | ~350 × N thực thể | như trên | `article_expand.py:179-243`; dossier agy §3.2 | Choice 11 lớp **cho từng thực thể đã trích** — nhưng Jev **không trích** được chuỗi (J2) | [V]/[I] |
| D7 | **Đối chiếu nhận diện** mô hình vs bộ nhận diện danh mục | Script đối chiếu, gắn nhãn hai nguồn | ~350 | 0 | `article_expand.py` (`build_mentions`, labels) | Noul "thực thể X có thật sự được nhắc tới với nghĩa là doanh nghiệp này?" cho ca bất đồng | [V]/[I] |
| D8 | **Dedup cùng sự kiện đa nguồn** | Script: SimHash Silver + rapidfuzz tiêu đề; `story-dedup-clusterer` **draft** (300 token/cặp) | chưa đo | 0 (script) | `project/src/db/dedup.py`, `src/pipeline/change_detect.py`; registry `story-dedup-clusterer` | Noul theo cặp "hai bài cùng sự kiện?" (tie-breaker) | [V] |
| D9 | **Triage đáng phân tích sâu** | `materiality-triage` **draft**, ý đồ cũ là cổng rẻ trước Gold | 0 | 0 | registry `materiality-triage`, pipeline stage `materiality_triage` (optional) | Score/Noul. **Nhưng** AGENTS.md §6B: "mọi bài đều được xử lý đầy đủ", tầng chỉ quyết **thứ tự** → Jev không được làm cổng loại bài | [V] |
| D10 | **DoD tất định** (schema, trích dẫn nguyên văn, chống chép key_points, độ dài hàm ý, độ phủ ≥ 90%) | Script | ~350 | 0 | `src/agent/dod.py:193`; `l1_ingest.py`, `agent_ingest.py`; `article_run.py:679 verify_wave` | Không — tất định | [V] |
| D11 | **DoD ngữ nghĩa** (hàm ý rỗng, sentiment sai, hallucination) | `adversarial-dod-verifier` **draft**, 500 token/bài mẫu | 0 | 0 | registry; pipeline `gold_qa` (optional) | Noul/Score trên (bài + output) — ví dụ "tóm tắt có mâu thuẫn với bài?" | [V]/[I] |
| D12 | **Phân tuyến tới người dùng** | Script: thực thể đã nhận diện ∩ watchlist từng user | 5 user × bài | 0 | `scripts/write_user_output.py`, `src/export/user_output.py` | Chỉ bổ trợ: Score "mức liên quan với watchlist user U" cho bài không khớp mã | [V]/[I] |
| D13 | **Lọc rác / độ liên quan nguồn** | Script: `domain_validator` (min_length…), không có lọc ngữ nghĩa | toàn bộ bài cào | 0 | `src/monitor/domain_validator.py:225` | Noul "bài là tin tài chính thực chất (không quảng cáo, không mục lục)?" — chỉ để gắn nhãn/sắp xếp, không loại | [V]/[I] |
| D14 | **Kích hoạt backlog / mở đợt** | Radar in một lệnh, **người** quyết | 1–2 quyết định | 0 | `scripts/pipeline_radar.py status` | Không — quyết định vận hành, không phải phân loại nội dung | [V] |
| D15 | **Brief cuối ngày** (chọn tin trọng yếu cho user) | `daily-brief-synthesizer` **draft** | 5 | 0 | registry | Jev xếp hạng (D3) làm đầu vào, sinh văn bản vẫn cần LLM sinh | [I] |

Nhận xét kết cấu [I]:

1. Chỉ có **một** stage cognitive đang chạy (`article_analyze`) và nó gộp cả trích xuất lẫn phân loại trong một lượt. Phần phân loại (D4, D5, một phần D6) là "hành khách" rẻ trong lượt ấy; tách chúng sang Jev **không giảm** đáng kể token DeepSeek vì phần đắt là đọc trọn bài + sinh tóm tắt/hàm ý/trích dẫn.
2. Giá trị gia tăng thật của Jev nằm ở những điểm **đang không làm** hoặc **đang là draft**: D3 materiality (khoảng trống đã xác nhận), D8 dedup tie-breaker, D11 QA ngữ nghĩa, D13 nhãn rác, D1 nâng cấp xếp tầng. Đây là nơi Jev thêm tín hiệu mà không đụng hợp đồng `agent-output-v2-lean`.
3. Chi phí Jev cho D3 trên 350 bài × ~2.000 token state ≈ 0,7M token/ngày ≈ **$0,03/ngày** (J4) — nhỏ hơn cả sai số của hoá đơn DeepSeek. Chi phí không phải biến quyết định; **chất lượng tiếng Việt (J6)** và **governance** mới là biến quyết định.
4. Toàn bộ nội dung bài đã là tiếng Việt, đã được Silver tách đoạn; một bài trung bình dưới 32k token (packet 100 bài ~348 KB, dossier agy §D) nên J3 không phải ràng buộc [I].

---

## 2. Ràng buộc runtime

### 2.1 DSH conductor gọi mô hình thế nào

| Sự thật | Nhãn |
|---|---|
| Phiên điều phối chạy preset `news-scape-conductor`, `mode: ptc`. Một đợt = **một** `run_code` chạy `wave_<mã>.conductor.ts` do `article_run.py:120-236 conductor_program()` sinh | [V] |
| Chương trình gọi `tools.read` (đọc packet theo cửa sổ dòng), `tools.agent_article` (worker), `tools.write` (ghi output). Hâm cache khi ≥ 2 lô | [V] `article_run.py:153-219` |
| Worker `agent_article`: row `dsh-tool-subagent`, `provider: spawn`, `agentOptions: {provider: deepseek-official, model: deepseek-flash, reasoningEffort: "off"}`, `toolFilter.allow: []`, `maxDepth: 1`, `backgroundMode: one-shot` | [V] `agent.cordis.yml:192-545` |
| `maxDepth: 0` **cấm delegation hoàn toàn** (con đầu đã là depth 1) → phải là 1 | [V] `agent.cordis.yml:172-176`; `dsh-surface-verified-2026-09-18.md` |
| Dưới `ptc`, `run_code` được chèn lại **sau** `toolFilter` → con không bao giờ 0 tool thật, chỉ "sdkSchemas rỗng + turns == 1" | [V] `agent.cordis.yml:178-183` |
| Row subagent chỉ có 9 khoá, `agentOptions` 4 khoá (`provider, model, reasoningEffort, maxTokens`); con không đặt được `mode`, kế thừa của cha | [V] `dsh-surface-verified` §6.1 |
| Chỉ `print`/`return` của chương trình vào ngữ cảnh cha; kết quả con ở lại log bền | [V] `agent.cordis.yml:566-585` |

### 2.2 Chương trình conductor có gọi HTTP được không

| Sự thật | Nhãn |
|---|---|
| Backend `dsh-code-runtime-worker-thread`: chạy TypeScript trong **Node worker thread mới**, "authority comparable to the bash tool: it can reach Node APIs", **môi trường rỗng (không có credential ambient)**, "containment, not a security boundary" | [V] `%LOCALAPPDATA%\npm-cache\_npx\1e7f6d9597241db0\node_modules\@deepseek-ai\dsh-code-runtime-worker-thread\README.md:12,55-57` |
| ⇒ Về kỹ thuật `fetch()` của Node khả dụng trong `run_code`, nhưng **API key không có trong env** → muốn gọi Jev phải nhúng key vào mã chương trình → key rơi vào **session log JSONL** (`~/.dsh/sessions/...`). **Không chấp nhận được** | [I] từ [V] |
| Preset có `tool-web` (`fetch: true`) — công cụ đọc web cho mô hình, không phải client POST có header xác thực | [V] `agent.cordis.yml:560-564`; [I] về khả năng POST |
| Preset có `tool-pwsh` → chương trình có thể gọi `tools.pwsh` chạy **script Python** đọc key từ env/Credential Manager. Sandbox `workspace-write` có chặn mạng hay không: **chưa kiểm** | [V] tồn tại; [I] mạng |
| DSH có adapter đa nhà cung cấp `dsh-llm-pi-ai`, **đã mount ngầm trong base composition** (`dsh-base/cordis.patch.yml:107-108`), kích hoạt khi `~/.dsh/settings.yaml` thêm mục `llm-pi-ai:`. Hỗ trợ `openai-completions`, `openai-responses`, `anthropic-messages`, key qua `apiKeyEnv` | [V] README gói + base patch |
| ⇒ Jev **không** cắm được như một `agentOptions.provider` của subagent, vì giao thức `systemone` không thuộc các protocol pi-ai hỗ trợ và Jev không sinh văn bản (J1, J2, J9). Chỉ khả thi nếu LiteLLM pass-through (https://docs.litellm.ai/docs/pass_through/typesafe) có lớp chuyển đổi — chưa kiểm | [I] |

**Kết luận 2.1–2.2 [I]:** Điểm cắm tự nhiên của Jev **không nằm trong DSH**, mà là một **bước Python chạy ở terminal** (cùng lớp với `article_pack`/`--finish`), đọc key từ biến môi trường, gọi SDK Python, ghi kết quả vào tệp/bảng riêng. DSH conductor không cần biết Jev tồn tại. Điều này giữ nguyên bất biến "một đợt = một `run_code`" và không thêm bước nào vào phiên điều phối (chi phí phiên tỉ lệ bình phương số bước — SKILL dsh-conductor).

### 2.3 agy runner (đề xuất 23/09, chưa duyệt)

| Sự thật | Nhãn |
|---|---|
| Kiến trúc chọn: **Python là conductor**, `agy -p` là hàm nhận thức thuần một tiến trình/một lô/một lượt, không tool, hồ sơ worker cô lập, stdin `stream-json`, Python parse + validate | [S] `docs/proposals/agy-automation-council-2026-09-23.md` §0, §3 |
| Kích hoạt bằng Task Scheduler `article_tick.py`, thang tự chủ L0→L1→L2, kill switch, quota guard | [S] như trên §3.4–3.5 |
| Trạng thái: **proposal**, Tier 3, cần ADR + Human duyệt; số ADR "0010" trong đề xuất **đã bị ADR 0010 (ngừng lane L1/Gold) chiếm** → ADR agy phải lấy số mới | [V] `docs/decisions/` |
| ⇒ Với agy, Python đã là conductor, nên Jev cắm vào đúng chỗ đó (một hàm `jev_classify()` trong vòng `article_run --runner agy`) mà không phụ thuộc agy. Jev độc lập với lựa chọn runner DSH/agy | [I] |

### 2.4 Nơi cắm một provider/tool mới

| Vị trí | Vai trò | Nhãn |
|---|---|---|
| `.agents/registry.yaml` | Entry mới; phải chọn `class`. Taxonomy hiện chỉ có `operator` (0 token, tất định) / `cognitive` (subagent qua invoke_subagent) / `conductor`. **Một script gọi Jev không vừa lớp nào**: không 0 token, không tất định, không phải subagent | [V] rule 07 §1; [I] khoảng trống |
| `.agents/pipeline.yaml` | Stage mới, ví dụ `article_classify` (needs `article_expand`, optional) hoặc chèn trước `deliver` | [V] cấu trúc |
| `docs/TOOL_REGISTRY.md` | Chỉ có 7 công cụ lõi + bậc thang suy giảm; chưa có mục nào cho LLM provider (DeepSeek không được liệt kê). Jev nếu vào sẽ là **dòng đầu tiên kiểu "provider"**, fallback = "bỏ trống nhãn, không chặn đợt" (Degrade-Don't-Fail) | [V] `docs/TOOL_REGISTRY.md` |
| `project/config/token_pricing.yaml` | Chỉ có `deepseek-flash`; `token_ledger.py` chỉ đọc phiên DSH. Cần model `jev-1.13.0` + nguồn usage từ `usage.input_tokens` của response | [V] |
| Provenance | `article_expand.py:53-54` hardcode `AGENT_PROVIDER="dsh"`, `MODEL_USED="deepseek-flash"`; xlsx đọc `agent_provider`/`model_used` | [V] dossier agy §D; `user_output.py:281-282` |
| Hợp đồng dữ liệu | Thêm trường materiality/nhãn mới vào `agent_outputs` hoặc bảng mới = **Data Contract change** | [V] AGENTS.md §0 Cấp 3 |

### 2.5 Governance áp dụng

| Luật | Tác động tới Jev | Nhãn |
|---|---|---|
| AGENTS.md §0 **Cấp 3 HIGH-RISK**: đổi DB schema, Data Contract, API token, provider mới → Hard Gate, ADR, Human duyệt, Detailed Trace. Tiền lệ ADR 0009 (DSH) và đề xuất agy | Jev = provider mới + API key mới + (nếu ghi nhãn vào DB) schema/contract → **chắc chắn Tier 3** | [V] |
| ADR 0009 D6 / registry: "**mọi** cognitive agent route về `deepseek-flash`; cấm model cao hơn vì chi phí" | Jev rẻ hơn, nhưng vẫn là **ngoại lệ allow-list model** → ADR phải sửa D6 tường minh | [V] `.agents/dsh/README.md` D6; registry header |
| **No Script Emulation** (AGENTS.md §6C, rule 05 §5, rule 07 §6): cấm regex/heuristic thay vùng trí tuệ | Jev **là mô hình**, không phải heuristic → không vi phạm về bản chất. Nhưng script gọi Jev sẽ trông như "operator sinh nhãn ngữ nghĩa" → ADR phải định nghĩa lớp tác nhân mới (đề xuất [I]: `class: cognitive-typed` hoặc `cognitive` với `invoke: http`) để không làm mờ ranh giới operator | [V]/[I] |
| **Vùng độc quyền LLM**: ngữ nghĩa, trích xuất thực thể, tóm tắt, hàm ý, trích dẫn là việc của `article-processor` (§6C) | Jev **không** được thay tóm tắt/hàm ý/trích dẫn/trích xuất (và cũng không làm được — J2). Thay sentiment/ts/nhóm thực thể = sửa phạm vi độc quyền → cần ADR | [V] |
| **Mọi bài đều được xử lý đầy đủ**; xếp tầng chỉ quyết thứ tự, không quyết độ sâu (§6B) | Cấm dùng Jev làm cổng loại bài (vd. triage "không đáng phân tích"). Chỉ được dùng để sắp thứ tự, gắn nhãn, sắp xếp giao hàng | [V] |
| **Token là ghi nhận, không phải cổng** (ADR 0010 §2.5) | Không đặt trần token/chi phí Jev. Ghi sổ cái thôi. Được phép có cổng **kỹ thuật** (429/529 backoff, lỗi 422) | [V] |
| **Đối chiếu tất định chỉ để kiểm, không để thay**; code-first không tính là phân tích | Nhãn Jev nên được xử lý tương tự: tín hiệu bổ sung, không tính là "đã phân tích", không đưa vào độ phủ ≥ 90% của đợt | [V]/[I] |
| Rule 07 §4: 5 bước (registry, SKILL, stage, story+proof, KPI) — thiếu thì `status: draft` | Áp nguyên | [V] |
| Rule 01 §1 Zero-Tool, Single-Turn | Jev tự nhiên thoả: một request, không tool | [I] |
| WIP = 1 | Không mở story Jev khi còn story khác `in_progress`; nhánh hiện tại (`feature/article-lane-remove-gates`) còn thay đổi chưa commit | [V] git status |
| Zero-Probe (§8) | Phiên điều phối không được dò; bước Jev phải có lệnh 0 token báo trạng thái (vd. `article_run.py --where` in thêm dòng Jev key/model/pin) | [V]/[I] |
| Dữ liệu ra ngoài | Gửi nội dung tin sang một nhà cung cấp Mỹ mới, early access, chưa công bố retention (J7) — cùng loại câu hỏi ToS/dữ liệu mà đề xuất agy đã đặt ra | [S]/[I] |

---

## 3. Số liệu chi phí và khối lượng đã tài liệu hoá

| Chỉ số | Giá trị | Nguồn |
|---|---|---|
| Bài/đợt ngày | 365 (W365, 21/09); 345 chờ (23/09) | [S] HANDOFF W365, SESSION-LATEST |
| Backlog | 2.915 bài 10–17/09 | [S] ADR 0010 |
| Độ phủ W365 | nhận diện 365/365, nội dung 364/365, nạp failed=0 | [S] SESSION-LATEST |
| Token worker | ~2.850 token quota/bài; cache hit ~9%; tiền tố tĩnh ~10k token/lô | [S] SKILL dsh-conductor |
| Output 100 bài | ~90.000 token (trần DSH 256.000/request) | [S] RUNBOOK §1.1 |
| Đơn giá DeepSeek flash | off-peak $0,15 miss / $0,003 hit / $0,60 out per 1M; peak ×2 | [S] `token_pricing.yaml`, https://api-docs.deepseek.com/quick_start/pricing |
| Chi phí ước/ngày Article Lane | ≈ $0,28 off-peak – $0,56 peak cho ~350 bài | [I] |
| Đơn giá Jev | $0,042/1M in, out miễn phí | [S] J4 |
| Chi phí ước Jev, 1 câu hỏi Score trên trọn bài | 350 × ~2k token ≈ 0,7M → ≈ $0,03/ngày; 5 câu hỏi cùng `state` trong một request vẫn ≈ cùng giá nếu tính theo input | [I] |
| Người dùng nhận hàng | 5 (AnPT, PhoHG, ThanhTD, VyPTT, UyenNNT) | [V] `project/config/entities/manifest.yaml` |
| Tests | 517 passed | [S] SESSION-LATEST |

---

## 4. Điểm cắm khuyến nghị (đầu vào cho vòng lập trường) [I]

1. **Nơi chạy:** bước Python ở terminal, sau `--finish` và trước `write_user_output.py` (vd. `scripts/jev_label.py --wave <mã>` hoặc bước `--finish --only ...,label`). Không chạy trong `run_code`; không đụng preset DSH; không phụ thuộc runner DSH/agy.
2. **Ứng viên đầu tiên:** D3 materiality (Score), vì đây là khoảng trống đã xác nhận, `_sort_key` đã có chỗ đọc `materiality.score`, và nó không cạnh tranh với vùng độc quyền của `article-processor`.
3. **Ứng viên thứ hai:** D8 tie-breaker dedup (Noul theo cặp), thay/kích hoạt draft `story-dedup-clusterer` với chi phí gần bằng 0.
4. **Chế độ an toàn:** shadow mode trước — ghi nhãn Jev vào bảng/tệp riêng, so với nhãn DeepSeek (D4/D5) trên vài đợt để đo đồng thuận trên **tiếng Việt** (J6) trước khi bất cứ nhãn nào vào xlsx.
5. **Không làm:** dùng Jev để loại bài, để thay trích xuất thực thể/tóm tắt/trích dẫn, hoặc gọi từ trong chương trình conductor bằng key nhúng.
6. **Governance:** Intake Tier 3 → ADR mới (số kế tiếp sau 0010, và không trùng số với ADR agy) gồm: provider mới + sửa ADR 0009 D6, lớp tác nhân mới trong rule 07 §1, hợp đồng trường materiality, chính sách key (env, không vào repo/log), ToS/dữ liệu ra ngoài, fallback Degrade-Don't-Fail trong `docs/TOOL_REGISTRY.md`.

## 5. Câu hỏi mở cho hội đồng

| # | Câu hỏi | Ai trả lời |
|---|---|---|
| Q1 | Jev phân loại tiếng Việt tài chính tốt đến đâu (J6)? Cần spike trên ~50 bài có nhãn | Researcher A / spike |
| Q2 | Sandbox `workspace-write` của DSH có chặn mạng cho `tools.pwsh` không? Chỉ quan trọng nếu muốn gọi Jev từ phiên DSH | spike 1 lệnh |
| Q3 | Retention/ToS của TypeSafe với nội dung gửi lên; tài khoản cá nhân hay miền FPTS | Human |
| Q4 | Materiality nên gắn vào `agent_outputs` (contract change) hay bảng riêng `article_labels` (schema change, nhưng không động `agent-output-v2-lean`)? | ADR |
| Q5 | `jev-latest` đổi ngầm → ghim `jev-1.13.0` và ghi `model` trả về vào meta, như bài học agy tự cập nhật | ADR |
