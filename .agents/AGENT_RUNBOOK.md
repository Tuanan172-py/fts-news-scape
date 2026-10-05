# AGENT_RUNBOOK — Quy trình thực thi với Mạng lưới Agent

> Runbook vận hành: **chạy thế nào mỗi ngày**. Bổ trợ cho [`AGENT_NETWORK_DESIGN.md`](AGENT_NETWORK_DESIGN.md) (cái gì/tại sao).
> Nguồn chân lý tác nhân: [`registry.yaml`](registry.yaml) · DAG điều phối: [`pipeline.yaml`](pipeline.yaml) · Quy tắc: [`rules/07`](rules/07-agent-registry-governance.md), [`rules/08`](rules/08-context-and-zero-probe-guardrails.md).
> Thư viện lệnh chi tiết + prompt handoff Subagent: skill [`news-scape-agent-operations`](skills/news-scape-agent-operations/SKILL.md). Runbook này KHÔNG lặp lại các lệnh đó, chỉ chỉ dẫn thứ tự và điểm chèn.

Mọi lệnh chạy với venv cách ly: `& "C:\venvs\news-scape\Scripts\python.exe"`, `Cwd = project/`.

---

## 0. Bốn nguyên tắc thực thi (bất biến)

1. **Radar-First, Never Probe** (rule 08): một lệnh `pipeline_radar.py status` cho toàn cảnh và câu lệnh kế tiếp. Cấm dò `-c "import sqlite3..."` ad-hoc.
2. **Gate-before-advance** (pipeline.yaml invariants): stage có `gate` phải đạt DoD pass mới cho stage sau chạy.
3. **Metric-after-ingest** (Spine 3): sau mỗi operator ingest, ghi 1 dòng `agent_metrics` cho cognitive agent vừa chạy.
4. **Human-in-the-loop**: cognitive agent chỉ đề xuất; thay đổi Data Contract/catalog/schema chờ người duyệt (Tier-3 + ADR).

---

## 1. Bản đồ thực thi (stage → agent → lệnh → cổng → metric)

Đọc từ [`pipeline.yaml`](pipeline.yaml). `active` = chạy hằng ngày; `optional` = kích hoạt theo nhu cầu.

| Stage           | Agent (`class`)                 | Trạng thái | Lệnh / Kích hoạt                                                                  |       Cổng DoD       |      Ghi metric      |
| :-------------- | :-------------------------------- | :----------: | :----------------------------------------------------------------------------------- | :-------------------: | :------------------: |
| scrape          | scraper-orchestrator (op)         |    active    | `scripts/run_once.py`                                                              |          —          |          —          |
| article_pack    | article-packer (op)               |    active    | `scripts/article_run.py --wave <mã> --date <ngày> --limit <n>`                   | preflight DB + prefix |          —          |
| article_analyze | **article-processor** (cog) |    active    | `tools.agent_article` trong MỘT `run_code` — trọn `wave_<mã>.conductor.ts` |          —          | ⭐ article-processor |
| article_expand  | article-expander (op)             |    active    | `scripts/article_run.py --wave <mã> --finish`                                     |    hai lớp ≥ 90%    | ⭐ article-processor |
| deliver         | delivery-writer (op)              |    active    | `scripts/write_user_output.py --date <ngày\|today>`                                |          —          |          —          |
| story_dedup     | story-dedup-clusterer (cog)       |    draft    | theo nhu cầu, sau expand                                                            |     `dod#dedup`     |          ⭐          |
| gold_qa         | adversarial-dod-verifier (cog)    |    draft    | QA theo mẫu sau ingest                                                              |   `dod#verifier`   |          ⭐          |
| daily_brief     | daily-brief-synthesizer (cog)     |    draft    | cuối ngày                                                                          |     `dod#brief`     |          ⭐          |

Vòng quản trị (ngoài đường giao hàng): **harness-auditor** (cog, draft) — định kỳ tuần.

> Chạy một đợt: [`.agents/dsh/RUNBOOK-article-lane.md`](dsh/RUNBOOK-article-lane.md) và skill `dsh-conductor`. Nghiệm thu hạ tầng trước khi vận hành: [`rules/09`](rules/09-dsh-preflight-gate.md).
>
> **Lane L1/Gold hai tầng đã ngừng (ADR 0010, 2026-09-23).** Skill `news-scape-agent-operations` và `gold-financial-analyst` chỉ còn giá trị tham khảo lịch sử. Không gọi `l1_route.py`, `l1_ingest.py --code-first`, `agent_export.py`, `requeue.py`, `agent_l1` hay `agent_gold`. `article-processor` xử lý **trọn một bài trong một lượt**, gồm cả nhận diện thực thể lẫn phân tích nội dung; đơn vị công việc là **bài**.

---

## 2. Nhịp phiên hằng ngày

### A. Mở phiên (Radar-First)

1. Đọc Bộ ba tệp (rule 08 §2): `AGENTS.md` → `docs/SESSION-LATEST.md` → skill chuyên trách.
2. Một lệnh trinh sát duy nhất:
   ```powershell
   & "C:\venvs\news-scape\Scripts\python.exe" scripts/pipeline_radar.py status
   ```
3. Thực thi đúng câu lệnh Radar gợi ý (không tự phát minh chuỗi khác).

### B. Chạy chuỗi vận hành (theo DAG §1)

Gửi câu lệnh mồi hằng ngày (xem `news-scape-agent-operations §2 Bước 0`), Conductor chạy: **L1** (route → match → ingest) rồi **Gold** (export → analyze → ingest → deliver). Mỗi cognitive stage chờ nghiệm thu đợt hiện tại mới sang đợt kế (Controlled Wave).

### C. Đóng phiên (rule 04 Closure + rule 08 handoff)

```powershell
scripts/harness_cli.py propose        # đọc backlog + agent_metrics
scripts/harness_cli.py audit          # entropy & drift
scripts/harness_cli.py trace --story <id> --outcome completed --summary "<...>"
```

Ghi đè `docs/SESSION-LATEST.md` và xuất Bảng Harness Closure (rule 04 §3).

---

## 3. Ghi KPI Ledger sau mỗi ingest (thói quen cốt lõi)

Sau khi `l1_ingest` / `agent_ingest` báo kết quả DoD, ghi ledger để nuôi vòng tự cải tiến:

```powershell
# Ví dụ sau L1 (85 bài, 85 pass):
scripts/harness_cli.py metric --agent l1-entity-matcher --items 85 --dod-pass 85 --dod-total 85 --tokens 12250
# Ví dụ sau Gold (10 bài, 9 pass, 1 bài lệch value-added):
scripts/harness_cli.py metric --agent gold-financial-analyst --items 10 --dod-pass 9 --dod-total 10 --tokens 14700 --fp 1
```

Xem xu hướng bất kỳ lúc nào:

```powershell
scripts/harness_cli.py query agent-metrics [--agent <id>]
```

Khi `propose` gắn cờ agent (`dod_pass_rate < 95%` hoặc `fp_flags > 0`): thực hiện RCA, siết SKILL tương ứng, ghi backlog/ADR nếu tái diễn.

---

## 4. Kích hoạt một agent đặc nhiệm (draft → active)

Lần đầu dùng một agent `draft`, đi qua checklist 5 bước ([`rules/07 §4`](rules/07-agent-registry-governance.md)):

1. Phân tier (chạm Data Contract → Tier-3 → ADR).
2. Xác nhận entry `registry.yaml` + `SKILL.md` + neo `dod_contract`.
3. Bật stage tương ứng trong `pipeline.yaml` (bỏ `optional` khi đã ổn định).
4. Lập Story `US-XXX` + proof test + `harness_cli.py story complete --run-verify`.
5. Ghi KPI đầu tiên vào `agent_metrics`.
   Hoàn tất → đổi `status: draft` thành `active` trong registry.

---

## 5. Nhịp định kỳ tuần

| Việc                                  | Agent                   | Lệnh / Đầu ra                                                                                                                         |
| :------------------------------------- | :---------------------- | :--------------------------------------------------------------------------------------------------------------------------------------- |
| Dọn & mở rộng từ điển thực thể | entity-curator (Tier-3) | Đọc`unlisted_candidates` → `data/proposals/entity_catalog_delta.json` → **người duyệt** → ADR trước khi nạp catalog |
| Soát sức khỏe harness & đề xuất  | harness-auditor         | `harness_cli.py propose`/`audit` (read-only) → `docs/proposals/harness_improvement_<date>.md`                                     |

---

## 6. Xử lý sự cố nhanh (trỏ về rule)

| Triệu chứng                                          | Trỏ về                                                                                                                                     |
| :----------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------- |
| Subagent lỗi`RESOURCE_EXHAUSTED` (429)              | Giảm concurrency, chia wave nhỏ hơn —[`multi-agent-orchestrator-governance §4.3`](skills/multi-agent-orchestrator-governance/SKILL.md) |
| DoD Ingest từ chối (schema/citations/key_points)     | [`rules/01`](rules/01-subagent-guardrails.md), [`rules/05`](rules/05-gold-agent-and-payload-invariants.md)                                 |
| Lỗi ghi file / OneDrive lock / conflict`<HOSTNAME>` | [`rules/03`](rules/03-io-concurrency-guardrails.md)                                                                                         |
| Muốn dò trạng thái nhưng bị cấm probe           | Chỉ dùng`pipeline_radar.py status` — [`rules/08`](rules/08-context-and-zero-probe-guardrails.md)                                       |
| Mojibake tiếng Việt trong output                     | `encoding="utf-8"`, `ensure_ascii=False` — [`news-scape-agent-operations §4`](skills/news-scape-agent-operations/SKILL.md)            |

---

## 7. Bản đồ tham chiếu

- Ai tồn tại (tác nhân + ranh giới): [`registry.yaml`](registry.yaml)
- Điều phối (DAG + wave + invariants): [`pipeline.yaml`](pipeline.yaml)
- Thiết kế & lý do: [`AGENT_NETWORK_DESIGN.md`](AGENT_NETWORK_DESIGN.md)
- Quy tắc tăng trưởng: [`rules/07`](rules/07-agent-registry-governance.md) · Ngữ cảnh & Radar-First: [`rules/08`](rules/08-context-and-zero-probe-guardrails.md)
- Vòng đời harness & Closure: [`rules/04`](rules/04-harness-durable-invariants.md)
- Thư viện lệnh + prompt handoff: [`news-scape-agent-operations`](skills/news-scape-agent-operations/SKILL.md)
