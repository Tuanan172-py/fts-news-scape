---
name: news-scape-agent-operations
description: Quy trình điều phối chuẩn hóa cho Agent và Subagents trong hệ thống News-Scape (định tuyến L1, nạp Code-First, bóc tách thực thể L1, xuất tác vụ Gold v2-lean, nghiệm thu DoD Ingest và phân phối Deliverable Excel).
---

# News-Scape Agent Operations Skill

> **Mục đích:** Đóng gói trọn vẹn toàn bộ quy trình vận hành chuỗi Agent đa tầng (Master Orchestrator, Subagents L1, Subagents Gold) từ khâu quét dữ liệu thô, lọc phân tuyến, xuất tác vụ, gọi Subagents cho đến nghiệm thu Definition-of-Done (DoD) và bàn giao báo cáo người dùng. Giúp Agent tự động hóa 100% các bước mà không phải dò tìm script hay lặp lại các bước thủ công.

---

## 1. Bản Đồ Quy Trình Khép Kín (5-Phase End-to-End Pipeline)

```
[Phase 1: Thu thập & Định tuyến L1]
       │
       ├─ Quét dữ liệu Silver/DB ngày hiện tại
       ├─ L1 Router (review="missed"): Phân loại Code-First (resolved) vs Cần Agent (needs_agent)
       └─ Vật chất hóa Code-First vào l1_outputs (0 token, 100% tiết kiệm)
       │
[Phase 2: Đóng gói Mini-Batches L1 & Phân phối Subagents]
       │
       ├─ Gom lô các bài needs_agent thành l1_batch_XX.task.json (25 bài/lô)
       └─ Gọi Subagents l1_entity_matcher (Model: Flash) xử lý theo Controlled Wave (2–3 batches/đợt)
       │
[Phase 3: Nghiệm thu DoD L1 (L1 Ingest) & Dọn Dẹp Archive]
       │
       ├─ Ghi nhận kết quả vào project/data/agent_outputs_l1/l1_batch_XX.output.json
       ├─ Chạy: python scripts/l1_ingest.py data/agent_outputs_l1/<batch>.output.json
       ├─ Cập nhật l1_outputs và tự động archive task packets đạt DoD
       └─ Xóa file task packet trong data/agent_tasks/l1/ sau khi hoàn tất
       │
[Phase 4: Xuất Tác vụ Gold Subscriber-Gated (v2-lean)]
       │
       ├─ Lọc Subscriber-Gating: chỉ xuất bài khớp Watchlist người dùng active
       ├─ Cắt tỉa DOM Dynamic 3-Pass Pruner (<= 2.200 chars), nhúng input.l1_entities
       ├─ Gom lô thành batch_XX.task.json (5 bài/lô theo chuẩn schema agent-output-v2-lean)
       └─ Gọi Subagents gold_financial_analyst (Model: Flash) phân tích chuyên sâu
       │
[Phase 5: Nghiệm thu DoD Gold & Phân phối Deliverable]
       │
       ├─ Ghi nhận output vào project/data/agent_outputs/batch_XX.output.json
       ├─ Chạy: python scripts/agent_ingest.py data/agent_outputs
       └─ Xuất file Excel cá nhân hóa: python scripts/write_user_output.py --date all
```

---

## 2. Thư Viện Lệnh Thực Thi Tiêu Chuẩn (Canonical Execution Commands)

Mọi lệnh BẮT BUỘC thực thi với Python venv cách ly: `& "C:\venvs\news-scape\Scripts\python.exe"` và chạy từ thư mục `project/`.

### Bước 1: Quét và Vật chất hóa L1 Code-First
```powershell
# Chạy vật chất hóa toàn bộ bài Code-First (0 token) vào l1_outputs:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py --code-first
```

### Bước 2: Đóng gói Batch Tác vụ L1 Cho Subagents
Khi phát hiện các bài viết `needs_agent`, hệ thống đóng gói thành mini-batch 25 bài/lô:
```python
from src.agent.batch_handoff import split_l1_tasks_into_batches
# Đầu ra: data/agent_tasks/l1/l1_batch_XX.task.json (25 bài/lô)
```

### Bước 3: Nghiệm thu DoD L1 Ingest & Dọn Dẹp
Sau khi Subagents hoàn tất và xuất file output:
```powershell
# Ingest 1 batch cụ thể:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py data/agent_outputs_l1/l1_batch_XX.output.json

# Hoặc ingest toàn bộ thư mục output L1:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py data/agent_outputs_l1
```

### Bước 4: Xuất Tác vụ Gold (Subscriber-Gated & Lean Schema)
```powershell
# Xuất các bài thỏa mãn Watchlist người dùng cho ngày hiện tại (hoặc ngày chỉ định):
& "C:\venvs\news-scape\Scripts\python.exe" scripts/agent_export.py `
    --date 2026-09-14 `
    --require-l1 `
    --subscriber-only `
    --limit 10000 `
    --no-sync
```
Sau đó đóng gói thành các mini-batches Gold (5 bài/lô):
```python
from src.agent.batch_handoff import split_tasks_into_batches
# Đầu ra: data/agent_tasks/batch_XX.task.json (5 bài/lô)
```

### Bước 5: Nghiệm thu DoD Gold Ingest & Giao hàng
```powershell
# Ingest và nghiệm thu 100% DoD cho các output Gold:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/agent_ingest.py data/agent_outputs

# Biên dịch và xuất Deliverable Excel cho toàn bộ người dùng active:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date all
```

---

## 3. Mẫu Prompt Handoff Chuẩn Hóa Cho Subagents (Anti-Drift & Anti-Burn)

Nhằm triệt tiêu 100% nguy cơ Subagent bị trượt schema hoặc gọi discovery loops thừa, Orchestrator BẮT BUỘC sử dụng mẫu prompt sau khi kích hoạt qua `invoke_subagent`:

### A. Mẫu Prompt Kích Hoạt Subagent L1 (`l1_entity_matcher`)
```text
Bạn là L1 Entity Matcher (tiêu chuẩn H2-H5 / l1-entity-output-v1).
Nhiệm vụ: Xử lý file task gom lô L1: `<ABSOLUTE_PATH>/l1_batch_XX.task.json`.

Quy tắc xử lý bất biến (Strict 2-I/O & Zero-Leakage):
1. Đọc file task bằng tool `view_file` DUY NHẤT một lần. CẤM gọi grep, find, list_dir để quét từ điển ngoài nhằm tránh tốn token và rate limit.
2. Với mỗi task trong danh sách:
   - Đọc article_id, title.
   - Bóc tách thực thể theo Ontology 10 Miền (TICKER, ETF, INDEX, EXCHANGE, INDUSTRY_GICS1/2/3, MACRO_GEO, MACRO_THEME, ASSET_CLASS, INSTITUTION).
   - Kiểm tra exact substring: surface và citations[].source_span BẮT BUỘC là chuỗi con nguyên văn của title.
   - Chống false positive: "Mỹ" trong "Mỹ Tho", "Mỹ Thuận", "Mỹ Đình" KHÔNG gán MACRO_GEO:MY; "PGD" của ngân hàng KHÔNG gán TICKER:PGD.
   - Định dạng entity object BẮT BUỘC có đủ: {"surface": str, "type": str, "method": "semantic", "in_list": bool, "entity_id": str or null, "confidence": float}.
   - Phân định in_list: Chỉ gán in_list: true nếu thuộc catalog chính thức (TICKER: 3 chữ cái, INDEX: VNINDEX/VN30, EXCHANGE: HOSE/HNX/UPCOM, MACRO_GEO: MY, TRUNG_QUOC, EU, NHAT_BAN, HAN_QUOC, NGA, DONG_NAM_A, AN_DO; INSTITUTION: NHNN, UBCKNN, BO_TAI_CHINH, FED, ECB, BOJ, WB_IMF). Nếu ngoài catalog: gán in_list: false, entity_id: null và đưa tên vào unlisted_candidates.
   - Nếu có thực thể: recognized: true, entities: [...], citations: [{"source_span": surface}], cập nhật categories tương ứng ("done" nếu có in_list, "out_of_list" nếu chỉ có unlisted).
   - Nếu không có thực thể: recognized: false, entities: [], citations: [], tất cả categories là "none".
   - processing_metadata: {"agent_provider": "antigravity", "model_used": "flash", "timestamp": "<ISO_NOW>", "schema_version": "1.0"}.
3. Gom kết quả thành mảng JSON và dùng `write_to_file` ghi trực tiếp đè vào file:
`<ABSOLUTE_PATH>/l1_batch_XX.output.json` (Overwrite: true).
4. Kết thúc và báo cáo số bài recognized/none.
```

### B. Mẫu Prompt Kích Hoạt Subagent Gold (`gold_financial_analyst`)
```text
Bạn là Chuyên viên Phân tích Tài chính Gold Cấp cao (tiêu chuẩn H2-H5 / schema agent-output-v2-lean).
Nhiệm vụ: Xử lý gói tác vụ Gold gom lô: `<ABSOLUTE_PATH>/batch_XX.task.json`.

Quy tắc xử lý bất biến (Strict 2-I/O & Grounded Citations):
1. Đọc file task bằng tool `view_file` DUY NHẤT một lần. CẤM gọi discovery tools.
2. Với mỗi task trong tasks[]:
   - Tận dụng input.l1_entities có sẵn để tập trung suy luận tác động tài chính.
   - Tóm tắt súc tích: summary (abstractive) và key_points (1-3 điểm chính).
   - Phân tích implication: tác động cụ thể đến doanh thu, dòng tiền, định giá và cổ phiếu liên quan.
   - Đánh giá sentiment: positive | negative | neutral.
   - Xác định time_sensitivity: immediate | short_term | medium_term.
   - Trích xuất citations: mảng các chuỗi NGUYÊN VĂN (>= 2 trích dẫn, mỗi trích dẫn >= 20 ký tự) lấy chính xác từ cleaned_text.
3. Gom kết quả thành mảng JSON gồm 7 trường cốt lõi (v2-lean) và ghi đè vào file:
`<ABSOLUTE_PATH>/batch_XX.output.json` bằng tool `write_to_file` (Overwrite: true).
4. Báo cáo hoàn tất kèm danh sách article_id và sentiment.
```

---

## 4. Ràng Buộc Bất Biến & Chống Lỗi (Production Invariants & Guardrails)

1. **Ràng buộc UTF-8 Encoding (Chống Mojibake)**:
   - Khi đọc/ghi file JSON kết quả giữa Subagents và Workspace, luôn sử dụng `encoding="utf-8"`, `ensure_ascii=False`.
   - Nếu gặp lỗi encoding ký tự tiếng Việt dạng byte Latin1/CP1252, giải mã lại bằng `s.encode('latin1').decode('utf-8')`.

2. **Ràng buộc I/O Concurrency & Đường dẫn Tuyệt đối**:
   - Khi gọi script thông qua `run_command`, luôn đặt `Cwd: <PROJECT_ROOT>` hoặc sử dụng đường dẫn tương đối đúng cấp bậc (`scripts/...`).
   - Mọi thao tác ghi deliverable và DB đều tuân thủ Single-Writer và Staging Atomic Write để chống conflict OneDrive.

3. **Chiến lược Điều phối Subagent Có Kiểm soát (Controlled Wave Dispatch)**:
   - Tuyệt đối không phóng cùng lúc hàng chục Subagent để tránh lỗi `RESOURCE_EXHAUSTED` (Rate Limit 429).
   - Chia thành các đợt (waves): **2–3 batches/đợt** cho L1 (50–75 bài) và **2 batches/đợt** cho Gold (10 bài).
   - Chờ hoàn tất và nghiệm thu xong đợt hiện tại mới kích hoạt đợt kế tiếp.

4. **Bảo đảm Definition-of-Done (DoD Schema Contract)**:
   - **L1 Output**: BẮT BUỘC `surface` và `source_span` là exact substring của `title`. Chỉ đánh dấu `categories.<nhóm>: "done"` khi có entity `in_list: true` thuộc nhóm đó.
   - **Gold Output (`v2-lean`)**: BẮT BUỘC gồm 7 trường phẳng (`article_id`, `summary`, `key_points`, `implication`, `sentiment`, `time_sensitivity`, `citations`). `citations` là mảng các chuỗi nguyên văn $\ge 20$ ký tự lấy từ `cleaned_text`. Không chứa metadata kỹ thuật rườm rà.
