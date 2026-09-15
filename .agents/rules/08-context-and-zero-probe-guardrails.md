# 08 — Zero-Probe Context & Continuous Agent Training Guardrails

Quy chuẩn định hướng bất biến giúp Agent nạp đúng ngữ cảnh, triệt tiêu hành vi chạy script thăm dò ad-hoc (Zero-Probe) và tự động huấn luyện, tích lũy tri thức sau mỗi ca vận hành (Continuous In-Context Training).

---

## 1. Nguyên Tắc Ngữ Cảnh "Radar-First, Never Probe" (Zero-Probe Invariant)

Nhằm chấm dứt tình trạng agent chạy hàng loạt lệnh shell rác chỉ để thăm dò trạng thái DB hoặc tìm đường dẫn tệp:

1. **CẤM TUYỆT ĐỐI Câu Lệnh Thăm Dò Ad-hoc (No Ad-hoc Probing Scripts)**:
   - Nghiêm cấm chạy các lệnh one-liner kiểu `python -c "import sqlite3; conn = ...; print(conn.execute(...))"` chỉ để đếm số bài viết, kiểm tra trạng thái bài viết hoặc dò tìm cấu trúc bảng.
   - Nghiêm cấm chạy các vòng lặp python ad-hoc chỉ để đếm file trong `data/silver` hay `data/work_packages`.
2. **Kính Ngắm Trinh Sát Duy Nhất (Single Observability Lens)**:
   - Mọi ca vận hành BẮT BUỘC chỉ dùng **1 lệnh duy nhất** để lấy toàn bộ bức tranh ngữ cảnh:
     ```powershell
     & "C:\venvs\news-scape\Scripts\python.exe" project/scripts/pipeline_radar.py status
     ```
   - Lệnh này đã tích hợp sẵn toàn bộ logic kiểm tra:
     - Số bài cào trong ngày từ CSDL.
     - Số bài L1 unrouted chưa qua bộ lọc.
     - Số bài L1 resolved đang chờ nạp Code-First.
     - Số tác vụ Gold đang chờ xử lý.
     - Độ tươi cào tin (Liveness) & cảnh báo khoảng trống đêm (Overnight gap).
     - **Chỉ rõ chính xác 1 câu lệnh chuẩn** cần thực thi tiếp theo.
3. **Tuân Thủ Chỉ Dẫn Của Radar (Follow Radar Recommendation)**:
   - Agent không được tự ý phát minh ra các chuỗi lệnh khác nếu Radar đã chỉ rõ câu lệnh hành động tiếp theo.

---

## 2. Ranh Giới Ngữ Cảnh Tinh Gọn (Context Boundary & Token Conservation)

Tuân thủ nghiêm ngặt [`docs/CONTEXT_RULES.md`](../../docs/CONTEXT_RULES.md):

1. **Bộ Ba Tệp Đọc Ban Đầu (Initial Context Triad)**:
   - Khi bắt đầu một phiên làm việc mới, Agent CHỈ ĐƯỢC đọc tối đa 3 tài liệu:
     1. `AGENTS.md` (Authority Gate & Rules).
     2. `docs/SESSION-LATEST.md` (Bối cảnh bàn giao phiên trước, đọc trong 1 màn hình).
     3. Tệp Skill chuyên trách tương ứng trong `.agents/skills/` (`pipeline-radar`, `news-scape-agent-operations`, `l1-entity-matcher`, hoặc `gold-financial-analyst`).
2. **Danh Mục Tệp CẤM ĐỌC Trực Tiếp (Blacklisted Discovery Files)**:
   - **CẤM đọc `project/data/entities/entities.json` (1.5 MB)**: Bảng tra cứu thực thể 10 miền đã được tóm tắt sẵn trong `l1-entity-matcher/SKILL.md`. Việc đọc tệp 1.5 MB làm cháy context window và làm suy giảm độ chính xác của LLM.
   - **CẤM đọc trực tiếp toàn bộ thư mục `data/silver/` hay `data/bronze/`**: Trừ khi nhiệm vụ cụ thể yêu cầu sửa bộ bóc tách scraper.
3. **Quy Tắc Dừng Khi Khớp Trực Tiếp (Direct Match Stop Heuristic)**:
   - Khi `grep_search` hoặc `view_file` đã tìm thấy đúng hàm/dòng code mục tiêu, Agent BẮT BUỘC dừng việc đọc thêm các file xung quanh.

---

## 3. Cơ Chế Huấn Luyện Agent Liên Tục (Continuous Agent Training Loop)

Sau mỗi ca thực thi thành công hoặc khi phát hiện ma sát nghiệp vụ, Agent BẮT BUỘC thực hiện quy trình "chưng cất tri thức" (Knowledge Distillation) để các thế hệ Agent kế tiếp không lặp lại sai lầm:

1. **Đúc Kết Ma Sát Thành Guardrails (Friction-to-Rule)**:
   - Khi gặp sự cố môi trường (ví dụ: *Windows Permission Timeout khi Subagent ghi file*), không để bài học trôi mất trong chat transcript.
   - BẮT BUỘC cập nhật ngay vào Rule hoặc System Prompt: Huấn luyện Subagent tự động fallback ghi vào thư mục `scratch/` để Parent Agent thu hồi an toàn.
2. **Đóng Gói Thành Quy Trình Chuẩn (Experience-to-Skill)**:
   - Bất kỳ chuỗi thao tác nào được tối ưu (ví dụ: *cờ `--from-db --date today --mini-batch 25` của `l1_route.py`*) phải được ghi ngay vào thư viện lệnh chuẩn của [news-scape-agent-operations/SKILL.md](../skills/news-scape-agent-operations/SKILL.md).
3. **Tích Lũy Tri Thức Danh Mục Thực Thể (Catalog Feedback)**:
   - Các thực thể ngoài danh mục được phát hiện trong phiên (`Sun Group`, `CITIGYM`, `LPT`...) phải được phân loại `in_list: false`, `entity_id: null` và gom vào `unlisted_candidates` để Agent chuyên trách `entity-curator` đề xuất bổ sung có kiểm soát.
4. **Bàn Giao Trạng Thái Sạch Sẽ (Session Handoff Invariant)**:
   - Kết thúc phiên làm việc, Agent BẮT BUỘC ghi đè (overwrite, không append) tệp [`docs/SESSION-LATEST.md`](../../docs/SESSION-LATEST.md) để Agent phiên sau kế thừa ngay lập tức mà không phải đọc lại lịch sử chat.
