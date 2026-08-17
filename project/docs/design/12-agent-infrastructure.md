# Design 12 — Agent Infrastructure (Vòng 3, AGENT-AGNOSTIC, không LLM)

Cập nhật: 2026-08-17 · Trạng thái: ĐÃ TRIỂN KHAI (hạ tầng) · KHÔNG nhúng LLM.
Quyết định owner (2026-08-17): "chỉ cần hệ thống spec + infrastructure; agent tự yêu cầu sau —
tự viết prompt dựa trên spec/guideline/ràng buộc đã dựng". Liên kết: [09](09-agent-io-contract.md),
[10](10-agent-orchestration-governance.md), [11](11-e2e-standardization-governance.md).

## 1. Ý tưởng
Producer KHÔNG gọi model. Chỉ cung cấp **khung cắm** để agent của người dùng (prompt tự viết,
provider bất kỳ) tiêu thụ việc chuẩn hoá và nộp kết quả — validate + DoD làm cổng nghiệm thu.

```
work_items=pending  ──export──►  data/agent_tasks/*.task.json
        ▲                              │  (INPUT + hợp đồng OUTPUT + ràng buộc)
        │                    [AGENT NGOÀI: prompt của bạn từ agent-instructions-v1.md]
        │                              ▼
   mark_done / mark_failed  ◄─ingest─  agent-output-v1 (*.json)
        (validate schema + DoD + preconditions, lưu agent_outputs)
```

## 2. Thành phần (đã code)
| Artifact | Vai trò |
|----------|---------|
| `src/agent/dod.py` | `verify_preconditions` + `check_dod` (thuần, 5 predicate — doc 10 §5) |
| `src/agent/packet.py` | `build_task_packet` / `write_packet` — gói việc self-describing |
| `src/agent/runner.py` | `AgentRunner.export_tasks` + `ingest_output` (agent-agnostic) |
| `scripts/agent_export.py` | CLI: claim pending → ghi task-packet |
| `scripts/agent_ingest.py` | CLI: nạp output → validate+DoD → mark |
| `schemas/agent-instructions-v1.md` | bản chỉ dẫn để người dùng viết prompt |
| `agent_outputs` (bảng) | lưu output đã nghiệm thu (idempotent theo article_id+raw_sha256) |

## 3. Ranh giới rõ ràng (ai làm gì)
- **Producer (đã có):** export packet, validate, DoD, persist, cập nhật catalog. Không có LLM.
- **Agent (người dùng):** đọc packet → suy luận → emit `agent-output-v1`. Producer không quan tâm
  provider/prompt — chỉ nghiệm thu theo hợp đồng.

## 4. Exactly-once & idempotency
- Export dùng `Catalog.claim` (BEGIN IMMEDIATE) → không double-claim.
- Ingest keyed `(article_id, raw_sha256)`; đã đạt DoD → replay trả cached, không mark lại.
- `agent_outputs` UNIQUE(article_id, raw_sha256) (INSERT OR REPLACE).

## 5. Definition-of-Done (cổng nghiệm thu — mark_done ⇔ TẤT CẢ)
1. schema PASS `agent-output-v1` · 2. `confidence ≥ 0.65` · 3. `≥2 citations` & mỗi `source_span ⊂ cleaned_text`
· 4. `extraction_quality ∈ {high, medium}` · 5. `processing_metadata` đủ provider/model/timestamp.
Không đạt ⇒ `mark_failed` + lưu `dod_reasons` (không bao giờ "done" thầm lặng).

## 6. Vận hành
```
python scripts/agent_export.py 100        # xuất tối đa 100 packet
#  → giao data/agent_tasks/*.task.json cho agent của bạn, thu về *.json
python scripts/agent_ingest.py data/agent_outputs_in   # nạp cả thư mục
```

## 7. Chưa làm (khi bạn muốn nhúng agent thật)
Thêm adapter mỗi provider (gọi LLM, ép schema) — cắm vào chỗ "AGENT NGOÀI". Refine-loop/HITL
(doc 10 §3,6) tùy chọn. Hạ tầng hiện tại đủ để chạy vòng người-điều-khiển (human-in-the-loop) ngay.
