---
name: materiality-triage
description: Cổng phân loại rẻ quyết định bài tin có đáng đẩy sang phân tích Gold sâu hay không.
---

# Materiality Triage Skill

> **Mục đích:** Chấm nhanh mức trọng yếu của bài tin tài chính bằng model Flash-Lite, lọc bỏ nhiễu trước tầng Gold để tiết kiệm chi phí phân tích sâu.

## 1. Đầu vào

Đọc `data/agent_tasks/triage/*.task.json`. Mỗi task chứa:

- `article_id`: định danh bài.
- `title`: tiêu đề.
- `l1_entities`: danh sách thực thể tài chính tầng 1.
- `lead`: sapo (~200 ký tự đầu).

Task KHÔNG chứa toàn văn. Chấm điểm chỉ dựa trên `title`, `l1_entities`, `lead`. Đây là cổng rẻ, không đọc nội dung đầy đủ.

## 2. Nhiệm vụ

Chấm `materiality_hint` (số thực thang 0-1) và quyết định `gold_worthy` (bool). Chỉ bài đạt ngưỡng mới đẩy sang Gold để phân tích sâu. Bước này bổ sung cho phễu subscriber-gating có sẵn, không thay thế.

## 3. Thang trọng yếu

Dùng thang DUY NHẤT 0-1, đồng bộ rule 02-financial-domain-rules:

- `0.80–1.00` Tối quan trọng: khởi tố lãnh đạo, M&A lớn, tăng vốn đột biến, hủy niêm yết/phá sản, đổi chính sách vĩ mô/lãi suất/thuế quan lớn.
- `0.50–0.79` Quan trọng vừa: BCTC quý/năm, trúng thầu lớn, cổ tức tỷ lệ cao, thay nhân sự cấp cao.
- `0.30–0.49` Ảnh hưởng nhẹ: SXKD thường nhật, MOU, giao dịch cổ đông nhỏ, lịch ĐHCĐ.
- `0.10–0.29` Nhiễu/PR: tài trợ, từ thiện, khai trương nhỏ, bài PR chung.

## 4. Quy tắc `gold_worthy`

- Đặt `true` khi `materiality_hint >= 0.30`.
- Đặt `false` khi `materiality_hint < 0.30` (nhiễu/PR).
- Ép `false` khi `l1_entities` rỗng (không thực thể tài chính), bất kể điểm.

## 5. Output

Ghi `data/agent_outputs_triage/*.output.json` dưới dạng MẢNG JSON. Mỗi phần tử:

```json
{ "article_id": "<id>", "gold_worthy": true, "materiality_hint": 0.65, "reason": "<<=120 ky tu, chi ro su kien va thuc the>" }
```

Ghi `reason` chỉ rõ sự kiện và thực thể. Giới hạn 120 ký tự. Không sao chép nguyên văn `title`.

## 6. Chế độ 2-I/O

- Đọc bằng `view_file` đúng 1 lần.
- Ghi bằng `write_to_file` đúng 1 lần, `Overwrite: true`.
- CẤM dùng discovery tools.
- Gom lô 30 bài/đợt (cổng rẻ nên lô lớn).
- Chạy 3 luồng song song.

## 7. Ràng buộc DoD `dod-gatekeeper#triage`

- `materiality_hint` phải nằm trong `[0,1]`.
- `gold_worthy` phải nhất quán với ngưỡng `0.30`.
- `reason` không rỗng và không sao chép nguyên văn `title`.

## 8. Khai báo hệ thống

- Đăng ký tại `.agents/registry.yaml`: `id: materiality-triage`, `status: draft`.
- Khai báo là stage `materiality_triage` (optional) trong `.agents/pipeline.yaml`.
- Đặt stage `materiality_triage` trước `gold_export`.
