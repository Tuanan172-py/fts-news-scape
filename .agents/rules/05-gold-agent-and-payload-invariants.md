
---
trigger: always_on
---
# 05 — Unified Article Processor, Smart Paragraph Distillation & Priority-Queue Invariants

Quy tắc thiết kế cốt lõi và ranh giới nghiệp vụ bất biến cho Agent xử lý bài đăng thống nhất trên Antigravity 2.0:

## 1. Ranh Giới Phân Công Trách Nhiệm (Unified Cognitive Model)
Hệ thống phân chia ranh giới tuyệt đối thành 2 vùng:

### A. Vùng Hạ Tầng Tự Động Hóa (Scripts Automate — 0 Token):
- **Bronze**: Cào mã nguồn và lưu trữ nguyên bản bất biến (`raw_html` + `.meta.json`) phục vụ audit và kiểm chứng SHA256.
- **Silver**: Chuẩn hóa, bóc tách cấu trúc DOM, phát hiện biến đổi (SimHash/Change Detection) và tách mảng đoạn văn bản `p[]`.
- **Priority Sorter & Packaging**: Quét nhận diện thực thể Code-First (`{code_entities}`), chấm điểm ưu tiên, đóng gói Mega-Batch (100 bài/batch) dưới dạng **Compact JSON** (`json.dumps(..., separators=(',', ':'))`).
- **Expander & Reconciliation**: Ánh xạ đối soát Intent chéo (`BOTH`, `LLM_ONLY`, `CODE_ONLY`), bù đắp citations nguyên văn từ chỉ số đoạn `c: [0, 2]`, kiểm tra DoD Schema, nạp database SQLite (`monocle.db`).
- **Delivery First**: Phân tuyến và xuất file Excel giao hàng sớm cho User ngay sau Batch 1 (`users/output/<user>/<date>.xlsx`).

### B. Vùng Trí Tuệ Thống Nhất (Unified Cognitive Agent — `agent_article`):
- Không còn phân biệt L1 vs GOLD; một Agent duy nhất đảm nhận trọn vẹn cả hai lớp nghiệp vụ trong **1 lượt duy nhất (Single-turn, Zero-tool)**:
  - **Lớp 1 (Nhận diện Thực thể & Intent Độc lập)**: Trích xuất các đối tượng ngữ nghĩa theo 11 mã nhóm (`TIC`, `COM`, `PER`, `FND`, `IDX`, `EXC`, `IND`, `GEO`, `THM`, `AST`, `INS`), không bị thiên kiến bởi Code.
  - **Lớp 2 (Xử lý Nội dung & Ngữ nghĩa)**: Tóm tắt súc tích (`s`), các luận điểm chính (`k`), phân tích hàm ý thị trường (`im`), phân loại sắc thái (`sn`), độ nhạy thời gian (`ts`), và chỉ số đoạn trích dẫn (`c`).

---

## 2. Quy Chuẩn Payload & Lọc Đoạn Thông Minh (Smart Semantic Paragraph Distillation)

Nhằm tối ưu tốc độ, triệt tiêu 100% rác DOM và ngăn chặn bùng nổ token:

1. **Bắt Buộc Compact JSON (Anti-Line-Truncation Invariant)**:
   - File packet gửi cho Agent BẮT BUỘC phải ghi dạng **Compact JSON** (`json.dumps(..., separators=(',', ':'))`), TUYỆT ĐỐI KHÔNG dùng `indent=2`.
   - Bảo đảm không có bất kỳ dòng vật lý nào dài quá 2.000 ký tự làm kích hoạt lỗi cắt dòng (line truncation) của parser, triệt tiêu nguyên nhân gốc khiến Agent tự mở vòng lặp Grep.
2. **Lọc Đoạn Giá Trị Cao (Thay thế trần cắt tỉa 2.200 ký tự cứng)**:
   - `p0`: Bắt buộc giữ đoạn Sapo mở đầu (chứa 70% nội dung sự kiện theo cấu trúc tháp ngược báo chí).
   - `p1..pk`: Giữ các đoạn chứa số liệu định lượng (%, tỷ đồng, triệu USD, KQKD, nợ xấu) và phát ngôn lãnh đạo / sự kiện pháp lý.
   - Loại bỏ triệt để: Lịch sử thành lập doanh nghiệp, giải thích thuật ngữ chung, liên kết xem thêm và footer tòa soạn.
3. **Citations bằng Chỉ Số Đoạn (`c: [0, 2]`)**:
   - Agent chỉ phát ra số thứ tự của các đoạn văn bản chứa chứng cứ.
   - Script Expander bên ngoài (0 token) tự động trích xuất chuỗi con nguyên văn từ `p0`, `p2` $\rightarrow$ Bảo đảm 100% vượt qua cổng DoD mà tiết kiệm hàng chục nghìn output token.

---

## 3. Hàng Đợi Mega-Batch Phân Tầng Ưu Tiên (Priority-Queue Mega-Batching)

Cố định quy chuẩn **100 bài / batch**:

1. **TIER 1 — Delivery First (Batch 1, 100 bài)**:
   - Bài khớp Ticker/Alias nằm trong Watchlist active (`manifest.yaml`, e.g., user `AnPT`) hoặc biến động vĩ mô khẩn (NHNN, lãi suất điều hành, tỷ giá, GDP, CPI, thuế tự vệ).
   - **Quy trình**: Đóng gói ngay vào **Batch 1** $\rightarrow$ LLM chạy $\rightarrow$ Expander đối soát $\rightarrow$ **Kích hoạt ngay `write_user_output.py` để xuất bản file Excel giao cho người dùng trước trong 2–3 phút**.
2. **TIER 2 & 3 — Background Queue (Batch 2..N, 100 bài/batch)**:
   - Cổ phiếu VN30 ngoài watchlist, báo cáo tài chính quý/năm, công bố thông tin hành chính, tin cổ đông nhỏ, tin thị trường chung.
   - **Quy trình**: Vẫn xử lý **FULL toàn bộ cả bài** (không bỏ sót bài nào, không để bài nào ở trạng thái L1-only mãi mãi), nhưng xếp hàng đợi phía sau để chạy các batch nối tiếp, hoàn tất nạp SQLite để làm giàu kho dữ liệu phân tích với **độ phủ 100%**.

---

## 4. Cơ Chế Nhận Diện Intent Độc Lập & Báo Cáo 2 Cột (Dual-Track Intent)

1. **Nhận diện độc lập ban đầu**:
   - Code-First quét mã CP và từ điển cứng $\rightarrow$ `{code_entities}`.
   - LLM đọc ngữ nghĩa tự nhiên và trích xuất thực thể theo nhóm $\rightarrow$ `{llm_entities}`.
2. **Lớp đối soát 0 token (`article_expand.py`)**:
   - `BOTH`: Cả Code và LLM cùng tìm thấy (Độ tin cậy cao nhất).
   - `LLM_ONLY`: LLM phát hiện ngữ nghĩa sâu mà Code không có từ khóa (Đưa vào `unlisted_candidates` để mở rộng catalog).
   - `CODE_ONLY`: Khớp từ khóa máy móc.
3. **Minh bạch hóa trên Deliverable Excel (`users/output/<user>/<date>.xlsx`)**:
   - Bổ sung 2 cột riêng biệt `intent_llm` và `intent_code` kèm cột phân loại nguồn gốc `intent_source`.

---

## 5. Cấm Tuyệt Đối Giả Lập Trí Tuệ Agent Bằng Heuristic Script (No Script Emulation)
- **Tuyệt đối không viết script Python để tự sinh kết quả phân tích**: Không dùng regex hay heuristic rules trong mã lệnh để bypass LLM và sinh output JSON tóm tắt/hàm ý.
- **Vùng độc quyền của LLM**: Xử lý ngữ nghĩa sâu, nhận diện đối tượng mơ hồ, tóm tắt, suy luận hàm ý tài chính và phân loại sắc thái là vùng trí tuệ độc quyền của LLM.
