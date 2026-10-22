# Runbook — Rút backlog tồn đọng (L1 & Gold)

Cập nhật: 2026-09-07 · Đối tượng: người vận hành + agent L1/Gold.
Tham chiếu: [daily-runbook-per-user](daily-runbook-per-user.md),
[13-per-user-output-workflow](../design/13-per-user-output-workflow.md).

---

## 0. Nguyên tắc chốt

Gate export là **L1-only**: `l1_outputs.dod_pass=1` là điều kiện CỨNG (định tuyến cần entity của
L1), Gold là enrichment TÙY CHỌN. Hệ quả trực tiếp cho việc rút backlog:

- **L1 là nút cổ chai, không phải Gold.** Không có L1 thì bài không map được vào danh mục của
  bất kỳ user nào — dù Gold đã chạy xong.
- **Không chạy agent cho bài không có dòng trong `articles`.** Gate là `articles ⨝ l1_outputs`,
  nhóm đó vĩnh viễn không ra `<date>.xlsx` (xem §4).

Bắt đầu mọi phiên rút backlog bằng:

```powershell
cd project
.venv\Scripts\python.exe scripts\l1_backlog.py
```

Lệnh này CHỈ ĐỌC — kiểm kê tồn đọng, xếp hạng T1..T4 và in sẵn chuỗi lệnh cho từng bậc.

---

## 1. T1 — `gold-ready`: lời nhất, tốn 0 token Gold

Bài **đã có Gold đạt DoD nhưng thiếu L1**. Token Gold đã tiêu rồi mà không giao được bài nào.
Chạy xong L1 là vào thẳng `<date>.xlsx` với `gold_status=GOLD`, đầy đủ summary + key_points.

```powershell
# 1. Phát packet L1 gom lô 25 bài/file
.venv\Scripts\python.exe scripts\l1_route.py --only gold-ready --all --mini-batch 25

# 2. [AGENT L1] xử lý data/agent_tasks/l1/l1_batch_XX.task.json
#    → ghi mảng JSON vào data/agent_outputs_l1/l1_batch_XX.output.json
#    Prompt: .agents/skills/l1-entity-matcher/SKILL.md (§5 Batch Mode)

# 3. Nạp + giao hàng
.venv\Scripts\python.exe scripts\l1_ingest.py data\agent_outputs_l1
.venv\Scripts\python.exe scripts\write_user_output.py --date all
```

Đối chiếu kết quả: log của bước 3 in `rows=N (new=X upgraded=Y l1_only=Z)`. Bài T1 sẽ hiện ở
`new=`, và `gold_status` trong CSV phải là `GOLD` (không phải `L1_ONLY`).

---

## 2. T2 — `in-articles`: mở khoá cho Gold

Bài chưa L1 chưa Gold, nhưng **có dòng trong `articles`**. Chạy L1 xong thì:
- vào `<date>.xlsx` ngay dạng `L1_ONLY` (có title/entity, chưa có summary/key_points), và
- **mở khoá** cho `agent_export.py` bốc Gold (mặc định `--require-l1`).

```powershell
.venv\Scripts\python.exe scripts\l1_route.py --only in-articles --all --mini-batch 25
# [AGENT L1] xử lý l1_batch_XX.task.json
.venv\Scripts\python.exe scripts\l1_ingest.py data\agent_outputs_l1
```

`--only in-articles` loại sẵn nhóm mồ côi T4 — đừng dùng `--only all` khi rút backlog.

---

## 3. T3 — Gold: chỉ bốc bài đã có L1

```powershell
# --require-l1 BẬT mặc định: không bốc bài chưa có L1
.venv\Scripts\python.exe scripts\agent_export.py --limit 50 --mini-batch 10

# [AGENT GOLD] xử lý data/agent_tasks/batch_XX.task.json
#    → ghi mảng JSON vào data/agent_outputs/batch_XX.output.json
#    Prompt: .agents/skills/gold-financial-analyst/SKILL.md (§4 Batch Mode)

.venv\Scripts\python.exe scripts\agent_ingest.py data\agent_outputs
.venv\Scripts\python.exe scripts\write_user_output.py --date all
```

Bài đã giao ở `L1_ONLY` nay được ghi đè đầy đủ; log hiện ở `upgraded=`.
Cắt ngắn giữa chừng vì hết quota **không hỏng gì** — bài chưa tới lượt vẫn nằm trong `<date>.xlsx`
dạng `L1_ONLY` và tự nâng cấp ở vòng sau (`write()` rewrite toàn tập, idempotent).

Chỉ dùng `--no-require-l1` khi **cố ý** rút backlog Gold cũ, chấp nhận packet thiếu
`input.l1_entities` và bài chưa chắc giao được.

---

## 4. T4 — Mồ côi: KHÔNG chạy agent

Có `work_items` / `l1_tasks` (kèm file work-package với `source_url` hợp lệ) nhưng **không có
dòng nào trong bảng `articles`**. Gate export không bao giờ chạm tới nhóm này.

Đếm:

```sql
SELECT COUNT(*) FROM l1_outputs l1 WHERE l1.dod_pass = 1 AND NOT EXISTS
  (SELECT 1 FROM articles a WHERE a.url_title_hash = l1.article_id);
```

Đây là **lỗi ghi `articles` ở Bronze/Silver**, phải sửa code — không phải việc của agent.
Chạy L1/Gold cho nhóm này là đốt token vô ích. Chi tiết: `docs/SESSION-LATEST.md`.

---

## 5. Thứ tự trong ngày & độ trễ 1 vòng

`run_daily.ps1` xếp `agent_export` TRƯỚC `l1_ingest`, nên bài mới trong ngày chưa có `l1_outputs`
⇒ `--require-l1` không bốc; sang vòng sau mới có packet Gold. **Không mất bài** — `work_items`
vẫn `pending` trong hàng đợi.

Muốn Gold bắt kịp trong cùng ngày, chạy chuỗi 2 nhịp agent:

```
l1_route → [AGENT L1] → l1_ingest → agent_export → [AGENT GOLD] → agent_ingest → write_user_output
```

---

## 6. Kiểm chứng sau mỗi vòng

```powershell
.venv\Scripts\python.exe scripts\l1_backlog.py          # T1/T2/T3 phải giảm
.venv\Scripts\python.exe scripts\db_status.py
```

- `_master/<date>.csv` có cột `gold_status` (`GOLD`/`L1_ONLY`) và `noise_signals` (chẩn đoán,
  chưa dùng làm gate).
- `_master/<date>_agent.csv` chỉ chứa bài `gold_status=GOLD`.
- `users/output/<user>/_checkpoint.json` lưu `{article_id: gold_status}` — tra nhanh bài nào
  đã giao đủ, bài nào còn chờ Gold.
