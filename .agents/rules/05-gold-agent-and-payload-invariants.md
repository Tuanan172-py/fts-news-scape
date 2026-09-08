
---
trigger: always_on
---
# 05 — Gold Tier Responsibility & Clean Paragraph Payload Invariants

Quy tắc thiết kế cốt lõi và ranh giới nghiệp vụ bất biến cho tầng Gold và cơ chế Handoff trên Antigravity 2.0:

## 1. Ranh giới Phân công Trách nhiệm (Scripts Automate vs Gold Agents)

Hệ thống phân chia ranh giới tuyệt đối thành 2 vùng:

### A. Vùng Hạ tầng Tự động hóa (Scripts Automate):

- **Bronze**: Cào mã nguồn và lưu trữ nguyên bản bất biến (`raw_html` + `.meta.json`) phục vụ audit và kiểm chứng SHA256.
- **Silver**: Chuẩn hóa, bóc tách cấu trúc DOM, phát hiện biến đổi (SimHash/Change Detection) và **tinh lọc dữ liệu thành các đoạn văn thuần túy**.
- **Task Packaging**: Đóng gói các file `.task.json` chứa payload văn bản sạch để chuyển giao (handoff).
- **Quality Gating & Ingest**: Kiểm tra hợp đồng Definition-of-Done (DoD Schema), nạp database SQLite (`monocle.db`).
- **Delivery**: Phân tuyến theo danh sách theo dõi của từng người dùng và xuất file `final.csv`.

### B. Vùng Trí tuệ Tầng Gold (Agents Realm — Đảm nhận trọn vẹn 2 lớp nghiệp vụ):

- **Lớp 1 (Xác định Thực thể — Entity Recognition)**:
  - Nhận diện toàn diện: Mã CP (3 ký tự in hoa), Tên công ty, Sàn niêm yết, Ngành kinh doanh, Chỉ số thị trường, và các trường có trong data/entitties.
  - Phân loại nhóm `categories` và trích xuất `surface`.
- **Lớp 2 (Xử lý Nội dung & Ngữ nghĩa — Content Processing)**:
  - Tóm tắt súc tích (`summary`: abstractive + key_points).
  - Phân tích hàm ý thị trường (`implication`: tác động doanh thu/dòng tiền/cổ phiếu).
  - Chấm điểm trọng yếu động (`materiality_score`: từ 0.1 đến 1.0).
  - Phân loại sắc thái (`sentiment`: positive/negative/neutral).
  - Trích xuất chứng cứ có căn cứ (`citations`: $\ge 2$ trích dẫn nguyên văn $\ge 20$ ký tự).

---

## 2. Quy chuẩn Dữ liệu Handoff cho Agents (Lean Payload & Mini-Batch Invariants)

Nhằm tối ưu tốc độ, giảm thiểu 95% Token Burn và triệt tiêu hoàn toàn ảo giác (hallucination) do rác thông tin:

1. **Bảo toàn Bản gốc Raw (Immutable Bronze)**:
   - File `raw_html` và `meta.json` luôn được lưu giữ nguyên bản tại Bronze để kiểm toán và đối chiếu SHA256.
2. **Loại bỏ Hoàn toàn Rác DOM (Zero-Waste Task Packet)**:
   - Tuyệt đối KHÔNG đưa `structure.links` (hàng ngàn liên kết menu/header/footer) và `images` vào Task Packet. Dung lượng 1 packet phải được nén dưới **10 KB** (thay vì 180 KB).
3. **Bảo toàn Đoạn văn Nguyên bản (Verbatim Paragraph Pruning Invariant)**:
   - Bộ lọc boilerplate (`pruner.py`) loại bỏ triệt để: Teaser ("Bài liên quan", "Xem thêm"), Hotline, Email, Tòa soạn, Giấy phép, Copyright, nguồn tin vặt.
   - **RÀNG BUỘC CỐT LÕI**: Bộ lọc BẮT BUỘC loại bỏ theo **nguyên khối đoạn văn** (`<p>`). Tuyệt đối KHÔNG cắt tỉa, biên tập lại câu từ trong các đoạn văn giữ lại, nhằm đảm bảo mọi `source_span` trích dẫn citations ($\ge 20$ ký tự) luôn là chuỗi con nguyên văn (exact substring) hợp lệ, vượt qua cổng kiểm tra DoD Ingest.
4. **Gom Lô Siêu Tốc (Consolidated Mini-Batch Handoff)**:
   - Khuyến khích đóng gói các task thành các mini-batch (5–10 bài/file `batch_XX.task.json`).
   - Subagent chỉ gọi 1 lần `view_file` và 1 lần `write_to_file` mảng JSON cho cả lô, giảm 90% số Tool Calls I/O.
5. **Tiếp sức Thực thể L1 $\rightarrow$ Gold (L1-Assisted Chaining)**:
   - Task Packet gửi cho Gold Agent BẮT BUỘC phải nhúng kèm danh sách mã cổ phiếu đã được L1 bóc tách sẵn (`input.l1_entities`), giúp Gold Agent tập trung trực tiếp vào việc phân tích tác động tài chính và chấm điểm trọng yếu.

---

## 3. Cấm Tuyệt đối Giả lập Trí tuệ Agent bằng Heuristic Script (No Script Emulation)
- **Tuyệt đối không viết script Python để tự sinh kết quả Gold/L1**: Không dùng regex hay heuristic rules trong mã lệnh để bypass Subagents và sinh output JSON.
- **Nhiệm vụ của Subagents**: Xử lý ngữ nghĩa, trích xuất thực thể, tóm tắt, suy luận hàm ý, chấm điểm trọng yếu và trích dẫn citations là vùng trí tuệ độc quyền của Subagents (Model: Flash/Pro).
- **Quy trình chuẩn**: Orchestrator kích hoạt Subagents qua `invoke_subagent` $\rightarrow$ Subagent xử lý task và ghi `data/agent_outputs/` $\rightarrow$ Chạy script Ingest & Delivery (`python scripts/run_agent_hierarchy.py --ingest-and-deliver`) để kiểm toán và giao hàng.

