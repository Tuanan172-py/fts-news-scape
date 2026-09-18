# RUNBOOK — Conductor DSH vận hành toàn bộ quy trình xử lý ngày

- **Phiên áp dụng:** 2026-09-17
- **Trạng thái:** ✅ sẵn sàng vận hành qua preset `news-scape-conductor`
- **Phạm vi:** toàn bộ đường L1 → Gold → giao hàng theo `.agents/pipeline.yaml`
- **Hoãn:** đóng gói bundle + hard gate `ns_activate` (H3) và vòng governance (H4) — xem §6
- **Neo quyết định:** `docs/decisions/0009` · `docs/decisions/0008` · `plans/20260917-1538-dsh-harness-integration/plan.md`

---

## 0. Mở phiên Conductor (Web GUI)

Preset chỉ được chọn khi phiên **chưa sinh nội dung**. Hai cách:

1. **Đặt làm preset mặc định** — Settings → General → *Agent preset* → **News-Scape Conductor** → tạo phiên mới.
2. **Đổi trong phiên trống** — tạo phiên mới rồi chọn preset ở bộ chọn preset trước khi gửi tin đầu tiên.

Kiểm tra phiên đã đúng khung DSH:
- Catalog skill có `dsh-conductor`.
- Tool trực tiếp chỉ có `run_code` (PTC mode).
- Binding trong SDK có `pwsh`, `read`, `write`, `agent_l1`, `agent_gold`, `ask_user_question`.

Chọn **permission preset** theo việc:

| Việc | Permission | Lý do |
|---|---|---|
| H1 proof (chỉ radar) | `read-only` | không cho ghi gì |
| Chạy wave thật | `workspace-write` | cần ghi packet/output/DB; approval `ask` giữ người trong vòng lặp |

## 1. Mô hình vận hành

Một phiên DSH chọn preset `news-scape-conductor` đóng vai **Conductor**. Conductor:

- đọc `.agents/pipeline.yaml` + `.agents/registry.yaml` để biết stage kế tiếp;
- chạy operator (0 token) qua binding `pwsh`;
- gọi cognitive agent qua binding `agent_l1` / `agent_gold` (subagent in-process, Option A);
- chỉ `run_code` gọi trực tiếp (PTC mode); mọi thứ khác gọi trong chương trình.

Cognitive agent là **con in-process** của Conductor, nhận ranh giới cứng:

| Thuộc tính | Giá trị | Nguồn |
|---|---|---|
| `toolFilter.allow` | `[read, write]` | registry `tools_allowed` (2-I/O) |
| `agentOptions.model` | `deepseek-flash` | D6 — cấm model cao hơn |
| `maxDepth` | `0` | cognitive không sinh sâu thêm |
| `persona` | đọc skill chuyên trách trước | rule 01 |

## 2. Bản đồ stage 17/09 → DSH

| # | Stage | Class | Ai chạy | Lệnh / binding | Cổng | Token |
|:-:|---|---|---|---|---|:-:|
| 0 | scrape / derive | operator | morninger nền | (ngoài DSH, đang chạy) | — | 0 |
| 1 | l1_route | operator | Conductor | `pwsh → scripts/l1_route.py --from-db --date today --review missed --limit 75` | — | 0 |
| 2 | l1_match | cognitive | `agent_l1` ×3 | wave 25 bài/lô | dod#l1 | flash |
| 3 | l1_ingest | operator | Conductor | `pwsh → scripts/l1_ingest.py data/agent_outputs_l1` | ✔ | 0 |
| 4 | triage (draft) | cognitive | — | chưa bật | dod#triage | — |
| 5 | dedup (draft) | cognitive | — | chưa bật | dod#dedup | — |
| 6 | gold_export | operator | Conductor | `pwsh → scripts/agent_export.py --date today --require-l1 --subscriber-only --mini-batch 5` | — | 0 |
| 7 | gold_analyze | cognitive | `agent_gold` ×2 | wave 5 bài/lô | dod#gold | flash |
| 8 | gold_ingest | operator | Conductor | `pwsh → scripts/agent_ingest.py data/agent_outputs` | ✔ | 0 |
| 9 | deliver | operator | Conductor | `pwsh → scripts/write_user_output.py --date all` | — | 0 |
| 10 | daily_brief (draft) | cognitive | — | chưa bật | dod#brief | — |

Ghi KPI (repo root): `harness_cli.py metric --agent <id> --items N --dod-pass N --dod-total N --tokens N`.

## 3. Vòng lặp một lượt (chuẩn)

0. **Hồi phục hàng kẹt (0 token, tùy chọn)** — nếu radar báo `failed`: `project/scripts/maintenance/requeue.py --state failed --layer all --apply`.
1. **Radar (0 token)** — trong `run_code`: gọi `tools.pwsh` chạy `project/scripts/pipeline_radar.py status`; `return` phần tóm tắt.
2. **Đọc DAG** — `tools.read({ file_path: '.agents/pipeline.yaml' })`; đối chiếu `needs`/`gate` với radar để chọn stage kế.
3. **Cổng ADR 0008** — trả lời văn bản: stage, số batch, số bài, model, ước lượng token, effort. **Dừng, chờ người xác nhận.**
4. **Sau xác nhận** — trong MỘT `run_code`:
   ```ts
   // 1) sinh packet đúng wave (demand-driven)
   await tools.pwsh({ command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/l1_route.py --from-db --date today --review missed --limit 75', description: 'L1 route wave' });
   // 2) wave cognitive (trần 3 do Conductor tự giới hạn; host cap 10)
   const batches = ['l1_batch_A','l1_batch_B','l1_batch_C'];
   const res = await Promise.all(batches.map(b => tools.agent_l1({ description: 'L1 batch ' + b, prompt: 'Đọc .agents/skills/l1-entity-matcher/SKILL.md, xử lý packet ' + b + ', ghi output l1-entity-output-v1.' })));
   // 3) ingest (gate dod#l1)
   await tools.pwsh({ command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" project/scripts/l1_ingest.py data/agent_outputs_l1', description: 'L1 ingest' });
   // 4) metric
   await tools.pwsh({ command: '& "C:\\venvs\\news-scape\\Scripts\\python.exe" scripts/harness_cli.py metric --agent l1-entity-matcher --items 75 --dod-pass <P> --dod-total 75 --tokens <T>', description: 'KPI L1' });
   return { batches: batches.length, next: 'gold_export' };
   ```
5. **Gate-before-advance** — chỉ sang Gold khi `l1_ingest` xanh.
6. **Lặp cho Gold** — thay `l1_route` bằng `agent_export`, `agent_l1` bằng `agent_gold`, gate `dod#gold`, trần 40.000 token.

## 4. Trần token & dừng sạch

| Stage | Wave | Trần mỗi lần activate | Căn cứ |
|---|---|---|---|
| L1 | 3 × 25 = 75 bài | **60.000** | budget 450/bài × 75 ≈ 33.750, biên ×1.8 |
| Gold | 2 × 5 = 10 bài | **40.000** | budget 1.470/bài × 10 ≈ 14.700, biên ×2.7 |

Vượt trần: dừng, báo số batch đã xong, ghi metric phần đã làm, không tự chạy tiếp.

## 5. Bất biến

1. Không tiêu token khi chưa có xác nhận người (ADR 0008 §2.1).
2. Chỉ `deepseek-flash` (V41). Cấm `deepseek-v4-pro`.
3. Demand-driven: không sinh packet ngoài wave sắp chạy.
4. Cognitive child chỉ `read`/`write`.
5. Gate-before-advance; metric-after-ingest.
6. Không chạm `raw_html` (WORM).
7. `agy` giữ làm option thay thế, **chưa thực thi**.

## 6. Trạng thái triển khai & phần hoãn

| Hạng mục | Trạng thái |
|---|---|
| Preset `news-scape-conductor` (PTC + agent_l1 + agent_gold) | ✅ |
| Skill `dsh-conductor` | ✅ |
| D6 registry → flash | ✅ |
| H1/H2 Platform proof (phiên GUI) | ⏳ chờ người |
| H3 bundle + `ns_activate` hard gate + generator | ⏸️ hoãn (chưa cần phiên 17/09) |
| H4 governance + brief/verifier/auditor | ⏸️ hoãn |

Trong khi hoãn H3, cổng ADR 0008 là **policy do skill conductor cưỡng chế** (người xác nhận trước khi Conductor chạy wave), chưa phải hard-enforce bằng code.

## 7. Xử lý sự cố

| Triệu chứng | Xử lý |
|---|---|
| Subagent trả lỗi 429 / quá tải | giảm wave còn 1–2 batch, chờ ingest đợt hiện tại |
| DoD ingest từ chối | xem `rules/01`, `rules/05`; chạy lại đúng batch lỗi |
| Conductor không thấy binding | kiểm PTC: chỉ `run_code` gọi trực tiếp; binding nằm trong SDK prompt |
| Preset không hiện trong picker | kiểm junction `%DSH_HOME%\.agent-presets\news-scape-conductor` → repo |
| Lỡ archive phiên Conductor | DSH **không có unarchive** (archive là one-way). Dừng host → sửa `%DSH_HOME%\storages\workspace.json` cho `archivedSessionIds: []` → khởi động lại |
| Phiên chạy nhầm preset `ptc` | đặt default preset = **News-Scape Conductor** (Settings → General) TRƯỚC khi tạo phiên; phiên đã sinh nội dung không đổi được preset |

## 8. Prompt kích hoạt

Dán vào phiên Conductor để mở màn L1:

> Đọc `.agents/pipeline.yaml` và `.agents/dsh/RUNBOOK.md`. Chạy radar (0 token) rồi xác định stage kế tiếp theo DAG. Trình cổng ADR 0008 cho wave L1 đầu tiên (3×25 bài, model deepseek-flash) và **chưa thực thi cho tới khi tôi xác nhận**. Sau khi tôi xác nhận: chạy wave → `l1_ingest` → ghi metric, rồi dừng báo cáo để tôi duyệt sang Gold.

Sau khi duyệt L1, mở màn Gold:

> Tiếp tục Gold wave 1: export 2×5 bài, trình cổng ADR 0008 (trần 40.000), sau xác nhận chạy `agent_gold` → `agent_ingest` → metric, rồi `write_user_output.py --date all`.

## 9. Phạm vi tồn đọng (chỉ đọc)

`project/scripts/l1_backlog.py` là nguồn số liệu tồn đọng — **không giới hạn theo ngày**, cộng dồn toàn bộ:

| Nhóm | Số bài | Ý nghĩa |
|---|---:|---|
| T1 gold-ready | 0 | Gold xong, thiếu L1 → giao ngay, 0 token Gold |
| T2 l1-only | 6.127 | chưa L1 chưa Gold (1.232 đã có packet chờ sẵn) |
| T3 gold-next | 4.482 | đã có L1, work_item pending → Gold bốc được |
| T4 orphan | 487 l1_tasks | không có dòng trong `articles` → không bao giờ ra final.csv |

Hàng đợi thô: `l1_tasks pending=1.105 failed=85` · `work_items pending=7.058 failed=189` · packet trên đĩa L1=219, Gold=60.

⚠️ **Cảnh báo coverage:** một wave chỉ phủ **đúng scope đã route** (mặc định `--date today` + `--limit`), KHÔNG phủ backlog. Từ 2026-09-17, `pipeline_radar.py status` in dòng **"Bao phủ L1 bài đăng hôm nay"** (covered/total · needs_agent chờ · chưa định tuyến) để đo trực tiếp. Muốn phủ toàn bộ nhóm l1-only phải route lại với `--all --only in-articles` (bỏ `--date`), rồi lặp wave cho tới khi `l1_tasks pending = 0` hoặc chạm trần token. Sau mỗi wave đối chiếu `l1_backlog.py`.

## 10. Quy trình active lại Conductor (từng bước)

**Quyết định:** dùng phiên **MỚI** dưới preset `news-scape-conductor` — phiên cũ chạy `ptc`, thiếu binding `agent_l1`/`agent_gold` và skill `dsh-conductor`. Khôi phục phiên cũ chỉ để giữ lịch sử.

| # | Việc | Ghi chú |
|:-:|---|---|
| 1 | (Tùy chọn) Khôi phục phiên archive | dừng host → sửa `%DSH_HOME%\storages\workspace.json` cho `archivedSessionIds: []` |
| 2 | Settings → General → Agent preset = **News-Scape Conductor** | phải làm TRƯỚC khi tạo phiên |
| 3 | Khởi động `dsh web` | nếu vừa dừng ở bước 1 |
| 4 | Tạo phiên mới + permission `workspace-write` | approval `ask` giữ người trong vòng lặp |
| 5 | Kiểm PTC: catalog có `dsh-conductor`; tool trực tiếp chỉ `run_code` | nếu không, xem §7 |
| 6 | Dán prompt kích hoạt (§8) | mở màn L1 |
| 7 | (0 token, tùy chọn) `requeue.py --state failed --layer all --apply` | hồi phục 189 work_items + 85 l1_tasks failed |
| 8 | Conductor chạy radar → đọc DAG → trình cổng ADR 0008 | **anh xác nhận** trước khi tiêu token |
| 9 | Wave 1 L1 (3×25) → `l1_ingest` → `metric` | Conductor **dừng** báo cáo |
| 10 | Anh duyệt → Gold (2×5) → `agent_ingest` → `metric` → `write_user_output.py --date all` | bước giao hàng |

**Điểm dừng bắt buộc:** Conductor phải dừng sau mỗi wave để anh duyệt. Nếu nó tự chạy tiếp, yêu cầu dừng và ghi nhận vi phạm ADR 0008.
