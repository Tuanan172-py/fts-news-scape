---
trigger: always_on
---
# 07 — Agent Network Registry & Growth Governance

Quy tắc bất biến để mạng lưới agent đặc nhiệm sinh sôi và tự điều phối mà không tăng entropy. Nguồn chi tiết: [`.agents/AGENT_NETWORK_DESIGN.md`](../AGENT_NETWORK_DESIGN.md), ADR [`0006`](../../docs/decisions/0006-agent-network-registry-pipeline-metrics.md).

## 1. Taxonomy 3 lớp tác nhân (bắt buộc phân định)
- **operator**: script Python tất định, 0 token, vào/ra cố định, idempotent.
- **cognitive**: subagent LLM gọi qua `invoke_subagent`, có phí token, ràng buộc 2-I/O + grounded citations.
- **conductor**: bộ điều phối đọc `.agents/pipeline.yaml`, quyết định stage kế tiếp và chính sách wave.

Tài liệu, sơ đồ, báo cáo BẮT BUỘC ghi rõ `class`. TUYỆT ĐỐI KHÔNG gọi operator là "agent".

## 2. Nguồn chân lý (Single Source of Truth)
- Mọi tác nhân BẮT BUỘC có entry trong [`.agents/registry.yaml`](../registry.yaml). Một tác nhân không có entry là không tồn tại về mặt vận hành.
- Mọi luồng điều phối BẮT BUỘC khai báo trong [`.agents/pipeline.yaml`](../pipeline.yaml). Cấm điều phối bằng runbook văn xuôi ngoài manifest.
- Khi bất biến (I/O boundary, model, ngân sách, DoD) đã ở registry, các rule/skill khác CHỈ được link về, KHÔNG lặp lại nội dung (chống drift).

## 3. Ranh giới I/O bất biến (khớp rule 01)
- `io_boundary.read` và `io_boundary.write` trong registry là ranh giới cứng. Cognitive agent chỉ đọc/ghi đúng đường dẫn khai báo; `tools_allowed` giới hạn công cụ; cấm discovery tools khi đã khai báo 2-I/O.
- Agent tier `high-risk` (chạm Data Contract/catalog/schema) chỉ ĐƯỢC PHÉP ghi file đề xuất (`data/proposals/*`), không ghi trực tiếp nguồn dữ liệu gốc; phải qua `activation_gate` ADR trước khi `status` chuyển `active`.

## 4. Checklist thêm 1 agent an toàn (5 bước bắt buộc)
1. **Phân tier** theo [`docs/FEATURE_INTAKE.md`](../../docs/FEATURE_INTAKE.md). Cognitive agent chạm Data Contract → Tier 3 → bắt buộc ADR `docs/decisions/NNNN-*.md`.
2. **Khai báo**: thêm entry `registry.yaml` + 1 `SKILL.md` (prompt + Ontology) + neo `dod_contract`.
3. **Điều phối**: chèn 1 stage vào `pipeline.yaml` với `needs`, `gate`, chính sách `wave`.
4. **Chứng minh**: lập Story `US-XXX`, có proof test, chạy `harness_cli.py story complete --run-verify`.
5. **Đo lường**: đăng ký `kpis` trong registry; operator ingest ghi `agent_metrics` qua `harness_cli.py metric`.

Thiếu bất kỳ bước nào → agent giữ `status: draft`, không được đưa vào đường giao hàng chính.

## 5. Vòng đo lường & tự cải tiến (khớp rule 04)
- Sau mỗi đợt cognitive agent chạy, operator ingest tương ứng BẮT BUỘC ghi 1 dòng KPI:
  `python scripts/harness_cli.py metric --agent <id> --items N --dod-pass N --dod-total N [--tokens N] [--fp N]`.
- `harness_cli.py propose` đọc `agent_metrics` để gắn cờ agent `dod_pass_rate < 95%` hoặc `fp_flags > 0`. Đề xuất nâng lane `high-risk` phải được RCA và đưa vào backlog/ADR nếu tái diễn.

## 6. Bất biến điều phối (Conductor)
- **WIP = 1**: không 2 story `in_progress` đồng thời (rule 04, AGENTS.md §1).
- **Controlled Wave**: chờ nghiệm thu đợt hiện tại mới kích hoạt đợt kế (chống `RESOURCE_EXHAUSTED` 429).
- **Gate-before-advance**: stage có `gate` phải đạt DoD pass mới cho stage sau chạy.
- **No Script Emulation** (rule 05 §3): cấm dùng regex/heuristic thay thế vùng trí tuệ cognitive agent.
