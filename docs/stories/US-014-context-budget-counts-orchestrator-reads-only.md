# US-014 — Ngân sách context chỉ đếm tệp của agent điều phối

- **Status:** implemented
- **Lane:** tiny
- **Parent / Epic:** Harness policy
- **Intake date:** 2026-09-17 (intake #14)
- **Depends On:** none — đóng backlog #6

## Product Contract

Quy tắc ngân sách context không còn phạt hành vi ủy thác khảo sát cho subagent — đúng mục đích khai
báo của chính nó là kiểm soát context window của agent điều phối.

## Vấn đề

`docs/CONTEXT_RULES.md` §1 đặt trần 10–15 tệp cho lane `normal`, nêu rõ mục đích là *"tránh làm tràn
Context Window"*. Nhưng công thức `score_context` (`docs/TRACE_SPEC.md` §3) đếm toàn bộ `files_read`
kê trong trace, kể cả tệp do Explore subagent đọc hộ — những tệp **không hề chiếm context window của
agent điều phối** (chúng nằm trong context riêng của subagent, chỉ trở về dưới dạng báo cáo cô đọng).

Quy tắc vì thế **phạt đúng hành vi mà chính nó khuyến khích**, tạo động cơ ngược: đọc thẳng mọi thứ
inline để giữ điểm đẹp. Bằng chứng: trace US-011 (#45) ghi vết đầy đủ và trung thực nhưng chỉ đạt
`score_context = 0.6` vì kê gộp cả tệp của 2 Explore subagent.

## Acceptance Criteria

- [x] `docs/CONTEXT_RULES.md` §1 bổ sung khối "Phạm vi áp dụng của trần số tệp".
- [x] `docs/TRACE_SPEC.md` §3 bổ sung gạch đầu dòng tương ứng cho công thức `score_context`.
- [x] Backlog #6 đóng kèm `Outcome`.

## Evidence

Hiệu lực quan sát được ngay trong cùng phiên: 3 trace tiếp theo (#46 US-012, #47 US-013, #48 US-014)
kê `files_read` theo quy tắc mới và đều đạt `score_context = 1.0`, trong khi khối lượng khảo sát thực
tế **lớn hơn** US-011 (2 Explore subagent + nhiều vòng đọc trực tiếp). Điểm số giờ phản ánh đúng mức
chiếm dụng context window thay vì phạt việc ủy thác.

## Harness Delta

Đóng backlog #6. Backlog #7 (`project/.venv` hỏng) vẫn mở — chỉ đề xuất xóa, chờ xác nhận vì là thao
tác phá hủy.

## Trace (inline)

- **Trace:** #48, `score_trace = 1.0`, `score_context = 1.0`.
- **Outcome:** completed.
