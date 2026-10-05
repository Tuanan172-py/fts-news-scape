# CHECKPOINT — Đợt W1001OPC01: 500 bài tồn đọng pre-01/10 trên OpenCode native

- **Wave:** W1001OPC01 (500 bài, 5 lô x100) · **Kết quả: ✅ HOÀN TẤT, nạp 500 failed 0, phủ 100% nhận diện + 100% nội dung**
- **Model phiên:** Muse Spark 1.3 (`muse-spark-1.3-contributor-free`) trên terminal OpenCode (Orca ADE)
- **Ngữ cảnh tiêu thụ:** ~917,6k tokens / ~88% window (1.048.576) — phiên sau bắt buộc mở mới theo khuyến nghị handoff
- **Thời gian:** pack 15:02:52 → finish 15:50:58, tổng **~48 phút** (01/10/2026)
- **Harness:** intake 30 / story US-OPC01 (`implemented`) / trace 97 (`completed`, 1.0/1.0)

## 1. Timeline đo thật (mtime trên đĩa)

| Mốc | Giờ | Ghi chú |
|---|---|---|
| Pack wave (500 bài, 269 tầng ưu tiên) | 15:02:52 | `article_run.py --wave W1001OPC01 --limit 500 --batch 100 --exclude-file ids-20261001.txt` |
| Lô 01 xong 100/100 | 15:19:58 | 118 KB, gồm viết adapter + 10 bài đầu |
| Lô 02 xong 100/100 | 15:27:30 | 104 KB (~8 phút) |
| Lô 03 xong 100/100 | 15:36:46 | 93 KB (~9 phút) |
| Lô 04 xong 100/100 | 15:44:00 | 89 KB (~7 phút) |
| Lô 05 xong 100/100 | 15:50:07 | 87 KB (~6 phút) |
| `--finish` + HANDOFF | 15:50:58 | exit 0, `ingested: done=500 failed=0` |

Tốc độ phân tích ổn định: **~10,6 bài/phút**, tổng output ~480 KB cho 500 bản ghi v2-lean.

## 2. Cách chia batch (thực tế đã chạy)

- **Lô wave (`--batch 100`, 5 lô):** giữ nguyên bất biến Article Lane — `--batch` là cách chia lô duy nhất.
- **Micro-chunk phân tích (10–20 bài/lượt, ~25 lượt `append_records`):** mỗi lượt đọc 1 file dump text → phân tích → nối vào `.output.json` qua `scripts/opencode_native_run.py` (validate DoD + ghi meta + `ops_events`). Checkpoint sau mỗi lượt; chạy lại chỉ skip phần đã có (resume miễn phí).
- Vì sao không 100 bài/lượt: trần output mô hình (~131k tokens) và độ chính xác trích dẫn — chunk nhỏ giữ `parse_fail_rate = 0`.

## 3. Log quá trình (vết đã ghi, không kể lại bằng lời)

| Kênh | Vị trí | Nội dung |
|---|---|---|
| Output + meta từng lô | `project/data/agent_outputs_article/article_W1001OPC01_*.output.json` / `.meta.json` | 5 output (84–118 KB) + 5 meta (`status: OK`, `domain_errors: []`) |
| Sự kiện vận hành | `C:\data\news-scape\ops.db :: ops_events` | 31 dòng wave này: 26 `runner.partial` + 5 `runner.ok`, **0 `runner.batch_error`** |
| Bàn giao đợt | `project/data/state/HANDOFF-20261001T155058.md` (+ `HANDOFF-latest.md`) | 5 packet, chưa chạy 0 |
| Harness trace | `harness.db` intake 30 / story US-OPC01 / trace 97 | Standard, `completed`, 1.0/1.0 |
| Lỗi free-tier | (không có) | 0 timeout, 0 not-connect, 0 rate-limit, 0 schema_fail |

## 4. Brainstorm — bố trí thư mục agent / archived

**Hiện trạng đo được:**

- `project/data/agent_tasks/article/` tồn **148 packet** `.task.json` nhiều wave cũ — không bao giờ vơi.
- `project/data/agent_tasks/archive/<YYYYMMDD>/` tồn tại theo ngày, nhưng `20261001/` **rỗng**.
- Nguyên nhân gốc (`project/src/agent/archive.py:50-92`): `archive_completed_tasks` chỉ nhận 2 format lane cũ (`<aid>.task.json`, `batch_*.task.json`). Packet Article Lane (`article_<wave>_NN.task.json`) **không khớp mẫu nào** → finish in `archived: 0/500` mà exit vẫn 0.

**Đề xuất (story riêng, Cấp 2 — không đụng Data Contract):**

1. Dạy `archive_completed_tasks` nhận thêm họ `article_*`: khi wave DONE (`--finish` exit 0), dời trọn bộ `article_<wave>_*.task.json` + `.map.json` + `wave_<wave>.json` + `wave_<wave>.conductor.ts` vào `archive/<YYYYMMDD>/W<wave>/` (gom theo wave, không rải lẻ theo ngày file).
2. Phân tầng lưu trữ: output (`agent_outputs_article/`, nhẹ, ~100 KB/lô) **giữ tại chỗ** làm bằng chứng kiểm toán; packet (nặng, ~500 KB/lô) archive sau DONE; `archive/` áp retention (ví dụ giữ 30 ngày rồi nén).
3. Radar hiển thị thêm "packet tồn chưa archive" để vệ sinh định kỳ có số đo thay vì cảm tính.

## 5. Vấn đề vận hành lộ ra trong đợt (trung thực, kể cả cái chưa sửa)

1. **`wave.conductor.ts` chỉ chạy trên DSH** (`tools.agent_article/read/write` không tồn tại trên OpenCode) — đã vượt bằng adapter native `opencode_native_run.py`. Đề xuất nâng thành `--runner opencode` chính thức.
2. **Pack thiếu `--before`** (`article_pack.py` chỉ `--date` 1 ngày) — đã vượt bằng `--exclude-file` 352 IDs 01/10. Lỗ hổng còn nguyên cho đợt sau.
3. **`token_ledger` không ghi dòng mới** ("Không có phiên DSH nào worker tạo sau mốc") — warning, không chặn đợt. Hệ quả: chi phí token free-tier **vô hình**; chỉ còn độ đo gián tiếp là 88% context.
4. **Radar trỏ nhầm đợt mới nhất:** giữa đợt xuất hiện W10011541 (15:41, 100 bài, đã xong, không phải của phiên này). `--finish` verify theo **tập bài của đợt** nên không sai, nhưng người đọc radar dễ tưởng đợt mình chưa xong. Cần quy ước: radar neo theo wave đang cầm (`--wave`), không neo theo `created_epoch` max khi có nhiều nguồn mở đợt.
5. **Nguồn mở W10011541 chưa rõ** (daemon L0 không tự mở; khả năng phiên khác) — cần đối chiếu `ops_waves` trước khi mở wave tay tiếp theo để tránh race packet.
6. **Trùng lặp nội dung trong backlog** (Starship i27/i28, NVL, PNJ, vàng lặp nhiều bản tin) — giữ nguyên theo ADR 0013 (tần suất là tín hiệu), chờ duyệt dedup P0 mới được miễn LLM.
7. **Ngữ cảnh 88%** — mọi wave 500 bài native đều chạm trần phiên; công thức đúng là 1 wave/phiên mới + handoff, không cố nhồi 2 wave/phiên.

## 6. Harness Closure

| File / Component | Updated? | Reason & Evidence |
|---|---|---|
| `docs/stories/US-OPC01-wave-W1001OPC01-checkpoint.md` (file này) | Yes | Checkpoint theo yêu cầu, số đo từ mtime + DB thật |
| `harness.db` | No | Đã ghi ở phiên thực thi (intake 30 / US-OPC01 / trace 97); phiên này chỉ đọc |
| `C:\data\news-scape\monocle.db`, `ops.db` | No | Chỉ truy vấn readonly kiểm chứng |
| `docs/SESSION-LATEST.md` | No | Giữ handoff phiên thực thi; checkpoint này là tài liệu bổ sung |
| `docs/OPEN-ITEMS.md`, ADR | No | Các mục §4–§5 là đề xuất story mới, chưa phải quyết định |
