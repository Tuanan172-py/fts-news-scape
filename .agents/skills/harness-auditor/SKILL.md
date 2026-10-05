---
name: harness-auditor
description: Đọc trend harness.db + agent_metrics, soạn proposal và ADR draft cho Human duyệt.
---

# Harness Auditor Skill

> **Mục đích:** Đọc dữ liệu harness bền vững, phát hiện tín hiệu suy giảm, soạn đề xuất tự cải tiến và ADR draft để Human duyệt; hiện thực hóa tầng H5 Self-Improvement trong News-Scape.

## 1. Cảnh báo quyền hạn

Agent này CHỈ ĐỌC harness và CHỈ GHI một file đề xuất `docs/proposals/harness_improvement_<date>.md`.

- TUYỆT ĐỐI KHÔNG ghi vào `harness.db`.
- TUYỆT ĐỐI KHÔNG sửa `src/**`.
- TUYỆT ĐỐI KHÔNG sửa code hay bất kỳ artifact thực thi nào.

Mọi thay đổi thực tế do Human duyệt và thực thi theo `docs/IMPROVEMENT_PROTOCOL.md`. Agent dừng ở mức đề xuất.

## 2. Nguồn dữ liệu (read-only)

Chạy các lệnh `harness_cli` chỉ đọc để lấy trạng thái:

- `python scripts/harness_cli.py query matrix` — lấy ma trận story/proof.
- `python scripts/harness_cli.py query agent-metrics` — lấy KPI từng cognitive agent: `dod_pass_rate`, `tokens`, `fp_flags`.
- `python scripts/harness_cli.py audit` — lấy điểm entropy và drift.
- `python scripts/harness_cli.py propose` — lấy đề xuất thô từ friction backlog và agent metrics.

Tham chiếu `docs/HARNESS_AUDIT.md` và `docs/IMPROVEMENT_PROTOCOL.md` để hiểu ngưỡng và quy trình duyệt.

## 3. Phân tích tín hiệu suy giảm

Đối chiếu dữ liệu vừa đọc và trích các tín hiệu sau:

- Agent có `dod_pass_rate` < 95%.
- Agent có `fp_flags` tăng so với đợt trước.
- Component tích nhiều friction backlog.
- Story tồn đọng thiếu proof trong ma trận.
- Điểm entropy vượt ngưỡng khai báo tại `docs/HARNESS_AUDIT.md`.

Gắn mỗi tín hiệu với số liệu định lượng làm bằng chứng.

## 4. Soạn đề xuất

Soạn mỗi đề xuất theo mẫu closed-loop:

1. Triệu chứng kèm bằng chứng số liệu.
2. Giả thuyết nguyên nhân gốc (RCA).
3. Hành động đề xuất.
4. Phép đo kỳ vọng ở đợt sau.
5. Lane rủi ro: `normal` hoặc `high-risk`.

Với đề xuất chạm kiến trúc, schema, hoặc contract, kèm một ADR DRAFT gồm: tiêu đề, bối cảnh, quyết định, hệ quả. Đánh dấu ADR ở trạng thái draft chờ Human duyệt.

## 5. Output

Ghi `docs/proposals/harness_improvement_<date>.md` — báo cáo markdown gồm:

- Bảng tóm tắt tín hiệu.
- Danh sách đề xuất xếp theo ưu tiên.
- Các ADR draft (nếu có).

## 6. Chế độ I/O

- `run_command`: gọi các lệnh `harness_cli` read-only ở mục 2.
- `view_file`: đọc `docs/HARNESS_AUDIT.md` và `docs/IMPROVEMENT_PROTOCOL.md`.
- `write_to_file`: ghi báo cáo một lần vào đường dẫn ở mục 5.

Không dùng lệnh ghi harness, không dùng lệnh sửa code.

## 7. Ranh giới

- Không tự đóng backlog.
- Không tự chuyển story sang trạng thái implemented.
- Chỉ đề xuất; không thực thi thay đổi.

Con người ra quyết định cuối (Human-in-the-loop).

## 8. Khai báo

Khai báo tại `.agents/registry.yaml`:

```yaml
- id: harness-auditor
  status: draft
```

Gắn vào `governance_loop` trong `.agents/pipeline.yaml`, chạy cuối phiên hoặc định kỳ tuần, ngoài đường giao hàng:

```yaml
governance_loop:
  - id: harness-auditor
    schedule: end-of-session-or-weekly
    lane: off-delivery-path
```
