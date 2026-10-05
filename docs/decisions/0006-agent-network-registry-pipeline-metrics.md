# ADR 0006 — Agent Network: Registry, Pipeline DAG & Per-Agent KPI Ledger

- **Ngày:** 2026-09-15
- **Trạng thái:** **accepted**
- **Lane:** high-risk (chạm Harness Core: schema `harness.db` v1→v2, thêm CLI, sửa init migration)
- **Story:** US-010 · **Tác động:** `scripts/harness_cli.py`, `scripts/schema/002-agent-metrics.sql`, `tests/test_harness_cli.py`, `.agents/registry.yaml`, `.agents/pipeline.yaml`, `.agents/rules/07-agent-registry-governance.md`, `.agents/skills/*` (6 skill mới)

---

## 1. Bối cảnh & Vấn đề

1. **Thuật ngữ "agent" lẫn lộn (G1)**:
   - Sơ đồ "Multi-Agent Swarm" gọi 5 "agent", nhưng kiểm chứng bằng grep cho thấy chỉ 2 tác nhân là subagent LLM thật (`l1-entity-matcher`, `gold-financial-analyst`). Query Radar / Token Auditor / DoD Gatekeeper / Delivery là script tất định 0-token.
   - Hệ quả: không suy luận được nên bổ sung agent LLM thật ở đâu; khó thiết kế tăng trưởng.
2. **Không có nguồn chân lý máy-đọc-được cho tác nhân (G2, G5)**:
   - Ranh giới I/O, model, ngân sách token, hợp đồng DoD của mỗi agent nằm rải rác trong văn xuôi `skills/` và `rules/`. Bất biến payload lặp giữa `rule 05` và `AGENTS.md §6` gây rủi ro drift.
3. **Điều phối ngầm định trong văn xuôi (G3)**:
   - Thứ tự stage, phụ thuộc, cổng DoD, chính sách wave chống 429 nằm trong runbook prose, phụ thuộc trí nhớ người vận hành, không kiểm toán được.
4. **Vòng tự cải tiến thiếu dữ liệu per-agent (G4)**:
   - `harness_cli propose` chỉ đọc friction backlog thủ công. Không có sổ KPI đo `dod_pass_rate`, `tokens`, `fp_flags` theo từng agent để phát hiện suy giảm sớm.

---

## 2. Quyết Định Kiến Trúc

### A. Chuẩn hóa Taxonomy 3 lớp tác nhân
Phân biệt bắt buộc: **operator** (script tất định 0-token) · **cognitive** (subagent LLM có phí) · **conductor** (bộ điều phối đọc manifest). Tài liệu và registry BẮT BUỘC ghi rõ `class`. Cấm gọi operator là "agent".

### B. Spine 1 — Agent Registry (`.agents/registry.yaml`)
Nguồn chân lý duy nhất khai báo mọi tác nhân theo schema thống nhất (`id`, `class`, `status`, `model`, `io_boundary`, `tools_allowed`, `dod_contract`, `cost_budget`, `kpis`, `owner_rules`). Rules/skills tham chiếu về registry thay vì lặp lại (chống drift G5).

### C. Spine 2 — Pipeline DAG Manifest (`.agents/pipeline.yaml`)
Biến quy trình 5-phase văn xuôi thành DAG khai báo (`stages[]` với `needs`, `gate`, `wave`, `optional`). `pipeline_radar` đọc manifest để suy ra stage kế tiếp và chính sách wave, thay cho hardcode. Ghi rõ `invariants` mà Conductor phải tuân (WIP=1, Controlled Wave, No Script Emulation, Gate-before-advance, Metric hook).

### D. Spine 3 — Per-Agent KPI Ledger (`harness.db` schema v2)
Thêm bảng `agent_metrics` (migration `002-agent-metrics.sql`) và lệnh CLI `metric` (ghi) + `query agent-metrics` (rollup). Nâng cấp `init_db` áp dụng tuần tự mọi migration `NNN-*.sql` (idempotent qua `IF NOT EXISTS`). Nâng cấp `propose` đọc trend per-agent: gắn cờ agent có `dod_pass_rate < 95%` hoặc `fp_flags > 0`, nâng lane `high-risk` khi vượt ngưỡng.

### E. Sinh 6 cognitive agent đặc nhiệm (status: draft)
`story-dedup-clusterer`, `materiality-triage`, `entity-curator`, `adversarial-dod-verifier`, `daily-brief-synthesizer`, `harness-auditor`. Mỗi agent có 1 SKILL.md + 1 entry registry + 1 stage pipeline. `entity-curator` tier high-risk, cần ADR riêng khi kích hoạt (chạm Data Contract catalog).

---

## 3. Hệ quả

- **Tích cực**: Thêm agent trở thành thao tác khai báo có kiểm soát (registry + pipeline + story + KPI). Điều phối kiểm toán được. Vòng tự cải tiến có dữ liệu định lượng per-agent. Diệt trùng lặp bất biến.
- **Chi phí**: Nâng schema `harness.db` lên v2 (bất khả hồi khi đã áp dụng, nhưng idempotent và tương thích ngược — bảng cũ nguyên vẹn). Tăng bề mặt tài liệu `.agents/`.
- **Kiểm chứng**: `tests/test_harness_cli.py` mở rộng (7 test, 100% pass), gồm test ledger + propose tự gắn cờ agent lệch chuẩn. Migration đã áp dụng lên `harness.db` thật (schema_version=2).

---

## 4. Bằng chứng (Proof)

- `python scripts/harness_cli.py init` → `schema_version: 2`, applied `[001-init.sql, 002-agent-metrics.sql]`.
- `python scripts/harness_cli.py query contract` → capabilities gồm `metric`, `agent-metrics`.
- `python scripts/harness_cli.py propose` → `agent_metric_proposals` tự phát hiện agent `dod_pass_rate=80%` + `fp_flags=1`, nâng lane `high-risk`.
- `python -m pytest tests/test_harness_cli.py -q` → 7 passed.
