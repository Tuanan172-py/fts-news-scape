---
name: pipeline-radar
description: Trinh sát trạng thái Article Lane end-to-end, phát hiện điểm nghẽn và in đúng một lệnh kế tiếp cho phiên điều phối.
---
# Pipeline Radar — Article Lane

> **Mục tiêu cốt lõi:** trả lời được câu hỏi *"Hôm nay đã cào bao nhiêu bài, bao nhiêu đã phân tích, đợt gần nhất đang ở nửa nào, DB có ghi được không, và lệnh kế tiếp chính xác là gì?"*

Article Lane (`scripts/article_run.py`) là **đường xử lý duy nhất** từ 2026-09-23. Radar không đọc và không khuyến nghị gì thuộc lane L1/Gold cũ: `l1_tasks`, hàng đợi `work_items`, packet `data/agent_tasks/l1/`, `l1_route.py`, `l1_ingest.py --code-first`, `requeue.py`, `agent_l1`/`agent_gold`. Trước đó radar vẫn bảo phía điều phối "gọi Subagents Flash `l1_entity_matcher`". Lệnh ấy dẫn sai lane, và agent nào tuân thủ luật Radar-first đều bị dẫn sai theo.

---

## 1. Bất biến

1. **Một nguồn chân lý, chỉ đọc.** Radar đọc đúng DB mà bước nạp ghi vào (`src/db/preflight.resolve_db_path()`: biến môi trường `MONOCLE_DB_PATH`, rồi `settings.yaml`) qua kết nối `mode=ro`, cộng với tệp mô tả đợt `data/agent_tasks/article/wave_<mã>.json`.
2. **Không suy đoán.** Mọi con số lấy từ DB hoặc từ tệp đợt. "Chờ phân tích" dùng **cùng câu truy vấn** với bước đóng gói (`article_pack.load_candidates`), nên đúng bằng số bài mà đợt kế tiếp sẽ lấy. Bản code-first (`l1_source = 'code_first'`) không tính là đã phân tích (ADR 0010).
3. **Mỗi khuyến nghị là một lệnh chạy được ngay**, kèm mức ưu tiên `HIGH`/`MEDIUM`/`INFO`. Mọi lệnh chạy với cwd = `project/`.
4. **Một đợt tại một thời điểm.** Đợt gần nhất chưa xong thì radar chỉ lệnh của đợt đó, không đề nghị mở đợt mới.
5. **Token không phải cổng.** Radar không so token với ngưỡng nào và không khuyến nghị gì dựa trên token.

---

## 2. Thứ tự suy luận

```
[Bước 1: Hạ tầng]
  ├── DB ghi được không (ghi thử một bảng trong giao dịch rồi rollback)
  ├── Độ tươi cào tin, Bronze kẹt ở Silver, domain 404 bất thường
       │
       ▼
[Bước 2: Đợt Article Lane gần nhất — theo đúng vòng đời]
  ├── Còn lô chưa có đầu ra           → chạy wave_<mã>.conductor.ts (hoặc .repair.ts) trong MỘT run_code
  ├── Có bài gửi đi chưa nhận bản ghi → article_run.py --wave <mã> --repair
  ├── Đủ bản ghi, DB dưới 90%         → article_run.py --wave <mã> --finish
  └── Đã xong                          → sang bước 3
       │
       ▼
[Bước 3: Ngày đang xem]
  ├── Còn bài chờ phân tích            → article_run.py --wave <mã-mới> --date <ngày> --limit <số chờ> --batch 100
  ├── Có bài phân tích nhưng chưa giao, hoặc tệp giao cũ hơn kết quả mới nhất
  │                                    → write_user_output.py --date <ngày>
  └── Không còn gì                     → INFO, đóng phiên
```

---

## 3. Lệnh

```powershell
# Trạng thái hôm nay:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status

# Một ngày cụ thể:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status --date YYYY-MM-DD

# Token và chi phí thật theo đợt:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --wave <mã>

# Đường dẫn, cwd, quyền ghi DB:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --where
```

---

## 4. Báo cáo mẫu (chạy thật ngày 2026-09-23)

```text
================================================================================
 🛰️  NEWS-SCAPE PIPELINE RADAR — ARTICLE LANE — [2026-09-23]
================================================================================
1. DỮ LIỆU TẠI KHO
   • Bài đăng trong ngày            : 372
   • Đã phân tích (mô hình, đạt)    : 0/372 (0.0%) · nội dung đạt 0
   • Chờ phân tích                  : 328 bài có gói Silver, chưa được mô hình phân tích (bản code-first không tính)
   • Bài bị nguồn xóa (404/410)     : 0 bài đăng hôm nay / 1 tổng tích lũy
   • Bronze kẹt ở Silver (ADR 0007) : 🟢 0 đang chặn watermark / 0 dead-letter
   • Độ tươi cào tin                : 🟢 Tươi mới (cách đây 1 phút)
   • Cơ sở dữ liệu                  : ✅ ghi được — C:\data\news-scape\monocle.db

2. ĐỢT ARTICLE LANE GẦN NHẤT
   • Mã đợt      : W365 (đóng gói 2026-09-21T17:35:31) · 365 bài · 5 lô gồm cả lô vá
   • Đầu ra      : 5/5 lô · nhận 365/365 bài
   • Vào DB      : nhận diện 361 (98.9%) · nội dung 364 (99.7%)
   • Trạng thái  : đã xong

3. ĐIỂM CHẠM & LỆNH KẾ TIẾP
   🔴 [HIGH] 328 bài đăng ngày 2026-09-23 chờ phân tích.
      👉 & "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave W09231659 --date 2026-09-23 --limit 328 --batch 100
```

Dòng `Cơ sở dữ liệu: ❌` trong phiên DSH gần như luôn là do sandbox `workspace-write` chặn ghi ra `C:\data\news-scape`. Xem mục 2b của `.agents/dsh/DSH-VIEC-THU-CONG.md`.

### 4b. Đọc đúng chỉ số "Bài bị nguồn xóa"

Chỉ số này hiển thị **hai con số** vì chúng trả lời hai câu hỏi khác nhau:

- **"bài đăng hôm nay"** lọc theo ngày đăng. Con số này luôn thấp hơn thực tế, vì bài bị gỡ thường được phát hiện muộn hơn ngày đăng.
- **"tổng tích lũy"** là mọi bài từng bị gắn cờ `source_deleted`, dùng để theo dõi xu hướng.

**Cảnh báo 404 giả.** Khi một domain có **hơn 10 bài** 404/410 **và** chiếm **hơn 30%** số bài của domain đó trong ngày, radar đẩy mục `HIGH` đề nghị chạy `validate_capture.py <domain>`. Tăng vọt tập trung ở một domain hầu như luôn là site đổi cấu trúc URL/selector, không phải tin bị gỡ thật.

---

## 5. Bù tin đêm

Máy không phải server nên có thể sleep qua đêm, để lại khoảng trống runtime (trễ hơn 120 phút). Radar hiện nhãn `🔴 Gián đoạn / Khoảng trống đêm` và đẩy `HIGH`:

```powershell
& "C:\venvs\news-scape\Scripts\python.exe" scripts/run_once.py
```

RSS giữ 20–50 tin gần nhất, nên chạy bù kéo được toàn bộ bài trong đêm về Bronze. Silver tự lọc trùng qua SimHash và watermark.

---

## 6. Mẫu prompt mồi đầu ngày

```text
Bắt đầu phiên ngày {YYYY-MM-DD}: chạy radar, rồi làm đúng lệnh radar in ra cho tới khi radar báo INFO.
Báo cáo độ phủ lấy từ bảng hậu kiểm của đợt, token lấy từ sổ cái (--workers-only).
```

Chuỗi phản xạ: radar → lệnh HIGH đầu tiên → radar lại. Không tự ghép chuỗi lệnh khác, không đọc mã nguồn để suy ra hợp đồng. Câu hỏi nào radar và `article_run.py --where` chưa trả lời được thì báo thiếu lệnh.
