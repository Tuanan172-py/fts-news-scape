# HARNESS_AUDIT.md — Quy chuẩn Kiểm toán Entropy & Trôi dạt Quy trình (H5)

Tài liệu này định nghĩa cơ chế tự động quét phát hiện độ trôi dạt (Drift) và suy thoái trật tự (Entropy) của hệ thống Harness.

---

## 1. Sáu Tiêu chí Quét Trôi dạt (6 Drift Checks)

Lệnh `python scripts/harness_cli.py audit` thực hiện quét 6 hạng mục sau:

| # | Tiêu chí Kiểm toán | Mô tả & Rủi ro | Điểm phạt (Penalty) |
|:---|:---|:---|:---:|
| **1** | **Unproven Implemented Stories** | Story được đánh dấu `implemented` nhưng toàn bộ các cột proof (`unit`, `integ`, `e2e`, `platform`) đều bằng 0. | $-0.20$ / story |
| **2** | **WIP = 1 Violation** | Có nhiều hơn 1 Story đang ở trạng thái `in_progress` cùng lúc. | $-0.25$ |
| **3** | **Missing Traces** | Story đã `implemented` hoặc `blocked` nhưng không có bản ghi trace nào trong bảng `trace`. | $-0.10$ / story |
| **4** | **Backlog Accumulation** | Có hơn 5 mục ma sát (friction) ở trạng thái `open` chưa được xử lý. | $-0.15$ |
| **5** | **High-Risk Missing Intake/ADR** | Story thuộc làn `high-risk` nhưng không có bản ghi intake liên kết hoặc thiếu ADR. | $-0.15$ / story |
| **6** | **Schema Health** | Phiên bản CSDL SQLite không khớp với mã nguồn migration. | Phạt theo độ lệch |

---

## 2. Công thức Điểm Sức khỏe & Entropy (Health vs Entropy Score)

$$\text{Health Score} = \max\Big(0.0, \, 1.0 - \sum \text{Penalties}\Big)$$
$$\text{Entropy Score} = 1.0 - \text{Health Score}$$

* **Health Score $\ge 0.85$:** Hệ thống ở trạng thái lý tưởng, kỷ luật tốt.
* **Health Score $0.50 – 0.84$:** Có dấu hiệu trôi dạt quy trình, cần dọn dẹp trace/proof.
* **Health Score $< 0.50$:** Hệ thống suy thoái nghiêm trọng, cần kích hoạt quy trình tái chuẩn hóa (Harness Re-alignment).
