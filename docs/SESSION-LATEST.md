# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-11
- **Current story:** US-011 (Customizable Gold Export — User, Date, Days & Dry-Run Filters) — `implemented` (42/42 tests passed)
- **Status:** All test suites green (42/42 passed). 0 story `in_progress`.
- **Blocker:** Không còn blocker kiến trúc. Cổng L1 và Gold đã sẵn sàng chạy end-to-end với đầy đủ tùy biến linh hoạt.



## Việc đã làm phiên này (US-009 / US-010 / US-011)

### 1. Triệt tiêu False Positive L1 & Cắt giảm Token Burn (US-009 / ADR 0005)
- **Morphological Guard**: Capitalized Suffix Guard + Prefix Guard cho `MACRO_GEO:MY`. False positive giảm 14 → 0 bài trên 7.656 bài trong `monocle.db`, bảo toàn 300/300 bài Nước Mỹ thật.
- **Dynamic 3-Pass Semantic Pruner**: Hạ trần xuống 2.200 ký tự (giảm ~47% token/bài), bảo toàn nguyên văn thẻ `<p>` cho trích dẫn $\ge 20$ ký tự.
- **Subscriber-Gated Export**: Mặc định chỉ xuất bài có người dùng theo dõi, giảm ngay 37.1% số bài gọi Gold Agent (947/1.505 bài).

### 2. Tăng cường Độ chính xác & Triệt tiêu Sót bài L1 (US-010)
- **Positional Disclosure Exemption** (`_DISCLOSURE_PREFIX_RE`): Cứu **36/36 bài CBTT VNDirect** (`VND:`) thoát khỏi Stoplist tiền tệ.
- **Bank PGD Domain Guard**: Triệt tiêu 100% (36 → 0 bài) nhận nhầm Phòng Giao Dịch ngân hàng sang mã `TICKER:PGD` (Khí thấp áp).
- **NGA Morphology & Person Name Guard**: Loại bỏ 100% false positive tên người (*Bà Trần Kim Nga, Nga Rose*), bảo toàn 100% tin thời sự Nước Nga.
- **Ecosystem Aliasing**: Nhận diện chuẩn xác thương hiệu con (*VinFast* → `VIC`, *Bách Hóa Xanh* → `MWG`, *WinCommerce* → `MSN`, *FE Credit* → `VPB`, *Becamex Tokyu* → `BCM`).

### 3. Tùy biến Cổng Xuất Gold & Điều phối (US-011)
- Bổ sung các cờ `--user` (lọc đích danh), `--days` (lọc số ngày gần nhất), `--date` (lọc ngày cụ thể) và `--dry-run` (kiểm tra an toàn không ghi đĩa) cho cả `agent_export.py` và `run_agent_hierarchy.py`.
- Toàn bộ test suite: **42 / 42 tests passed 100% green**.

## Số liệu đo trên `monocle.db` thật (read-only)

| Chỉ số | Trước phiên | Sau phiên (US-009/010/011) | Thay đổi |
|---|---|---|---|
| L1 False Positive `MACRO_GEO:MY` | 14 bài (*"Mỹ Thuận"*, *"Á Mỹ"*...) | **0 bài** | **-100% false positive** |
| L1 False Positive `TICKER:PGD` (Ngân hàng) | 36 bài (*"MBB: Thành lập PGD..."*) | **0 bài** | **-100% false positive** |
| L1 False Positive `MACRO_GEO:NGA` (Tên người) | Nhiều ca (*Bà Kim Nga, Nga Rose*) | **0 bài** | **-100% false positive** |
| Thu hồi tin CBTT `TICKER:VND` | 0 bài (bị stoplist chặn) | **36 bài match chuẩn** | **+100% tin CBTT** |
| Chiều dài payload bài Gold | 4.000 ký tự (~1.800 tokens) | **2.200 ký tự (~950 tokens)** | **-47% token/bài** |
| Số bài xuất cho Gold Agent | 1.505 bài (toàn bộ pending) | **947 bài (chỉ bài user theo dõi)** | **-37.1% số bài gọi LLM** |
| **Tổng lượng token tiết kiệm ước tính** | - | - | **~66.7% tổng token burn** |


## Next Steps
1. Thực hiện chạy nạp dữ liệu định kỳ theo chuỗi:
   ```powershell
   python scripts/run_agent_hierarchy.py
   ```
2. Kiểm tra log tự phục hồi (Self-Healing) của Subagent Gold nếu có bài trượt DoD.
3. Chạy `python scripts/run_user_workflow.py` để xuất báo cáo deliverable XLSX đơn sắc mới nhất cho người dùng.
