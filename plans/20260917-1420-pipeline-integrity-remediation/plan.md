# Plan — Khắc phục triệt để tính toàn vẹn tuyến Bronze → giao hàng

## Overview

|              |                                                                                                                                                                                                                                                                                                                                                                 |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ngày        | 2026-09-17                                                                                                                                                                                                                                                                                                                                                      |
| Bối cảnh   | Rà soát end-to-end phát hiện**7.203 bài đã cào nhưng chỉ 424 bài tới tay người dùng**. Khoảng cách lâu nay quy cho quota Gold, nhưng thực tế phần lớn do các cơ chế **làm rơi bài** nằm giữa đường: watermark bỏ qua vĩnh viễn, bốn ngõ cụt trạng thái, và packet bị xoá bởi chính script vận hành |
| Nguồn       | `docs/OPEN-ITEMS.md` §A0 (đầy đủ chứng cứ + số dòng) · story US-011…US-015                                                                                                                                                                                                                                                                         |
| Trạng thái | 🟢 **Đã chốt toàn bộ 8 quyết định (2026-09-17)** — phạm vi **cả 4 phase**. Hai ADR bắt buộc đã lập: [0007](../../docs/decisions/0007-silver-watermark-integrity-va-bang-silver-failures.md) (đổi schema) · [0008](../../docs/decisions/0008-gold-activation-human-in-the-loop-va-tran-token.md) (kiểm soát token Gold) |

## Nguyên tắc xuyên suốt

Phiên 2026-09-17 rút ra ba bài học, áp cho mọi phase dưới đây:

1. **Chạy thật mới là bằng chứng.** 403 test xanh vẫn để lọt 3 lỗi sống trên đường sản xuất. Mọi
   phase phải có tier Platform (chạy trong tiến trình thật), không chỉ Unit/Integration.
2. **Đo trước khi chỉnh tham số thời gian.** Đặt interval 5 phút khi cycle mất 335s là vô nghĩa.
3. **Im lặng là hỏng.** Job không in gì khi rảnh thì không phân biệt được với job đã chết. Mọi
   nhánh thoát sớm phải để lại dấu vết.

## Chỉ số nghiệm thu chung

| Chỉ số                                                    | Hiện tại          | Mục tiêu                                                          |
| ----------------------------------------------------------- | ------------------- | ------------------------------------------------------------------- |
| Bài Bronze rơi khỏi Silver không dấu vết              | không đo được  | **0**, mọi ca rơi đều có dead-letter + hiện trên radar |
| Bài kẹt`held`/`failed`/`claimed` không lối thoát | 4 loại, ~306 hàng | mọi loại có đường requeue có kiểm soát                     |
| Packet bị xoá khi chưa xử lý                           | có thể xảy ra    | **không thể xảy ra về mặt cấu trúc**                   |
| Job báo thành công giả                                  | AutoPilot có       | thất bại phải ồn ào                                            |

## Các phase

| #  | Phase                                                                                             |  Ưu tiên  | Phụ thuộc |
| -- | ------------------------------------------------------------------------------------------------- | :----------: | ----------- |
| 01 | [Watermark Silver — chặn mất bài vĩnh viễn](phase-01-silver-watermark-integrity.md)          | **P0** | không      |
| 02 | [Chặn tự động hoá phá hoại (`run_daily` + AutoPilot)](phase-02-destructive-automation.md) | **P0** | không      |
| 03 | [Đường requeue cho bốn ngõ cụt trạng thái](phase-03-state-requeue-paths.md)                |      P1      | phase-01    |
| 04 | [Lỗi chức năng, vệ sinh, hiệu năng](phase-04-functional-and-hygiene.md)                      |    P2-P3    | không      |

Phase 01 và 02 độc lập nhau, làm song song được. Phase 03 nên chờ 01 vì cùng chạm vòng đời trạng thái.

---

# QUYẾT ĐỊNH ĐÃ CHỐT — 2026-09-17

Toàn bộ 8 quyết định đã được người dùng chốt. Mục này là **nguồn chân lý** cho cả 4 phase;
phase nào lệch khỏi đây là sai.

| # | Quyết định | Ràng buộc kèm theo |
|:--|---|---|
| **Q1** | **Cả 4 phase** | Không cắt phạm vi |
| **Q2** | Ngưỡng **5 lần thử** → dead-letter, **có lưu hồ sơ** · Sổ lỗi là **bảng `silver_failures` riêng** (phương án b) | **Đổi schema ⇒ Hard Gate ⇒ [ADR 0007](../../docs/decisions/0007-silver-watermark-integrity-va-bang-silver-failures.md)**. Người dùng đã duyệt. Bắt buộc sao lưu `monocle.db` trước lần chạy đầu |
| **Q3** | **(b)** Giữ `news_cron` làm lưới an toàn, sửa `--once` để chiếm scheduler lock | Chạy độc lập được khi morninger chết, nhưng không còn cào song song |
| **Q4** | **(c)** Lai — `held` requeue **tự động**, `failed` requeue **theo lệnh** operator | Trần số lần thử là **bắt buộc** cho nhánh tự động |
| **Q5** | **(c)** Chỉ tự động nhánh `resolved` (0 token). Thêm ràng buộc của người dùng: **producer chỉ sản xuất khi consumer chạy** | Đây là mô hình **kéo theo nhu cầu** (demand-driven), mạnh hơn đề xuất ban đầu — xem §Diễn giải Q5 |
| **Q6** | **Bắt buộc có người trong vòng lặp + cấp quyền tường minh** trước khi Gold tiêu thụ token | **[ADR 0008](../../docs/decisions/0008-gold-activation-human-in-the-loop-va-tran-token.md)**. Bỏ `--dangerously-skip-permissions` khỏi đường mặc định |
| **Q7** | **(a)** Bỏ hẳn `-Mode full`. Kèm **(b)**: dựng cơ chế kích hoạt `agy` có bước người dùng chấp thuận để quản mức tiêu thụ token | Gộp vào ADR 0008 |
| **Q8** | Retention **90 ngày** (`work_packages`, `silver`) · **30 ngày** (`archive`). Kèm yêu cầu khảo sát **phương án tốn ít đĩa hơn** (gom vào DB hoặc nén) miễn là **vẫn dễ truy vấn** | **Bronze `raw_html` tuyệt đối không dọn** — tạo tác WORM |

## Diễn giải Q5 — mô hình kéo theo nhu cầu

Người dùng nêu rõ: *"đây sẽ là cơ chế khi nào consumer chạy thì producer mới sản xuất"*. Nghĩa là
không chỉ tắt nhánh `needs_agent` mà đảo hẳn chiều điều khiển:

- Job `l1_route` tự động **chỉ xử lý nhánh `resolved`** (code-first, 0 token) — phần này luôn chạy
  vì không tốn gì.
- Packet `needs_agent` **chỉ được sinh khi có consumer thật sự sắp chạy** — tức do người vận hành
  kích hoạt (theo Q6/ADR 0008), và sinh đúng số lượng consumer sắp tiêu thụ.
- Hệ quả: hàng đợi packet không còn phình vô hạn. Số 163 file hiện tại là hậu quả của mô hình đẩy
  cũ; cần dọn khi triển khai.

## Diễn giải Q8 — khảo sát trước khi chọn cách lưu

Người dùng mở thêm hướng: thay vì chỉ xoá theo hạn, cân nhắc **gom vào DB hoặc nén** để tốn ít đĩa
mà vẫn truy vấn được. Phase-04 phải **đo trước, chọn sau**:

1. Đo dung lượng thật của `work_packages` + `silver` + `archive`, và tần suất thật sự cần đọc lại.
2. So ba phương án: (i) xoá theo hạn 90/30 ngày · (ii) nén theo tháng (`.tar.zst`/`.zip`) giữ nguyên
   khả năng bung ra tra cứu · (iii) gom nội dung vào bảng SQLite.
3. Chốt theo số đo, ghi kết quả vào phase-04. Nếu chọn (iii) thì **lại là đổi schema ⇒ cần ADR riêng**.

Mặc định an toàn nếu khảo sát không kết luận được: dùng (i) đúng hạn 90/30 ngày đã chốt.

## Hai thao tác phá huỷ vẫn cần xác nhận riêng tại thời điểm thực hiện

Chốt phương án không đồng nghĩa chốt thao tác. Trước khi chạy, phải hỏi lại:

1. **Archive `data/agent_outputs/batch_03..11.output.json`** (dữ liệu 14/09 đã ingest) — bắt buộc
   làm trước khi bật lại AutoPilot, nếu không lỗi va chạm vẫn tái diễn dù đã sửa cách đánh số.
2. **Xoá `project/.venv`** hỏng (harness backlog #7).
3. **Lần chạy retention đầu tiên** — phải `--dry-run` và cho người dùng duyệt danh sách trước.

---

---

## Nghiệm thu chung cho cả đợt

```powershell
cd project
& "C:\venvs\news-scape\Scripts\python.exe" -m pytest tests/ -q      # giữ >= 413 passed
& "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
```

Mỗi phase phải trả đủ: Unit + Integration + **Platform** (chạy trong morninger thật, quan sát log),
rồi mới `harness_cli.py story complete`. Không phase nào đạt `implemented` chỉ bằng pytest xanh.
