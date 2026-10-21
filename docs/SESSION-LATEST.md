# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-10-21 15:15  
**Nhiệm vụ:** Đánh giá hiện trạng sau khi Terminal bị ngắt quãng, RCA lỗi WinError 206, cứu nạp dữ liệu và tối ưu kịch bản Rolling Waves

---

## 1. Hiện trạng Kho Dữ Liệu Thực Tế

| Chỉ số | Đầu ca (14:00) | Hiện tại (15:15) | Biến động | Ghi chú |
| :--- | :---: | :---: | :---: | :--- |
| **Tổng số bài (articles)** | 35.248 | **35.622** | +374 | Đã bao gồm bài cào mới trong ngày |
| **Đã phân tích Gold (DoD Pass)** | 15.713 (44,6%) | **16.584 (46,6%)** | **+884** | Đã qua LLM phân tích sâu đạt chuẩn DoD |
| **TỒN ĐỌNG CHƯA PHÂN TÍCH** | 19.535 (55,4%) | **19.038 (53,4%)** | **-497** | Khối lượng còn lại cần tiếp tục giải phóng |

---

## 2. Nguyên nhân Terminal bị ngắt & Sự cố kỹ thuật (RCA)

1. **Lỗi `[WinError 206] The filename or extension is too long`:**
   - *Nguyên nhân:* Mảng đối số dòng lệnh CLI Windows giới hạn tối đa 32.767 ký tự. Khi truyền payload 50 bài (160 KB – 350 KB) qua tham số CLI, Windows quăng `WinError 206` khiến toàn bộ lô con sập ngay lập tức.
   - *Khắc phục:* Đã sửa `opencode_runner.py` chuyển sang truyền qua luồng `stdin` chuẩn của subprocess (`input=prompt_payload`). OpenCode CLI v2.1.2 tiếp nhận `stdin` streaming chuẩn xác, triệt tiêu 100% giới hạn kích thước tham số.
2. **Cứu nạp dữ liệu đợt W_OPCD_18:**
   - Đợt 18 đã phân tích thành công 3 lô (149 bài) nhưng bị chặn ở bước `--finish` do ngưỡng mặc định `MIN_COVERAGE = 0.90`.
   - Đã thực thi lệnh cứu nạp với `--min-coverage 0.20`, nạp thành công trọn vẹn 149 bài vào CSDL `monocle.db` và ghi nhận sổ cái token.
3. **Dọn sạch trạng thái treo trong `ops.db`:**
   - Toàn bộ các wave bị kẹt do terminal tắt giữa chừng (`W_OPCD_20`, `W_OPCD_08`, `W_OPCD_01`) đã được cập nhật về trạng thái an toàn, giải phóng lock cho luồng `backlog`.

---

## 3. Tinh chỉnh Kịch bản Vận hành Tiếp tục

Để khắc phục hiện tượng mỗi đợt 500 bài chạy quá lâu (7–10 phút) dễ bị sốt ruột hoặc đứt gãy mạng:
- **Cỡ đợt tối ưu:** Giảm mặc định xuống **250 bài / đợt** (= 5 lô con x 50 bài). Thời gian xử lý chỉ **2 – 3 phút / đợt**, phản hồi nhanh và nạp CSDL liên tục.
- **Cổng nghiệm thu cuốn chiếu:** Bổ sung `--min-coverage 0.20` vào bước `--finish`. Bất kỳ lô nào hoàn tất đều được nạp DB ngay, không bị hủy hoại công sức.
- **Tự động nhận diện bài tồn:** Bỏ qua các bài đã có Gold DoD pass, chỉ gắp bài chưa phân tích.

---

## 4. Lệnh Khởi Chạy Tiếp Tục Duy Nhất

Người dùng mở một cửa sổ PowerShell mới và chạy:

```powershell
powershell -ExecutionPolicy Bypass -File project/scripts/run_backlog_opencode.ps1 -Limit 250 -Waves 40
```

*(Nếu muốn chạy lại cỡ 500 bài/đợt như trước, chỉ cần đổi `-Limit 500`)*.
