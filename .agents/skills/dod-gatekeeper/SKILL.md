---
name: dod-gatekeeper
description: Chuyên viên kiểm định chất lượng độc lập, kiểm tra schema v2-lean, rà soát citations nguyên văn exact substring, chống lặp key_points và tự động cải tiến System Prompt (Human-in-the-loop).
---

# DoD Quality Gatekeeper Agent Skill

> **Mục tiêu cốt lõi:** Tuyệt đối không để dữ liệu hallucination hoặc dữ liệu vi phạm chuẩn chạm vào Database và Deliverable Excel. Thực thi nguyên tắc *"No proof = Not done"*.

---

## 1. Định Hướng & Bất Biến Kiểm Định (Quality Invariants)

1. **Rào Cản Schema Hợp Lệ (Schema Valid — Hard Gate)**:
   - **Tầng Gold (`agent-output-v2-lean`)**: Bắt buộc chuẩn phẳng 7 trường cốt lõi (`article_id`, `summary`, `key_points`, `implication`, `sentiment`, `time_sensitivity`, `citations`). Không chấp nhận các trường thừa cũ (`affected_parties`, `impact_area`, `materiality.score`).
   - **Tầng L1 (`l1-entity-output-v1`)**: Bắt buộc đủ `article_id`, `recognized`, `entities`, `categories`, `citations`, `processing_metadata`.
2. **Ràng Buộc Căn Cứ Thực Tế (Grounded Citations)**:
   - Mô hình trả 2 đến 4 chỉ số đoạn `c` (1 chỉ số khi bài chỉ có một đoạn đủ dài), theo rule 11.
   - Bộ bung dựng `source_span` từ chỉ số đoạn, nên trích dẫn là **chuỗi con nguyên văn** do cấu trúc; cổng vẫn kiểm lại.
   - Mỗi đoạn được trỏ tới phải đạt **$\ge 20$ ký tự**.
3. **Rào Cản Giá Trị Mới & Chống Trùng Lặp (Value-Added Invariant)**:
   - `summary`: Phải là tóm tắt trừu tượng (abstractive), không được copy nguyên văn bài báo.
   - `key_points`: Phải là các gạch đầu dòng diễn giải bằng lời văn phân tích tài chính riêng của Agent, **TUYỆT ĐỐI KHÔNG copy nguyên văn chuỗi citations**.
   - `implication`: Phải là phân tích hàm ý thị trường riêng (>= 40 ký tự), không được dùng câu mẫu sáo rỗng.

---

## 2. Quy Trình Vận Hành (Gatekeeper Workflow)

```
[Bản ghi article-compact-v2 của đợt] (<DATA_ROOT>/agent_outputs_article/article_<đợt>_*.output.json)
       │
       ▼
[article_run.py --wave <đợt> --finish]
  ├── expand: article_expand.py dựng l1-entity-output-v1 + agent-output-v2-lean
  ├── ingest: l1_ingest.py + agent_ingest.py, chỉ tệp của đợt; chấm DoD bằng src/agent/contract/dod.py
  │     ├── Soát Schema: cú pháp JSON, cấu trúc trường, kiểu dữ liệu
  │     ├── Soát Grounding: trích dẫn là chuỗi con nguyên văn của bài
  │     └── Soát Value-Added: key_points không chép citations
  ├── verify: độ phủ của đợt >= 90% ở cả hai lớp
  └── ledger, handoff
       │
       ├─► Đạt: ghi agent_outputs / l1_outputs (dod_pass=1), in ✅ và thoát 0
       └─► Không đạt: in ❌ kèm đúng lệnh chạy lại (--only ...) hoặc --repair cho phần thiếu
```

---

## 3. Vòng Lặp Tự Học & Cải Tiến Liên Tục (Continuous Learning Loop)

Khi cổng phát hiện lỗi lặp lại của mô hình, không sửa ngầm bản ghi (rule 11 §2.3): bản ghi sai bị từ chối và đi vào `--repair`. Sửa tri thức hệ thống thay vì sửa dữ liệu:

```
[Phát hiện vi phạm lặp lại]
       │
       ▼
[1. Sửa nguồn prefix] (schema/catalog → scripts/build_article_prefix.py → dán persona, --check-preset)
       │
       ▼
[2. Ghi KPI và ma sát] (harness_cli.py metric --fp N; harness_cli.py backlog add)
       │
       ▼
[3. Ghi vết vào SESSION-LATEST.md]
```

---

## 4. Bộ Công Cụ Cơ Học Thực Thi (Execution Tooling)

```powershell
# cwd = project/. Không gọi l1_ingest.py / agent_ingest.py tay: --finish gọi chúng với đúng tệp của đợt.
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave <đợt> --finish
& "C:\venvs\news-scape\Scripts\python.exe" scripts/article_run.py --wave <đợt> --finish --only ingest,verify,ledger,handoff
```
