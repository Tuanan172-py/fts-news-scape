# Thiết kế — Quy trình end-to-end lớp NGƯỜI DÙNG (input → output)

Cập nhật: 2026-09-08 · Đối tượng: dev/vận hành muốn chạy từ input user tới khi có file giao hàng.
Tham chiếu chéo: [00-end-to-end-architecture](00-end-to-end-architecture.md),
[09-agent-io-contract](09-agent-io-contract.md), [10-agent-orchestration-governance](10-agent-orchestration-governance.md).

---

## 1. Mục tiêu & nguyên tắc chốt

Input cấp cao nhất = **thư mục theo user**. Hệ thống chạy các lớp agent rồi xuất **1 file XLSX/ngày
cho từng user**, lọc theo entity user đăng ký. Idempotent, resume theo `article_id`.

Quyết định thiết kế (chốt 2026-08-18, **sửa 2026-09-07**):
- **Gate output** = `l1_outputs.dod_pass=1` **CHỈ** (L1 phải agent-reviewed). Định tuyến dựa entity
  của L1 nên thiếu L1 là không map được user nào ⇒ đây là gate CỨNG duy nhất.
  `agent_outputs.dod_pass=1` là **enrichment TÙY CHỌN**: thiếu thì trường Gold để chuỗi rỗng và
  cột `gold_status=L1_ONLY`; vòng sau Gold về thì bài được ghi đè đầy đủ (rewrite toàn tập).
  *(Trước 2026-09-07 gate là AND cả 2 lớp — bài chỉ có L1 bị giữ lại, giao hàng trễ vô ích.)*
- **Phạm vi agent** = chỉ article có entity giao với **union subscription** của user đang bật.
- **Scrape TÁCH** khỏi workflow (`--skip-scrape` mặc định — giả định cron đã scrape).
- **Bật/tắt user** = `users/subscriptions/manifest.yaml` (vắng tên = mặc định BẬT).
- **Không notify** giai đoạn này — chỉ `logger.info("done …")`.

---

## 2. Sơ đồ tổng thể

```
STAGE 0  users/subscriptions/<name>_news.xlsx|csv + users/subscriptions/manifest.yaml  (USER nhập tay)
   │           scripts/compile_users.py --all
STAGE 1  → project/config/entities/users/<name>.yaml   (+ _unknown.txt)      → EntityRegistry
   │
STAGE 2  scrape → bronze(raw_html) → silver → work_packages(work_items)      (ĐÃ CÓ, cron)
   │
STAGE 3  L1:  l1_route.py → packet → [AGENT] → l1_ingest.py → l1_outputs.dod_pass=1
   │
STAGE 4  Agent: agent_export.py(--require-l1) → packet → [AGENT] → agent_ingest.py → agent_outputs.dod_pass=1
   │           GATE: l1 dod_pass=1 (CỨNG) · agent dod_pass=1 (TÙY CHỌN → gold_status)
STAGE 5  → subscribers_for(entities) ∩ enabled → users/output/<name>/<YYYY-MM-DD>.xlsx
                                                 + _checkpoint.json · log "done"
```

`[AGENT]` = agent NGOÀI (provider bất kỳ do bạn điều khiển), prompt theo `schemas/*-instructions-v1.md`.
Runtime chỉ **phát packet** + **nạp & chấm DoD**, không nhúng LLM.

---

## 3. Cấu trúc thư mục

```
users/                                   (REPO ROOT, sibling của project/)
├── subscriptions/
│   ├── manifest.yaml                    # bật/tắt user
│   ├── <name>_news.xlsx | .csv          # USER nhập (1 file phẳng / user)
│   ├── _template_news.csv               # mẫu để copy
│   └── _unknown/<name>.txt              # (auto) entity nhập sai
└── output/
    ├── <name>/<YYYY-MM-DD>.xlsx          # deliverable — 1 file/ngày, PHẲNG
    ├── <name>/_checkpoint.json          # sổ cái đã giao
    └── _master/<YYYY-MM-DD>.csv         # audit; kèm _L1.csv và _agent.csv cùng ngày
project/config/entities/users/<name>.yaml    # (auto) config máy đọc
```

> **Phẳng, không thư mục con theo ngày.** `users/output/<name>/2026-08-14.xlsx`, KHÔNG phải
> `users/output/<name>/2026-08-14/final.csv`. Nguồn sự thật: `src/export/user_output.py`
> (`file_path = user_dir / f"{d}.xlsx"`). Tài liệu trước 2026-09-08 ghi sai dạng thư mục con.
>
> Deliverable user đổi CSV → XLSX ngày 2026-09-08 (US-101, §10). File `.csv` đã giao trước đó
> vẫn nằm nguyên trong thư mục — **không xoá** (đồng bộ SharePoint, xem `dev/07` §1).

---

## 4. STAGE 0 — USER khai báo input

### 4.1 File đăng ký `users/subscriptions/<name>_news.xlsx` (hoặc `.csv`)
Sheet đầu tiên (`entities`): mỗi **cột** = 1 nhóm, mỗi **dòng** = 1 giá trị. Username suy ra từ
TÊN FILE (`AnPT_news.xlsx` → `AnPT`) — user không phải điền sheet `meta`. Bản `.csv` cùng cấu trúc
(ma trận ngang, header = tên nhóm); khi có cả hai, `.xlsx` được ưu tiên.

| Cột | Nhập gì | Nguồn tra trong `data/entities/entities.xlsx` | Ví dụ |
|-----|---------|-----------------------------------------------|-------|
| `tickers` | **code** | sheet `Securities`.code | `HPG`, `FPT` |
| `etfs` | **code** | `Securities`(ETF).code | `E1VFVN30` |
| `indices` | **code** | `Indices`.code | `VNINDEX`, `VN30` |
| `exchanges` | **code** | `Exchanges`.code | `HOSE`, `HNX` |
| `industries` | **code** ngành GICS | `Industries`.code | `THEP`, `NGAN_HANG` |
| `entities` | **entity_id** (cửa thoát) | cột `entity_id` | `TICKER:HPG` |

- Nhóm dùng code tự viết hoa khi compile (`hpg`→`HPG`, `thep`→`THEP`). `industries` khớp theo **CODE** ngành GICS (KHÔNG theo tên).
- Lấy template: `python scripts/make_user_template.py` → `users/subscriptions/_template_news.csv`
  (+ bản xlsx có dropdown tại `users/template/entities_template.xlsx`).
- Seed từ config yaml có sẵn: `python scripts/make_user_template.py --seed <name>`.

### 4.2 `users/subscriptions/manifest.yaml`
```yaml
users:
  AnPT: true
  A: false          # tắt
# vắng tên = mặc định BẬT; thư mục tên bắt đầu '_' luôn bị bỏ qua
```

---

## 5. STAGE 1 — Compile input → config yaml

`scripts/compile_users.py --all` → `src/users/compile.py`:
- `read_user_xlsx()` đọc sheet `entities`/`meta` → `(doc, meta)`; `_normalize()` upper code.
- `EntityRegistry.select(doc)` (không viết lại logic map) → `(ids, unknown)`.
- Ghi `project/config/entities/users/<name>.yaml` (header `AUTO-GENERATED`); nếu có unknown → `_unknown.txt`.
- `compile_all()` cuối cùng gọi `load_registry.cache_clear()` để subscription mới có hiệu lực.

Kết quả: `EntityRegistry.subscriptions[<name>] = {entity_id…}`; `subscribers_for()` ánh xạ entity→user.

---

## 6. STAGE 2 — Scrape/Process (đã có, chạy riêng)

Cron/pipeline hiện tại: `scrape → bronze(raw_html) → silver → work_packages`. Chi tiết xem
[02-execution-flow](02-execution-flow.md), [07-storage-layers-and-change-detection](07-storage-layers-and-change-detection.md),
[08-handoff-contract-catalog](08-handoff-contract-catalog.md). Đây là phần `--skip-scrape` (mặc định)
của user-workflow — giả định đã sinh `work_items` trong DB.

---

## 7. STAGE 3 — L1 nhận diện entity (handoff)

| Bước | Lệnh / module | Ghi ra |
|------|---------------|--------|
| export | `scripts/l1_route.py` → `L1Runner.route_and_export()` | `l1_tasks` + packet `data/agent_tasks/l1/<id>.task.json` |
| agent | AGENT ngoài (prompt theo `schemas/l1-entity-instructions-v1.md`) | `l1-entity-output-v1` `*.json` |
| ingest | `scripts/l1_ingest.py <dir>` → `L1Runner.ingest_output()` | `l1_outputs` (+ `dod_pass`), `l1_tasks.status` |

**L1 done** = `l1_outputs.dod_pass=1` (schema + grounding surface/citation ⊂ title). `confidence` không còn là gate.

---

## 8. STAGE 4 — Agent bóc tách (handoff, giới hạn phạm vi)

| Bước | Lệnh / module | Ghi ra |
|------|---------------|--------|
| export | `scripts/agent_export.py` → `AgentRunner.export_tasks()` | packet `data/agent_tasks/<id>.task.json` |
| agent | AGENT ngoài (prompt theo `schemas/agent-instructions-v1.md`) | `agent-output-v1` `*.json` |
| ingest | `scripts/agent_ingest.py <dir>` → `AgentRunner.ingest_output()` | `agent_outputs` (+ `dod_pass`) |

**Trường agent phải thêm** (`agent-output-v1`): `summary.abstractive` + `key_points`, `implication.text`
+ `impact_area`, `materiality.score` + `time_sensitivity`, (tuỳ chọn) `sentiment`, `event_type`; `citations`≥2.
**Agent done** = `agent_outputs.dod_pass=1` — 6 predicate: schema hợp lệ · ≥2 citation ⊂
`cleaned_text` · `extraction_quality`∈{high,medium} · `processing_metadata` đủ ·
**`value_added`** (tóm tắt không phải bản sao, `key_points` khác `citations`) ·
**`implication_specific`** (≥40 ký tự, không trích nguyên văn, không phải câu template).
`confidence` không còn là gate.

> 2 predicate cuối thêm 2026-09-08. Trước đó cổng chỉ đo tính CÓ CĂN CỨ nên với output
> copy nguyên văn thì phép thử hiển nhiên đúng: **1.274/1.274** bản ghi `agent_outputs`
> đều `dod_pass=1` trong khi 100% có `key_points` copy y hệt `source_span` và 100%
> `implication` là 1 trong 3 câu template. Xem
> [ADR 0004](../../../docs/decisions/0004-gold-value-gate-va-du-lieu-gia-lap.md).
> Kiểm định định kỳ: `python scripts/verify_gold_quality.py`.

**Giới hạn phạm vi (tiết kiệm):** chỉ nên export article có entity ∈ `union_subscription(registry, enabled)`
(`src/pipeline/user_workflow.py::union_subscription`). Article không ai theo dõi → không cần agent.

---

## 9. STAGE 5 — Output per-user (gated)

`scripts/write_user_output.py` → `src/export/user_output.py::UserOutputWriter.write()`:

1. **`gated_rows()`** — JOIN (`_GATED_SQL`):
   `articles ⨝ l1_outputs(dod_pass=1)` **LEFT JOIN** `agent_outputs(dod_pass=1)` trên `url_title_hash`.
   `agent_outputs` UNIQUE theo `(article_id, raw_sha256)` nên 1 bài tái-capture có nhiều dòng đạt
   DoD → subquery `MAX(id)` chọn **bản Gold mới nhất**, tránh fan-out không xác định.
   Lọc theo `--date today|YYYY-MM-DD` hoặc `--days N` (dùng `published_at`, fallback `fetched_at`).
2. **Định tuyến** — entity của article = `l1_outputs.entities[in_list].entity_id`;
   `subscribers_for(eset)` ∩ `enabled`; mỗi user lấy `matched = eset ∩ resolve_subscription(user)`.
3. **Ghi file** (atomic temp + `os.replace`, utf-8-sig):
   - Thư mục user (`users/output/<name>/`): **chỉ ghi duy nhất `<date>.xlsx`** (deliverable tinh gọn).
   - Thư mục audit tập trung (`users/output/_master/`): `<date>.csv`, `<date>_L1.csv`, `<date>_agent.csv`.
     `_master/<date>.csv` dùng `MASTER_COLUMNS` = `FINAL_COLUMNS` + **`noise_signals`** — tín hiệu
     nhiễu TẤT ĐỊNH từ Silver (`alias_title`, `alias_body`, `body_len`, `code_in_symbols`, `cats`),
     **chỉ để quan sát, CHƯA dùng làm gate**. Gom số liệu thật trước, chọn ngưỡng sau.
     `_master/<date>_agent.csv` chỉ chứa bài `gold_status=GOLD`.
4. **Checkpoint** — `src/export/checkpoint.py::mark_written()` cập nhật `_checkpoint.json` **SAU** khi
   `<date>.xlsx` đã replace (crash-safe). `logger.info("done user=… date=… rows=…")`.

Article thiếu **L1**, hoặc không ai đăng ký entity → **không** vào `<date>.xlsx`.
Article có L1 nhưng chưa có Gold → **vẫn vào**, `gold_status=L1_ONLY`, trường Gold rỗng.

**Lọc rác (`_passes_noise_filter`)** — KHÔNG đọc bất kỳ trường Gold nào: pass nếu match ≥1 entity
cụ thể (TICKER/ETF/INDEX/EXCHANGE/INDUSTRY/INSTITUTION), hoặc — khi chỉ match entity diện rộng
(`MACRO_GEO`/`MACRO_THEME`/`ASSET_CLASS`) — alias của entity xuất hiện trong `title`.

---

## 10. Định dạng file giao hàng `users/output/<name>/<YYYY-MM-DD>.xlsx`

Nguồn sự thật: `src/export/xlsx_delivery.py::DELIVERY_FIELDS`. **12 cột**, 4 khối:

| # | Cột (nhãn hiển thị) | Nguồn | Khối |
|---|---|---|---|
| 1 | Ngày | `published_at` → fallback `fetched_at` (kiểu date thật, `yyyy-mm-dd`) | định vị |
| 2 | Mã theo dõi | code entity user đăng ký MÀ article chạm, join `; `, **đã khử trùng** | định vị |
| 3 | Tiêu đề | `articles.title` | định vị |
| 4 | Sắc thái | `sentiment.polarity` → `Tích cực`/`Tiêu cực`/`Trung lập` | phân loại |
| 5 | Độ khẩn | `materiality.time_sensitivity` → `Khẩn`/`Trong ngày`/`Trong tuần`/`Trong tháng`/`Lưu trữ` | phân loại |
| 6 | Độ đầy đủ | `gold_status` → `Đầy đủ` (GOLD) / `Sơ bộ` (L1_ONLY) | phân loại |
| 7 | Nguồn | `source_domain` | nguồn |
| 8 | Tóm tắt | `summary.abstractive` | văn bản dài |
| 9 | Ý chính | `summary.key_points`, dạng `- điểm 1\n- điểm 2` (wrap trong ô) | văn bản dài |
| 10 | Hàm ý thị trường | `implication.text` | văn bản dài |
| 11 | Link | `articles.url` — clickable, giữ chữ đen (không dùng style Hyperlink xanh) | kỹ thuật |
| 12 | Mã bài | `article_id` | kỹ thuật |

**Vì sao XLSX chứ không CSV (chốt 2026-09-08, US-101).** CSV không lưu được độ rộng cột,
freeze pane, AutoFilter, wrap-text. Đo trên dữ liệu thật: `Tóm tắt` trung bình 460 ký tự,
`Ý chính` trung bình 593 ký tự có xuống dòng — mở CSV bằng Excel là lưới trần, và vì file
sinh MỚI mỗi ngày nên người dùng phải lặp lại ~5 thao tác định dạng hằng ngày, không lưu
lại được. XLSX lưu các thứ đó một lần.

**Quy chuẩn trình bày — đơn sắc, không trang trí:**
- Đúng 1 dòng header ở dòng 1. Không tiêu đề báo cáo, không merge cell, không dòng trống,
  không dòng tổng.
- KHÔNG màu nền, KHÔNG banding, KHÔNG màu chữ. Phân cấp bằng **in đậm** + 1 kẻ mảnh dưới header.
- `freeze_panes = A2` + AutoFilter trên toàn dải.
- 7 cột đầu đều ngắn (≤ 20 ký tự) nên vừa một màn hình; 3 cột văn bản dài nằm sau nên tràn
  vào vùng trống bên phải thay vì đẩy cột ngắn ra ngoài.
- Thứ tự dòng TẤT ĐỊNH: `Độ khẩn` → `materiality.score` giảm dần → `Mã theo dõi` → `Tiêu đề`.
  Trước đây dòng đi theo thứ tự SQL JOIN trả về nên nhìn như dữ liệu ngẫu nhiên.

**Cột bị loại khỏi deliverable** (vẫn còn đủ trong `_master/*.csv`):
- `impact_area` — đo trên 1.274 bản ghi Gold: **100% = `market`**. Lọc được gì đâu.
- `event_type` — 80% = `macro`.
- `agent_provider`, `model_used` — metadata máy, không phải nội dung nghiệp vụ.
- `materiality_score` — ẩn từ 2026-09-07 theo CORE/DETAIL bên dưới, nhưng **vẫn dùng làm khoá
  sắp xếp** nên tin quan trọng tự nổi lên đầu mà không tốn một cột.

**Chống formula injection.** openpyxl tự đoán chuỗi mở đầu `=` là CÔNG THỨC, và tiêu đề tin tài
chính mở đầu `-5%…`/`+3%…` là chuyện thường. Mọi ô văn bản bị ép `data_type="s"`
(`xlsx_delivery._set_text`). Tham chiếu OWASP CSV Injection.

- `gold_status` ∈ `GOLD` | `L1_ONLY` — phân biệt "Gold chưa chạm bài" với "Gold đã chạy nhưng
  trường optional rỗng" (`sentiment`/`time_sensitivity` là optional trong `agent-output-v1`).
  Không có cột này thì ô rỗng là nhập nhằng.
- Flatten null-safe: field agent tuỳ chọn thiếu → ô rỗng, không lỗi.
- Enum lạ (agent trả sai giá trị) được giữ NGUYÊN VĂN, không nuốt — nhìn thấy giá trị lạ trong
  file là tín hiệu đi sửa agent.
- File CSV đã giao trước 2026-09-08 **không bị xoá** (thư mục output đồng bộ SharePoint,
  xem `dev/07` §1); pipeline chỉ ngừng sinh CSV mới cho thư mục user.

### 10.1 Mô hình CORE / DETAIL (chốt 2026-09-07)

Tách **hợp đồng LƯU TRỮ** (`agent-output-v1`, không đổi) khỏi **hợp đồng GIAO HÀNG**
(`xlsx_delivery.DELIVERY_FIELDS` cho người, `MASTER_COLUMNS` cho máy).

| Tầng | Ai làm | Trường | Vai trò |
|---|---|---|---|
| Bronze/Silver | code (tất định) | `article_id, title, url, source_domain, date, cleaned_text` | CORE — luôn có |
| L1 | agent | `entities[].entity_id` + `in_list`, `categories` | **CORE — gate CỨNG** |
| Gold | agent | `summary.abstractive`, `summary.key_points`, `citations`≥2 | CORE — gate MỀM |
| Gold | agent | `implication`, `materiality`, `sentiment`, `event_type` | DETAIL |

Không đổi `agent-output-v1`: đổi Data Contract là HIGH-RISK hard gate (`AGENTS.md` §Cấp 3) cần ADR.
Ẩn/hiện cột ở tầng giao hàng là thay đổi rẻ và có thể đảo ngược.
- **`confidence` đã bỏ** (2026-08-18): self-reported, calibration kém → gây hiểu nhầm. Không xuất ra
  CSV và KHÔNG còn là gate DoD. Chất lượng do grounded citations + schema + `extraction_quality` gác.

---

## 11. Orchestrator gộp — `run_user_workflow.py`

`src/pipeline/user_workflow.py::run()` nối: **compile → (ingest L1) → (ingest agent) → output → log done**.
KHÔNG tự scrape, KHÔNG tự chạy agent (handoff bất đồng bộ).

```bash
# 1 lần khi user đổi danh mục
python scripts/compile_users.py --all

# ƯU TIÊN khi rút backlog: bài đã có Gold nhưng thiếu L1 — xong L1 là giao được ngay
python scripts/l1_route.py --only gold-ready --all

# mỗi chu kỳ (sau khi cron scrape xong):
python scripts/l1_route.py --review missed          # phát packet L1
python scripts/agent_export.py                      # phát packet agent (nên scope theo union subscription)
#   → [agent ngoài xử lý *.task.json, nộp *.json vào 2 thư mục]
python scripts/run_user_workflow.py \               # nạp 2 lớp + gate + ghi output
    --l1-dir data/agent_outputs_l1 \
    --agent-dir data/agent_outputs \
    --date today
```

Chỉ ghi output từ dữ liệu đã ingest sẵn: `python scripts/write_user_output.py --date today`.

---

## 12. Idempotency & Resume

- **DB**: `l1_outputs`/`agent_outputs` UNIQUE theo article → ingest lại trả **cached**, không double-mark.
- **File**: `write()` rewrite **toàn tập** per (user, ngày) + dedupe theo `article_id` → chạy lại **không nhân đôi**.
- **Checkpoint**: `_checkpoint.json.written[date] = {article_id: gold_status}`; thứ tự
  **replace file → mark** đảm bảo ngắt giữa chừng vẫn an toàn (lần sau ghi lại phần còn thiếu).
  Định dạng cũ (list id) vẫn đọc được (status rỗng).

  **Checkpoint có cần không? (rà 2026-09-07)** — Nó KHÔNG quyết định nội dung output: idempotency
  đến từ rewrite toàn tập + `os.replace` + dedupe `article_id`. Vai trò thật là **sổ cái giao hàng**:
  nguồn duy nhất trả lời "bài nào mới" và "bài nào vừa được Gold bổ sung". Với gate L1-only, một bài
  có thể giao ở `L1_ONLY` rồi vòng sau mới `GOLD` — nếu chỉ lưu list id thì "đã ghi" không còn đồng
  nghĩa "đã giao đủ". Vì vậy **giữ checkpoint** nhưng lưu kèm `gold_status`;
  `ckpt.filter_upgraded()` cho ra danh sách bài vừa nâng cấp, hiện trong log
  `rows=N (new=X upgraded=Y l1_only=Z)`.

---

## 13. Bản đồ file (mới cho luồng này)

| File | Vai trò |
|------|---------|
| `src/users/compile.py` | xlsx↔yaml, `compile_user/compile_all`, `load_manifest/enabled_users` |
| `src/export/user_output.py` | `UserOutputWriter` — gate + route + ghi CSV |
| `src/export/checkpoint.py` | checkpoint per-user theo article_id |
| `src/pipeline/user_workflow.py` | `run()` orchestrator + `union_subscription()` |
| `scripts/compile_users.py` | CLI compile |
| `scripts/make_user_template.py` | sinh template / seed xlsx |
| `scripts/write_user_output.py` | CLI ghi output |
| `scripts/run_user_workflow.py` | CLI orchestrator end-to-end |
| `tests/test_compile_users.py`, `test_user_output.py`, `test_user_checkpoint.py`, `test_user_workflow.py` | 13 test |

Tái dùng: `src/agent/entities.py` (select/subscribers_for), `l1_runner.py`, `runner.py`,
`db/store.py` (l1_outputs/agent_outputs), `export/csv_export.py` (utf-8-sig).

---

## 14. Vận hành: thủ công vs tự động & cách automate

### 14.1 Phân loại từng script — ai chạy, khi nào

| Script / bước | Ai thực hiện | Tần suất | Tự động hoá? |
|---------------|--------------|----------|--------------|
| `make_user_template.py` | **NGƯỜI DÙNG** | 1 lần khi tạo user mới | không cần (thủ công) |
| điền `<name>_news.xlsx` + `manifest.yaml` | **NGƯỜI DÙNG** | khi thêm/sửa danh mục theo dõi | không (đầu vào của con người) |
| `compile_users.py --all` | NGƯỜI DÙNG *hoặc* cron | sau khi đổi input (hoặc đầu mỗi lần chạy) | ✅ (run_user_workflow tự gọi) |
| scrape cycle (`orchestrator.py`/`run_once.py`) | **FRAMEWORK** | liên tục, mỗi ~15′ | ✅ cron/scheduler |
| `l1_route.py` (phát packet L1) | **FRAMEWORK** | theo lô, vài lần/ngày | ✅ cron |
| **[PROMPT AGENT] xử lý packet L1** | **AGENT (cần prompt)** | sau mỗi lô L1 | ⚠️ bán tự động (xem §14.4) |
| `l1_ingest.py <dir>` | **FRAMEWORK** | sau khi agent nộp | ✅ cron |
| `agent_export.py` (phát packet bóc tách) | **FRAMEWORK** | theo lô | ✅ cron |
| **[PROMPT AGENT] xử lý packet bóc tách** | **AGENT (cần prompt)** | sau mỗi lô agent | ⚠️ bán tự động (xem §14.4) |
| `agent_ingest.py <dir>` | **FRAMEWORK** | sau khi agent nộp | ✅ cron |
| `run_user_workflow.py` / `write_user_output.py` | **FRAMEWORK** | cuối ngày (hoặc sau mỗi lô) | ✅ cron |

Quy tắc gọn: **con người chỉ chạm 2 việc** — (a) khai báo entity (Excel/manifest), (b) cấu hình/kích agent.
Mọi thứ còn lại là script tất định (deterministic) chạy được bằng cron.

### 14.2 Nhịp trong ngày (timeline lý tưởng)

```
LIÊN TỤC  mỗi 15′ : scrape → silver → work_packages          (đã có, cron)
KHI ĐỔI INPUT     : compile_users.py --all                   (người dùng, tức thời)
THEO LÔ / CUỐI NGÀY:
   l1_route ─▶ [AGENT L1] ─▶ l1_ingest
   agent_export(scoped) ─▶ [AGENT bóc tách] ─▶ agent_ingest
   run_user_workflow --date today        → users/output/<name>/<ngày>.xlsx
```

- Có thể chạy chuỗi "theo lô" **nhiều lần/ngày** (vd mỗi 2–4h) để output cập nhật liên tục,
  hoặc **1 lần cuối ngày** cho gọn. Idempotent nên chạy trùng vô hại.
- `compile_users` không cần theo lịch — chỉ chạy khi input đổi (hoặc để ngay đầu chuỗi cho chắc).

### 14.3 Hai điểm DUY NHẤT cần prompt agent

| Điểm | Đọc packet | Prompt lấy từ | Nộp ra (để ingest) |
|------|-----------|---------------|--------------------|
| **L1** nhận diện entity | `data/agent_tasks/l1/*.task.json` | `schemas/l1-entity-instructions-v1.md` | `l1-entity-output-v1` `*.json` |
| **Bóc tách** (summary/implication/materiality…) | `data/agent_tasks/*.task.json` | `schemas/agent-instructions-v1.md` | `agent-output-v1` `*.json` |

Runtime **agent-agnostic**: chỉ validate output theo schema + chấm DoD, KHÔNG quy định provider hay cách prompt.
Ép schema theo provider (doc [09](09-agent-io-contract.md) §3): OpenAI `response_format json_schema` ·
Anthropic tool `input_schema` · Gemini `responseSchema` · local/MCP → validate cùng schema.

### 14.4 Automate lý tưởng — biến bán tự động thành full-auto

Điểm chặn duy nhất để full-auto là **bước agent** (hiện cần tác nhân ngoài). Để khép kín:

1. Viết **1 adapter** `scripts/agent_run.py` (chưa có — cần thêm) làm đúng 3 việc:
   `đọc *.task.json` → gọi LLM (API/local) ép JSON theo schema → `ghi *.json` vào thư mục ingest.
   Adapter này là nơi DUY NHẤT chứa prompt/khoá API; phần còn lại giữ nguyên.
2. Khi có adapter, cả chuỗi thành lệnh tất định → cắm thẳng vào **cron / Windows Task Scheduler**.

**Ví dụ lịch (khép kín, sau khi có `agent_run.py`):**
```
# scrape mỗi 15′
*/15 * * * *   python -m src.orchestrator --once
# chu kỳ per-user lúc 18:00 hằng ngày
0 18 * * *     python scripts/compile_users.py --all \
            && python scripts/l1_route.py --review missed \
            && python scripts/agent_run.py --queue l1  --out data/agent_outputs_l1 \
            && python scripts/l1_ingest.py data/agent_outputs_l1 \
            && python scripts/agent_export.py \
            && python scripts/agent_run.py --queue main --out data/agent_outputs \
            && python scripts/agent_ingest.py data/agent_outputs \
            && python scripts/run_user_workflow.py --date today
```
(Windows: gói chuỗi trên vào 1 `.ps1`/`run_daily.ps1` rồi tạo Task Scheduler chạy 18:00; dùng
`.venv\Scripts\python.exe` thay `python`.)

**Nếu KHÔNG viết adapter** (giữ agent thủ công): tách lịch làm 2 mốc — cron chạy `l1_route`+`agent_export`
buổi sáng → người/agent xử lý packet → chiều chạy `*_ingest` + `run_user_workflow`. Vẫn idempotent.

### 14.5 Trạng thái tự động hoá hiện tại

| Thành phần | Trạng thái |
|-----------|-----------|
| scrape · silver · work_packages | ✅ tự động (cron sẵn) |
| L1 code-first route · ingest · agent export/ingest | ✅ script tất định, cron được |
| output writer · checkpoint · compile | ✅ script tất định, cron được |
| **bước agent gọi LLM** | ⚠️ chưa có adapter trong repo (thiết kế agent-agnostic) → cần `scripts/agent_run.py` để full-auto |
| gói chuỗi 1 lệnh `run_daily` | ⚠️ chưa có — hiện chuỗi bằng cron `&&` như §14.4 |

---

## 15. Câu hỏi mở

- Chưa có 1 lệnh gộp cả **phát packet** (`l1_route` + `agent_export` scoped) — hiện tách 2 script.
  Có thể thêm `run_user_workflow --emit` nếu cần.
- Chưa có `scripts/agent_run.py` (adapter gọi LLM) và `scripts/run_daily` (gói chuỗi) — cần cho full-auto (§14.4).
- `agent_export.py` hiện chưa lọc sẵn theo union-subscription; cần thêm bước lọc `work_items` để đạt
  tối ưu "chỉ agent article chạm subscription".
- `exchanges` là tín hiệu thô (chỉ 3 mã sàn) — chưa map sàn theo từng ticker.
