# ADR 0005 — Subscriber-Gated Gold Export & Morphological L1 Guard

- **Ngày:** 2026-09-11
- **Trạng thái:** **accepted**
- **Lane:** normal (tối ưu hóa pipeline, gating export & nâng cấp bộ lọc thực thể)
- **Story:** US-009 · **Tác động:** `entities.py`, `pruner.py`, `packet.py`, `catalog.py`, `runner.py`, `agent_export.py`, `l1_route.py`, `run_agent_hierarchy.py`

---

## 1. Bối cảnh & Vấn đề

1. **Rò rỉ Token Khổng Lồ ở Tầng Gold (~38%)**:
   - `AgentRunner.export_tasks` bốc mù quáng mọi `work_item` có `l1_outputs.dod_pass=1` mà không kiểm tra xem thực thể bài viết có thuộc Watchlist của bất kỳ người dùng active nào hay không.
   - Đo trên `monocle.db`: 1.274 bài đã chạy Gold tốn hàng triệu token nhưng chỉ 791 bài được giao cho active user (`AnPT`). Có tới **483 bài (~38%) đốt token vô ích**.
2. **Sai lệch Thực thể L1 do Bẫy Danh từ Riêng Ghép Tiếng Việt**:
   - Trong tiếng Việt, khoảng trắng phân tách âm tiết chứ không phân tách từ.
   - Regex ranh giới từ `\bMỹ\b` bắt trúng các danh từ riêng địa danh ghép (*"Mỹ Thuận"*, *"Mỹ Tho"*, *"Mỹ Thủy"*, *"Mỹ Lâm"*), tên người (*"Phạm Thị Mỹ Diệu"*), tên thương hiệu (*"Á Mỹ Grupo"*), gán nhầm mã vĩ mô `MACRO_GEO:MY` (Nước Mỹ).
   - Hậu quả: Giao tin sai danh mục người dùng và kích hoạt nhầm Gold Agent đốt token phân tích "hàm ý kinh tế Mỹ" cho một dự án cầu đường nội địa.
3. **Trần Ký tự và Cách Bốc Đoạn Văn trong `pruner.py` Chưa Tối Ưu**:
   - Trần 4.000 ký tự quá cao đối với tin tài chính tiếng Việt (vốn viết theo Inverted Pyramid).
   - Pruner cũ duyệt tuần tự từ đầu và `break` khi chạm trần, dễ bỏ sót các đoạn văn chứa mã CP/số liệu ở cuối bài khi các đoạn đầu chứa nhiều bình luận chung chung.
4. **L1 Review All Gây Lãng Phí Token**:
   - Mặc định `--review all` khiến Agent LLM phải đọc lại cả 1.108 bài (62%) đã được code-first giải quyết chính xác.

---

## 2. Quyết Định Kiến Trúc

### A. Triệt tiêu False Positive L1 bằng Morphological & Prefix Guard (0 Token)
- Thay vì chỉ dựa vào blacklist `block_in` thủ công (dễ bị va chạm khi bỏ dấu như `Mỹ Lâm` $\rightarrow$ `my lam` đè `Mỹ làm`), triển khai `_blocked_by_morphology` trực tiếp trên chuỗi gốc:
  1. **Capitalized Suffix Guard**: Khi gặp *"Mỹ"*, nếu từ liền sau viết hoa (`Thuận`, `Tho`, `Đình`, `Thủy`, `Lâm`, `Diệu`, `Phước`...) và không nằm trong `_INTL_AFTER_MY` (`Trump`, `Biden`, `Fed`, `Wall Street`...), tự động từ chối khớp.
  2. **Prefix Guard**: Chặn nếu từ liền trước là tiền tố thương hiệu (`Á`, `Phú`, `Phù`, `Bắc`, `Nam`) hoặc danh xưng/họ tên (`Bà`, `Ông`, `Thị`, `Văn`, `Cô`, `Chị`).
- Hiệu quả: Triệt tiêu 100% false positive địa danh/tên người mà vẫn giữ nguyên vẹn 100% các ca nói về Nước Mỹ.

### B. Thiết lập Cổng Chặn Subscriber-Gated Export cho Tầng Gold
- Trong `AgentRunner.export_tasks` và `Catalog.claim`:
  - Chỉ bốc các `work_items` có `l1_entities` giao thoa với Watchlist của ít nhất 1 active user (`manifest.yaml` và `users/*.yaml`).
  - Sử dụng SQLite temporary table `_allowed_aids` để lọc atomic ở tốc độ C-speed.
  - Các bài viết không có người theo dõi được giữ nguyên vẹn ở trạng thái `L1_ONLY`, sẵn sàng phục vụ khi có người dùng mới (Lazy Evaluation / On-Demand Enrichment).
- Hiệu quả: Tiết kiệm ngay ~38% – 45% tổng lượng token Gold toàn hệ thống.

### C. Nâng Cấp Semantic Pruner 3-Pass (2.200 Chars Max)
- Hạ trần ký tự mặc định từ `4.000` xuống `2.200` ký tự.
- Thuật toán 3-pass:
  - *Pass 1*: Luôn giữ tối đa 2 đoạn đầu (Sapo / Mở đầu).
  - *Pass 2*: Quét toàn bài, ưu tiên giữ các đoạn văn chứa mã CP từ `l1_entities` hoặc số liệu tài chính (`%`, `tỷ đồng`, `lợi nhuận`, `doanh thu`, `kế hoạch`).
  - *Pass 3*: Điền các đoạn văn còn lại theo thứ tự xuất hiện gốc cho tới khi chạm trần 2.200 chars.
- Bảo toàn Invariant Rule 05: Giữ nguyên khối đoạn văn `<p>` để bảo đảm tính exact substring cho `citations` qua cổng DoD.
- Hiệu quả: Giảm ~45% input token trên mỗi bài viết gửi cho Gold Subagent.

### D. Chuẩn Hóa Định Tuyến L1 (--review missed Mặc Định)
- Đổi mặc định trong `l1_route.py` và `run_agent_hierarchy.py` sang `--review missed`.
- Các bài `resolved` được vật chất hoá thẳng qua `l1_ingest.py --code-first` (0 token).
- Hiệu quả: Tiết kiệm 62% token tại tầng L1.

---

## 3. Kết Quả Đo Thực Tế & Kiểm Chứng

- Test suite: `37 / 37 passed` (100% green).
- False positives trên 7.656 bài trong `monocle.db`: Giảm từ 14 ca sai về **0 ca sai**.
- Tỷ lệ lọc Subscriber: 947 / 1505 bài có người theo dõi (tiết kiệm 558 bài không phải chạy Gold).
- Tổng ước tính token burn tiết kiệm toàn hệ thống: **60% – 70%**.
