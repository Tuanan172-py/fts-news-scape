# OPEN-ITEMS — việc tồn đọng của tuyến L1 → giao hàng người dùng

- **Cập nhật:** 2026-09-09
- **Bối cảnh:** rà soát vì sao mapping từ L1 sang danh mục người dùng ghi nhận rất ít số liệu.
- **Số đo tham chiếu:** trên **bản sao** `project/data/monocle.db` (7.219 articles, chụp 2026-09-07).
  Chưa có thay đổi nào được áp lên DB vận hành.
- Đóng một mục: chuyển sang §D kèm **Kết quả đo thực tế**, đừng xoá.

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
Chưa điều tra.

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

**Kiểm tay sau khi sửa:** 25 dòng ngẫu nhiên của AnPT → **0/29 mã không có căn cứ trong tiêu đề**.
**pytest:** 42 passed (100% green).

