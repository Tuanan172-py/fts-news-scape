# OPEN-ITEMS — việc tồn đọng của tuyến L1 → giao hàng người dùng

- **Cập nhật:** 2026-09-17 (bổ sung C5 manh mối Errno 22, C6 tối ưu cycle, C7 metric phát hiện)
- **Bối cảnh:** rà soát vì sao mapping từ L1 sang danh mục người dùng ghi nhận rất ít số liệu.
- **Số đo tham chiếu:** trên **bản sao** `project/data/monocle.db` (7.219 articles, chụp 2026-09-07).
  Chưa có thay đổi nào được áp lên DB vận hành.
- Đóng một mục: chuyển sang §D kèm **Kết quả đo thực tế**, đừng xoá.

---

## A0. RÀ SOÁT END-TO-END 2026-09-17 — mất dữ liệu âm thầm & ngõ cụt trạng thái

Rà soát toàn tuyến Bronze → Silver → L1 → Gold → giao hàng. Con số nền: **7.203 bài đã cào,
424 bài qua cổng giao hàng**; `work_items`: `pending=3585, claimed=304, done=135, held=2`.
Khoảng cách đó không phải do quota Gold — dưới đây là các cơ chế làm rơi bài.

### A0-1. [P0 · ĐÃ KIỂM CHỨNG] Watermark Silver nhảy cóc ⇒ mất bài VĨNH VIỄN

`project/src/pipeline/derive.py:130` — `watermark_new = max(ok_ts)` chỉ lấy max của bài **thành
công**; `_should_process` (dòng 51-57) trả `fetch_ts > watermark`. Một file Bronze lỗi có
`fetch_ts` cũ hơn một bài thành công sẽ **vĩnh viễn không bao giờ thoả điều kiện** nữa.

Không cảnh báo, không retry counter, không dead-letter — chỉ một dòng log rồi `continue`
(dòng 115-117). Bronze bắt trọn 100% bài vẫn vô nghĩa nếu Silver lặng lẽ đánh rơi.
**Sửa đúng:** watermark phải là `min(fetch_ts của phần CHƯA xong)`, không phải `max` của phần đã xong.

### A0-2. [P0 · ĐÃ KIỂM CHỨNG] `run_daily.ps1 -Mode full` là vòng lặp tự huỷ

`param` khai `[ValidateSet('api')] $Agent` (dòng 19) nên nhánh `'hierarchy'` (dòng 108-110)
**không bao giờ chạy được**; nhánh `default` chỉ in hướng dẫn. Sau đó `CleanPackets` (dòng 138)
`Get-ChildItem 'data/agent_tasks' -Filter '*.task.json' -Recurse` xoá **mọi** packet kể cả trong
`l1/`. Chuỗi `full` = xuất packet → in chữ → ingest khi chưa có output → **xoá sạch packet vừa xuất**.

**Cảnh báo vận hành:** chạy `-Mode ingest` hoặc `-Mode full` lúc này sẽ xoá trắng **155 packet L1**
đang chờ. Dùng `-KeepPackets` cho tới khi sửa xong.

### A0-3. [P0 · ĐÃ KIỂM CHỨNG] AutoPilot va chạm tên batch ⇒ ingest lại dữ liệu cũ

`auto_pilot.py:66-72` bỏ qua batch nếu `<batch>.output.json` đã tồn tại, nhưng
`split_tasks_into_batches` đánh số lại từ `batch_01` **mỗi lần chạy**. Hiện `data/agent_outputs/`
có `batch_01`–`batch_02` (17/09) lẫn `batch_03`–`batch_11` (**14/09**). Lần chạy tới: skip toàn bộ
batch mới, ingest lại dữ liệu 3 ngày trước, rồi in "hoàn tất 100%". AutoPilot không bao giờ dọn
thư mục output.

Kèm theo: `run_cmd` (dòng 29-31) chỉ *in* lỗi không raise; `except Exception` (dòng 89) nuốt cả
`FileNotFoundError` khi thiếu `agy`; không timeout, không kiểm output đã sinh, không retry.

### A0-4. [P1] Bốn ngõ cụt trạng thái — bài kẹt vĩnh viễn, không có đường quay lại

| Trạng thái | Sinh ra khi | Vì sao kẹt |
|---|---|---|
| `work_items='failed'` | Trượt DoD Gold (`runner.py:276` → `catalog.mark_failed`) | `reclaim_stale` chỉ thu `claimed`; `claim()` chỉ chọn `pending`. Không script nào requeue |
| `l1_tasks='failed'` | Trượt DoD L1 (`l1_runner.py:140, 231`) | `upsert_l1_task` cố ý giữ status (`store.py:477-480`); `drain_code_first` chỉ lấy `pending` |
| `work_items='held'` | `silver_ok` hoặc `pkg_ok` sai (`run.py:111`) | `Catalog.enqueue` dùng `INSERT OR IGNORE` ⇒ sửa nguyên nhân xong hàng cũ vẫn không về `pending` |
| `work_items='claimed'` | Worker nhận việc | `reclaim_stale` chỉ chạy **bên trong** `claim()`; không ai claim thì treo mãi (hiện 304 hàng) |

### A0-5. [P2] Các lỗi chức năng khác

- **`l1_ingest.py:83` dùng `json.loads` nhưng module KHÔNG `import json`** (đã kiểm chứng) →
  `NameError` bị nuốt bởi `except Exception: pass` (dòng 88-89) ⇒ khối dọn `l1_batch_*.task.json`
  **chưa từng chạy một lần nào**.
- **`news_cron` vừa thừa vừa va chạm**: chạy `run_once.py` 16:00 hằng ngày; nhánh `--once` của
  `orchestrator.main` (dòng 253-262) **không chiếm scheduler lock** ⇒ cào song song với morninger
  (đang bận ~56% thời gian). morninger đã bao trọn capture + derive ⇒ nên tắt task này.
- **DoD L1 hai luồng không đồng nhất**: code-first truyền registry (`l1_runner.py:124`), luồng đọc
  output subagent **không truyền** (dòng 214) ⇒ `entity_id` lạ không bị chặn ở luồng agent.
- **Sản xuất packet không có consumer**: job `l1_route` (thêm 2026-09-17) chạy mỗi 15 phút sinh
  packet `needs_agent`, nhưng không job nào tiêu thụ ⇒ `data/agent_tasks/l1/` phình đều (155 file).

### A0-6. [P3] Hiệu năng, vệ sinh, tái lập

- `rederive_incremental` đọc/parse **mỗi `.meta.json` 3 lần** mỗi chu kỳ (`derive.py:95, 131, 132`)
  ≈ 22k lượt đọc/30 phút trên OneDrive.
- `checkpoint_reached` chỉ đạt khi `backlog == 0`; một file mới nhất luôn lỗi ⇒ `export_silver_manifest`
  **không bao giờ tự chạy**.
- `article_versions` thêm một hàng mỗi lần re-derive cùng bài khi meta thiếu `fetch_ts`
  (`derive.py:55-56` luôn process; `store.py:383` INSERT thuần, không UPSERT).
- Không có job retention: `data/work_packages` 7.289 file, `data/silver` 7.289 file,
  `agent_tasks/l1/archive` 2.461 file.
- `user_output.gated_rows` nạp toàn bộ bảng vào RAM rồi lọc ngày bằng Python (dòng 166-177).
- **Tái lập & bảo mật**: `auto_pilot.py:80-88` gọi CLI ngoài `agy` kèm cờ
  `--dangerously-skip-permissions`; binary nằm ở `C:\Users\anpt\AppData\Local\agy\bin\agy.exe`,
  **ngoài repo, không pin version, không có trong `requirements.txt`** ⇒ không tái lập được trên
  máy khác hay CI, và chạy tác nhân ngoài với kiểm tra quyền bị tắt.

---

## A. CHẶN — cần người duyệt trước khi chạm dữ liệu thật

### A1. [ĐÃ DUYỆT 2026-09-09] ADR 0003 chuyển sang `accepted`

`docs/decisions/0003-code-first-l1-delivery.md` — đã chuyển trạng thái sang `accepted`. Cơ chế
vật chất hoá kết quả tra danh mục tất định (`code_first`) vào `l1_outputs` đã được phê duyệt.

### A2. [ĐÃ DUYỆT & THỰC THI 2026-09-09] ADR 0004 phần D (Phương án D1)

`docs/decisions/0004-gold-value-gate-va-du-lieu-gia-lap.md`.
Đã phê duyệt Phương án D1 và thực thi `scripts/verify_gold_quality.py --apply` trên database:
toàn bộ 1.274 bản ghi Gold giả lập/template đã được hạ `dod_pass=0` (giữ nguyên `output_json`),
rút hoàn toàn khỏi deliverable người dùng và quay về hàng đợi Gold. Xem D14.

### A3. Chưa có gì chạy trên DB vận hành

Toàn bộ số liệu trong tài liệu này đo trên bản sao. Máy vận hành phải `git pull` rồi chạy §B.
**Bước sao lưu là bắt buộc** — quy trình có `ALTER TABLE l1_outputs ADD COLUMN l1_source`.

---

## B. Các bước triển khai bắt buộc

### B1. Phải re-derive Silver, nếu không bản sửa tiêu đề vô tác dụng với backlog

3.910 work-package hiện có **không mang trường `title`**; bản sửa (commit `7cb0f44`) chỉ áp cho
gói sinh mới. Chạy trước §B2:

```powershell
cd project
.venv\Scripts\python scripts\rederive_from_bronze.py
```

`rederive_from_bronze.py` duyệt lại TOÀN BỘ Bronze, không dùng watermark.

### B2. Chuỗi chạy lần đầu

```powershell
cd project

# BẮT BUỘC — bước sau đổi schema
Copy-Item data\monocle.db data\monocle_backup_260909.db

.venv\Scripts\python scripts\maintenance\refresh_aliases.py --dry-run
.venv\Scripts\python scripts\maintenance\refresh_aliases.py

.venv\Scripts\python scripts\l1_ingest.py --code-first --dry-run
.venv\Scripts\python scripts\l1_ingest.py --code-first

.venv\Scripts\python scripts\maintenance\heal_orphans.py --dry-run
.venv\Scripts\python scripts\maintenance\heal_orphans.py

.venv\Scripts\python scripts\maintenance\relativize_paths.py
.venv\Scripts\python -c "from src.db.store import ArticleStore; from src.handoff.catalog import Catalog; print(Catalog(ArticleStore()).reclaim_stale())"

.venv\Scripts\python scripts\run_user_workflow.py --date all
```

Kỳ vọng: ~2.200–2.400 dòng cho 4 user. Lệch nhiều thì dừng, đối chiếu
`.venv\Scripts\python scripts\l1_backlog.py`.

### B3. Rút phần cần Agent (~282 bài `needs_agent`)

```powershell
.venv\Scripts\python scripts\l1_route.py --review missed --all --mini-batch 25
```

Với mỗi `data\agent_tasks\l1\l1_batch_XX.task.json`: gọi Subagent theo
`.agents/skills/l1-entity-matcher/SKILL.md`, ghi **một mảng JSON** vào
`data\agent_outputs_l1\l1_batch_XX.output.json`. Rồi:

```powershell
.venv\Scripts\python scripts\l1_ingest.py data\agent_outputs_l1\
.venv\Scripts\python scripts\run_user_workflow.py --days 30
```

### B4. Kiểm chứng bản sửa tiêu đề trên dữ liệu thật

Chưa làm được trên máy dev: toàn bộ `data/raw_html` là placeholder OneDrive chưa tải (client
không chạy), nên 122/122 bài lệch đều không đọc được Bronze. Sau §B1, đối chiếu:

```sql
SELECT COUNT(*) FROM l1_tasks t JOIN articles a ON a.url_title_hash = t.article_id
WHERE TRIM(t.title) <> TRIM(a.title);     -- kỳ vọng: 0 (trước đó: 122/1.320)
```

### B5. [ĐÃ THỰC THI 2026-09-09] Sinh lại `entities.csv` / `entities.xlsx`

Đã sửa lỗi thiếu đường dẫn `sys.path` trong `scripts/build_entities.py` và chạy thành công:
nạp từ `FRA - Data`, đồng bộ toàn bộ alias chuyên gia từ `config/`, sinh mới 2.072 thực thể cho cả
`entities.json`, `entities.csv`, `entities.xlsx`, `taxonomy.json` và `stats.json`. Xem D15.

---

## C. Quyết định còn treo

### C1. 685 dòng `l1_outputs` nguồn `agent` (lô 25/08) mang nhiễu cũ

22 nhãn `IND_GICS*:QUY` mà matcher hiện tại phản đối. ADR 0003 quy định bản `agent` được ưu tiên
hơn `code_first` nên chưa đụng. Ba lựa chọn:

1. chạy lại Subagent L1 cho nhóm đó;
2. cho `code_first` ghi đè các dòng `agent` cũ hơn một mốc thời gian — **lật một điều khoản của
   ADR 0003**, phải sửa ADR;
3. để nguyên.

Đối chiếu: **0/28** nhãn từ `code_first` bị matcher hiện tại phản đối.

### C2. Không có runner LLM — hàng đợi chỉ dài thêm

Không module nào trong repo gọi API LLM (`requirements.txt` không có SDK nào); `run_daily.ps1`
gọi `scripts/agent_stub.py` — **file không tồn tại**. Hiện tồn: ~282 bài `needs_agent`,
3.781 `work_items` chờ Gold.

Chọn: chạy tay theo §B3, hay dựng runner tự động (phải chốt provider trước).

### C3. `url_title_hash = sha256(url + title)` — khoá định danh chứa trường thay đổi được

Toà soạn sửa tít sau khi đăng là sinh hash mới: 12 bài cùng một URL nằm dưới nhiều hash,
`heal_orphans.py` phải bỏ qua chúng vì ràng buộc `UNIQUE(url)`. Sửa đúng là chuyển định danh
sang URL chuẩn hoá, giữ title làm thuộc tính — **mức ADR, cần rehash toàn bộ**. Chưa soạn.

### C4. Alias nhập nhằng nghĩa mà tầng tất định không giải được

Đã xử lý theo intent trong `config/entities/aliases/_context_guards.yaml` (`drop_bare` cho
`Nước`/`Điện`/`Giấy`/`Quỹ`, `block_in` cho `MACRO_GEO:MY`). Phần còn lại là suy luận ngữ cảnh —
thuộc Subagent. `BTC` cố ý trỏ **cả hai** `ASSET_CLASS:TIEN_MA_HOA` và
`INSTITUTION:BO_TAI_CHINH`: hai thực thể cùng mức quan trọng, giữ recall cho cả hai phía.

### C5. Silver mỏng ở 2 nguồn nhỏ

`fireant.vn` 8/33 và `tinnhanhchungkhoan.vn` 4/32 work-package có `cleaned_text` < 200 ký tự.

**Manh mối mới (2026-09-17)** — log vận hành cho thấy Bronze của fireant có file đọc KHÔNG được:

```
WARNING | _extract_from_bronze | read bronze failed
  data/raw_html\fireant.vn\20260907\e669e1e3…f99ade4f.html: [Errno 22] Invalid argument
```

Bronze không đọc được thì Silver rỗng — rất có thể đây chính là nguyên nhân gốc của C5 chứ không
phải lỗi bóc tách. Bước điều tra đầu tiên: kiểm tra file đó có tồn tại thật và đọc được bằng tay
không (`Errno 22` trên Windows thường là path/tên file không hợp lệ hoặc file bị OneDrive
dehydrate — xem rule 03 Bất biến 4 về Files On-Demand Pinning).

### C6. Tối ưu chi phí chu kỳ capture trước khi hạ interval dưới 10 phút

Đo 2026-09-17: cycle = **335s**, trong đó cafef 124s (fetch 900 item → 5 bài mới) và fireant 87s
(600 item → 0 bài mới) chiếm 63%. Đã chốt đặt `capture_interval_minutes: 10` để có ~40% biên dự
phòng. Muốn xuống 5 phút phải giảm chi phí cycle trước.

Hướng: **dừng phân trang sớm** khi gặp một trang mà toàn bộ item đã nằm trong `seen_articles`.
Rủi ro phải kiểm soát: phân trang nông quá là bỏ sót bài — đi ngược mục tiêu gốc của US-011.
Cần test trên dữ liệu thật trước khi bật.

### C7. Metric "bài bị nguồn xóa" chưa đếm theo thời điểm phát hiện

Radar hiện hiển thị "N bài đăng hôm nay / M tổng tích lũy". Con số theo ngày đăng luôn thấp hơn
thực tế vì bài bị gỡ thường được phát hiện muộn hơn ngày đăng. Dữ liệu để làm đúng đã có sẵn:
`metadata_json.capture_retry.last_at`. Chưa có truy vấn theo trường này.

---

## D. Đã đóng — đừng mở lại

| # | Vấn đề | Kết quả đo thực tế |
|---|--------|--------------------|
| D1 | Cổng export bỏ qua toàn bộ kết quả tất định; bài `route=resolved` nằm `pending` vĩnh viễn | Bài qua cổng **424 → 1.529**; khớp danh mục AnPT **146 → 791**; user có output **1 → 4** |
| D2 | `make_aliases()` bơm mọi chuỗi trong ngoặc thành alias → `"(Việt Nam)"` thành alias của `TICKER:IVS` | `TICKER:IVS` khớp sai **164 → 0** |
| D3 | `seen_articles` đánh dấu ngay lúc cào trong khi `articles` ghi bất đồng bộ | 429/429 bài mồ côi đều nằm trong `seen_articles`; nay ghi **cùng transaction**; `heal_orphans.py` thu hồi **437 bài** |
| D4 | `work_items` kẹt `claimed`, không có đường nhả | **304 → 0** (`Catalog.reclaim_stale()`) |
| D5 | `packet_path` lưu đường dẫn tuyệt đối của 2 máy | **1.787 dòng** chuyển sang tương đối theo `PROJECT_ROOT` |
| D6 | `l1_route` sắp nguồn theo chuỗi đường dẫn → 400 file đầu tiên 100% là `vneconomy.vn`, trần 50/lần chạy không bao giờ chạm 5 domain còn lại | Sắp theo thời gian |
| D7 | `VyPTT` có file đăng ký nhưng bị `default: false` tắt im lặng | Đã bật + cảnh báo log; xoá `A.yaml`/`B.yaml` (nhóm ví dụ viết tay) |
| D8 | `"TP.HCM"` khớp nhầm `TICKER:HCM`; `"quý 3"` khớp `IND_GICS*:QUY`; `"Xăng dầu Việt Nam"` (PLX) sinh `TICKER:OIL` | Guard ngữ cảnh trái, guard dấu cho alias 1 từ ngắn, khử chồng lấn tên chứng khoán |
| D9 | DoD L1 không kiểm `entity_id` có thật → `"INDUSTRY_GICS3:THEP"` sai dạng vẫn qua cổng rồi định tuyến cho 0 người | `check_l1_dod` kiểm registry |
| D10 | Silver lấy `h1` = header trang hồ sơ doanh nghiệp làm tiêu đề (122/1.320 bài), làm mất cả mã cổ phiếu | Giải tiêu đề bằng đối chiếu `sha256(url+title)` với `url_title_hash`; **chờ kiểm chứng §B4** |
| D11 | `process_l1_pipeline.py` là matcher thứ hai đang trôi khác, `build_l1_output` đóng dấu `agent_provider="gemini"` + timestamp cố định | Rút còn lớp vỏ uỷ quyền; provenance khai đúng `code_first`/`deterministic` |
| D12 | ~~2.677/7.219 bài `content_text` mỏng~~ — **xếp nhầm, không phải lỗi pipeline** | Mỏng là `articles.content_text` (đường RSS của scraper). `cleaned_text` của Silver — thứ L1/Gold thực sự đọc — thì lành: mẫu 400 gói có 374 bài ≥1.000 ký tự, cafef **0/137** mỏng |
| D13 | ADR 0003 còn ở `proposed` | Đã duyệt sang `accepted` ngày 2026-09-09; code-first sẵn sàng cho pipeline |
| D14 | 1.117/1.274 bản ghi Gold là sản phẩm của regex nhưng mang nhãn LLM (ADR 0004 D) | Đã duyệt Phương án D1; `verify_gold_quality.py --apply` đã hạ `dod_pass=1`: **1.274 → 0 (0.0%)**, deliverable sạch template |
| D15 | `build_entities.py` lỗi thiếu `sys.path` và thiếu `pyarrow`; `entities.csv/xlsx` cũ | Đã sửa `sys.path`, cài `pyarrow`; sinh mới 2.072 thực thể cho cả master json, csv, xlsx, taxonomy |
| D16 | Token burn Gold quá cao do payload 4.000 chars và export toàn bộ pending không ai đọc (ADR 0005) | **Subscriber-Gated Export**: claim 947/1.505 bài, bỏ 558 bài unmonitored (-37.1% token); **Semantic Pruner 2.200 chars** (-47% token/bài); tổng tiết kiệm ~66.7% |
| D17 | L1 false positives danh từ riêng tiếng Việt (*Mỹ Thuận, Á Mỹ, Mỹ Tho, Bà Kim Nga, Nga Rose*) | **Morphological & Compound Guard** (`_blocked_by_morphology`): FP `MY` **14 → 0**, FP `NGA` tên người **→ 0** |
| D18 | Sót tin CBTT VNDirect (bị stoplist nuốt), nhầm PGD ngân hàng với mã CP, sót tin công ty con (US-010, US-011) | **Positional Exemption** (`^VND:`): cứu **36/36 bài CBTT**; **Bank PGD Guard**: FP `PGD` **36 → 0**; **Ecosystem Aliasing**: nhận diện thêm VinFast, Bách Hóa Xanh, WinCommerce, FE Credit |
| D19 | Xử lý dứt điểm toàn bộ 258 bài L1 ngày 14/09; chống burn token do tool loop; đóng gói End-to-End Playbook | **258/258 bài PASS DoD 100%**; 0 task tồn đọng; nạp 4.921 L1 outputs; chuẩn hóa Rule 01 (Strict 2-I/O), ban hành `end-to-end-operations-playbook.md` |

**Kiểm tay sau khi sửa:** 25 dòng ngẫu nhiên của AnPT → **0/29 mã không có căn cứ trong tiêu đề**.
**pytest:** 413 passed (100% green, cập nhật 2026-09-17 — gồm 10 test CLI entry point chạy thật
qua subprocess, bổ sung sau sự cố 3 lỗi sản xuất vô hình với test import hàm).

