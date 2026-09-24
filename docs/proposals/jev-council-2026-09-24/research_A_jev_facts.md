# Researcher A: sự thật sản phẩm Jev (TypeSafe AI System One)

Ngày tra cứu: 2026-09-24. Vai trò: kiểm toán/nghiên cứu, chỉ đọc. Không gọi API, không dùng khoá.
Nhãn: **[S]** có nguồn (URL), **[V]** kiểm chứng thực nghiệm tại máy, **[I]** suy luận.
Ghi chú: tài liệu này không có mục [V] nào vì chưa có API key và vai trò không cho phép gọi API.

## Nguồn chính

| Mã | URL |
|----|-----|
| BLOG | https://typesafe.ai/blog/introducing-system-one-models-and-jev |
| DOCS-IDX | https://docs.typesafe.ai/llms.txt |
| API | https://docs.typesafe.ai/api.md |
| MODELS | https://docs.typesafe.ai/models.md |
| JAG | https://docs.typesafe.ai/model-jaggedness/jev-1.13.md |
| CONF | https://docs.typesafe.ai/confidence.md |
| ADV | https://docs.typesafe.ai/primitives/advanced.md |
| STATE | https://docs.typesafe.ai/concepts/state.md |
| PYSDK | https://docs.typesafe.ai/sdk/python.md |
| AGENTS | https://docs.typesafe.ai/introduction/coding-agents.md |
| LEGAL | https://docs.typesafe.ai/legal.md |
| FLAVIO | https://flaviocopes.com/jev/ |
| DEVTO | https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e |
| MTP | https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/ |
| MTP-ANY | https://www.marktechpost.com/2026/09/23/nokia-open-sources-anyjev-a-training-free-layer-that-turns-any-open-llm-into-a-calibrated-decision-model/ |
| WIKI | https://en.wikipedia.org/wiki/Jev_(AI_model) |
| MIND | https://www.mindstudio.ai/blog/jev-system-one-model-launch |
| PYD | https://pydantic.dev/docs/ai/models/typesafe/ |

## 1. Sản phẩm là gì

- [S BLOG, WIKI] Jev là model đầu tiên của TypeSafe AI (San Francisco, thành lập 2024, CEO Diogo Almeida, đồng tác giả InstructGPT). Ra mắt early access 2026-09-15, kèm vòng seed 40 triệu USD do DCVC dẫn.
- [S BLOG] "System One model": trạng thái phi cấu trúc vào, quyết định có kiểu và có xác suất ra. Sinh mọi đầu ra trong một lượt song song, không sinh token tuần tự.
- [S WIKI, MTP] Nền transformer nhưng không phải LLM. Huấn luyện bằng RLCD (Reinforcement Learning for Calibrated Decisions), theo WIKI chỉ trên dữ liệu tổng hợp. Không công bố kiến trúc, số tham số hay trọng số.
- [S BLOG, AGENTS] **Không sinh văn bản**: không tóm tắt, không viết code, không giải thích. TypeSafe ghi rõ Jev không thay được LLM của agent lập trình.

## 2. API

- [S API, FLAVIO] `POST https://api.typesafe.ai/v1/systemone`, header `Authorization: Bearer <API_KEY>`, `Content-Type: application/json`. Khoá dạng `sk-...` lấy tại console.typesafe.ai, biến môi trường `TYPESAFE_API_KEY` [S DEVTO, PYSDK].
- [S API] Request gồm:
  - `model` (bắt buộc): `jev-latest`, `jev-preview` hoặc `jev-1.13.0`.
  - `state` (bắt buộc): chuỗi, JSON object hoặc mảng văn bản.
  - `questions` (bắt buộc): map `id → Question`.
- [S API] Question có `type` ∈ {`noul`, `choice`, `score`}, `instructions` (chuỗi, object hoặc mảng) và `criteria`.
- [S API] Response trả `model`, `answers` (map theo id) và `usage` (`input_tokens`, `output_tokens`).
- [S API] Mã lỗi: 401 (khoá sai), 422 (sai schema), 429 (vượt rate limit), 529 (quá tải). SDK tự backoff.
- [S API] Không có trường nào cho temperature, seed, few-shot hay endpoint batch.

## 3. Hệ kiểu (chỉ 3 primitive)

| Primitive | Khai báo | Trả về | Có `confidence` |
|---|---|---|---|
| Noul (có/không) | `criteria.true` / `criteria.false` (tuỳ chọn) | `noul` ∈ [0,1] (xác suất "có") | Không [S CONF] |
| Choice (chọn 1) | `criteria`: map option → mô tả, tối đa **255** option | `choice`, `probabilities`, `confidence` | Có |
| Score (thang thứ tự) | `criteria`: mảng **2–10** mức | `score` (có thể lẻ, ví dụ 1.035), `legend`, `probabilities`, `confidence` | Có |

- [S ADV] Instructions, option và level đều nhận JSON có cấu trúc: option có thể mang `what`, `not_for`, `examples`; level mang `summary`, `signals`; noul mang `true`/`false` kèm `examples`. Đây là đường duy nhất để đưa ví dụ vào, qua mô tả, không qua trường few-shot riêng.
- [S API, PYD] Không có kiểu string, số tự do, datetime, danh sách tự do hay multi-label gốc.
  - Pydantic AI mô phỏng multi-label bằng một Noul cho mỗi option.
  - Pydantic AI mô phỏng số bị chặn (`float ge/le`) qua xác suất.
  - Kiểu `str` hoặc số không chặn bị chặn ngay bằng `UserError`.
- [S CONF] `confidence` là thống kê suy ra từ độ tập trung của phân phối, không phải một đầu ra độc lập. Ví dụ với 3 option: `(3·pmax − 1)/2`. Tài liệu khuyên đặt ngưỡng theo mức hậu quả của hành động.
- [S BLOG] Tuyên bố hiệu chuẩn: "higher confidence means higher accuracy". Đánh dấu hallucination 0% là "not empirical": chỉ nghĩa là đầu ra luôn đúng schema, không nghĩa là đúng sự thật [S MTP].
- [S JAG] Không có bảo đảm nhất quán giữa các câu hỏi, ví dụ P(yes) ≠ 1 − P(no) khi hỏi theo hai cách.
- [S PYD] Thứ tự option ảnh hưởng đáp án.

## 4. Giới hạn, độ trễ, giá

- [S MODELS, FLAVIO] Ngữ cảnh: tổng **64k token** cho state và mọi câu hỏi; tối đa **32k token** cho state cộng câu hỏi dài nhất. Chỉ nhận văn bản.
- [S BLOG, DEVTO] Độ trễ đầu-cuối 70–500 ms, trung vị khoảng 256 ms. Thêm câu hỏi trong cùng request tốn token nhưng gần như không thêm thời gian.
- [S MODELS] Giá: input **$0.042/1M token** ($42/1 tỷ), **output miễn phí**. MTP ghi TypeSafe "cannot prove the price is unsubsidized", tức giá có thể thay đổi.
- [S MODELS] Rate limit: 250.000 token/giây, 1.200 request/phút, "adjusting dynamically" và có thể đổi không báo trước.
- [S API] Không có tài liệu về số câu hỏi tối đa mỗi request. Không có batch API.

## 5. Ngôn ngữ

- [S MODELS, STATE] Tốt nhất với tiếng Anh. Ngôn ngữ khác, kể cả CJK, vẫn chạy nhưng độ chính xác thấp hơn và dao động.
- [S] Không có số liệu công khai cho tiếng Việt.
- [I] Bài tiếng Việt về tài chính là vùng rủi ro chưa đo. Phải chạy đối chứng trên mẫu thật trước khi dùng.

## 6. SDK và tích hợp

- [S PYSDK] Python `typesafe-sdk` (Python ≥ 3.10), có client đồng bộ `TypeSafeClient` và bất đồng bộ `AsyncTypeSafeClient`, gọi qua `client.system_one(state=..., questions=...)`.
- [S FLAVIO] JavaScript `@typesafe-ai/sdk` (Node ≥ 20). Vercel AI SDK `@ai-sdk/typesafe-ai` (Node ≥ 22).
- [S PYD] Pydantic AI có provider `typesafe:jev-latest` (`TypeSafeModel`).
- [S AGENTS] TypeSafe phát hành "agent skill" cho Claude Code và Codex để agent viết mã tích hợp đúng.
- [S MTP, FLAVIO] Vercel AI Gateway cung cấp `typesafe-ai/jev` mà không cần qua waitlist.
- [S MTP-ANY] Mã nguồn mở thay thế: Nokia **AnyJev**, Apache-2.0, https://github.com/nokia-applied-research/AnyJev.
  - Dùng cùng giao diện choice/noul/score, đọc xác suất từ next-token của LLM mở (Qwen, OLMo, Granite, Phi, Mistral) qua HF/vLLM.
  - Hiệu chuẩn bằng cyclic shift, prior correction và temperature scaling.
  - Trên BANKING77 với Qwen3-8B: độ chính xác tăng 74,7% → 80,7%, ECE giảm 0,240 → 0,095.

## 7. Triển khai, dữ liệu, truy cập

- [S MTP] Chỉ có API cloud: không self-host, không trọng số.
- [S] Không tìm thấy tài liệu công khai về region hay nơi lưu dữ liệu.
- [S MODELS, LEGAL] Không huấn luyện trên request/response của khách. Zero data retention chỉ dành cho khách enterprise (liên hệ privacy@typesafe.ai). Có DPA, Master Customer Agreement và Privacy Policy.
- [S BLOG, DEVTO] Early access qua waitlist tại typesafe.ai.
- [S] Không tìm thấy điều khoản early access, SLA hay danh sách subprocessor công khai.
- [S DEVTO, FLAVIO] Phiên bản hiện tại là `jev-1.13.0`. `jev-latest` và `jev-preview` đều trỏ về bản này. Tài liệu khuyên ghim phiên bản để tránh hành vi đổi ngầm.

## 8. Benchmark (do nhà cung cấp tự chạy)

- [S DEVTO] 67,8% trên 4 workflow, với nhãn là đồng thuận giữa GPT-6 Astra và Claude Fable 5.1. Ngang Sonnet 5 (67,8%) với khoảng 1/200 chi phí và 1/50 độ trễ.
- [S DEVTO] Caveat: tự chạy, chưa ai tái lập, và đo mức đồng thuận với model frontier chứ không đo với ground truth.
- [S BLOG, MTP, WIKI] Nhanh hơn 40–200 lần. Đỉnh 193,6 lần nhanh hơn và 444,6 lần rẻ hơn trên workflow do chính TypeSafe viết.
- [S WIKI] Đánh giá độc lập còn ít. Có nhắc JevBench (Benchmark Heaven).
- [S MIND] Các demo (Minecraft, drone, Doom) đều chạy trong simulator.

## 9. Failure mode đã biết [S JAG, DEVTO, PYD]

- Đọc câu hỏi theo nghĩa đen: phủ định, từ giới hạn phạm vi và điều kiện ngầm bị hiểu đúng như chữ viết.
- Không làm được số học, đếm hay so sánh số. Nhận "hình dạng" đáp án chứ không tính.
- Ngày tháng được đọc như văn bản: không so sánh, không tính khoảng cách, không xử lý tốt định dạng lẫn lộn.
- Suy luận nhiều bước và phủ định kép kém.
- Context rot: nội dung không liên quan trong state làm giảm độ chính xác.
- Không cảnh giác với dữ liệu thù địch: prompt injection trong state có thể lái kết quả.
- Criteria mâu thuẫn với instructions làm giảm chất lượng.
- Không sinh văn bản, nên không tự trích văn bản hay thực thể mới ngoài danh sách option.

## 10. Hàm ý sơ bộ cho news-scape (chỉ suy luận, để Researcher B/C phản biện)

- [I] Jev không thay được `article-processor`. Lớp phân tích (tóm tắt, hàm ý, trích dẫn) và phần trích thực thể mở của lớp nhận diện đều cần sinh văn bản hoặc tập mở.
- [I] Các vị trí có thể hợp với Jev:
  - `materiality` và `sentiment` dưới dạng Score hoặc Choice có `confidence`.
  - Xác minh ứng viên mã CP: mỗi ứng viên từ bộ đối chiếu tất định thành một Noul. Đây là phân xử ngữ nghĩa bằng model, không phải script giả lập.
  - Phân loại ngành hoặc tuyến watchlist, miễn tập nhãn không vượt 255 option.
  - Kiểm tra trích dẫn theo chỉ số đoạn, dựa trên cookbook `citation_check`.
- [I] Chi phí ước lượng: đợt 100 bài × khoảng 3k token × vài câu hỏi ≈ 0,3–1M token, tức khoảng 0,013–0,042 USD mỗi đợt.
- [I] Bài dài hơn khoảng 32k token phải lọc hoặc chia đoạn, dù bài tin tài chính hiếm khi dài như vậy.
- [I] Rủi ro:
  - Tiếng Việt chưa có số đo.
  - Jev bị gọi qua HTTP từ Python, nằm ngoài DSH và `deepseek-flash`, nên đổi ranh giới công cụ. Phải có ADR vì AGENTS.md §6C nói "mọi model là deepseek-flash" (ADR 0009 D6).
  - Phụ thuộc nhà cung cấp mới ở giai đoạn early access, giá chưa chứng minh là không được trợ giá, rate limit có thể đổi.
  - Nội dung bài báo có thể chứa injection.

## 11. Ẩn số còn mở

1. Độ chính xác với tiếng Việt, đặc biệt văn bản tài chính có tên doanh nghiệp và mã CP. Cần [V] trên mẫu có nhãn.
2. Region xử lý dữ liệu và thời gian lưu dữ liệu với khách không phải enterprise (non-ZDR).
3. Điều khoản early access: SLA, giới hạn sử dụng thương mại, thời gian chờ waitlist, có quota miễn phí hay không.
4. Có trần số câu hỏi mỗi request hay không. Tổng token cho nhiều câu hỏi được tính thế nào: câu hỏi có nhân với state không, tức mỗi câu hỏi có tính lại toàn bộ state không.
5. Tính tất định: cùng input có ra cùng xác suất không (không có seed hay temperature).
6. Hiệu chuẩn thực tế ngoài phân phối tiếng Anh, vì chưa có số ECE công khai cho Jev.
7. Giá và rate limit trên Vercel AI Gateway so với API trực tiếp. Gateway có thêm markup hay retention không.
8. Lộ trình phiên bản (sau 1.13) và chính sách ngừng hỗ trợ.
9. DSH có gọi được HTTP tool tuỳ biến tới Jev không, hay Jev chỉ gọi được từ script Python ngoài DSH. Cần đối chiếu với tài liệu DSH của dự án.
10. AnyJev chạy cục bộ với LLM mở có đủ tốt cho tiếng Việt không. Đây là phương án không phụ thuộc nhà cung cấp.
