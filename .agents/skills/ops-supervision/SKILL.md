---
name: ops-supervision
description: Giám sát multi-agent đang tự vận hành - đọc Phòng điều khiển, cây vết ops_spans, lệnh /map /trace /agent /improve và duyệt đề xuất cải tiến. Dùng khi cần biết agent nào đã chạy gì trong một đợt, hoặc khi xử lý hộp thư cải tiến.
---

# Giám sát multi-agent

Người vận hành chỉ giám sát và cải tiến quy trình (ADR 0014). Skill này mô tả công cụ nhìn và quyền duyệt.

## Nhìn ở đâu

| Cần biết | Dùng |
|---|---|
| Hệ thống có khoẻ không, đang chạy gì | Phòng điều khiển, màn Toàn cảnh (`python scripts/ops_daemon.py open`) hoặc `/status`, `/map` |
| Một đợt đã diễn ra thế nào | màn Đợt (Gantt và cây vết) hoặc `/trace <đợt>` |
| Một agent đang ra sao | màn Tác nhân hoặc `/agent <id>` |
| Có gì bất thường | màn Sự cố, `/log`, bản tin 08:00 và 18:00 |
| Nên đổi gì ở quy trình | màn Cải tiến hoặc `/improve` |

Phòng điều khiển chỉ nghe `127.0.0.1` (cổng trong `config/ops.yaml`, mục `control_room`).

## Dữ liệu

- **Bản đồ tĩnh:** `.agents/registry.yaml` và `.agents/pipeline.yaml`.
- **Vết động:** bảng `ops_spans` trong `ops.db`. Một đợt là một cây: workflow, step, script, agent, gate. `trace_id` là mã đợt, `actor_id` khớp id trong registry.
- Mã tạo span chỉ ghi khi daemon đặt biến `OPS_TRACE_DB`, `OPS_TRACE_WAVE`, `OPS_TRACE_PARENT`. Chạy tay `article_run.py` không ghi gì.
- KPI từng tác nhân ghi vào `agent_metrics` của `harness.db` khi đợt chốt.

## Hai điều cần nhớ khi đọc

1. Agent lúc vận hành không nạp skill động. Cột skill là skill khai trong registry; cột công cụ mới là chỗ kiểm: `article-processor` phải luôn `0 gọi · 0 từ chối`.
2. Chỗ chưa đo thì trang hiện "chưa đo", không hiện số đẹp. Chất lượng tóm tắt vẫn chưa có golden set.

## Quyền duyệt của người

- Đề xuất cải tiến tự sinh **không bao giờ tự thi hành**. **Mở story** tạo intake và story `US-IMP-nnn` ở trạng thái `planned`; **Hoãn** và **Bác** ẩn đề xuất 30 ngày.
- Mandate (standing order) tự gia hạn khi hệ thống khoẻ. Điều kiện: không có sự kiện đỏ trong 24 giờ, chuỗi đợt sạch ≥ 5, không có chuỗi đợt hỏng, không có lượt gọi công cụ trái Zero-Tool trong 7 ngày. Không đủ điều kiện thì dừng gia hạn và báo lý do. `/stop` luôn thu hồi được.
- Mandate đã hết hạn hoặc chưa từng cấp không bao giờ tự cấp lại: đó là hành động của người (`/level L1`).

## Không làm

- Không viết script sinh đề xuất bằng ngữ nghĩa thay agent: bộ phát hiện chỉ đo.
- Không thêm trần hay ngưỡng token làm cổng chặn: token chỉ được ghi nhận (ADR 0010).
