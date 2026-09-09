# Runbook vận hành từng bước — chu kỳ per-user (input → <date>.xlsx)

Cập nhật: 2026-08-19 · Đối tượng: người vận hành chạy tay/bán tự động chuỗi agent per-user.
Bổ trợ cho: [13-per-user-output-workflow](../design/13-per-user-output-workflow.md) (thiết kế),
[agent-prompting-guide](agent-prompting-guide.md) (soạn prompt), [runbook](../runbook.md) (lớp scrape).

**Đọc trước:** cơ chế là **hàng đợi + trạng thái**, KHÔNG đồng bộ theo giờ. Mỗi bài tự đi qua state
machine trong `data/monocle.db`; bạn hỏi tiến độ bằng `db_status.py`, không canh đồng hồ. Mọi bước
**idempotent** — chạy trùng vô hại. `write_user_output` gate **tối thiểu L1**: chỉ cần
`l1_outputs.dod_pass=1` là vào `<date>.xlsx` (routing dựa entity của L1). `agent_outputs.dod_pass=1`
là enrichment TÙY CHỌN — thiếu thì các trường Gold để trống và `gold_status=L1_ONLY`; vòng sau
Gold về là bài tự được ghi đè đầy đủ (rewrite toàn tập nên không nhân đôi).

**Ưu tiên khi rút backlog:** `python scripts/l1_route.py --only gold-ready --all` phát packet L1
cho đúng nhóm bài **đã có Gold đạt DoD nhưng thiếu L1**. Nhóm này Gold đã trả tiền rồi mà vẫn không
giao được (định tuyến cần entity của L1) — xong L1 là vào `<date>.xlsx` ngay, `gold_status=GOLD`.
Ngược lại `scripts/agent_export.py` mặc định `--require-l1`: không bốc bài chưa có L1, khỏi đốt
token Gold cho bài không định tuyến được (dùng `--no-require-l1` nếu cố ý rút backlog cũ).

> **Hệ quả nhịp chạy — Gold trễ L1 đúng 1 vòng.** `run_daily.ps1` xếp `agent_export` TRƯỚC
> `l1_ingest`, nên bài mới hôm nay chưa có `l1_outputs` ⇒ `--require-l1` không bốc; sang vòng sau
> (L1 đã ingest) mới có packet Gold. Không mất bài — `work_items` vẫn `pending` trong hàng đợi.
> Muốn Gold bắt kịp trong cùng ngày: chạy chuỗi `l1_route → [agent L1] → l1_ingest → agent_export
> → [agent Gold] → agent_ingest` (2 nhịp agent), hoặc chấp nhận độ trễ 1 vòng.

Quy ước: mọi lệnh chạy tại thư mục `project/`, dùng `python` (sau khi kích hoạt venv `.\.venv\Scripts\Activate.ps1`) hoặc trỏ trực tiếp `.\.venv\Scripts\python.exe`.

---

## 0. Sơ đồ 1 chu kỳ (7 bước)

```
[1] compile_users --all        (chỉ khi user đổi danh mục — có thể bỏ nếu không đổi)
[2] l1_route --review missed   → phát packet L1   data/agent_tasks/l1/*.task.json
[3] ⟨AGENT L1⟩                  → *.json vào       data/agent_outputs_l1/     ← handoff #1
[4] l1_ingest data/agent_outputs_l1                → l1_outputs.dod_pass
[5] agent_export               → phát packet bóc tách  data/agent_tasks/*.task.json
[6] ⟨AGENT bóc tách⟩            → *.json vào       data/agent_outputs/        ← handoff #2
[7] agent_ingest data/agent_outputs                → agent_outputs.dod_pass
    ─────────────────── GATE ───────────────────
    write_user_output --date today  → users/output/<user>/<ngày>.xlsx
```

Hai ⟨AGENT⟩ là điểm DUY NHẤT cần LLM ngoài (xem §3). Còn lại là script tất định, cron được.

---

## 1. Chuẩn bị MỘT LẦN (setup)

| Việc                                       | Lệnh / thao tác                                                                                         | Khi nào       |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------- |
| venv + deps                                 | xem[deployment §1](deployment.md)                                                                         | 1 lần         |
| Bronze→Silver→work_packages có dữ liệu | `.venv\Scripts\python.exe -m src.morninger` (chạy nền)                                                | luôn bật     |
| Tạo user mới                              | `.venv\Scripts\python.exe scripts\make_user_template.py` → copy `users/subscriptions/_template_news.csv` thành `<name>_news.csv` rồi điền | khi thêm user |
| Bật/tắt user                              | sửa `users/subscriptions/manifest.yaml` (`AnPT: true`)                                                        | khi cần       |

Kiểm tra đã có `work_items` chờ xử lý (nếu trống thì chưa scrape/derive xong):

```powershell
.venv\Scripts\python.exe scripts\db_status.py      # xem mục 7 (work_items theo status)
```

---

## 2. Chu kỳ hằng ngày — CHẠY TAY từng bước

### Bước 1 — Compile input (bỏ qua nếu danh mục user không đổi)

```powershell
.venv\Scripts\python.exe scripts\compile_users.py --all
```

Kết quả: `project/config/entities/users/<name>.yaml`. Có `_unknown.txt` → user gõ sai entity, sửa Excel rồi chạy lại.

### Bước 2 — Phát packet L1

```powershell
.venv\Scripts\python.exe scripts\l1_route.py --review missed
#   --review missed = chỉ tin code-first KHÔNG tự khớp (tiết kiệm)
#   --review all    = tra soát lại tất cả (kỹ hơn, tốn hơn)
```

Kết quả: `data/agent_tasks/l1/<article_id>.task.json` + hàng chờ trong `l1_tasks`.

### Bước 3 — ⟨AGENT L1⟩ xử lý (handoff #1)

Xem §3. Đầu ra: mỗi bài 1 file `data/agent_outputs_l1/<article_id>.json` đúng `l1-entity-output-v1`.

### Bước 4 — Nạp + chấm DoD lớp L1

```powershell
.venv\Scripts\python.exe scripts\l1_ingest.py data/agent_outputs_l1
```

Đóng dấu `l1_outputs.dod_pass=1` (đạt) hoặc `=0` + `dod_reasons` (trượt → sửa, nộp lại; §4).

### Bước 5 — Phát packet bóc tách

```powershell
.venv\Scripts\python.exe scripts\agent_export.py --all       # xuất toàn bộ việc pending
.venv\Scripts\python.exe scripts\agent_export.py --limit 100 # hoặc chỉ định số lượng
```

Kết quả: `data/agent_tasks/<article_id>.task.json` (có `cleaned_text`, `raw_sha256`, `change_state`).

> Lưu ý: Mặc định không tham số sẽ xuất tối đa 20 việc. Dùng `--all` để đồng bộ dung lượng với L1.

### Bước 6 — ⟨AGENT bóc tách⟩ xử lý (handoff #2)

Xem §3 hoặc dùng Skill `agent-file-processor`. Đầu ra: `data/agent_outputs/<article_id>.json` đúng `agent-output-v1`.

### Bước 7 — Nạp + chấm DoD lớp bóc tách

```powershell
.venv\Scripts\python.exe scripts\agent_ingest.py data/agent_outputs
```

Đóng dấu `agent_outputs.dod_pass`.

### CỔNG — Ghi output per-user

```powershell
# Cho chu kỳ hôm nay (nếu dữ liệu vừa cào trong ngày):
.venv\Scripts\python.exe scripts\write_user_output.py --date today

# Cho Backlog cũ / dữ liệu nhiều ngày (KHUYẾN NGHỊ nếu bài xuất bản ngày trước):
.venv\Scripts\python.exe scripts\write_user_output.py --days 30
.venv\Scripts\python.exe scripts\write_user_output.py --date all
```

Kết quả mỗi user: `users/output/<name>/<ngày>.xlsx` + `_checkpoint.json`.
Master audit: `users/output/_master/<ngày>.csv` (toàn bộ bài đạt 2 lớp, không phụ thuộc user subscription).
`<date>.xlsx` = deliverable đã qua cổng. Bài thiếu 1 lớp / không ai đăng ký entity → không xuất (đúng thiết kế).

---

## 2b. Chạy toàn chu kỳ bằng `run_daily.ps1`

```powershell
# 1. Phát packet (mở rộng toàn bộ):
.\scripts\run_daily.ps1 -Mode emit -ExportLimit 0

# 2. Cho Agent chạy Skill agent-file-processor...

# 3. Nạp, Xuất kết quả và TỰ ĐỘNG DỌN DẸP packet trung gian (tiết kiệm I/O OneDrive):
.\scripts\run_daily.ps1 -Mode ingest -Days 30

# Nếu muốn GIỮ LẠI các file task packet và output JSON sau khi nạp:
.\scripts\run_daily.ps1 -Mode ingest -Days 30 -KeepPackets
```

Đã ingest riêng ở bước 4/7 rồi thì bỏ `--l1-dir/--agent-dir` (idempotent, không double-mark).

---

## 3. Hai cách chạy bước ⟨AGENT⟩

### (A) Copy-paste thủ công — dùng LLM ngoài

1. Mở file packet (`data/agent_tasks/l1/<id>.task.json` hoặc `data/agent_tasks/<id>.task.json`).
2. Dán **[SYSTEM]** + **[USER]** theo [agent-prompting-guide §2](agent-prompting-guide.md), ép schema theo provider.
3. Lưu JSON trả về thành `<article_id>.json` vào thư mục ingest đúng lớp.
4. Nhiều bài: dán mảng packet → nhận JSON array → tách từng phần tử thành file riêng.

### (B) Stub — nghiệm thu luồng KHÔNG cần LLM

Sinh output hợp lệ theo quy tắc (không phân tích thật) để test end-to-end:

```powershell
.venv\Scripts\python.exe scripts\agent_stub.py --queue l1   --out data/agent_outputs_l1
.venv\Scripts\python.exe scripts\agent_stub.py --queue main --out data/agent_outputs
```

### (C) Full-auto — adapter gọi API (CHƯA có trong repo)

`scripts/agent_run.py` (cần viết): `đọc *.task.json → gọi LLM ép schema → ghi *.json`. Khi có →
cắm thẳng vào `run_daily.ps1` (§6) / Task Scheduler. Thiết kế: [13 §14.4](../design/13-per-user-output-workflow.md).

### (D) Agent CÓ TOOL FILE — tự đọc packet, tự ghi output (KHÔNG copy-paste, KHÔNG adapter)

Dùng khi agent của bạn có công cụ đọc/ghi file (Claude Code, Cursor, MCP filesystem…). Dán **1 phiếu
giao việc** → agent tự quét packet và tự ghi `<id>.json` vào 2 thư mục ingest. Vận hành:
`run_daily.ps1 -Mode emit` → dán phiếu → `run_daily.ps1 -Mode ingest`.
Phiếu dán sẵn: [agent-runner-prompt.md](agent-runner-prompt.md).

---

## 4. Kiểm tra trạng thái & vòng lặp sửa lỗi

### Xem cả pipeline đang ở đâu

```powershell
.venv\Scripts\python.exe scripts\db_status.py
#   mục 7 = work_items | mục 8 = l1_tasks + l1_outputs.dod_pass | mục 9 = agent_outputs.dod_pass
```

"Lô xong" = mục 8 & 9 có `dod_pass=1` phủ hết bài cần → cổng mới ghi được `<date>.xlsx`.

### Xem bài trượt DoD để sửa trúng

```powershell
python scripts/dbq.py "select article_id,dod_pass,dod_reasons from l1_outputs where dod_pass=0 limit 20"
# Hoặc:
python -c "import sqlite3; [print(r) for r in sqlite3.connect('data/monocle.db').execute('select article_id,dod_pass,dod_reasons from l1_outputs where dod_pass=0 limit 20')]"
# (đổi l1_outputs → agent_outputs cho lớp bóc tách)
```

Sửa đúng điểm trong `dod_reasons` → nộp lại file → chạy lại `*_ingest`. Bài đã `dod_pass=1` nạp lại = cached.

Bảng lỗi thường gặp → cách sửa: [agent-prompting-guide §6](agent-prompting-guide.md).

---

## 5. Đặt lịch (bán tự động, KHÔNG cần adapter)

Tách 2 mốc/ngày — giữa 2 mốc là lúc agent xử lý packet:

```
Sáng (Task Scheduler): l1_route --review missed  →  agent_export        (phát packet)
   ⟨người/agent xử lý packet trong ngày⟩
Chiều (Task Scheduler): l1_ingest → agent_ingest → write_user_output --date today
```

Chạy chuỗi "theo lô" nhiều lần/ngày (vd mỗi 2–4h) để output cập nhật liên tục, hoặc 1 lần cuối ngày.
Idempotent nên trùng vô hại. `compile_users` chỉ chạy khi input đổi.

---

## 6. Full-auto bằng `run_daily.ps1`

Đã kèm `scripts/run_daily.ps1` — chạy cả chuỗi 1 lệnh. Mặc định dùng **stub** cho bước agent
(để test luồng); có `-Agent api` để chuyển sang adapter thật khi `agent_run.py` sẵn sàng:

```powershell
# test toàn luồng bằng stub:
.\scripts\run_daily.ps1
# khi có scripts/agent_run.py (LLM thật):
.\scripts\run_daily.ps1 -Agent api
```

Cắm vào Task Scheduler: Action `powershell.exe -File C:\...\project\scripts\run_daily.ps1`, Start in `project/`.

---

## 7. Câu hỏi mở

- `agent_export.py` chưa lọc theo union-subscription → phát dư packet cho bài không ai theo dõi (tốn agent, không sai kết quả). Cần thêm bước lọc `work_items ∩ union_subscription`.
- `scripts/agent_run.py` (adapter LLM) chưa có → hiện chỉ stub hoặc thủ công.
- Chưa có 1 lệnh gộp cả 2 bước phát packet (`l1_route` + `agent_export`); có thể thêm `run_user_workflow --emit`.
