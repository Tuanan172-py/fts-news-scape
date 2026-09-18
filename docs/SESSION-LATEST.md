# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-17 (DSH Conductor vận hành trọn ngày: L1 wave + Gold 50 bài + deliver)
- **Current story:** US-020 `in_progress` (H1/H2 DSH conductor); US-021..023 `planned`. US-016..019 `implemented`.
- **Test:** **435 passed**.
- **Pipeline:** ✅ background morninger chạy ổn định (capture/10min, derive/30min, l1_route/15min, reclaim/30min, drift/6:0).

## Kết quả vận hành 2026-09-17 (DSH Conductor)
- **L1:** route 75 tin → 44 code-first (0 token) + 31 needs-agent; 2 subagent; `dod#l1` 31/31 pass; drain code-first +136 → L1 hôm nay **429**.
- **Gold:** export 50 bài (10 mini-batch); 5 wave × 10 bài; `dod#gold` **50/50 pass**; Gold hôm nay **60**.
- **Deliver:** 5 user xlsx (AnPT, PhoHG, ThanhTD, UyenNNT, VyPTT) · **10.207 dòng final**.
- **Metric:** l1-entity-matcher items 31 (metric_id 3); gold-financial-analyst metric_id 5..9 (50 pass).
- **Deviation (đã chấp nhận):** chạy bằng `subagent` generic thay `agent_l1`/`agent_gold` vì phiên chưa ở preset Conductor; token là **ước lượng định mức**, không có telemetry.

## Friction / bài học (đã ghi backlog)
- #10 L1 ghi `unlisted_candidates` sai kiểu (object thay vì string) → 3 bài fail rồi chuẩn hoá.
- #11 Radar báo "Gold eligible = 0" nhưng `agent_export` xuất 50.
- #12 `agent_export` không giới hạn theo wave (vi phạm demand-driven Q5).
- #13 L1 sinh entity GICS giả `IND_GICS2:QUY` / `IND_GICS3:QUY`.
- #14 **CWD:** mọi lệnh pipeline phải chạy `Cwd=project`; chạy từ repo root làm `agent_ingest` fail `precondition raw missing data/raw_html`.
- Metric gold có 1 dòng `dod_pass_rate=0.0` (metric_id 4) từ lần chạy sai CWD — cần dọn khi có công cụ.

## Next Steps
1. Mở phiên preset **news-scape-conductor** (H2) — hiện Conductor vẫn chạy preset generic.
2. Requeue hàng kẹt: `work_items failed=189`, `l1_tasks failed=85`.
3. Dọn metric sai `id=4`; archive output Gold cũ ngày 14/09.
4. **Git commit** khối công việc đã hoàn tất.
