# HARNESS_MATURITY.md — Thang đo Độ Trưởng Thành của Harness (H0 – H5)

Tài liệu này xác lập tiêu chí định lượng để đánh giá mức độ hoàn thiện và năng lực tự vận hành của hệ thống Harness.

---

## Bảng Phân cấp Trưởng thành

| Cấp độ | Tên gọi | Bản chất & Đặc trưng | Tiêu chí đạt được (Exit Criteria) |
|:---|:---|:---|:---|
| **H0** | **Bare** | Prompt vào $\rightarrow$ Patch ra. Không có harness hay quy tắc nào. | Điểm xuất phát ban đầu. |
| **H1** | **Scaffolding** | Bộ quy tắc tĩnh bằng Markdown, template, phân làn rủi ro. Không có CSDL. | Đã có `AGENTS.md`, `HARNESS.md`, `FEATURE_INTAKE.md`, `TEST_MATRIX.md`, `SESSION-LATEST.md`. |
| **H2** | **Durable** | Có CSDL SQLite + CLI mỏng ghi nhận state bền vững (intake, story, decision, trace, backlog). | Đã có `harness.db`, `harness_cli.py`, `CONTEXT_RULES.md`, `TRACE_SPEC.md`. |
| **H3** | **Active Observability** | Chấm điểm trace, context budget compliance, gom nhóm friction theo component. | Có lệnh `score-trace`, `score-context`, phân tích friction theo component. |
| **H4** | **Auto-Verification** | Công cụ kiểm thử tự động, chặn story hoàn thành nếu chưa chạy verify command thực tế. | Đã có `TOOL_REGISTRY.md`, lệnh `story complete --run-verify` có cổng chặn. |
| **H5** | **Self-Improvement** | Tự động quét kiểm toán entropy và đề xuất cải tiến có bằng chứng cho con người duyệt. | Đã có `HARNESS_AUDIT.md`, `IMPROVEMENT_PROTOCOL.md`, lệnh `audit` và `propose`. |

---

## Trạng thái Hiện tại của Hệ thống

* **Cấp độ đã triển khai:** **H5 Ready** (Đầy đủ CSDL Durable, CLI Tooling, Tracing & Scoring, Cổng Verification, và Giao thức Tự cải tiến).
