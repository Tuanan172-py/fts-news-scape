# CONTEXT_RULES.md — Bounded Context & Token Budget Matrix (H2)

Tài liệu này định nghĩa phạm vi đọc tài liệu/mã nguồn của Agent theo từng **Giai đoạn (Phase)** và **Làn rủi ro (Risk Lane)** nhằm đảm bảo agent chỉ đọc đúng, đọc đủ, tránh làm tràn Context Window và kiểm soát ngân sách token.

---

## 1. Ngân sách Token theo Làn Rủi ro (Token Budgets)

| Làn Rủi ro | Ngân sách Context ước tính | Giới hạn số tệp đọc tối đa | Chiến lược dừng (Stop heuristic) |
|:---|:---:|:---:|:---|
| **`tiny`** | $\le 2.000$ tokens | 3 – 5 files | Dừng ngay khi xác định được dòng code cần patch và lệnh test. |
| **`normal`** | $\le 5.000$ tokens | 10 – 15 files | Dừng khi hoàn thành Story Packet và hiểu rõ module liên quan. |
| **`high-risk`** | $\le 10.000$ tokens | 20 – 30 files | Dừng khi thu thập đủ dữ liệu để viết ADR và xác định Hard Gate. |

---

## 2. Ma trận Ngữ cảnh (Phase × Lane Matrix)

Quy tắc: **MUST** (Bắt buộc đọc) · **SHOULD** (Khuyến khích đọc nếu chưa rõ) · **SKIP** (Tuyệt đối không đọc).

| Giai đoạn (Phase) | Tiny Lane | Normal Lane | High-Risk Lane |
|:---|:---|:---|:---|
| **1. Intake & Classify** | **MUST:** `AGENTS.md`, `FEATURE_INTAKE.md`<br/>**SKIP:** Story packets cũ, DB source code | **MUST:** `AGENTS.md`, `FEATURE_INTAKE.md`<br/>**SHOULD:** `HARNESS.md`<br/>**SKIP:** Implementation details sâu | **MUST:** `AGENTS.md`, `FEATURE_INTAKE.md`, `docs/decisions/`<br/>**SHOULD:** `project/docs/design/` |
| **2. Context & Planning** | **MUST:** Tệp code mục tiêu cần sửa<br/>**SKIP:** Toàn bộ docs kiến trúc tổng quát | **MUST:** OKF docs liên quan (`project/docs/skills/`), tệp tests<br/>**SKIP:** Các module không liên quan | **MUST:** OKF + `project/docs/design/`, Schema definitions, ADRs liên quan |
| **3. Implementation** | **MUST:** Tệp code đích<br/>**SKIP:** Mọi tài liệu policy | **MUST:** Tệp module đích + unit test tương ứng<br/>**SKIP:** Toàn bộ docs/ | **MUST:** Core models, data contracts, migrations |
| **4. Validation & Proof** | **MUST:** Tệp test liên quan<br/>**SKIP:** Mọi tài liệu khác | **MUST:** Test suite liên quan, `TEST_MATRIX.md` | **MUST:** Toàn bộ tầng Unit + Integration + Platform test runner |
| **5. Trace & Handoff** | **MUST:** `SESSION-LATEST.md` | **MUST:** `SESSION-LATEST.md`, `docs/stories/US-XXX.md` | **MUST:** `SESSION-LATEST.md`, ADR, Story packet |

---

## 3. Quy tắc Dừng Truy xuất (Retrieval Stopping Rules)

1. **Rule of Direct Match:** Nếu công cụ tìm kiếm (`grep_search`, `find_by_name`) đã chỉ ra chính xác vị trí lỗi hoặc hàm cần can thiệp, agent **không được tiếp tục mở thêm** các file tham khảo xung quanh.
2. **No Full-Repo Dumps:** Tuyệt đối không đọc toàn bộ thư mục hoặc dump hàng loạt file `.md` vào prompt khi chưa có lý do cụ thể.
3. **Progressive Disclosure:** Luôn đọc tệp tóm tắt trước; chỉ mở tài liệu con trong `references/` hoặc `scripts/` khi bước thực thi yêu cầu.
