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

Môi trường Python được cách ly ngoài OneDrive tại `C:\venvs\news-scape`. Tuyệt đối không tạo `.venv` nội bộ.

```powershell
# Kích hoạt môi trường (chỉ cần 1 lần / phiên terminal):
& "C:\venvs\news-scape\Scripts\Activate.ps1"

# Hoặc gọi trực tiếp Python:
# & "C:\venvs\news-scape\Scripts\python.exe" <script_path>

cd project
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
| [docs/OPEN-ITEMS.md](docs/OPEN-ITEMS.md) | Việc tồn đọng tuyến L1 → giao hàng: mục CHẶN, bước triển khai, quyết định treo. |

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
- **Subscriber-Gated Gold Export (ADR 0005)**: Chỉ xuất task Gold cho bài viết có `l1_entities` giao thoa với danh sách Watchlist của các user đang active (`manifest.yaml`). Bài không có người đăng ký lưu trữ ở trạng thái `L1_ONLY` (tiết kiệm ~38% token Gold).
- **Morphological Cú Pháp & Ranh Giới Từ L1 (ADR 0005)**: Tầng L1 code-first áp dụng `Capitalized Suffix Guard` (chặn từ viết hoa liền sau như *"Mỹ Thuận"*, *"Mỹ Tho"*, *"Mỹ Thủy"*) và `Prefix Guard` (chặn tiền tố thương hiệu/danh xưng) để triệt tiêu 100% false positive địa danh/tên người mà không tốn token.
- **Dynamic 3-Pass Semantic Pruning (2.200 Chars Max)**: Trần ký tự hạ xuống 2.200 chars. Áp dụng thuật toán 3-pass: giữ tối đa 2 đoạn đầu (Sapo) $\rightarrow$ ưu tiên quét đoạn chứa `l1_entities` và số liệu tài chính $\rightarrow$ điền đầy theo thứ tự gốc. Tuyệt đối bảo toàn nguyên khối đoạn văn (`<p>`) cho Grounded Citations ($\ge 20$ ký tự) qua cổng DoD.
- **L1 Missed-Only Review Default**: `l1_route.py` mặc định `--review missed` để 62% bài đã được code-first giải quyết chính xác đi thẳng qua `l1_ingest.py --code-first` (0 token).
- **Zero-Waste Task Packet**: Dữ liệu packet gửi cho Agent BẮT BUỘC chỉ chứa các trường cốt lõi; loại bỏ 100% `structure.links` (hàng ngàn thẻ links menu/header/footer) và `images` để nén dung lượng dưới 10 KB (giảm 96% token input thừa).
- **Consolidated Mini-Batch Handoff**: Hỗ trợ gom lô 5–10 tasks vào một file `batch_XX.task.json`, giúp Subagent xử lý trong 1 lần đọc và 1 lần ghi (giảm 90% số Tool Calls I/O).
- **Tiếp sức Thực thể L1 $\rightarrow$ Gold**: Tự động bơm sẵn `input.l1_entities` vào Gold task để Agent tập trung suy luận hàm ý thị trường.
- **Bảo toàn Raw Gốc**: Bản gốc `raw_html` và `meta.json` luôn được lưu giữ nguyên bản tại Bronze để kiểm toán.

### C. Cấm Tuyệt đối Giả lập Trí tuệ Agent bằng Heuristic Script (No Script Emulation)
- **Không tự viết script bypass Agent**: Tuyệt đối không dùng regex hay code heuristic để tự sinh kết quả phân tích Gold/L1.
- **Vùng độc quyền của Subagents**: Xử lý ngữ nghĩa, trích xuất thực thể, tóm tắt, suy luận hàm ý và trích dẫn citations là vùng trí tuệ độc quyền của Subagents LLM (Model: Flash/Pro) được kích hoạt qua `invoke_subagent`.
- **Zero Hallucination User Manifest**: Khi báo cáo phân phối và định tuyến tin, chỉ được phép tham chiếu người dùng thực tế được định nghĩa trong `manifest.yaml` (hiện tại: `AnPT`).




