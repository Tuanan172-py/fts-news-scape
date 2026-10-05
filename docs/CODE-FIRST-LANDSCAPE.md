# CODE-FIRST LANDSCAPE — bối cảnh trước khi phát triển lớp nhận diện tất định

- **Lập ngày:** 2026-09-21
- **Mục đích:** một bản đồ duy nhất cho câu hỏi "lớp code-first đang ở đâu, làm gì, hỏng ở đâu,
  còn dư địa nào" — đọc trước khi chạm vào bất kỳ dòng mã nào.
- **Phạm vi:** tầng nhận diện thực thể tất định (0 token) và mọi điểm nó chạm vào pipeline.
  Không bàn scraper, không bàn phần ngữ nghĩa của tầng Gold.
- **Quy ước:** mọi con số trong tài liệu này được đo trực tiếp ngày lập, không ước lượng.
  Lệnh tái lập ở §8. Phần suy luận được ghi rõ là suy luận.

---

## 1. Bản đồ codebase trong một trang

Kho gồm hai nửa: **sản phẩm** ở `project/` và **harness** ở `docs/` + `.agents/` + `scripts/`.

```
Bronze (raw_html + meta)  ->  Silver (DOM sạch, cleaned_text, work_package)
        |
   +--------------------------- hai tuyến song song, cùng đích ---------------------------+
   |                                                                                      |
   |  TUYẾN L1 RỜI (cũ, đang chạy tự động)        TUYẾN ARTICLE LANE (mới, 18/09)          |
   |  l1_route.py  -> l1_tasks (route)            article_pack.py  -> packet gộp           |
   |    +- resolved    -> l1_ingest --code-first    (LLM đọc trọn bài, phát bản ghi gọn)    |
   |    +- needs_agent -> packet -> Subagent L1    article_expand.py -> l1 + gold + mentions|
   |  agent_export/ingest -> Gold riêng           article_run.py    -> một lệnh cả đợt      |
   +--------------------------------------------------------------------------------------+
        |
   l1_outputs (dod_pass=1) JOIN articles  ->  cổng giao hàng  ->  users/output/<user>/<date>.xlsx
```

| Thành phần | Tệp | Vai trò |
|---|---|---|
| Danh mục thực thể | `project/src/agent/entities.py` (570 dòng) | `EntityRegistry`: index alias, `detect()`, các guard chống khớp sai, đăng ký watchlist |
| Phân loại tiêu đề | `project/src/agent/l1_classifier.py` | `classify_title()` cho ra thực thể, ngành, `relevance`, `needs_agent` |
| Định tuyến + DoD | `project/src/agent/l1_router.py` | `route_article`, `build_code_first_output`, `check_l1_dod` |
| Điều phối L1 | `project/src/agent/l1_runner.py` | `route_and_export`, `ingest_code_first`, `drain_code_first`, `ingest_output` |
| Tra cứu cho LLM | `project/src/agent/intent_resolve.py` | `IntentResolver` (LLM nêu tên, script tra định danh), `reconcile()` |
| Xếp tầng ưu tiên | `project/scripts/article_pack.py` | `tier_of()` dùng `reg.detect(title)` để xếp thứ tự chạy |
| Bung bản ghi | `project/scripts/article_expand.py` | dựng `l1-entity-output-v1`, `agent-output-v2-lean`, `*.mentions.json` |
| Lịch tự động | `project/src/morninger.py` | job `l1_route` mỗi 15 phút, kèm bước `l1_ingest --code-first` |

Hợp đồng dữ liệu: `project/schemas/l1-entity-output-v1.schema.json`.
Quyết định nền: [ADR 0003](decisions/0003-code-first-l1-delivery.md) — cho phép ghi kết quả tất định
vào `l1_outputs`; [ADR 0005](decisions/0005-subscriber-gated-gold-va-morphological-l1-guard.md) —
guard hình thái, cổng subscriber, `--review missed`.

---

## 2. "Code-first" không phải một thứ — nó sống ở bốn chỗ khác nhau

Đây là điều dễ gây nhầm nhất khi lên kế hoạch: bốn điểm dưới đây dùng **chung một danh mục**
nhưng **khác luật, khác mục đích, khác hệ quả khi sai**.

| # | Điểm | Đầu vào | Luật áp dụng | Sai thì mất gì |
|:-:|---|---|---|---|
| 1 | **Định tuyến** — `route_article` | tiêu đề | `detect()` đầy đủ guard | Bài bị đẩy nhầm sang Agent (tốn token) hoặc giữ lại nhầm |
| 2 | **Vật chất hoá** — `ingest_code_first` | tiêu đề | `detect()` + DoD + grounding | Giao bài cho sai người dùng, hoặc mất bài |
| 3 | **Xếp tầng** — `tier_of` (Article Lane) | tiêu đề | `detect()` thô, nhận rộng có chủ đích | Chỉ đổi **thứ tự** chạy, không đổi độ sâu — rủi ro thấp nhất |
| 4 | **Tra cứu cho LLM** — `IntentResolver` | chuỗi LLM nêu | khớp fold chính xác trên `canonical_name + aliases`, **không** guard hình thái | Thực thể rơi vào `unlisted`, mất khỏi deliverable |

Điểm 4 là đường tra thứ hai, viết độc lập với `detect()`. Hai đường cùng đọc `entities.json`
nhưng không chia sẻ luật: `IntentResolver._by_type_name` dùng `bucket.setdefault(key, eid)`
(`intent_resolve.py:112-118`), nên **tên trùng giữa hai thực thể bị nuốt lặng, ai vào index trước thì thắng**.

---

## 3. Số đo hiện trạng

### 3.1 Kho dữ liệu vận hành (`C:/data/news-scape/monocle.db`, 21/09)

| Chỉ số | Giá trị |
|---|---|
| `articles` | 12.536 |
| `l1_outputs` đạt DoD | 6.082 — **code_first 3.069 / agent 3.013** |
| `agent_outputs` (Gold) đạt DoD | 470 |
| `l1_tasks` theo tuyến | resolved 4.814 (63,9%) · needs_agent 2.722 (36,1%) |
| `l1_tasks` kẹt | resolved·pending **162** · needs_agent·pending 1.207 · failed **85** |
| Bản ghi L1 của Agent đạt DoD nhưng **0 thực thể** | 1.289 / 3.013 = **42,8%** |
| Phân bố số thực thể mỗi bản ghi code_first | 1 ent: 1.422 · 2: 939 · từ 3 trở lên: 707 · 0: 1 |
| Danh mục | 1.262 thực thể (TICKER 1.093 = tier 1 742 + **tier 2 351**), index 2.611 khoá alias |

### 3.2 Đối chiếu code-first với LLM trên 300 bài thật (đợt W1 + W2 của Article Lane)

`reconcile()` gắn nhãn cho từng định danh: `BOTH` (cả hai tìm ra), `LLM_ONLY`, `CODE_ONLY`.

| Nhãn | Tổng | Riêng TICKER |
|---|---:|---:|
| `LLM_ONLY` | 854 | **403** |
| `BOTH` | 156 | 45 |
| `CODE_ONLY` | 168 | 8 |

> **Code-first bắt được 45/448 = 10,0% số mã chứng khoán mà LLM nêu ra.**
> Nguyên nhân là ranh giới thiết kế, không phải chất lượng matcher: code-first chỉ đọc **tiêu đề**,
> LLM đọc **trọn bài**.

`CODE_ONLY` tập trung ở nhóm ngành và tài sản (`IND_GICS2` 50, `IND_GICS3` 35, `ASSET_CLASS` 30,
`IND_GICS1` 17) — các alias ngành khớp thẳng trong tiêu đề mà LLM không liệt kê thành thực thể.
Chưa xác định phần nào trong đó là khớp sai và phần nào là LLM bỏ sót; **đây là ô trống cần kiểm tay**.

### 3.3 Khối lượng đang nằm chết

| Hiện vật | Số lượng | Nơi chứa | Có consumer? |
|---|---:|---|---|
| Thực thể thân bài LLM bắt được | 2.748 lượt / 300 bài | `data/article_mentions/*.json` | **Không** |
| Trong đó tra được vào danh mục | **1.010** (456 TICKER) | như trên | **Không** |
| Chuỗi ngoài danh mục (`unlisted_candidates`) | 1.287 chuỗi / 2.029 lượt | như trên | **Không** |
| Lượt mang mã nhóm sai định dạng, rơi lặng | **424 / 2.748 = 15,4%** | — | — |
| Gói L1 chờ Subagent | 375 tệp | `data/agent_tasks/l1/` | **Không** |

424 lượt rơi lặng là do mô hình phát thẳng `entity_id` vào ô mã nhóm (`IND_GICS2:NGAN_HANG`,
`ASSET_CLASS:CO_PHIEU`...) thay vì mã nhóm hai-ba ký tự. `resolve_one` thấy nhóm không thuộc
`VALID_GROUPS` thì trả `in_list=False` và **không ghi lại lý do** (`intent_resolve.py:160-163`).

### 3.4 Hiệu năng đo được

| Phép đo | Kết quả |
|---|---|
| `load_registry()` | 0,23 s (một lần, có `lru_cache`) |
| `detect()` trên tiêu đề | **0,9 ms/bài** (500 tiêu đề thật) |
| `detect()` trên thân bài 4.520 ký tự | **31 ms/bài** |
| Suy ra: quét thân bài toàn kho 12.536 bài | **khoảng 6,5 phút** một luồng |
| `classify_title()` | 1,4 ms |
| `check_l1_dod()` | **28,6 ms** — gấp 19 lần chính phép nhận diện |
| `validate()` khi schema đã nạp sẵn | 1,5 ms |

`check_l1_dod` gọi `contract_validator.validate(output, "l1-entity-output-v1")`, và hàm này
**đọc lại tệp schema từ đĩa rồi dựng lại `Draft202012Validator` ở mỗi lượt gọi**
(`src/handoff/contract_validator.py:34, 48-51`). Không có cache. Chi phí kiểm định đang lớn hơn
chi phí nhận diện gần hai chục lần.

---

## 4. Vấn đề, xếp theo nhóm

### A. Ranh giới thiết kế — nguồn gốc của khoảng cách 10%

- **A1. Code-first chỉ đọc tiêu đề.** ADR 0003 ghi nhận đây là đánh đổi có ý thức, với lập luận
  "không hồi quy vì Agent L1 cũng chỉ nhận tiêu đề". Lập luận đó **đã hết hiệu lực** từ 18/09:
  Article Lane cho LLM đọc trọn bài, và số đo §3.2 cho thấy phần thân bài chứa 90% số mã.
- **A2. Lược đồ chặn đường.** `l1-entity-output-v1` bắt `surface` phải là chuỗi con của `title`
  (`l1_router.py:225-231` và DoD). Vì vậy thực thể thân bài **không có chỗ chứa hợp lệ**, kể cả khi
  LLM đã tìm ra. Kết quả: 200/300 bài của Article Lane có `recognized=false` và 0 thực thể,
  dù tổng cộng 1.010 định danh đã được tra ra rồi phải đổ sang tệp `*.mentions.json` bên lề.
- **A3. Rào cản là lược đồ, không phải hiệu năng.** 31 ms/bài, 6,5 phút cho toàn kho (§3.4).
  Lập luận "quét thân bài quá đắt" không còn cơ sở.

### B. Chất lượng nhận diện

- **B1. Guard hình thái viết cứng theo từng định danh.** `_blocked_by_morphology`
  (`entities.py:432-490`) có nhánh `if` riêng cho đúng hai thực thể: `MACRO_GEO:MY` và `MACRO_GEO:NGA`,
  kèm danh sách tên người và tiền tố nằm thẳng trong mã Python. Thêm một ca mới đồng nghĩa với sửa mã
  và chạy lại test. `_context_guards.yaml` chỉ có hai cơ chế (`drop_bare`, `block_in`), không phủ được
  loại luật này.
- **B2. Ba danh sách chặn nằm trong mã, không nằm trong cấu hình.** `CODE_STOPLIST`,
  `GENERIC_ALIAS_STOPLIST`, `PROTECTED_SHORT_WORDS` (`entities.py:21-70`). Người biên tập không sửa được.
- **B3. 351 mã tier 2 gần như mù.** Chỉ nhận qua mã ba ký tự khi tiêu đề là công bố thông tin
  (`entities.py:301-303`). Trong văn bản thường, chúng phụ thuộc hoàn toàn vào alias tên công ty.
- **B4. Thực thể khớp nhưng biến mất khi vật chất hoá.** `_alias_match` có thể trả `surface=None`
  cho alias nhiều từ khi `_locate_folded` không dựng lại được chuỗi gốc (`entities.py:497-513`);
  `build_code_first_output` sau đó loại mọi thực thể không ground được vào tiêu đề
  (`l1_router.py:225-231`). Bài vẫn được xếp `resolved` nhưng bản ghi giao đi rỗng hơn dự kiến.
- **B5. `citations` của code-first là hình thức.** Luôn đúng một phần tử, lấy `surface` của thực thể
  đầu tiên (`l1_router.py:240`). Đủ qua DoD, không mang giá trị kiểm chứng nào.
- **B6. Cột `recognized` luôn ghi 1.** `ingest_code_first` truyền `"recognized": 1` cố định
  (`l1_runner.py:129`) kể cả khi `output_json.recognized` là `false`. Cột và nội dung lệch nhau.
- **B7. Hai đường tra cứu, hai bộ luật.** Xem §2 điểm 4. `IntentResolver` không có guard hình thái,
  không lọc `GENERIC_ALIAS_STOPLIST` ở tầng tra, và nuốt lặng tên trùng.

### C. Danh mục và dữ liệu

- **C1. Không có vòng mở rộng danh mục.** 1.287 chuỗi `unlisted_candidates` và 1.010 định danh thân bài
  đã tra được đang nằm trong tệp bên lề, không script nào đọc, không bảng nào chứa.
- **C2. Nhóm `PER` chưa có nguồn tra.** `GROUPS_WITHOUT_RESOLVER = {"PER"}`; `leaders.yaml` chưa tồn tại.
  259 lượt tên người đã thu được trên 300 bài — đủ nguyên liệu để dựng bảng, chưa ai dựng.
- **C3. ADR 0003 chưa bao giờ được nghiệm thu.** Mục "Actual Outcome" vẫn là khuôn trống sau 12 ngày
  vận hành. Không có số đo nào về tỷ lệ khớp đúng của 3.069 bản ghi code_first đang giao cho người dùng.
- **C4. Nhánh `resolved` không ai tra soát.** ADR 0005 đặt `--review missed` làm mặc định, nên 63,9%
  số bài đi thẳng ra deliverable mà không có lượt kiểm nào. Không sai — nhưng phải có cơ chế lấy mẫu,
  hiện chưa có.

### D. Vận hành — các phát hiện đang sống ngay lúc này

- **D1. Hai tiến trình `morninger` cũ bốn ngày đang chạy song song.**
  PID 35576 / 84636 (17/09 14:55) và 38092 / 63268 (17/09 15:16). Chúng chạy mã có trước khi
  `run_l1_route` được đổi sang `--review none` kèm bước vật chất hoá.
  **Bằng chứng:** trong `project/logs/monocle.log` hôm nay chỉ có dòng `[morninger] l1_route:`,
  **không có một dòng `[morninger] l1_code_first:` nào**; số hiệu dòng trong log nhảy giữa `:195` và `:208`
  — dấu hiệu hai phiên bản mã khác nhau cùng ghi log.
- **D2. Hệ quả trực tiếp:** hôm nay 0/232 bài có L1 (radar), 162 `l1_tasks` `resolved` nằm chờ,
  375 gói L1 tích lại. Dry-run xác nhận cả 162 bài **đều sẽ đạt DoD** nếu được chạy:
  `quét=162 ghi=162 dod_fail=0`.
- **D3. Trần thời gian mỏng, lỗi bị nuốt.** Bước vật chất hoá chạy bằng `subprocess` với `timeout=120`
  và không truyền `--limit` (`morninger.py:215-219`); toàn khối nằm trong `except Exception` chỉ ghi log
  (`morninger.py:226-228`). Lượt chạy nguội đầu tiên hôm nay của chính lệnh đó **vượt 120 giây**;
  lượt ấm sau đó 20 bài mất 3,0 giây. Biên an toàn rất mỏng, và khi vượt thì không ai biết.
- **D4. `l1_route` tiêu ngân sách vào chính việc đã làm.** Mặc định `limit=50`, và chỉ bỏ qua bài có
  `status='done'` (`l1_route.py:88-96`). Bài đã route nhưng còn `pending` bị route lại mỗi chu kỳ,
  nên với 162 bài tồn, ngân sách 50 bài mỗi 15 phút không bao giờ chạm tới bài mới.
- **D5. 85 `l1_tasks` `failed` và 90 `work_items` `failed`** đang chờ `scripts/maintenance/requeue.py`.
- **D6. Hai tệp `monocle.db`.** `project/data/monocle.db` (7.203 bài, đóng băng 08/09) và
  `C:/data/news-scape/monocle.db` (12.536 bài, đang sống). `config/settings.yaml:3` ghi đường dẫn
  tương đối trỏ vào tệp chết; chỉ biến môi trường `MONOCLE_DB_PATH` / `MONOCLE_DATA_DIR`
  (`src/core/config.py:86-92`) kéo hệ thống về tệp đúng. Máy nào thiếu biến đó sẽ chạy trên kho chết
  mà không báo gì.

### E. Nợ kỹ thuật

- **E1.** `check_l1_dod` đắt gấp 19 lần phép nhận diện vì không cache validator (§3.4).
- **E2.** Hai tuyến L1 cùng tồn tại (L1 rời và Article Lane) với hai bộ mã dựng
  `l1-entity-output-v1` riêng (`l1_router.build_code_first_output` và
  `article_expand.build_l1_output`). Sửa luật ở một nơi không tự lan sang nơi kia.
- **E3.** Chưa có bộ kiểm hồi quy nhận diện trên tập tiêu đề thật. `test_l1_classifier.py` và
  `test_l1_router.py` dùng registry dựng tay bốn thực thể — bảo vệ được cấu trúc, không bảo vệ được
  chất lượng khớp.

---

## 5. Dư địa phát triển, xếp theo đòn bẩy

Xếp theo giá trị mở ra chia cho chi phí cộng rủi ro. Chưa có mục nào được duyệt.

| # | Hướng | Giá trị đã đo | Chi phí | Cần ADR? |
|:-:|---|---|---|:-:|
| 1 | **Cho code-first đọc thân bài** | LLM tìm 456 TICKER thân bài trên 300 bài mà code-first bỏ 100% | 31 ms/bài; 6,5 phút toàn kho | **Có** — đụng lược đồ |
| 2 | **Nơi chứa thực thể thân bài** (bảng `article_entities` hoặc lược đồ v2) | giải phóng 1.010 định danh đang nằm chết | vừa | **Có** — data contract |
| 3 | **Vòng đối chiếu code với LLM thành nguyên liệu danh mục** | 854 `LLM_ONLY` thành ứng viên alias; 168 `CODE_ONLY` thành danh sách soát khớp sai | thấp, dữ liệu đã có sẵn | Không |
| 4 | **Đưa guard và stoplist ra cấu hình**, kèm bộ kiểm hồi quy trên tiêu đề thật | gỡ B1, B2, mở đường cho người biên tập | vừa | Không |
| 5 | **Vá vận hành** (D1–D6) | mở lại 162 bài đang chờ, chặn tái diễn | thấp | Không |
| 6 | **Cache validator** (E1) | kiểm định 28,6 ms xuống khoảng 2 ms | rất thấp | Không |
| 7 | **`leaders.yaml` từ 259 lượt `PER`** | mở nhóm thực thể thứ mười một | vừa | Không |
| 8 | **Automaton (Aho-Corasick) thay vòng quét alias** | chỉ cần khi mở thân bài cho toàn kho định kỳ | vừa | Không |

Mục 1 và 2 là **một cặp**: mở quét thân bài mà không có nơi chứa hợp lệ thì kết quả lại rơi vào
đúng tệp bên lề như hiện nay.

---

## 6. Ranh giới bất biến — cái gì code-first tuyệt đối không được làm

Trích `AGENTS.md` §6C và ADR 0003, giữ nguyên hiệu lực:

- **Được phép:** ánh xạ chuỗi ký tự sang `entity_id` bằng tra danh mục chuẩn. Đây là *lookup*,
  kiểm chứng được, tái lập 100%.
- **Không được phép:** tóm tắt, `implication`, `materiality_score`, `sentiment`, `event_type`,
  `citations` ngữ nghĩa, và nhận diện thực thể **không có trong danh mục**.
- Bản `code_first` là **tạm**: Agent có quyền ghi đè, chiều ngược lại thì không.
- Mở quét sang thân bài **không** nới ranh giới này. Nó chỉ đổi phạm vi văn bản được tra,
  không đổi bản chất phép tra. Nhưng vì thân bài nhiễu hơn tiêu đề nhiều lần, ngưỡng guard phải
  được đo lại từ đầu, không được thừa kế ngầm từ tiêu đề.

---

## 7. Câu hỏi phải chốt trước khi viết dòng mã đầu tiên

1. **Tuyến nào là chính thức?** L1 rời và Article Lane đang cùng sống, cùng ghi `l1_outputs`,
   bằng hai bộ mã riêng. Giữ song song, hay Article Lane thay hẳn? Câu trả lời quyết định mục 1–2 §5
   được làm ở đâu.
2. **Thực thể thân bài đi vào đâu?** Mở `l1-entity-output-v2` (nới ràng buộc `surface` nằm trong `title`)
   hay dựng bảng `article_entities` riêng? Cả hai đều là data contract, tức Hard Gate, tức cần ADR.
3. **Thực thể thân bài có được vào cổng giao hàng không?** Người dùng có muốn nhận bài chỉ nhắc mã
   của họ ở đoạn giữa, hay chỉ bài có mã ngay trên tiêu đề? Đây là câu hỏi sản phẩm, không phải kỹ thuật.
4. **Có sửa vận hành trước không?** D1–D6 không cần ADR và đang chặn dòng chảy ngay lúc này.
   Khuyến nghị: xử lý §5 mục 5 và 6 trước, vì mọi số đo sau đó mới đáng tin.

---

## 8. Lệnh tái lập các số đo trong tài liệu này

```powershell
$py = "C:\venvs\news-scape\Scripts\python.exe"

# Ảnh chụp pipeline (luôn chạy đầu ca — Zero-Probe)
& $py project/scripts/pipeline_radar.py status

cd project

# 3.1 — kho dữ liệu
& $py scripts/dbq.py "SELECT COALESCE(l1_source,'(null)') src, dod_pass, COUNT(*) n FROM l1_outputs GROUP BY 1,2"
& $py scripts/dbq.py "SELECT route, status, COUNT(*) n FROM l1_tasks GROUP BY 1,2 ORDER BY n DESC"

# 3.2 và 3.3 — đối chiếu code với LLM trên đợt W1/W2
#   nguồn: data/agent_outputs_l1/article_*.output.json  (processing_metadata.intent_source)
#          data/article_mentions/*.mentions.json

# 3.4 — hiệu năng: đo bằng src.agent.entities.load_registry và reg.detect trên tiêu đề thật

# D2 — kiểm chứng 162 bài đang chờ (chỉ đọc, không ghi)
& $py scripts/l1_ingest.py --code-first --dry-run
```

---

## 9. Nguồn tra cứu

| Chủ đề | Tệp |
|---|---|
| Quyết định mở cổng code-first | `docs/decisions/0003-code-first-l1-delivery.md` |
| Guard hình thái, cổng subscriber, `--review missed` | `docs/decisions/0005-subscriber-gated-gold-va-morphological-l1-guard.md` |
| Tồn đọng tuyến L1 tới giao hàng | `docs/OPEN-ITEMS.md` |
| Trạng thái phiên gần nhất | `docs/SESSION-LATEST.md` |
| Kế hoạch Article Lane (quy phạm) | `plans/20260918-1651-article-lane-unified/plan.md` |
| Luật nhận diện cho Subagent | `.agents/skills/l1-entity-matcher/SKILL.md` |
| Hợp đồng đầu ra L1 | `project/schemas/l1-entity-output-v1.schema.json` |
