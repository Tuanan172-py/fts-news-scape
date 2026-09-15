# SESSION-LATEST — where am I, what next

<!-- Step 9 handoff. OVERWRITE this (never append) at the end of every session. Keep to one screen. -->

- **Updated:** 2026-09-15
- **Current story:** US-010 (Agent Network Registry, Pipeline DAG & KPI Ledger) — `implemented` (7/7 harness tests passed)
- **Status:** 0 story `in_progress`. Live matrix: 7 implemented, 1 blocked (US-001), 0 in-progress. `harness.db` nâng schema v1→v2.
- **Blocker:** Không còn blocker cho US-010. US-001 vẫn `blocked` (nền cũ, không đụng phiên này).

## Việc đã làm phiên này (15/09/2026) — Xây dựng Mạng lưới Agent Đặc nhiệm (ADR 0006)

### 1. Ba xương sống khai báo (3 Spines)
- **Spine 1 — Registry**: `.agents/registry.yaml` — nguồn chân lý khai báo toàn bộ tác nhân theo taxonomy 3 lớp (operator / cognitive / conductor), kèm io_boundary, tools_allowed, dod_contract, cost_budget, kpis.
- **Spine 2 — Pipeline DAG**: `.agents/pipeline.yaml` — DAG điều phối end-to-end (stages + needs + gate + wave + invariants), thay mô tả 5-phase văn xuôi.
- **Spine 3 — KPI Ledger**: `harness.db` schema v2 (`002-agent-metrics.sql` + bảng `agent_metrics`); `harness_cli.py` thêm lệnh `metric` (ghi) + `query agent-metrics` (rollup); `propose` đọc trend per-agent, tự gắn cờ agent `dod_pass_rate<95%` / `fp_flags>0`, nâng lane high-risk.

### 2. Sáu cognitive agent đặc nhiệm (status: draft — roadmap §4)
`story-dedup-clusterer`, `materiality-triage`, `entity-curator` (tier high-risk, cần ADR khi kích hoạt), `adversarial-dod-verifier`, `daily-brief-synthesizer`, `harness-auditor`. Mỗi agent: 1 SKILL.md + 1 entry registry + 1 stage pipeline.

### 3. Governance & Hạ tầng
- Rule mới `.agents/rules/07-agent-registry-governance.md` (taxonomy + checklist 5 bước thêm agent an toàn).
- `.agents/AGENT_NETWORK_DESIGN.md` (thiết kế tổng thể đã duyệt). ADR `0006`. AGENTS.md §2 trỏ registry/pipeline là nguồn chân lý.
- `init_db` nâng cấp áp dụng tuần tự mọi migration `NNN-*.sql` (idempotent). Thêm `_force_utf8_stdio()` cho harness_cli (chống charmap Windows).
- Test: `tests/test_harness_cli.py` mở rộng lên 7 test (thêm ledger + propose), 100% pass.

## Next Steps
1. Kích hoạt agent đặc nhiệm #1 `story-dedup-clusterer` hoặc #2 `materiality-triage` (Tier 2, đòn bẩy token cao): dựng operator tiền lọc (SimHash pre-group / triage packet) + wiring metric hook vào ingest.
2. `entity-curator` cần ADR riêng trước khi chuyển `active` (chạm Data Contract catalog).
3. Wiring `pipeline_radar` đọc `pipeline.yaml` để gợi ý stage kế tiếp từ DAG (P2 code, cần proof test).
