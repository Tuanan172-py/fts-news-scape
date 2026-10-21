# Bàn giao Phiên Vận Hành (Session Handoff)

**Thời điểm:** 2026-10-21  
**Nhánh:** dev/us038 | **Nhiệm vụ:** Đóng gói OpencodeRunner v2 & Kế hoạch giải phóng Backlog 19.535 bài (500 bài/wave)

---

## 1. Đã hoàn thành (Code & Thực nghiệm)

| # | Hạng mục | Kết quả kỹ thuật |
|---|---|---|
| 1 | **Nâng cấp OpenCode v2.1.2** | Cài đặt nhị phân chính thức `@opencode/cli-windows-x64@2.1.2` vào `AppData\Local\opencode-cli\opencode.exe` (sao lưu bản cũ `1.18.34.exe.bak`). Xác minh `opencode -v` đạt `v2.1.2`. |
| 2 | **Benchmark 9 Free-Tier Models** | Kiểm thử trực tiếp 9 mô hình: 100% đạt chuẩn `v2-lean` 8 trường. Đứng đầu về chất lượng phân tích: `deepseek-v4.1-flash-free` (hàm ý 254 ký tự). Đứng đầu về tốc độ: `minimax-m3.1-flash-free` (7.18s) và `beam-free` (3.25s). |
| 3 | **Xây dựng OpencodeRunner** | Tạo mới `project/src/agent/opencode_runner.py`: cơ chế gọi headless với stdin pipe `""`, bóc tách NDJSON streaming (`text` và `step_finish`), tích hợp cơ chế tự động thử lại (retry) và xoay vòng failover sang `minimax-m3.1-flash-free` / `mimo-v2.6-flash-free`. |
| 4 | **Tích hợp article_run.py** | Bổ sung `--runner opencode` vào `argparse`, `cmd_analyze`, `cmd_repair` và sổ cái token (`opencode-native`, đơn giá $0). |
| 5 | **Kiểm thử thực tế (End-to-End)** | Chạy thực tế đợt thử nghiệm `W_OPCD_BENCH` (2 bài): 1/1 lô OK, 2 bài trích xuất đạt chuẩn DoD `v2-lean`, 0 domain errors. |
| 6 | **Bộ kiểm thử tự động** | Bổ sung `project/tests/test_opencode_runner.py` (3 test cases: thành công, từ chối lỗi hợp đồng, cache hit) — 100% PASS trong 2.15s. |
| 7 | **Headless Auto-Runner** | Tạo mới `project/scripts/run_backlog_opencode.py` và `.ps1` tự động cuốn chiếu tuần tự các wave 500 bài, có trần ngân sách thời gian, tự ngắt khi hết bài tồn đọng và ghi nhật ký giám sát `C:\data\news-scape\logs\backlog_opencode_status.json`. |

---

## 2. Chiến lược phân bổ Workload (Context 256k & 500 bài / wave)

- **Ngân sách Context (Context Budget):** `deepseek-v4.1-flash-free` có trần 256k tokens.
- **Quy chuẩn chia lô (Batch Partitioning):**
  - **KHÔNG** gửi gộp 500 bài trong 1 prompt (tránh rủi ro tràn 256k và vượt trần max output token gây cụt JSON).
  - **BẮT BUỘC** chia thành **10 lô x 50 bài / lô** (mỗi lô ~15k–25k tokens $\approx 8\%$ context budget).
  - Output mỗi lô ~1.500 tokens (an toàn tuyệt đối, không trượt DoD).
- **Tiến độ dự toán:**
  - 1 wave (500 bài) = 10 lô x ~15s = **~150–200 giây (~3–4 phút/wave)**.
  - 40 waves (19.535 bài tồn đọng) = **~2.5 – 3.5 giờ** chạy tuần tự.

---

## 3. Thư viện lệnh vận hành chuẩn

```powershell
# 1. Đóng gói đợt 500 bài tồn đọng (hệ thống tự chia lô 50 bài/lô)
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BL001 --limit 500 --runner opencode

# 2. Phân tích nhận thức bằng OpenCode Free Tier (DeepSeek Flash Free)
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BL001 --runner opencode --analyze --concurrency 2

# 3. Vá nếu có sót (tự động)
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BL001 --runner opencode --repair --concurrency 2

# 4. Nạp CSDL SQLite monocle.db và sổ cái
& "C:\venvs\news-scape\Scripts\python.exe" project/scripts/article_run.py --wave W_BL001 --finish --force
```

---

## 4. Khuyến nghị điều phối đa phiên (Session & Subagent Guidelines)

1. **Cách ly áp suất ngữ cảnh (Context Pressure):**
   - Không nên chạy cả 40 waves trong cùng một phiên chat tương tác (transcript sẽ phình to).
   - Khuyến nghị: Sử dụng script vòng lặp tự động ngoài tiến trình hoặc chạy qua daemon nền / subagent riêng lẻ.
2. **Kiểm soát Rate Limit:**
   - Đặt thời gian nghỉ `time.sleep(10)` giữa các wave 500 bài để làm mát kết nối mạng và hạn chế chạm trần Free Tier Gateway.
