# Hội đồng nghiên cứu thiết kế và dư địa phát triển — 2026-09-24

- **Loại:** nghiên cứu, chỉ đọc. Không sửa mã, không ghi DB vận hành, không chạy đợt.
- **Phương pháp:** 6 agent nghiên cứu song song, mỗi agent một phạm vi: (1) tầng dữ liệu, (2) tầng agent / Article Lane, (3) giao hàng và giá trị người dùng, (4) harness và quản trị, (5) lịch sử ADR và đề xuất, (6) thực hành bên ngoài 2024–2026. Phiên điều phối đối chiếu chéo và tự kiểm lại bằng mã các phát hiện nặng nhất (đánh dấu **[đã kiểm]**).
- **Cập nhật 2026-09-24 (quyết định người dùng):** `materiality` và `event_type` **không còn dùng**. Đầu ra giữ sạch: mô hình không sinh, giao hàng không xuất (`user_output.py` đã gỡ, `materiality-triage` retired). Mọi xếp hạng/cảnh báo dưới đây dựa trên tín hiệu sẵn có: `time_sensitivity`, tầng watchlist, kích thước cụm và số nguồn. Kế hoạch triển khai: `plans/20260924-research-council-execution/plan.md`.
- **Trạng thái:** đề xuất. Mọi mục đổi Data Contract, schema DB hay ADR 0009 D6 là Cấp 3, phải có ADR và người duyệt.

---

## 1. Kết luận điều hành

1. **Kiến trúc lõi đúng hướng và nên giữ.** Hệ thống là một *workflow tất định có đúng một bước LLM*: cào → Bronze bất biến → Silver → đóng gói → `article-processor` (deepseek-flash, song song theo lô) → bung → cổng DoD → giao hàng. Theo phân loại "Building effective agents" của Anthropic, đây là prompt chaining + parallelization. Hướng này khớp thực hành ngành (phần lớn hệ thống production là workflow, không phải agent tự chủ).
2. **Nút thắt không nằm ở "thiếu agent" mà ở hai chỗ:**
   - **Khoảng trống đo lường.** Hệ thống đo *đủ số lượng* (độ phủ ≥ 90%, nạp không lỗi), không đo *đúng*. Không có golden set, precision/recall hay chấm chất lượng tóm tắt/hàm ý. Mọi tối ưu prompt, model hay agent mới hiện là đoán.
   - **Rò giá trị ở ranh giới giữa các tầng.** Nhiều giá trị được tạo ra rồi bị vứt trước khi đến tay analyst (mục 3).
3. **Dư địa lớn nhất theo thứ tự:** vá rò giá trị (rẻ, S) → golden set + eval (M, tiền đề cho mọi thứ) → đưa thực thể thân bài vào phân tuyến (Cấp 3) → tầng *sự kiện* (gom cụm câu chuyện) mở khoá cảnh báo, bản tin ngày, dòng thời gian theo mã và RAG.
4. **Agent tự chủ chỉ nên đặt ở rìa, không đặt trên đường giao hàng:** `entity-curator` (đề xuất delta danh mục, người duyệt) và `harness-auditor` (chỉ đọc). Các ý tưởng còn lại (gom cụm, verifier, brief) nên là bước workflow cố định.

---

## 2. Thiết kế hiện tại (như mã thực thi, không như tài liệu)

```
[8 nguồn bật: cafef(API theo mã + 6 RSS), vietstock, vneconomy, baodautu, tnck, fireant, vietnambiz, tbtc]
   │ morninger: capture 10' (tuần tự theo nguồn, chu kỳ ~335s) · derive 30' · reclaim · drift 06:00
   ▼
BRONZE  raw_html + .meta.json (sha256, ghi nguyên tử)            ← điểm mạnh: tái dựng được mọi thứ
   │ dedup: sha256(url+title) + fuzzy title ≥90 trong 48h           ← [R1] vứt bài vĩnh viễn
   ▼
SILVER  trafilatura→fallback, <p>, simhash64, article_versions, watermark mốc thấp + dead-letter (ADR 0007)
   ▼
ARTICLE LANE (ADR 0010, đường duy nhất)
   article_run --wave → article_pack (xếp tầng watchlist = chỉ thứ tự) → packet {i,t,p[]} + wave_X.conductor.ts
   → DSH run_code: hâm cache → Promise.all lô → agent_article (deepseek-flash, 0 tool, 1 bước/lô)
   → article_expand (resolve entity_id, reconcile LLM↔danh mục, dựng trích dẫn từ chỉ số đoạn)
   → l1_ingest + agent_ingest (DoD) → hậu kiểm độ phủ ≥90% → token_ledger → handoff
   ▼
GIAO HÀNG  write_user_output → users/output/<user>/<ngày đăng>.xlsx (1 sheet, sắp theo thời gian)
```

**Lệch giữa tài liệu và mã (đã xác minh):**

| Tài liệu nói                                           | Mã làm                                                                                                                                        |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| AGENTS.md §6A: `article-processor` trả `materiality` | Đã xử lý 2026-09-24: bỏ trường khỏi AGENTS.md và khỏi đầu ra giao hàng |
| `docs/design/07…`: simhash64 dùng gom gần-trùng     | `change_detect.classify` chỉ dùng sha + DOM-sig; Hamming tính nhưng không dùng                                                          |
| `charter.md`: WSL/T7920/ClickHouse/Telegram, 1 user     | Windows + OneDrive + SQLite, 5 user, không có Telegram                                                                                        |
| Rule 05: "Smart Paragraph Distillation"                   | AGENTS.md §6B: đọc trọn nội dung, trần chắt lọc đã tắt                                                                               |
| HARNESS_MATURITY: H4 chặn story chưa verify             | `harness_cli.py:294` mặc định `unit_proof or 1`, `--run-verify` là tuỳ chọn                                                         |

---

## 3. Phát hiện chéo: nơi giá trị bị rò

Xếp theo luồng dữ liệu, từ thượng nguồn xuống.

| #   | Rò ở đâu                                                           | Bằng chứng                                                                                                                                                                                                                                                                  | Hệ quả                                                                                                                                                        |
| --- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| L1  | **Fuzzy dedup vứt bài, so cả với chính nguồn**             | `src/core/base_scraper.py:70` truyền `self.name` ("cafef") trong khi `seen_articles.source_domain` có cả "cafef.vn"; `dedup.py:92` lọc `!=` nên không loại được chính nguồn. `token_set_ratio`=100 khi tiêu đề là tập con **[đã kiểm]** | ~1.566 hash có trong`seen_articles` mà không có trong `articles`, gồm tin CBTT dạng "VHM: CBTT…". Không lưu Bronze nên không khôi phục được |
| L2  | **Bài sửa không bao giờ phân tích lại**                   | `articles` INSERT OR IGNORE theo url; bộ chọn bài lấy `package_path` tuỳ ý giữa các phiên bản (`article_pack.py:185-193`)                                                                                                                                     | 180 bản`CONTENT_CHANGED` bị bỏ qua                                                                                                                         |
| L3  | **Thực thể thân bài và ngành suy từ ngữ cảnh bị vứt** | `article_expand.py:197` chỉ giữ `e.in_title and e.surface in title`; `article_mentions/*.json` chỉ ghi, không ai đọc **[đã kiểm]**                                                                                                                       | Đúng phần prompt gọi là "giá trị chỉ bạn làm được" (`build_article_prefix.py:313`) bị loại khỏi phân tuyến watchlist                        |
| L4  | **Few-shot dạy sai**                                            | Ví dụ gán ngành "Vận tải đường bộ & đường sắt" cho bài thép Hòa Phát (`build_article_prefix.py:300`) **[đã kiểm]**                                                                                                                               | Nhiễu ngành có hệ thống                                                                                                                                    |
| L5  | **Trích dẫn tự bù không do mô hình chọn**                | Mô hình trả < 2 chỉ số thì script bù đoạn đầu đủ dài (`article_expand.py:281-288`), comment ghi "dài nhất" nhưng không sắp **[đã kiểm]**                                                                                                        | "Bằng chứng" có thể không đỡ luận điểm; DoD grounding hiển nhiên đúng                                                                             |
| L6  | **Bài trượt phần nội dung kẹt vĩnh viễn**                | Bộ chọn chỉ nhìn`l1_outputs`, mà bản ghi nhận diện luôn được sinh (`article_pack.py:190-192`)                                                                                                                                                                 | Tới 10% mỗi đợt không bao giờ được chạy lại                                                                                                          |
| L7  | ~~Không có materiality / event_type~~ | Đã quyết định ngừng dùng; khoá sắp phụ đã gỡ khỏi `user_output.py` | Đóng |
| L8  | **xlsx giấu điểm mạnh**                                      | Không có cột citations; 3 cột Intent kỹ thuật chiếm đầu bảng (`xlsx_delivery.py:16-36`)                                                                                                                                                  | Trích dẫn nguyên văn, lợi thế chính của Article Lane, không tới tay analyst                                                                           |
| L9  | **Nhịp đợt thưa, độ phủ thấp**                           | Từ 15/09: 3.870 bài, 763 được phân tích (~20%); các ngày 19, 20, 22/09 không có đợt; tệp giao mới nhất 21/09; trễ trung vị ~6 giờ                                                                                                                          | Analyst không nhận gì trong nhiều ngày                                                                                                                     |
| L10 | **Lane cũ vẫn chạy được**                                  | `project/scripts/run_daily.ps1:96-105` vẫn gọi `l1_route`, `l1_ingest --code-first`, `agent_export` **[đã kiểm]**; `morninger` đang chạy từ 17/09 bằng mã cũ                                                                                       | Có thể tái sinh đúng lỗi ADR 0010 (code-first bị coi là đã phân tích)                                                                               |

**Rủi ro vận hành đi kèm:**

- Bronze 2,1 GB và Silver nằm trong OneDrive, đường dẫn tương đối theo cwd; 478 MB rơi nhầm vào `project/src/data/`.
- 2 bản DB xung đột OneDrive; `settings.yaml:3` còn trỏ DB chết 187 MB.
- `project/data/archive/` (3.350 tệp) không bị gitignore.
- 25 tệp chưa commit (+1.064/−846) trên `feature/article-lane-remove-gates`.

---

## 4. Workflow hay agent: nên đặt trí tuệ ở đâu

| Thành phần                    | Mẫu hiện tại                                        | Mẫu nên có                                                                                                                                             | Ghi chú                                                                           |
| ------------------------------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| pack → LLM → expand → ingest | Prompt chaining + parallelization                      | Giữ nguyên                                                                                                                                              | Đúng, dự đoán được, sửa được bằng 1 lệnh                             |
| Xếp tầng watchlist            | Routing suy biến (chỉ thứ tự)                      | Giữ + thêm**nhịp riêng cho tầng 1** (đợt nhỏ, dày)                                                                                         | Phục vụ cảnh báo gần thời gian thực                                         |
| `--repair`                    | Retry tất định                                      | **Evaluator-optimizer có giới hạn 1 vòng**: bài trượt DoD/bị verifier gắn cờ đóng gói lại kèm lý do trượt                         | Vá L6                                                                             |
| `adversarial-dod-verifier`    | Draft, 0 dòng mã                                     | **Evaluator lấy mẫu**: 5% mỗi đợt + 100% bài `time_sensitivity=urgent` thuộc watchlist                                                                                  | Chỉ báo cáo, không chặn (bài học lịch sử)                                 |
| `story-dedup-clusterer`       | Draft                                                  | **Workflow lai**: simhash LSH + embedding (bge-m3) tất định, LLM chỉ phân xử ca biên, đặt trước pack                                     | Giảm token, sinh tín hiệu "độ lan truyền"                                    |
| `materiality-triage`          | Retired 2026-09-24 | Không làm | Người dùng ngừng dùng materiality |
| `daily-brief-synthesizer`     | Draft, skill lỗi thời (`model: pro`, sai manifest) | **Orchestrator-workers map-reduce** theo user, mỗi ý neo `article_id` + đoạn đã kiểm                                                       | Phụ thuộc cụm + `time_sensitivity`                                                     |
| `entity-curator`              | Draft                                                  | **Agent bán tự chủ, có cổng người duyệt**: đọc `article_mentions` + bất đồng reconcile, đề xuất delta danh mục, sinh lại prefix | Chỗ duy nhất tự chủ có lợi rõ                                               |
| `harness-auditor`             | Draft                                                  | **Agent chỉ đọc**: đọc ledger + điểm eval + defect, soạn đề xuất                                                                         | Thay`propose` hiện gần như rỗng                                              |
| Model                           | Chỉ deepseek-flash (ADR 0009 D6)                      | **Cascade** flash → pro cho bài bất đồng mô hình↔danh mục hoặc bị verifier gắn cờ, *chỉ khi eval chứng minh lợi ích*                                              | Cấp 3, sửa ADR 0009                                                              |

---

## 5. Dư địa phát triển theo tầng

### 5.1 Tầng dữ liệu

| Việc                                                                                                                                             | Công sức | Giá trị                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------ |
| Vá L1: chuẩn hoá`source_domain`; không vứt mà lưu Bronze + `duplicate_of`/`similarity`; miễn trừ tiêu đề CBTT dạng `MÃ: …` | S          | Rất cao (dừng mất dữ liệu)                  |
| Gom đường dẫn Bronze/Silver/package về`MONOCLE_DATA_DIR` tuyệt đối, ra khỏi OneDrive; preflight thất bại khi cấu hình DB sai       | S          | Cao                                              |
| Bảng`capture_daily` (fetched, detail_ok, deferred, giveup, extraction_quality, fuzzy_dropped) + cảnh báo                                     | S          | Cao về vận hành                               |
| Derive tăng dần bằng chỉ mục Bronze trong DB thay vì`rglob` mỗi 30 phút                                                                 | S–M       | Trung bình                                      |
| Phân tích lại bài sửa (vá L2)                                                                                                               | M          | Trung bình                                      |
| Song song theo nguồn (một luồng/nguồn, một luồng ghi DB)                                                                                    | M          | Rút chu kỳ ~7' → 2–3', có chỗ thêm nguồn |
| **Nguồn có cấu trúc**: CBTT HOSE/HNX/SSC, lịch sự kiện doanh nghiệp, lập lịch NSO; khoá (mã, loại, kỳ)                        | M–L       | Rất cao cho analyst                             |

### 5.2 Tầng agent

| Việc                                                                                                                                                                                                                                                                   | Công sức | Giá trị                          |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------- |
| Sửa few-shot (L4), sắp trích dẫn bù đúng hoặc bỏ bù (L5), lưu`prefix_hash` + `model` theo dòng, sửa `agent_provider="antigravity"` cứng                                                                                                             | S          | Cao                                |
| **Golden set 150–200 bài** phân tầng theo nguồn / có-không mã theo dõi; `scripts/eval_article.py` 0 token: precision/recall thực thể theo nhóm, khớp sentiment, tỷ lệ trích dẫn đỡ luận điểm; ghi `agent_metrics` sau mỗi `--finish` | M          | Rất cao, tiền đề cho mọi thứ |
| Kiểm neo tất định 0 token: số liệu và mã trong`s`/`k`/`im` phải xuất hiện trong đoạn trích                                                                                                                                                          | S          | Cao                                |
| **ADR thực thể thân bài:** thực thể thân bài + ngành suy ra đi vào phân tuyến (vá L3), lưu `prefix_hash`/`model` theo dòng                                                                                                 | M, Cấp 3  | Rất cao, mở khoá mục 5.3       |
| Vá L6 + evaluator-optimizer 1 vòng                                                                                                                                                                                                                                    | S–M       | Cao                                |
| Verifier lấy mẫu                                                                                                                                                                                                                                                      | M          | Cao                                |
| Gom cụm câu chuyện +`story_id`                                                                                                                                                                                                                                     | M          | Cao                                |
| Tự động hoá bước tay DSH (preflight persona/preset/mốc khởi động host)                                                                                                                                                                                        | S–M       | Giảm lỗi hỏng im lặng          |

### 5.3 Tầng người dùng

| Việc                                                                                                               | Công sức | Phụ thuộc        |
| ------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------ |
| Sắp lại xlsx: cột Trích dẫn; dời cột Intent ra sau; sắp `urgent` lên đầu                                    | S          | —                  |
| Tệp theo ngày xử lý / "mới từ lần trước" thay vì ghi ngược vào ngày đăng                            | S          | —                 |
| Hợp nhất hai manifest user (ngữ nghĩa mặc định ngược nhau)                                                 | S          | —                 |
| Nhịp đợt đều + đợt nhỏ dày cho tầng watchlist                                                             | M          | Vận hành DSH     |
| Cảnh báo (Teams/email) cho (mã watchlist) ∧ (`time_sensitivity=urgent` ∨ cụm tăng nhanh), khử trùng theo`story_id` | M          | Cụm |
| Bản tin ngày theo user                                                                                            | S–M       | Cụm |
| Thu phản hồi (cột đánh giá được giữ qua các lần ghi → bảng`user_feedback`)                          | M, Cấp 3  | —                 |
| Dòng thời gian theo mã; dashboard                                                                                | M          | Cụm               |
| Hỏi đáp: FTS5 +`sqlite-vec` (bge-m3), lọc metadata trước, trả lời phải trích `article_id`             | L          | ADR thực thể thân bài |

### 5.4 Harness và quản trị

Harness hiện gồm 16 tài liệu, 9 rule, 18 skill, khoảng 60 tệp okf, 15 plan và 7 proposal, cho một người và một lane. `audit` cho health 0.15, nhưng điểm này đo backlog và ADR, không đo chất lượng sản phẩm. H3–H5 phần lớn mới có trên giấy (`agent_metrics` không có dòng nào cho `article-processor`).

| Việc                                                                                                                                                          | Công sức |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Commit nhánh hiện tại thành 2–3 commit; gitignore`project/data/archive/` và `*-DESKTOP-*`                                                            | S          |
| Gỡ lane L1/Gold khỏi`run_daily.ps1`; chuyển ~10 script chết vào archive; sửa `test_cli_entrypoints.py`                                               | M          |
| Sửa cổng proof (`harness_cli.py:294`), `CURRENT_SCHEMA_VERSION`, bỏ `tool-registry` rỗng                                                             | S          |
| Viết lại rule 05, làm sạch rule 08; đóng OPEN-ITEMS lỗi thời; sinh TEST_MATRIX/BACKLOG từ DB; đánh dấu retired cho playbook okf và skill lane cũ | M          |
| Giảm thuế cố định: TINY không cần Closure/trace đầy đủ                                                                                              | S          |
| CI cục bộ: pre-commit`ast.parse` + pytest marker `fast` (bộ đầy đủ 517 test mất 296 giây)                                                         | M          |
| Đổi chỉ số trung tâm của harness sang chất lượng bài giao (từ eval), thay cho entropy quy trình                                                    | M          |

---

## 6. Chi phí: đòn bẩy không cần cổng token

Nhất quán với ADR 0010 ("token là số ghi nhận"), các đòn bẩy dưới đây không đặt trần:

- **Lịch chạy ngoài giờ cao điểm.** Theo trang giá DeepSeek (agent nghiên cứu đọc ngày 24/09), deepseek-flash có giá cao điểm gấp đôi trong khung 08:00–11:00 và 13:00–17:00 giờ Việt Nam, ngày làm việc. Chạy đợt trước 08:00, trong khoảng 11:00–13:00 hoặc sau 17:00 sẽ giảm khoảng một nửa chi phí. **Cần kiểm lại trang giá trước khi đổi lịch.**
- **Tiền tố giống hệt từng byte giữa các lô**, ghi `prompt_cache_hit_tokens` và `prompt_cache_miss_tokens` vào sổ cái.
- **Gom cụm trước pack.** Chỉ phân tích bài đại diện, các bài còn lại gắn làm nguồn xác nhận.

---

## 7. Lộ trình đề xuất

| Giai đoạn                | Nội dung                                                                                                                                                                                          | Cấp  |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| **0 — tuần này**  | Commit nhánh; gitignore; vá L1 (dedup); gỡ lane cũ khỏi`run_daily.ps1`; khởi động lại `morninger`; sửa few-shot (L4) và trích dẫn bù (L5); gom đường dẫn ra khỏi OneDrive   | 1–2  |
| **1 — 2–3 tuần**  | Golden set +`eval_article.py` + `agent_metrics`; **ADR thực thể thân bài** (phân tuyến theo thân bài, prefix_hash/model); vá L6; sắp lại xlsx; nhịp đợt đều | 2 + 3 |
| **2 — 1–2 tháng** | Gom cụm câu chuyện +`story_id`; verifier lấy mẫu + evaluator-optimizer 1 vòng; bản tin ngày; đợt nhỏ cho tầng watchlist + cảnh báo; `capture_daily`                              | 2     |
| **3 — sau đó**    | Nguồn có cấu trúc (CBTT sở, NSO);`entity-curator` có người duyệt; cascade model (sửa ADR 0009 D6); RAG FTS5 + vector; vòng phản hồi user; `harness-auditor`; tinh gọn harness    | 2 + 3 |

**Liên hệ với các đề xuất đang treo:**

- *JEV Spike 0* (kiểm `cite_k`, `ent_<mã>`) cần chính golden set của giai đoạn 1 để hiệu chỉnh. Làm golden set trước thì phục vụ được cả hai.
- *AGY* (runner thay DSH) chỉ nên A/B khi đã có eval. Nếu không, không có thước đo nào để so.
- *US-028* (dọn nợ registry cho `adversarial-dod-verifier`; `materiality-triage` đã retired) đi trước ADR thực thể thân bài.

---

## 8. Không nên làm (bài học từ ADR 0003–0010)

1. **Không thêm cổng, trần hay bộ lọc mới khi chưa có số đo.** Chu kỳ "dựng cổng rồi gỡ cổng" đã lặp 5 lần. Mọi kiểm tra mới mặc định *chỉ báo cáo*.
2. **Không để script thay việc của LLM.** Chuyện này đã xảy ra 3 lần: regex Gold, code-first bị coi là đã phân tích, trần chắt lọc. Vá L3 và L5 cũng đi theo tinh thần này: đừng để code cắt bỏ hay thay thế đầu ra của mô hình.
3. **Không tin exit code.** Mọi runner mới (agy, Jev) phải có bộ phân loại lỗi riêng. `l1_ingest.py:94` và `agent_ingest.py:75` luôn `return 0`.
4. **Không để lane cũ chạy song song "để quay lui".** L10 là bằng chứng.
5. **Không đặt số ADR hay số story trước trong đề xuất.** Cấp số từ `harness.db` lúc intake.

---

## 9. Quyết định cần người

| #  | Quyết định                                                             | Ghi chú                                                                                    |
| -- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| H1 | Commit toàn bộ US-025…027                                              | Đang chặn WIP=1 cho mọi việc sau                                                        |
| H2 | Mở ADR đưa thực thể thân bài vào phân tuyến | Cấp 3; tăng recall giao hàng |
| H3 | Dành 6–10 giờ công analyst gán nhãn golden set                      | Dùng chung cho eval nội bộ và JEV Spike 0                                               |
| H4 | Chạy backlog 2.915 bài 10–17/09 hay không                             | Quyết định vận hành                                                                    |
| H5 | Chuyển lịch đợt ra ngoài giờ cao điểm                             | Kiểm lại trang giá trước                                                               |
| H6 | Thứ tự so với AGY / JEV / US-028                                       | Đề xuất: H1 → US-028 → giai đoạn 0 → golden set → ADR thực thể thân bài → JEV Spike 0 → A/B AGY |

## Nguồn ngoài chính

- https://www.anthropic.com/engineering/building-effective-agents
- https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf
- https://hamel.dev/blog/posts/llm-judge/ · https://hamel.dev/blog/posts/evals-faq/
- https://api-docs.deepseek.com/quick_start/pricing/ · https://api-docs.deepseek.com/guides/kv_cache/
- https://arxiv.org/pdf/2402.10302 (gom cụm tin và độ khẩn) · https://arxiv.org/pdf/2501.02237 (NER tài chính bằng LLM)
- https://arxiv.org/pdf/2404.10774 (MiniCheck, kiểm neo)
