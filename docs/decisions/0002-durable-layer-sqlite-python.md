# 0002 — Durable Layer using SQLite and Python CLI

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision-makers:** Human Operator & AGY Agent
- **Parent / Scope:** Harness H2 Infrastructure

---

## Context
Ở cấp độ H1, việc duy trì trạng thái bằng các tệp Markdown thủ công (`SESSION-LATEST.md`, bảng Markdown trong `TEST_MATRIX.md`) đã xuất hiện ma sát: khó truy vấn tự động, dễ bị lệch trạng thái (drift), và không thể tự động hóa khâu chấm điểm trace hay kiểm toán entropy.

## Decision
Xây dựng tầng lưu trữ bền vững (**Durable Layer**) cho Harness sử dụng:
1. **SQLite (`harness.db`):** Chạy ở chế độ `WAL`, cô lập hoàn toàn với `monocle.db`, lưu trữ trạng thái của Story, Intake, Decision, Backlog, Trace, Intervention, Tool.
2. **Python CLI (`scripts/harness_cli.py`):** Cung cấp giao diện dòng lệnh thống nhất để Agent và Con người tương tác với Durable Layer, không đòi hỏi cài đặt toolchain binary bên ngoài (Rust/Go), hoàn toàn tương thích trên môi trường Windows / Python hiện hành.

## Consequences
* **Tích cực:** Quản lý Story, Trace và Audit hoàn toàn tự động, máy đọc được (JSON/Table), cho phép kiểm tra bằng chứng trước khi chuyển trạng thái sang `implemented`.
* **Đánh đổi:** Cần chạy lệnh CLI thay vì sửa chay file markdown.

## Actual Outcome
Hệ thống chuyển dịch mượt mà từ H1 sang H2–H5, truy vấn trạng thái và kiểm toán tự động thành công.
