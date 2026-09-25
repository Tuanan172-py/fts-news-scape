# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-23 (US-025, US-026, US-027 — Article Lane là đường duy nhất, ADR 0010)
- **Điểm vào vận hành:** `pipeline_radar.py status` → chạy đúng lệnh HIGH nó in ra. Đường dẫn/quyền ghi: `article_run.py --where`
- **Nguồn quy phạm:** `AGENTS.md` §6 (đã viết lại) · `docs/decisions/0010-…` · `.agents/dsh/RUNBOOK-article-lane.md` · skill `dsh-conductor`

## Đã làm trong phiên này

| Story | Kết quả |
|---|---|
| US-025 | `--finish` hết nuốt lỗi (❌ + exit 1 + lệnh `--only`), hậu kiểm theo tập bài của đợt, `readPacket` đọc object `lines[]` và đọc hết packet trước khi gọi mô hình, `--where`, radar chỉ Article Lane, sổ cái `--workers-only`, `L1Runner` tự ghi `l1_tasks route=article_lane` |
| US-026 | **Token chỉ ghi nhận**: bỏ mọi ngưỡng/cảnh báo token. Gỡ row `agent_l1`/`agent_gold` khỏi preset. Nhiễu: `--finish` chỉ bung/nạp tệp `article_<mã>_*`; bỏ job `l1_route` + `--code-first` khỏi `morninger`; bộ chọn bài không coi bản code-first là đã phân tích; 38 mục tồn chuyển sang `project/data/archive/legacy-lane-20260923/` (có `MANIFEST.json`) |
| US-027 | ADR 0010 accepted; `AGENTS.md` §2/§3/§6/§8, `registry.yaml` (4 agent → `retired`), `pipeline.yaml` v2 (bỏ 6 stage lane cũ) |

**Quyền ghi DB (đính chính):** DSH không có cấu hình mở rộng quyền ghi — `writableRoots()` chỉ gồm workspace root + thư mục tạm. `--finish` và `write_user_output.py` chạy với `danger-full-access`; radar, chuẩn bị đợt, chạy mô hình, `--repair` chạy dưới `workspace-write`. Chốt quyền ghi chỉ nằm ở `--finish` (trước bước nạp); nửa chuẩn bị chỉ in ⓘ.

Số thật: W365 nhận diện **365/365**, nội dung **364/365**; nạp W365 `failed=0` (trước 123). Worker W365 ~2.850 token/bài (chỉ ghi nhận). `pytest tests/` **517 passed**. Trace 74–76.

## Next Steps

1. ~~Khởi động lại `morninger`~~ **Đã xong 2026-09-24 15:35**: một tiến trình duy nhất chạy mã mới (commit `39c9898`), giữ khoá `C:\data\news-scape\capture.lock`, log không còn job `l1_route`, 0 lỗi. `news_cron` đã **Disabled**. morninger chạy trong terminal của người dùng: đóng terminal hoặc khởi động lại máy thì phải bật lại tay (chưa có tác vụ tự khởi động).
2. Chạy đợt hôm nay theo lệnh radar (23/09: 345 bài chờ).
3. **Backlog 2.915 bài 10–17/09** nay đã hiện ở hàng chờ (ví dụ `radar status --date 2026-09-15`: 254 bài). Chạy hay không là quyết định vận hành.

## Việc còn treo

- Chưa commit: toàn bộ thay đổi US-025…027 trên nhánh `feature/article-lane-remove-gates`. `docs/proposals/agy-*` không thuộc phiên này.
- Audit còn 2 mục có từ trước: 2 tệp xung đột OneDrive, cụm cấm ở `src/monitor/daily_reporter.py:389`.
- `leaders.yaml`, amendment ADR 0008 (nay phần trần token đã hết hiệu lực theo ADR 0010).
