# HARNESS_BACKLOG.md — Friction reservoir (news-scape, H1)

The harness grows from friction. When something is hard / repeats / is ambiguous / lacks a rule → add a row here (don't silently change the process). Moves to a DB `backlog` table at H2.

**Risk** = a lane (`tiny` / `normal` / `high-risk`), not `low`.

| # | Title | Discovered while | Current pain | Suggested improvement | Risk | Status |
|---|-------|------------------|--------------|-----------------------|------|--------|
| 1 | Status not queryable across stories | Building TEST_MATRIX by hand | Proof/status live in a hand-edited markdown table + scattered story files; no single query for "what's in_progress / unproven". Stale-prone. | H2: SQLite `story`/`trace` + `harness-cli query matrix`. Primary climb-to-H2 signal. | normal | open |
| 2 | WIP=1 has no enforcement | Writing the WIP=1 rule | Honor-system only; nothing stops two `in_progress` stories or a stray branch. | H2 candidate: git pre-commit hook checking a single `in_progress` marker. | tiny | open |
| 3 | SESSION-LATEST is live-state in markdown | Wiring step-9 handoff | A hand-edited state file drifts if not overwritten every session; accepted small debt at H1. | H2: fold into durable `trace.next_action`; keep the file as a generated view. | tiny | open |
| 6 | Ngân sách context Normal-lane quá chật cho tác vụ audit | Ghi trace US-011 | `score_context` đếm cả tệp do Explore subagent đọc hộ → phạt đúng hành vi ủy thác mà quy tắc khuyến khích. | Làm rõ phạm vi: trần chỉ áp cho tệp vào thẳng context agent điều phối. | normal | **resolved** (US-014) |
| 7 | `project/.venv` nội bộ hỏng | Chạy pytest cho US-011 | Trỏ Python 3.14 của hồ sơ Windows cũ đã đổi tên; trái AGENTS.md §3 (cấm `.venv` nội bộ). | Xoá thư mục — **cần xác nhận vì là thao tác phá huỷ**. | tiny | open |
| 8 | `harness_cli intake`: argparse 9 loại, DB CHECK 6 loại | Ghi intake cho US-015 | `qa_inquiry`/`diagnostic`/`exploration` hợp lệ theo FEATURE_INTAKE.md §1 nhưng luôn bị CHECK constraint từ chối. | Mở rộng CHECK cho đủ 9 loại (khớp tài liệu), hoặc thu hẹp argparse còn 6. | tiny | open |

> **Nguồn chân lý từ H2 trở đi là bảng `backlog` trong `harness.db`** (`harness_cli.py backlog add/close`).
> Bảng markdown này là bản chụp để đọc nhanh; mục #4, #5 nằm trong DB, chưa chép sang đây.

<!-- On close: add "Outcome:" with the actual measured result. -->
