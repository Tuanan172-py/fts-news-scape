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
       Không giám sát: ops_daemon (ADR 0012) · Tương tác: phiên DSH agent_article
                                      │
     ┌──────────────────┬─────────────┼───────────────┬──────────────────┐
     ▼                  ▼             ▼               ▼                  ▼
┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌──────────────┐ ┌──────────────┐
│ QUERY RADAR  │ │ WATCHLIST    │ │ TOKEN AUDITOR │ │ DOD INGEST   │ │ ARTICLE      │
│    AGENT     │ │   MONITOR    │ │     AGENT     │ │  GATEKEEPER  │ │  PROCESSOR   │
│ (Soi pipeline│ │ (Bảo vệ user,│ │ (Đọc sổ cái,  │ │ (Soát schema,│ │ (1 bài/lượt, │
│  & điểm chạm)│ │  thực thể mới)│ │  cache)      │ │  grounding)  │ │  hai lớp)    │
└──────────────┘ └──────────────┘ └───────────────┘ └──────────────┘ └──────────────┘
```

---

## 2. Nhiệm Vụ Cụ Thể Của Từng Chuyên Viên Agent

### 1. `Query Radar Agent` — Điểm Chạm Vận Hành & Hướng Dẫn Hành Động

- **Nhiệm vụ**: Khi Dev hoặc Agent bắt đầu phiên mà chưa rõ hệ thống đang ở bước nào (cào xong chưa, đợt Article Lane gần nhất ở nửa nào, DB có ghi được không), Radar đọc `monocle.db` (chỉ đọc) và tệp mô tả đợt để chỉ ra chính xác:
  - Điểm chạm hiện tại của dữ liệu và trạng thái `ops_daemon`.
  - Số bài cào về, số bài đã được mô hình phân tích, số bài chờ phân tích.
  - Trạng thái đợt gần nhất theo vòng đời (chạy mô hình, `--repair`, `--finish`, giao hàng).
  - **Đề xuất hành động tiếp theo** dạng lệnh PowerShell sẵn sàng copy-paste.
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status [--date YYYY-MM-DD]
  ```

### 2. `Watchlist & Entity Monitor Agent` — Quan Sát Người Dùng

- **Nhiệm vụ**:
  - Quét `<DATA_ROOT>/subscriptions/` để phát hiện ngay khi có người dùng mới thêm file đăng ký mà chưa được kích hoạt trong `<DATA_ROOT>/subscriptions/manifest.yaml`.
  - Giám sát các thực thể lạ (`unlisted_candidates`) do mô hình nhận diện để đề xuất Dev cập nhật catalog `<DATA_ROOT>/entities/entities.json` (qua `entity-curator`, Tier 3).
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py users
  ```

### 3. `Token Auditor Agent` — Đọc Số Token Thật

- **Nhiệm vụ**:
  - Đọc token và USD thật từ sổ cái `token_ledger` trong `harness.db`, không nhân định mức.
  - Theo dõi sàn bộ nhớ đệm và sai số dự toán (`estimate_wave.py`).
  - Token là số ghi nhận, không phải cổng: không trần, không ngưỡng cảnh báo, không đề nghị giảm số bài (AGENTS.md §7.2).
- **Công cụ chuẩn**:
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token [--date YYYY-MM-DD]
  ```

### 4. `DoD Ingest Gatekeeper Agent` — Người Gác Cổng Chất Lượng & Grounding

- **Nhiệm vụ**:
  - Nghiệm thu tự động Definition-of-Done trên 100% output của Subagents trước khi nạp DB.
  - Kiểm tra 3 rào cản bất biến:
    1. Schema: record `article-compact-v2` (rule 11), bung thành `l1-entity-output-v1` và `agent-output-v2-lean`.
    2. Grounded Citations: dựng từ chỉ số đoạn, mỗi đoạn $\ge 20$ ký tự, nên nguyên văn do cấu trúc.
    3. Value-Added: Luận điểm `key_points` phải được diễn giải độc lập, tuyệt đối không copy nguyên văn chuỗi citations.
  - Cổng của đợt: nạp không lỗi và độ phủ của đợt $\ge 90\%$ ở cả hai lớp.
- **Công cụ chuẩn** (cwd `project/`; `--finish` gọi `l1_ingest.py` và `agent_ingest.py` với đúng tệp của đợt, không gọi tay):
  ```powershell
  & "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave <đợt> --finish
  ```

### 5. `Delivery & Formatting Agent` — Xuất Bản Deliverable Đơn Sắc

- **Nhiệm vụ**:
  - Tổng hợp kết quả hai lớp vào các file Excel người dùng `<DATA_ROOT>/users/output/<user>/<date>.xlsx` (ADR-0026.D6).
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
Bắt đầu phiên ngày {YYYY-MM-DD}: chạy radar, rồi làm đúng lệnh radar in ra cho tới khi radar báo INFO. Báo cáo độ phủ lấy từ bảng hậu kiểm của đợt, token lấy từ sổ cái (--workers-only).
```

### B. Các Lệnh Thực Thi Cơ Học Tương Ứng:

1. **Kiểm tra trạng thái**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
   ```
2. **Thực hiện hành động đề xuất**: Chạy đúng lệnh `pipeline_radar.py` gợi ý (chuẩn bị đợt $\rightarrow$ một `run_code` $\rightarrow$ `--finish`). Khi `ops_daemon` sống ở mức L1 thì không mở đợt tay song song.
3. **Kiểm tra ngân sách token**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py token
   ```
4. **Xuất bản kết quả**:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/write_user_output.py --date today
   ```
