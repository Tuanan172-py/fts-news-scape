# AGENTS.md — Entrypoint & authority gate (news-scape)

> Read this FIRST every session. It is a small, stable shim. Detail lives in `docs/`.
> **App is what users touch. The harness is what agents touch.**

## 0. Rule number one — Classify Per-Prompt into 3 Tiers & Harness Closure

Mọi prompt/yêu cầu đều được phân loại vào **3 Cấp độ Tầm quan trọng** và BẮT BUỘC kết thúc bằng **Bảng Nghiệm thu Đóng phiên (Harness Closure Protocol)**:

```
Mọi Yêu cầu (Prompt)
  ├─ Cấp 1: TINY (Hỏi đáp, tra cứu, giải thích, patch 1-2 dòng)
  │    └─ Không chặn WIP → Trả lời/Patch → Minimal Trace vào harness.db → Harness Closure Table.
  ├─ Cấp 2: NORMAL (Tính năng mới, refactor, nghiên cứu chuyên sâu)
  │    └─ Intake → Bounded Context → WIP=1 → Story US-XXX → Proof test → Standard Trace → Closure Table.
  └─ Cấp 3: HIGH-RISK (Đổi DB Schema, sửa Data Contract, API token, Harness Core)
       └─ Intake → Dừng tại Hard Gate (status: blocked) → Lập ADR → Human Duyệt → Detailed Trace → Closure Table.
```


## 1. WIP = 1

At most **one** story `in_progress` at a time. If an urgent request interrupts, park the current story (`blocked` or `deferred`, with reason) BEFORE starting the new one. Never two `in_progress`.

## 2. OKF — where to get product context (priority order)

Read these before inventing context; do NOT create a new knowledge folder:
1. `project/docs/skills/*` — per-domain scraper knowledge (cafef, fireant, rss-sources, tnck).
2. `project/docs/{design,dev,domains,operations}/` — architecture, how-tos, source taxonomy, ops.
3. `project/docs/charter.md` + `project/docs/ARCHITECTURE.md` — goals, phases, TDRs.
4. repo `okf/` — cross-cutting operational knowledge.

## 3. Project build / run (the product lives in `project/`)

```powershell
cd project
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
python -m src.morninger            # daytime pipeline (capture + re-derive Silver + drift)
python scripts/run_once.py         # one cycle
python -m pytest tests/ -v         # tests
python -m src.monitor.health       # health check
```

## 4. Harness map (read as the phase needs — bounded context)

| Doc | Purpose |
|-----|---------|
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Vocabulary (read once). |
| [docs/HARNESS.md](docs/HARNESS.md) | The collaboration model + change loop + Done definition. |
| [docs/FEATURE_INTAKE.md](docs/FEATURE_INTAKE.md) | Risk classification → lane (do this before any change). |
| [docs/CONTEXT_RULES.md](docs/CONTEXT_RULES.md) | Bounded context & token budgets (Phase × Lane). |
| [docs/TRACE_SPEC.md](docs/TRACE_SPEC.md) | 3-tier trace schema & scoring specification. |
| [docs/HARNESS_COMPONENTS.md](docs/HARNESS_COMPONENTS.md) | 11 runtime responsibilities. |
| [docs/HARNESS_MATURITY.md](docs/HARNESS_MATURITY.md) | H0–H5 maturity ladder & criteria. |
| [docs/TOOL_REGISTRY.md](docs/TOOL_REGISTRY.md) | Tool manifest & degrade ladder. |
| [docs/HARNESS_AUDIT.md](docs/HARNESS_AUDIT.md) | Entropy scoring & 6 drift checks. |
| [docs/IMPROVEMENT_PROTOCOL.md](docs/IMPROVEMENT_PROTOCOL.md) | Closed-loop propose & outcome measurement. |
| [docs/TEST_MATRIX.md](docs/TEST_MATRIX.md) | Proof vocabulary & live proof table query. |
| [docs/SESSION-LATEST.md](docs/SESSION-LATEST.md) | "Where am I, what next" — read at start, overwrite at end. |

## 5. Harness CLI (Durable Layer H2-H5)

```powershell
python scripts/harness_cli.py query contract   # Check harness capabilities & schema state
python scripts/harness_cli.py query matrix     # Query live story proof matrix
python scripts/harness_cli.py audit            # Run entropy & drift audit
python scripts/harness_cli.py propose          # Generate self-improvement proposals
```

Maturity: this harness is at **H2-H5 (Durable SQLite + Active Observability + Auto-Verification + Self-Improvement Protocol)**.

## 6. Core Architecture Boundaries & Invariants (Scope Định vị Toàn Dự Án)

### A. Ranh giới Phân công Nghiệp vụ (Scripts Automate vs Gold Agents)
1. **Hạ tầng Scripts Automate (0 Token • Tốc độ Tức thì)**:
   - **Bronze**: Cào mã nguồn và lưu trữ nguyên bản bất biến (`raw_html` + `.meta.json`) phục vụ audit và kiểm chứng SHA256.
   - **Silver**: Chuẩn hóa DOM, tính SimHash biến đổi và **tinh lọc dữ liệu thành các đoạn văn thuần túy (`<p>`)**.
   - **Task Packaging**: Đóng gói các file `.task.json` chứa payload văn bản sạch vào `data/agent_tasks/`.
   - **Quality Ingest & Gating**: Kiểm tra hợp đồng DoD Schema, nạp database SQLite (`monocle.db`).
   - **User Delivery**: Phân tuyến theo danh sách theo dõi người dùng và xuất file `users/output/<user>/<date>.xlsx`.
2. **Vùng Trí tuệ Tầng Gold (Agents Realm — Đảm nhận ĐỦ 2 Lớp Nghiệp vụ)**:
   - **Lớp 1 (Xác định Thực thể — Entity Recognition)**: Nhận diện mã CP (3 ký tự in hoa), doanh nghiệp, sàn niêm yết, ngành kinh doanh, chỉ số từ tiêu đề & nội dung (`l1-entity-output-v1`).
   - **Lớp 2 (Xử lý Nội dung & Ngữ nghĩa — Content Processing)**: Tóm tắt súc tích, viết hàm ý thị trường (`implication`), chấm điểm `materiality_score` động (`0.1 - 1.0`), phân loại `sentiment`, và trích xuất `citations` ($\ge 2$ trích dẫn $\ge 20$ ký tự nguyên văn) (`agent-output-v1`).

### B. Quy chuẩn Dữ liệu Handoff & Gom Lô (Lean Payload & Mini-Batch Invariants)
- **Zero-Waste Task Packet**: Dữ liệu packet gửi cho Agent BẮT BUỘC chỉ chứa các trường cốt lõi; loại bỏ 100% `structure.links` (hàng ngàn thẻ links menu/header/footer) và `images` để nén dung lượng dưới 10 KB (giảm 96% token input thừa).
- **Verbatim Extractive Paragraph Pruning**: Lọc sạch rác tòa soạn, teaser ("Bài liên quan"), hotline, email, copyright theo **nguyên khối đoạn văn (`<p>`)**. Tuyệt đối không chỉnh sửa câu từ trong đoạn văn giữ lại để đảm bảo tính nguyên văn exact substring cho Grounded Citations ($\ge 20$ ký tự) qua cổng DoD.
- **Consolidated Mini-Batch Handoff**: Hỗ trợ gom lô 5–10 tasks vào một file `batch_XX.task.json`, giúp Subagent xử lý trong 1 lần đọc và 1 lần ghi (giảm 90% số Tool Calls I/O).
- **Tiếp sức Thực thể L1 $\rightarrow$ Gold**: Tự động bơm sẵn `input.l1_entities` vào Gold task để Agent tập trung suy luận hàm ý thị trường.
- **Bảo toàn Raw Gốc**: Bản gốc `raw_html` và `meta.json` luôn được lưu giữ nguyên bản tại Bronze để kiểm toán.

### C. Cấm Tuyệt đối Giả lập Trí tuệ Agent bằng Heuristic Script (No Script Emulation)
- **Không tự viết script bypass Agent**: Tuyệt đối không dùng regex hay code heuristic để tự sinh kết quả phân tích Gold/L1.
- **Vùng độc quyền của Subagents**: Xử lý ngữ nghĩa, trích xuất thực thể, tóm tắt, suy luận hàm ý và trích dẫn citations là vùng trí tuệ độc quyền của Subagents LLM (Model: Flash/Pro) được kích hoạt qua `invoke_subagent`.
- **Zero Hallucination User Manifest**: Khi báo cáo phân phối và định tuyến tin, chỉ được phép tham chiếu người dùng thực tế được định nghĩa trong `manifest.yaml` (hiện tại: `AnPT`).



