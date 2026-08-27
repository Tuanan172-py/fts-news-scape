# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-08-27
- **Current story:** US-018: Flat Dual Root User Subscriptions & ISO Daily Output Redesign
- **Status:** **implemented & verified** (249/249 pytest passed, live migration completed)
- **Blocker:** none
- **Accomplished:**
  - Tái cấu trúc thư mục `users/` thành mô hình Flat Dual Root: `users/subscriptions/` và `users/output/`.
  - Hỗ trợ parser CSV đa năng (cột ngang nhóm thực thể & cột dọc), tự động bỏ qua template `_*`, tách alert `_unknown/`.
  - Xuất deliverable hàng ngày phẳng `users/output/{username}/{YYYY-MM-DD}.csv` và master audit `_master/{YYYY-MM-DD}.csv`.
  - Dọn dẹp 100% các thư mục legacy cũ (`users/input/`, `users/template/`, subfolder ngày con).
  - Toàn bộ 249 unit & integration tests PASS 100%.
- **Files changed this session:** `src/users/compile.py`, `src/export/user_output.py`, `scripts/make_user_template.py`, `scripts/compile_users.py`, `tests/*`, `.gitignore`, `walkthrough.md`.

