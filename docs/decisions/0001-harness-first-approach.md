# 0001 — Harness-First Approach for Agentic Collaboration

- **Status:** accepted
- **Date:** 2026-08-24
- **Decision-makers:** Human Operator & AGY Agent
- **Parent / Scope:** Governance & Operational Framework

---

## Context
Khi phát triển hệ thống cào và xử lý tin tức tài chính `news-scape` với nhiều Subagent và tác vụ tự động, việc để Agent can thiệp trực tiếp vào mã nguồn mà không có ranh giới kiểm soát (harness) dễ dẫn đến: code trôi dạt, mất khả năng quan sát, thiếu kiểm thử chứng minh, và không duy trì được ngữ cảnh giữa các phiên làm việc.

## Decision
Áp dụng triết lý **Harness-First**: Xây dựng khung vận hành và kỷ luật làm việc (Harness) bao quanh sản phẩm trước khi mở rộng tính năng sản phẩm. Mọi yêu cầu đều phải đi qua cổng phân loại rủi ro (Intake Gate), giới hạn phạm vi đọc (Bounded Context), bắt buộc kiểm thử cơ học (Proof-Driven), và ghi nhận bằng chứng bền vững (Durable Layer).

## Consequences
* **Tích cực:** Tăng tính ổn định, mọi thay đổi đều có bằng chứng nghiệm thu rõ ràng, Agent không bao giờ phá vỡ cấu trúc CSDL hoặc Data Contract mà không qua kiểm duyệt.
* **Đánh đổi:** Cần thêm các bước khởi tạo intake và ghi nhận trace trong mỗi phiên làm việc.

## Actual Outcome
Đã hoàn thành thiết lập nền tảng H1–H5, giúp loại bỏ hoàn toàn các lỗi mất dấu vết và sai lệch trạng thái làm việc.
