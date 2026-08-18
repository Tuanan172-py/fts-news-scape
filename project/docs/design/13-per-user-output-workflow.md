# Thiết kế — Quy trình end-to-end lớp NGƯỜI DÙNG (input → output)

Cập nhật: 2026-08-18 · Đối tượng: dev/vận hành muốn chạy từ input user tới khi có CSV output.
Tham chiếu chéo: [00-end-to-end-architecture](00-end-to-end-architecture.md),
[09-agent-io-contract](09-agent-io-contract.md), [10-agent-orchestration-governance](10-agent-orchestration-governance.md).

---

## 1. Mục tiêu & nguyên tắc chốt

Input cấp cao nhất = **thư mục theo user**. Hệ thống chạy các lớp agent rồi xuất **CSV cuối cho từng
user**, lọc theo entity user đăng ký, phân theo ngày. Idempotent, resume theo `article_id`.

Quyết định thiết kế (chốt 2026-08-18):
- **Gate output** = `l1_outputs.dod_pass=1` **AND** `agent_outputs.dod_pass=1` (L1 phải agent-reviewed).
- **Phạm vi agent** = chỉ article có entity giao với **union subscription** của user đang bật.
- **Scrape TÁCH** khỏi workflow (`--skip-scrape` mặc định — giả định cron đã scrape).
- **Bật/tắt user** = `users/input/manifest.yaml` (vắng tên = mặc định BẬT).
- **Không notify** giai đoạn này — chỉ `logger.info("done …")`.

---

## 2. Sơ đồ tổng thể

```
STAGE 0  users/input/<name>/entities.xlsx   +  users/input/manifest.yaml    (USER nhập tay)
   │           scripts/compile_users.py --all
STAGE 1  → project/config/entities/users/<name>.yaml   (+ _unknown.txt)      → EntityRegistry
   │
STAGE 2  scrape → bronze(raw_html) → silver → work_packages(work_items)      (ĐÃ CÓ, cron)
   │
STAGE 3  L1:  l1_route.py → packet → [AGENT] → l1_ingest.py → l1_outputs.dod_pass=1
   │
STAGE 4  Agent: agent_export.py(scoped) → packet → [AGENT] → agent_ingest.py → agent_outputs.dod_pass=1
   │           GATE: cả 2 dod_pass=1
STAGE 5  → subscribers_for(entities) ∩ enabled → users/output/<name>/<YYYY-MM-DD>/{L1,agent,final}.csv
                                                 + _checkpoint.json · log "done"
```

`[AGENT]` = agent NGOÀI (provider bất kỳ do bạn điều khiển), prompt theo `schemas/*-instructions-v1.md`.
Runtime chỉ **phát packet** + **nạp & chấm DoD**, không nhúng LLM.

---

## 3. Cấu trúc thư mục

```
users/                              (REPO ROOT, sibling của project/)
├── input/
│   ├── manifest.yaml               # bật/tắt user
│   ├── <name>/entities.xlsx        # USER nhập
│   └── <name>/_unknown.txt         # (auto) entity nhập sai
├── output/
│   └── <name>/<YYYY-MM-DD>/{L1.csv, agent.csv, final.csv}
│       + <name>/_checkpoint.json
└── template/entities_template.xlsx # mẫu có dropdown
project/config/entities/users/<name>.yaml    # (auto) config máy đọc
```

---

## 4. STAGE 0 — USER khai báo input

### 4.1 File Excel `users/input/<name>/entities.xlsx`
Sheet `entities`: mỗi **cột** = 1 nhóm, mỗi **dòng** = 1 giá trị. Sheet `meta`: `user`, `note`.

| Cột | Nhập gì | Nguồn tra trong `data/entities/entities.xlsx` | Ví dụ |
|-----|---------|-----------------------------------------------|-------|
| `tickers` | **code** | sheet `Securities`.code | `HPG`, `FPT` |
| `etfs` | **code** | `Securities`(ETF).code | `E1VFVN30` |
| `indices` | **code** | `Indices`.code | `VNINDEX`, `VN30` |
| `exchanges` | **code** | `Exchanges`.code | `HOSE`, `HNX` |
| `industries` | **code** ngành GICS | `Industries`.code | `THEP`, `NGAN_HANG` |
| `entities` | **entity_id** (cửa thoát) | cột `entity_id` | `TICKER:HPG` |

- Nhóm dùng code tự viết hoa khi compile (`hpg`→`HPG`, `thep`→`THEP`). `industries` khớp theo **CODE** ngành GICS (KHÔNG theo tên).
- Lấy template: `python scripts/make_user_template.py` → `users/template/entities_template.xlsx`.
- Seed từ config yaml có sẵn: `python scripts/make_user_template.py --seed <name>`.

### 4.2 `users/input/manifest.yaml`
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

**L1 done** = `l1_outputs.dod_pass=1` (schema + grounding surface/citation ⊂ title + confidence≥0.60).

---

## 8. STAGE 4 — Agent bóc tách (handoff, giới hạn phạm vi)

| Bước | Lệnh / module | Ghi ra |
|------|---------------|--------|
| export | `scripts/agent_export.py` → `AgentRunner.export_tasks()` | packet `data/agent_tasks/<id>.task.json` |
| agent | AGENT ngoài (prompt theo `schemas/agent-instructions-v1.md`) | `agent-output-v1` `*.json` |
| ingest | `scripts/agent_ingest.py <dir>` → `AgentRunner.ingest_output()` | `agent_outputs` (+ `dod_pass`) |

**Trường agent phải thêm** (`agent-output-v1`): `summary.abstractive` + `key_points`, `implication.text`
+ `impact_area`, `materiality.score` + `time_sensitivity`, (tuỳ chọn) `sentiment`, `event_type`; `citations`≥2.
**Agent done** = `agent_outputs.dod_pass=1` (confidence≥0.65, ≥2 citation ⊂ cleaned_text, extraction_quality∈{high,medium}).

**Giới hạn phạm vi (tiết kiệm):** chỉ nên export article có entity ∈ `union_subscription(registry, enabled)`
(`src/pipeline/user_workflow.py::union_subscription`). Article không ai theo dõi → không cần agent.

---

## 9. STAGE 5 — Output per-user (gated)

`scripts/write_user_output.py` → `src/export/user_output.py::UserOutputWriter.write()`:

1. **`gated_rows()`** — JOIN (`_GATED_SQL`):
   `articles ⨝ l1_outputs(dod_pass=1) ⨝ agent_outputs(dod_pass=1)` trên `url_title_hash`.
   Lọc theo `--date today|YYYY-MM-DD` hoặc `--days N` (dùng `published_at`, fallback `fetched_at`).
2. **Định tuyến** — entity của article = `l1_outputs.entities[in_list].entity_id`;
   `subscribers_for(eset)` ∩ `enabled`; mỗi user lấy `matched = eset ∩ resolve_subscription(user)`.
3. **Ghi 3 file/ngày** (atomic temp + `os.replace`, utf-8-sig):
   - `L1.csv` — dump lớp L1 (audit): article_id, date, title, entities, l1_confidence, categories.
   - `agent.csv` — dump lớp agent (audit).
   - `final.csv` — **deliverable gated** (xem cột §10).
4. **Checkpoint** — `src/export/checkpoint.py::mark_written()` cập nhật `_checkpoint.json` **SAU** khi
   `final.csv` đã replace (crash-safe). `logger.info("done user=… date=… rows=…")`.

Article thiếu 1 lớp, hoặc không ai đăng ký entity → **không** vào `final.csv`.

---

## 10. Định dạng `final.csv`

`article_id, date, source_domain, url, title, matched_entities, summary, key_points, implication,
impact_area, materiality_score, time_sensitivity, sentiment, event_type, confidence`

- `matched_entities` = **code** các entity user đăng ký MÀ article chạm (join `;`).
- `summary`←`summary.abstractive`; `key_points`←`summary.key_points`; `implication`←`implication.text`;
  `materiality_score`←`materiality.score`; `sentiment`←`sentiment.polarity`; `confidence`←agent `confidence`.
- Flatten null-safe: field agent tuỳ chọn thiếu → ô rỗng, không lỗi.

---

## 11. Orchestrator gộp — `run_user_workflow.py`

`src/pipeline/user_workflow.py::run()` nối: **compile → (ingest L1) → (ingest agent) → output → log done**.
KHÔNG tự scrape, KHÔNG tự chạy agent (handoff bất đồng bộ).

```bash
# 1 lần khi user đổi danh mục
python scripts/compile_users.py --all

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
- **Checkpoint**: `_checkpoint.json.written[date] = [article_id…]`; thứ tự **replace file → mark** đảm bảo
  ngắt giữa chừng vẫn an toàn (lần sau ghi lại phần còn thiếu). Resume theo `article_id` (yêu cầu đã chốt).

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
| điền `entities.xlsx` + `manifest.yaml` | **NGƯỜI DÙNG** | khi thêm/sửa danh mục theo dõi | không (đầu vào của con người) |
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
   run_user_workflow --date today        → users/output/<name>/<ngày>/final.csv
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
