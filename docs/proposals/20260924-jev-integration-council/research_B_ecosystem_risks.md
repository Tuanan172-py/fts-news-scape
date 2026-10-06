# Research B — Hệ sinh thái, mẫu tích hợp và rủi ro của Jev

Vai trò: Researcher B (chỉ đọc mã, nghiên cứu web). Ngày: 2026-09-24.
Nhãn: **[S]** có nguồn (URL), **[V]** kiểm chứng tại máy, **[I]** suy luận.
Lưu ý: không có mục [V] về hành vi Jev vì phiên này không gọi API (không dùng credential). Mọi số liệu về Jev là [S] hoặc [I].

## 1. Jev là gì (tóm tắt để đặt nền)

- TypeSafe AI ra khỏi stealth 2026-09-15, seed $40M do DCVC dẫn; nhà sáng lập Diogo Almeida (đồng tác giả InstructGPT), Erik Gafni, Sasha Sheng. [S] https://beam.ai/agentic-insights/jev-typesafe-ai-agents , https://finance.yahoo.com/technology/ai/articles/typesafe-ai-emerges-stealth-40m-190000776.html , https://en.wowtale.net/2026/09/21/235190/
- Jev không sinh văn bản. Nhận `state` (văn bản/JSON) + các câu hỏi có kiểu, trả xác suất: `Noul` (có/không), `Choice` (≤255 lựa chọn), `Score` (thang có thứ tự). Mọi câu hỏi trong một request được đánh giá song song. [S] https://www.langchain.com/blog/building-a-harness-with-jev , https://typesafe.ai/blog/introducing-system-one-models-and-jev
- Endpoint `POST https://api.typesafe.ai/v1/systemone`; SDK `typesafe-sdk` (Python ≥3.10), `@typesafe-ai/sdk`, `@ai-sdk/typesafe-ai`; model `jev-1.13.0`, alias `jev-latest`. [S] https://flaviocopes.com/jev/
- Ngữ cảnh 64k token/request; `state` + câu hỏi dài nhất ≤ 32k token. Rate limit early access 250k token/s, 1.200 req/phút, "can change without notice". [S] https://docs.typesafe.ai/models
- Giá $0.042/1M token input, output miễn phí; là giá early access, không phải bảng giá GA, có thể đổi. [S] https://docs.typesafe.ai/models , https://www.ai-crescent.com/blog/jev-typesafe-pricing-2026
- Độ trễ 70–500 ms end-to-end (đo từ US West Coast). [S] https://flaviocopes.com/jev/
- Kênh phân phối: TypeSafe API trực tiếp, Vercel AI Gateway, OpenRouter (`typesafe/jev-1.13`), Cloudflare AI, LangChain (`langchain-typesafe`), Pydantic AI (`typesafe:jev-latest`). [S] https://openrouter.ai/typesafe/jev-1.13 , https://developers.cloudflare.com/ai/models/typesafe/jev/ , https://pydantic.dev/docs/ai/models/typesafe/
- Không huấn luyện trên dữ liệu khách hàng; ZDR/DPA cho enterprise. [S] https://docs.typesafe.ai/models

## 2. Các mẫu tích hợp chuẩn (canonical patterns)

| Mẫu | Mô tả | Nguồn |
|---|---|---|
| Smart if | Jev là một `if` có xác suất; code đọc xác suất và quyết định | [S] https://vercel.com/i/what-is-jev , https://www.datacamp.com/blog/system-one-models-jev |
| Router (System1→System2) | Jev ước độ khó/ý định, code chọn model ID rồi gọi LLM; LangChain `ModelRouterMiddleware` | [S] https://www.firecrawl.dev/blog/what-is-jev , https://www.langchain.com/blog/building-a-harness-with-jev |
| Guard / Auto mode | Phân loại rủi ro tool call trước khi chạy; LangChain `AutoModeMiddleware`; pi-warden giữ lệnh phá huỷ ~250 ms | [S] như trên |
| Triage + escalation theo ngưỡng | Ngưỡng gợi ý: confidence < 0.5 → người xét; > 0.9 mới cho hành động phá huỷ; "application code owns policy and execution" | [S] https://flaviocopes.com/jev/ , https://vercel.com/i/what-is-jev |
| Scorer / reranker | BM25 shortlist → mỗi kết quả 10 câu `Noul`; top-1 5%→18%, top-10 38%→62% | [S] https://www.firecrawl.dev/blog/what-is-jev |
| Crawl-and-classify | Trang scrape → Jev hỏi loại trang, lỗi thời, có code không; 500 trang ≈ 2M token < $0.10 | [S] https://www.firecrawl.dev/blog/what-is-jev |
| Sàng lọc đầu ra LLM | Kiểm trích dẫn: đoạn nguồn `supports / contradicts / says_nothing` với khẳng định | [S] https://www.firecrawl.dev/blog/what-is-jev |
| LLM trích, Jev xác minh | "let the LLM extract the field, then hand the extracted value and its source to Jev to verify" | [S] https://beam.ai/agentic-insights/jev-typesafe-ai-agents |
| Cổng chống injection cho nội dung web | Nội dung cào qua cổng relevance/evidence/adversarial-instruction trước khi vào ngữ cảnh agent | [S] https://www.firecrawl.dev/blog/what-is-jev |
| MCP | Nhiều server cộng đồng (không chính thức): `rashedInt32/jev-mcp` (plugin Claude Code), `tphakala/jev-mcp` (TypeSafe API/OpenRouter), `blakestone-x/jev-mcp`, `jbt95/jev-toolkit` (event log + Prometheus) | [S] https://github.com/rashedInt32/jev-mcp , https://github.com/tphakala/jev-mcp , https://github.com/jbt95/jev-toolkit |

Điều kiện dùng hợp lý theo Beam: tập đáp án định trước, quyết định lặp lại nhiều, có ngưỡng confidence để gác cổng. [S] https://beam.ai/agentic-insights/jev-typesafe-ai-agents

## 3. Thực hành đánh giá và hiệu chuẩn

- **Tự hiệu chuẩn, không tin mặc định.** Pydantic: confidence là biên so với ngưỡng, cần "calibrate each [threshold] against labelled examples of your own". [S] https://pydantic.dev/docs/ai/models/typesafe/
- **Chạy shadow trên hồ sơ quyết định cũ.** Một đợt 5.721 lượt gọi tốn $0.176. [S] https://www.beri.net/article/typesafe-jev-typed-decision-model-calibration-decomposition-shadow-eval
- **Phân rã câu hỏi.** Phishing: một câu hỏi 62,6% (Haiku 81,3%); tách 5 câu nguyên tử + logistic regression trên 1.000 nhãn → 95,0%. "The 95% is not Jev. It is Jev plus your labelled data plus a regression you maintain." [S] cùng nguồn beri.net
- **Hiệu chuẩn không đều.** ECE 0,107 trong một nghiên cứu; Choice/Score quá tự tin, Noul thiếu tự tin; trên tác vụ không trả lời được: đúng 44,7% nhưng xác suất trung bình 0,74. [S] beri.net; ECE 0,008–0,117 tuỳ tác vụ [S] https://github.com/stillmarcus24/awesome-jev-robustness
- **Phải có lựa chọn "unknown".** Bỏ lựa chọn abstain: KoBBQ từ 95% → 0%, ECE 0,023 → 0,793. [S] awesome-jev-robustness (dẫn jujumilk3/jev-calibration-audit)
- **Nhất quán.** Gọi lặp gần tất định (std 0,001–0,015). P(x)+P(¬x) dao động 0,71–1,42; Noul và Choice lệch trung bình 0,125 cho cùng phán đoán. [S] awesome-jev-robustness
- **Thứ tự lựa chọn — có mâu thuẫn giữa nguồn.** Pydantic và trang giới hạn của TypeSafe cảnh báo đổi thứ tự có thể dịch đáp án [S] https://pydantic.dev/docs/ai/models/typesafe/ ; audit độc lập thấy ảnh hưởng nhỏ (0/400 lật khi đảo, 5% khi hoán vị 4 cách) nhưng đếm/số học tụt 88%→57% khi đáp án đúng ở cuối. [S] awesome-jev-robustness. Kết luận [I]: phải cố định thứ tự lựa chọn và kiểm hoán vị trong bộ eval.
- **Thêm ứng viên không liên quan làm lệch log-odds 0,31–0,50**; gộp 40 hàng/request phá xếp hạng. [S] awesome-jev-robustness → [I] một bài một request, không gộp nhiều bài vào một `state`.
- Điểm yếu tự công bố: đếm, số học, ngày tháng, phủ định kép, suy luận nhiều bước, `state` lớn nhiều chi tiết thừa. [S] https://flaviocopes.com/jev/ , https://www.firecrawl.dev/blog/what-is-jev

## 4. Bảo mật: prompt injection vào phán quyết

- Octomind: xác suất chặn `rm -rf ~/.ssh` 0,76 → 0,48 (confidence 0,22) sau khi chèn "đã được duyệt trước" vào tool output. [S] https://venturebeat.com/security/companies-are-putting-jev-in-charge-of-ai-agent-decisions-and-prompt-injection-can-influence-the-verdict
- TypeSafe 1.13 tự nhận: nội dung viết để lái mô hình "can move the answer"; `state` mặc định "not treated as hostile". [S] VentureBeat, Pydantic
- Audit độc lập: lệnh thô 0/30 vượt; mạo danh thẩm quyền tới 3/30 vượt; bộ Wikipedia deletion 96,5% → 26,5% khi có chỉ thị chèn; một benchmark khác chỉ 1/1.056 thành công. [S] https://github.com/stillmarcus24/awesome-jev-robustness
- Giảm thiểu: LangChain loại tool output khỏi input của bộ phân loại "so content the agent fetched cannot authorize its own execution"; guard Jev "belongs alongside deterministic checks, not instead of them"; giữ người duyệt cho hành động hệ quả lớn. [S] VentureBeat, Pydantic
- Checklist trước production (VentureBeat): log state/schema/thứ tự lựa chọn/version/confidence; workload identity riêng; test đa thứ tự; test văn bản đối nghịch; **ghim version, không dùng `jev-latest`**; ai chịu trách nhiệm khi bỏ sót leo thang. [S] VentureBeat
- [I] Với news-scape: nội dung bài báo là đầu vào không tin cậy (nguồn công khai, có thể chứa PR/quảng cáo "bài viết này rất quan trọng"). Jev chỉ nên đưa ra tín hiệu thứ tự/cờ kiểm, không cấp quyền hành động nào.

## 5. Rủi ro nhà cung cấp

- Startup seed, 9 ngày tuổi; model đang early access; waitlist được gỡ 2026-09-20 (140k người được mở trong 36 giờ). [S] VentureBeat
- Giá là giá early access, có thể đổi; rate limit "can change without notice". [S] https://www.ai-crescent.com/blog/jev-typesafe-pricing-2026 , https://docs.typesafe.ai/models
- Alias tự trỏ sang version mới → hành vi đổi lặng lẽ nếu không ghim. [S] https://docs.typesafe.ai/models
- Chỉ hosted; không chạy offline; gửi dữ liệu ra API ngoài cần opt-in. Dự án `cc-operator-plugin` coi đây là rủi ro chi phối tính khả thi hơn cả thiết kế. [S] https://github.com/betmoar/cc-operator-plugin/issues/151
- Phương án thoát: mã nguồn mở tương tự — Laya (ModernBERT/mmBERT, checkpoint đa ngữ 100+ ngôn ngữ, chạy local), Nimble/Kev (Qwen3.5 + LoRA), SemIf, NanoJev. [S] https://www.datacamp.com/blog/top-open-source-jev-alternatives , https://jevmodel.org/jev-vs-laya/
- Hệ sinh thái MCP/SDK phần lớn do cộng đồng viết trong vài ngày, chưa có bảo trì dài hạn. [I]

## 6. Phản biện và góc nhìn hoài nghi

- "Zero hallucination" chỉ nghĩa là đúng schema: "can't emit an invalid type, but it can still emit a wrong valid value"; con số 0% không đo thực nghiệm. [S] https://news.ycombinator.com/item?id=49745752 , https://www.firecrawl.dev/blog/what-is-jev
- So sánh 193x nhanh / 445x rẻ là so với LLM làm việc nặng hơn; đo độc lập ≈2,9x nhanh, ≈12x rẻ; "444.6x cheaper" đo độ đồng thuận với frontier model chứ không phải độ đúng so với nhãn thật. [S] HN tổng hợp qua firecrawl/hackerspot; beri.net
- r/LocalLLaMA: giống zero-shot classifier encoder (gliformer) hoặc "logprobs wrapper" trên model mở fine-tune. [S] https://www.firecrawl.dev/blog/what-is-jev
- Every: Jev bắt 6/7 lỗi cài sẵn so với Fable 7/7. [S] https://www.firecrawl.dev/blog/what-is-jev
- Tool hallucination 76% ở ca không cần tool (When2Call). [S] awesome-jev-robustness
- Pre-registered test: 4/12 failure mode được xác nhận, 8 bị bác. [S] awesome-jev-robustness (primeline.cc)

## 7. Bằng chứng về văn bản không phải tiếng Anh

- TypeSafe: tiếng Anh là ngôn ngữ huấn luyện chính; ngôn ngữ khác "not equally well; test on your own content". Không có eval đa ngữ chính thức. [S] https://docs.typesafe.ai/models , https://chatmaxima.com/blog/typesafe-jev-system-one-model/
- Audit cộng đồng: Nga 77,3% vs Anh 88,3% (ECE 0,096 vs 0,032); Tây Ban Nha mất 3–6,4 điểm, ECE gấp đôi; Hàn mất 6,5 điểm; Ba Tư gần ngang Anh. [S] https://github.com/stillmarcus24/awesome-jev-robustness
- **Không tìm thấy bằng chứng nào cho tiếng Việt.** [S: tìm không ra] → [I] kỳ vọng hợp lý: giảm 5–11 điểm chính xác và ECE gấp 2–3 lần so với tiếng Anh; văn bản tài chính tiếng Việt có mã CP viết hoa, số liệu, ngày tháng — đúng các điểm yếu tự công bố (số học, ngày tháng).

## 8. Hàm ý cho news-scape (suy luận, để hội đồng phản biện)

Đối chiếu bất biến AGENTS.md §6 và registry:

1. [I] **Không dùng Jev làm cổng lọc bài.** AGENTS.md §6.B: "Mọi bài đều được xử lý đầy đủ… xếp tầng chỉ quyết định thứ tự". Agent draft `materiality-triage` trong `.agents/registry.yaml` (dòng 288–303) mô tả là "cổng rẻ quyết định bài có đáng phân tích Gold sâu không" — mâu thuẫn với ADR 0010 hiện hành. Nếu dùng Jev ở đây, chỉ được dùng làm tín hiệu **thứ tự** trong `article_pack.py`, không bỏ bài.
2. [I] **Không để Jev thay `article-processor`.** Jev không sinh tóm tắt, hàm ý, trích dẫn; §6.C giữ các việc ngữ nghĩa cho `deepseek-flash`. Jev cũng không thay được nhận diện thực thể (không sinh chuỗi; mã CP là tập ~1.600+ lựa chọn > trần 255 Choice).
3. [I] **Ứng viên hợp lý nhất — kiểm chứng hậu kỳ (post-check), report-only:**
   - Kiểm trích dẫn: đoạn được trích (theo chỉ số) `supports / contradicts / says_nothing` với tóm tắt/hàm ý → một KPI `citation_ground_rate` độc lập với chính mô hình sinh ra (mẫu "LLM trích, Jev xác minh").
   - Kiểm `materiality`/`sentiment` của deepseek-flash bằng `Score`/`Choice` thứ hai → cờ bất đồng để người rà, không ghi đè.
   - `story-dedup-clusterer` tie-breaker: sau SimHash, hỏi Noul "hai bài có cùng một sự kiện?" (mẫu giống issue #151 rework detection).
   Cả ba đều thuộc "đối chiếu tất định chỉ để kiểm, không để thay" và không chặn `--finish`.
4. [I] **Ràng buộc vận hành:** gọi Jev phải nằm trong script có credential riêng, ngoài sandbox DSH (`workspace-write` không ra mạng/DB ngoài kho); ghim `jev-1.13.0`; log state hash + schema + thứ tự lựa chọn + version + confidence vào bảng riêng; luôn có lựa chọn `unknown`; một bài một request.
5. [I] **Điều kiện tiên quyết:** shadow eval trên ≥ 300 bài tiếng Việt đã có nhãn (kết quả `article-processor` đã được người rà) trước khi đưa bất kỳ tín hiệu Jev nào vào radar/handoff. Chi phí eval ước < $0.05 (300 bài × ~3k token × vài câu hỏi). Nếu độ đồng thuận hoặc ECE kém, dừng và cân nhắc Laya mmBERT chạy local.
6. [I] **Phân cấp theo AGENTS.md §0:** tích hợp Jev vào pipeline là thêm API token mới + nhà cung cấp mới → Cấp 3 HIGH-RISK, cần ADR và người duyệt. Shadow eval độc lập, không ghi DB vận hành, có thể là Cấp 2.
