# ADR 0017 — Hợp đồng đầu ra Article Lane thống nhất cho mọi provider

- **Loại tài liệu:** giải thích (explanation), ghi lại một quyết định.
- **Ngày:** 2026-10-05
- **Trạng thái:** accepted
- **Lane:** high-risk (sửa Data Contract của `article-processor`, sửa runner và expander)
- **Story:** US-034
- **Kế thừa:** ADR 0009 D6 (nay không còn đúng vì không phải mọi model là `deepseek-flash`), ADR 0010, ADR 0011. Không đổi lược đồ mở rộng `agent-output-v2-lean` và `l1-entity-output-v1`.
- **Người duyệt:** người vận hành, 2026-10-05. Hard Gate đã mở.

## 0. Tham số đã chốt (2026-10-05)

| Tham số | Giá trị |
|---|---|
| Số chỉ số `c` | 2 đến 4 |
| Kích thước lô chuẩn | 50 |
| Provider chuẩn đo bộ vàng | agy (`gemini-3.8-flash-low`) |
| Ngưỡng khớp bộ vàng | Tạm thời: provider khác đạt từ mức agy đo được trên bộ vàng trừ 5 điểm phần trăm ở `sn`, `ts` và tập TIC. Số cụ thể chốt sau lần đo agy đầu tiên (D7). |
| `claude` | Chưa đưa vào lane. Không thêm `--runner claude` ở D6. |

> ADR đã `accepted` không sửa nội dung. Muốn đổi thì lập ADR mới.

## 1. Bối cảnh

Article Lane chạy với nhiều provider: agy (gemini-3.8-flash-low), OpenRouter, opencode (Muse Spark), DSH (deepseek-flash). Cùng một bài nhưng đầu ra khác nhau. Audit ngày 2026-10-05 có ba hướng: hợp đồng và cổng kiểm, prompt và runner, đo thực nghiệm trên 467 tệp đầu ra. Kết quả cho thấy nguyên nhân là cấu trúc, không phải một model cụ thể.

**Bằng chứng 1. Record gọn `{i,e,s,k,im,sn,ts,c}` không có nguồn chân lý.** Không có JSON Schema, pydantic hay module hằng số cho record này. Nó tồn tại rời rạc ở `build_article_prefix.py`, `article_expand.py`, `agy_runner.py`, `openrouter_runner.py`, `opencode_native_run.py`, `intent_resolve.py`. Hai schema mở rộng có tệp thật nhưng chỉ kiểm đầu ra của expander, vốn đúng theo cấu trúc, nên không kiểm được model.

**Bằng chứng 2. Bốn bộ phân tích JSON và ba validator, mức nghiêm khác nhau trên cùng một đầu ra.**

| Đường | Phân tích | Kiểm |
|---|---|---|
| agy | `salvage_json_records`, lỗi cắt cụt thì mất cả lô | từ chối theo `c` và nhóm; không kiểm enum, độ dài `im`, số `k` |
| openrouter | tha thứ nhất, cứu từng đối tượng | tự sửa: bịa chữ đệm vào `im`, map `sn` theo chuỗi con, điền `c` thiếu, nhận khoá đồng nghĩa |
| opencode | không phân tích | nghiêm nhất: đủ 8 khoá, `k` 2-4, `im` từ 40 ký tự, enum đúng |
| DSH | không kiểm trước | chỉ `article_expand.salvage_records` |

**Bằng chứng 3. Cổng chung `article_expand.py` im lặng gán giá trị mặc định.** Cụ thể: `sn` sai thành `neutral`; `ts` sai thành `this_week` (openrouter lại mặc định `today`). `c` ít hơn 2 chỉ số hợp lệ thì tự điền các đoạn đầu. `k` kiểu chuỗi bị tách thành từng ký tự và không có giới hạn tối đa 4. `c` trùng sinh trích dẫn trùng. Chỉ số `c` 1-based lệch mọi trích dẫn mà không báo lỗi. Độ lệch giữa provider vì vậy bị che đi, không bị đo.

**Bằng chứng 4. Số đo độ lệch (đầu ra thật, tỷ lệ theo record).**

| Lớp lệch | agy | openrouter | opencode | DSH cũ |
|---|---|---|---|---|
| Thiếu id (lô PARTIAL) | 623 id, 43/124 lô | 299 id, 33/79 lô | 0 | không đo được |
| `c` dưới 2 chỉ số hợp lệ (bị đệm im lặng) | 5,5% | 1,3% | 1,2% | 10 record |
| `c` dài bất thường | tối đa 9 | tối đa 16, 136 record từ 9 chỉ số | luôn đúng 3 | tối đa 12 |
| `k` lớn hơn 4 | 0 | 9,3% | 0 | 1,4% |
| `k` nhỏ hơn 2 | 1,8% | 0 | 0 | 4 record |
| Cặp thực thể trùng | 1,2% | 1,0% | 0 | 55 cặp |
| TIC sai dạng (`TPBank`, `Vinhomes`) | 14 | 24 | 3 | 50 |
| `ts` ngoài enum | 2 (`year`) | 0 | 0 | 0 |
| `e` rỗng | 0,5% | 1 | 0,8% | 0 |
| Lệch phân phối | `sn` pos 53% | `sn` pos 36% | `ts` month 75%, `c` luôn 3 | khác lược đồ thực thể |

Hai điều rút ra. Một: lệch cấu trúc JSON là thiểu số. Chi phí lớn nhất là lô thiếu id (cắt cụt, trần đầu ra OpenRouter 24000 token) và độ lệch về kích thước danh sách. Hai: các đợt DSH cũ (W09241605, W09241723, W365, W1, W2) dùng lược đồ thực thể khác hẳn. 2988 cặp không resolve được dưới resolver hiện tại.

**Bằng chứng 5. Quy trình và tài liệu mâu thuẫn.**

- Khung prompt người dùng không chung. agy thêm khối "QUY TẮC BẮT BUỘC" và tiêu đề `## Packet`. openrouter đóng gói lại packet thành `{d,n,a}`. DSH gửi nguyên văn tệp packet.
- Lấy mẫu không chung: openrouter `temperature 0.1`, `max_tokens 24000`, `reasoning minimal`; DSH `reasoning off`; agy không đặt gì. Không provider nào đặt seed.
- Prefix tự mâu thuẫn. Ví dụ phát ra thực thể không nằm trong văn bản, trong khi luật bắt buộc nguyên văn. Ví dụ có record `k` một mục, trong khi luật là 2-4. Prefix cấm code fence, trong khi expander và tài liệu opencode kỳ vọng có fence.
- `registry.yaml` ghi `article-processor` dùng skill `l1-entity-matcher` (lane đã ngừng) và xuất hai tên schema mà prefix không phát ra. AGENTS.md ghi mọi model là `deepseek-flash`, trái với agy, OpenRouter, opencode và mặc định daemon là agy.
- `agent-runner-prompt.md` và `agent-prompting-guide.md` (đã lưu trữ) dạy agent tự đọc packet, ghi một tệp mỗi bài, báo cáo "đã ghi tệp", nêu `materiality` và `impact_area`. Đây là hợp đồng ngược với Article Lane. Không có đường chạy `claude` trong mã, nên agent kiểu Claude chỉ có hai tài liệu này để theo.
- Meta provenance sai. Expander mặc định `dsh/deepseek-flash` khi thiếu meta. Sổ cái token chỉ gắn `--source agy` cho agy, nên chi phí openrouter và opencode bị gán sai nguồn. `cmd_analyze` rơi về agy với mọi runner khác openrouter.

**Giới hạn phải nói thẳng.** "Giống nhau" không thể là giống từng ký tự giữa các model. Tóm tắt, `sn` và danh sách thực thể là phán đoán ngôn ngữ, nên hai model khác nhau sẽ khác nhau. ADR này đảm bảo tất định ba điều. Một: hình dạng và dạng chuẩn của đầu ra. Hai: mọi lệch đều bị phát hiện và vào vòng vá. Ba: mức đồng thuận ngữ nghĩa giữa provider được đo bằng bộ vàng.

## 2. Quyết định

### D1. Một nguồn chân lý cho record gọn

Tạo `project/schemas/article-compact-v2.schema.json` (JSON Schema) và một module duy nhất `project/src/agent/article_contract.py` đọc schema này, xuất ra hằng số (nhóm thực thể, enum, giới hạn). Ba nơi sau chỉ được **sinh** từ nguồn này, không chép tay: prefix (`build_article_prefix.py`), validator, bảng đổi `sn`/`ts` của expander. Test `test_article_contract_sync.py` chặn lệch, theo mẫu `test_pipeline_spec.py`.

### D2. Luật đóng cho từng trường

| Trường | Luật cứng |
|---|---|
| `i` | số nguyên, có trong packet, duy nhất, thứ tự tăng dần |
| `e` | mảng cặp đúng 2 phần tử `[bề mặt, MÃ_NHÓM]`, mã nhóm thuộc 11 mã, không trùng (so khớp không phân biệt hoa thường), mảng rỗng hợp lệ |
| `s` | chuỗi, 1 đến 3 câu |
| `k` | mảng chuỗi, **đúng 2 đến 4 mục**, không có mục trùng trích dẫn |
| `im` | chuỗi từ 40 ký tự, không sao chép nguyên văn |
| `sn` | đúng `pos`, `neg`, `neu` |
| `ts` | đúng `urg`, `today`, `week`, `month`, `arch` |
| `c` | mảng số nguyên **0-based**, không trùng, tăng dần, trong `[0, n_đoạn)`, từ 2 đến 4 chỉ số (con số 4 chờ người vận hành chốt) |
| khoá lạ | bị từ chối, không bỏ qua |

Ngôn ngữ của `s`, `k`, `im` là tiếng Việt, ghi vào prefix.

### D3. Cấm sửa ngầm

Cấm mọi mặc định ngữ nghĩa. Không `sn` sai thành `neutral`, không `ts` sai thành `this_week` hay `today`, không tự điền `c`, không đệm `im`, không nhận khoá đồng nghĩa, không tách `k` kiểu chuỗi. Record vi phạm bị loại khỏi lô và vào `--repair` kèm mã lỗi. Chỉ cho phép hai nhóm chuẩn hoá cơ học, đều ghi vào meta thành bộ đếm:

1. Bóc vỏ truyền tải: envelope của vendor, code fence, văn bản trước `[`, cứu từng đối tượng khi cắt cụt.
2. Dạng chuẩn do mã quyết định, không do model: `c` sắp tăng dần, `e` sắp theo (thứ tự nhóm, bề mặt), `k` giữ thứ tự model. Việc này cơ học, không thay thế phán đoán LLM nên không vi phạm mục C của AGENTS.md.

### D4. Một hàm phân tích và kiểm duy nhất

`article_contract.parse_and_validate(text, packet) -> (records_hợp_lệ, lỗi_theo_id, bộ_đếm_vỏ)`. Gọi từ agy, openrouter, opencode, conductor DSH (qua bước hậu kiểm của `article_run.py`) và expander. Xoá `agy_runner.validate_records`, `openrouter_runner.validate_records`, hai `salvage_json_records`, `ENTITY_GROUP_MAP` và các bản chép `VALID_ENTITY_GROUPS`. Expander chỉ nhận record đã qua hàm này, nên gỡ các nhánh mặc định của nó.

### D5. Một khung đầu vào, một bộ tham số

- Một hàm `build_user_message(packet)` duy nhất; không agy-guard riêng, không đóng gói lại packet. Mọi provider nhận cùng byte.
- Prefix hệ thống một tệp (đã có), thêm SHA256 vào meta. Bản dán tay trong `agent.cordis.yml` tiếp tục bị `--check` chặn lệch.
- Tham số chuẩn: `temperature 0`, seed cố định nếu provider hỗ trợ, không `reasoning` hoặc mức thấp nhất. `max_tokens` bằng trần của provider. Đó là giới hạn truyền tải để tránh cắt cụt, không phải trần token theo quy tắc "token là ghi nhận". Provider không hỗ trợ tham số nào thì ghi rõ vào meta.
- Meta bắt buộc mỗi lô: `provider`, `model`, tham số lấy mẫu, SHA256 prefix, phiên bản hợp đồng. Thiếu meta thì `--finish` thất bại; bỏ mặc định `dsh/deepseek-flash` của expander; sổ cái gắn nguồn theo meta.
- Kích thước lô một giá trị chuẩn cho mọi provider (đề xuất 50, theo daemon). Chênh lệch theo provider chỉ khi có số đo và ghi vào `ops.yaml`.

### D6. Quy trình một vòng đời, provider chỉ là bộ chuyển vận

Mọi provider đi cùng đường: `pack` → `run` (adapter chỉ làm việc gửi và nhận) → `parse_and_validate` → `repair` → `expand` → `--finish`. Giao diện adapter: `run_batch(packet_text) -> raw_text`. Opencode và agent kiểu Claude đi qua `append_records` vào đúng hàm của D4, không có validator riêng. Thêm `--runner` cho `opencode` và `claude` vào `article_run.py`, và sửa `cmd_analyze` để runner lạ báo lỗi thay vì rơi về agy.

### D7. Cổng cho provider hoặc model mới (bộ vàng)

Một bộ vàng gồm 30 bài cố định, nhãn bởi người vận hành qua màn duyệt mẫu S-13, cùng lệnh `python scripts/provider_conformance.py --runner <r> --model <m>`. Provider hoặc model chỉ được vào lane khi đạt ba điều kiện. Một: tỷ lệ record vi phạm cấu trúc bằng 0 sau bóc vỏ. Hai: không thiếu id. Ba: độ khớp nhãn vàng ở `sn`, `ts` và tập TIC đạt ngưỡng đã chốt. Kết quả ghi thành bản kiểm ở `docs/templates/validation-report.md`. Lệnh này tiêu token nên chỉ chạy khi có model mới, không chạy mỗi đợt.

### D8. Dọn mâu thuẫn tài liệu và cấu hình

- Sửa prefix: ví dụ phải tuân đúng luật (thực thể nằm trong văn bản, `k` 2-4 mục). Thống nhất chính sách code fence: cấm, và vẫn bóc nếu có.
- Sửa `registry.yaml` cho `article-processor`: skill hiện hành, schema đầu ra là record gọn, `model` theo cấu hình thật.
- Sửa AGENTS.md mục 6.A: "mọi model là deepseek-flash" thành danh sách provider được phép theo bộ vàng.
- Đưa `agent-runner-prompt.md` và `agent-prompting-guide.md` ra khỏi đường đọc của agent bằng banner thu hồi kèm đường dẫn tới hợp đồng mới. Hai tài liệu này trái hợp đồng hiện hành.
- Luật mới `.agents/rules/11-hop-dong-dau-ra-thong-nhat.md` tóm tắt D1 đến D7 thành bất biến cấp dự án. Chỉ viết sau khi ADR được duyệt.

### D9. Đợt cũ

Năm đợt DSH cũ giữ nguyên ở Bronze và DB, đánh dấu `contract=legacy` trong báo cáo, không tái mở rộng. Không xoá.

## 3. Phương án đã loại

| Phương án | Lý do loại |
|---|---|
| Ép mọi provider dùng một model | Không bảo đảm được: free tier hết hạn, giá khác nhau, người vận hành đã chọn đa provider. |
| Giữ expander mặc định và thêm validator thứ tư | Thêm một bản chép nữa vào bốn bản đã lệch nhau. |
| Dùng structured output của từng provider | Không provider nào trong lane đang dùng, hỗ trợ không đồng đều (agy CLI, opencode phiên sống). Có thể bổ sung sau như lớp phụ, không thay D4. |
| Dùng regex hoặc heuristic để sửa đầu ra sai | Vi phạm mục C AGENTS.md; sửa ngầm chính là nguyên nhân che độ lệch. |
| Đặt trần số bài hay token để giảm cắt cụt | Trái quy tắc "token là ghi nhận, không phải cổng". |

## 4. Hệ quả

**Được:**

- Một chỗ sửa hợp đồng; test chặn lệch giữa prompt, validator và expander.
- Độ lệch giữa provider hiện ra thành số đo và hàng đợi vá, không bị che bởi giá trị mặc định.
- Provider mới có cổng vào rõ ràng, có số đo.
- Provenance và chi phí gán đúng nguồn.

**Phải chấp nhận:**

- Tỷ lệ record bị từ chối tăng trong thời gian đầu (agy: khoảng 5,5% `c` ngắn, 1,8% `k` ngắn; openrouter: 9,3% `k` dài; trước đây bị che). Giảm bằng vòng `--repair` có sẵn, và chỉnh prefix cho đúng các điểm lệch đã đo.
- Chi phí token thêm cho vòng vá. Ghi nhận, không phải cổng.
- Sửa nhiều tệp trên đường chạy tới hạn; cần cửa sổ không có đợt mở song song với daemon.
- Bộ vàng phụ thuộc công gán nhãn của người vận hành.

## 5. Quay lui

Mỗi bước D1 đến D8 là một commit riêng, hoàn tác bằng `git revert`. Cờ `contract.strict: false` trong `ops.yaml` trả expander về hành vi cũ trong thời gian chuyển tiếp (người vận hành bật). Chỉ người vận hành được tắt cổng bộ vàng.

## 6. Việc theo dõi

- [ ] Người vận hành duyệt ADR; chốt giới hạn `c` (2 đến 4 hay khác), kích thước lô chuẩn, ngưỡng khớp bộ vàng.
- [ ] Mở story. Thứ tự đề xuất: D1 và D4, D3, D5, D2 và D8, D6, D7.
- [ ] Hỏi người vận hành: dùng provider nào làm bản chuẩn đo bộ vàng, và có đưa `claude` vào lane hay không.
- [ ] Tái đo độ lệch sau D3 bằng đúng kịch bản của audit này để so trước và sau.
- [ ] Rà `src/agent/packet.py`, `batch_handoff.py`, `dod.py` còn hằng số v1 (nằm ngoài phạm vi ADR này, ghi vào `OPEN-ITEMS.md`).

## 7. Điều chỉnh khi thi công

Các điều chỉnh sau đã áp dụng ở US-034. Chúng không đổi hướng của quyết định.

- **D2, `e` và `c` trùng:** mã chuẩn hoá cơ học (bỏ phần tử trùng, sắp thứ tự) và ghi bộ đếm, thay vì từ chối record. Lý do: trùng không đổi nghĩa, từ chối sẽ đẩy cả bài vào vòng vá. Số chỉ số `c` được tính sau khi bỏ trùng.
- **D2, `s` 1 đến 3 câu:** chỉ cảnh báo bằng bộ đếm `warn_summary_sentences`, không từ chối. Lý do: chữ viết tắt tiếng Việt như "TP. Hồ Chí Minh" làm bộ đếm câu bằng dấu chấm đếm sai.
- **D2, `c` và đoạn ngắn:** chỉ số trỏ vào đoạn dưới 20 ký tự bị từ chối. Khi bài có ít hơn hai đoạn đủ dài thì số chỉ số tối thiểu giảm theo số đoạn đó.
- **D2, kiểm dấu tiếng Việt:** giữ kiểm tra `lost_diacritics` vốn có ở agy và đưa vào bộ kiểm chung.
- **§5, cờ `contract.strict`:** không thực hiện. Quay lui bằng `git revert` từng commit.
