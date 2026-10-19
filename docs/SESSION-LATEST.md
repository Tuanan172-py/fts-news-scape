# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-10-19 17:28 (GMT+7)  
**Nhánh:** dev/us038 | **Nhiệm vụ:** Rà Soát Automate & Xử Lý Cuốn Chiếu 2.000 Bài Backlog (Runner AGY)

---

## 1. Kết Quả Vận Hành Dữ Liệu Cuối Tuần (17/10 & 18/10/2026)

Toàn bộ bài đăng trong 2 ngày nghỉ cuối tuần đã được đối chiếu sitemap độc lập, cào bù đầy đủ các nguồn và phân tích hoàn tất qua runner `agy` (`gemini-3.8-flash-low`):

| Ngày dữ liệu | Mã Wave | Bài đóng gói | Xong (Lượt 1 + Các vòng vá) | Tỷ lệ đạt | Quota Token | Phí ước tính | Dòng Excel Final |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **17/10/2026** | `W1017_DAY` | 82 | 57 + 26 = **83** | **98.8% ✅** | 190.664 | ~$0.0207 | **46 dòng** |
| **18/10/2026** | `W1018_DAY` + `W10191035` | 150 + 3 | 150 + 3 = **153** | **100.0% ✅** | ~395.000 | ~$0.0425 | **116 dòng** |
| **TỔNG** | — | **235** | **236 bài** | **100.0%** | **~585.664** | **~$0.0632** | **162 dòng** |

Đã xuất bản đầy đủ file Excel tại `C:\data\news-scape\users_output\<user>\` cho 5 chuyên viên (`AnPT`, `PhoHG`, `ThanhTD`, `UyenNNT`, `VyPTT`).

---

## 2. Rà Soát Quy Trình Automate & Khắc Phục Lỗi Vòng Lặp Mở Đợt Rác (Ops Daemon)

### 2.1. Triệu chứng & Báo động
- NewsBot gửi cảnh báo lúc 09:49: `[CẢNH BÁO] Đủ điều kiện mở đợt (260 ≥ 100 bài) nhưng chưa có mandate`.
- Người vận hành đã cấp mandate `/level L1` (hiệu lực đến 31/10/2026).
- Sau khi có mandate L1, `ops_daemon` tự động mở đợt liên tục mỗi 2 phút cho ngày `18/10/2026` (`W10191014`, `W10191016`, `W10191021`...), nhưng bước `prepare` thoát với mã 2 (`Không còn bài để xử lý`), chặn đứng 99 bài mới của ngày `19/10/2026`.

### 2.2. Phân tích Nguyên nhân Gốc (Root Cause Analysis)
1. **Lỗi Fail-Open trong Sensor (`src/ops/sensor.py`)**:
   - `read_pending()` gọi `load_candidates(..., with_content=False)`.
   - Vì không nạp cột `content_text`, hàm `is_thin_row()` thiếu dữ kiện để đếm số đoạn văn $\rightarrow$ trả về `False` (fail-open).
   - Hơn 100 mẩu tin ngắn/stub crawl từ Cafef/Vietnambiz (< 2 đoạn trích dẫn) bị sensor tính nhầm là bài chờ hợp lệ trên ngày 18/10. Sensor thấy 18/10 còn bài nên cố định `target_date = 2026-10-18`.
2. **Lỗi Nghẽn LIMIT SQL Trước Tầng Lọc Python (`scripts/article_pack.py`)**:
   - Trong `load_candidates()`, câu lệnh SQL chèn `LIMIT 100` **trước** khi đưa qua bộ lọc `[r for r in rows if not is_thin_row(r)]`.
   - 100 bài mới nhất theo `published_at DESC` của chiều 18/10 đều là mẩu tin ngắn. SQL lấy trọn 100 bài này, Python lọc mỏng loại bỏ toàn bộ 100 bài $\rightarrow$ trả về rỗng! 3 bài hợp lệ xuất bản buổi sáng bị chặn ngoài cửa sổ `LIMIT 100` nên không bao giờ được chạm tới.
3. **Nghẽn Đo Backlog Toàn CSDL (821s thay vì 0.9s)**:
   - Khi đo `backlog_all`, `load_candidates` mặc định `exclude_thin=True` đã duyệt và quét tệp đĩa của 18.000 bài trong CSDL, làm luồng sensor bị nghẽn 13.6 phút.

### 2.3. Giải Pháp & Bản Vá
1. **`project/src/ops/sensor.py`**:
   - Đổi `with_content=True` trong vòng lặp ngày để `is_thin_row` lọc chính xác bài mỏng, đồng bộ hoàn toàn với `article_pack.py`.
   - Thêm `exclude_thin=False` cho nhánh `with_backlog` (chỉ dùng báo cáo hiển thị) $\rightarrow$ thời gian đo giảm từ 821s xuống **2.3s**.
2. **`project/scripts/article_pack.py`**:
   - Khi `exclude_thin=True`, chuyển sang cơ chế streaming cursor gom đủ `limit` bài đạt chuẩn mới dừng (`break`), không chèn `LIMIT` cứng trong SQL làm nghẽn các bài hợp lệ phía sau.
3. **Khởi động lại Scheduled Task & Nghiệm thu Thực tế**:
   - Khởi động lại task `\news-scape-ops` để nạp mã mới vào tiến trình `pythonw.exe`.
   - Đợt `W10191035` gom thành công 3 bài hợp lệ còn sót của ngày 18/10, hoàn tất nạp DB (3/3 bài, 100%).
   - Sensor chuyển sạch sẽ: `per_date: [('2026-10-18', 0), ('2026-10-19', 105)]` $\rightarrow$ `target_date = 2026-10-19`.
   - Đợt `W10191037` cho ngày hôm nay **19/10/2026 (99 bài, 2 lô song song)** đã tự động mở và nạp DB đạt **99/99 bài (100.0%)**.

---

## 3. Vận Hành Giải Phóng Tồn Đọng Cuốn Chiếu (Rolling Backlog Waves)

Thực thi tuần tự các đợt 500 bài pending theo lệnh của Operator qua runner `agy` (`gemini-3.8-flash-low`):

| Mã Wave | Bài đóng gói | Tier 1 (Watchlist) | Hoàn tất phân tích | Tỷ lệ đạt | Quota Token | Phí ước tính | Nạp DB |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`W_BACKLOG_500_01`** | 500 | 300 (60.0%) | 270 + 228 + 2 = **499** | **99.8% ✅** | 1.120.385 | ~$0.1201 | 499 bài |
| **`W_BACKLOG_500_02`** | 500 | 263 (52.6%) | 333 + 166 + 1 = **500** | **100.0% ✅** | 993.577 | ~$0.1084 | 499 bài |
| **`W_BACKLOG_500_03`** | 499 | 301 (60.3%) | 351 + 146 + 2 = **499** | **100.0% ✅** | 960.047 | ~$0.1039 | 499 bài |
| **`W_BACKLOG_500_04`** | 499 | 262 (52.5%) | 308 + 185 + 22 + 9 = **499** | **100.0% ✅** | 1.192.072 | ~$0.1221 | 499 bài |
| **TỔNG 4 ĐỢT** | **1.998 bài** | **1.126 bài (56.4%)** | **1.997 bài** | **99.9%** | **4.266.081** | **~$0.4545** | **1.996 bài** |

### Cập Nhật Deliverables Cho 5 Chuyên Viên Phân Tích
Đã chạy `write_user_output.py --force`, cập nhật **13.314 dòng final** (+346 dòng) qua các file `.xlsx` cho 5 chuyên viên:
- **AnPT**: **3.860 dòng final** (+99 dòng)
- **VyPTT**: **3.774 dòng final** (+110 dòng)
- **UyenNNT**: **2.079 dòng final** (+57 dòng)
- **ThanhTD**: **1.981 dòng final** (+46 dòng)
- **PhoHG**: **1.620 dòng final** (+34 dòng)

### Hiện Trạng Kho Sau 4 Đợt Cuốn Chiếu
- **Tổng số bài đã phân tích Gold**: **16.570 bài (~49.1% toàn kho)** (tăng từ 14.543 bài lúc đầu ngày).
- **Tồn đọng còn lại**: **16.381 bài** (đã giải phóng 2.279 bài so với 18.660 bài).

---

## 4. Cải Tiến Kiến Trúc & Kiểm Định Chất Lượng

1. **Bản Vá Nâng Cấp Tự Động Gói Công Việc (Auto-Upgrade Legacy Work Package)**:
   - *Nguyên nhân*: Các bài viết cũ có `work_package` v1.0 tạo từ tháng 09/2026 mang `raw_sha256` của bản cào sơ khởi. Khi trang web được Bronze re-crawl, `raw_sha256` trên đĩa thay đổi khiến `verify_preconditions` báo lỗi `raw_sha256 mismatch (integrity)` khi nạp vào DB.
   - *Giải pháp*: Cập nhật `AgentRunner._register_article_lane_item` và `ingest_output` trong `src/agent/runner.py`: Tự động nhận diện các gói công việc cũ (`work_package_version != "1.1"`), nâng cấp tức thì lên bản 1.1 dựa trên nội dung Silver chuẩn và đồng bộ `work_items` table.
   - *Kiểm chứng*: Thêm unit test `test_runner_ingest_upgrades_legacy_work_package`. 100% 499 bài của đợt 4 nạp DB sạch sẽ (`ingested: done=499 failed=0`).
2. **Bộ Kiểm Thử**:
   - 79/79 tests PASS (`test_ops_core.py`, `test_ops_runtime.py`, `test_agent_infra.py`) trong 19.4s.
   - AST syntax validation đạt chuẩn Google Python Style.
3. **Quy Chuẩn Git**:
   - Cây làm việc sạch sẽ, commit chuẩn Conventional Commits kèm mã `(US-038)`.
   - Sẵn sàng đóng phiên (`clean_for_closure: true`).
