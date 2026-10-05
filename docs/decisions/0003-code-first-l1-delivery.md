# 0003 — Kết quả nhận diện TẤT ĐỊNH (code-first) được ghi vào `l1_outputs` và giao hàng

- **Status:** accepted (Duyệt bởi Human Operator ngày 2026-09-09)
- **Date:** 2026-09-08
- **Decision-makers:** Human Operator & Agent
- **Parent / Scope:** L1 Entity Recognition → User Delivery
- **Liên quan:** [0001](0001-harness-first-approach.md) (Hard Gate), AGENTS.md §6C (No Script Emulation)

---

## Context

Cổng giao hàng cho người dùng (`src/export/user_output.py:35-50`) bắt buộc
`articles ⨝ l1_outputs (dod_pass=1)`. Bảng `l1_outputs` chỉ có MỘT nguồn ghi duy nhất:
`L1Runner.ingest_output()` — tức chỉ khi một LLM subagent đã nộp output.

Trong khi đó tầng 1 `l1_classifier` (tất định, 0 token) đã tra được thực thể và lưu vào
`l1_tasks.code_first_json`, nhưng **không có đường nào để dữ liệu đó tới cổng giao hàng**.
Bài `route='resolved'` — chính là những bài code-first ĐÃ tìm thấy mã người dùng đăng ký —
nằm `status='pending'` vĩnh viễn.

Số đo trên `data/monocle.db` ngày 2026-09-07:

| | |
|---|---|
| `articles` | 7.219 |
| `l1_tasks` | 1.787 — trong đó `resolved` có TICKER: **562** |
| lượt TICKER trong `code_first_json` | **710** (216 entity_id riêng) |
| `l1_outputs` | 685 (dừng hẳn từ 2026-08-25) — **0 entity TICKER** |
| bài qua cổng giao hàng | 424 → khớp danh mục AnPT: **146** |
| nếu đọc `code_first` | 1.320 → khớp AnPT: **743** (gấp 5,1 lần) |

Đồng thời không có runner LLM tự động nào trong repo (`requirements.txt` không có SDK nào;
`scripts/agent_stub.py` được `run_daily.ps1` gọi nhưng **không tồn tại**). Hàng đợi chỉ lớn dần:
1.102 `l1_tasks` + 3.477 `work_items` pending. Nói cách khác, cổng hiện tại phụ thuộc vào một
bước thủ công không được vận hành, nên trên thực tế nó là cổng ĐÓNG.

## Decision

Cho phép ghi vào `l1_outputs` các bản ghi có nguồn gốc **tra bảng tất định**, đánh dấu tách bạch
bằng cột mới `l1_source ∈ {'agent','code_first'}`.

Ranh giới với AGENTS.md §6C ("Cấm giả lập trí tuệ Agent bằng heuristic script"):

* **ĐƯỢC phép** — ánh xạ chuỗi ký tự → `entity_id` bằng cách tra danh mục chuẩn
  (`data/entities/entities.json`, 2.152 thực thể do tổ chức phát hành). Đây là *lookup*, kết quả
  kiểm chứng được, tái lập 100%, không có suy diễn. Bản thân `l1_classifier` đã làm đúng việc này
  từ đầu và kết quả của nó đã được tin dùng để định tuyến `resolved` vs `needs_agent`.
* **KHÔNG được phép** (giữ nguyên) — tóm tắt, `implication`, `materiality_score`, `sentiment`,
  `event_type`, `citations` ngữ nghĩa, và nhận diện thực thể **không có trong danh mục**
  (`unlisted_candidates`). Toàn bộ phần này vẫn 100% thuộc Subagent LLM.
* Bài `route='needs_agent'` (code-first không khớp gì — 541 bài) **vẫn bắt buộc qua Agent**.
  Quyết định này không thu hẹp vùng trí tuệ của Agent, nó chỉ ngừng vứt bỏ phần đã tra được.

Bản `code_first` là **tạm** theo nghĩa: khi Agent xử lý cùng `article_id`, output của Agent
được phép GHI ĐÈ (`l1_source='agent'`). Chiều ngược lại không được phép.

## Consequences

* **Tích cực**
  * Mở lại đường giao hàng: ~1.320 bài đủ điều kiện thay vì 424; AnPT từ 146 → ~700.
  * Hệ thống hết phụ thuộc vào một bước thủ công không ai chạy để có output hằng ngày.
  * Tiết kiệm token: 1.246/1.787 (70%) bài không cần gọi LLM cho L1.
  * `l1_source` cho phép đo riêng chất lượng 2 nguồn thay vì trộn lẫn.

* **Đánh đổi / Rủi ro**
  * Nhận diện tất định chỉ chạy trên **tiêu đề**, không có ngữ cảnh thân bài → bỏ sót thực thể
    chỉ xuất hiện trong body. Không hồi quy so với hiện tại (Agent L1 cũng chỉ nhận tiêu đề).
  * **False positive theo alias.** Đây là rủi ro chính và đã được xử lý TRƯỚC khi mở cổng
    (xem "Điều kiện tiên quyết"). Nếu mở cổng mà không xử lý, riêng `TICKER:IVS` sẽ phát tán
    164 bài sai cho người dùng.
  * Nhập nhằng nghĩa từ còn tồn đọng (`IND_GICS3:NUOC` với "trong nước"/"nước ngoài",
    `MACRO_GEO:MY` với "thẩm mỹ") — tầng tất định không giải được, cần Agent hoặc sửa dữ liệu
    alias biên tập. Ghi nhận, chưa chặn.

* **Điều kiện tiên quyết (ĐÃ hoàn thành trước ADR này)**
  * `GENERIC_ALIAS_STOPLIST` — chặn alias địa danh/hậu tố chung sinh tự động từ tên pháp lý.
  * Guard ngữ cảnh mã 3 ký tự ("TP.HCM" không còn là `TICKER:HCM`).
  * Guard bỏ dấu cho alias 1 từ ngắn ("quý 3" không còn là `IND_GICS*:QUY`).
  * DoD L1 kiểm `entity_id` có thật trong danh mục.
  * Kết quả đo trên 1.787 tiêu đề thật: **loại 270 khớp sai, thêm 37 khớp đúng**;
    `TICKER:IVS` từ 164 → 0.

## Rollback

Đặt lại cổng cũ bằng một điều kiện SQL: thêm `AND l1.l1_source = 'agent'` vào `_GATED_SQL`.
Không cần đổi schema ngược, không mất dữ liệu.

## Actual Outcome

_(điền sau khi vận hành 1 tuần: số bài giao / tỉ lệ khớp đúng khi kiểm tay 20 dòng /
số lần Agent phải ghi đè bản code_first)_
