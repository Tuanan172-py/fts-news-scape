# Audit điều phối: các tác nhân có ngoài workflow hoặc trái chỉ dẫn không

- **Loại tài liệu:** báo cáo audit (chỉ đọc).
- **Ngày:** 2026-10-05
- **Phạm vi:** `ops.db` (đợt, sự kiện, vết) từ 02/10, tệp packet và đầu ra của W10051042, W10051050, W10051122, radar, harness audit.
- **Phương pháp:** truy vấn chỉ đọc; không sửa dữ liệu.

## 1. Kết luận

Daemon và `article-processor` tuân thủ hợp đồng ở chỗ kiểm được: 0 lần gọi công cụ trái Zero-Tool trong mọi vết, mọi đợt do daemon mở đều đủ vết và đủ giữ chỗ bài. Vi phạm nằm ở chỗ **người và phiên ngoài daemon can thiệp vào đợt**, và ở ba lỗ hổng cơ chế.

## 2. Phát hiện

| # | Mức | Phát hiện | Bằng chứng | Việc cần làm |
|---|---|---|---|---|
| F1 | Cao | W10051122 chạy ngoài daemon: 500 bài, 27 lô cộng vá, không có dòng `ops_waves`, 0 span, 0 bài giữ chỗ | `ops_spans`, `ops_wave_articles` đều 0 cho đợt này | Bắt buộc mọi runner ghi `ops_waves` và vết (S-18); khoá đợt tay khi daemon sống (ADR 0012) |
| F2 | Cao | Đợt W10051042 do daemon mở với provider `agy`, nhưng 5 lô được chạy bằng `openrouter` (`stealth/space-bunny-alpha`) sau `/retry` | Meta đầu ra: agy 3 lô, openrouter 5 lô; mandate ghi `failover never` | Chặn đổi provider giữa đợt: `retry_wave` phải giữ provider của đợt, hoặc ghi sự kiện `provider.override` |
| F3 | Cao | Giới hạn vá bị vượt. Cấu hình `max_repair_rounds: 2`, `max_attempts_per_article: 2`; thực tế 47 bài đóng gói 4 lần và 3 bài 8 lần ở W10051042; W10051122 có bài 9 lần | Đếm trong các `*.map.json` | `retry` và vá tay phải tính vào số lần của bài, không đặt lại bộ đếm |
| F4 | Trung bình | Không có thời gian nghỉ sau đợt hỏng: W10051050 mở 8 phút sau W10051042 hỏng cùng nguyên nhân, tiêu thêm token rồi hỏng tiếp; chỉ sau lần hai mới hạ L1 xuống L0 | Sự kiện 10:48 đến 10:55 | Đợt hỏng thứ nhất đặt thời gian nghỉ (đề xuất 30 phút) trước khi sensor mở đợt mới |
| F5 | Trung bình | Lỗi hệ thống của runner, không phải của mô hình: lô 50 bài trả về 0 bài (`Bóc tách JSON thất bại`) ở 105 đến 126 giây, lặp lại ở mọi vòng vá; độ phủ nội dung 58% so với nhận diện 100% | Span agent `fail`, `verify_wave` | Chẩn đoán phản hồi rỗng của agy ở lô 50 bài; thử lô 25 trong lúc chờ ADR 0017 (D6/D7) |
| F6 | Trung bình | Lệnh `/retry` qua Git Bash bị đổi thành `C:/Program Files/Git/retry`, vẫn được ghi là `human.command` | Hai sự kiện 10:53 | Bộ phân tích lệnh từ chối chuỗi không bắt đầu bằng `/` và báo lỗi rõ |
| F7 | Trung bình | Tầng thu thập đỏ theo ADR 0013: baodautu thiếu 66%, cafef 61%, tinnhanhchungkhoan 61%; 976 URL chờ cào bù; 122 Bronze kẹt Silver; 1.241 bài mất Bronze. Daemon không gọi `capture_reconcile.py`; `reconcile()` của daemon chỉ khôi phục workflow | `pipeline_radar.py status`; grep `src/ops` | Nối `capture_reconcile.py run` vào chu kỳ daemon (probe đã có, hành động chưa) |
| F8 | Thấp | Mô hình khác tài liệu: agent chạy `gemini-3.8-flash-low`, AGENTS.md §6C vẫn ghi mọi model là `deepseek-flash`; registry ghi `flash` chung chung | ADR 0017 đã ghi nhận ADR 0009 D6 hết đúng | Cập nhật AGENTS.md §6C và `registry.yaml` sau khi ADR 0017 có hiệu lực |
| F9 | Thấp | Mandate đang L0 sau hạ tự động; `/level L1` lúc 14:02 chưa kèm `confirm`, nên daemon vẫn không tự mở đợt dù bài chờ lâu nhất 291 phút | `human.command` 14:02, radar | Gõ `/level L1 confirm` nếu muốn tiếp tục tự chạy. Nên sửa F2 và F5 trước |
| F10 | Thấp | Ba đợt `FAILED` còn mở từ 02/10 và 05/10 chưa nhả bài | `ops_waves` | `/cancel <đợt>` cho W10021650, W10051042, W10051050 sau khi quyết định giữ hay bỏ |

## 3. Điều đã tuân thủ

- 0 vi phạm Zero-Tool, 0 lượt bị từ chối công cụ trong toàn bộ vết.
- Mọi đợt daemon mở đều qua cổng `--finish`; đợt không đạt cổng bị chặn nạp DB đúng thiết kế.
- Hạ L1 xuống L0 sau hai đợt hỏng chạy đúng và báo mức khẩn.
- Lệnh nâng quyền cần xác nhận hai lần, thực tế hai lần `/level L1` đều qua xác nhận trước khi mở đợt.

## 4. Thứ tự xử lý đề xuất

1. F2 và F3 (chặn đổi provider và vượt vòng vá): sửa `retry_wave` và bộ đếm bài.
2. F4 (thời gian nghỉ) và F5 (lô rỗng).
3. F1 qua S-18, F7 nối `capture_reconcile` vào daemon.
4. F6, F8, F9, F10.
