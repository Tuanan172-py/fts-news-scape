---
name: pipeline-radar
description: Chuyên viên trinh sát, quan sát trạng thái pipeline end-to-end, phát hiện điểm nghẽn dữ liệu và đề xuất hành động vận hành tiếp theo (Human-in-the-loop).
---

# Pipeline Radar & Triage Agent Skill

> **Mục tiêu cốt lõi:** Luôn trả lời được câu hỏi then chốt: *"Dữ liệu đang ở điểm chạm nào? Đã cào bao nhiêu bài? L1 đã xong chưa? Gold đang nghẽn ở đâu? Và hành động tiếp theo chính xác là gì?"*

---

## 1. Định Hướng & Bất Biến Nghiệp Vụ (Context & Domain Invariants)

1. **Nguyên lý Single Source of Truth (SQLite Read-Only)**:
   - Mọi thông tin trạng thái dữ liệu phải được truy vấn trực tiếp từ cơ sở dữ liệu `C:/data/news-scape/monocle.db` qua kết nối `mode=ro` (chống lock file) kết hợp kiểm tra hàng đợi tệp tin vật lý (`data/agent_tasks/` và `data/agent_outputs/`).
2. **Kỷ luật Zero-Guesswork (Không suy đoán mù quáng)**:
   - Tuyệt đối không phỏng đoán trạng thái của hệ thống. Phải định lượng bằng số liệu thực tế: số bài cào về, số bài đạt chuẩn L1, số bài đạt chuẩn Gold, số batch đang chờ xử lý trên đĩa.
3. **Quy chuẩn Đề Xuất Hành Động (Actionable Output)**:
   - Mọi báo cáo trạng thái BẮT BUỘC phải kết thúc bằng một danh mục đề xuất hành động cụ thể kèm mức độ ưu tiên (`HIGH`, `MEDIUM`, `INFO`) và **lệnh PowerShell chuẩn xác để người dùng có thể chạy ngay**.

---

## 2. Quy Trình Vận Hành & Mô Hình Tư Duy (Thinking Order)

Khi Dev bắt đầu một phiên làm việc mới hoặc khi chu kỳ cào tin tự động kết thúc:

```
[Bắt đầu phiên] 
       │
       ▼
[Bước 1: Quét Database & Hàng đợi Tệp tin]
  ├── Đếm số bài cào trong ngày (articles)
  ├── Đếm số bài đã có kết quả L1 hợp lệ (l1_outputs)
  ├── Đếm số bài đã có kết quả Gold hợp lệ (agent_outputs)
  └── Đếm số task packet / output json đang tồn đọng trên đĩa
       │
       ▼
[Bước 2: Đối chiếu Điểm Chạm Pipeline (Pipeline Phase Triage)]
  ├── TH1: Có bài mới cào nhưng chưa chạy L1 -> Điểm chạm: Phase 1 (L1 Code-First)
  ├── TH2: Có batch L1/Gold đang chờ Subagents -> Điểm chạm: Phase 2/4 (Invoke Subagents)
  ├── TH3: Có output L1/Gold đã sinh nhưng chưa Ingest -> Điểm chạm: Phase 3/5 (DoD Ingest)
  ├── TH4: Đã Ingest Gold xong nhưng chưa xuất Excel -> Điểm chạm: Phase 5 (Write User Deliverable)
  └── TH5: Đã hoàn tất 100% -> Điểm chạm: Sẵn sàng đóng phiên (Stable State)
       │
       ▼
[Bước 3: Xuất Báo Cáo Trinh Sát & Lệnh Đề Xuất Tiếp Theo]
```

---

## 3. Bộ Công Cụ Cơ Học Thực Thi (Execution Tooling)

Chuyên viên Radar sử dụng công cụ CLI chuẩn hóa được tích hợp sẵn trong dự án:

```powershell
# 1. Soi toàn diện trạng thái ngày hôm nay:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status

# 2. Soi trạng thái của một ngày cụ thể trong quá khứ:
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status --date YYYY-MM-DD
```

---

## 4. Cơ Chế Báo Cáo Mẫu (Canonical Radar Output)

```text
================================================================================
 🛰️  NEWS-SCAPE PIPELINE OBSERVABILITY & STATUS REPORT — [2026-09-14]
================================================================================
1. DỮ LIỆU TẠI KHO (DATABASE & BRONZE/SILVER):
   • Số bài cào xuất bản trong ngày : 320 bài
   • Số bài đã hoàn tất tầng L1     : 764 bài
   • Số bài đã hoàn tất tầng Gold   : 64 bài

2. TRẠNG THÁI HÀNG ĐỢI FILE (TASK PACKETS & BATCHES):
   • Tác vụ L1 đang chờ Subagents   : 0 files/batches
   • Tác vụ Gold đang chờ Subagents : 0 files/batches
   • Bài L1 đã xuất chưa Ingest DB  : 0 bài
   • Bài Gold đã xuất chưa Ingest DB: 0 bài

3. ĐIỂM CHẠM VẬN HÀNH & ĐỀ XUẤT HÀNH ĐỘNG CỤ THỂ:
   🟢 [INFO] Toàn bộ chuỗi vận hành ngày này đã hoàn tất 100% sạch sẽ. Deliverable đã sẵn sàng.
      👉 Hành động: Không cần thao tác thêm. Hệ thống ở trạng thái ổn định.
================================================================================
```

---

## 5. Mẫu Prompt Mồi Chuẩn Hóa Cho Developer (Daily Activation Template)

Khi bước sang ngày mới hoặc bắt đầu ca vận hành, người dùng gửi câu lệnh chuẩn hóa (Mẫu 2):

```text
Bắt đầu phiên ngày {YYYY-MM-DD}: Hãy dùng Radar kiểm tra điểm chạm pipeline, sau đó thực thi trọn vẹn chuỗi L1 (vật chất hóa Code-First trước để tiết kiệm token, phần còn lại gom mini-batches cho Subagents Flash xử lý có kiểm soát). Báo cáo tỷ lệ DoD và tổng lượng token tiêu thụ sau khi hoàn tất.
```

### Chuỗi Phản Xạ Tự Động Của Agent (Autonomous Execution Chain):
1. **Bước 1 — Định vị điểm chạm**: Chạy `& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status --date {YYYY-MM-DD}`.
2. **Bước 2 — Tiết kiệm token tối đa**: Chạy `& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py --code-first` để giải quyết 60–70% bài cào với chi phí 0 token.
3. **Bước 3 — Đóng gói mini-batches**: Gom các bài `needs_agent` còn lại thành các batch 25 bài/lô (`l1_batch_XX.task.json`).
4. **Bước 4 — Triển khai Controlled Waves**: Kích hoạt Subagents Flash (`l1_entity_matcher`) theo từng đợt 2–3 batches (50–75 bài/đợt) chống lỗi 429 rate limit.
5. **Bước 5 — Cổng kiểm định DoD & Archive**: Chạy `& "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py data/agent_outputs_l1`, tự động nạp DB và di chuyển task packets vào `data/agent_tasks/l1/archive/<YYYYMMDD>/`.
6. **Bước 6 — Báo cáo nghiệm thu & Telemetry**: Chạy `& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token --date {YYYY-MM-DD}` báo cáo số token thực tế và tỷ lệ đạt chuẩn DoD cho Developer.

