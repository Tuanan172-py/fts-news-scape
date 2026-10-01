---
name: ops-supervision
description: Giám sát đội tác nhân đang tự vận hành. Đọc Phòng điều khiển và cây vết ops_spans, dùng lệnh /map, /trace, /agent, /mandate, /improve, duyệt đề xuất cải tiến. Dùng khi cần biết tác nhân nào đã chạy gì trong một đợt, hoặc khi xử lý hộp thư cải tiến.
---

# Giám sát đội tác nhân

Người vận hành chỉ giám sát và cải tiến quy trình (ADR 0014). Skill này mô tả công cụ để nhìn và quyền duyệt của người.

## Khi nào dùng

- Cần biết hệ thống có khoẻ không và đang chạy gì.
- Cần lần lại một đợt: ai chạy, skill nào, script nào, tốn bao nhiêu.
- Có cảnh báo cần chẩn đoán, hoặc có đề xuất cải tiến chờ quyết định.

## Nhìn ở đâu

| Cần biết | Dùng |
|---|---|
| Hệ thống có khoẻ không, đang chạy gì | Phòng điều khiển, màn Toàn cảnh (`python scripts/ops_daemon.py open`), hoặc `/status`, `/map` |
| Một đợt đã diễn ra thế nào | Màn Đợt (Gantt và cây vết), hoặc `/trace <đợt>` |
| Một tác nhân đang ra sao | Màn Tác nhân, hoặc `/agent <id>` |
| Có gì bất thường | Màn Sự cố, `/log`, bản tin 08:00 và 18:00 (`/digest`) |
| Mandate còn bao lâu | `/mandate` |
| Nên đổi gì ở quy trình | Màn Cải tiến, hoặc `/improve` |

Phòng điều khiển chỉ nghe `127.0.0.1`. Cổng đặt trong `config/ops.yaml`, mục `control_room`.

## Dữ liệu vào và ra

- **Bản đồ tĩnh:** `.agents/registry.yaml` và `.agents/pipeline.yaml`.
- **Vết động:** bảng `ops_spans` trong `ops.db`. Mỗi đợt là một cây gồm quy trình, bước, script, lô agy và cổng. `trace_id` là mã đợt, `actor_id` khớp id trong registry.
- Mã ghi vết chỉ chạy khi daemon đặt biến `OPS_TRACE_DB`, `OPS_TRACE_WAVE`, `OPS_TRACE_PARENT`. Chạy tay `article_run.py` không ghi gì.
- KPI từng tác nhân vào `agent_metrics` của `harness.db` khi đợt chốt.

## Hai điều cần nhớ khi đọc

1. Tác nhân lúc vận hành không nạp skill động. Cột skill là skill khai trong registry. Cột công cụ mới là chỗ kiểm: `article-processor` phải luôn hiện "0 gọi, 0 từ chối".
2. Chỗ chưa đo thì trang ghi "chưa đo", không hiện số đẹp. Chất lượng tóm tắt vẫn chưa có bộ vàng.

## Quyền duyệt của người

- Đề xuất cải tiến tự sinh không bao giờ tự thi hành. **Mở story** tạo intake và story `US-IMP-nnn` ở trạng thái `planned`. **Hoãn** và **Bác** ẩn đề xuất 30 ngày.
- Mandate tự gia hạn khi hệ thống khoẻ. Điều kiện nằm ở [tài liệu tham chiếu](../../../project/docs/operations/ops-daemon-reference.md). Không đủ điều kiện thì dừng gia hạn và báo lý do.
- Mandate đã hết hạn hoặc chưa cấp không bao giờ tự cấp lại. Người cấp bằng `/level L1`.
- `/stop` luôn thu hồi được.

## Khi thất bại

- Phòng điều khiển không mở: xem runbook `project/docs/operations/ops-daemon.md`, mục xử lý sự cố.
- Cây vết trống: đợt chạy tay hoặc chạy trước khi có ghi vết. Chỉ đợt chạy qua daemon mới có cây vết.

## Không làm

- Không viết script sinh đề xuất bằng ngữ nghĩa thay agent. Bộ phát hiện chỉ đo.
- Không đặt trần hay ngưỡng token làm cổng chặn. Token chỉ được ghi nhận (ADR 0010).
