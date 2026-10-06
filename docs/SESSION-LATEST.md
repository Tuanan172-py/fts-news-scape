# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

> **Session US-039 2026-10-06 (high-risk, ADR-0021 accepted by operator Q1-Q4), branch `feature/us039-knowledge-framework`, worktree `C:/src/news-scape-us039`:**
> - Knowledge contract: `docs/knowledge/{README.md,schema.yaml}`, `scripts/knowledge.py`, `harness_cli.py doc new|lint|index|sync`, lint in pre-commit (installed, guarded) and `audit`. English templates for 8 types.
> - ADR-0001 to ADR-0019 normalized to English with commit evidence; ADR-0015 recorded as rejected. 20 Claude memories are now `docs/knowledge/facts/FACT-*`. `AGENTS.md` in English; `CLAUDE.md`, `GEMINI.md` redirect.
> - Next: G4 stories/proposals, G2 rules, G5 plans + per-lane handoff, G6 drift; ADR-0020 after US-038 merges; reduce Claude `MEMORY.md` to a pointer only after this branch merges.

> **Phiên ops 2026-10-06 (tiny/normal, trên `feature/article-lane-remove-gates`, chưa commit):**
> - Sửa khởi động lại daemon thoát oan (mã 3): `acquire_single_instance` chờ ân hạn `daemon.lock_grace_seconds` 45 s; test `tests/test_ops_restart_lock.py`; kiểm thật bằng `schtasks /End` + `/Run`.
> - Radar không còn đẩy `recapture` cho dòng `raw_missing` mồ côi (bài không còn trong kho); 1.241 dòng cũ đã được phiên khác xử lý, còn 2 dead-letter thật.
> - OPEN-ITEMS: CON-1 mục 1 đóng (không dùng DSH; runner là agy + opencode Muse Spark 1.3), mục 2 bộ vàng PENDING; OPS-1 cập nhật Telegram và L1.
> - Test toàn bộ: 841 đạt, 6 đỏ ngoài phạm vi (`test_inherit` 1, `test_periodic_reports` 4, `test_doc_lint` do ADR 0020 thiếu mục). **Cần cherry-pick 4 tệp sang `dev/us038`.**

> **Phiên OpenCode 2026-10-05 (Tier 2+3, DONE): đợt W10051122 HOÀN TẤT 500/500.**
> - 5 vòng vá OpenRouter free $0 (256→36→30→11→0) rồi phát hiện packet cũ: đóng lúc Silver chưa có, trích RSS ngắn.
> - Sửa lane đọc Silver trước (pack/runner/wp v1.1), `--repair` làm mới, expand dồn hàng cũ, ingest bỏ tệp rỗng. Finish 15:30: L1 100%, nội dung 100%.
> - ADR 0018 accepted (Human duyệt hướng a). Test 146 passed. 5 test khác rớt do phiên US-036, không thuộc phạm vi này.

> **Phiên ổn định pipeline 2026-10-05 (US-037, một phần):** audit điều phối `docs/proposals/20261005-audit-dieu-phoi-agent.md`, kế hoạch `~/.claude/plans/lovely-herding-moler.md`.
> - Xong (R-01 đến R-05): phản hồi thô của agy lưu khi lô rỗng (`ops_logs/waves/<đợt>/raw/`); `/retry` bị chặn sau 2 lần `max_repair_rounds` vòng vá; mỗi vòng vá tính lần thử cho từng bài; nghỉ 30 phút sau đợt hỏng (`wave.cooldown_minutes`); lệnh dạng đường dẫn Git Bash được khôi phục hoặc bị từ chối; chạy tay có ba chế độ `--mode backlog|bench|adhoc` tự đăng ký `ops_waves`, vết, giữ chỗ, khoá provider, kiểm va chạm (`src/ops/manual.py`); span cho OpenRouter; probe độ phủ thu thập. Daemon đã khởi động lại bằng mã mới.
> - Đã nhả W10021650, W10051042, W10051050 (`/cancel`). Phân luồng (`src/ops/lanes.py`): auto, backlog, bench; mỗi luồng tối đa một đợt, đợt tay không còn chặn sensor; `/stop` huỷ mọi luồng. Mô tả ở `ops-daemon-reference.md` mục 8.
> - Chưa làm: R-06, R-07 (cào bù và `raw_html`) vì trùng phạm vi phiên US-036 đang chạy; R-08 phần nhả đợt hỏng.
> - Test: bộ ops và `test_ops_manual.py` xanh. 5 test ngoài phạm vi đang đỏ do phiên khác: `test_inherit` (1), `test_periodic_reports` (4).

- **Updated:** 2026-10-05 (Data plane decoupled; clean commit 737d8ce; ready for Research-FPA/news-scraper)
- **Điểm vào vận hành:** `pipeline_radar.py status` · `ops_daemon.py status` · `scripts/harness_cli.py git status`
- **Tài liệu:** ADR 0018, ADR 0019 (`0019-loai-bai-mong-khoi-packet-article-lane.md`) · `project/docs/operations/ops-daemon.md`

## Next Steps

> **Phiên US-038 2026-10-05 (high-risk, blocked chờ người):** đưa mã lên `Research-FPA/news-scraper`, đề xuất ADR 0020.
> - Nhánh cục bộ `import/clean-20261005` (df021e6): snapshot lịch sử mới của 986a7c6, 888 tệp, 8,2 MB, không dữ liệu, không bí mật thật. Kho tổ chức đang rỗng và private.
> - Push bị chặn quyền trong phiên agent. Người vận hành chạy: `git push fpa import/clean-20261005:refs/heads/main`.
> - Dữ liệu cũ đã chuyển (không xoá) vào `C:/data/news-scape/archive/20261005-cleanup/` kèm `MANIFEST.txt`. `C:/data/news-scape/raw_html` (legacy 08/09) chưa chuyển do bị chặn quyền; dòng manifest của nó ghi nhầm là đã chuyển. `project/src/data` nằm trong archive và chứa Bronze duy nhất, không xoá.
> - `FRA - Data` = teamsite `sites/FRA/Data` qua shortcut OneDrive, Files On-Demand chỉ-trên-mây. ADR 0020 (proposed): xuất bản một chiều, chỉ thêm, manifest SHA256, thang L0/L1/L2.

1. Người vận hành push snapshot lên `fpa` (lệnh trên). Sau đó phát triển trên nhánh tách từ `fpa/main`.
2. Duyệt ADR 0020 và trả lời ba câu hỏi mở ở §6 của ADR 0020 (quyền ghi `sites/FRA/Data`, tài khoản dịch vụ, hạn mức).
3. PR kế tiếp trên kho tổ chức: cách ly test (`conftest.py`), rồi `core/paths.py` làm nguồn đường dẫn duy nhất, rồi chuyển dữ liệu nóng khỏi OneDrive trong khung dừng daemon.
