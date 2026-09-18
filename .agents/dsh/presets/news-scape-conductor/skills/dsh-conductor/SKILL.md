---
name: dsh-conductor
description: Điều phối mạng lưới agent News-Scape trên DSH — đọc pipeline DAG, chạy wave cognitive qua subagent in-process, cưỡng chế cổng ADR 0008 và trần token.
---

# DSH Conductor — News-Scape

## Nguồn chân lý
- `.agents/pipeline.yaml` — DAG stage, `needs`, `gate`, `wave`.
- `.agents/registry.yaml` — class, io_boundary, model, cost_budget, kpis.
- `docs/decisions/0008` — cổng cấp quyền + trần token (BẮT BUỘC).
- `docs/decisions/0009` — quyết định DSH runtime.
- `.agents/dsh/RUNBOOK.md` — runbook vận hành toàn bộ quy trình (L1 + Gold).

## Bất biến không được vi phạm
1. **Cổng ADR 0008**: trước mọi lần tiêu token, hiển thị số batch + số bài + model + ước lượng token + effort và **hỏi người xác nhận**. Không có xác nhận thì không spawn.
2. **Chỉ model `deepseek-flash`** (DeepSeek-V41-Flash). Cấm model cao hơn.
3. **Demand-driven (Q5)**: chỉ sinh packet đúng số consumer sắp chạy. Không sinh packet thừa.
4. **Controlled Wave**: L1 3×25 bài; dừng chờ ingest đạt DoD mới sang đợt kế.
5. **Trần token**: L1 60.000 · Gold 40.000 mỗi lần activate. Vượt trần thì dừng sạch, báo phần đã làm.
6. **Gate-before-advance**: stage có `gate` phải DoD pass mới cho stage sau.
7. **Metric-after-ingest**: sau mỗi ingest ghi một dòng `agent_metrics`.

## PTC mode
Chỉ `run_code` gọi trực tiếp. Mọi tool khác gọi trong chương trình: `await tools.<name>(args)`.
Chỉ những gì `print`/`return` mới vào history; kết quả tool trung gian ở lại trong chương trình.

## Quy trình một lượt L1
1. **Trinh sát (0 token)** — trong `run_code`, chạy radar:
   ```ts
   const r = await tools.pwsh({
     command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/pipeline_radar.py status',
     description: 'Radar status' });
   return r.stdout.text;
   ```
2. **Đọc DAG** — `tools.read({ file_path: '.agents/pipeline.yaml' })` để suy stage kế tiếp.
3. **Trình cổng ADR 0008** — trả lời văn bản cho người: wave, số bài, model, est token, effort. Dừng ở đây, chờ xác nhận.
4. **Sau khi người xác nhận** — trong MỘT `run_code`:
   - Sinh packet đúng wave: `l1_route.py --from-db --date today --review missed --limit 75`
   - Spawn song song tối đa 3: `await Promise.all(batches.slice(0,3).map(b => tools.agent_l1({ description: 'L1 batch', prompt: <handoff> })))`
   - Ingest (gate `dod#l1`): `l1_ingest.py data/agent_outputs_l1`
   - Ghi metric: `harness_cli.py metric --agent l1-entity-matcher --items N --dod-pass N --dod-total N --tokens N`
   - `return` bảng tóm tắt: batch chạy, DoD pass, token thật, stage kế tiếp.
5. **Vượt trần token** → dừng, báo phần đã làm, không tự chạy tiếp.

## Prompt handoff cho agent_l1
Ngắn, tự chứa: nhắc đọc `.agents/skills/l1-entity-matcher/SKILL.md`, đọc packet, ghi output `l1-entity-output-v1`. Agent con chỉ có `read`/`write`, không có tool discovery.

## Quy trình một lượt Gold
Sau khi `l1_ingest` xanh (gate-before-advance):
1. Sinh packet Gold đúng wave: `agent_export.py --date today --require-l1 --subscriber-only --mini-batch 5` (2×5 = 10 bài).
2. Cổng ADR 0008 (est token ≈ 14.700, trần 40.000) → chờ người xác nhận.
3. Spawn tối đa 2: `await Promise.all([tools.agent_gold({ description, prompt })])` — persona đọc `.agents/skills/gold-financial-analyst/SKILL.md`.
4. Ingest (gate `dod#gold`): `agent_ingest.py data/agent_outputs`.
5. Metric: `harness_cli.py metric --agent gold-financial-analyst ...`.
6. Giao hàng: `write_user_output.py --date all`.

## Cấm
- Không gọi `agy` (giữ làm option thay thế, chưa thực thi).
- Không dùng model ngoài `deepseek-flash`.
- Không chạm `raw_html`.
- Không sinh packet khi chưa có consumer.
