# Đề xuất: Tích hợp Jev (TypeSafe AI System One) vào news-scape — kết luận hội đồng 2026-09-24

|  |  |
| --- | --- |
| Loại tài liệu | **Đề xuất (proposal)**, chưa phải quyết định. Cần Intake → ADR → Human duyệt trước khi cấp key hay sửa mã sản xuất |
| Tier | **Cấp 3 HIGH-RISK** (AGENTS.md §0: nhà cung cấp mới + API token mới + sửa ADR 0009 D6; ghi nhãn vào DB là thêm đổi schema). Riêng dọn nợ registry (US-028) là Cấp 2 |
| Phạm vi | Jev chỉ làm **bộ kiểm định có kiểu, chạy sau `--finish`, không chặn, không thay `article-processor`**. Không đụng preset DSH, không đụng `run_code`, không đổi runner DSH/agy |
| Bằng chứng | `docs/proposals/jev-council-2026-09-24/` (research A/B/C, 3 position, 3 rebuttal) |
| Jev | `jev-1.13.0` (early access từ 2026-09-15; `jev-latest` và `jev-preview` cùng trỏ bản này) |
| Nhãn | **[V]** kiểm chứng tại máy (ở tài liệu này chỉ là đọc mã và tệp, **chưa có lệnh Jev nào được chạy**) · **[S]** có nguồn · **[I]** suy luận |

## 0. Tóm tắt một đoạn

Jev là mô hình phân loại một lượt: nhận `state` văn bản và trả xác suất có kiểu (Noul, Choice, Score). Mô hình **không sinh văn bản** [S], nên không thay được `article-processor` và không làm Article Lane rẻ hơn: token DeepSeek tiết kiệm được bằng 0 [I]. Toàn bộ Article Lane chỉ tốn khoảng $0,28–0,56/ngày, nên chi phí không phải biến quyết định. Biến quyết định là **chất lượng trên tiếng Việt** (chưa có số đo công khai nào) và **governance**. Hội đồng chọn **phương án "kiểm định hậu kỳ, shadow, report-only"**: một bước Python ở terminal, đặt sau `article_run.py --finish` và trước `write_user_output.py`, trả lời hai câu hỏi mà cả DoD tất định lẫn lượt DeepSeek hiện không kiểm độc lập được. Câu `cite_k` hỏi đoạn trích có đỡ claim không. Câu `ent_<mã>` hỏi mã được gắn có đúng là chủ thể của bài không. Hội đồng loại phương án "Jev tiền xử lý trước pack", vì mã hiện tại cho thấy tầng ưu tiên không quyết định bài nào vào đợt và thứ tự Jev không tất định sẽ làm trượt cache. Hội đồng cũng loại mọi vai trò cổng lọc. **Chưa đưa gì vào sản xuất trong quý này.** Bước đầu là dọn nợ registry (không cần Jev), sau đó là một spike ngoại tuyến Cấp 3 rút gọn (Spike 0). Spike 0 đo Jev trên cùng golden set với đối chứng cục bộ AnyJev/Laya và kill theo ngưỡng cứng. L1 shadow và L2 chỉ mở khi đạt từng cổng.

## 1. Quy trình hội đồng

| Vòng | Thành phần | Kết quả |
| --- | --- | --- |
| 1 — Nghiên cứu | A: sự thật sản phẩm Jev (docs.typesafe.ai, báo chí) · B: hệ sinh thái, mẫu tích hợp, hiệu chuẩn, injection, rủi ro nhà cung cấp · C: nền tảng news-scape (điểm quyết định, DSH/agy, governance, chi phí) | `research_A_jev_facts.md`, `research_B_ecosystem_risks.md`, `research_C_platform.md` |
| 2 — Lập trường | P1: Jev tiền xử lý (sắp thứ tự trước pack) · P2: Jev kiểm định và định tuyến sau LLM · P3: red team (vận hành, governance, kinh tế): "không tích hợp quý này" | `position_1..3.md` |
| 3 — Phản biện chéo | Cả ba bên đọc lại mã. P1 **tự rút** phương án tiền xử lý. P2 bỏ materiality làm khoá sắp và bỏ `sent` khỏi sản xuất. P3 rút lập luận "spike là Cấp 2" và rút lập luận "Bước 0 lấp khoảng trống sắp thứ tự" | `rebuttal_1..3.md` |
| 4 — Chủ toạ | Tự đọc lại các dòng mã chịu lực (`user_output.py:286-297`, `article_pack.py:196-205, 384, 420, 439`, `registry.yaml:288-338`, `article_expand.py:53-54`, ADR 0009:39) rồi tổng hợp | tài liệu này |

**Giới hạn của hội đồng:** không ai gọi Jev. Mọi nhận định về chất lượng Jev là [S] (nhà cung cấp hoặc audit cộng đồng) hoặc [I]. Không có mục [V] nào về hành vi Jev.

## 2. Sự thật chịu lực về Jev

| # | Sự thật | Nhãn / nguồn | Hệ quả thiết kế |
| --- | --- | --- | --- |
| J1 | TypeSafe AI, seed $40M, ra mắt early access 2026-09-15. Waitlist gỡ 2026-09-20. Công ty chưa tới 10 ngày tuổi | [S] https://typesafe.ai/blog/introducing-system-one-models-and-jev · https://venturebeat.com/security/companies-are-putting-jev-in-charge-of-ai-agent-decisions-and-prompt-injection-can-influence-the-verdict | Rủi ro nhà cung cấp cao. Bước Jev phải là tuỳ chọn, gỡ bỏ không làm gãy pipeline |
| J2 | **Không sinh văn bản.** Chỉ có 3 primitive: Noul (xác suất có/không), Choice (≤ 255 option, trả `probabilities` và `confidence`), Score (2–10 mức) | [S] https://docs.typesafe.ai/api.md · https://docs.typesafe.ai/introduction/coding-agents.md | Không thay được tóm tắt, hàm ý, trích dẫn hay trích thực thể mở. Danh mục mã CP (~1.600) vượt trần 255, nên chỉ hỏi được Noul trên từng ứng viên |
| J3 | `POST https://api.typesafe.ai/v1/systemone`, Bearer key, `model`/`state`/`questions`. Không có seed, temperature hay batch endpoint. Lỗi 401/422/429/529 | [S] https://docs.typesafe.ai/api.md | Mỗi bài một request. Tính tất định phải đo, không được giả định |
| J4 | Ngữ cảnh 64k/request. `state` + câu hỏi dài nhất ≤ 32k. Chỉ nhận văn bản | [S] https://docs.typesafe.ai/models.md | Một bài tin vừa trần. Nếu dùng nhiều câu `cite_k` thì phải tính cả hai trần |
| J5 | Giá $0,042/1M token vào, output miễn phí. Là giá early access, "cannot prove unsubsidized". Rate limit 250k token/s, 1.200 req/phút, "adjusting dynamically" | [S] https://docs.typesafe.ai/models.md · https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/ | Tiền không đáng kể (≈ $0,03–0,07/ngày [I]). Không đặt trần token (ADR 0010). Chỉ có cổng kỹ thuật 429/529 |
| J6 | Tiếng Anh là chính. Ngôn ngữ khác "not equally well; test on your own content". **Không có số đo tiếng Việt.** Audit cộng đồng: Nga −11 điểm (ECE 0,032 → 0,096), Hàn −6,5, Tây Ban Nha −3 đến −6,4 | [S] https://docs.typesafe.ai/models.md · https://github.com/stillmarcus24/awesome-jev-robustness | **Biến quyết định số 1.** Spike trên tiếng Việt là cổng kill |
| J7 | Hiệu chuẩn không đều: ECE 0,107 trong một nghiên cứu. Ở câu không trả lời được, đúng 44,7% trong khi xác suất trung bình 0,74. Bỏ option "unknown" thì KoBBQ rơi 95% → 0% | [S] https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval · awesome-jev-robustness | Không dùng `confidence` thô. Ngưỡng học từ nhãn riêng. Mọi câu hỏi có "unknown" |
| J8 | Không nhất quán giữa câu hỏi: P(x) + P(¬x) dao động 0,71–1,42. Gọi lặp gần tất định (std 0,001–0,015). Thứ tự option có thể dịch đáp án (nguồn mâu thuẫn về mức độ) | [S] https://docs.typesafe.ai/model-jaggedness/jev-1.13.md · https://pydantic.dev/docs/ai/models/typesafe/ · awesome-jev-robustness | Cố định thứ tự option, ghi `option_order_hash`, đo flip-rate trong spike |
| J9 | Điểm yếu tự công bố: số học, đếm, ngày tháng, phủ định kép, suy luận nhiều bước, `state` nhiều nội dung thừa | [S] https://docs.typesafe.ai/model-jaggedness/jev-1.13.md | Không hỏi Jev về số liệu hay ngày. Đó là việc của DoD tất định |
| J10 | Prompt injection lái được phán quyết: 0,76 → 0,48 (Octomind); 96,5% → 26,5% trên một bộ audit. `state` "not treated as hostile" | [S] VentureBeat (trên) · awesome-jev-robustness | Jev chỉ gắn cờ, không có quyền hành động nào. Spike có 30 bài chèn injection |
| J11 | Cloud-only, không có trọng số. Không huấn luyện trên dữ liệu khách. ZDR chỉ cho enterprise. Region xử lý không công bố | [S] https://docs.typesafe.ai/legal.md · https://docs.typesafe.ai/models.md | Cổng ToS/DPA cứng, do Human quyết |
| J12 | Alias `jev-latest` tự trỏ sang bản mới. Nên ghim phiên bản | [S] https://docs.typesafe.ai/models.md | Ghim `jev-1.13.0`, ghi `model` trả về vào mỗi dòng kết quả (bài học agy 1.2.7 → 1.2.9) |
| J13 | Có SDK Python `typesafe-sdk` (≥ 3.10, sync và async). Có provider Pydantic AI, LangChain, Vercel AI Gateway, OpenRouter, Cloudflare | [S] https://docs.typesafe.ai/sdk/python.md · https://openrouter.ai/typesafe/jev-1.13 | Gọi từ Python thuần. Không cần framework |
| J14 | Có đường thoát mã nguồn mở: Nokia **AnyJev** (Apache-2.0, cùng giao diện, chạy trên LLM mở qua HF/vLLM). **Laya** (mmBERT đa ngữ, chạy local) | [S] https://www.marktechpost.com/2026/09/23/nokia-open-sources-anyjev-a-training-free-layer-that-turns-any-open-llm-into-a-calibrated-decision-model/ · https://www.datacamp.com/blog/top-open-source-jev-alternatives | Đưa làm nhánh đối chứng trong Spike 0. Là phương án thay thế nếu bị kill vì ToS |
| J15 | Benchmark do nhà cung cấp tự chạy: 193,6× nhanh, 444,6× rẻ trên workflow tự viết. Đo độc lập ≈ 2,9× nhanh, ≈ 12× rẻ. "0% hallucination" chỉ nghĩa là đúng schema | [S] https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e · https://news.ycombinator.com/item?id=49745752 · https://www.firecrawl.dev/blog/what-is-jev | Không dùng số của nhà cung cấp làm tiền đề |

**Ẩn số còn mở (chưa ai trả lời được):**

1. Độ chính xác và ECE trên **tiếng Việt tài chính**. Chỉ Spike 0 trả lời được.
2. **`state` bị tính tiền một lần hay mỗi câu hỏi.** api.md chỉ trả `usage.input_tokens`. Nếu tính theo câu hỏi thì mọi số chi phí ở đây sai tới cỡ ×N. Spike 0 phải đo bằng 1 câu và 20 câu trên cùng `state`.
3. Noul có kèm `confidence` không. Theo tài liệu thì chỉ Choice và Score có. Hệ quả là ngưỡng cho `ent_<mã>` phải đặt trên xác suất.
4. Region xử lý, thời hạn lưu dữ liệu với tài khoản không phải enterprise, điều khoản early access (SLA, dùng thương mại), lịch deprecation.
5. Có trần số câu hỏi mỗi request không.
6. AnyJev và Laya có đủ tốt cho tiếng Việt trên máy vận hành không.
7. Sandbox `workspace-write` của DSH có chặn mạng với `tools.pwsh` không. Câu này không quan trọng với kiến trúc được chọn, vì kiến trúc này không gọi Jev từ DSH.

## 3. Bản đồ điểm quyết định trong news-scape và độ phù hợp Jev

Khối lượng tham chiếu ~350 bài/ngày (W365 = 365 bài, 23/09 có 345 bài chờ) [S `docs/SESSION-LATEST.md`, HANDOFF W365].

| # | Điểm quyết định | Hiện tại | Jev fit | Lý do |
| --- | --- | --- | --- | --- |
| D1 | Xếp tầng ưu tiên trong đợt | Script `tier_of` (tiêu đề ∩ watchlist, GICS, regex vĩ mô). Chạy **sau** `LIMIT`, chỉ sắp bên trong đợt [V `article_pack.py:204, 420, 439`] | **low** | Mọi lô chạy song song trong một `run_code`, nên thứ tự trong đợt gần như không đổi giờ giao [I]. Thứ tự Jev không tất định sẽ phá bất biến packet giống từng byte để trúng cache [V `article_pack.py:196-201`] |
| D2 | Bộ chọn bài vào đợt | SQL `ORDER BY published_at DESC, url_title_hash LIMIT ?`, loại `code_first` [V `article_pack.py:202-204`] | **none** | Tất định, chỉ có một đáp án đúng. Cho Jev vào đây là biến thứ tự thành bộ lọc, trái §6B |
| D3 | Materiality | **Không ai làm.** Lean không có trường `m`. `_sort_key` đọc `materiality.score`. Do `ag.get("materiality") or {}` luôn là dict nên nhánh `materiality_score` là mã chết và score luôn bằng 0 [V `user_output.py:288-293`] | **med** (chỉ để đo) | Khoảng trống có thật. Nhưng score chỉ là **khoá phụ sau timestamp** [V `user_output.py:297`], nên điền điểm vào không đổi thứ tự giao hàng nếu không đổi khoá sắp. Đổi khoá là quyết định sản phẩm. Cách rẻ nhất về governance là thêm `m` trong chính lượt DeepSeek (intake riêng, không phụ thuộc Jev) |
| D4 | Sentiment `sn` | DeepSeek trong cùng lượt, chi phí biên ≈ 0 [V `article_expand.py:301`] | **low** | Thay thế tiết kiệm chưa tới $0,01/ngày. Chỉ đo độ đồng thuận trong spike |
| D5 | Time sensitivity `ts` | DeepSeek trong cùng lượt [V `article_expand.py:302`] | **low** | Như D4. Thêm nữa, ngày tháng là điểm yếu của Jev (J9) |
| D6 | Nhóm thực thể `e[1]` (11 mã) | DeepSeek trích và gán nhóm | **low** | Jev không trích được chuỗi (J2). Chỉ gán lại được nhóm cho thực thể đã có |
| D7 | Xác minh mã CP đã gắn là chủ thể thật | Không ai kiểm. Đối chiếu danh mục chỉ để so, không để thay (§6B) | **high** | Noul trên tập đóng các mã mà LLM đã trả về. Theo mẫu "LLM trích, Jev xác minh" [S https://beam.ai/agentic-insights/jev-typesafe-ai-agents]. Gắn sai mã thì bài bị giao nhầm người |
| D8 | Dedup cùng sự kiện đa nguồn | SimHash và rapidfuzz. `story-dedup-clusterer` còn draft | **med** | Noul theo cặp làm tie-breaker. Có giá trị nhưng chưa có nhu cầu đo được. Hoãn |
| D9 | Triage "đáng phân tích sâu" | `materiality-triage` draft, `stage_role: pre-gold-gate`, "cổng rẻ" [V `registry.yaml:288-303`] | **none** | Trái §6B ("mọi bài đều được xử lý đầy đủ") và ADR 0010. Entry phải sửa, có Jev hay không |
| D10 | DoD tất định (schema, trích nguyên văn, độ phủ ≥ 90%) | Script [V `src/agent/dod.py`, `article_run.py verify_wave`] | **none** | Tất định |
| D11 | Kiểm trích dẫn và DoD ngữ nghĩa | **Không ai kiểm.** `adversarial-dod-verifier` draft, `post-gold-qa`, mang luật 05-gold [V `registry.yaml:323-338`] | **high** | Choice `supports/contradicts/says_nothing/unknown` trên cặp (đoạn k, claim) [S firecrawl cookbook]. Khác họ mô hình nên lỗi ít tương quan hơn flash tự kiểm flash [I]. Là use case duy nhất cả 3 bên đồng thuận |
| D12 | Phân tuyến tới người dùng | Script: thực thể ∩ watchlist từng user | **low** | Hỏi Jev "có liên quan watchlist U" là nhận diện thực thể thứ hai, xâm vùng độc quyền §6C. Giá trị gián tiếp đi qua D7 |
| D13 | Nhãn tin rác/PR | `domain_validator` (cơ học) | **low** | Chỉ được gắn nhãn, không được loại. Rủi ro trôi thành bộ lọc |
| D14 | Kích hoạt đợt / backlog | Radar in một lệnh, người quyết | **none** | Quyết định vận hành, không phải phân loại nội dung |
| D15 | Brief cuối ngày | `daily-brief-synthesizer` draft | **low** | Vẫn cần LLM sinh văn bản. Có thể dùng D3 làm đầu vào về sau |

Nhận xét [I]: tách phân loại khỏi lượt DeepSeek để giao cho Jev không tiết kiệm được gì, vì phần đắt của lượt là đọc trọn bài và sinh văn bản. Giá trị Jev chỉ nằm ở những chỗ **đang không ai làm**, và trong số đó chỉ D7 và D11 vừa có giá trị vừa nằm ngoài vùng độc quyền của `article-processor`.

## 4. Các phương án đã xét và kết cục

| Phương án | Người đề xuất | Kết cục | Bằng chứng |
| --- | --- | --- | --- |
| **K — Kiểm định hậu kỳ `cite_k` + `ent_<mã>`, shadow, report-only, sau `--finish`** | P2 (thu hẹp ở rebuttal), P1 và P3 nhận | **CHỌN**, có điều kiện Spike 0 đạt | D7 và D11 là hai loại lỗi DoD tất định không bắt được và DeepSeek không tự kiểm độc lập được. Không chạm §6B/§6C. Không thêm bước nào vào phiên điều phối |
| Dọn nợ registry: sửa `materiality-triage` và `adversarial-dod-verifier` cho khớp ADR 0010 | P1, P3 | **CHỌN**, làm đầu tiên, không cần Jev (Cấp 2) | `stage_role: pre-gold-gate`, KPI `gold_burn_reduction_pct`, `cost_budget` (trái "token là ghi nhận"), luật 05-gold [V `registry.yaml:288-338`] |
| Nhánh đối chứng cục bộ AnyJev/Laya trên cùng golden set | P3, P1, P2 | **CHỌN** trong Spike 0 | Loại rủi ro nhà cung cấp và dữ liệu ra ngoài (J11, J14). Là đường thay thế nếu ToS bị kill |
| Nhánh đối chứng deepseek-flash tự kiểm trên cùng câu hỏi | P2 | **CHỌN** trong Spike 0 (nhánh C) | Nếu flash có precision flag hơn Jev ≥ 15 điểm thì bỏ Jev. Không cần nhà cung cấp mới |
| `mat` (materiality) trong Spike 0 | P3 giữ, P2 bỏ khỏi sản xuất | **CHỌN chỉ để đo**, không đưa vào sản xuất qua Jev | Số đo làm đầu vào cho quyết định `m` của DeepSeek. Bất đồng còn lại: xem cuối mục |
| Thêm trường `m` vào `agent-output-v2-lean` + đổi khoá sắp xlsx | P3 (Bước 0), P1 #3, P2 #4 | **HOÃN, tách intake riêng Cấp 3** | Là Data Contract (AGENTS.md §0). Không có tác dụng nếu không đổi `_sort_key` [V `user_output.py:297`]. Cần Human quyết khoá sắp |
| Jev tiền xử lý: sắp thứ tự / nâng tầng trước pack (`jev_triage.py`) | P1 (bản đầu) | **LOẠI**, P1 tự rút | `tier_of` chạy sau `LIMIT` [V]. Thứ tự trong đợt không đổi giờ giao [I]. Phá bất biến packet tất định từng byte [V `article_pack.py:196-201`], nên `--repair` trượt cache. Phần tràn ngày 23/09 chỉ 45 bài (345 so với `--limit` 300 [V `article_pack.py:384`]). Mở lại chỉ khi tồn đọng > `--limit` kéo dài > 24h ít nhất 3 lần/tuần **và** có ADR riêng cho bộ chọn theo tầng |
| Jev lọc tin rác / bỏ phân tích sâu | P1 (phương án B) | **LOẠI** | Vi phạm §6B. Lặp lại đúng lỗi 2.915 bài kẹt mà ADR 0010 vừa gỡ |
| Jev thay `sn`/`ts`/`e[1]` của DeepSeek | — | **LOẠI** | Tiết kiệm < $0,01/ngày, thêm nhà cung cấp, thu hẹp vùng độc quyền §6C |
| Jev trong `run_code` DSH (gọi `fetch`) | — | **LOẠI** | Worker thread có môi trường rỗng, không có credential. Phải nhúng key vào mã và key sẽ rơi vào session log JSONL [V README `dsh-code-runtime-worker-thread` theo research C] |
| Jev làm `agentOptions.provider` qua `dsh-llm-pi-ai` | — | **LOẠI** | Giao thức `systemone` không phải openai/anthropic và Jev không sinh văn bản [I từ J2, J3] |
| Leo thang cờ sang `adversarial-dod-verifier` | P2 (bản đầu) | **HOÃN**, P2 tự rút | Là kích hoạt thêm một agent draft của lane đã ngừng, tức gộp hai thay đổi Cấp 3 (trái WIP=1). Pha 1 chỉ ghi hàng đợi tệp cho người xem |
| Dedup tie-breaker (D8), nhãn rác (D13) | research C | **HOÃN** | Chưa có nhu cầu đo được. Xem lại sau L2 |
| MCP server cộng đồng (`jev-mcp`) | research B | **LOẠI** | Bảo trì vài ngày tuổi. Python SDK trực tiếp đơn giản hơn |
| Không làm gì với Jev trong quý | P3 | **Chấp nhận một phần**: không có gì vào sản xuất (L2) trong quý này | Mọi lợi ích mới là giả thuyết. Mọi rủi ro đã có dữ liệu |

**Bất đồng còn lại (không che):**

1. **Cấp của Spike 0.** P1 cho rằng dùng key cá nhân và chỉ ghi scratch là Cấp 2. P3 (sau khi rút) và P2 cho rằng AGENTS.md §0 ghi đích danh "API token" nên là Cấp 3. **Chủ toạ theo câu chữ: Cấp 3 rút gọn** (story `blocked`, Human duyệt key và ToS, chưa viết ADR trước khi spike đạt). Human có quyền hạ về Cấp 2 (H2).
2. **Ngưỡng kill AUROC `cite_k`.** P1 và P2 dùng 0,70, P3 dùng 0,75 trên hard negative. Chủ toạ chọn **0,75**, vì negative trong cùng bài khó hơn negative tổng hợp nên 0,70 là quá dễ dãi. Chưa có dữ liệu nào xác nhận con số nào đúng.
3. **Ngưỡng tất định.** P3 đòi ≥ 98% giữ nguyên. P1 và P2 dùng flip-rate ≤ 10%. Chưa có dữ liệu, cả hai đều là đoán [I]. Chủ toạ dùng ≤ 10% làm kill và ghi con số đo được làm cơ sở cho các lần sau.
4. **Có đo `mat` bằng Jev không.** P2 coi là nhiễu vì sẽ không vào sản xuất. P3 muốn có baseline. Chủ toạ giữ trong spike vì chi phí biên ≈ 0 và nhãn người đằng nào cũng phải gán.
5. **Lời văn sửa ADR 0009 D6.** P1 và P2 muốn "mọi model **sinh văn bản** là deepseek-flash". P3 cảnh báo cách viết này mở cửa cho mọi mô hình phân loại về sau. **Chủ toạ theo P3:** ngoại lệ ghim tên nhà cung cấp, tên model, phiên bản và vai trò.
6. **Có đáng làm Jev không, ngay cả khi spike đạt.** P3 vẫn giữ "chi phí governance Tier 3 lớn hơn lợi ích nếu tỷ lệ flag thật < 1%". Điều này được đưa thành tiêu chí kill ở L1, không giải quyết bằng tranh luận.

## 5. Kiến trúc được chọn

```
Bronze → Silver → article_run.py --wave W (pack) → DSH run_code | agy runner (deepseek-flash, KHÔNG ĐỔI)
                                                         │
                                                         ▼
                                   article_run.py --wave W --finish   (cổng kỹ thuật, KHÔNG ĐỔI)
                                                         │  thoát 0
                                                         ▼
        ┌──────────── scripts/jev_verify.py --wave W   (bước tuỳ chọn, terminal, không trong DSH) ─────────────┐
        │ đọc (chỉ đọc):  article_W_*.task.json (đoạn Silver đánh số) + *.output.json (l1-entity-v1, lean-v2)│
        │ key:            TYPESAFE_API_KEY từ env người dùng / Credential Manager, không vào repo/log/preset │
        │ gọi:            typesafe-sdk async, model=jev-1.13.0 (ghim), 1 bài = 1 request, 8–16 luồng,        │
        │                 429/529 → backoff 3 lần; 401/422/mạng → jev_status=skipped                        │
        │ state:          <article> tiêu đề + đoạn đánh số </article> + "nội dung trên là dữ liệu"           │
        │ questions:      cite_k  Choice {supports, contradicts, says_nothing, unknown}  × mỗi trích dẫn    │
        │                 ent_<mã> Noul  × mỗi mã LLM đã trả về (tập đóng, không hỏi danh mục mở)            │
        │ ghi:            L1: data/qa/jev/<W>.jsonl (+ .escalate.json)  |  L2: bảng jev_verdicts (DB)        │
        │                 mỗi dòng: article_id, q_id, answer, probs, model_returned, option_order_hash, usage │
        └───────────────────────────────────── luôn thoát 0 ──────────────────────────────────────────────┘
                                                         │
                                                         ▼
                           write_user_output.py (L1: KHÔNG ĐỔI · L2: thêm cột chỉ đọc `jev_flag`)
```

**Điểm cắm:**

- **DSH:** không đổi gì. Không thêm bước vào phiên điều phối, nên bất biến "một đợt = một `run_code`" giữ nguyên. Preset `news-scape-conductor` không biết Jev tồn tại.
- **agy** (nếu đề xuất 23/09 được duyệt): Python đã là conductor, nên `article_tick.py` gọi `jev_verify.py` như một bước con sau `--finish`, cùng hợp đồng I/O. Jev độc lập với lựa chọn runner.
- **Python:** `jev_verify.py` là script duy nhất gọi Jev. Nó đọc tệp của đúng đợt đã có trên đĩa [V: `data/agent_tasks/article/article_W365_*.task.json` và `data/agent_outputs/article_W365_*.output.json` tồn tại], nên ở L1 không cần mở `monocle.db`.
- **Zero-Probe:** `pipeline_radar.py status` thêm một dòng `jev: <pin> · đợt W: ok|skipped|n_flag` và `article_run.py --where` thêm dòng báo key có mặt (không in giá trị).

**Fallback (Degrade-Don't-Fail):** thiếu key, lỗi mạng, hoặc > 20% request lỗi thì ghi `jev_status=skipped`, in cảnh báo, thoát 0. Giao hàng chạy bình thường. Jev **không bao giờ** là điều kiện thoát 0 của `--finish` hay của giao hàng, và không tính vào độ phủ ≥ 90%. Dự phòng dài hạn là AnyJev/Laya cục bộ, cùng giao diện câu hỏi, đổi được bằng một cờ `--backend`.

**Những gì Jev không bao giờ làm:** loại bài, đổi thứ tự bộ chọn bài, ghi đè `agent_outputs`, tự sửa nhãn, cấp quyền cho hành động nào, hay được tính là "đã phân tích".

## 6. Governance

| Hạng mục | Nội dung |
| --- | --- |
| Tier | US-028 (dọn registry) là **Cấp 2**. US-029 (Spike 0) là **Cấp 3 rút gọn**: Hard Gate cho key và ToS, chưa có ADR. US-030/031 là **Cấp 3 đầy đủ**: ADR, Human duyệt, Detailed Trace |
| Intake | Mở **Intake #26** (số kế tiếp sau #25 của agy, cần xác nhận trong harness.db) cho Jev. Story `status: blocked` tới khi Human duyệt H1 |
| ADR cần lập | **ADR số kế tiếp** (0011 nếu ADR agy chưa lấy; đề xuất agy cũng cần số mới vì 0010 đã bị ADR ngừng lane L1/Gold chiếm [V `docs/decisions/`]). Nội dung: (1) ngoại lệ ADR 0009 D6 [V `0009*:39` "Mọi route agent = deepseek-flash"], ghim `typesafe/jev-1.13.0`, vai trò verifier hậu kỳ, **không** nới thành "mọi model phân loại"; (2) lớp tác nhân mới `typed-classifier` trong rule 07 §1, với ba cam kết: không tính là đã phân tích, không vào độ phủ, không bao giờ là cổng; (3) chính sách key: env/Credential Manager, luân chuyển, không vào log; (4) ToS, DPA, region, dữ liệu ra ngoài; (5) bảng `jev_verdicts` (L2) là schema mới, không động `agent-output-v2-lean`; (6) fallback |
| `registry.yaml` | US-028: sửa `materiality-triage` (bỏ `pre-gold-gate`, `cost_budget`, `gold_burn_reduction_pct`, sửa intent thành "sắp thứ tự, không phải cổng", hoặc `retired`) và `adversarial-dod-verifier` (bỏ `post-gold-qa`, luật 05-gold, trần token; I/O trỏ Article Lane). US-030: thêm `jev-verifier` (`class: typed-classifier`, `status: draft`, `model: jev-1.13.0`, `stage_role: post-finish-verifier`, `io_boundary.write: data/qa/jev/*`, `activation_gate: ADR-00xx`, KPI `cite_flag_precision`, `ent_flag_precision`, `flag_rate`, `skipped_rate`, `flip_rate`) |
| `pipeline.yaml` | US-030: node tuỳ chọn `jev_verify` (needs `finish`, trước `deliver`, `on_fail: continue`) |
| `docs/TOOL_REGISTRY.md` | Dòng provider đầu tiên: Jev → (AnyJev/Laya cục bộ) → bỏ qua |
| Sổ cái | `token_pricing.yaml` thêm `jev-1.13.0`. `token_ledger` thêm nguồn `jev` đọc `usage.input_tokens`. Chỉ ghi nhận, không đặt trần |
| Provenance | `article_expand.py:53-54` hardcode `AGENT_PROVIDER="dsh"`, `MODEL_USED="deepseek-flash"` [V]. Không đổi, vì Jev ghi bảng riêng, không đi qua expander |
| Bất biến bị chạm | ADR 0009 D6 (ngoại lệ tường minh). Taxonomy rule 07 §1 (lớp mới). **Không chạm:** "một đợt = một `run_code`", "mọi bài xử lý đầy đủ", "token là ghi nhận", "đối chiếu chỉ để kiểm", vùng độc quyền §6C, "Bảo toàn raw" |
| WIP = 1 | Nhánh `feature/article-lane-remove-gates` còn thay đổi chưa commit. Đề xuất agy (US-025..027) cũng đang chờ. Human phải xếp thứ tự (H1). Không mở US-029 khi còn story khác `in_progress` |

## 7. Kế hoạch thực thi theo giai đoạn

Số story là số tạm (sau US-027 của đề xuất agy). Lấy số thật từ harness.db khi intake.

### Giai đoạn −1: US-028 — Dọn nợ registry (Cấp 2, không cần Jev)

| | |
| --- | --- |
| Deliverable | Sửa hai entry `registry.yaml` như mục 6. Cập nhật SKILL tương ứng nếu có |
| Proof | `harness_cli.py audit` không báo drift mới. Test registry (nếu có) PASS. `pytest tests/` 100% |
| Chi phí | ≈ 0,5 ngày công, 0 USD |

### Giai đoạn 0: US-029 — Spike 0 shadow ngoại tuyến (Cấp 3 rút gọn, tối đa 1 tuần)

| | |
| --- | --- |
| Tiền đề | Human duyệt H1 (key, ToS/DPA, loại tài khoản). Story `blocked` → `in_progress` chỉ sau đó |
| Golden set | 300 bài từ các tệp W365 và 23/09 trên đĩa (không mở `monocle.db`), phân tầng theo nguồn và độ dài. 100 bài do analyst FRA gán nhãn mù: từng cặp (trích dẫn, claim) đỡ/không đỡ, mã được gắn có đúng là chủ thể, materiality 1–5. **Hard negative:** đoạn khác trong **cùng bài**, cùng thực thể. Hàm ý vượt quá trích dẫn. Mã CP xuất hiện trong bài nhưng không phải chủ thể. Thêm ~300 negative tổng hợp (chỉ để tham khảo). 30 bài chèn injection. Đảo thứ tự option trên toàn bộ |
| Nhánh | **A** Jev `jev-1.13.0` · **B** AnyJev (LLM mở cục bộ) hoặc Laya · **C** deepseek-flash tự kiểm trên cùng câu hỏi (chạy qua DSH trên packet scratch, không nạp DB) |
| Đo | AUROC `cite_k`, `ent_<mã>` trên hard negative. Precision/recall của flag (người xác nhận). ECE trước và sau hiệu chuẩn isotonic. Flip-rate khi chạy lại 3 lần và khi đảo option. Δ khi bị injection. **`usage.input_tokens` với 1 câu và 20 câu trên cùng `state`** (ẩn số #2). Spearman `mat` với người. Độ trễ |
| Deliverable | `project/scripts/jev_shadow_eval.py` (đọc JSONL, ghi CSV ra scratch). Test mock HTTP cho 429/401/422 và fallback. `docs/proposals/jev-council-2026-09-24/spike0-RESULTS.md` với số [V] |
| Pass (đủ tất cả) | AUROC `cite_k` ≥ 0,85 trên hard negative · precision flag ≥ 50% · flip-rate ≤ 5% · Δ injection ≤ 10 điểm · ECE sau hiệu chuẩn ≤ 0,08 · Jev không kém nhánh C quá 15 điểm precision flag · có ToS/DPA chấp nhận được |
| Kill (một là đủ) | AUROC `cite_k` < 0,75 **và** `ent_<mã>` < 0,75 · flip-rate > 10% · injection làm lệch > 20% số bài · precision flag < 30% · nhánh C hơn Jev ≥ 15 điểm precision (khi đó chọn flash) · `state` bị tính theo câu hỏi làm chi phí Jev vượt chi phí Article Lane/ngày · giá hoặc rate limit đổi trong spike · quá 1 tuần · không có ToS/DPA. Kill vì ToS mà nhánh B đạt thì chuyển sang AnyJev/Laya, không kết thúc |
| Vùng xám | Kết quả nằm giữa pass và kill: chọn từng câu hỏi riêng (ví dụ giữ `cite_k`, bỏ `ent`). Không nâng ngưỡng sau khi đã thấy số |
| Chi phí | Jev ≈ 300 bài × 4 lượt × ~5k token ≈ 6M token ≈ **$0,25** [I, nếu `state` tính một lần]. Nhánh C ≈ $0,3–0,5. Nhánh B ≈ 0 USD, tốn giờ máy. Chi phí thật lớn nhất là **công gán nhãn của analyst: ≈ 6–10 giờ** [I]. Công dev ≈ 3–5 ngày |

### Giai đoạn 1: US-030 — L1 shadow trong pipeline (Cấp 3 đầy đủ, 14 ngày)

| | |
| --- | --- |
| Tiền đề | Spike 0 đạt. ADR được duyệt (H3). Registry/pipeline/TOOL_REGISTRY cập nhật như mục 6 |
| Deliverable | `scripts/jev_verify.py --wave W` chạy sau `--finish`, ghi `data/qa/jev/<W>.jsonl` và `.escalate.json`. **Không ghi DB, không đổi xlsx.** Dòng radar `jev` và `--where`. Ledger nguồn `jev` |
| Proof | pytest: mock HTTP, 429/529 backoff, 401/422 → skipped và thoát 0, không có key → skipped và thoát 0, `--finish` và `write_user_output` không phụ thuộc Jev. Kiểm tra key không xuất hiện trong mọi tệp log/output |
| Pass | Sau 14 ngày: precision flag do người xác nhận ≥ 50% trên mẫu 50 cờ · flag rate 3–20% · skipped rate ≤ 5% · không lần nào Jev làm chậm hay gãy giao hàng |
| Kill | Precision < 30% · flag rate < 1% (LLM đã đủ tốt, lời P3 thắng) hoặc > 35% · giá hoặc rate limit đổi bất lợi · model trả về ≠ pin |
| Chi phí | Jev ≈ $0,03–0,07/ngày [I]. Người xem 10–70 cờ/ngày nếu flag rate 3–20% [I]. Đây là chi phí thật, cần Human cam kết người xem (H4) |

### Giai đoạn 2: US-031 — L2 active (Cấp 3, sau khi L1 đạt, không trong quý này)

| | |
| --- | --- |
| Deliverable | Bảng `jev_verdicts` (schema mới, migration riêng). `write_user_output.py` thêm cột chỉ đọc `jev_flag` (không đổi khoá sắp, không lọc). Cảnh báo drift khi flag rate vượt ±2σ của 14 ngày |
| Proof | Test migration. Test xlsx có và không có dữ liệu Jev cho ra cùng tập bài và cùng thứ tự |
| Pass / kill | Như L1, cộng thêm phản hồi người dùng về cột `jev_flag`. Tự rơi về L1 nếu skipped rate > 20% trong 3 ngày liên tiếp |

## 8. Rủi ro và giảm thiểu

| # | Rủi ro | Mức | Giảm thiểu |
| --- | --- | --- | --- |
| R1 | Chất lượng tiếng Việt kém (J6). Tin tài chính dày số và ngày (J9) | Cao | Spike 0 là cổng kill. Không hỏi về số hay ngày. Có nhánh B và C |
| R2 | Nhà cung cấp < 10 ngày tuổi, giá và rate limit đổi không báo, alias trôi (J1, J5, J12) | Cao | Ghim bản. Ghi `model_returned`. Bước tuỳ chọn. Có AnyJev/Laya thay thế |
| R3 | Hiệu chuẩn lệch, confidence quá tự tin (J7) | Cao | Isotonic trên nhãn riêng. Ngưỡng học từ dữ liệu. Có option `unknown` |
| R4 | Prompt injection từ nội dung bài (J10) | Trung bình | Jev chỉ gắn cờ, không có quyền. State bọc `<article>`. Đo Δ injection trong spike |
| R5 | Dữ liệu ra ngoài, ToS, region (J11) | Trung bình | Chỉ gửi tin công khai đã cào, không gửi watchlist hay dữ liệu người dùng. Human quyết H1 |
| R6 | Trôi phạm vi thành cổng lọc (D9) | Cao về governance | ADR ghi cấm. Registry sửa trước (US-028). Test xlsx cùng tập bài có hoặc không có Jev |
| R7 | Rò key vào log DSH | Cao nếu đặt sai chỗ | Không bao giờ gọi từ `run_code`. Test quét key trong output |
| R8 | Mệt mỏi vì báo động giả: người phải xem 10–70 cờ/ngày | Trung bình | Kill khi precision < 30%. Chỉ đưa lên hàng đợi các cờ trên ngưỡng học được |
| R9 | Chi phí nhân ×N nếu `state` tính theo câu hỏi (ẩn số #2) | Thấp về tiền, cao về tính đúng của đề xuất | Đo ngay trong ngày đầu Spike 0 |
| R10 | Làm mờ ranh giới "No Script Emulation" | Thấp | Lớp `typed-classifier` riêng. Jev là mô hình, không phải heuristic |
| R11 | Chen hàng WIP với agy và nhánh đang dở | Trung bình | Human xếp thứ tự (H1). Jev xếp sau US-025 |

## 9. Việc cần Human quyết định

| # | Quyết định | Khuyến nghị của chủ toạ |
| --- | --- | --- |
| H1 | Thứ tự ưu tiên so với đề xuất agy (US-025..027) và nhánh `feature/article-lane-remove-gates` chưa commit (WIP = 1) | Commit nhánh hiện tại → US-028 → US-025 (tiền đề agy) → US-029 |
| H2 | Cấp của Spike 0: Cấp 3 rút gọn hay Cấp 2 (bất đồng số 1) | Cấp 3 rút gọn |
| H3 | Cấp key TypeSafe: tài khoản cá nhân hay miền FPTS. Chấp nhận gửi nội dung tin công khai sang nhà cung cấp Mỹ chưa công bố region và retention (non-ZDR) | Chỉ tiến hành khi có ToS/DPA bằng văn bản. Nếu không có thì chạy nhánh B (cục bộ) |
| H4 | Cam kết công analyst FRA: ≈ 6–10 giờ gán nhãn golden set, và người xem cờ trong 14 ngày L1 | Bắt buộc. Không có nhãn người thì spike không có ground truth |
| H5 | Duyệt ADR (ngoại lệ D6 ghim nhà cung cấp và bản, lớp `typed-classifier`) trước L1 | Chỉ viết ADR sau khi Spike 0 đạt |
| H6 | Tách intake riêng cho trường `m` trong DeepSeek, và **có đổi khoá sắp xlsx** thành `(ngày, -m, -ts)` hay không | Hỏi 5 người dùng trước. Không có đổi khoá thì trường `m` vô tác dụng |
| H7 | Chấp nhận chạy nhánh C (flash tự kiểm) qua DSH trên packet scratch trong spike | Đồng ý. Đây là đối chứng quyết định Jev có đáng không |
