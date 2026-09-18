---
trigger: always_on
---
# 01 — Subagent Guardrails & Authority Boundary

Ranh giới quyền hạn bất biến cho MỌI Subagent trong hệ thống News-Scape trên nền tảng Antigravity 2.0:

## 1. Nguyên Tắc Zero-Tool & Single-Turn (Strict Zero-Tool Invariant)
- **Cognitive Worker (Subagent)**: BẮT BUỘC cấu hình `toolFilter: { allow: [] }`. Subagent KHÔNG được cấp bất kỳ công cụ tương tác file hay tìm kiếm nào (`view_file`, `write_to_file`, `grep_search`, `find_by_name`, `list_dir`).
- **Single-turn Prompt-in / JSON-out**: Subagent nhận toàn bộ payload bài viết qua User Prompt và trả kết quả mảng JSON trực tiếp trong Final Message trong đúng **1 lượt duy nhất**. Triệt tiêu 100% hiện tượng re-send transcript O(n²).
- **CẤM TUYỆT ĐỐI Vòng Lặp Tự Kiểm Chứng (No Self-Verification Loops)**: Cấm Subagent tự ý tìm cách gọi công cụ để rà soát citations, đọc lại file vừa ghi hoặc tra cứu từ điển ngoài.

## 2. Các Hành Động CẤM TUYỆT ĐỐI (Strict Prohibitions)
- **KHÔNG** sửa đổi database SQLite (`data/monocle.db`, `harness.db`).
- **KHÔNG** chỉnh sửa mã nguồn hệ thống (`src/**`, `scripts/**`).
- **KHÔNG** chỉnh sửa hoặc xóa các file task packets đầu vào (`data/agent_tasks/**`).
- **KHÔNG** tự ý chạy các script ingest (`l1_ingest.py`, `agent_ingest.py`, `run_user_workflow.py`). Đây là thẩm quyền độc quyền của Master Orchestrator.

## 3. Ràng Buộc Grounding Bằng Index Đoạn (Citations by Paragraph Index)
- **Chỉ số mảng đoạn `c: [0, 2]`**: Subagent CHỈ trả về số thứ tự của các đoạn văn bản làm căn cứ chứng minh (`c: [0, 2]`), TUYỆT ĐỐI KHÔNG tự chép lại chuỗi ký tự dài vào output để tránh lãng phí token và tránh trượt exact substring.
- **Bảo Đảm Bằng Xây Dựng (Guaranteed by Construction)**: Tầng Python Expander bên ngoài (`article_expand.py`, 0 token) chịu trách nhiệm cắt nguyên văn đoạn `p0`, `p2` thành chuỗi citations $\ge 20$ ký tự hợp lệ, bảo đảm vượt qua cổng DoD 100% mà không tốn output token.
- **Không suy diễn ngoài văn bản**: Tuyệt đối không bịa đặt số liệu, mã cổ phiếu hoặc sự kiện không xuất hiện trong các đoạn văn bản cung cấp.

## 4. Ràng Buộc Schema Enum & Danh Tính Người Dùng (Enums & User Identity)
- **Sentiment Enum**: `sentiment` chỉ được phép là 1 trong: `['pos', 'neg', 'neu']`.
- **Time Sensitivity Enum**: `time_sensitivity` chỉ được phép là 1 trong: `['urg', 'today', 'week', 'month', 'arch']`.
- **Entity Group Codes**: Mã nhóm trong thực thể chỉ gồm 11 mã chuẩn: `['TIC', 'COM', 'PER', 'FND', 'IDX', 'EXC', 'IND', 'GEO', 'THM', 'AST', 'INS']`.
- **Zero Hallucination User Manifest**: Khi phân tích hoặc báo cáo phân phối tin, chỉ được phép tham chiếu các người dùng thực tế được định nghĩa trong `config/entities/users/` và `users/input/manifest.yaml` (hiện tại: `AnPT`). Tuyệt đối không bịa đặt người dùng hư cấu.

## 5. Ràng Buộc Nhận Diện Thực Thể Độc Lập (Independent Intent Recognition)
- **Nhận diện độc lập**: Subagent bóc tách thực thể hoàn toàn dựa trên ngữ nghĩa văn bản, không nhận bất kỳ gợi ý (hints) nào từ Code-First để triệt tiêu thiên kiến (Confirmation Bias).
- **Phân định đối soát**: Lớp đối soát bên ngoài (Python tất định) tự động gán nhãn xuất xứ:
  - `BOTH`: Cả Code và LLM cùng nhận diện được (Độ tin cậy cao nhất).
  - `LLM_ONLY`: LLM nhận diện sâu dựa trên ngữ nghĩa (Được đẩy vào `unlisted_candidates` để mở rộng catalog).
  - `CODE_ONLY`: Code khớp từ khóa cứng nhưng LLM không coi là trọng tâm.

## 6. Rào Cản Giá Trị Mới & Chống Trùng Lặp (Value-Added Invariant)
- **Diễn giải độc lập**: Tóm tắt `summary` (`s`), các luận điểm `key_points` (`k`), và hàm ý thị trường `implication` (`im`) BẮT BUỘC phải được diễn giải bằng lời văn phân tích tài chính riêng của Agent, mang lại giá trị gia tăng so với bản tin gốc.
- **CẤM TUYỆT ĐỐI Sao Chép Đoạn Trích Vào Key Points**: Không được phép copy nguyên văn câu trích dẫn sang mảng `key_points`. Cổng kiểm định DoD Ingest sẽ tự động quét đối chiếu độ tương đồng và từ chối nạp DB nếu phát hiện `key_points` trùng lặp với `citations`.

