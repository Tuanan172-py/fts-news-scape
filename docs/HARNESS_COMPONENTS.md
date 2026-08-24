# HARNESS_COMPONENTS.md — 11 Trách nhiệm Runtime của Harness (H2)

Tài liệu này xác định **11 trách nhiệm cốt lõi** mà hệ thống Harness phải đảm bảo trong suốt vòng đời tương tác giữa Con người và Agent.

---

## Danh mục 11 Trách nhiệm Runtime

| # | Trách nhiệm | Vai trò & Ý nghĩa | Triển khai trong News-Scape |
|:---|:---|:---|:---|
| **1** | **Task Specification** | Định nghĩa công việc máy đọc được, phân loại rủi ro rõ ràng. | `FEATURE_INTAKE.md` + bảng `intake`, `story`. |
| **2** | **Context Boundary** | Giới hạn tài liệu và mã nguồn nạp vào context, tránh tràn token. | `CONTEXT_RULES.md` + ngân sách token theo lane. |
| **3** | **Tool Access** | Quản lý công cụ agent được phép gọi và cơ chế suy giảm (degrade). | `TOOL_REGISTRY.md` + bảng `tool`. |
| **4** | **Memory & State** | Lưu trữ bền vững điều đã xảy ra qua các phiên làm việc. | CSDL SQLite `harness.db` (bảng `story`, `trace`, `backlog`). |
| **5** | **Task State** | Quản lý trạng thái và thứ tự công việc, chống double-claim. | Cột `story.status`, kỷ luật `WIP = 1`. |
| **6** | **Observability** | Đo lường và giám sát toàn bộ hành vi, files read/changed. | Bảng `trace` + lệnh `score-trace`, `query matrix`. |
| **7** | **Failure Attribution** | Bắt lỗi và ma sát phát sinh để phân tích nguyên nhân gốc. | Bảng `intervention`, `backlog` (friction reservoir). |
| **8** | **Verification Gate** | Ràng buộc kiểm thử trước khi kết luận hoàn thành ("No proof = not done"). | Cột `unit/integ/e2e/platform_proof` + lệnh `story complete`. |
| **9** | **Permissions Gate** | Kiểm soát quyền hạn: Phân tách Read-only vs Mutation; Hard Gates. | `AGENTS.md` (Rule 0) + `FEATURE_INTAKE.md` (Hard Gates). |
| **10**| **Entropy Audit** | Tự động phát hiện độ trôi dạt (drift) của quy trình và tài liệu. | Lệnh `python scripts/harness_cli.py audit`. |
| **11**| **Intervention & Propose** | Tự đề xuất cải tiến quy trình dựa trên dữ liệu ma sát tích lũy. | Lệnh `python scripts/harness_cli.py propose`. |

---

## Lăng kính Thiết kế (Self-Check Lens)

Mỗi khi bổ sung quy trình hoặc công cụ mới, Agent tự đối soát:
* Tính năng mới có vi phạm ranh giới **Context Boundary** không?
* Thay đổi có đi kèm **Verification Gate** cơ học không?
* Trạng thái mới có được ghi vào **Durable Storage** không?
