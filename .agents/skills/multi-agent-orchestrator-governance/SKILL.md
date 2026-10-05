---
name: multi-agent-orchestrator-governance
description: Quy trình điều phối mạng lưới Agent đa tầng (Master, Query Radar, Watchlist Monitor, Token Auditor, DoD Gatekeeper) và cơ chế tự học hỏi, nhắc nhở tối ưu hệ thống News-Scape (Human-in-the-loop).
---
# Multi-Agent Orchestrator & System Governance Skill

> **Tầm nhìn & Mục tiêu:** Chuyển hóa toàn bộ quy trình vận hành tin tức tài chính News-Scape thành một **mạng lưới các chuyên viên Agent chuyên biệt (Multi-Agent Swarm)** tự điều phối, tự kiểm toán, đo lường chi phí, phát hiện bất thường và chủ động đề xuất hành động cho Developer / Human-in-the-loop.

---

## 1. Bản Đồ Phân Vai Các Agent Chuyên Trách (Agent Topology)

```
                       ┌───────────────────────────────┐
                       │      HUMAN-IN-THE-LOOP        │
                       │     (Developer / User)        │
                       └──────────────┬────────────────┘
                                      │ Yêu cầu / Quyết định
                                      ▼
                       ┌───────────────────────────────┐
                       │      MASTER ORCHESTRATOR      │
                       │  (Điều phối vòng đời End-to-End)
                       └──────────────┬────────────────┘
                                      │
     ┌──────────────────┬─────────────┼───────────────┬──────────────────┐
     ▼                  ▼             ▼               ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌──────────────┐ ┌──────────────┐
│ QUERY RADAR  │ │ WATCHLIST    │ │ TOKEN AUDITOR │ │ DOD INGEST   │ │ SUBAGENTS    │
│    AGENT     │ │   MONITOR    │ │     AGENT     │ │  GATEKEEPER  │ │  L1 & GOLD   │
│ (Soi pipeline│ │ (Bảo vệ user,│ │ (Đo hạn mức,  │ │ (Soát schema,│ │ (Bóc tách L1,│
│  & điểm chạm)│ │  thực thể mới)│ │  chống burn) │ │  grounding)  │ │  suy luận v2)│
└──────────────┘ └──────────────┘ └───────────────┘ └──────────────┘ └──────────────┘
```

---

## 2. Nhiệm Vụ Cụ Thể Của Từng Chuyên Viên Agent

### 1. `Query Radar Agent` — Điểm Chạm Vận Hành & Hướng Dẫn Hành Động

- **Nhiệm vụ**: Khi Dev hoặc Agent bắt đầu phiên mà chưa rõ hệ thống đang ở bước nào (cào xong chưa, L1 xong chưa, bài Gold đang nghẽn ở đâu), Radar Agent sẽ truy vấn SQLite `monocle.db` và các thư mục task/output để chỉ ra chính xác:
  - Điểm chạm hiện tại của dữ liệu.
  - Số lượng bài cào về, bài đã qua L1, bài đã qua Gold.
  - Số batch/task đang tồn đọng trên đĩa.
  - **Đề xuất hành động tiếp theo** dạng lệnh PowerShell sẵn sàng copy-paste.
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status [--date YYYY-MM-DD]
  ```

### 2. `Watchlist & Entity Monitor Agent` — Quan Sát Người Dùng

- **Nhiệm vụ**:
  - Quét thư mục `users/subscriptions/*.xlsx` để phát hiện ngay khi có người dùng mới thêm file đăng ký mà chưa được kích hoạt trong `config/entities/manifest.yaml`.
  - Giám sát các thực thể lạ (`unlisted_candidates`) do Subagents nhận diện để đề xuất Dev cập nhật từ điển catalog `data/entities/entities.json`.
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py users
  ```

### 3. `Token Auditor Agent` — Giám Sát Ngân Sách & Chống Burn Token

- **Nhiệm vụ**:
  - Đo lường chính xác số token tiêu thụ thực tế của từng ngày theo benchmark thực nghiệm (L1: ~450 tokens/bài, Gold v2-lean: ~1.470 tokens/bài).
  - Đánh giá hiệu quả của phễu lọc **Subscriber-Gating** (thường tiết kiệm >90% token vô ích).
  - Cảnh báo Dev khi chi phí hoặc số lượng bài phân tích tăng đột biến.
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token [--date YYYY-MM-DD]
  ```

### 4. `DoD Ingest Gatekeeper Agent` — Người Gác Cổng Chất Lượng & Grounding

- **Nhiệm vụ**:
  - Nghiệm thu tự động Definition-of-Done trên 100% output của Subagents trước khi nạp DB.
  - Kiểm tra 3 rào cản bất biến:
    1. Schema v2-lean: Cấu trúc phẳng 7 trường cốt lõi.
    2. Grounded Citations: Chuỗi con nguyên văn (exact substring) $\ge 20$ ký tự.
    3. Value-Added: Luận điểm `key_points` phải được diễn giải độc lập, tuyệt đối không copy nguyên văn chuỗi citations.
  - Tự động di chuyển task packets đạt chuẩn sang `data/agent_tasks/archive/<YYYYMMDD>/`.
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/l1_ingest.py data/agent_outputs_l1
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/agent_ingest.py data/agent_outputs
  ```

### 5. `Delivery & Formatting Agent` — Xuất Bản Deliverable Đơn Sắc

- **Nhiệm vụ**:
  - Tổng hợp dữ liệu Gold v2-lean và L1 vào các file Excel người dùng `users/output/<user>/<date>.xlsx`.
  - Bảo đảm định dạng đơn sắc chuyên nghiệp, wrap text, độ rộng cột tối ưu.
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date <YYYY-MM-DD>
  ```

---

## 3. Cơ Chế Tự Cải Tiến Quy Trình (Self-Improvement Protocol & HITL)

Mạng lưới Agent áp dụng cơ chế tự hoàn thiện khép kín dựa trên các bài học vận hành thực tế:

```
[Phát hiện lỗi / Lệch chuẩn DoD]
       │  (Ví dụ: Subagent copy citations vào key_points)
       ▼
[Phân tích nguyên nhân gốc rễ (RCA)]
       │  (Do prompt chưa cấm triệt để việc trùng lặp)
       ▼
[Cập nhật ngay vào System Prompt & Skills]
       │  (Bổ sung điều khoản Value-Added Invariant vào SKILL.md)
       ▼
[Tái kiểm tra & Đo lường ở Đợt tiếp theo]
       │  (Tỷ lệ DoD Pass tăng lên 100%)
       ▼
[Ghi vết nghiệm thu vào SESSION-LATEST.md & Báo cáo Human]
```

---

## 4. Runbook 5 Phút Hàng Ngày Cho Developer / Orchestrator

### A. Mẫu Prompt Mồi Kích Hoạt Nhanh (1-Prompt Daily Trigger):

Developer chỉ cần gửi câu lệnh mồi chuẩn hóa cho Agent:

```text
Bắt đầu phiên ngày {YYYY-MM-DD}: Hãy dùng Radar kiểm tra điểm chạm pipeline, sau đó thực thi trọn vẹn chuỗi L1 (vật chất hóa Code-First trước để tiết kiệm token, phần còn lại gom mini-batches cho Subagents Flash xử lý có kiểm soát). Báo cáo tỷ lệ DoD và tổng lượng token tiêu thụ sau khi hoàn tất.
```

### B. Các Lệnh Thực Thi Cơ Học Tương Ứng:

1. **Kiểm tra trạng thái**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
   ```
2. **Thực hiện hành động đề xuất**: Chạy lệnh được `pipeline_radar.py` gợi ý ở mục 3 (L1 Code-First $\rightarrow$ Subagents $\rightarrow$ Ingest).
3. **Kiểm tra ngân sách token**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token
   ```
4. **Xuất bản kết quả**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date today
   ```
