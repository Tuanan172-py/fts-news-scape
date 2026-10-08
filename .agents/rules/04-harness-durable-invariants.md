# 04 — Harness H2–H5 Durable Layer Invariants & Closure Protocol

Quy tắc vận hành bắt buộc cho mọi Agent khi làm việc trong repo News-Scape trên nền tảng Harness H2–H5:

## 1. Phân định 3 Cấp độ Tầm quan trọng (Per-Prompt 3-Tier Classification)
Tại MỌI prompt (kể cả tra cứu, giải thích, thiết kế hay sửa code), Agent BẮT BUỘC tự động phân loại yêu cầu vào một trong 3 cấp độ:
- **Cấp 1: TINY (Nhẹ / Tra cứu / Khảo sát / Patch 1 dòng):**
  * Không làm gián đoạn WIP chính của Story đang chạy.
  * Tự động ghi nhận `intake` + `trace` (Minimal Trace) vào `harness.db` để lưu giữ trọn vẹn ngữ cảnh lịch sử.
- **Cấp 2: NORMAL (Quan trọng vừa / Tính năng / Refactor / Đánh giá):**
  * Bắt buộc ghi nhận `intake`, tuân thủ `WIP = 1`, lập Story Packet `docs/stories/US-XXX.md`.
  * Bắt buộc có kiểm thử cơ học (Proof) và ghi Standard Trace.
- **Cấp 3: HIGH-RISK (Tối quan trọng / Quyết định Kiến trúc / Schema / Contract):**
  * Chạm Hard Gate: Sửa DB Schema (`monocle.db`), Data Contract (Bronze/Silver/Gold), Secret Token, Harness Core.
  * Bắt buộc dừng tại Hard Gate, lập ADR `docs/decisions/NNNN-*.md`, chờ người duyệt và ghi Detailed Trace.

## 2. Kỷ luật Bắt buộc của Vòng đời Tác vụ (Lifecycle Invariants)
1. **Intake Gate:** Bắt buộc ghi nhận phân loại trước khi thao tác:
   `python scripts/harness_cli.py intake --type <type> --lane <lane> --summary <text>`
2. **Bounded Context:** Tuân thủ ma trận `docs/CONTEXT_RULES.md` và ngân sách token theo lane (Tiny $\le 5$ files, Normal $\le 15$ files, High-risk $\le 30$ files).
3. **WIP = 1 cho mỗi worktree (ADR-0022):** Không bao giờ để 2 Story `in_progress` trên cùng một nhánh. Worktree khác nhau làm song song.
4. **Verification Gate ("No proof = not implemented"):**
   - Chỉ được chuyển Story sang `implemented` khi có lệnh kiểm thử cơ học thực tế đã chạy và có bằng chứng ghi nhận qua:
     `python scripts/harness_cli.py story complete --id <id> --run-verify`
5. **Durable Trace Logging:** Kết thúc mỗi prompt/change loop, bắt buộc ghi trace vào CSDL bền vững:
   `python scripts/harness_cli.py trace --story <id> --summary <text> --outcome <completed|blocked|failed>`
   - Đảm bảo `score_trace` $\ge 0.75$ và `score_context` $\ge 0.8$.
6. **Friction Capture:** Mọi điểm nghẽn hoặc lỗi phát sinh phải được đưa vào backlog:
   `python scripts/harness_cli.py backlog add --title <title> --pain <text> --component <comp>`

## 3. Ràng Buộc Quy Trình Git & Commit Nguyên Tử (Git Lifecycle Invariants)
Nhằm bảo đảm toàn bộ thay đổi đủ quan trọng đều được Git lưu vết và liên kết chặt chẽ với Harness:
1. **High-Risk (Cấp 3):** BẮT BUỘC thực hiện trên nhánh feature độc lập (`feature/...`), lập ADR `docs/decisions/NNNN-*.md`, commit theo chuẩn `docs(adr): NNNN-<title>`, và mở Pull Request (PR) để Human Review trước khi merge vào `main`.
2. **Normal (Cấp 2 - Story):** BẤT BIẾN: **1 Story hoàn tất = Tối thiểu 1 Atomic Commit**.
   - Chỉ commit SAU KHI Proof Tier (Unit/Integ/Platform) pass 100%.
   - Định dạng: `<type>(<scope>): <title> (US-XXX)`.
   - Có thể kích hoạt tự động qua: `python scripts/harness_cli.py story complete --id US-XXX --run-verify --commit`.
   - Mã băm `git_commit` và nhánh `git_branch` bắt buộc được tự động lưu vào bảng `story` và `trace` trong `harness.db`.
3. **Tiny (Cấp 1):** Không commit riêng lẻ nếu chỉ là tra cứu/khảo sát. Nếu có chỉnh sửa code/doc nhỏ: Gom thành Checkpoint Commit cuối phiên qua `python scripts/harness_cli.py git checkpoint --summary "<nội dung>"`.
4. **Vệ sinh tệp (Hygiene Invariant):** TUYỆT ĐỐI KHÔNG commit tệp rác, file chạy thử (`scratch/`, `test_scratch*.py`, `check_key*.py`, `-HOSTNAME`). Chạy `python scripts/harness_cli.py git verify` trước khi kết thúc ca.

## 4. Giao thức Đóng Phiên Bắt buộc (Mandatory Harness Closure Protocol)
Ở cuối **MỖI CÂU TRẢ LỜI / PHIÊN THỰC THI**, Agent BẮT BUỘC phải xuất Bảng Nghiệm thu Đóng phiên (Harness Closure Table) minh bạch định tuyến ghi nhận file/DB và trạng thái Git:

```markdown
### 📋 Harness Closure Protocol

| File / Component | Updated? | Reason & Evidence |
|:---|:---:|:---|
| `harness.db` *(Trace & Intake)* | **Yes** | Trace ID #X (Lane: Tiny/Normal/High-Risk, Score: 1.0) |
| `docs/stories/US-XXX.md` | **Yes / No** | [Lý do: Tạo mới / Cập nhật / Không cần (tác vụ Tiny)] |
| `docs/TEST_MATRIX.md` | **Yes / No** | [Lý do: Chạy X tests passed / Chưa có test mới] |
| `docs/decisions/NNNN-*.md` | **Yes / No** | [Lý do: Lập ADR do đổi kiến trúc / Không chạm Hard Gate] |
| `docs/SESSION-LATEST.md` | **Yes / No** | [Lý do: Cập nhật tiến độ handoff / Không đổi] |
| `docs/HARNESS_BACKLOG.md` | **Yes / No** | [Lý do: Ghi nhận ma sát / Không phát sinh ma sát] |
| `Git Codebase Status` | **Yes / Clean** | Commit `<hash>` trên nhánh `<branch>`, working tree sạch |
```

## 5. Quản trị CSDL Phân lập
- CSDL `harness.db` là CSDL vận hành nội bộ của Harness, phân tách hoàn toàn với CSDL nghiệp vụ `data/monocle.db`.
- Mọi thao tác ghi nhận trạng thái của Agent phải đi qua `scripts/harness_cli.py`.
