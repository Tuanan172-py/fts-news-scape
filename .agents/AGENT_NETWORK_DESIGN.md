# AGENT_NETWORK_DESIGN — Thiết kế Mạng lưới Agent Đặc nhiệm Tự quản trị

> Trạng thái: **đã hiện thực** theo ADR 0006 — Spine 1 `registry.yaml`, Spine 2 `pipeline.yaml`, Spine 3 bảng `agent_metrics` (`harness_cli.py metric`, `query agent-metrics`, `propose`). Khảo sát gốc ngày 2026-09-15; từ 2026-09-23 Article Lane là đường xử lý duy nhất (ADR 0010), lane L1/Gold hai tầng đã ngừng.
> Mục tiêu: Xác lập kiến trúc để agents đặc nhiệm sinh sôi, tự điều phối pipeline, và tiến hóa cùng dự án — dưới sự kiểm soát tất định và ngân sách token.

---

## 0. Nguyên tắc nền (Design Axioms)

1. **Tách tuyệt đối việc tất định khỏi việc ngữ nghĩa.** Mọi việc suy luận được bằng quy tắc phải ở script 0-token; chỉ trả tiền LLM cho ngữ nghĩa. Trục này đã đúng, giữ nguyên.
2. **Agent là thực thể khai báo được, không phải văn xuôi.** Một agent chỉ tồn tại khi có entry trong Registry với hợp đồng I/O, tool, ngân sách, và DoD rõ ràng.
3. **Điều phối là dữ liệu, không phải trí nhớ con người.** Thứ tự stage, phụ thuộc, cổng chất lượng, chính sách wave phải nằm trong manifest máy-đọc-được.
4. **Không thêm được nếu không đo được.** Mỗi agent phải có KPI ghi vào harness bền vững; tăng trưởng dựa trên bằng chứng, không dựa trên cảm tính.

---

## 1. Phân loại lại 3 lớp tác nhân (Taxonomy — sửa lỗi lẫn lộn thuật ngữ)

Chuẩn hóa 3 lớp (danh sách đầy đủ ở `registry.yaml`):

| Lớp                      | Định nghĩa                            | Đặc trưng                                                      | Thành viên hiện tại                                                                                                         |
| :------------------------ | :--------------------------------------- | :---------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------ |
| **Operator**        | Script Python tất định, 0 token       | Vào/ra cố định, idempotent, không suy luận                  | `pipeline_radar`, `article_pack`, `article_expand`, `l1_ingest`, `agent_ingest`, `token_ledger`, `story_cluster`, `capture_reconcile`, `write_user_output` |
| **Cognitive Agent** | Subagent LLM gọi qua`invoke_subagent` | Có phí token, xử lý ngữ nghĩa, ràng buộc 2-I/O + grounded | `article-processor` (một bài một lượt, cả nhận diện lẫn phân tích); các agent đặc nhiệm `draft` trong registry           |
| **Conductor**       | Bộ điều phối đọc pipeline manifest | Quyết định stage kế tiếp, chính sách wave, cổng           | `master-orchestrator`: `ops_daemon` khi chạy không giám sát, phiên DSH `agent_article` khi tương tác                     |

Nguyên tắc: tài liệu, sơ đồ, registry BẮT BUỘC ghi rõ `class` của mỗi tác nhân. Cấm gọi Operator là "Agent".

---

## 2. Đánh giá hiện trạng (căn cứ để thiết kế)

### Điểm mạnh giữ nguyên

- Ranh giới 0-token infra vs LLM realm (AGENTS.md §7.1) — nền tài chính bền vững.
- Guardrails trưởng thành: 2-I/O, trích dẫn nguyên văn dựng từ chỉ số đoạn, morphological guards tiếng Việt (`entity-system-invariants.md`).
- Harness bền vững H5-ready: `harness.db` (story/intake/trace/decision/backlog), `harness_cli.py` có `audit`/`propose`.

### Khoảng trống cần lấp (định hướng thiết kế nhắm vào đây)

| Mã | Khoảng trống                                      | Hệ quả                                                 | Spine xử lý      |
| :-- | :-------------------------------------------------- | :------------------------------------------------------- | :----------------- |
| G1  | Thuật ngữ "agent" lẫn lộn Operator vs Cognitive | Không suy luận được nên thêm agent thật ở đâu | §1 Taxonomy       |
| G2  | Không có Agent Registry máy-đọc-được        | Thêm agent là việc ad-hoc, entropy tăng              | Spine 1            |
| G3  | Điều phối ngầm định trong văn xuôi SKILL    | Không kiểm toán được, phụ thuộc trí nhớ        | Spine 2            |
| G4  | Không có KPI per-agent bền vững                 | Vòng tự cải tiến thiếu dữ liệu                    | Spine 3            |
| G5  | Trùng lặp bất biến (rule 05 ↔ AGENTS.md §7)   | Sửa 1 chỗ quên chỗ khác, drift                      | Spine 1 (DRY link) |

---

## 3. Ba xương sống (Spines)

### Spine 1 — Agent Registry: `.agents/registry.yaml`

Nguồn chân lý duy nhất khai báo mọi tác nhân. Rules/skills chỉ *link* về đây (diệt trùng lặp G5).

Schema mỗi entry:

```yaml
agents:
  - id: article-processor
    class: cognitive            # operator | cognitive | conductor
    status: active              # active | draft | deprecated | retired
    model: flash
    skill: .agents/skills/l1-entity-matcher/SKILL.md
    io_boundary:
      read:  []                 # worker không có tool; packet nằm trong prompt
      write: []                 # kết quả trả trong thông điệp cuối
    tools_allowed: []
    dod_contract: dod-gatekeeper#l1
    output_schema: [article-compact-v2]
    cost_budget: { tokens_per_item: null, source: "harness.db token_ledger" }
    kpis: [turns_per_batch, parse_fail_rate, resolve_rate, dod_pass_rate]
    owner_rules: ["01-subagent-guardrails", "05-gold-agent-and-payload-invariants"]
```

Lợi ích: thêm agent = 1 entry + 1 skill + 1 ADR; kiểm toán tự động ranh giới I/O; sinh sơ đồ topology từ dữ liệu.

### Spine 2 — Pipeline DAG Manifest: `.agents/pipeline.yaml`

Biến runbook văn xuôi thành DAG khai báo. Conductor/`pipeline_radar` đọc DAG để suy ra stage kế tiếp thay vì con người ghi nhớ runbook. Khối `ops_spec` của tệp được mã vận hành đọc trực tiếp (`project/src/core/pipeline_spec.py`).

```yaml
stages:
  - id: scrape            ; agent: scraper-orchestrator ; class: operator
  - id: capture_reconcile ; agent: capture-reconciler   ; class: operator ; needs: [scrape]
  - id: story_cluster     ; agent: story-clusterer      ; class: operator ; needs: [scrape]
  - id: article_pack      ; agent: article-packer       ; class: operator
                            needs: [scrape, story_cluster] ; gate: "DB ghi được + prefix khớp"
  - id: article_analyze   ; agent: article-processor    ; class: cognitive
                            needs: [article_pack] ; wave: {batch: 100}   # một run_code cho cả đợt
  - id: article_expand    ; agent: article-expander     ; class: operator
                            needs: [article_analyze] ; gate: "độ phủ đợt >= 90% ở cả hai lớp"
  - id: deliver           ; agent: delivery-writer      ; class: operator ; needs: [article_expand]
```

Lợi ích: chính sách wave nằm trong dữ liệu; `pipeline_radar` gợi ý lệnh chính xác theo DAG; thêm agent mới chỉ là chèn 1 stage.

### Spine 3 — Per-Agent KPI Ledger: bảng `agent_metrics` trong `harness.db`

Mỗi lần ingest ghi một dòng đo lường; `harness_cli.py propose` đọc trend để đề xuất cải tiến có bằng chứng.

```sql
CREATE TABLE agent_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id   TEXT NOT NULL,
  run_ts     TEXT NOT NULL,
  items      INTEGER,
  dod_pass   INTEGER,
  dod_total  INTEGER,
  tokens     INTEGER,
  fp_flags   INTEGER,            -- false positive nghi ngờ (vd citations copy vào key_points)
  note       TEXT
);
```

Lợi ích: hiện thực hóa vòng RCA trong `multi-agent-orchestrator-governance §3` thành dữ liệu. Ví dụ đề xuất tự sinh: *"article-processor: dod_pass_rate 100% → 88% trong 7 ngày, fp_flags tăng ở key_points → siết điều khoản Value-Added trong persona."* Đợt do `ops_daemon` chạy tự ghi `agent_metrics` (`project/src/ops/wave/metrics.py`); đợt tay ghi bằng `harness_cli.py metric`.

---

## 4. Danh mục Agents đặc nhiệm nên phát triển (ưu tiên theo đòn bẩy)

Chỉ triển khai sau khi có tối thiểu Spine 1 + Spine 2.

| # | Agent                              | Class         | Vấn đề giải quyết                                                                                   | Rủi ro / Tier                                                |
| :- | :--------------------------------- | :------------ | :------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------ |
| 1 | **Story-Dedup / Clustering** | operator      | Cùng 1 sự kiện trên nhiều nguồn → bài `copy` kế thừa kết quả bài gốc                             | Đã làm tất định bằng `story-clusterer` (ADR 0016); agent cognitive đã gỡ |
| 2 | **Materiality Triage**       | —             | —                                                                                                        | Đã gỡ 2026-09-24: `materiality`/`event_type`/`impact_area` không còn là trường đầu ra |
| 3 | **Entity/Watchlist Curator** | cognitive     | `unlisted_candidates` → đề xuất bổ sung catalog kèm bằng chứng                                 | Nuôi tăng trưởng từ điển. Chạm catalog = Tier 3 (ADR) |
| 4 | **Adversarial DoD Verifier** | cognitive     | Kiểm định ngữ nghĩa (chất lượng implication, hallucination) trên mẫu                           | Feeds Spine 3. Tier 2                                         |
| 5 | **Daily Brief Synthesizer**  | cognitive     | Tổng hợp cuối ngày theo watchlist từng user                                                         | Deliverable bậc cao. Tier 2                                  |
| 6 | **Harness Auditor**          | cognitive     | Đọc trend`harness.db` → soạn proposal + ADR draft                                                  | Hiện thực hóa H5. Tier 2                                   |

---

## 5. Quy trình thêm 1 agent an toàn (Growth Governance Checklist)

Mọi agent mới đi qua đủ 5 bước bất biến:

1. **Phân tier** theo `FEATURE_INTAKE.md`. Agent LLM chạm Data Contract → Tier 3, bắt buộc ADR `docs/decisions/NNNN-*.md`.
2. **Khai báo**: entry `registry.yaml` + `SKILL.md` (prompt + Ontology) + `dod_contract`.
3. **Điều phối**: chèn stage vào `pipeline.yaml` với chính sách wave.
4. **Chứng minh**: Story `US-XXX` + proof test + `harness_cli.py story complete --run-verify`.
5. **Đo lường**: đăng ký KPI vào `agent_metrics`.

---

## 6. Lộ trình triển khai theo giai đoạn

| Giai đoạn                  | Nội dung                                                    | Đầu ra kiểm chứng                                                       |
| :--------------------------- | :----------------------------------------------------------- | :-------------------------------------------------------------------------- |
| **P1 — Khai báo**    | Spine 1 Registry + refactor rules/skills link về registry   | `registry.yaml` phủ 100% tác nhân hiện có; audit ranh giới I/O pass |
| **P2 — Điều phối** | Spine 2 DAG + nâng cấp`pipeline_radar` đọc DAG         | Radar gợi ý stage kế tiếp suy ra từ manifest, không hardcode          |
| **P3 — Đo lường**  | Spine 3`agent_metrics` + `propose` đọc trend per-agent | Một đề xuất cải tiến tự sinh từ dữ liệu thật                     |
| **P4 — Sinh sôi**    | Thêm agents đặc nhiệm#1, #2 theo Checklist §5           | 2 agent mới có Story + KPI + DoD pass                                     |

---

## 7. Ranh giới không làm (Anti-scope)

- Runner LLM xếp hạng `agy`, rồi `opencode run`, rồi OpenRouter; Claude không bao giờ là runtime thay thế (ADR-0026.D3). Không viết thêm runner ngoài thứ hạng này.
- Không thêm agent LLM cho việc script tất định giải quyết được (giữ Axiom 1).
- Không phá vỡ `harness.db` nghiệp vụ tách biệt `monocle.db`; `agent_metrics` nằm ở `harness.db`.
- Không xóa rule/skill hiện có khi refactor DRY — chỉ thay nội dung trùng bằng link về registry, giữ lịch sử.
