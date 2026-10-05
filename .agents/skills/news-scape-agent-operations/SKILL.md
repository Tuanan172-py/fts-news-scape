---
name: news-scape-agent-operations
description: Quy trình điều phối chuẩn hóa cho Agent và Subagents trong hệ thống News-Scape (đóng gói Mega-Batch phân tầng ưu tiên, xử lý thống nhất thực thể & nội dung, mở rộng citations bằng index và phân phối Deliverable Excel 2 cột Intent).
---
# News-Scape Agent Operations Skill

> **Mục đích:** Quy trình vận hành chuỗi Agent thống nhất (`agent_article`) từ khâu quét dữ liệu thô, phân tầng ưu tiên (Priority-Queue), đóng gói Mega-Batch 100 bài, kích hoạt Subagent Single-turn Zero-Tool, đối soát Intent độc lập (Dual-Track), mở rộng citations bằng index và bàn giao báo cáo người dùng sớm.

---

## 1. Bản Đồ Quy Trình Khép Kín (Unified Priority Pipeline)

```
[Phase 1: Quét Code-First & Phân Tầng Ưu Tiên (Priority Queue)]
       │
       ├─ Quét dữ liệu Silver/DB ngày hiện tại
       ├─ Code-First quét đối tượng từ điển cứng ({code_entities})
       ├─ Phân loại 3 Tiers:
       │    ├─ TIER 1 (Ưu tiên cao): Khớp Watchlist active (manifest.yaml) hoặc biến động vĩ mô khẩn
       │    └─ TIER 2 & 3 (Hàng đợi nền): VN30 ngoài watchlist, BCTC định kỳ, CBTT, thị trường chung
       │
[Phase 2: Đóng Gói Mega-Batch 1 (100 Bài — Delivery First)]
       │
       ├─ Đóng gói 100 bài Tier 1 thành file packet batch_01.task.json
       ├─ Bắt buộc Compact JSON: json.dumps(..., separators=(',', ':')) (chống tràn dòng >2.000 ký tự)
       ├─ Smart Paragraph Distillation: giữ p0 (Sapo) + đoạn chứa số liệu tài chính / sự kiện
       │
[Phase 3: Kích Hoạt Subagent Thống Nhất (Single-Turn, Zero-Tool)]
       │
       ├─ Kích hoạt agent_article (Model: Flash) với toolFilter: { allow: [] }
       ├─ Prompt-in toàn bộ 100 bài / JSON-out mảng kết quả trong đúng 1 lượt
       ├─ Bóc tách độc lập: intent/thực thể 11 nhóm (e), tóm tắt (s), key points (k), hàm ý (im), sentiment (sn), độ nhạy (ts), citations index (c: [0, 2])
       │
[Phase 4: Expander & Đối Soát Intent Độc Lập (Python tất định — 0 Token)]
       │
       ├─ article_expand.py bù đắp exact substring citations từ chỉ số c: [0, 2] (bảo đảm 100% vượt DoD)
       ├─ Đối soát Intent 2 nguồn: gán nhãn BOTH, LLM_ONLY, CODE_ONLY
       ├─ Ingest vào SQLite (monocle.db) trong transaction BEGIN IMMEDIATE
       │
[Phase 5: Giao Hàng Sớm Cho User (Deliverable First)]
       │
       ├─ Kích hoạt ngay write_user_output.py xuất Excel cho người dùng trong 2–3 phút
       ├─ Bảng dữ liệu chứa 2 cột riêng biệt: intent_llm và intent_code (kèm intent_source)
       │
[Phase 6: Xử Lý Nền Batch 2..N (100% Phủ Kho Dữ Liệu)]
       │
       └─ Tuần tự xử lý các batch tiếp theo để nạp CSDL đầy đủ 100%, không bỏ sót bài viết
```

---

## 2. Thư Viện Lệnh Thực Thi Tiêu Chuẩn (Canonical Execution Commands)

Mọi lệnh BẮT BUỘC thực thi với Python venv cách ly: `& "C:\venvs\news-scape\Scripts\python.exe"` và chạy từ thư mục `project/`.

### Bước 0: Kiểm Tra Tình Trạng Pipeline Qua Radar

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py status
```

### Bước 1: Đóng Gói Mega-Batch Ưu Tiên (Priority-Queue Packaging)

```powershell
# Đóng gói 100 bài Tier 1 (khớp Watchlist + Vĩ mô khẩn) dạng Compact JSON:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_pack.py --date today --priority watchlist --batch-size 100
```

### Bước 2: Kích Hoạt Subagent Xử Lý Thống Nhất

Chạy Subagent qua `invoke_subagent` (Model: Flash) với `toolFilter: { allow: [] }` bằng mẫu prompt tại Mục 3. Subagent nhận task packet qua prompt và trả mảng JSON trực tiếp trong 1 lượt duy nhất.

### Bước 3: Mở Rộng Citations & Nghiệm Thu DoD (Expander & Ingest)

```powershell
# Expander bù citations từ index và đối soát intent chéo vào SQLite:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_expand.py project/data/agent_outputs/batch_01.output.json --ingest
```

### Bước 4: Giao Hàng Excel Sớm Cho Người Dùng (2 Cột Intent)

```powershell
# Xuất deliverable Excel ngay sau Batch 1 cho người dùng active:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/write_user_output.py --date today
```

### Bước 5: Tiếp Tục Xử Lý Nền Các Batch Còn Lại (Batch 2..N)

```powershell
# Đóng gói và xử lý nền toàn bộ bài viết còn lại trong ngày để đạt 100% độ phủ:
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_pack.py --date today --priority background --batch-size 100
```

---

## 3. Mẫu Prompt Chuẩn Hóa Cho Subagent Thống Nhất (`agent_article`)

Nhằm triệt tiêu 100% nguy cơ Subagent bị trượt schema hoặc tự mở vòng lặp Grep/View, Orchestrator BẮT BUỘC sử dụng mẫu prompt sau (truyền qua prompt-in, không cấp công cụ):

```text
Bạn là Unified Article Analyst (tiêu chuẩn H2-H5 / compact schema).
Nhiệm vụ: Phân tích danh sách bài viết tài chính trong payload JSON được đính kèm.

Quy tắc xử lý bất biến (Single-turn, Zero-tool, Citations by Index):
1. Không sử dụng bất kỳ công cụ nào. Chỉ đọc dữ liệu từ tin nhắn và trả về mảng JSON thuần túy.
2. Với mỗi bài trong danh sách:
   - "id": Giữ nguyên article_id.
   - "e": Trích xuất thực thể/intent độc lập theo nhóm (mỗi thực thể gồm {"s": surface, "g": group_code, "in": in_list_bool, "id": entity_id_or_null}). 
     Mã nhóm hợp lệ: TIC (Mã CP), COM (Doanh nghiệp), PER (Lãnh đạo), FND (Quỹ đầu tư), IDX (Chỉ số), EXC (Sàn), IND (Ngành GICS), GEO (Vĩ mô địa lý), THM (Chủ đề vĩ mô), AST (Tài sản), INS (Định chế tài chính).
     Lưu ý: Bóc tách khách quan theo ngữ nghĩa, không phỏng đoán theo mã lạ.
   - "s": Tóm tắt súc tích nội dung sự kiện (1-2 câu ngắn).
   - "k": 1-3 luận điểm tài chính chính (diễn giải bằng lời văn riêng, TUYỆT ĐỐI KHÔNG sao chép nguyên văn đoạn trích).
   - "im": Phân tích hàm ý tài chính đối với doanh nghiệp/dòng tiền/định giá.
   - "sn": Sắc thái bài viết (pos | neg | neu).
   - "ts": Độ nhạy thời gian (urg | today | week | month | arch).
   - "c": Mảng số thứ tự của các đoạn văn bản làm bằng chứng (ví dụ [0, 2]). TUYỆT ĐỐI KHÔNG sao chép chuỗi ký tự dài.
3. Trả về DUY NHẤT một khối mảng JSON [ { ... }, { ... } ] trong phản hồi cuối cùng, không kèm lời mở đầu hoặc kết luận.
```

---

## 4. Ràng Buộc Bất Biến & An Toàn Vận Hành (Production Invariants)

1. **Bắt Buộc Compact JSON**:
   - Khi ghi file task packet, luôn dùng `json.dumps(obj, separators=(',', ':'))`. Không định dạng thụt đầu dòng `indent=2` trên các bài viết có đoạn văn dài để chống lỗi cắt dòng của parser.
2. **Nguyên Lý Bảo Đảm Bằng Xây Dựng (Guaranteed by Construction)**:
   - LLM chỉ chọn index đoạn `c: [0, 2]`.
   - Script Python bên ngoài trích xuất exact substring $\ge 20$ chars trực tiếp từ mảng `p[]` gốc. Tỷ lệ vượt qua cổng DoD citations là 100%, loại bỏ hoàn toàn nhu cầu Subagent tự kiểm tra lại.
3. **Đối Soát Intent Hai Kênh (Dual-Track Reconciliation)**:
   - Output Excel bắt buộc phân định rõ:
     - `intent_llm`: Nhận diện ngữ nghĩa từ Subagent.
     - `intent_code`: Nhận diện từ điển cứng từ Code-First.
     - `intent_source`: `BOTH`, `LLM_ONLY`, hoặc `CODE_ONLY`.
4. **Phân Tuyến Ưu Tiên Giao Hàng Nhanh**:
   - Ưu tiên tối thượng là giao file Excel cho người dùng trong vòng 2–3 phút đầu tiên thông qua Batch 1.
   - Không được phép trì hoãn việc giao hàng cho đến khi toàn bộ hàng đợi kết thúc.
