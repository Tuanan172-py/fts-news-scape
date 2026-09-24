# Position 2: Jev làm lớp kiểm định và định tuyến sau LLM

Lập trường: Jev đứng **sau hoặc song song** `article-processor`, làm bộ phân loại độc lập thứ hai. Jev không thay mô hình, không chặn bài, không chặn `--finish`. Nhãn: [S] có nguồn, [V] kiểm tại máy, [I] suy luận.

## 1. Luận điểm chính
1. Jev không sinh văn bản, nên không thay được tóm tắt, hàm ý, trích dẫn hay trích thực thể mở [S docs.typesafe.ai/introduction/coding-agents.md]. Trong khi đó "đọc trạng thái, trả xác suất có kiểu" đúng là việc của một bộ kiểm định.
2. Pipeline hiện chỉ có kiểm tất định: DoD đúng schema và độ phủ ≥ 90% [V AGENTS.md §6B]. Chưa có kiểm ngữ nghĩa. `adversarial-dod-verifier` vẫn là `status: draft` [V .agents/registry.yaml:323-333].
3. Để deepseek-flash tự kiểm chính deepseek-flash thì lỗi tương quan. Jev là một họ mô hình khác (transformer một lượt, RLCD), nên lỗi của nó ít trùng hơn [S Wikipedia Jev; I về mức độ độc lập].
4. Materiality hiện luôn bằng 0 khi giao hàng: `_sort_key` đọc `materiality.score`, còn output lean không có trường này [V src/export/user_output.py:287-297]. Người dùng đang nhận bảng không có điểm quan trọng nào đã hiệu chuẩn.
5. Chi phí gần bằng 0 và hầu như không thêm độ trễ. Vì vậy câu hỏi chỉ còn là chất lượng tiếng Việt và governance, không còn là tiền [S docs.typesafe.ai/models.md; I].

## 2. Kiến trúc đề xuất
**Vị trí.** Thêm một bước Python ở terminal: `scripts/jev_verify.py --wave <mã>`. Bước này chạy **sau** `article_run.py --finish` và **trước** `write_user_output.py`.
- **Không đặt trong `run_code` của DSH.** Worker có môi trường rỗng, nên key phải nhúng vào mã và sẽ rơi vào session log JSONL [V research C]. Protocol `systemone` cũng không khớp adapter `dsh-llm-pi-ai` [I].
- **Không có bước nào trong phiên điều phối.** Luật "một đợt = một `run_code`" giữ nguyên.
- **agy runner (nếu được duyệt):** gọi đúng script này như một bước con, cùng hợp đồng I/O. Không cần code riêng cho từng runner.
- **Key** đọc từ `TYPESAFE_API_KEY` trong biến môi trường người dùng, không bao giờ nằm trong kho mã hay preset.

**Đầu vào (chỉ đọc).** Với mỗi bài của đợt, script đọc ba nguồn:
- đoạn văn Silver (nguyên văn);
- bản ghi `l1-entity-output-v1`;
- bản ghi `agent-output-v2-lean`.

Script dùng một request mỗi bài: `state` = tiêu đề + đoạn văn đánh số (≤ 32k token), `model` ghim `jev-1.13.0` [S models.md khuyên ghim]. Ở pha shadow, đầu ra ghi vào `data/qa/jev/<mã>.jsonl`. Pha sản xuất mới dùng bảng riêng `jev_verdicts(article_id, wave, question_id, answer, probs_json, confidence, model_returned, option_order_hash, ts)`, và thay đổi đó là Tier 3. Script không bao giờ ghi đè `agent_outputs`.

**Bộ câu hỏi mỗi bài (khoảng 8–20 câu, chạy song song trong một request)** [S api.md]:
| ID | Kiểu | Kiểm gì | Ghi chú |
|---|---|---|---|
| `cite_k` | Choice `supports / contradicts / says_nothing / unknown` | Đoạn trích k có đỡ câu hàm ý/tóm tắt không | Mẫu "citation check" [S research B]. Mỗi câu hỏi nhắc lại nguyên văn claim |
| `ent_<mã>` | Noul | Bài có thực sự nói về mã X (chủ thể, không chỉ nhắc qua) | Chỉ hỏi các mã LLM đã trả về. Tránh trần 255 option vì không hỏi danh mục mở |
| `sent` | Choice `tích cực / trung tính / tiêu cực / không rõ` | Đối chiếu với `sn` | Luôn có lựa chọn "không rõ": thiếu nó, KoBBQ rơi từ 95% về 0% [S research B] |
| `mat` | Score 5 mức, mỗi mức có `what / not_for / examples` | Materiality độc lập | Mô tả mức theo [S primitives/advanced.md] |
| `inj` | Noul | State có chứa chỉ thị nhắm vào mô hình không | Cờ phụ để phát hiện injection [I] |

**Định tuyến theo độ tin cậy** [I, ngưỡng lấy từ spike, không đoán trước]:
- **Đồng thuận:** Jev khớp LLM và `confidence ≥ τ_hi`. Gắn `verified`, không làm gì thêm.
- **Bất đồng:** Jev ngược LLM với `confidence ≥ τ_hi`, hoặc có `cite_k = contradicts`. Gắn `flag` và đưa vào hàng đợi `data/qa/jev/<mã>.escalate.json`. Cách xử lý theo thứ tự:
  1. `adversarial-dod-verifier` (flash) đọc lại bài và phán xử;
  2. nếu vẫn tranh chấp, chuyển người xem.
  3. **Không ai tự sửa nhãn.**
- **Jev không chắc:** `confidence < τ_lo`. Gắn `uncertain`, không leo thang, chỉ thống kê.
- **Giao hàng:** Excel thêm cột chỉ đọc `jev_flag` và `jev_materiality`. Việc dùng `jev_materiality` làm khoá phụ trong `_sort_key` phải có quyết định trong ADR. Đây chỉ là sắp **thứ tự**, không lọc bài, nên hợp §6B.
- **Giám sát drift:** theo dõi hàng ngày tỉ lệ `flag` và độ lệch phân phối `sent` / `mat` giữa Jev và LLM. Tỉ lệ flag nhảy ±2σ so với trung bình 14 ngày là tín hiệu cho một trong ba nguyên nhân: prompt/model DeepSeek đổi, nguồn tin đổi, hoặc Jev đổi phiên bản [I].

**Fallback khi Jev lỗi hoặc không có.** Lỗi 429/529 được thử lại có backoff 3 lần. Lỗi 401/422 hoặc mất mạng làm đợt được ghi `jev_status=skipped`, nhưng `write_user_output.py` vẫn chạy bình thường với cột trống. Jev **không bao giờ** là điều kiện thoát 0 của `--finish` hay của bước giao hàng. Nếu vendor ngừng dịch vụ, dự phòng dài hạn là AnyJev (Apache-2.0, cùng giao diện choice/noul/score) hoặc Laya chạy cục bộ [S research A/B].

## 3. Lợi ích dự kiến (có số)
- **Chi phí.** Mỗi bài tốn khoảng 3k token state và 2k token câu hỏi, tức 5k input. 350 bài/ngày là 1,75M token, nhân $0,042/1M ra khoảng **$0,07/ngày**. So với chi phí Article Lane hiện tại khoảng $0,28–0,56/ngày, phần thêm là khoảng 13–25% [S giá; I khối lượng từ research C]. Theo ADR "Token là ghi nhận", con số này chỉ ghi vào sổ cái, không đặt trần.
- **Độ trễ.** Trung vị 256 ms mỗi request [S blog]. Chạy 350 request với 10 luồng song song mất khoảng 10–20 giây mỗi ngày, dưới mức 1.200 req/phút [I].
- **Chất lượng (giả thuyết, chờ spike xác nhận):**
  - bắt được phần lớn các trích dẫn không đỡ claim, là loại lỗi hiện không ai kiểm;
  - có điểm materiality đã hiệu chuẩn thay cho giá trị luôn bằng 0;
  - rút phạm vi xem lại của người về 5–15% số bài bị flag, thay vì lấy mẫu ngẫu nhiên [I].
- **So với phương án tự kiểm bằng deepseek-flash.** Một lượt kiểm bằng flash tốn khoảng bằng lượt phân tích, cỡ $0,3–0,5/ngày, và lỗi tương quan với chính lượt phân tích [I]. Jev rẻ hơn khoảng 4–7 lần và độc lập hơn. Đổi lại, Jev yếu hơn ở tiếng Việt, và điểm yếu này phải đo, không được giả định.

## 4. Rủi ro và cách giảm
| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Tiếng Việt chưa có số liệu. Tiếng Nga mất 11 điểm, ECE tăng gấp đôi [S research B] | Cao | Spike là cổng kill. Hiệu chuẩn lại bằng isotonic trên nhãn riêng |
| Confidence quá tự tin: ECE 0,107, đúng 44,7% dù báo p≈0,74 [S research B] | Cao | Không dùng confidence thô. Ngưỡng τ học từ golden set |
| Prompt injection: độ chính xác rơi từ 96,5% về 26,5% [S VentureBeat] | Trung bình | Jev chỉ **gắn cờ**, không có quyền hành động. Có câu `inj`. Tin tức là nội dung bên ngoài nên coi là nguồn thù địch |
| Thứ tự option làm đổi đáp án [S pydantic] | Trung bình | Ghi `option_order_hash`. Spike đo độ ổn định khi hoán vị |
| Jev yếu với số và ngày [S jaggedness] | Trung bình | Không hỏi Jev về con số (EPS, % tăng). Việc đó để DoD tất định |
| Vendor mới 9 ngày tuổi, giá và rate limit có thể đổi, alias `latest` tự trôi | Trung bình | Ghim `jev-1.13.0`. Bước này là tuỳ chọn, bỏ đi không làm gãy pipeline |
| Gửi nội dung tin ra API ngoài, chính sách retention chưa rõ [S legal.md] | Trung bình | Chỉ gửi tin công khai đã cào, không gửi watchlist hay dữ liệu người dùng. Cần xác nhận ToS trước |
| Làm mờ ranh giới No Script Emulation | Thấp | Jev là mô hình. ADR định nghĩa lớp `typed-verifier` riêng |

## 5. Governance
- **Intake.** Tier 3 HIGH-RISK vì có provider mới và API token mới [V AGENTS.md §0]. Ngay cả spike cũng cần key, nên phải qua Hard Gate: tạo story `status: blocked`, người duyệt riêng quyết định "cho phép shadow eval".
- **ADR-0011** "Jev làm bộ kiểm định có kiểu sau Article Lane" (số 0010 đã dùng). Nội dung ADR:
  1. sửa ADR 0009 D6 thành "mọi model **sinh văn bản** là deepseek-flash";
  2. khẳng định Jev không gate, không đếm vào độ phủ, không ghi đè;
  3. quy định lưu và luân chuyển key;
  4. ToS và retention.
- **registry.yaml:**
  - thêm `jev-verifier` với `class: typed-verifier`, là lớp mới cần bổ sung vào taxonomy rule 07 §1, `status: draft` và `activation_gate: Tier-3 ADR-0011`;
  - đổi `adversarial-dod-verifier` thành bước escalate nhận `*.escalate.json`;
  - sửa `materiality-triage` bỏ `stage_role: pre-gold-gate`. Vai trò này đang trái ADR 0010 ngay cả khi không có Jev [V registry.yaml:288-298].
- **pipeline.yaml:** thêm node tuỳ chọn `jev_verify` nằm giữa `finish` và `deliver`, với `on_fail: continue`.
- **Tài liệu và công cụ:**
  - thêm dòng provider vào `docs/TOOL_REGISTRY.md` (degrade ladder: Jev → bỏ qua);
  - thêm giá Jev vào `token_pricing.yaml` và thêm cột `provider` vào `token_ledger`;
  - thêm lệnh `pipeline_radar.py` báo `jev_status` của đợt (Zero-Probe).
- **Proof.** Cần `pytest` cho script, gồm mock HTTP và các trường hợp fallback 429/401, trước khi chuyển story sang done. WIP=1 được giữ.

## 6. Spike (thí nghiệm chứng minh, 3–5 ngày công)
**Golden set: 300 bài đã chạy xong từ W365 và ngày 23/09.**
- 100 bài do chuyên viên FPTS gán nhãn sentiment, materiality 1–5 và cặp (trích dẫn, claim) đỡ hoặc không đỡ.
- 200 bài còn lại dùng nhãn DeepSeek làm đối chứng về mức đồng thuận.
- Sinh thêm negative tổng hợp:
  - hoán đổi trích dẫn giữa các bài (khoảng 300 cặp sai chắc chắn);
  - gắn mã CP của bài khác vào bài (khoảng 200 cặp).

Chạy offline, không ghi DB, key riêng. Chi phí dự kiến < $0,10 [I, theo mức beri.net: 5.721 call hết $0,176].

| Chỉ số | Pass (tiếp tục) | Kill (dừng) |
|---|---|---|
| AUROC `cite_k` trên negative tổng hợp và nhãn người | ≥ 0,85 | < 0,70 |
| AUROC `ent_<mã>` (mã gắn sai) | ≥ 0,85 | < 0,70 |
| Cohen κ `sent` so với nhãn người, đặt cạnh κ của DeepSeek | ≥ 0,55 và không kém DeepSeek quá 0,1 | < 0,40 |
| Spearman `mat` so với nhãn người | ≥ 0,45 | < 0,25 |
| ECE sau hiệu chuẩn isotonic (5-fold) | ≤ 0,08 | > 0,15 |
| Precision của `flag` (người xác nhận là lỗi thật) | ≥ 50% | < 30% |
| Tỉ lệ flag trên bài thật | 3–20% | > 35% (gây nhiễu) |
| Độ ổn định khi hoán vị option / chạy lại 3 lần | ≥ 90% đáp án giữ nguyên | < 80% |
| Rơi độ chính xác khi chèn câu injection vào 30 bài | ≤ 10 điểm | > 25 điểm |

Kết quả cho phép chọn từng câu hỏi riêng: ví dụ giữ `cite_k`, bỏ `mat`. Nếu mọi câu hỏi đều ở vùng kill thì thử AnyJev (Qwen3-8B cục bộ) trên cùng golden set trước khi kết luận.

## 7. Bằng chứng khiến tôi đổi lập trường
- AUROC tiếng Việt < 0,70 cho citation check và entity check. Khi đó Jev thêm nhiễu, không thêm tín hiệu.
- Một lượt deepseek-flash tự kiểm, dù tương quan lỗi, có precision flag cao hơn Jev ≥ 15 điểm với chi phí chấp nhận được. Khi đó độc lập không đáng giá.
- ToS hoặc retention không cho gửi nội dung ra ngoài, hoặc FPTS không chấp nhận xử lý dữ liệu ở region không rõ.
- Flip-rate khi chạy lại cùng input > 10%, tức là không tất định. Khi đó không dùng được để giám sát drift.
- Tỉ lệ flag thật trên W365 < 1%, tức LLM đã đủ tốt. Khi đó chi phí governance Tier 3 lớn hơn lợi ích.
