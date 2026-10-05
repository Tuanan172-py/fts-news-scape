---
name: ops-sentinel
description: Trực ban vận hành nhận thức của ops_daemon. Đọc trích đoạn sự kiện, breaker và đuôi nhật ký của một đợt, chẩn đoán sự cố và đề xuất đúng một lệnh trong danh sách trắng. Không thi hành gì.
---

# ops-sentinel

Agent cognitive dạng **draft** (registry), chạy qua runner `agy` một lượt, không tool, trong hồ sơ cô lập `%LOCALAPPDATA%\news-scape\agy_profiles\ops-sentinel`. Mã: `project/src/ops/sentinel.py`. Quyết định: ADR 0012.

## Khi nào được gọi

- Người vận hành gõ `/diagnose [đợt]` trên Telegram hoặc ops console.
- Nút **Chẩn đoán** đính kèm cảnh báo breaker, đợt FAILED/PARKED, tự hạ mức.

Daemon không tự gọi sentinel theo lịch: vòng điều phối phải tất định và không phụ thuộc provider, vì sự cố hay gặp nhất chính là provider mất kết nối.

## Vào / ra

| Vào | Ra |
|---|---|
| 40 sự kiện gần nhất (lọc theo đợt nếu có), trạng thái breaker, hàng `ops_waves`, 30 dòng cuối của hai log bước mới nhất | Một đối tượng JSON `{chan_doan, nguyen_nhan[], lenh_de_xuat, ly_do}` |

Ngữ cảnh cắt ở khoảng 12 nghìn ký tự. Không đọc nội dung bài báo.

## Danh sách trắng lệnh

`/retry <đợt đang chẩn đoán>` · `/resume` · `/pause` · `/run` · `/reset agy|openrouter` · `/provider agy|openrouter` · `/capture restart` · `none`.

Lệnh ngoài danh sách, hoặc `/retry` cho đợt khác, bị `parse_diagnosis` ép về `none`. Lệnh hợp lệ chỉ hiện thành **nút bấm** trong tin nhắn; daemon thi hành khi người bấm, đi qua `commands.execute` và ghi `human.command`.

## Thất bại

agy lỗi, quá hạn 240 s hoặc trả rỗng thì trả `Diagnosis(command="none")` kèm lý do. Sentinel không bao giờ làm hỏng daemon, và mỗi lần chạy đều ghi sự kiện `sentinel.diagnosis`.

## Cổng chuyển active (rule 07)

Ghi lại 10 sự cố thật; đề xuất đúng ≥ 8/10 (người vận hành chấm) thì chuyển `status: active` trong registry.
