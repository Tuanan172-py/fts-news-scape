# Phase 02 — H2: L1 cognitive pilot (Option A, PTC)

- Parent: [plan.md](plan.md) · Token: **flash** · DB write: **có (qua `l1_ingest`)**
- Phụ thuộc: H1 · Bắt buộc qua **cổng cấp quyền ADR 0008** ở mỗi lần chạy.

## Mục tiêu

Chạy **một wave L1 thật** bằng subagent in-process do DSH điều phối, không gọi `agy`, đúng demand-driven, có ghi metric. Đây là bằng chứng DSH thay được `invoke_subagent` thủ công.

## Deliverable

- Row `agent_l1` trong preset conductor (patch).
- Skill conductor bổ sung: activation gate → produce demand-driven → spawn wave → ingest → metric.
- Không tạo tool operator định kiểu (để H3).

## Cấu hình agent_l1

```yaml
- id: tool-presentation
  name: '@deepseek-ai/dsh-agent-tool-presentation'
  config: { mode: ptc }
- id: tools
  name: '@deepseek-ai/dsh-tools'
  config: { maxParallelSubCalls: 3 }        # = concurrency 3 của registry
- id: agent-l1
  name: '@deepseek-ai/dsh-tool-subagent'
  config:
    provider: spawn
    toolName: agent_l1
    persona: >-
      Bạn là l1-entity-matcher. Chỉ đọc task packet L1 và ghi output JSON theo
      l1-entity-output-v1. Không dùng discovery tools. Không suy đoán ngoài title.
      Nguồn chân lý ontology: .agents/skills/l1-entity-matcher/SKILL.md
    agentOptions: { provider: deepseek-official, model: deepseek-flash }
    toolFilter: { allow: [read, write] }
    maxDepth: 0
    backgroundMode: one-shot
```

## Quy trình conductor

1. **Gate ADR 0008** — hỏi người xác nhận; hiển thị wave, số bài, model, ước lượng token, effort.
2. **Demand-driven produce** — `l1_route.py --from-db --date today --review missed --limit 75` (3×25), không sinh packet thừa.
3. **Spawn wave** — gọi `tools.agent_l1` 3 lần song song trong `run_code`; trần 3 do `maxParallelSubCalls`.
4. **Ingest** — `l1_ingest.py data/agent_outputs_l1` (gate dod#l1).
5. **Metric** — `harness_cli.py metric --agent l1-entity-matcher`.
6. Dừng sạch nếu vượt trần token.

## Trần token đề xuất

| Tham số | Giá trị | Căn cứ |
|---|---|---|
| Wave | 3 batch × 25 = 75 bài | registry `wave.batch=25, concurrency=3` |
| Trần token | 60.000 | budget 450/item × 75 ≈ 33.750, biên ×1.8 |
| Effort | low | ADR 0008 §2.1 phải hiển thị |

## Nghiệm thu

| Tier | Điều kiện |
|---|---|
| Unit | — |
| Integration | Child chỉ thấy `read`/`write`; gọi tool khác bị từ chối (chứng minh `toolFilter`) |
| **Platform** | 1 wave thật: DoD L1 pass ≥ 95%; 1 dòng `agent_metrics`; 0 lần gọi `agy`; cổng xác nhận hiện trước khi spawn; không packet nào ngoài wave |

## Rủi ro & rollback

- Chất lượng flash dưới PTC chưa kiểm chứng → fallback **native mode** (bỏ row presentation) rồi đo lại; đối chứng chéo với `agy` như option thay thế nếu cần.
- 163 packet cũ gây nhiễu → archive trước H2 (cần anh xác nhận).
- Rollback: revert row `agent-l1` + presentation; archive output của wave.
