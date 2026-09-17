# Phase 04 — Lỗi chức năng, vệ sinh, hiệu năng

- Parent: [plan.md](plan.md) · Ưu tiên: P2-P3 · **Q3, Q5, Q8 đã chốt** — không còn chặn
- Q3 **(b)**: giữ `news_cron` làm lưới an toàn, sửa `--once` chiếm lock
- Q5 **(c) + kéo theo nhu cầu**: producer chỉ sản xuất khi consumer chạy — xem `plan.md` §Diễn giải Q5
- Q8: retention 90/30 ngày, **kèm khảo sát phương án nén/gom DB** — xem `plan.md` §Diễn giải Q8
- Bằng chứng: `docs/OPEN-ITEMS.md` §A0-5, §A0-6

## 4a. Lỗi chức năng (P2)

| Lỗi | Sửa | Ghi chú |
|---|---|---|
| `l1_ingest.py:83` dùng `json.loads` nhưng module **không `import json`** → `NameError` bị nuốt bởi `except Exception: pass` (dòng 88-89) ⇒ khối dọn `l1_batch_*.task.json` **chưa từng chạy** | Thêm `import json`; **bỏ `except` trần** để lỗi tương tự không im lặng nữa | Đã tôi kiểm chứng |
| `news_cron` cào song song morninger — nhánh `--once` của `orchestrator.main` (dòng 253-262) không chiếm lock | Theo **Q3** | Đã tôi kiểm chứng |
| DoD L1 hai luồng khác nhau: code-first truyền registry (`l1_runner.py:124`), luồng subagent **không** (dòng 214) ⇒ `entity_id` lạ lọt qua ở luồng agent | Truyền registry cho cả hai | Agent báo cáo |
| Job `l1_route` sinh packet không ai tiêu thụ (153 → 163 file trong một buổi) | **Đảo sang mô hình kéo theo nhu cầu (Q5)**: job tự động chỉ chạy nhánh `resolved` (0 token); packet `needs_agent` **chỉ sinh khi consumer sắp chạy**, đúng số lượng sắp tiêu thụ. Dọn 163 file tồn khi triển khai | Do thay đổi của tôi hôm nay |

> Bài học chung của mục này: **`except Exception: pass` là nơi lỗi đi để chết**. Rà soát các
> `except` trần khác trên đường automation trong lúc sửa.

## 4b. Vệ sinh & hiệu năng (P3)

| Vấn đề | Sửa |
|---|---|
| `rederive_incremental` đọc/parse **mỗi `.meta.json` 3 lần** mỗi chu kỳ (`derive.py:95, 131, 132`) ≈ 22k lượt đọc/30 phút trên OneDrive | Đọc một lần, cache `fetch_ts` trong bộ nhớ cho cả ba mục đích |
| `checkpoint_reached` chỉ đạt khi `backlog == 0`; một file mới nhất luôn lỗi ⇒ `export_silver_manifest` **không bao giờ tự chạy** | Tự khỏi sau phase-01 (dead-letter không còn tính vào backlog). Cần test khẳng định |
| `article_versions` thêm một hàng mỗi lần re-derive cùng bài khi meta thiếu `fetch_ts` (`derive.py:55-56` luôn process, `store.py:383` INSERT thuần) | UPSERT theo `(url_title_hash, content_sha256)`, hoặc bỏ qua khi nội dung không đổi |
| Không có retention: `work_packages` 7.289 · `silver` 7.289 · `agent_tasks/l1/archive` 2.461 | **Đo trước, chọn sau** (Q8): so 3 phương án — xoá theo hạn 90/30 ngày · nén theo tháng giữ khả năng bung tra cứu · gom vào SQLite. Chọn theo số đo thật. Nếu chọn gom DB thì **lại là đổi schema ⇒ ADR riêng**. Mặc định an toàn nếu không kết luận được: xoá theo hạn 90/30. **Bronze `raw_html` tuyệt đối không dọn** — tạo tác WORM |
| `user_output.gated_rows` nạp toàn bộ bảng vào RAM rồi lọc ngày bằng Python (dòng 166-177) | Đẩy bộ lọc ngày xuống SQL |
| Cycle capture 335s → 360s, biên dự phòng mỏng dần | Theo dõi; nếu vượt 480s thì kích hoạt C6 (tối ưu phân trang) trong `OPEN-ITEMS.md` |

## 4c. Harness backlog đang mở

| # | Vấn đề |
|---|---|
| 7 | `project/.venv` hỏng (trỏ Python 3.14 của hồ sơ Windows cũ), trái AGENTS.md §3 — **xoá cần anh xác nhận** |
| 8 | `harness_cli intake` argparse cho 9 `--type` nhưng DB CHECK chỉ nhận 6 ⇒ `qa_inquiry`/`diagnostic`/`exploration` luôn lỗi |
| 9 | Audit Rule 06 Blacklist grep toàn văn nên bắt nhầm văn bản sản phẩm (đã làm vỡ `test_daily_reporter_metrics` khi sửa mù) |

## Nghiệm thu

| Tier | Cách chứng minh |
|---|---|
| Unit | `l1_ingest` dọn đúng batch đã hoàn tất (test này fail trên code hiện tại vì `NameError`) |
| Unit | DoD luồng subagent chặn `entity_id` không có trong registry |
| Unit | Retention job giữ file trong hạn, xoá file quá hạn, **không đụng `raw_html`** |
| Integration | derive chạy 2 chu kỳ: số lượt đọc file giảm rõ rệt so với trước |
| **Platform** | morninger thật: `news_cron` không còn chồng lấn (theo Q3), log xác nhận |

## Rủi ro

Retention job là thao tác **xoá dữ liệu** — phải chạy `--dry-run` và cho anh duyệt danh sách trước
lần chạy thật đầu tiên. Đặt nhầm đường dẫn có thể xoá `raw_html`, là mất vĩnh viễn tạo tác kiểm toán.
